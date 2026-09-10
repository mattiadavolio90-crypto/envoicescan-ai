"""Snapshot di riferimento per l'apertura al retail: cattura e confronto.

Il vincolo del piano e' che i clienti ristorazione non cambino di un centesimo.
Questo script lo rende misurabile invece che dichiarato: `capture` fotografa i
numeri che i clienti vedono oggi, `check` li ri-misura e fallisce se divergono.

Due dimensioni, entrambe sui dati veri:
  - costi: la RPC `costi_automatici_mensili` per ogni (sede, anno) con dati, che
    e' la sorgente del MOL in pagina;
  - classificazione: la categoria che i livelli DETERMINISTICI assegnano a un
    campione di righe reali. L'AI non viene mai chiamata (il campione e' fatto di
    descrizioni gia' viste): il presidio riguarda dizionario, regole e memorie.

Uso:
    python scripts/retail_baseline.py capture     # prima di toccare il codice
    python scripts/retail_baseline.py check       # a fine di ogni fase

SOLA LETTURA, garantita da due presidi indipendenti:
  1. il client passato a `categorizza_con_memoria` e' un proxy che solleva su
     insert/update/upsert/delete. NB: il chiamante cattura l'eccezione e prosegue
     (logga "Errore salvataggio memoria locale"), quindi il processo non muore —
     ma la scrittura non raggiunge il DB. Verificato per mutazione: senza
     `pending_local_saves` il conteggio di prodotti_utente resta invariato;
  2. le auto-scritture in memoria locale vengono dirottate su
     `pending_local_saves` (lista che nessuno flusha) invece che sul DB.

Il presidio 2 da solo non basta: `categorizza_con_memoria` con un client vero
scrive comunque per altre vie. La prima stesura di questo script aveva solo
l'intenzione dichiarata, e ha creato 308 voci in `prodotti_utente` sui clienti
di produzione (10/9/2026, poi rimosse).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

BASELINE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "retail_baseline"
COSTI_FILE = BASELINE_DIR / "costi_per_sede_mese.json"
CATEGORIE_FILE = BASELINE_DIR / "categorie_deterministiche.json"

# Descrizioni DISTINTE per sede nel campione di classificazione.
# Non e' un `limit` sulla query: ordinando per descrizione, un limit prenderebbe
# le prime N dell'alfabeto — cioe' un campione sbilanciato proprio dove stanno le
# descrizioni generiche. Qui si leggono tutte le righe della sede, si deduplica
# per descrizione e si campiona a passo costante su tutto l'alfabeto.
CAMPIONE_PER_SEDE = 400


class _SoloLettura:
    """Proxy sul client Supabase che lascia passare solo le letture.

    Non e' paranoia: il costo di una scrittura accidentale qui e' un dato di
    cliente alterato in produzione, e il chiamante (`categorizza_con_memoria`)
    scrive di sua iniziativa quando riconosce un prodotto.
    """

    _VIETATI = ("insert", "update", "upsert", "delete", "rpc_write")

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, nome):
        if nome in self._VIETATI:
            raise RuntimeError(f"snapshot in sola lettura: '{nome}' non e' consentito")
        valore = getattr(self._inner, nome)
        if callable(valore):
            def _wrap(*a, **k):
                return _SoloLettura(valore(*a, **k))
            return _wrap
        return valore

    def execute(self, *a, **k):
        return self._inner.execute(*a, **k)


def _client(sola_lettura: bool = True):
    from services import get_supabase_client

    vero = get_supabase_client()
    return _SoloLettura(vero) if sola_lettura else vero


def _sedi(sb) -> list[dict[str, Any]]:
    res = sb.table("ristoranti").select("id,user_id,nome_ristorante,sede_tecnica").eq("attivo", True).execute()
    return sorted(res.data or [], key=lambda r: r["nome_ristorante"])


def _anni_con_dati(sb, ristorante_id: str) -> list[int]:
    """Anni in cui la sede ha righe non cancellate.

    Legge le date invece di assumere l'anno corrente: una sede con storico su
    piu' anni deve essere fotografata su tutti, o il confronto copre meno di
    quello che il cliente vede.
    """
    res = (
        sb.table("fatture")
        .select("data_documento,data_competenza")
        .eq("ristorante_id", ristorante_id)
        .is_("deleted_at", "null")
        .execute()
    )
    anni = set()
    for row in res.data or []:
        data = row.get("data_competenza") or row.get("data_documento")
        if data:
            anni.add(int(str(data)[:4]))
    return sorted(anni)


def _cattura_costi(sb) -> dict[str, Any]:
    from config.constants import CATEGORIE_SPESE_GENERALI

    out: dict[str, Any] = {}
    for sede in _sedi(sb):
        for anno in _anni_con_dati(sb, sede["id"]):
            res = sb.rpc(
                "costi_automatici_mensili",
                {
                    "p_user_id": sede["user_id"],
                    "p_ristorante_id": sede["id"],
                    "p_anno": anno,
                    "p_cat_food": [],
                    "p_cat_spese": list(CATEGORIE_SPESE_GENERALI),
                    "p_escludi_da_verificare": False,
                },
            ).execute()
            for riga in res.data or []:
                chiave = f"{sede['nome_ristorante']}|{anno}|{riga['mese']:02d}"
                out[chiave] = {
                    "food": f"{float(riga['food']):.2f}",
                    "spese": f"{float(riga['spese']):.2f}",
                }
    return out


def _azzera_cache_memoria() -> None:
    """Riporta la cache in-memory di ai_service allo stato di processo appena avviato."""
    from services import ai_service

    with ai_service._cache_lock:
        ai_service._memoria_cache["loaded"] = False
        ai_service._memoria_cache["_loaded_at"] = 0.0
        ai_service._memoria_cache["_loaded_user_ids"] = set()
        for chiave in ("prodotti_utente", "prodotti_utente_norm"):
            if chiave in ai_service._memoria_cache:
                ai_service._memoria_cache[chiave] = {}


def _cattura_categorie(sb) -> dict[str, Any]:
    from services.ai_service import carica_memoria_completa, categorizza_con_memoria

    out: dict[str, Any] = {}
    scarti: list[dict[str, Any]] = []
    for sede in _sedi(sb):
        # La cache di ai_service e' di PROCESSO e condivisa fra utenti: la sede
        # elaborata per seconda eredita lo stato lasciato dalla prima, e la
        # stessa riga puo' uscire con categorie diverse (misurato il 10/9/2026:
        # 11 divergenze su 400 righe di una sede, a seconda dell'ordine).
        # Azzerarla prima di ogni sede rende lo snapshot riproducibile.
        # NB: e' un difetto del prodotto, non dello snapshot — vale anche per il
        # worker in produzione, che elabora piu' clienti nello stesso processo.
        _azzera_cache_memoria()
        from utils.supabase_paging import fetch_all

        righe_tutte = fetch_all(
            sb.table("fatture")
            .select("descrizione,fornitore,unita_misura,prezzo_unitario,totale_riga,quantita")
            .eq("ristorante_id", sede["id"])
            .is_("deleted_at", "null")
            .order("descrizione")
        )
        # Deduplica per (descrizione, fornitore): e' la coppia che i livelli L5
        # (regola fornitore) e L2/L3 (memorie) distinguono davvero.
        #
        # ATTENZIONE — "la prima riga trovata" NON e' deterministica: su questa
        # sede 659 chiavi su 1.817 hanno righe con prezzo/quantita' diversi, e
        # `order("descrizione")` non ordina fra pari. Poiche' il prezzo e' un
        # input della classificazione (il gate delle diciture e' `prezzo == 0`),
        # pescare una riga diversa cambia la categoria e lo snapshot diverge da
        # se stesso. Si sceglie sempre la stessa riga con un criterio esplicito:
        # prezzo, poi quantita', poi totale.
        gruppi: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for r in righe_tutte or []:
            chiave = ((r.get("descrizione") or "").strip(), (r.get("fornitore") or "").strip())
            if chiave[0]:
                gruppi.setdefault(chiave, []).append(r)

        def _ordinamento(r: dict[str, Any]) -> tuple[float, float, float]:
            return (
                float(r.get("prezzo_unitario") or 0),
                float(r.get("quantita") or 0),
                float(r.get("totale_riga") or 0),
            )

        distinte = [
            sorted(righe_g, key=_ordinamento)[0]
            for _chiave, righe_g in sorted(gruppi.items())
        ]
        if not distinte:
            continue
        # Passo costante invece dei primi N: copre tutto l'alfabeto.
        passo = max(1, len(distinte) // CAMPIONE_PER_SEDE)
        righe = distinte[::passo][:CAMPIONE_PER_SEDE]

        # La cache va caricata per l'utente della sede: i livelli L2 (memoria
        # locale) e L3 (globale) leggono da li'. Senza, il campione misurerebbe
        # solo dizionario e regole, cioe' meno di meta' dei livelli.
        try:
            carica_memoria_completa(sede["user_id"], supabase_client=sb)
        except Exception as exc:  # pragma: no cover - difensivo
            print(f"  ! cache non caricata per {sede['nome_ristorante']}: {exc}", file=sys.stderr)

        for riga in righe:
            desc = (riga.get("descrizione") or "").strip()
            if not desc:
                continue
            categoria = categorizza_con_memoria(
                desc,
                riga.get("prezzo_unitario") or 0,
                riga.get("quantita") or 0,
                user_id=sede["user_id"],
                supabase_client=sb,
                # Dirotta le auto-scritture in memoria locale su una lista che
                # nessuno flusha: senza, la sola lettura del campione creerebbe
                # voci in prodotti_utente (e' gia' successo).
                pending_local_saves=scarti,
                fornitore=riga.get("fornitore"),
                unita_misura=riga.get("unita_misura"),
                totale_riga=riga.get("totale_riga"),
            )
            if isinstance(categoria, tuple):
                categoria = categoria[0]
            forn = (riga.get("fornitore") or "").strip()
            out[f"{sede['nome_ristorante']}|{forn}|{desc}"] = categoria
    return out


def _scrivi(path: Path, dati: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dati, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _diff(atteso: dict[str, Any], attuale: dict[str, Any]) -> list[str]:
    problemi = []
    for chiave in sorted(set(atteso) | set(attuale)):
        prima, dopo = atteso.get(chiave), attuale.get(chiave)
        if prima != dopo:
            problemi.append(f"  {chiave}: {prima!r} -> {dopo!r}")
    return problemi


def capture() -> int:
    sb = _client()
    print("Costi per sede/anno/mese (RPC di produzione)...")
    costi = _cattura_costi(sb)
    _scrivi(COSTI_FILE, costi)
    print(f"  {len(costi)} righe -> {COSTI_FILE.name}")

    print("Categorie deterministiche su righe reali...")
    categorie = _cattura_categorie(sb)
    _scrivi(CATEGORIE_FILE, categorie)
    print(f"  {len(categorie)} righe -> {CATEGORIE_FILE.name}")
    return 0


def check() -> int:
    if not COSTI_FILE.exists() or not CATEGORIE_FILE.exists():
        print("Baseline assente: esegui prima `capture`.", file=sys.stderr)
        return 2

    sb = _client()
    problemi: list[str] = []

    costi_attesi = json.loads(COSTI_FILE.read_text(encoding="utf-8"))
    diff_costi = _diff(costi_attesi, _cattura_costi(sb))
    if diff_costi:
        problemi.append(f"COSTI/MOL divergenti ({len(diff_costi)}):\n" + "\n".join(diff_costi[:20]))

    cat_attese = json.loads(CATEGORIE_FILE.read_text(encoding="utf-8"))
    diff_cat = _diff(cat_attese, _cattura_categorie(sb))
    if diff_cat:
        problemi.append(f"CATEGORIE divergenti ({len(diff_cat)}):\n" + "\n".join(diff_cat[:20]))

    if problemi:
        print("\n\n".join(problemi), file=sys.stderr)
        print("\nI clienti ristorazione vedrebbero numeri diversi: la fase NON e' chiusa.", file=sys.stderr)
        return 1

    print(f"Diff a zero: {len(costi_attesi)} righe di costi e {len(cat_attese)} categorie invariate.")
    return 0


if __name__ == "__main__":
    azione = sys.argv[1] if len(sys.argv) > 1 else ""
    if azione == "capture":
        sys.exit(capture())
    if azione == "check":
        sys.exit(check())
    print(__doc__)
    sys.exit(2)
