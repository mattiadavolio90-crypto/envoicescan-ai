"""Backup delle tabelle che il lavoro sul retail puo' toccare, e sua verifica.

SOLA LETTURA sul DB: legge e scrive su file locali, non modifica nulla. Il
client e' lo stesso proxy di `retail_baseline` che solleva su qualunque
scrittura: un backup che per errore scrivesse sarebbe il contrario di un backup.

Perche' esiste: il 10/9/2026 uno script di snapshot ha creato 308 voci in
`prodotti_utente` senza che esistesse una copia del "prima". La cancellazione e'
riuscita solo perche' il filtro era stretto — non perche' ci fosse una rete.

Cosa salva, e perche' queste tabelle:
  - prodotti_utente         memoria locale per utente (include le correzioni
                            MANUALI dei clienti: il dato piu' prezioso)
  - prodotti_master         memoria globale condivisa fra tutti i clienti
  - classificazioni_manuali memoria admin, priorita' assoluta
  - categorie               tassonomia canonica (globale, senza ristorante_id)
  - ristoranti              anagrafica sedi: la migration aggiunge una colonna qui

Le `fatture` NON sono qui: 39.515 righe, e nessuna fase del piano le scrive.
Se una fase dovesse toccarle, questo backup va esteso PRIMA.

Uso:
    python scripts/retail_backup.py            # crea un backup con timestamp
    python scripts/retail_backup.py --verify   # ricarica l'ultimo e lo confronta col DB

`--verify` non si ferma ai conteggi: un conteggio che torna non prova che il
contenuto sia utilizzabile per un ripristino. Controlla anche che le correzioni
manuali dei clienti ci siano, che i campi necessari esistano, e che una riga
presa dal backup combaci campo per campo con quella a DB.

Ripristino: NON esiste uno script. Si scrive solo se e quando serve, con
dry-run di default e `salta_correzioni_manuali` (CLAUDE.md, convenzioni): un
ripristino e' una scrittura in produzione e va deciso da Mattia, non lanciato.

Destinazione: `~/oneflux-backup/<timestamp>/` (fuori dal repo e fuori dallo
scratchpad di sessione: un backup che sparisce con la sessione non e' un
backup). Sovrascrivibile con ONEFLUX_BACKUP_DIR.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from dotenv import load_dotenv

load_dotenv(_REPO / ".env")

from scripts.retail_baseline import _client  # noqa: E402 — proxy di sola lettura
from utils.supabase_paging import fetch_all  # noqa: E402

DEST = Path(os.environ.get("ONEFLUX_BACKUP_DIR", Path.home() / "oneflux-backup"))

TABELLE = [
    "prodotti_utente",
    "prodotti_master",
    "classificazioni_manuali",
    "categorie",
    "ristoranti",
]

# Senza questi campi una riga di prodotti_utente non si puo' ricostruire.
_CAMPI_RIPRISTINO = {"id", "user_id", "descrizione", "categoria", "classificato_da"}


def _ultimo() -> Path | None:
    if not DEST.exists():
        return None
    dirs = sorted((d for d in DEST.iterdir() if d.is_dir()), reverse=True)
    return dirs[0] if dirs else None


def backup() -> int:
    sb = _client()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cartella = DEST / stamp
    cartella.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, int] = {}
    for tab in TABELLE:
        righe = fetch_all(sb.table(tab).select("*"))
        (cartella / f"{tab}.json").write_text(
            json.dumps(righe, ensure_ascii=False, indent=1, sort_keys=True, default=str),
            encoding="utf-8",
        )
        manifest[tab] = len(righe)
        print(f"  {tab:26s} {len(righe):6d} righe")

    (cartella / "_manifest.json").write_text(
        json.dumps(
            {"creato": datetime.now().isoformat(), "conteggi": manifest},
            ensure_ascii=False, indent=1,
        ),
        encoding="utf-8",
    )
    print(f"\nbackup in: {cartella}")
    return 0


def verify() -> int:
    cartella = _ultimo()
    if not cartella:
        print("nessun backup trovato", file=sys.stderr)
        return 2

    manifest = json.loads((cartella / "_manifest.json").read_text(encoding="utf-8"))
    sb = _client()
    print(f"verifica di {cartella.name} (creato {manifest['creato'][:19]})\n")

    ok = True
    print("=== 1. Conteggi: file, manifest, DB ===")
    for tab, atteso in manifest["conteggi"].items():
        dati = json.loads((cartella / f"{tab}.json").read_text(encoding="utf-8"))
        vivo = sb.table(tab).select("id", count="exact").limit(1).execute().count
        stato = "OK" if len(dati) == atteso == vivo else "DIVERGE"
        if stato != "OK":
            ok = False
        print(f"  {tab:26s} file={len(dati):6d}  manifest={atteso:6d}  db={vivo:6d}  {stato}")

    pu = json.loads((cartella / "prodotti_utente.json").read_text(encoding="utf-8"))

    print("\n=== 2. Le correzioni manuali dei clienti sono nel backup? ===")
    fonti = Counter(r.get("classificato_da") for r in pu)
    manuali = {k: v for k, v in fonti.items() if k and "keyword-auto" not in k}
    print(f"  voci totali: {len(pu)}   voci non automatiche: {sum(manuali.values())}")
    if not manuali:
        ok = False
        print("  NESSUNA correzione manuale nel backup: contenuto sospetto")

    print("\n=== 3. I campi necessari a un ripristino ci sono? ===")
    mancanti = sorted(k for k in _CAMPI_RIPRISTINO if pu and k not in pu[0])
    vuote = sum(1 for r in pu if not r.get("descrizione") or not r.get("categoria"))
    print(f"  campi mancanti: {mancanti or 'nessuno'}   righe con descrizione/categoria vuota: {vuote}")
    if mancanti:
        ok = False

    print("\n=== 4. Una riga presa dal backup combacia col DB? ===")
    if pu:
        campione = pu[len(pu) // 2]
        vivo = sb.table("prodotti_utente").select("*").eq("id", campione["id"]).execute().data
        if not vivo:
            ok = False
            print(f"  id {campione['id']}: NON trovata a DB")
        else:
            diff = [k for k in _CAMPI_RIPRISTINO if str(campione.get(k)) != str(vivo[0].get(k))]
            if diff:
                ok = False
            print(f"  id {campione['id']}: {'identica' if not diff else 'DIVERGE su ' + str(diff)}")

    tot = sum(f.stat().st_size for f in cartella.iterdir())
    print(f"\n  {tot / 1024 / 1024:.1f} MB in {cartella}")
    print("\nBackup leggibile e allineato al DB." if ok else "\nATTENZIONE: divergenze sopra.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else backup())
