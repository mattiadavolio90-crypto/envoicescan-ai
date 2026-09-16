"""Il contatore in cima alla lista conta la stessa popolazione che la lista elenca.

`contaDaPagare` alimenta la riga "N su M fatture da pagare" sopra le sezioni
dello scadenziario. Fino al 16/09/2026 quella riga usava `documentiFiltrati
.length`, cioe' OGNI documento che passava i filtri: su una sede reale diceva
"426 su 581" mentre la sezione Scadute ne elencava 414. I 12 di differenza erano
note di credito scadute, che hanno una sezione propria e non un bucket di
scadenza.

Nessun numero era falso: erano due popolazioni diverse a due centimetri di
distanza, senza niente che lo dicesse. La classe di difetto e' quella piu' cara
del progetto — nessun errore visibile, solo un numero che non torna.

**L'invariante provata qui** e' quella che rende il contatore verificabile:
il conteggio deve essere ESATTAMENTE la somma dei bucket di pagamento prodotti
da `bucketizeDocumenti`. Legare il test ai bucket, invece che a un numero
atteso scritto a mano, fa fallire il test anche se un domani cambia la regola
di bucketizzazione senza aggiornare il contatore.
"""
import datetime

import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"

# Rome = il fuso degli utenti. Los Angeles = quello che smaschera gli errori di
# mezzanotte UTC nelle date (stessa ragione di test_scadenziario_kpi_frontend).
FUSI = ["Europe/Rome", "America/Los_Angeles"]


def _doc(**kw):
    base = {
        "id": kw.get("id", "x"),
        "fornitore": "F",
        "is_nota_credito": False,
        "oscurata": False,
        "totale_documento": 100,
        "scadenza_effettiva": None,
        "pagata": False,
        "pagata_at": None,
    }
    base.update(kw)
    return base


def _iso(delta_giorni: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=delta_giorni)).isoformat()


def _conta(documenti, tz):
    return esegui_ts(
        MODULO,
        "emit(m.contaDaPagare(input));",
        argomento=documenti,
        tz=tz,
        richiede=["contaDaPagare"],
    )


def _buckets(documenti, tz):
    return esegui_ts(
        MODULO,
        "emit(Object.fromEntries(Object.entries(m.bucketizeDocumenti(input))"
        ".map(([k, v]) => [k, v.length])));",
        argomento=documenti,
        tz=tz,
        richiede=["bucketizeDocumenti", "contaDaPagare"],
    )


# Il caso reale che ha rivelato il difetto: fatture scadute con in mezzo note di
# credito scadute. Le date sono relative a oggi, non fisse: con date fisse il
# test invecchia e i mutanti tornano a sopravvivere in silenzio.
CASO_MISTO = [
    _doc(id="s1", scadenza_effettiva=_iso(-30)),
    _doc(id="s2", scadenza_effettiva=_iso(-1)),
    _doc(id="nc1", scadenza_effettiva=_iso(-30), is_nota_credito=True),
    _doc(id="nc2", scadenza_effettiva=_iso(-2), is_nota_credito=True),
    _doc(id="osc", scadenza_effettiva=_iso(-5), oscurata=True),
    _doc(id="pag", scadenza_effettiva=_iso(-9), pagata=True, pagata_at=_iso(-8)),
    _doc(id="sett", scadenza_effettiva=_iso(3)),
    _doc(id="mese", scadenza_effettiva=_iso(20)),
    _doc(id="oltre", scadenza_effettiva=_iso(90)),
    _doc(id="senza", scadenza_effettiva=None),
]


@pytest.mark.parametrize("tz", FUSI)
def test_conta_solo_le_fatture_da_pagare(tz):
    """6 da pagare su 10 documenti: NC, escluse e pagate non sono debiti."""
    assert _conta(CASO_MISTO, tz) == 6


@pytest.mark.parametrize("tz", FUSI)
def test_il_contatore_coincide_con_i_bucket_elencati(tz):
    """L'invariante vera: il contatore == la somma delle sezioni di pagamento.

    E' questa uguaglianza che il cliente legge, e che prima non reggeva.
    """
    b = _buckets(CASO_MISTO, tz)
    elencate = b["scadute"] + b["settimana"] + b["mese"] + b["oltre"] + b["senzaScadenza"]
    assert _conta(CASO_MISTO, tz) == elencate


@pytest.mark.parametrize("tz", FUSI)
def test_le_note_di_credito_non_gonfiano_il_contatore(tz):
    """Aggiungere SOLO note di credito non deve muovere il contatore.

    E' il difetto originale isolato: 426 vs 414, dove i 12 erano NC.
    """
    prima = _conta(CASO_MISTO, tz)
    con_nc = CASO_MISTO + [
        _doc(id=f"nc{i}", scadenza_effettiva=_iso(-i - 1), is_nota_credito=True)
        for i in range(12)
    ]
    assert _conta(con_nc, tz) == prima


@pytest.mark.parametrize("tz", FUSI)
def test_le_escluse_dai_conti_non_gonfiano_il_contatore(tz):
    prima = _conta(CASO_MISTO, tz)
    con_oscurate = CASO_MISTO + [
        _doc(id=f"o{i}", scadenza_effettiva=_iso(-i - 1), oscurata=True) for i in range(7)
    ]
    assert _conta(con_oscurate, tz) == prima


@pytest.mark.parametrize("tz", FUSI)
def test_una_fattura_da_pagare_in_piu_muove_il_contatore(tz):
    """Il contrario del test sopra: se NON contasse nulla sarebbe verde a vuoto."""
    prima = _conta(CASO_MISTO, tz)
    assert _conta(CASO_MISTO + [_doc(id="nuova", scadenza_effettiva=_iso(-3))], tz) == prima + 1


@pytest.mark.parametrize("tz", FUSI)
def test_lista_vuota(tz):
    assert _conta([], tz) == 0
