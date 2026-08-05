"""
Re-import delle fatture manuali OFFSIDE finite 'dead' per purga GDPR dell'XML.

CONTESTO
--------
333 fatture caricate a mano dal cliente OFFSIDE (source='upload_manuale') sono
in fatture_queue con status='dead' e xml_content=NULL: l'XML e' stato purgato
(purge_processed_xml_content, GDPR) prima che il worker completasse il
salvataggio. Il cliente aveva gia' smistato ogni fattura alla sede giusta:
il ristorante_id sulla riga di coda E' quel lavoro e NON va rifatto.

I file XML originali sono su disco in:
    OFFSIDE GENNAIO-GIUGNO 2026/fatture_MM_26/XML/<nome_file>

COSA FA QUESTO SCRIPT
---------------------
Per ogni riga dead di OFFSIDE:
  1. trova il file su disco per payload_meta->>'nome_file'
  2. ne rilegge l'XML e lo re-inietta in xml_content
  3. rimette status='pending' (azzera retry) SENZA toccare ristorante_id/user_id
Poi il queue-worker Railway riprende la riga, salva le righe in `fatture` sulla
sede gia' scelta dal cliente (rispetta ristorante_id, non ri-smista),
categorizza e - per la sede tecnica - marca la fattura come ripartita.

E' IDEMPOTENTE: salva_fattura_processata fa upsert su uq_fatture_dedup_active,
quindi rilanciarlo non duplica. Le righe gia' 'done' non vengono ritoccate.

SICUREZZA
---------
- WHERE blindato: aggiorna SOLO status='dead' + source='upload_manuale' +
  user_id OFFSIDE + il ristorante_id atteso. Mai altre righe.
- Non cambia MAI il ristorante_id (lo smistamento del cliente e' intoccabile).
- Dry-run di default: senza --esegui stampa solo cosa farebbe.

USO
---
  # 1. credenziali Supabase nell'ambiente (NON in chat, sul tuo PC):
  #    crea un file .env con:
  #       SUPABASE_URL=https://vthikmfpywilukizputn.supabase.co
  #       SUPABASE_SERVICE_ROLE_KEY=<service_role_key>
  #    (oppure export/set delle stesse variabili)
  #
  # 2. prova a vuoto (non scrive niente):
  #       python scripts/reimport_offside_dead.py
  #
  # 3. esegui davvero:
  #       python scripts/reimport_offside_dead.py --esegui
  #
  # 4. (opzionale) limita a N righe per un test:
  #       python scripts/reimport_offside_dead.py --esegui --limit 5
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Costanti OFFSIDE (verificate live 24/7/2026) ──────────────────────────────
OFFSIDE_USER_ID = "2f3f93a1-c1f4-4804-858e-a161e6f36f3f"
SEDI_ATTESE = {
    "f7bba05f-90a8-4f12-94ed-4d8a08a0bbae": "Costi comuni di gruppo (tecnica)",
    "bdda08d1-9490-486c-adfb-dd05cbddc25c": "SPORTS PUB",
    "dcf1996e-f430-4549-8505-902b169f6bab": "OVERTIME",
}
# Radice dei file su disco (relativa alla root del repo).
CARTELLA_OFFSIDE = "OFFSIDE GENNAIO-GIUGNO 2026"


def _repo_root() -> Path:
    # scripts/ e' figlia diretta della root del repo.
    return Path(__file__).resolve().parent.parent


def _carica_env_file(root: Path) -> None:
    """Carica un .env locale (root del repo) nell'ambiente, se presente.

    Mini-parser senza dipendenze (il progetto non usa python-dotenv): righe
    NOME=valore, ignora commenti/vuote, non sovrascrive variabili gia' presenti
    nell'ambiente. Serve solo comodita': si puo' anche esportare a mano.
    """
    env_path = root / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        nome, _, valore = line.partition("=")
        nome = nome.strip()
        valore = valore.strip().strip('"').strip("'")
        if nome and nome not in os.environ:
            os.environ[nome] = valore


def _indice_file_su_disco(root: Path) -> dict[str, Path]:
    """Mappa nome_file -> path, scandendo tutte le sottocartelle fatture_MM_26/XML."""
    base = root / CARTELLA_OFFSIDE
    if not base.is_dir():
        sys.exit(f"ERRORE: cartella non trovata: {base}")
    indice: dict[str, Path] = {}
    for p in base.glob("fatture_*/XML/*.xml"):
        # in caso (improbabile) di nomi duplicati fra mesi, il primo vince: sono
        # nomi SDI univoci (IT<piva>_<progressivo>), collisioni non attese.
        indice.setdefault(p.name, p)
    return indice


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-import fatture dead OFFSIDE da disco")
    ap.add_argument("--esegui", action="store_true",
                    help="esegue gli UPDATE (senza, e' un dry-run che non scrive)")
    ap.add_argument("--limit", type=int, default=0,
                    help="processa al massimo N righe (0 = tutte)")
    args = ap.parse_args()

    root = _repo_root()
    _carica_env_file(root)

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        sys.exit(
            "ERRORE: SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY non nell'ambiente.\n"
            "Crea un file .env (vedi header dello script) o esportale prima di lanciare."
        )

    # import tardivo: serve l'ambiente gia' pronto (le env sopra)
    sys.path.insert(0, str(root))
    from services import get_supabase_client  # noqa: E402

    sb = get_supabase_client()

    # 1) righe dead di OFFSIDE (source manuale)
    resp = (
        sb.table("fatture_queue")
        .select("id, ristorante_id, payload_meta, status")
        .eq("user_id", OFFSIDE_USER_ID)
        .eq("source", "upload_manuale")
        .eq("status", "dead")
        .order("id")
        .execute()
    )
    righe = resp.data or []
    if args.limit > 0:
        righe = righe[: args.limit]

    if not righe:
        print("Nessuna riga dead da re-importare (gia' fatto?). Esco.")
        return

    indice = _indice_file_su_disco(root)
    print(f"File XML su disco: {len(indice)}")
    print(f"Righe dead da processare: {len(righe)}")
    print(f"Modo: {'ESECUZIONE (scrive)' if args.esegui else 'DRY-RUN (non scrive)'}\n")

    ok = mancanti = saltate = errori = 0
    for r in righe:
        qid = r["id"]
        rid = r.get("ristorante_id")
        nome = (r.get("payload_meta") or {}).get("nome_file")

        if rid not in SEDI_ATTESE:
            print(f"  [SKIP] id={qid}: ristorante_id inatteso {rid} (non tocco)")
            saltate += 1
            continue
        if not nome:
            print(f"  [SKIP] id={qid}: nome_file assente in payload_meta")
            saltate += 1
            continue

        path = indice.get(nome)
        if path is None:
            print(f"  [MANCA] id={qid}: file '{nome}' non su disco")
            mancanti += 1
            continue

        try:
            xml = path.read_text(encoding="utf-8")
        except Exception as exc:  # file illeggibile: non blocca il resto
            print(f"  [ERR ] id={qid}: lettura '{nome}' fallita: {exc}")
            errori += 1
            continue

        if not args.esegui:
            print(f"  [DRY ] id={qid} -> {SEDI_ATTESE[rid]:<32} {nome} ({len(xml)} char)")
            ok += 1
            continue

        try:
            upd = (
                sb.table("fatture_queue")
                .update({
                    "xml_content": xml,
                    "status": "pending",
                    # ISO now(): via PostgREST "now()" sarebbe una stringa letterale,
                    # non la funzione SQL — passiamo un timestamp esplicito.
                    "next_retry_at": datetime.now(timezone.utc).isoformat(),
                    "attempt_count": 0,
                    "last_error": None,
                })
                # WHERE blindato: solo QUESTA riga, solo se ancora dead, solo
                # se sede e proprietario combaciano (mai tocca altro).
                .eq("id", qid)
                .eq("status", "dead")
                .eq("user_id", OFFSIDE_USER_ID)
                .eq("ristorante_id", rid)
                .execute()
            )
            if upd.data:
                print(f"  [OK  ] id={qid} -> {SEDI_ATTESE[rid]:<32} {nome}")
                ok += 1
            else:
                print(f"  [NOOP] id={qid}: nessuna riga aggiornata (gia' non-dead?)")
                saltate += 1
        except Exception as exc:
            print(f"  [ERR ] id={qid}: update fallito: {exc}")
            errori += 1

    print("\n── Riepilogo ─────────────────────────────")
    print(f"  {'iniettate' if args.esegui else 'pronte (dry-run)'}: {ok}")
    print(f"  file mancanti su disco: {mancanti}")
    print(f"  saltate:                {saltate}")
    print(f"  errori:                 {errori}")
    if args.esegui and ok:
        print("\nOra il queue-worker Railway riprendera' le righe 'pending' e le")
        print("salvera' nelle sedi gia' scelte dal cliente. Verifica su Admin > Flusso dati")
        print("o interroga la tabella `fatture` per file_origine.")


if __name__ == "__main__":
    main()
