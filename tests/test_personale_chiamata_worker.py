"""Fase C1 «Assistente consulente»: il personale ha TRE voci che si sommano.

margini_mensili.costo_dipendenti («Lordo») + costo_personale_extra («Ore
extra») + costo_personale_chiamata («Chiamata») = costo del personale, in OGNI
lettore del worker: MOL e personale di `_kpi_periodo`, i due aggregatori del
conto economico, e i quattro punti che decidono se il personale del mese e'
«inserito» (briefing, indice di salute, card Completezza dati, alert chat).

Ogni lettore ha un caso con la SOLA chiamata > 0 (lordo 0, extra 0): e' l'unico
che separa «somma tre voci» da «somma le due di prima». Le componenti sono
distinguibili (lordo 1000, extra 200, chiamata 37) e si asseriscono una per una
dove la funzione le espone.

Dove il lettore usa una select a colonne ESPLICITE, il mock REGISTRA la stringa
passata a `.select(...)` e il test la controlla: un mock che restituisce la
colonna comunque sarebbe verde anche se la query non la chiedesse, e in
produzione PostgREST la ometterebbe (chiamata letta come 0).
"""
import os
from datetime import date
from unittest.mock import patch

import pytest

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.fastapi_worker as fw  # noqa: E402
from tests.test_costi_auto_fatture_mol import RID as RID_FAKE, _FakeSB  # noqa: E402

RID = "rist-chiamata"
COL = "costo_personale_chiamata"

# Mese "oggi" pinnato al 20/09/2026: il personale di agosto e' gia' dovuto
# (dal giorno _GIORNO_SOLLECITO_PERSONALE), quindi "inserito o no" decide.
OGGI = date(2026, 9, 20)
MC_ANNO, MC_MESE = 2026, 8


def _riga_margini(mese=MC_MESE, iva10=0.0, dip=0.0, extra=0.0, chiamata=0.0):
    return {
        "anno": MC_ANNO, "mese": mese,
        "fatturato_iva10": iva10, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "costo_dipendenti": dip, "costo_personale_extra": extra,
        COL: chiamata,
    }


class _SbRegistra:
    """Client fake che ricorda (tabella, colonne) di ogni `.select(...)`.

    Una query nuova per `table()`; tutti gli altri metodi del builder tornano la
    query stessa. `righe` mappa tabella -> righe restituite da `execute()`.
    """

    def __init__(self, righe):
        self._righe = righe
        self.select_fatte = []

    def table(self, nome):
        return _Q(self, nome)

    def rpc(self, *a, **k):
        return _Q(self, "__rpc__")

    def colonne_di(self, tabella):
        return [c for (t, c) in self.select_fatte if t == tabella]


class _Q:
    def __init__(self, sb, tabella):
        self._sb = sb
        self._t = tabella

    def select(self, colonne="*", *a, **k):
        self._sb.select_fatte.append((self._t, colonne))
        return self

    def __getattr__(self, nome):
        # Ogni filtro/modificatore del builder (eq, in_, gte, range, ...).
        return lambda *a, **k: self

    def execute(self):
        dati = list(self._sb._righe.get(self._t, []))

        class _R:
            data = dati
            count = len(dati)

        return _R()


def _oggi_pinnato():
    """`datetime.now` pinnato a OGGI: le funzioni importano datetime localmente."""
    import datetime as _dtmod

    class _FakeDateTime(_dtmod.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dtmod.datetime(OGGI.year, OGGI.month, OGGI.day, 12, 0, tzinfo=tz)

    return patch.object(_dtmod, "datetime", _FakeDateTime)


def _select_margini_chiede_chiamata(sb):
    colonne = sb.colonne_di("margini_mensili")
    con_personale = [c for c in colonne if "costo_dipendenti" in c]
    assert con_personale, f"nessuna select del personale su margini_mensili: {colonne}"
    for c in con_personale:
        assert COL in c, f"la select non chiede {COL}: {c!r}"


# ─────────────────────────────────────────────────────────────────────────────
# _kpi_periodo — Home KPI, buona notizia del briefing, prompt chat
# ─────────────────────────────────────────────────────────────────────────────

def test_kpi_periodo_solo_chiamata_riduce_il_mol():
    margini = {5: {"altri_ricavi_noiva": 10000, "costo_dipendenti": 0,
                   "costo_personale_extra": 0, COL: 37}}
    kpi = fw._kpi_periodo(margini, costi_fb={5: 1000}, costi_spese={}, mese=5)
    assert kpi["costo_personale"] == pytest.approx(37.0)
    # 10000 - 1000 F&B - 37 chiamata
    assert kpi["mol"] == pytest.approx(8963.0)


def test_kpi_periodo_solo_chiamata_e_un_mese_con_dati():
    margini = {5: {"costo_dipendenti": 0, "costo_personale_extra": 0, COL: 37}}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=5)
    assert kpi["has_data"] is True
    assert kpi["costo_personale"] == pytest.approx(37.0)


def test_kpi_periodo_somma_le_tre_voci():
    margini = {5: {"altri_ricavi_noiva": 10000, "costo_dipendenti": 1000,
                   "costo_personale_extra": 200, COL: 37}}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=5)
    assert kpi["costo_personale"] == pytest.approx(1237.0)
    assert kpi["mol"] == pytest.approx(10000 - 1237.0)


def test_kpi_periodo_chiamata_assente_vale_zero():
    """Righe vecchie (o NULL) senza la colonna: niente errore, vale 0."""
    margini = {5: {"altri_ricavi_noiva": 10000, "costo_dipendenti": 1000,
                   "costo_personale_extra": 200, COL: None}}
    kpi = fw._kpi_periodo(margini, costi_fb={}, costi_spese={}, mese=5)
    assert kpi["costo_personale"] == pytest.approx(1200.0)


# ─────────────────────────────────────────────────────────────────────────────
# _aggrega_mensili_margini / _aggrega_totali_margini — conto economico Margini
# ─────────────────────────────────────────────────────────────────────────────

def _margini_fake(dip=0.0, extra=0.0, chiamata=0.0):
    return [{
        "ristorante_id": RID_FAKE, "anno": 2026, "mese": 3,
        "fatturato_iva10": 0, "fatturato_iva22": 0, "altri_ricavi_noiva": 10000.0,
        "altri_costi_fb": 1500.0, "altri_costi_spese": 300.0,
        "quote_riparto_fb": 0, "quote_riparto_spese": 0,
        "costo_dipendenti": dip, "costo_personale_extra": extra, COL: chiamata,
    }]


MARZO = (date(2026, 3, 1), date(2026, 3, 31))


def test_aggrega_totali_solo_chiamata():
    tot = fw._aggrega_totali_margini(
        _FakeSB(margini=_margini_fake(chiamata=37.0)), RID_FAKE, *MARZO)
    assert tot["pers"] == pytest.approx(37.0)
    # 10000 - 1500 F&B - 300 spese - 37 chiamata
    assert tot["mol"] == pytest.approx(8163.0)


def test_aggrega_mensili_solo_chiamata():
    mens = fw._aggrega_mensili_margini(
        _FakeSB(margini=_margini_fake(chiamata=37.0)), RID_FAKE, *MARZO)
    assert mens["pers"] == pytest.approx(37.0)
    assert mens["spark_personale"] == [37.0]
    assert mens["mol"] == pytest.approx(8163.0)
    assert mens["spark_mol"] == [8163.0]


def test_parita_kpi_e_analisi_con_extra_e_chiamata():
    """Home KPI e pagina Margini sullo stesso mese: stesso personale, stesso MOL.

    Tutte e tre le voci > 0 e diverse: una funzione che ne dimenticasse una
    divergerebbe dalle altre di 200 o di 37.
    """
    righe = _margini_fake(dip=1000.0, extra=200.0, chiamata=37.0)
    tot = fw._aggrega_totali_margini(_FakeSB(margini=righe), RID_FAKE, *MARZO)
    mens = fw._aggrega_mensili_margini(_FakeSB(margini=righe), RID_FAKE, *MARZO)
    kpi = fw._kpi_periodo({3: righe[0]}, costi_fb={}, costi_spese={}, mese=3)

    assert tot["pers"] == pytest.approx(1237.0)
    assert mens["pers"] == pytest.approx(1237.0)
    assert kpi["costo_personale"] == pytest.approx(1237.0)
    # 10000 - 1500 - 300 - 1237
    assert tot["mol"] == pytest.approx(6963.0)
    assert mens["mol"] == pytest.approx(6963.0)
    assert kpi["mol"] == pytest.approx(6963.0)


# ─────────────────────────────────────────────────────────────────────────────
# «Personale inserito»: briefing, indice di salute, card, alert chat
# ─────────────────────────────────────────────────────────────────────────────

def _righe_tabelle(chiamata, iva10=10000.0):
    return {
        "margini_mensili": [_riga_margini(iva10=iva10, chiamata=chiamata)],
        # incasso di ieri presente: il briefing non parla d'altro
        "ricavi_giornalieri": [{"data": "2026-09-19"}],
    }


def _topics_briefing(chiamata):
    sb = _SbRegistra(_righe_tabelle(chiamata))
    with _oggi_pinnato():
        out = fw._briefing_dati_mensili_mancanti(RID, sb)
    return {n["topic_key"] for n in out}, sb


def test_briefing_solo_chiamata_e_personale_inserito():
    topics, sb = _topics_briefing(37.0)
    assert "costo_personale_mancante" not in topics
    _select_margini_chiede_chiamata(sb)


def test_briefing_senza_chiamata_sollecita_il_personale():
    """Controllo: con la chiamata a 0 lo stesso scenario sollecita."""
    topics, _ = _topics_briefing(0.0)
    assert "costo_personale_mancante" in topics


def _salute_rossa(chiamata):
    """Fatture di costo presenti, fatturato 0, nessuna riga da classificare:
    il personale e' il voto che decide (25 se manca -> rosso, 50 se c'e')."""
    import services.daily_briefing_service as dbs

    voci_viste = []
    calcola_vero = dbs.calcola_indice_salute

    def _registra(voci, spente=None):
        voci_viste.append(dict(voci))
        return calcola_vero(voci, spente)

    sb = _SbRegistra(_righe_tabelle(chiamata, iva10=0.0))
    with _oggi_pinnato(), \
            patch.object(fw, "_costi_automatici_mese", return_value=5000.0), \
            patch.object(dbs, "calcola_indice_salute", side_effect=_registra):
        rosso = fw._salute_indice_rosso(RID, sb)
    assert len(voci_viste) == 1, voci_viste
    return rosso, voci_viste[0], sb


def test_salute_solo_chiamata_non_e_rossa():
    rosso, voci, sb = _salute_rossa(37.0)
    assert voci["personale"] == 100
    assert rosso is False
    _select_margini_chiede_chiamata(sb)


def test_salute_senza_chiamata_e_rossa():
    rosso, voci, _ = _salute_rossa(0.0)
    assert voci["personale"] == 0
    assert rosso is True


def _voce_personale_card(chiamata):
    sb = _SbRegistra(_righe_tabelle(chiamata))
    with patch.object(fw, "_resolve_user_from_token", return_value={"id": "user-1"}), \
            patch.object(fw, "_get_supabase_client", return_value=sb), \
            patch.object(fw, "_resolve_ristorante_id", return_value=RID), \
            patch.object(fw, "_costi_automatici_mese", return_value=5000.0), \
            _oggi_pinnato():
        resp = fw.home_salute(authorization="Bearer x")
    return next(v for v in resp.voci if v.key == "personale"), sb


def test_card_completezza_solo_chiamata_e_personale_inserito():
    voce, sb = _voce_personale_card(37.0)
    assert voce.ok is True
    _select_margini_chiede_chiamata(sb)


def test_card_completezza_senza_chiamata_manca():
    voce, _ = _voce_personale_card(0.0)
    assert voce.ok is False


def _prompt_chat(chiamata):
    sb = _SbRegistra(_righe_tabelle(chiamata))
    with _oggi_pinnato(), \
            patch.object(fw, "_oggi_rome", return_value=OGGI), \
            patch.object(fw, "_costi_automatici_mese", return_value=5000.0):
        prompt = fw._build_chat_system_prompt(
            {"id": "user-1", "pagine_abilitate": ["margini"]},
            sb,
            None,
            ristorante_id=RID,
        )
    return prompt, sb


def test_chat_solo_chiamata_non_dice_personale_mancante():
    prompt, sb = _prompt_chat(37.0)
    assert "Costo del personale non registrato" not in prompt
    _select_margini_chiede_chiamata(sb)


def test_chat_senza_chiamata_dice_personale_mancante():
    prompt, _ = _prompt_chat(0.0)
    assert "Costo del personale non registrato" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# margine_service.carica_margini_anno — sorgente di _kpi_periodo (Home, chat)
# ─────────────────────────────────────────────────────────────────────────────

def test_carica_margini_anno_chiede_la_chiamata():
    import services.margine_service as ms

    sb = _SbRegistra({"margini_mensili": [_riga_margini(mese=8, chiamata=37.0)]})
    with patch.object(ms, "get_supabase_client", return_value=sb):
        dati = ms.carica_margini_anno("user-1", RID, MC_ANNO)

    colonne = sb.colonne_di("margini_mensili")
    assert len(colonne) == 1, colonne
    assert COL in colonne[0], f"carica_margini_anno non chiede {COL}: {colonne[0]!r}"
    # e la riga arriva intera a _kpi_periodo, che la conta
    kpi = fw._kpi_periodo(dati, costi_fb={}, costi_spese={}, mese=8)
    assert kpi["costo_personale"] == pytest.approx(37.0)
