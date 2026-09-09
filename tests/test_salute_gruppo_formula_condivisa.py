"""L'indice di Salute della CATENA deve dare lo stesso numero di quello del PV.

Difetto misurato il 9/9/2026 sui dati veri (7 sedi di catena in produzione).
`_salute_indici_batch` era la TERZA copia della formula, rimasta fuori dal
consolidamento del 2/9 (che aveva unito home_salute e _salute_indice_rosso), e
divergeva in due modi indipendenti:

1a. DENOMINATORE FISSO: divideva sempre per 4, ignorando i toggle del
    configuratore. Una voce spenta valeva 0 qui e usciva dal denominatore nel PV
    -> stessa sede, due indici diversi. Nessuna SEDE DI CATENA aveva voci della
    Salute spente al momento del fix (una sede non-catena, CASATI 14, ha 4 topic
    spenti ma nessuno mappa sulle 4 voci di _VOCE_TOPIC_SALUTE): e' un presidio,
    non una correzione visibile.

1b. VOCE "FATTURE" SU UN'ALTRA POPOLAZIONE: contava le RIGHE caricate negli
    ultimi 30 giorni invece degli EURO di costi del mese chiuso (criterio del PV
    da fastapi_worker:7195-7206, introdotto proprio per togliere questo falso
    verde). Misurato in produzione l'8/9, mese chiuso agosto 2026:
      - LAND DEI SAPORI:        3.344 righe caricate, 0 EUR di competenza -> 75 in
                                catena, voce ROSSA nel PV. Col fix: 50.
      - SUSHILAND VILLA GUARDIA: 1.564 righe, 0 EUR -> 74. Col fix: 49.

    NB: la voce `classificate` resta gateata sulle RIGHE caricate (tot_righe), non
    sulla voce `fatture` — e' cosi' anche nel PV (fastapi_worker:7327): misura la
    qualita' di cio' che e' entrato, non la competenza del mese. Una prima stima
    dava 25 perche' la query di misura la azzerava insieme a `fatture`: il numero
    giusto e' 50.
      - OFFSIDE SPORTS PUB:      221 righe, 13.893 EUR -> 49 prima e dopo (sano).
    Verificato con la RPC di produzione costi_automatici_mensili_gruppo: per LAND
    e VILLA GUARDIA agosto non restituisce alcuna riga.

Questi test misurano il COMPORTAMENTO (numeri in, numeri out): un assert sul
sorgente sopravviverebbe alla mutazione della formula.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from services.daily_briefing_service import calcola_indice_salute  # noqa: E402
from services.routers import gruppo  # noqa: E402

RID = "sede-1"


def _row(rid=RID, n_fatture=100, n_needs=0, netto=1000.0, personale=500.0):
    return {
        "ristorante_id": rid, "n_fatture": n_fatture, "n_needs_review": n_needs,
        "netto": netto, "personale": personale,
    }


@pytest.fixture
def no_toggle(monkeypatch):
    """Nessuna voce spenta: isola le altre dimensioni del calcolo."""
    monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {r: set() for r in ids})


class TestVociSpente:
    """1a — una voce spenta esce dal denominatore, non vale zero."""

    def test_la_voce_spenta_alza_l_indice(self, monkeypatch):
        # fatture ok, fatturato assente, personale ok, 100% classificate.
        row = _row(netto=0.0)
        monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {RID: set()})
        con_tutte = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese={RID: 500.0})
        monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {RID: {"fatturato"}})
        senza = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese={RID: 500.0})
        assert con_tutte == {RID: 75}, "media su 4 voci (100+0+100+100)/4"
        assert senza == {RID: 100}, "la spenta ESCE dal denominatore: (100+100+100)/3"

    def test_e_lo_stesso_numero_della_formula_del_pv(self, monkeypatch):
        """Il presidio vero: catena e PV devono dare lo stesso risultato sui
        medesimi punteggi. Se qualcuno riscrive la formula qui, questo test cade."""
        row = _row(n_fatture=200, n_needs=20, netto=0.0, personale=0.0)
        monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {RID: {"personale"}})
        catena = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese={RID: 1.0})
        pv = calcola_indice_salute(
            {"fatture": 100, "fatturato": 0, "personale": 0, "classificate": 90},
            {"personale"},
        )
        assert catena[RID] == pv

    def test_tutte_spente_non_e_misurabile(self, monkeypatch):
        tutte = {"fatture", "fatturato", "personale", "classificate"}
        monkeypatch.setattr(gruppo, "_voci_spente_per_sede", lambda sb, ids: {RID: tutte})
        out = gruppo._salute_indici_batch(None, [RID], rows=[_row()], costi_mese={RID: 0.0})
        assert out == {RID: 100}, "nessuna voce da completare per scelta dell'utente"


class TestVoceFatture:
    """1b — il falso verde delle fatture vecchie caricate di recente."""

    def test_land_dei_sapori_il_caso_reale(self, no_toggle):
        """3.344 righe caricate negli ultimi 30gg, 0 EUR di competenza agosto.
        Col criterio vecchio faceva 75; ora 25, come la voce rossa del PV."""
        row = _row(n_fatture=3344, n_needs=38, netto=511081.0, personale=0.0)
        out = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese={RID: 0.0})
        # (0 fatture + 100 fatturato + 0 personale + 99 classificate) / 4 = 50.
        # Col criterio vecchio era 75: la voce "fatture" valeva 100 per via delle
        # 3.344 righe caricate, mentre nel PV era gia' rossa.
        assert out[RID] == 50
        vecchio = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese=None)
        assert vecchio[RID] == 75, "il falso verde che il fix elimina"

    def test_offside_sana_non_si_muove(self, no_toggle):
        """Contro-prova: la sede con costi veri nel mese resta dov'era."""
        row = _row(n_fatture=221, n_needs=7, netto=0.0, personale=0.0)
        out = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese={RID: 13892.53})
        assert out[RID] == 49

    def test_senza_costi_si_ripiega_sulle_righe(self, no_toggle):
        """costi_mese=None = "non lo so" (RPC non disponibile): si usa il criterio
        vecchio, come fa il PV. Non e' un verde inventato, e' un ripiego dichiarato."""
        row = _row(n_fatture=3344, n_needs=38, netto=511081.0, personale=0.0)
        out = gruppo._salute_indici_batch(None, [RID], rows=[row], costi_mese=None)
        assert out[RID] == 75, "ripiego: senza il dato costi vale il caricamento recente"


class TestCompletezzaStessoCriterio:
    """La riga "Mancano le fatture costo" vive nella STESSA card dell'indice:
    se usasse un criterio diverso, la card direbbe due cose incompatibili."""

    def test_le_fatture_costo_mancano_se_mancano_gli_euro(self):
        row = _row(n_fatture=3344, n_needs=38, netto=511081.0, personale=100.0)
        comp = gruppo._completezza_dati_pv(None, [RID], rows=[row], costi_mese={RID: 0.0})
        assert comp[RID] == ["le fatture costo"], (
            "3.344 righe caricate ma 0 EUR nel mese: manca, come dice il PV"
        )

    def test_con_gli_euro_e_completo(self):
        row = _row(n_fatture=221, n_needs=7, netto=1000.0, personale=100.0)
        comp = gruppo._completezza_dati_pv(None, [RID], rows=[row], costi_mese={RID: 13892.53})
        assert RID not in comp

    def test_senza_costi_si_ripiega_sulle_righe(self):
        row = _row(n_fatture=3344, n_needs=38, netto=511081.0, personale=100.0)
        comp = gruppo._completezza_dati_pv(None, [RID], rows=[row], costi_mese=None)
        assert RID not in comp, "ripiego sul criterio vecchio quando il dato manca"


class TestCostiMesePerSede:
    """L'helper che estrae gli EURO del mese dalla struttura dei costi di gruppo."""

    def test_somma_food_e_spese_del_mese_richiesto(self):
        costi = {RID: ({8: 13677.05, 7: 999.0}, {8: 215.48})}
        out = gruppo._costi_mese_per_sede("u1", [RID], 2026, 8, costi_auto=costi)
        assert out == {RID: pytest.approx(13892.53)}

    def test_mese_senza_costi_vale_zero(self):
        costi = {RID: ({7: 999.0}, {})}
        out = gruppo._costi_mese_per_sede("u1", [RID], 2026, 8, costi_auto=costi)
        assert out == {RID: 0.0}

    def test_senza_user_id_dice_non_lo_so(self):
        """None != {}: il chiamante deve poter distinguere "non lo so" da
        "nessun costo", o reintroduce il falso rosso."""
        assert gruppo._costi_mese_per_sede(None, [RID], 2026, 8) is None

    def test_a_gennaio_il_fallback_interroga_l_anno_precedente(self, monkeypatch):
        """Bordo che si manifesterebbe solo a gennaio: il mese chiuso e' dicembre
        dell'anno PRIMA, mentre `costi_auto_gruppo` in gruppo_overview e' dell'anno
        corrente. Il chiamante passa costi_auto=None in quel caso, e l'helper deve
        ricalcolare sull'anno giusto — altrimenti leggerebbe dicembre da una
        struttura che non lo contiene e ogni sede risulterebbe senza costi."""
        chiamate = []

        def _fake(user_id, ids, anno):
            chiamate.append(anno)
            return {RID: ({12: 500.0}, {12: 100.0})}

        import services.margine_service as ms
        monkeypatch.setattr(ms, "calcola_costi_automatici_gruppo_sql", _fake)
        # Anno DELIBERATAMENTE lontano da quello corrente: con 2026 un mutante che
        # usasse datetime.now().year sopravviverebbe (misurato, e' successo).
        out = gruppo._costi_mese_per_sede("u1", [RID], 2019, 12, costi_auto=None)
        assert chiamate == [2019], "deve chiedere l'anno del mese chiuso, non quello corrente"
        assert out == {RID: 600.0}
