"""La pagina Personale a finestra stretta (~950-1280px).

Blocco H della fase 3: fino al 23/09/2026 nessuno aveva mai guardato l'app sotto
i 1900px — i 70 screenshot di riferimento sono tutti a schermo pieno. Due
screenshot a ~1000px hanno chiuso il residuo R2, aperto da settembre, con due
esiti opposti:

- il sospetto del piano era SBAGLIATO: le card dipendente espanse non si rompono,
  respirano;
- ma la pagina scorreva in ORIZZONTALE, e le ore andavano a capo in mezzo al
  numero.

Questi presidi difendono le due correzioni. Nessuno dei due misura un rendering
(non c'e' un runner npm): misurano le CLASSI che decidono il comportamento, che
e' l'unica cosa verificabile da qui — e per questo asseriscono la relazione fra
classi, non la loro presenza nuda.
"""

import re
from pathlib import Path

import pytest

PAGINA = Path(__file__).resolve().parents[1] / "apps/web/src/app/(app)/workspace/personale-tab.tsx"


@pytest.fixture(scope="module")
def src() -> str:
    assert PAGINA.exists(), f"{PAGINA} non esiste: spostata o rinominata?"
    return PAGINA.read_text(encoding="utf-8")


def _senza_commenti(s: str) -> str:
    """Via i commenti JSX e di riga: un difetto CITATO in un commento non e' un
    difetto, e una classe nominata in un commento non e' una classe applicata.
    E' l'errore che in questa fase ha prodotto quattro presidi finti."""
    s = re.sub(r"\{/\*.*?\*/\}", "", s, flags=re.S)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    return "\n".join(r for r in s.splitlines() if not r.lstrip().startswith("//"))


def test_la_barra_azioni_va_a_capo(src):
    """I cinque bottoni della barra sono ~700px: senza `flex-wrap` restano un
    blocco indivisibile che sfonda il bordo destro e trascina l'INTERA pagina in
    scroll orizzontale. A 1000px «Aggiungi turno» usciva tagliato a meta'.

    Il contenitore ESTERNO aveva gia' `flex-wrap`: non bastava, perche' il wrap
    agisce sui figli diretti e i bottoni sono nipoti. Per questo il presidio
    guarda il contenitore interno, non la pagina in generale.
    """
    pulito = _senza_commenti(src)
    m = re.search(r'<div className="(ml-auto[^"]*)">\s*\n\s*<Button', pulito)
    assert m, "la barra azioni di Personale non e' piu' un <div ml-auto> con <Button> dentro"
    classi = m.group(1).split()
    assert "flex" in classi, f"la barra non e' piu' flex: {classi}"
    assert "flex-wrap" in classi, (
        f"la barra azioni non va a capo ({classi}): i cinque bottoni sfondano il "
        "bordo destro sotto i ~1100px e la pagina scorre in orizzontale"
    )
    assert "justify-end" in classi, (
        "senza justify-end i bottoni andati a capo si allineano a sinistra: "
        "`ml-auto` posiziona il blocco, non le sue righe interne"
    )


def test_i_numeri_delle_card_non_vanno_a_capo(src):
    """«409h 30m» andava a capo IN MEZZO: le ore su una riga, i minuti sotto.

    Una durata spezzata su due righe si legge come due valori diversi — lo stesso
    inganno del troncamento che il commento sopra le card vieta da settembre. La
    somma misurata era 365px di contenuto in 223px disponibili a 1140px: nessuna
    valvola puo' ripartire 365 in 223, quindi si riduce la taglia sotto `lg`.
    """
    pulito = _senza_commenti(src)
    numeri = re.findall(r'<p className="([^"]*tabular-nums[^"]*)"', pulito)
    assert len(numeri) >= 4, f"attesi almeno 4 numeri tabulari nelle card, trovati {len(numeri)}"

    for classi in numeri:
        insieme = classi.split()
        assert "whitespace-nowrap" in insieme, (
            f"un numero delle card puo' andare a capo ({classi}): «409h 30m» si "
            "spezzerebbe fra ore e minuti e sembrerebbero due valori"
        )
        # La taglia deve SCALARE: fissa a text-4xl non ci sta a 1000px.
        assert "lg:text-4xl" in insieme, (
            f"il numero non torna grande sopra `lg` ({classi}): a schermo pieno "
            "le card perderebbero la loro gerarchia"
        )
        piccole = [c for c in insieme if re.fullmatch(r"text-(xs|sm|base|lg|xl|2xl|3xl)", c)]
        assert piccole, (
            f"il numero non ha una taglia ridotta sotto `lg` ({classi}): a 1000px "
            "ore e costo insieme non entrano nei 223px della card"
        )


def test_le_due_colonne_della_card_hanno_la_stessa_taglia(src):
    """Ore e costo stanno affiancati: se scalassero in modo diverso, a finestra
    stretta una delle due sembrerebbe il dato principale senza esserlo."""
    pulito = _senza_commenti(src)
    numeri = re.findall(r'<p className="([^"]*tabular-nums[^"]*)"', pulito)
    # Solo le TAGLIE: `text-` prefissa anche colori (`text-primary-text`) e
    # allineamenti (`text-right`), che qui non c'entrano. Si riconosce la taglia
    # dalla sua forma, non escludendo a mano i nomi che capita di incontrare.
    taglia = re.compile(r"^(?:lg:)?text-(?:xs|sm|base|lg|[2-9]?xl)$")
    taglie = {
        tuple(sorted(c for c in cls.split() if taglia.fullmatch(c)))
        for cls in numeri
    }
    assert len(taglie) == 1, (
        f"i numeri delle card scalano in modo diverso: {taglie} — affiancati, "
        "la colonna piu' grande si legge come quella che conta"
    )
