"""Test guardia: l'aggregazione per sede della catena deve dare gli STESSI numeri
della pagina Margini del PV.

Nasce da 3 bug reali trovati in audit (16/7) dopo il fix "MOL coerente tra viste":
1. RICAVI: la Sintesi leggeva margini_mensili.fatturato_netto (snapshot) mentre il
   PV applica gli override di ricavi_modalita_mensile → su TIME CAFE giugno 2026 lo
   snapshot diceva 3.227€ contro 73.322€ reali (70k di divergenza). Il fix sui costi
   aveva allineato metà formula lasciando l'altra metà rotta.
2. MESI SENZA RIGA: la Sintesi iterava solo le righe margini_mensili esistenti, il PV
   itera i mesi di CALENDARIO (`margini_map.get((y,m), {})`). Una sede con fatture ma
   senza riga del mese (nessun ricavo ancora inserito) aveva i costi caricati dalla
   RPC e poi buttati via dal loop → PV mostrava MOL -3000, Sintesi 0.
3. (perf, non coperto qui) la RPC girava sull'anno intero anche con un mese filtrato.

Questi test bloccano il ritorno di 1 e 2, e la divergenza PV↔Sintesi in generale.
"""
from services.routers.gruppo import _aggrega_sedi_mensili


def _mm(rid, mese, **kw):
    """Riga margini_mensili minima; i campi non passati valgono 0/None come da DB."""
    base = {
        "ristorante_id": rid,
        "mese": mese,
        "fatturato_netto": 0,
        "fatturato_iva10": 0,
        "fatturato_iva22": 0,
        "altri_ricavi_noiva": 0,
        "altri_costi_fb": 0,
        "altri_costi_spese": 0,
        "quote_riparto_fb": 0,
        "quote_riparto_spese": 0,
        "costo_dipendenti": 0,
        "costo_personale_extra": 0,
        "coperti": 0,
    }
    base.update(kw)
    return base


class TestMesiSenzaRigaMarginiMensili:
    """Bug 2: i costi di un mese con fatture ma senza riga margini_mensili devono
    entrare comunque nel MOL, come fa la pagina Margini del PV."""

    def test_costi_contati_anche_senza_riga_del_mese(self):
        # Sede con fatture a giugno (mese 6) ma nessuna riga margini_mensili.
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[],                       # nessuna riga: cliente senza ricavi inseriti
            costi_auto={"a": ({6: 3000.0}, {})},
            overrides={},
            mesi=[6],
        )
        # Il PV mostrerebbe MOL -3000: la Sintesi deve dire lo stesso, non 0.
        assert out["a"]["fb"] == 3000.0
        assert out["a"]["mol"] == -3000.0

    def test_mese_con_riga_e_mese_senza_riga_convivono(self):
        # Il netto si calcola dalle componenti IVA come sul PV (1100/1.10 = 1000),
        # non dalla colonna snapshot fatturato_netto.
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[_mm("a", 5, fatturato_iva10=1100.0)],
            costi_auto={"a": ({5: 200.0, 6: 300.0}, {})},
            overrides={},
            mesi=[5, 6],
        )
        # mese 5: 1000 - 200 = 800 ; mese 6 (nessuna riga): 0 - 300 = -300 → 500
        assert out["a"]["fb"] == 500.0
        assert abs(out["a"]["mol"] - 500.0) < 0.01
        assert abs(out["a"]["netto"] - 1000.0) < 0.01


class TestOverrideRicaviMensili:
    """Bug 1: quando il mese è in modalità mensile (ricavi_modalita_mensile),
    i ricavi vengono dall'override, non dallo snapshot fatturato_netto."""

    def test_override_vince_sullo_snapshot(self):
        # Caso TIME CAFE giugno: snapshot fermo a 3227, override reale 80655 lordo.
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[_mm("a", 6, fatturato_netto=3227.27, fatturato_iva10=3550.0)],
            costi_auto={"a": ({}, {})},
            overrides={"a": {6: {"iva10": 80655.0, "iva22": 0.0, "altri": 0.0}}},
            mesi=[6],
        )
        atteso_netto = 80655.0 / 1.10
        assert abs(out["a"]["netto"] - atteso_netto) < 0.01
        assert abs(out["a"]["lordo"] - 80655.0) < 0.01
        # Il MOL segue il netto vero, non lo snapshot.
        assert abs(out["a"]["mol"] - atteso_netto) < 0.01

    def test_override_e_per_sede_non_contagia_le_altre(self):
        # Catena reale: una sede in modalità mensile, l'altra no. L'override della
        # prima non deve toccare i ricavi della seconda.
        out = _aggrega_sedi_mensili(
            ids=["a", "b"],
            righe_mm=[
                _mm("a", 6, fatturato_iva10=1100.0),
                _mm("b", 6, fatturato_iva10=2200.0),
            ],
            costi_auto={},
            overrides={"a": {6: {"iva10": 11000.0, "iva22": 0.0, "altri": 0.0}}},
            mesi=[6],
        )
        assert abs(out["a"]["netto"] - 10000.0) < 0.01   # override
        assert abs(out["b"]["netto"] - 2000.0) < 0.01    # snapshot, intatto

    def test_senza_override_usa_scorporo_dello_snapshot(self):
        # Senza override il netto si calcola come il PV: iva10/1.10 + iva22/1.22 + altri.
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[_mm("a", 3, fatturato_iva10=1100.0, fatturato_iva22=1220.0, altri_ricavi_noiva=50.0)],
            costi_auto={"a": ({}, {})},
            overrides={},
            mesi=[3],
        )
        assert abs(out["a"]["netto"] - (1000.0 + 1000.0 + 50.0)) < 0.01
        assert abs(out["a"]["lordo"] - 2370.0) < 0.01


class TestFormulaMol:
    def test_mol_somma_quote_riparto_e_costi_manuali(self):
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[_mm(
                "a", 7,
                fatturato_iva10=1100.0,          # netto 1000
                altri_costi_fb=50.0,
                altri_costi_spese=20.0,
                quote_riparto_fb=10.0,
                quote_riparto_spese=5.0,
                costo_dipendenti=100.0,
                costo_personale_extra=30.0,
            )],
            costi_auto={"a": ({7: 200.0}, {7: 80.0})},
            overrides={},
            mesi=[7],
        )
        # fb = 200 auto + 50 manuali + 10 quota = 260
        # spese = 80 auto + 20 manuali + 5 quota = 105
        # pers = 130 → mol = 1000 - 260 - 105 - 130 = 505
        assert abs(out["a"]["fb"] - 260.0) < 0.01
        assert abs(out["a"]["spese"] - 105.0) < 0.01
        assert abs(out["a"]["pers"] - 130.0) < 0.01
        assert abs(out["a"]["mol"] - 505.0) < 0.01

    def test_sede_senza_dati_resta_a_zero(self):
        out = _aggrega_sedi_mensili(
            ids=["a", "b"], righe_mm=[], costi_auto={}, overrides={}, mesi=[1, 2],
        )
        for rid in ("a", "b"):
            assert out[rid]["mol"] == 0.0
            assert out[rid]["netto"] == 0.0


class TestPerMese:
    """La sparkline MOL del gruppo e i mesi 'attivi' si appoggiano agli stessi numeri."""

    def test_serie_per_mese_include_mesi_senza_riga(self):
        out = _aggrega_sedi_mensili(
            ids=["a"],
            righe_mm=[_mm("a", 1, fatturato_iva10=1100.0)],
            costi_auto={"a": ({2: 500.0}, {})},
            overrides={},
            mesi=[1, 2],
            per_mese=True,
        )
        assert abs(out["_mol_per_mese"][1] - 1000.0) < 0.01
        # mese 2: solo costi, nessuna riga → -500 (prima spariva del tutto)
        assert abs(out["_mol_per_mese"][2] - (-500.0)) < 0.01
        assert abs(out["_netto_per_mese"][1] - 1000.0) < 0.01
        assert out["_netto_per_mese"].get(2, 0.0) == 0.0
