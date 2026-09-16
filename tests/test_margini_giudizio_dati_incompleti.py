"""Niente giudizio di soglia quando il periodo ha mesi senza costi.

Misurato il 16/09/2026 su una sede reale, anno in corso: 4 mesi su 9 senza costi
merce (e 3 senza personale) portavano la media del MOL al 68%, con "MOL
eccellente — ottima redditivita' operativa" in verde. I soli mesi completi
(apr-giu) dicevano 34,9%, 39,2%, 39,3%. L'app si complimentava su dati che non
aveva.

`costi_mancanti` (fastapi_worker._kpi_periodo) gia' riconosceva il caso, ma per
il SINGOLO mese: sull'aggregato — cioe' sul periodo che la pagina apre di
default — non scattava, perche' basta che qualche mese i costi ce li abbia.

Decisione di Mattia: il CALCOLO non si tocca, il numero resta. Sparisce il
GIUDIZIO. Stessa forma del caso retail (test_margini_soglie_settore): emoji
neutra, che il frontend mappa gia' su gauge NEUTRAL perche' "ℹ️" non e' in
GAUGE_PER_EMOJI (calcolo-tab.tsx) — la riga resta e dice il valore invece di
valutarlo.
"""
import pytest

from services.routers.margini import (
    _mesi_senza_costi,
    _testo_dati_incompleti,
)


class _Mese:
    """Il minimo che `_mesi_senza_costi` legge da un MesiPivot."""

    def __init__(self, fb=0.0, spese=0.0):
        self.costi_fb_totali = fb
        self.costi_spese_totali = spese


# Il caso reale: 9 mesi attivi, 4 senza alcun costo (gen, feb, ago, set).
CASO_REALE = [
    _Mese(fb=0, spese=0),          # gen
    _Mese(fb=0, spese=0),          # feb
    _Mese(fb=37777, spese=1734),   # mar
    _Mese(fb=133473, spese=41800), # apr
    _Mese(fb=153429, spese=25932), # mag
    _Mese(fb=128889, spese=39179), # giu
    _Mese(fb=86404, spese=42452),  # lug
    _Mese(fb=0, spese=0),          # ago
    _Mese(fb=0, spese=0),          # set
]


def test_conta_i_mesi_senza_alcun_costo():
    assert _mesi_senza_costi(CASO_REALE) == 4


def test_un_periodo_tutto_completo_non_ha_mesi_da_segnalare():
    """Il contrario: se contasse sempre qualcosa, spegnerebbe i giudizi ovunque."""
    assert _mesi_senza_costi([_Mese(fb=100, spese=50), _Mese(fb=200, spese=80)]) == 0


def test_un_mese_con_le_sole_spese_non_e_senza_costi():
    """Spese senza food: il dato c'e', e' il locale che non ha comprato merce."""
    assert _mesi_senza_costi([_Mese(fb=0, spese=1200)]) == 0


def test_un_mese_con_il_solo_food_non_e_senza_costi():
    assert _mesi_senza_costi([_Mese(fb=1200, spese=0)]) == 0


def test_periodo_vuoto():
    assert _mesi_senza_costi([]) == 0


# ── Il testo che sostituisce il giudizio ─────────────────────────────────

def test_il_testo_dice_quanti_mesi_mancano():
    t = _testo_dati_incompleti(4, 9)
    assert "4" in t and "9" in t


def test_il_testo_non_contiene_un_giudizio():
    """E' l'invariante che conta: nessuna lode, nessuna condanna su dati parziali."""
    t = _testo_dati_incompleti(4, 9).lower()
    for parola in ("eccellente", "critico", "ottima", "nella norma", "elevate", "basso"):
        assert parola not in t, f"il testo neutro contiene un giudizio: {parola}"


def test_il_testo_e_al_singolare_con_un_mese_solo():
    t = _testo_dati_incompleti(1, 1)
    assert "1 mese su 1 mese" in t, t


def test_il_testo_e_al_plurale_con_piu_mesi():
    assert "2 mesi su 5 mesi" in _testo_dati_incompleti(2, 5)


# ── L'ENDPOINT vero, non solo i due helper ───────────────────────────────
#
# Provato per mutazione: con i soli test sugli helper, rimuovere il COLLEGAMENTO
# dentro get_margini_analisi (cioe' reintrodurre il bug per intero) lasciava 9
# test verdi. Un test che chiama solo le funzioni prova le funzioni, non che
# l'endpoint le usi. Stesso impianto di test_margini_soglie_settore.

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.routers import margini


def _commenti_endpoint(mesi_saved, costi_auto, data_da, data_a):
    q = MagicMock()
    for m in ("select", "eq", "in_", "gte", "lte"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=mesi_saved)
    client = MagicMock()
    client.table.return_value = q

    with patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ), patch.object(
        margini, "_calcola_costi_auto_per_periodo", MagicMock(return_value=costi_auto)
    ), patch.object(
        margini, "_load_mensile_overrides", MagicMock(return_value={})
    ), patch(
        "services.settore_service.settore_utente", MagicMock(return_value="ristorazione")
    ):
        resp = margini.get_margini_analisi(data_da, data_a, authorization="Bearer x")
    return {c.kpi_nome: c for c in resp.commenti}


def _mese(anno, mese, ricavi, personale=0.0):
    return {
        "anno": anno, "mese": mese,
        "fatturato_iva10": ricavi, "fatturato_iva22": 0.0, "altri_ricavi_noiva": 0.0,
        "altri_costi_fb": 0.0, "altri_costi_spese": 0.0,
        "quote_riparto_fb": 0.0, "quote_riparto_spese": 0.0,
        "costo_dipendenti": personale, "costo_personale_extra": 0.0,
    }


def test_endpoint_niente_giudizio_se_un_mese_del_periodo_non_ha_costi():
    """Il caso reale: gennaio senza costi dentro un periodo di due mesi."""
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 2): (30000.0, 5000.0)},   # gennaio: nessun costo
        "2026-01-01", "2026-02-28",
    )
    assert c["MOL"].emoji == "ℹ️", f"giudizio su dati incompleti: {c['MOL'].commento}"
    assert "eccellente" not in c["MOL"].commento
    assert "1 mese su 2 mesi" in c["MOL"].commento


def test_endpoint_giudica_ancora_quando_tutti_i_mesi_hanno_costi():
    """Il contrario: se spegnesse sempre i giudizi, avrebbe rotto la pagina."""
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 1): (30000.0, 5000.0), (2026, 2): (30000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    assert c["MOL"].emoji in ("🟢", "🟡", "🟠", "🔴"), c["MOL"].commento
    assert c["Food Cost"].emoji in ("🟢", "🟡", "🟠", "🔴")


def test_endpoint_il_mese_singolo_completo_resta_giudicato():
    c = _commenti_endpoint(
        [_mese(2026, 3, 110000.0)],
        {(2026, 3): (30000.0, 5000.0)},
        "2026-03-01", "2026-03-31",
    )
    assert c["MOL"].emoji != "ℹ️"


def test_endpoint_tutte_le_voci_diventano_neutre_insieme():
    """Le percentuali condividono la stessa base incompleta: o tutte o nessuna."""
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 2): (30000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    for nome in ("Food Cost", "1° Margine", "Spese Generali", "Costo del Lavoro", "MOL"):
        assert c[nome].emoji == "ℹ️", f"{nome} giudica su base incompleta"
