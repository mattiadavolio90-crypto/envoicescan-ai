#!/usr/bin/env python3
"""
scripts/check_documentazione.py — Trova documentazione candidata a pulizia.

Non elimina né archivia nulla: segnala. La decisione (elimina / archivia in
docs/storico/ / lascia) resta a chi legge l'output, perché solo chi conosce
il contenuto sa se un piano "chiuso" ha ancora valore predittivo (regola in
docs/storico/README.md) — questo script non lo può giudicare da solo.

Cerca quattro cose:
1. Documenti fuori da docs/storico/ con marcatori di chiusura
   (CHIUSO/DEPLOYATO/COMPLETATO/SUPERATO) — candidati a eliminazione o
   archiviazione.
2. Link markdown [testo](file.md) rotti in TUTTI i .md del repo (non solo
   DOC_VIVI: quello lo fa già tests/test_documentazione_onesta.py).
3. File in docs/piani/ — dovrebbero esistere solo per lavoro davvero in
   corso (sono git-ignorati apposta, vedi docs/piani/README.md).
4. Documenti "vivi" (elencati nell'indice di DOCUMENTAZIONE/MAPPA_TECNICA.md)
   che l'indice stesso NON menziona più — segnale di indice andato fuori sync.

Uso:
    python scripts/check_documentazione.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

ESCLUDI_DIR = {".venv", "node_modules", ".git", ".next", "__pycache__", ".claude"}

MARCATORI_CHIUSURA = re.compile(
    r"✅\s*\**\s*(?:CHIUSO|DEPLOYAT[OA]|COMPLETAT[OA]|VERIFICAT[OA]|SUPERAT[OA])"
    r"|^>\s*\**\s*(?:CHIUSO|DEPLOYAT[OA]|COMPLETAT[OA]|SUPERAT[OA])\b",
    re.IGNORECASE | re.MULTILINE,
)

_LINK_MD = re.compile(r"\[[^\]]+\]\(([^)#]+\.md)[^)]*\)")


def _tutti_i_md() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.md"):
        if any(parte in ESCLUDI_DIR for parte in p.parts):
            continue
        out.append(p)
    return out


def _leggi(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def check_marcatori_chiusura(md_files: list[Path]) -> list[str]:
    problemi = []
    for p in md_files:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith("docs/storico/"):
            continue  # lì i marcatori di chiusura sono attesi, è l'archivio
        testo = _leggi(p)
        if MARCATORI_CHIUSURA.search(testo):
            problemi.append(rel)
    return problemi


def check_link_rotti(md_files: list[Path]) -> list[tuple[str, str]]:
    problemi = []
    for p in md_files:
        testo = _leggi(p)
        for match in _LINK_MD.finditer(testo):
            target = match.group(1)
            if target.startswith(("http://", "https://")):
                continue
            if not (p.parent / target).resolve().exists():
                problemi.append((p.relative_to(ROOT).as_posix(), target))
    return problemi


def check_piani_orfani() -> list[str]:
    piani_dir = ROOT / "docs" / "piani"
    if not piani_dir.exists():
        return []
    # TUTTI i .md, non solo PIANO_*: il 2/9/2026 un PROMPT_PROSSIMA_SESSIONE.md
    # stantio e' rimasto qui invisibile a questo check (diceva "Fase 3 da fare"
    # di una fase deployata, e "51 commit in coda" quando erano 7) finche' una
    # sessione non ha ereditato da lui una cifra falsa. Il nome del file non e'
    # una garanzia: conta la cartella. README.md e' la documentazione della
    # cartella stessa, non un piano.
    return [
        p.relative_to(ROOT).as_posix()
        for p in sorted(piani_dir.glob("*.md"))
        if p.name != "README.md"
    ]


def check_indice_fuori_sync(md_files: list[Path]) -> list[str]:
    mappa = ROOT / "DOCUMENTAZIONE" / "MAPPA_TECNICA.md"
    if not mappa.exists():
        return []
    testo_mappa = _leggi(mappa)

    # Cartelle "vive" indicizzate esplicitamente: root, DOCUMENTAZIONE/,
    # DOCUMENTAZIONE/tecnica/, docs/ (non ricorsivo in docs/storico|piani,
    # che hanno le proprie regole/README dedicate).
    candidati = []
    for p in md_files:
        rel = p.relative_to(ROOT).as_posix()
        if rel.startswith(("docs/storico/", "docs/piani/", ".claude/")):
            continue
        if "/" in rel and not rel.startswith(("DOCUMENTAZIONE/", "docs/")):
            continue  # es. apps/web/README.md: indicizzato a parte, non qui
        candidati.append((rel, p.name))

    fuori_sync = []
    for rel, nome in candidati:
        if nome not in testo_mappa and rel not in testo_mappa:
            fuori_sync.append(rel)
    return fuori_sync


def main() -> int:
    md_files = _tutti_i_md()

    chiusi = check_marcatori_chiusura(md_files)
    link_rotti = check_link_rotti(md_files)
    piani = check_piani_orfani()
    fuori_sync = check_indice_fuori_sync(md_files)

    ha_problemi = False

    if chiusi:
        ha_problemi = True
        print(f"\n[MARCATORI DI CHIUSURA] {len(chiusi)} documento/i fuori da docs/storico/ si dichiarano chiusi:")
        for f in chiusi:
            print(f"  - {f}")
        print("  -> Se il contenuto e' gia' in memoria/git history: elimina.")
        print("  -> Se ha valore predittivo futuro: sposta in docs/storico/ (vedi docs/storico/README.md).")

    if link_rotti:
        ha_problemi = True
        print(f"\n[LINK ROTTI] {len(link_rotti)} link puntano a file inesistenti:")
        for doc, target in link_rotti:
            print(f"  - {doc} -> {target}")

    if piani:
        print(f"\n[PIANI ATTIVI] {len(piani)} file in docs/piani/ (normale se lavoro in corso, verifica se orfani):")
        for f in piani:
            print(f"  - {f}")

    if fuori_sync:
        ha_problemi = True
        print(f"\n[INDICE FUORI SYNC] {len(fuori_sync)} documento/i non citati in DOCUMENTAZIONE/MAPPA_TECNICA.md §6:")
        for f in fuori_sync:
            print(f"  - {f}")
        print("  -> Aggiungi una riga all'indice, o e' un file che andrebbe eliminato.")

    if not ha_problemi and not piani:
        print("Documentazione in ordine: nessun marcatore di chiusura fuori posto, nessun link rotto, indice allineato.")

    return 1 if ha_problemi else 0


if __name__ == "__main__":
    sys.exit(main())
