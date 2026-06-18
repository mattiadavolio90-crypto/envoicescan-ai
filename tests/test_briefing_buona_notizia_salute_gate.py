"""Test guardia per il gate Salute della 'buona notizia' MOL nel briefing.

Difetto osservato (LAND DEI SAPORI, 17/06): il briefing apriva festante
("margine € 280.924, +172,1%!") mentre la card "Salute della gestione"
mostrava 0% / "dati incompleti". Le due sezioni leggono lo stesso margine ma
con criteri diversi: il MOL viene da dati inseriti a mano, la Salute pesa anche
la freschezza (fatture caricate negli ultimi 30 gg, mese consolidato).

Regola decisa: se la Salute e' ROSSA non si apre con la festa del MOL. L'incasso
di ieri resta (e' un fatto fresco e neutro, non una celebrazione del margine).
Qui verifichiamo SOLO il gate, isolando il blocco MOL con i mock.
"""
from unittest.mock import MagicMock, patch

from services.fastapi_worker import _briefing_buona_notizia

UID = "user-aaa"
RID = "rist-bbb"


def _sb_senza_incasso():
    """Supabase mock: ricavi_giornalieri di ieri vuoto -> nessun fallback incasso,
    cosi' l'output dipende SOLO dal blocco MOL (quello che il gate governa).
    """
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _margini_in_crescita():
    """Due mesi consecutivi con MOL positivo e in crescita -> 'buona notizia' MOL.

    _kpi_periodo legge 'mol' grezzo dalla riga del mese: basta popolarlo. Le altre
    voci non servono per il ramo mol_curr > mol_prec > 0.
    """
    # mese corrente "appena chiuso" deve avere mol > del precedente.
    # Mappa mese->riga; copriamo qualunque mese il codice scelga come ultimo
    # completo, dando a ogni mese un MOL e al precedente uno piu' basso.
    return {m: {"mol": 1000 + m, "fatturato_iva10": 50000} for m in range(1, 13)}


def _patch_loaders(costi=True):
    """Patcha i loader del margine importati dentro _briefing_buona_notizia.

    `costi=True` -> costi food/spese presenti in ogni mese, cosi' il gate
    'costi_mancanti' NON scatta e si testa SOLO il gate Salute. `costi=False`
    -> mese senza costi (food + spese = 0), per testare il gate costi.
    """
    margini = _margini_in_crescita()
    if costi:
        cfb = {m: 5000.0 for m in range(1, 13)}
        csp = {m: 1000.0 for m in range(1, 13)}
    else:
        cfb, csp = {}, {}
    return patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=MagicMock(return_value=(cfb, csp)),
    )


def test_salute_rossa_sopprime_buona_notizia_mol():
    sb = _sb_senza_incasso()
    with _patch_loaders(), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=True
    ) as rosso:
        out = _briefing_buona_notizia(UID, RID, sb)
    rosso.assert_called_once()
    # Salute rossa + nessun incasso di ieri -> niente apertura festante.
    assert out is None


def test_salute_non_rossa_mostra_buona_notizia_mol():
    sb = _sb_senza_incasso()
    with _patch_loaders(), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is not None
    assert out["topic_key"] == "buona_notizia"
    assert out["payload"]["tipo"] == "mol_mese"


def test_costi_mancanti_sopprime_buona_notizia_mol():
    """Anche con Salute non rossa, un mese con ricavi ma ZERO costi (food+spese)
    non si festeggia: il MOL sarebbe fatturato - personale, un '+X%' falso."""
    sb = _sb_senza_incasso()
    with _patch_loaders(costi=False), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is None
