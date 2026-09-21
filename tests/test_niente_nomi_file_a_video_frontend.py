"""Il nome del file XML non si mostra al cliente.

Perche' qui e non in `apps/web/`: un runner di test sotto `apps/web/` farebbe
scattare `deploy-vercel.yml` a ogni merge. Questo presidio legge i sorgenti.

Cosa protegge: le fatture elettroniche arrivano dall'SDI come file con nomi
tipo `IT02621200126_037BG.xml` — l'identificativo del trasmittente piu' un
progressivo. E' il nome tecnico del trasporto, non un dato del cliente: non
corrisponde al numero della fattura, non e' cercabile, e nel mezzo di una
tabella di prezzi non risponde a nessuna domanda.

Il 21/09/2026 l'Osservatorio lo mostrava in una colonna intitolata "File", in
Sconti e Omaggi e in Note di Credito, **accanto** alla colonna "N. Documento"
che porta gia' il numero vero (screenshot 10, 11, 23, 24). Rilievo O2 del piano
di coerenza visiva.

Il campo NON e' stato tolto dal tipo: in `nc-tab.tsx` `r.documento` conta i
documenti distinti per il KPI "Documenti NC". E' la sua resa a video che era
sbagliata, non il dato.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.test_colori_solo_token_frontend import ESCLUSI

SRC = Path(__file__).resolve().parent.parent / "apps" / "web" / "src"

# Un'intestazione di colonna che dice "File" o "Nome file". Si cerca fra
# virgolette perche' le intestazioni sono letterali in un array.
INTESTAZIONE_FILE = re.compile(r"""["'`]\s*(File|Nome file|Filename|File XML)\s*["'`]""", re.I)

# I campi che portano il nome del file cosi' come arriva dall'SDI.
CAMPI_FILE = ("file_origine", "nome_file", "filename", "file_name")

# `file_origine` compare a video SOLO come ripiego quando manca il nome vero:
# "{item.fornitore || item.file_origine}" mostra il file solo se il fornitore
# non e' stato riconosciuto — li' e' l'unica cosa che identifica la riga, e
# toglierlo lascerebbe una riga vuota.
RIPIEGHI_AMMESSI = {
    ("app/(app)/scadenziario/scadenziario-client.tsx", "item.fornitore || item.file_origine"),
}


def _perimetro() -> list[Path]:
    file = []
    for p in sorted(SRC.rglob("*.tsx")):
        rel = p.relative_to(SRC).as_posix()
        if any(rel.startswith(e) or ("/" + e) in ("/" + rel) for e in ESCLUSI):
            continue
        file.append(p)
    return file


def _senza_commenti(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


PERIMETRO = _perimetro()


def test_il_perimetro_non_e_vuoto():
    assert len(PERIMETRO) >= 80, len(PERIMETRO)
    assert any(p.name == "sconti-tab.tsx" for p in PERIMETRO)


def test_il_rilevatore_riconosce_le_forme_che_il_codice_usa():
    """Un rilevatore che non matcha non misura niente."""
    assert INTESTAZIONE_FILE.search('["Data", "Fornitore", "File"]')
    assert INTESTAZIONE_FILE.search("['File XML']")
    assert INTESTAZIONE_FILE.search('"Nome file"')
    # Non deve scattare su parole che contengono "file" o su altre colonne
    assert not INTESTAZIONE_FILE.search('["Profile", "Fornitore"]')
    assert not INTESTAZIONE_FILE.search('["N. Documento"]')
    assert not INTESTAZIONE_FILE.search('"Carica file"')  # e' un bottone, non una colonna

    # Il matcher del testo a video: prende cio' che si LEGGE, non il codice
    assert RESO_A_VIDEO.findall("<td>{r.file_origine}</td>") == ["r.file_origine"]
    assert RESO_A_VIDEO.findall("key={doc.file_origine}") == []
    assert RESO_A_VIDEO.findall("file_origine: string | null") == []
    assert RESO_A_VIDEO.findall("onToggle={() => f(doc.file_origine)}") == []


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_nessuna_colonna_intitolata_file(file: Path):
    """Una colonna "File" in una tabella di dati mostra il nome del trasporto."""
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    # Solo dentro un array di intestazioni: `[... , "File"]` seguito da .map
    for m in re.finditer(r"\[[^\[\]]*\]\.map\(", src, re.S):
        assert not INTESTAZIONE_FILE.search(m.group(0)), (
            f"{file.relative_to(SRC).as_posix()}: colonna \"File\" — il nome del "
            f"file XML e' il nome del trasporto, non un dato del cliente"
        )


# Solo il testo RENDERIZZATO: `{x}` subito dopo un `>` o fra due tag. Il primo
# giro cercava ogni graffa JSX e pescava chiavi React (`key={doc.file_origine}`),
# dichiarazioni di tipo (`file_origine: string | null`) e handler
# (`onToggleSelect(doc.file_origine)`) — 3 falsi positivi su 4. Ma il quarto era
# vero: `articoli-tab.tsx` aveva la stessa colonna "File" dell'Osservatorio.
RESO_A_VIDEO = re.compile(r">\s*\{\s*([^{}]*?)\s*\}\s*<")


@pytest.mark.parametrize("file", PERIMETRO, ids=lambda p: p.relative_to(SRC).as_posix())
def test_il_nome_del_file_non_si_rende_da_solo(file: Path):
    """`file_origine` a video va bene solo come RIPIEGO di un nome mancante."""
    src = _senza_commenti(file.read_text(encoding="utf-8"))
    rel = file.relative_to(SRC).as_posix()
    nudi = []
    for m in RESO_A_VIDEO.finditer(src):
        espressione = " ".join(m.group(1).split())
        if not any(c in espressione for c in CAMPI_FILE):
            continue
        if (rel, espressione) in RIPIEGHI_AMMESSI:
            continue
        if "||" in espressione or "??" in espressione or "?" in espressione:
            continue  # e' un ripiego: mostra il file solo se manca l'altro
        nudi.append(espressione[:70])
    assert not nudi, (
        f"{rel}: il nome del file reso come dato a se': {nudi[:3]}"
    )


def test_i_ripieghi_ammessi_esistono_ancora():
    """Un'eccezione che non corrisponde piu' a niente autorizzerebbe in
    silenzio un uso futuro con la stessa forma."""
    vivi = set()
    for p in PERIMETRO:
        src = _senza_commenti(p.read_text(encoding="utf-8"))
        rel = p.relative_to(SRC).as_posix()
        for m in RESO_A_VIDEO.finditer(src):
            vivi.add((rel, " ".join(m.group(1).split())))
    orfani = sorted(k for k in RIPIEGHI_AMMESSI if k not in vivi)
    assert not orfani, f"ripieghi che non corrispondono a nulla: {orfani}"
