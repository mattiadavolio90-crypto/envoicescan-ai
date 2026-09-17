"""Il bordo rosso della riga non compare dove la scadenza e' nascosta.

Perche' esiste
==============
La vista "Per mese" passa `mostraScadenze={false}` e il commento a
`DocumentoRowProps` dichiara l'intento: «sparisce tutto cio' che riguarda le
scadenze: badge della fonte, data di scadenza, selezione multipla e "Paga"».

Quattro conseguenze elencate, quattro gestite. La quinta — il bordo rosso di
riga — era rimasta fuori: la riga gridava "scaduta" mentre il dato che lo
giustifica era nascosto di proposito, e al cliente restava una marcatura
inspiegabile.

`mostraBordoScaduta` e' la decisione estratta in `lib/`, dove la rete di test
del frontend arriva davvero: dentro il .tsx nessun test la vedrebbe (nessun
runner npm, i 40 file `test_*_frontend.py` coprono solo `lib/`).

Le due direzioni contano entrambe
=================================
Un test che controlla solo "in Per mese niente bordo" resta verde anche se si
spegne il bordo OVUNQUE — che sarebbe una regressione sulla vista Lista, dove
il bordo e' l'unico segnale di scaduto insieme alla data. Per questo ogni caso
e' verificato in entrambe le viste.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

# Un fuso a ovest di Greenwich insieme a Roma: `parseLocalDate` su una data ISO
# decide se "ieri" e' ieri davvero, e statoDocumento ci si appoggia.
FUSI = ["Europe/Rome", "America/Los_Angeles"]


def _doc(**kw):
    base = {
        "id": "x.xml",
        "file_origine": "x.xml",
        "fornitore": "F",
        "tipo_documento": "TD01",
        "is_nota_credito": False,
        "totale_documento": 100.0,
        "data_documento": "2026-01-10",
        "numero_documento": None,
        "scadenza_effettiva": None,
        "scadenza_source": None,
        "pagata": False,
        "data_pagamento": None,
        "pagata_at": None,
        "stato_scadenza": "",
        "oscurata": False,
    }
    base.update(kw)
    return base


def _bordo(doc, mostra_scadenze, tz):
    """True se la riga deve avere il bordo rosso, come lo decide la lib."""
    return esegui_ts(
        MODULO,
        "emit(m.mostraBordoScaduta(input.doc, input.mostraScadenze, "
        "new Date('2026-06-15T12:00:00')));",
        argomento={"doc": doc, "mostraScadenze": mostra_scadenze},
        tz=tz,
        richiede=["mostraBordoScaduta", "statoDocumento"],
    )


SCADUTA = _doc(scadenza_effettiva="2026-05-01")
DA_PAGARE = _doc(scadenza_effettiva="2026-08-01")


@pytest.mark.parametrize("tz", FUSI)
def test_vista_lista_la_scaduta_ha_il_bordo(tz):
    """La direzione che impedisce di spegnere il bordo ovunque."""
    assert _bordo(SCADUTA, True, tz) is True


@pytest.mark.parametrize("tz", FUSI)
def test_vista_per_mese_la_stessa_scaduta_non_ha_il_bordo(tz):
    """Stesso documento, stessa data: cambia solo la vista."""
    assert _bordo(SCADUTA, False, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_una_non_scaduta_non_ha_il_bordo_in_nessuna_vista(tz):
    assert _bordo(DA_PAGARE, True, tz) is False
    assert _bordo(DA_PAGARE, False, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_una_scaduta_gia_pagata_non_ha_il_bordo(tz):
    """`statoDocumento` mette "Pagata" prima di "Scaduta": il bordo segue."""
    pagata = _doc(scadenza_effettiva="2026-05-01", pagata=True)
    assert _bordo(pagata, True, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_una_nota_di_credito_scaduta_non_ha_il_bordo(tz):
    """Una NC non e' un debito: non si "paga" e non e' in ritardo."""
    nc = _doc(scadenza_effettiva="2026-05-01", is_nota_credito=True)
    assert _bordo(nc, True, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_una_esclusa_dai_conti_non_ha_il_bordo(tz):
    """Coerente col calendario del worker, che salta le oscurate."""
    osc = _doc(scadenza_effettiva="2026-05-01", oscurata=True)
    assert _bordo(osc, True, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_senza_scadenza_nessun_bordo(tz):
    """`scadenza_effettiva` e' nullable: niente data, niente ritardo."""
    assert _bordo(_doc(scadenza_effettiva=None), True, tz) is False


@pytest.mark.parametrize("tz", FUSI)
def test_il_bordo_segue_statoDocumento_non_una_regola_propria(tz):
    """L'invariante che lega le due funzioni: se un giorno `statoDocumento`
    cambiasse la precedenza (es. "Fuori dai conti" prima di "Pagata"), il bordo
    deve seguirla senza che questo file vada aggiornato a mano."""
    casi = [SCADUTA, DA_PAGARE,
            _doc(scadenza_effettiva="2026-05-01", pagata=True),
            _doc(scadenza_effettiva="2026-05-01", is_nota_credito=True),
            _doc(scadenza_effettiva="2026-05-01", oscurata=True),
            _doc(scadenza_effettiva=None)]
    stati = esegui_ts(
        MODULO,
        "emit(input.map((d) => m.statoDocumento(d, new Date('2026-06-15T12:00:00'))));",
        argomento=casi,
        tz=tz,
        richiede=["statoDocumento"],
    )
    for doc, stato in zip(casi, stati):
        atteso = (stato == "Scaduta")
        assert _bordo(doc, True, tz) is atteso, f"stato {stato!r} e bordo non concordano"
