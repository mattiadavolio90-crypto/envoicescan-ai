"""Test guardia: il segnale «margine in calo» della catena.

Nasce da Q1 (quadratura 03/09): il segnale NON è mai potuto scattare per nessun
cliente reale. Leggeva due colonne snapshot di `margini_mensili` — il gate
`fatturato_netto > 0` e il valore `mol_perc` — che per le sedi di catena non sono
valorizzate (i costi automatici restano a 0 finché nessuno salva la pagina
Margini della sede; i ricavi in modalità mensile vivono negli override).
Misurato a DB: 0 sedi servite su 2 catene reali.

Il fix calcola il MOL con la formula viva (`_aggrega_sedi_mensili`), la stessa di
gruppo_overview e gruppo_margini_coperti.

Il secondo test è il più importante: ricalcolare il MOL senza un gate di
completezza produce ~100% sui mesi in cui le fatture non sono ancora arrivate
(misurato sui dati veri: LAND 8-9, SUSHILAND 7-9). Un segnale acceso su quei
valori è peggio di un segnale spento.
"""
from unittest.mock import MagicMock, patch

from services.routers import gruppo as G


def _mm(rid, mese, iva10=0.0, fb_manuale=0.0, pers=0.0):
    """Riga margini_mensili come la ritorna il DB (colonne componenti)."""
    return {
        "ristorante_id": rid, "mese": mese,
        "fatturato_iva10": iva10, "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
        "altri_costi_fb": fb_manuale, "altri_costi_spese": 0,
        "quote_riparto_fb": 0, "quote_riparto_spese": 0,
        "costo_dipendenti": pers, "costo_personale_extra": 0,
    }


def _sb(righe_per_anno):
    """sb.table('margini_mensili') ritorna le righe dell'anno filtrato con .eq()."""
    sb = MagicMock()
    stato = {"anno": None}

    tbl = MagicMock()
    tbl.select.return_value = tbl
    tbl.in_.return_value = tbl
    tbl.gte.return_value = tbl
    tbl.lte.return_value = tbl

    def _eq(campo, valore):
        if campo == "anno":
            stato["anno"] = int(valore)
        return tbl
    tbl.eq.side_effect = _eq
    tbl.execute.side_effect = lambda: MagicMock(
        data=righe_per_anno.get(stato["anno"], []), count=0
    )
    sb.table.return_value = tbl

    rpc_res = MagicMock()
    rpc_res.execute.return_value = MagicMock(data=[])
    sb.rpc.return_value = rpc_res
    return sb


def _segnali(righe, costi_auto, overrides=None, ids=("a",)):
    """Esegue _calcola_segnali isolando tutto cio' che non e' il segnale 1.

    `righe` e `costi_auto` sono {anno: ...}; i mesi sono ancorati a oggi (vedi MESI).
    """
    ids = list(ids)
    with patch.object(G, "_completezza_dati_pv", return_value={}), \
         patch.object(G, "_overrides_mese_sede",
                      side_effect=lambda sb, rid, a: (overrides or {}).get(rid, {})), \
         patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
               side_effect=lambda uid, rids, a: costi_auto.get(a, {})):
        out = G._calcola_segnali(
            _sb(righe), ids, {r: f"PV {r}" for r in ids},
            segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra"},
            user_id="u1",
        )
    return [s for s in out if s["tipo"] == "margine_calo"]


# I mesi si ANCORANO a oggi, non si scrivono fissi: il codice guarda solo i mesi
# gia' passati (`range(1, oggi.month + 1)`), quindi mesi 1-4 hardcodati farebbero
# fallire questi test da gennaio a marzo. M1 e' il mese piu' vecchio dei 4 usati.
_OGGI = __import__("datetime").date.today()
ANNO = _OGGI.year if _OGGI.month >= 4 else _OGGI.year - 1
M1, M2, M3, M4 = 1, 2, 3, 4
if _OGGI.year == ANNO:
    M4 = _OGGI.month
    M1, M2, M3 = M4 - 3, M4 - 2, M4 - 1
else:
    # A gen-mar si lavora sull'anno precedente, dove tutti i 12 mesi sono chiusi.
    M1, M2, M3, M4 = 9, 10, 11, 12
MESI = (M1, M2, M3, M4)


class TestSedeInModalitaMensile:
    """Il caso che il segnale non vedeva: ricavi negli override, snapshot a 0."""

    def test_sede_in_modalita_mensile_ora_puo_scattare(self):
        # 4 mesi: i primi 3 al ~30% di margine, il quarto crolla al ~2%.
        # Snapshot fatturato a 0 (come OFFSIDE a DB): i ricavi stanno negli override.
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        seg = _segnali(righe, costi, overrides=ovr)

        assert len(seg) == 1, "il segnale deve scattare: era muto per ogni catena"
        assert seg[0]["ristorante_id"] == "a"
        assert seg[0]["cta_page"] == "/margini"

    def test_il_testo_riporta_i_due_numeri(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        testo = _segnali(righe, costi, overrides=ovr)[0]["testo"]

        assert testo.startswith("Margine al ")
        assert "era" in testo and "% di media" in testo


class TestMesiIncompleti:
    """Il trappolone misurato sui dati veri: senza gate di completezza il MOL
    dei mesi senza fatture esce ~100% e il segnale confronta numeri inventati."""

    def test_mese_senza_costi_non_entra_nel_confronto(self):
        # Mesi 1-3 reali al ~30%; il mese 4 ha ricavi ma NESSUNA fattura ancora
        # arrivata (costi 0) -> MOL 100%. Non deve diventare il "mese corrente".
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in (M1, M2, M3)] + [_mm("a", M4)]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        seg = _segnali(righe, costi, overrides=ovr)

        assert seg == [], "un mese senza costi vale ~100%: non e' confrontabile"

    def test_mese_senza_personale_non_entra_nel_confronto(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in (M1, M2, M3)] + [_mm("a", M4, pers=0.0)]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        seg = _segnali(righe, costi, overrides=ovr)

        assert seg == [], "senza costo del personale il MOL e' gonfiato"

    def test_mese_senza_ricavi_non_entra_nel_confronto(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in (M1, M2, M3)}}

        seg = _segnali(righe, costi, overrides=ovr)

        assert seg == [], "senza ricavi il margine non e' calcolabile"


class TestSoglia:
    """La soglia dei 3 punti resta come e': niente segnale per un calo minimo."""

    def test_calo_sotto_soglia_non_scatta(self):
        # ~30% nei primi tre mesi, ~28,6% nel quarto: 1,4 punti, sotto i 3.
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 6050.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        assert _segnali(righe, costi, overrides=ovr) == []

    def test_margine_stabile_non_scatta(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({m: 5900.0 for m in MESI}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        assert _segnali(righe, costi, overrides=ovr) == []


class TestPerimetro:
    """Il segnale resta disattivabile e non calcola nulla senza user_id."""

    def test_disattivabile_da_config(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        with patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede",
                          side_effect=lambda sb, rid, a: ovr.get(rid, {})), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   side_effect=lambda uid, rids, a: costi.get(a, {})):
            out = G._calcola_segnali(
                _sb(righe), ["a"], {"a": "PV A"},
                segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra",
                             "margine_calo"},
                user_id="u1",
            )
        assert [s for s in out if s["tipo"] == "margine_calo"] == []

    def test_disattivato_non_calcola_nemmeno(self):
        """La guardia `segnali_off` sul blocco non e' ridondante col filtro finale:
        quel filtro toglie i segnali dall'OUTPUT, ma il calcolo (una query + una RPC
        + N override per anno) sarebbe girato lo stesso. Qui si prova che, disattivato
        il segnale, la RPC dei costi non viene proprio chiamata."""
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}
        chiamate = []

        def _costi(uid, rids, anno):
            chiamate.append(anno)
            return {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}

        with patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede",
                          side_effect=lambda sb, rid, a: ovr.get(rid, {})), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   side_effect=_costi):
            G._calcola_segnali(
                _sb(righe), ["a"], {"a": "PV A"},
                segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra",
                             "margine_calo"},
                user_id="u1",
            )

        assert chiamate == [], "segnale disattivato: il calcolo non deve partire"

    def test_senza_user_id_tace(self):
        """I costi live non sono calcolabili: meglio muto che con margini al 100%."""
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi = {ANNO: {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        with patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede",
                          side_effect=lambda sb, rid, a: ovr.get(rid, {})), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   side_effect=lambda uid, rids, a: costi.get(a, {})):
            out = G._calcola_segnali(
                _sb(righe), ["a"], {"a": "PV A"},
                segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra"},
            )
        assert [s for s in out if s["tipo"] == "margine_calo"] == []


class TestFinestraSuDueAnni:
    """La chiave di `per_pv_mesi` porta l'ANNO. Senza, i mesi dell'anno precedente
    verrebbero sovrascritti da quelli dell'anno corrente — e per un cliente la cui
    finestra cavalca il capodanno il segnale si SPEGNEREBBE del tutto, perche' i
    3 mesi di confronto stanno tutti nell'anno vecchio."""

    def test_finestra_a_cavallo_del_capodanno(self):
        """Ultimo mese completo = gennaio; i 3 precedenti = ott/nov/dic dell'anno
        prima. E' l'unico caso in cui i mesi dell'anno vecchio entrano davvero nel
        confronto: con una chiave senza anno (o con `per_pv_mesi` riazzerato a ogni
        anno) qui il segnale sparisce."""
        import datetime as _d

        anno_cur, anno_prec = 2027, 2026

        class _FakeDate(_d.date):
            @classmethod
            def today(cls):
                return cls(anno_cur, 1, 20)

        class _FakeDT(_d.datetime):
            @classmethod
            def now(cls, tz=None):
                return _d.datetime(anno_cur, 1, 20, 12, 0, tzinfo=tz)

        # ott/nov/dic al ~31% di margine, gennaio crolla al ~3%.
        righe = {
            anno_prec: [_mm("a", m, pers=1000.0) for m in (10, 11, 12)],
            anno_cur: [_mm("a", 1, pers=1000.0)],
        }
        costi = {
            anno_prec: {"a": ({10: 5900.0, 11: 5900.0, 12: 5900.0}, {})},
            anno_cur: {"a": ({1: 8700.0}, {})},
        }
        ovr_val = {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0}
        ovr = {"a": {m: ovr_val for m in (1, 10, 11, 12)}}

        with patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede",
                          side_effect=lambda sb, rid, a: ovr.get(rid, {})), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   side_effect=lambda uid, rids, a: costi.get(a, {})), \
             patch.object(_d, "date", _FakeDate), \
             patch.object(_d, "datetime", _FakeDT):
            out = G._calcola_segnali(
                _sb(righe), ["a"], {"a": "PV A"},
                segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra"},
                user_id="u1",
            )

        seg = [x for x in out if x["tipo"] == "margine_calo"]
        assert len(seg) == 1, "i 3 mesi di confronto stanno nell'anno precedente"
        assert "Margine al" in seg[0]["testo"]


class TestResilienzaPerAnno:
    """Un guasto sull'anno PRECEDENTE non deve buttare via i mesi dell'anno
    corrente gia' calcolati: prima un solo try avvolgeva entrambi gli anni."""

    def test_guasto_sull_anno_vecchio_non_spegne_il_segnale(self):
        righe = {ANNO: [_mm("a", m, pers=1000.0) for m in MESI]}
        costi_ok = {"a": ({M1: 5900.0, M2: 5900.0, M3: 5900.0, M4: 8700.0}, {})}
        ovr = {"a": {m: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0} for m in MESI}}

        def _costi(uid, rids, anno):
            if anno != ANNO:
                raise RuntimeError("RPC giu' sull'anno vecchio")
            return costi_ok

        with patch.object(G, "_completezza_dati_pv", return_value={}), \
             patch.object(G, "_overrides_mese_sede",
                          side_effect=lambda sb, rid, a: ovr.get(rid, {})), \
             patch("services.margine_service.calcola_costi_automatici_gruppo_sql",
                   side_effect=_costi):
            out = G._calcola_segnali(
                _sb(righe), ["a"], {"a": "PV A"},
                segnali_off={"dati_mancanti", "ricavi_mancanti", "prezzi_sopra"},
                user_id="u1",
            )

        seg = [x for x in out if x["tipo"] == "margine_calo"]
        assert len(seg) == 1, "l'anno corrente era gia' calcolato: non va buttato"
