"""La finestra «Regole fornitore» dello scadenziario (PV e catena).

Fino al 28/9/2026 questo file provava anche il riquadro giallo «N fatture
senza scadenza», con la classifica dei fornitori per euro. Mattia l'ha tolto:
il totale sta sotto «Da pagare», le fatture nella sezione «Senza scadenza»
dell'elenco, e i termini si impostano da «Regole fornitore». Restano i
presidi sulla finestra, che non dipendevano dal riquadro.

Assert sul sorgente: il .tsx non e' eseguibile dall'harness node.
"""
import re
from pathlib import Path

import pytest

CLIENT = (
    Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


@pytest.fixture(scope="module")
def sorgente() -> str:
    return CLIENT.read_text(encoding="utf-8")


def test_il_riquadro_giallo_non_c_e_piu(sorgente: str):
    """Mattia, 28/9: nessuna delle due viste lo mostra. Si cerca il testo a
    video e la preselezione che solo il riquadro usava."""
    testo = re.sub(r"\s+", " ", sorgente)
    assert "senza scadenza (" not in testo
    assert "nomeIniziale" not in sorgente


def test_la_toolbar_apre_le_regole(sorgente: str):
    """Tolto il riquadro, la toolbar e' l'unica porta: non deve sparire."""
    testo = re.sub(r"\s+", " ", sorgente)
    assert 'onClick={() => setRegoleOpen(true)}> <Settings2 className="size-3.5" /> Regole fornitore' in testo


def test_la_finestra_parte_senza_selezione(sorgente: str):
    testo = re.sub(r"\s+", " ", sorgente)
    assert "if (open) { loadAll(); setSelectedNomi(new Set());" in testo


def test_salvare_una_regola_ricarica_la_lista(sorgente: str):
    """Prima il dialog ricaricava solo se stesso: la regola veniva creata e le
    scadenze a video restavano quelle di prima, fino a un «Aggiorna» a mano."""
    assert "onSalvato={loadData}" in sorgente, (
        "dopo il salvataggio la lista non viene piu' ricaricata"
    )
    assert "if (salvate > 0) onSalvato?.();" in sorgente, (
        "RegoleDialog non avvisa piu' il genitore dopo un salvataggio"
    )


def test_eliminare_una_regola_ricarica_la_lista_solo_se_riuscita(sorgente: str):
    """Togliere una regola ricalcola le scadenze delle sue fatture: senza
    `onSalvato` la lista restava quella di prima (mutante sopravvissuto il
    26/09). E senza guardare la risposta diceva «Regola eliminata» anche quando
    il server aveva rifiutato."""
    # Due handleDelete nel file: questa e' quella delle regole (l'altra elimina
    # la fattura dal dettaglio).
    i = sorgente.index("async function handleDelete(id: string)")
    corpo = re.sub(r"\s+", " ", sorgente[i:sorgente.index("const pivaToNome", i)])
    ordine = [
        'const res = await fetch(`/api/scadenziario/regole/${id}`, { method: "DELETE" });',
        'if (!res.ok) { toast.error("Errore eliminazione"); return; }',
        "setRegole(r => r.filter(x => x.id !== id));",
        'toast.success("Regola eliminata");',
        "onSalvato?.();",
    ]
    posizioni = [corpo.find(riga) for riga in ordine]
    assert -1 not in posizioni, f"manca un passo dell'eliminazione: {list(zip(ordine, posizioni))}"
    assert posizioni == sorted(posizioni), f"passi dell'eliminazione fuori ordine: {corpo}"
