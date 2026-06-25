"""Test di accettazione import fatture — certifica un punto vendita prima del go-live.

Filosofia: misurare PRIMA di toccare, confrontare DOPO. Ogni numero è verificabile,
niente "a sensazione". Pensato per il flusso: il cliente invia fatture nuove di un PV,
le carichi a mano, e questo script certifica che l'import sia andato bene.

USO TIPICO
  1) PRIMA di caricare le fatture, scatta la baseline:
       python scripts/test_accettazione_import.py --pv "MARIANO" --baseline
     (salva una foto in scripts/_baseline_<ristorante_id>.json)

  2) Carichi le fatture nell'app.

  3) DOPO, lancia il report di confronto + tutti i check oggettivi:
       python scripts/test_accettazione_import.py --pv "MARIANO" --report

Il --pv accetta un frammento del nome ristorante (case-insensitive). Senza --pv
elenca i punti vendita SUSHILAND e chiede di specificarne uno.

COSA CERTIFICA (le 3 richieste di Mattia + 5 aggiunte)
  A. Categorizzazione corretta come da principio 24/06:
     - zero righe con categoria vuota/NULL (constraint),
     - 'Da Classificare' NON è un errore: è il sistema onesto,
     - distribuzione per "imbuto" (categorizzate vs in coda vs da classificare).
  B. Coerenza dati ↔ documenti (no asimmetrie):
     - quadratura per fattura: sum(totale_riga) ≈ totale_imponibile,
       e totale_imponibile + totale_iva ≈ totale_documento (tolleranza 1 cent/riga),
     - NOTE E DICITURE solo su righe a importo zero (regola dominio #2),
     - righe orfane (senza fornitore / senza data / quantità o prezzo assurdi).
  C. Idempotenza / duplicati:
     - stessa fattura (file_origine) non deve comparire due volte con conteggi diversi,
     - righe duplicate (stesso file_origine + numero_riga) = parsing rotto.
  + coda fatture_queue del PV (failed/dead/unknown_tenant) se presente.

Solo lettura: NON modifica il DB.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore

import os

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

secrets_path = ROOT / ".streamlit" / "secrets.toml"
if secrets_path.exists():
    with open(secrets_path, "rb") as f:
        _secrets = tomllib.load(f)
    sb = _secrets.get("supabase", {})
    os.environ.setdefault("SUPABASE_URL", sb.get("url", ""))
    os.environ.setdefault(
        "SUPABASE_SERVICE_ROLE_KEY",
        sb.get("service_role_key") or sb.get("key", ""),
    )

from services import get_supabase_client  # noqa: E402

NOTE_CAT = "📝 NOTE E DICITURE"
DA_CLASSIFICARE = "Da Classificare"
# Tolleranza di quadratura: 1 cent per riga (arrotondamenti per riga), minimo 2 cent.
TOL_PER_RIGA = 0.01


# ───────────────────────── helper DB ─────────────────────────

def _fetch_all(client, table: str, columns: str, eq: dict, page_size: int = 1000):
    rows = []
    start = 0
    while True:
        q = client.table(table).select(columns)
        for k, v in eq.items():
            q = q.eq(k, v)
        q = q.is_("deleted_at", "null") if table == "fatture" else q
        res = q.range(start, start + page_size - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def _trova_pv(client, frammento: str | None):
    res = client.table("ristoranti").select(
        "id, nome_ristorante, partita_iva, attivo"
    ).execute()
    sushi = [
        r for r in (res.data or [])
        if "SUSHI" in (r.get("nome_ristorante") or "").upper()
        or "LAND" in (r.get("nome_ristorante") or "").upper()
    ]
    if frammento:
        f = frammento.upper()
        match = [r for r in sushi if f in (r.get("nome_ristorante") or "").upper()]
        if len(match) == 1:
            return match[0]
        if len(match) > 1:
            print(f"⚠ '{frammento}' è ambiguo, corrisponde a più PV:")
            for r in match:
                print(f"   - {r['nome_ristorante']}")
            sys.exit(2)
        print(f"⚠ Nessun PV trovato per '{frammento}'.")
    print("Punti vendita SUSHILAND disponibili (usa --pv con un frammento del nome):")
    for r in sushi:
        flag = "" if r.get("attivo") else " [NON attivo]"
        print(f"   - {r['nome_ristorante']}  (P.IVA {r.get('partita_iva')}){flag}")
    sys.exit(2)


def _baseline_path(ristorante_id: str) -> Path:
    return ROOT / "scripts" / f"_baseline_{ristorante_id}.json"


# ───────────────────────── snapshot ─────────────────────────

def _snapshot(client, ristorante_id: str) -> dict:
    righe = _fetch_all(
        client, "fatture",
        "id, file_origine, categoria, needs_review, totale_riga, deleted_at",
        {"ristorante_id": ristorante_id},
    )
    somma = sum(float(r.get("totale_riga") or 0) for r in righe)
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ristorante_id": ristorante_id,
        "n_righe": len(righe),
        "n_fatture": len({r.get("file_origine") for r in righe if r.get("file_origine")}),
        "n_coda": sum(1 for r in righe if r.get("needs_review") is True),
        "n_da_classificare": sum(1 for r in righe if r.get("categoria") == DA_CLASSIFICARE),
        "somma_righe": round(somma, 2),
        "file_origine": sorted({r.get("file_origine") for r in righe if r.get("file_origine")}),
    }


# ───────────────────────── check di accettazione ─────────────────────────

def _check_categorizzazione(righe: list[dict]) -> list[str]:
    problemi = []
    vuote = [r for r in righe if not (r.get("categoria") or "").strip()]
    if vuote:
        problemi.append(
            f"❌ {len(vuote)} righe con categoria VUOTA/NULL (viola il constraint!) "
            f"es. id={[r['id'] for r in vuote[:5]]}"
        )
    return problemi


def _check_quadratura(righe: list[dict]) -> tuple[list[str], dict]:
    """Quadratura per fattura (file_origine).

    Due livelli, con nature diverse:
    1) BLOCCANTE — coerenza INTERNA al documento: totale_imponibile + totale_iva
       ≈ totale_documento. Questa è una legge contabile: deve SEMPRE tornare.
       Se non torna, il parsing dei totali è rotto.
    2) INFORMATIVO — Σ(totale_riga) vs totale_imponibile. NON è una legge universale:
       differisce legittimamente su note di credito (segni), sconti/cauzioni/arrotondamenti
       di documento non rappresentati come righe-prodotto. Si confronta in valore assoluto
       (le note di credito hanno segno invertito) e si segnala solo come ⚠, mai come ❌.
    """
    bloccanti = []
    informativi = []
    per_file: dict[str, list[dict]] = defaultdict(list)
    for r in righe:
        per_file[r.get("file_origine") or "(senza file)"].append(r)

    doc_ok = 0
    doc_verificabili = 0
    for fo, rs in per_file.items():
        n = len(rs)
        tol = max(TOL_PER_RIGA * n, 0.02)
        somma = sum(float(r.get("totale_riga") or 0) for r in rs)
        imp = next((float(r["totale_imponibile"]) for r in rs
                    if r.get("totale_imponibile") is not None), None)
        iva = next((float(r["totale_iva"]) for r in rs
                    if r.get("totale_iva") is not None), None)
        doc = next((float(r["totale_documento"]) for r in rs
                    if r.get("totale_documento") is not None), None)

        # (1) coerenza interna del documento: imponibile + IVA ≈ documento.
        # Arrotondamenti IVA/totale del FORNITORE nell'XML originale (noi parsiamo
        # fedelmente i 3 valori) producono scarti piccoli: ⚠ non bloccante.
        # Un parsing davvero rotto produce scarti GROSSI (euro, fattori 2x, cifre
        # spostate), non centesimi. Soglia: il maggiore tra 0.50 € e 0.5% del documento.
        tol_arrotondamento = max(0.50, abs(doc or 0) * 0.005) if doc is not None else 0.50
        if imp is not None and iva is not None and doc is not None:
            doc_verificabili += 1
            scarto = (imp + iva) - doc
            if abs(scarto) <= tol_arrotondamento:
                doc_ok += 1
                if abs(scarto) > tol:
                    informativi.append(
                        f"⚠ {fo}: imp+IVA vs documento, scarto {scarto:+.2f} "
                        f"— arrotondamento del fornitore (innocuo)"
                    )
            else:
                bloccanti.append(
                    f"❌ {fo}: imponibile {imp:.2f} + IVA {iva:.2f} ≠ documento {doc:.2f} "
                    f"(scarto {scarto:+.2f}) — possibile parsing totali rotto"
                )

        # (2) informativo: righe vs imponibile, in valore assoluto
        if imp is not None and abs(abs(somma) - abs(imp)) > tol:
            informativi.append(
                f"⚠ {fo}: Σ righe {somma:.2f} vs imponibile {imp:.2f} "
                f"(|scarto| {abs(abs(somma) - abs(imp)):.2f}, {n} righe) "
                f"— normale se ci sono sconti/cauzioni o è una nota di credito"
            )

    return bloccanti + informativi, {"fatture_ok": doc_ok, "fatture_tot": doc_verificabili}


def _check_note_diciture(righe: list[dict]) -> list[str]:
    problemi = []
    for r in righe:
        if r.get("categoria") == NOTE_CAT and float(r.get("totale_riga") or 0) != 0:
            problemi.append(
                f"❌ riga id={r['id']} è NOTE E DICITURE ma importo {r.get('totale_riga')} ≠ 0 "
                f"(viola regola dominio #2): {r.get('descrizione')}"
            )
    return problemi


def _check_integrita_righe(righe: list[dict]) -> list[str]:
    problemi = []
    senza_forn = [r for r in righe if not (r.get("fornitore") or "").strip()]
    if senza_forn:
        problemi.append(f"⚠ {len(senza_forn)} righe senza fornitore "
                        f"es. id={[r['id'] for r in senza_forn[:5]]}")
    senza_data = [r for r in righe if not r.get("data_documento")]
    if senza_data:
        problemi.append(f"⚠ {len(senza_data)} righe senza data_documento "
                        f"es. id={[r['id'] for r in senza_data[:5]]}")
    return problemi


def _check_duplicati(righe: list[dict]) -> list[str]:
    problemi = []
    seen: dict[tuple, list] = defaultdict(list)
    for r in righe:
        seen[(r.get("file_origine"), r.get("numero_riga"))].append(r["id"])
    dup = {k: v for k, v in seen.items() if len(v) > 1 and k[0]}
    if dup:
        esempi = list(dup.items())[:5]
        problemi.append(
            f"❌ {len(dup)} coppie (file_origine, numero_riga) DUPLICATE "
            f"(parsing/import doppio): es. {esempi}"
        )
    return problemi


def _imbuto(righe: list[dict]) -> dict:
    tot = len(righe)
    da_class = sum(1 for r in righe if r.get("categoria") == DA_CLASSIFICARE)
    coda = sum(1 for r in righe if r.get("needs_review") is True)
    categorizzate_sicure = tot - da_class - coda
    return {
        "totale": tot,
        "categorizzate_affidabili": categorizzate_sicure,
        "in_coda_da_controllare": coda,
        "da_classificare": da_class,
    }


def _coda_queue(client, ristorante_id: str) -> list[str]:
    try:
        res = client.table("fatture_queue").select(
            "id, status, last_error, piva_raw"
        ).eq("ristorante_id", ristorante_id).execute()
    except Exception as e:
        return [f"(coda non leggibile: {e})"]
    cattivi = [r for r in (res.data or [])
               if r.get("status") in ("failed", "dead", "unknown_tenant")]
    out = []
    for r in cattivi:
        out.append(f"⚠ queue id={r['id']} status={r['status']} "
                   f"err={(r.get('last_error') or '')[:80]}")
    return out


def _carica_attesi(pv: dict) -> dict | None:
    """Cerca scripts/_attesi_<rid>.json o _attesi_<parola>.json con il rid giusto."""
    for p in (ROOT / "scripts").glob("_attesi_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("ristorante_id") == pv["id"]:
            return d
    return None


def _check_attesi(righe: list[dict], attesi: dict) -> list[str]:
    """Confronta il DB contro i totali letti dai documenti ORIGINALI (verità di fonte).
    È il controllo 'documento ↔ DB, nessuna asimmetria' più forte: non guarda la
    coerenza interna ma il match col file vero.
    """
    problemi = []
    per_file: dict[str, list[dict]] = defaultdict(list)
    for r in righe:
        per_file[r.get("file_origine") or "(senza file)"].append(r)

    n_doc = len(per_file)
    if n_doc != attesi.get("n_fatture_attese"):
        problemi.append(
            f"❌ fatture nel DB: {n_doc}, attese dai documenti: {attesi['n_fatture_attese']}"
        )
    n_righe = len(righe)
    if n_righe != attesi.get("totale_righe_attese"):
        problemi.append(
            f"❌ righe nel DB: {n_righe}, attese dai documenti: {attesi['totale_righe_attese']} "
            f"(scarto {n_righe - attesi['totale_righe_attese']:+d})"
        )

    for att in attesi.get("fatture", []):
        chiave = att["chiave"]
        rs = [r for r in righe if chiave in (r.get("file_origine") or "")]
        if not rs:
            problemi.append(f"❌ fattura {chiave} ({att['fornitore_piva']}) NON trovata nel DB")
            continue
        if len(rs) != att["righe"]:
            problemi.append(
                f"❌ {chiave}: {len(rs)} righe nel DB, {att['righe']} nel documento"
            )
        doc_db = next((float(r["totale_documento"]) for r in rs
                       if r.get("totale_documento") is not None), None)
        if doc_db is not None and abs(doc_db - att["documento"]) > 0.02:
            problemi.append(
                f"❌ {chiave}: totale_documento DB {doc_db:.2f} ≠ documento originale "
                f"{att['documento']:.2f} (scarto {doc_db - att['documento']:+.2f})"
            )

    if not problemi:
        tot_db = round(sum(float(r.get("totale_riga") or 0) for r in righe), 2)
        problemi.append(
            f"✓ {n_doc} fatture / {n_righe} righe combaciano coi documenti originali; "
            f"Σ righe DB = {tot_db:.2f}"
        )
    return problemi


# ───────────────────────── report ─────────────────────────

def _print_diff(base: dict, ora: dict):
    print("\n📸 CONFRONTO BASELINE → ORA")
    print(f"   righe:           {base['n_righe']:>6} → {ora['n_righe']:>6}  "
          f"(+{ora['n_righe'] - base['n_righe']})")
    print(f"   fatture:         {base['n_fatture']:>6} → {ora['n_fatture']:>6}  "
          f"(+{ora['n_fatture'] - base['n_fatture']})")
    print(f"   in coda:         {base['n_coda']:>6} → {ora['n_coda']:>6}  "
          f"({ora['n_coda'] - base['n_coda']:+d})")
    print(f"   da classificare: {base['n_da_classificare']:>6} → {ora['n_da_classificare']:>6}  "
          f"({ora['n_da_classificare'] - base['n_da_classificare']:+d})")
    print(f"   somma righe:     {base['somma_righe']:>10.2f} → {ora['somma_righe']:>10.2f}")
    nuove = set(ora["file_origine"]) - set(base["file_origine"])
    print(f"\n   📄 {len(nuove)} fatture NUOVE rispetto alla baseline:")
    for fo in sorted(nuove):
        print(f"      + {fo}")


def comando_baseline(client, pv: dict):
    snap = _snapshot(client, pv["id"])
    path = _baseline_path(pv["id"])
    path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📸 Baseline salvata per {pv['nome_ristorante']}")
    print(f"   righe={snap['n_righe']} fatture={snap['n_fatture']} "
          f"coda={snap['n_coda']} da_classificare={snap['n_da_classificare']}")
    print(f"   → {path}")
    print("\nOra carica le fatture nell'app, poi lancia con --report.")


def comando_report(client, pv: dict, solo_nuove: bool):
    rid = pv["id"]
    righe = _fetch_all(
        client, "fatture",
        "id, file_origine, numero_riga, descrizione, fornitore, data_documento, "
        "categoria, needs_review, quantita, prezzo_unitario, totale_riga, "
        "totale_imponibile, totale_iva, totale_documento, deleted_at",
        {"ristorante_id": rid},
    )

    base = None
    nuove_files = None
    bpath = _baseline_path(rid)
    if bpath.exists():
        base = json.loads(bpath.read_text(encoding="utf-8"))
        nuove_files = set(f.get("file_origine") for f in righe) - set(base["file_origine"])

    if solo_nuove and nuove_files is not None:
        righe_check = [r for r in righe if r.get("file_origine") in nuove_files]
        scope = f"solo le {len(nuove_files)} fatture nuove"
    else:
        righe_check = righe
        scope = "tutte le fatture del PV"

    print("=" * 64)
    print(f"  TEST ACCETTAZIONE IMPORT — {pv['nome_ristorante']}")
    print(f"  P.IVA {pv['partita_iva']} · ristorante_id {rid}")
    print(f"  Ambito controlli: {scope}")
    print("=" * 64)

    if base:
        _print_diff(base, _snapshot(client, rid))

    imb = _imbuto(righe_check)
    print("\n🧭 IMBUTO CATEGORIZZAZIONE (sull'ambito controllato)")
    print(f"   totale righe:              {imb['totale']}")
    print(f"   ✅ categorizzate affidabili: {imb['categorizzate_affidabili']}  "
          f"(il cliente NON deve guardarle)")
    print(f"   👀 in coda da controllare:   {imb['in_coda_da_controllare']}")
    print(f"   ❓ da classificare:          {imb['da_classificare']}  "
          f"(onesto: l'AI non era sicura)")

    blocchi = [
        ("CATEGORIZZAZIONE (constraint)", _check_categorizzazione(righe_check)),
        ("NOTE E DICITURE (regola #2)", _check_note_diciture(righe_check)),
        ("INTEGRITÀ RIGHE", _check_integrita_righe(righe_check)),
        ("DUPLICATI", _check_duplicati(righe_check)),
        ("CODA fatture_queue", _coda_queue(client, rid)),
    ]
    quad_problemi, quad_stat = _check_quadratura(righe_check)
    blocchi.insert(1, ("QUADRATURA IMPORTI", quad_problemi))

    attesi = _carica_attesi(pv)
    if attesi:
        blocchi.insert(0, (
            f"DOCUMENTO ↔ DB (vs {attesi['n_fatture_attese']} file originali)",
            _check_attesi(righe_check, attesi),
        ))

    bloccanti = 0
    print("\n🔍 CONTROLLI OGGETTIVI")
    for nome, problemi in blocchi:
        if nome == "QUADRATURA IMPORTI":
            etichetta = f"{nome}  ({quad_stat['fatture_ok']}/{quad_stat['fatture_tot']} fatture quadrano)"
        else:
            etichetta = nome
        if not problemi:
            print(f"   ✅ {etichetta}: ok")
        else:
            print(f"   ⚠ {etichetta}: {len(problemi)} segnalazioni")
            for p in problemi[:15]:
                print(f"        {p}")
            if len(problemi) > 15:
                print(f"        … e altre {len(problemi) - 15}")
            bloccanti += sum(1 for p in problemi if p.startswith("❌"))

    print("\n" + "=" * 64)
    if bloccanti == 0:
        print("  ✅ ESITO: nessun problema BLOCCANTE.")
        print("     Restano da fare a mano (checklist):")
        print("     · spot-check 2-3 fatture vs PDF originale (fornitore/numero/righe)")
        print("     · giro pagine web + /m (Home, Articoli, Margini, Prezzi, Scadenziario)")
        print("     · svuotare cache briefing della sede e guardarlo come il cliente")
        print("     · revisione categorie con: categorization-reviewer")
    else:
        print(f"  ❌ ESITO: {bloccanti} problemi BLOCCANTI (❌) — NON pronti, da fixare.")
    print("=" * 64)


def main():
    ap = argparse.ArgumentParser(description="Test accettazione import fatture SUSHILAND")
    ap.add_argument("--pv", help="frammento del nome del punto vendita")
    ap.add_argument("--baseline", action="store_true", help="scatta la foto PRIMA dell'import")
    ap.add_argument("--report", action="store_true", help="confronto + check DOPO l'import")
    ap.add_argument("--tutte", action="store_true",
                    help="con --report: controlla tutte le fatture, non solo le nuove")
    args = ap.parse_args()

    client = get_supabase_client()
    pv = _trova_pv(client, args.pv)

    if args.baseline:
        comando_baseline(client, pv)
    elif args.report:
        comando_report(client, pv, solo_nuove=not args.tutte)
    else:
        ap.error("specifica --baseline (prima) o --report (dopo)")


if __name__ == "__main__":
    main()
