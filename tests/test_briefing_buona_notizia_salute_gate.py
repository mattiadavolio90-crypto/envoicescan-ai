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
from datetime import date
from unittest.mock import MagicMock, patch

from services.fastapi_worker import _briefing_buona_notizia

UID = "user-aaa"
RID = "rist-bbb"

# Il blocco MOL parla del mese chiuso SOLO nella finestra fine/inizio mese
# (decisione 19/06). I test del MOL fissano "oggi" al 3 del mese (dentro i primi 7).
_DENTRO_FINESTRA_MOL = patch(
    "services.fastapi_worker._oggi_rome", return_value=date(2026, 7, 3)
)


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
    """Mesi con MOL positivo e CRESCENTE -> 'buona notizia' MOL.

    Il MOL è ora RICALCOLATO da _kpi_periodo (netto − costi), non letto dal campo
    salvato. Uso altri_ricavi_noiva crescente (niente scorporo IVA): con i costi
    food/spese fissi del patch (5000+1000), il MOL = (10000 + m*1000) − 6000 =
    4000 + m*1000, positivo e crescente mese su mese.
    """
    return {m: {"altri_ricavi_noiva": 10000 + m * 1000} for m in range(1, 13)}


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
    with _DENTRO_FINESTRA_MOL, _patch_loaders(), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=True
    ) as rosso:
        out = _briefing_buona_notizia(UID, RID, sb)
    rosso.assert_called_once()
    # Salute rossa + nessun incasso di ieri -> niente apertura festante.
    assert out is None


def test_salute_non_rossa_mostra_buona_notizia_mol():
    sb = _sb_senza_incasso()
    with _DENTRO_FINESTRA_MOL, _patch_loaders(), patch(
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
    with _DENTRO_FINESTRA_MOL, _patch_loaders(costi=False), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is None


def test_fuori_finestra_niente_mol():
    """Decisione 19/06: fuori dalla finestra fine/inizio mese il MOL NON si cita,
    anche se in crescita e Salute non rossa. Oggi = 15 del mese (fuori finestra)."""
    sb = _sb_senza_incasso()
    with patch(
        "services.fastapi_worker._oggi_rome", return_value=date(2026, 7, 15)
    ), _patch_loaders(), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    # Nessun incasso di ieri nel mock -> senza il MOL non resta nulla.
    assert out is None
