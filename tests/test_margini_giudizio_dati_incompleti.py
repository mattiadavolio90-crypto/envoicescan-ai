"""Niente giudizio di soglia quando il periodo ha mesi senza costi.

Misurato il 16/09/2026 su una sede reale, anno in corso: 3 mesi su 9 senza alcun
costo (e 3 senza personale) portavano la media del MOL al 68%, con "MOL
eccellente — ottima redditivita' operativa" in verde. I soli mesi completi
(apr-giu) dicevano 34,9%, 39,2%, 39,3%. L'app si complimentava su dati che non
aveva.

**La cifra e' 3, non 4.** Alla prima stesura avevo scritto 4 contando gennaio
fra i mesi vuoti: gennaio ha 114,08 EUR di `quote_riparto_spese` (quota di un
costo di gruppo), che entra in `costi_spese_totali` e quindi lo rende un mese
"con costi". L'avevo misurato guardando `altri_costi_*` senza le quote — il
reviewer l'ha ri-misurato e aveva ragione. La fixture qui sotto rispecchia i
dati veri, quote comprese.

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
    """Il minimo che `_mesi_senza_costi` legge da un MesiPivot.

    Dal 16/10/2026 `_mesi_senza_costi` legge `senza_merce`, deciso da
    `get_margini_analisi` con la regola unica: qui si calcola allo stesso modo,
    con un incasso netto di 400.000 EUR (le spese non contano)."""

    def __init__(self, fb=0.0, spese=0.0, netto=400000.0):
        from services.completezza_mese import merce_insufficiente
        self.costi_fb_totali = fb
        self.costi_spese_totali = spese
        self.fatturato_netto = netto
        self.senza_merce = merce_insufficiente(netto, fb)


# Il caso reale, coi valori letti a DB: 9 mesi attivi, 4 senza fatture merce
# (gen, feb, ago, set). Gennaio E' fra questi dal 23/09/2026: i suoi 114,08 EUR
# sono una quota di riparto SPESE, e con la soglia nuova (solo F&B) un mese di
# sole spese resta scoperto — vedi docstring.
#
# Dal 16/10/2026 i mesi senza merce sono 5: anche marzo, 37.777 EUR su 405.016
# netti (9,3%), il mese in cui la sede e' entrata (prima fattura il 7 marzo).
# Netti del 16/10 (cc016821, regola unica in services/completezza_mese.py).
CASO_REALE = [
    _Mese(fb=0, spese=114.08, netto=392806),     # gen: sola quota di riparto di gruppo
    _Mese(fb=0, spese=0, netto=358677),          # feb
    _Mese(fb=37777, spese=1734, netto=405016),   # mar: 9,3%
    _Mese(fb=133473, spese=41800, netto=361181), # apr
    _Mese(fb=153429, spese=25932, netto=393422), # mag
    _Mese(fb=128889, spese=39179, netto=375963), # giu
    _Mese(fb=86404, spese=42452, netto=373626),  # lug: 23,1%
    _Mese(fb=0, spese=0, netto=416798),          # ago
    _Mese(fb=0, spese=0, netto=357950),          # set
]


def test_conta_i_mesi_senza_fatture_merce():
    """Cinque: dal 23/09/2026 gennaio (sole spese), dal 16/10/2026 marzo (9,3%)."""
    assert _mesi_senza_costi(CASO_REALE) == 5


def test_una_quota_di_riparto_spese_non_basta_a_completare_il_mese():
    """Il caso di gennaio: 114,08 EUR di sola quota di gruppo, e il mese NON conta.

    Fino al 23/09/2026 quei 114 EUR bastavano a dichiararlo completo, e la
    tabella Margini mostrava il MOL in verde all'86% su 444.000 EUR di ricavi
    con food cost 0% (SUSHILAND, tutte e tre le sedi). Decisione di Mattia:
    senza fatture della merce il mese non si giudica, quale che sia la bolletta.

    Una quota di riparto F&B invece lo completa davvero: e' merce, comprata dal
    gruppo e ripartita sulla sede.

    E' la stessa soglia di `costi_mancanti` (fastapi_worker._kpi_periodo): la
    coerenza fra i due e' voluta.
    """
    assert _mesi_senza_costi([_Mese(fb=0, spese=114.08)]) == 1
    assert _mesi_senza_costi([_Mese(fb=114.08, spese=0, netto=500.0)]) == 0
    assert _mesi_senza_costi([_Mese(fb=0, spese=0)]) == 1


def test_un_periodo_tutto_completo_non_ha_mesi_da_segnalare():
    """Il contrario: se contasse sempre qualcosa, spegnerebbe i giudizi ovunque."""
    assert _mesi_senza_costi([_Mese(fb=100, spese=50, netto=500), _Mese(fb=200, spese=80, netto=900)]) == 0


def test_un_mese_con_le_sole_spese_resta_senza_costi():
    """Spese senza merce: le fatture non sono arrivate, non e' un locale a digiuno.

    Era l'assunzione opposta fino al 23/09/2026 («e' il locale che non ha
    comprato merce»). I dati l'hanno smentita: CASATI Set 2026 incassava
    5.696 EUR con 101 EUR di sole utenze, e un ristorante che incassa senza
    comprare merce non esiste — mancano le fatture, e il MOL al 98% e' finto.
    """
    assert _mesi_senza_costi([_Mese(fb=0, spese=1200)]) == 1


def test_un_mese_con_il_solo_food_non_e_senza_costi():
    assert _mesi_senza_costi([_Mese(fb=1200, spese=0, netto=6000)]) == 0


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
    # La spiegazione compare UNA volta sola, non su tutte e cinque le voci: e' la
    # stessa frase per tutte, e ripetuta cinque volte non la legge nessuno.
    con_testo = [n for n, x in c.items() if "1 mese su 2 mesi" in x.commento]
    assert len(con_testo) == 1, f"spiegazione ripetuta su {con_testo}"


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


def test_endpoint_nessun_commento_e_mai_vuoto():
    """Nessuna voce esce con commento "" — il frontend lo renderebbe come riga bianca.

    `calcolo-tab.tsx` rende `commento?.commento ?? "—"`: il `??` scatta su
    null/undefined, NON su stringa vuota. Mostrare la spiegazione lunga una volta
    sola (giusto) tentava di lasciare le altre a "", che a video e' uno spazio
    bianco sotto al gauge invece del trattino. Le altre portano il rimando breve.
    """
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 2): (30000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    for nome, voce in c.items():
        assert voce.commento.strip(), f"{nome} ha commento vuoto"


def test_la_spiegazione_sta_su_una_voce_che_il_frontend_mostra():
    """La frase con le cifre non deve finire sull'unica voce senza gauge.

    Il worker manda CINQUE commenti, `calcolo-tab.tsx` rende QUATTRO gauge:
    "Costo del Lavoro" non ne ha uno. Ancorare la spiegazione alla prima voce
    della lista funzionava per caso — riordinandola, la frase con le cifre
    sarebbe finita sull'unica voce che nessuno vede, e il cliente avrebbe letto
    cinque volte il rimando breve senza mai il motivo.
    """
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 2): (30000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    con_cifre = [n for n, x in c.items() if "1 mese su 2 mesi" in x.commento]
    assert len(con_cifre) == 1, f"spiegazione su {len(con_cifre)} voci: {con_cifre}"
    assert con_cifre[0] != "Costo del Lavoro", (
        "la spiegazione e' sull'unica voce senza gauge: il cliente non la vede"
    )


# ── La soglia del 20% (audit di ottobre 2026, K03) ─────────────────────────
#
# 110.000 EUR al 10% = 100.000 netti: 19.000 EUR di merce (19%) e' un mese senza
# merce, 21.000 (21%) no. La decisione e' del worker (`senza_merce` in MesiPivot,
# regola unica in services/completezza_mese.py), il frontend la legge.

def test_endpoint_un_mese_al_19_per_cento_spegne_il_giudizio():
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 1): (21000.0, 5000.0), (2026, 2): (19000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    assert c["MOL"].emoji == "ℹ️", c["MOL"].commento
    assert "1 mese su 2 mesi" in " ".join(x.commento for x in c.values())


def test_endpoint_due_mesi_al_21_per_cento_restano_giudicati():
    c = _commenti_endpoint(
        [_mese(2026, 1, 110000.0), _mese(2026, 2, 110000.0)],
        {(2026, 1): (21000.0, 5000.0), (2026, 2): (21000.0, 5000.0)},
        "2026-01-01", "2026-02-28",
    )
    assert c["MOL"].emoji != "ℹ️", c["MOL"].commento


from datetime import date  # noqa: E402


def _pivot_endpoint(mesi_saved, costi_auto, data_da, data_a, oggi, fine_coperta=()):
    q = MagicMock()
    for m in ("select", "eq", "in_", "gte", "lte"):
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=mesi_saved)
    client = MagicMock()
    client.table.return_value = q
    import services.fastapi_worker as fw
    with patch.multiple(
        margini,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _get_supabase_client=MagicMock(return_value=client),
        _resolve_ristorante_id=MagicMock(return_value="rist-1"),
    ), patch.object(
        margini, "_calcola_costi_auto_per_periodo",
        # Come la funzione vera: solo i mesi chiesti, e `fine_mese` riempito per i
        # mesi con una fattura di merce negli ultimi 5 giorni (`fine_coperta`).
        MagicMock(side_effect=lambda _sb, _rid, mesi, fine_mese=None: (
            fine_mese.update({k: True for k in fine_coperta if k in mesi}) if fine_mese is not None else None,
            {k: v for k, v in costi_auto.items() if k in mesi},
        )[1]),
    ), patch.object(margini, "_load_mensile_overrides", MagicMock(return_value={})), \
         patch.object(fw, "_oggi_rome", return_value=oggi), \
         patch("services.settore_service.settore_utente", return_value="ristorazione"):
        return margini.get_margini_analisi(data_da, data_a, authorization="Bearer x")


def test_il_pivot_porta_senza_merce_e_il_mese_in_corso_resta_sulla_merce_assente():
    resp = _pivot_endpoint(
        [_mese(2026, 9, 110000.0), _mese(2026, 10, 110000.0)],
        {(2026, 9): (14000.0, 5000.0), (2026, 10): (2000.0, 500.0)},
        "2026-09-01", "2026-10-31", date(2026, 10, 15),
    )
    per_mese = {p.mese: p.senza_merce for p in resp.mesi}
    assert per_mese == {9: True, 10: False}


def test_il_pivot_mette_in_attesa_il_mese_senza_fatture_di_fine_mese():
    """Agosto ha una fattura di merce negli ultimi 5 giorni, settembre no:
    settembre e' in attesa, agosto no, ottobre (in corso) mai."""
    resp = _pivot_endpoint(
        [_mese(2026, 8, 110000.0), _mese(2026, 9, 110000.0), _mese(2026, 10, 110000.0)],
        {(2026, 8): (25000.0, 5000.0), (2026, 9): (25000.0, 5000.0), (2026, 10): (5000.0, 0.0)},
        "2026-08-01", "2026-10-31", date(2026, 10, 15), fine_coperta={(2026, 8)},
    )
    assert {p.mese: p.in_attesa for p in resp.mesi} == {8: False, 9: True, 10: False}
    # l'attesa non spegne il giudizio del periodo
    assert not any(p.senza_merce for p in resp.mesi if p.mese in (8, 9))


def test_il_pivot_chiede_le_date_al_caricamento_dei_costi():
    """Senza `fine_mese` passato al caricamento, nessun mese avrebbe la fine
    coperta e ogni mese chiuso sarebbe in attesa."""
    resp = _pivot_endpoint(
        [_mese(2026, 8, 110000.0)], {(2026, 8): (25000.0, 5000.0)},
        "2026-08-01", "2026-08-31", date(2026, 10, 15), fine_coperta={(2026, 8)},
    )
    assert resp.mesi[0].in_attesa is False


def test_il_pivot_non_mette_in_attesa_un_mese_di_sola_merce_a_mano():
    """Merce tutta inserita a mano, nessuna fattura: non c'e' una data da
    aspettare, il mese non resta grigio per sempre."""
    a_mano = dict(_mese(2026, 9, 110000.0), altri_costi_fb=25000.0)
    resp = _pivot_endpoint([a_mano], {}, "2026-09-01", "2026-09-30", date(2026, 10, 15))
    assert resp.mesi[0].in_attesa is False and resp.mesi[0].senza_merce is False
