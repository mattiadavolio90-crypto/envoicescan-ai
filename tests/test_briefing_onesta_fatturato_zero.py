"""Presidio: nessuna "buona notizia" su mesi senza incassi.

Difetto osservato in PRODUZIONE (sede dcf1996e, briefing dell'1 e 2/9/2026):

    «Agosto mostra un miglioramento: la perdita è scesa a € 9.380»

Luglio E agosto avevano fatturato 0,00 a DB. La "perdita" era la sola somma dei
costi, e il "miglioramento" era che ne erano stati inseriti MENO. L'assistente
dichiarava un progresso dove non c'era nemmeno un incasso.

Perche' il gate storico non lo fermava: guardava solo `costi_mancanti`, che per
costruzione (`_kpi_periodo`) e' `fatturato > 0 and fb <= 0 and spese <= 0` —
cioe' e' False PROPRIO quando il fatturato e' 0. Il gate lasciava passare
esattamente il caso che doveva fermare.

Qui si presidia la regola nuova (`_mesi_confrontabili`): un confronto di MOL si
dichiara solo se ENTRAMBI i mesi hanno fatturato > 0.
"""
from datetime import date
from unittest.mock import MagicMock, patch

from services.fastapi_worker import _briefing_buona_notizia, _mesi_confrontabili

UID = "user-aaa"
RID = "rist-bbb"

_DENTRO_FINESTRA_MOL = patch(
    "services.fastapi_worker._oggi_rome", return_value=date(2026, 9, 3)
)


def _sb_senza_incasso():
    q = MagicMock()
    q.table.return_value = q
    q.select.return_value = q
    q.eq.return_value = q
    q.limit.return_value = q
    q.lt.return_value = q
    q.execute.return_value = MagicMock(data=[])
    return q


def _patch_loaders(margini, cfb, csp):
    return patch.multiple(
        "services.margine_service",
        carica_margini_anno=MagicMock(return_value=margini),
        calcola_costi_automatici_per_anno_sql=MagicMock(return_value=(cfb, csp)),
    )


def test_perdita_in_calo_non_scatta_con_fatturato_zero():
    """Il caso di produzione, riprodotto: due mesi a fatturato 0 con costi.

    Luglio (mese 7): costi 12.000 -> MOL -12.000
    Agosto (mese 8): costi  9.380 -> MOL  -9.380  (meno negativo = "migliore")

    Senza il gate sul fatturato, questo e' esattamente «la perdita e' scesa».
    """
    margini = {m: {} for m in range(1, 13)}
    cfb = {7: 12000.0, 8: 9380.0}
    csp = {}
    sb = _sb_senza_incasso()
    with _DENTRO_FINESTRA_MOL, _patch_loaders(margini, cfb, csp), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is None, f"festeggiata una perdita su mesi senza incassi: {out}"


def test_perdita_in_calo_non_scatta_se_solo_un_mese_ha_incassi():
    """Basta UNO dei due mesi senza incassi: il confronto non regge.

    Agosto ha incassi veri ma chiude in perdita; luglio non ha incassi e la sua
    "perdita" e' la sola somma dei costi. Dire «la perdita e' scesa» significa
    confrontare una perdita commerciale con un mese che non e' mai esistito.

    NOTA sul ramo "MOL in crescita": quel caso non e' raggiungibile con fatturato
    0, perche' il MOL e' `netto - costi` e con netto 0 non puo' essere positivo
    (verificato su `_kpi_periodo`). Il gate sul fatturato difende quindi il ramo
    "perdita in calo" — che e' esattamente quello che ha sbagliato in produzione.
    """
    margini = {m: {} for m in range(1, 13)}
    margini[8] = {"altri_ricavi_noiva": 30000.0}
    cfb = {7: 12000.0, 8: 34000.0}
    csp = {7: 500.0, 8: 1000.0}
    sb = _sb_senza_incasso()
    with _DENTRO_FINESTRA_MOL, _patch_loaders(margini, cfb, csp), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is None, f"confronto dichiarato contro un mese senza incassi: {out}"


def test_mol_in_crescita_scatta_quando_entrambi_i_mesi_hanno_incassi():
    """Il controllo non deve zittire il caso legittimo: due mesi veri, MOL su.

    Senza questo, «non dice mai niente» passerebbe per un presidio verde.
    """
    margini = {
        m: {"altri_ricavi_noiva": 40000.0 + m * 1000} for m in range(1, 13)
    }
    cfb = {m: 5000.0 for m in range(1, 13)}
    csp = {m: 1000.0 for m in range(1, 13)}
    sb = _sb_senza_incasso()
    with _DENTRO_FINESTRA_MOL, _patch_loaders(margini, cfb, csp), patch(
        "services.fastapi_worker._salute_indice_rosso", return_value=False
    ):
        out = _briefing_buona_notizia(UID, RID, sb)
    assert out is not None, "il caso legittimo e' stato zittito"
    assert out["payload"]["tipo"] == "mol_mese"


def test_regola_in_isolamento():
    """La regola da sola, senza il resto della funzione."""
    pieno = {"fatturato": 10000.0, "costi_mancanti": False}
    vuoto = {"fatturato": 0.0, "costi_mancanti": False}
    senza_costi = {"fatturato": 10000.0, "costi_mancanti": True}

    assert _mesi_confrontabili(pieno, pieno) is True
    assert _mesi_confrontabili(vuoto, pieno) is False
    assert _mesi_confrontabili(pieno, vuoto) is False
    assert _mesi_confrontabili(senza_costi, pieno) is False
    assert _mesi_confrontabili(pieno, senza_costi) is False
