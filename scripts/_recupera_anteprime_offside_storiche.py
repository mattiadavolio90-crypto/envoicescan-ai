"""Recupero anteprime delle fatture storiche OFFSIDE (gen-giu 2026) il cui
xml_content era stato purgato in coda 'da_assegnare' prima che la cache anteprima
venisse popolata (vedi migration 20260723210000).

I file XML originali sono su disco ("OFFSIDE GENNAIO-GIUGNO 2026/**/XML/*.xml").
Questo script è OFFLINE: non tocca il DB. Per ogni XML locale calcola
sha256(bytes del file) — identico all'xml_hash che il worker salva all'upload — e
ri-parsa con lo STESSO parser di produzione (estrai_dati_da_xml, user_id=None →
nessuna memoria personalizzata, nessuna scrittura, categoria = stima globale).

Emette un JSON {sha256: anteprima_righe}. L'associazione hash→queue_id la fa poi il
DB stesso (join su fatture_queue.xml_hash), così nessun id viene trascritto a mano.

Uso:
    python scripts/_recupera_anteprime_offside_storiche.py <output.json>
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.invoice_service import estrai_dati_da_xml
from services.routers.riparto import _AnteprimaFileLike, costruisci_anteprima_righe

XML_GLOB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "OFFSIDE GENNAIO-GIUGNO 2026", "**", "XML", "*.xml",
)


def main(out_path: str) -> int:
    files = glob.glob(XML_GLOB, recursive=True)
    print(f"XML locali trovati: {len(files)}")

    by_hash = {}
    n_ok = n_fail = 0
    for f in files:
        b = open(f, "rb").read()
        h = hashlib.sha256(b).hexdigest()
        try:
            righe = estrai_dati_da_xml(_AnteprimaFileLike(b, os.path.basename(f)), user_id=None) or []
            by_hash[h] = costruisci_anteprima_righe(righe)
            n_ok += 1
        except Exception as exc:
            n_fail += 1
            print(f"  PARSE FAIL {os.path.basename(f)}: {exc}")

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(by_hash, fh, ensure_ascii=False)

    print("-" * 60)
    print(f"parse riuscito: {n_ok}")
    print(f"parse fallito:  {n_fail}")
    print(f"hash distinti:  {len(by_hash)}")
    print(f"scritto in:     {out_path}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/_recupera_anteprime_offside_storiche.py <output.json>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
