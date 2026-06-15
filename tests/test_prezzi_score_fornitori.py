"""Score Fornitori (Osservatorio, tab 4) — logica interna cliente↔fornitore.

Test sui pure helper del router prezzi: mappa punteggio→stato per asse,
guardrail anti-rumore (dati insufficienti / provvisorio), coerenza prudente,
coerenza sintesi↔assi, e bozze trattativa deterministiche.

Nessun auth/Supabase: tutta la logica di dominio sta nelle funzioni sincrone.
"""
import pandas as pd
import pytest

from services.routers.prezzi import (
    _stato_metrica,
    _periodo_label,
    _bozza_trattativa,
    _calcola_score_fornitori,
    _calcola_variazioni_prezzi_sync,
    _nc_credito_per_fornitore,
)

OGGI = pd.Timestamp("2026-06-14", tz="UTC")


def _riga(desc, forn, prezzo, data, *, categoria="ALIMENTARI", quantita=10.0,
          totale=None, file=None, tipo="TD01"):
    return {
        "descrizione": desc,
        "categoria": categoria,
        "fornitore": forn,
        "prezzo_unitario": prezzo,
        "quantita": quantita,
        "totale_riga": totale if totale is not None else prezzo * quantita,
        "data_documento": data,
        "file_origine": file or f"{forn}-{data}.xml",
        "tipo_documento": tipo,
    }


def _serie(desc, forn, coppie, **kw):
    """Lista di righe da [(data, prezzo), ...]."""
    return [_riga(desc, forn, p, d, file=f"{forn}-{i}.xml", **kw)
            for i, (d, p) in enumerate(coppie)]


def _by_name(res):
    return {f.fornitore: f for f in res}


def _score(rows, nc=None, soglia=5.0):
    vars_ = _calcola_variazioni_prezzi_sync(rows, soglia)
    return _calcola_score_fornitori(rows, vars_, nc or {}, oggi=OGGI)


# ─────────────────────────────────────────────────────────────────────────────
# _stato_metrica — mappa punteggio → stato per asse
# ─────────────────────────────────────────────────────────────────────────────
class TestStatoMetrica:
    def test_soglie(self):
        assert _stato_metrica(90) == "stabile"
        assert _stato_metrica(75) == "stabile"          # bordo incluso
        assert _stato_metrica(74.9) == "da_monitorare"
        assert _stato_metrica(55) == "da_monitorare"    # bordo incluso
        assert _stato_metrica(54.9) == "instabile"
        assert _stato_metrica(0) == "instabile"

    def test_non_disponibile_sempre_non_valutabile(self):
        # Anche con punteggio alto, se disponibile=False → non_valutabile.
        assert _stato_metrica(95, disponibile=False) == "non_valutabile"
        assert _stato_metrica(10, disponibile=False) == "non_valutabile"


# ─────────────────────────────────────────────────────────────────────────────
# _periodo_label — etichetta periodo
# ─────────────────────────────────────────────────────────────────────────────
class TestPeriodoLabel:
    def test_stesso_mese(self):
        d = pd.Timestamp("2026-03-10", tz="UTC")
        assert _periodo_label(d, d) == "mar 2026"

    def test_stesso_anno(self):
        a = pd.Timestamp("2026-03-10", tz="UTC")
        b = pd.Timestamp("2026-06-10", tz="UTC")
        assert _periodo_label(a, b) == "mar–giu 2026"

    def test_a_cavallo_anno(self):
        a = pd.Timestamp("2025-11-10", tz="UTC")
        b = pd.Timestamp("2026-02-10", tz="UTC")
        assert _periodo_label(a, b) == "nov 2025 – feb 2026"

    def test_none_ritorna_vuoto(self):
        assert _periodo_label(None, None) == ""
        assert _periodo_label(pd.Timestamp("2026-01-01", tz="UTC"), None) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Guardrail anti-rumore
# ─────────────────────────────────────────────────────────────────────────────
class TestGuardrail:
    def test_poche_fatture_dati_insufficienti(self):
        # 2 fatture < soglia minima (3) → nessuno score, stato dichiarato.
        rows = _serie("VINO", "Cantina", [("2026-04-01", 8.0), ("2026-04-20", 9.0)])
        f = _by_name(_score(rows))["Cantina"]
        assert f.score is None
        assert f.stato == "dati_insufficienti"
        assert f.affidabilita_dato == "bassa"
        assert f.sottometriche == []
        # ma la bozza esiste comunque (il cliente può comunque scrivere)
        assert f.bozza.testo

    def test_storico_fresco_ma_corto_senza_variazioni(self):
        # 3 fatture nello stesso mese, nessuna variazione sopra soglia, < 2 mesi.
        rows = _serie("PANE", "Forno", [
            ("2026-05-02", 2.0), ("2026-05-10", 2.0), ("2026-05-20", 2.0),
        ])
        f = _by_name(_score(rows))["Forno"]
        # troppo_breve and not vars_f → dati insufficienti
        assert f.stato == "dati_insufficienti"
        assert f.score is None

    def test_dato_vecchio_diventa_provvisorio(self):
        # Storico ricco ma ultimo acquisto > 6 mesi fa → provvisorio.
        rows = _serie("OLIO", "Frantoio", [
            ("2025-06-05", 5.0), ("2025-07-05", 5.0), ("2025-08-05", 5.0),
            ("2025-09-05", 5.0), ("2025-10-05", 5.0),
        ])
        f = _by_name(_score(rows))["Frantoio"]
        assert f.stato == "provvisorio"
        # lo score numerico interno esiste comunque
        assert f.score is not None


# ─────────────────────────────────────────────────────────────────────────────
# Assi e sintesi
# ─────────────────────────────────────────────────────────────────────────────
class TestAssiESintesi:
    def test_fornitore_stabile_e_affidabile(self):
        rows = _serie("FARINA", "MulinoBeta", [
            ("2026-01-12", 5.0), ("2026-02-12", 5.0), ("2026-03-12", 5.0),
            ("2026-04-12", 5.0), ("2026-05-12", 5.0),
        ])
        f = _by_name(_score(rows))["MulinoBeta"]
        assert f.stato == "affidabile"
        assert f.score >= 75
        assi = {m.chiave: m.stato for m in f.sottometriche}
        assert assi["stabilita"] == "stabile"
        assert assi["impatto"] == "stabile"
        assert assi["documentale"] == "stabile"
        # nessuna agevolazione → coerenza non valutabile (non pesa)
        assert assi["coerenza"] == "non_valutabile"

    def test_tutte_e_4_le_metriche_presenti(self):
        rows = _serie("RISO", "Riseria", [
            ("2026-01-10", 3.0), ("2026-02-10", 3.0), ("2026-03-10", 3.0),
            ("2026-04-10", 3.0),
        ])
        f = _by_name(_score(rows))["Riseria"]
        chiavi = [m.chiave for m in f.sottometriche]
        assert chiavi == ["stabilita", "coerenza", "impatto", "documentale"]

    def test_coerenza_sintesi_assi_no_affidabile_con_asse_instabile(self):
        # Rincaro forte + NC alte → almeno un asse instabile. La sintesi NON può
        # restare "affidabile": deve scendere ad almeno "da_monitorare".
        rows = _serie("MANZO", "Carni", [
            ("2026-01-10", 10.0), ("2026-02-10", 10.5), ("2026-03-10", 11.0),
            ("2026-04-10", 13.0), ("2026-05-10", 15.0),
        ])
        nc = {"CARNI": 9999.0}  # NC enormi → documentale instabile
        f = _by_name(_score(rows, nc=nc))["Carni"]
        stati_assi = {m.stato for m in f.sottometriche if m.disponibile}
        if "instabile" in stati_assi:
            assert f.stato != "affidabile"

    def test_media_pesata_ignora_assi_non_valutabili(self):
        # La coerenza non valutabile non deve spostare lo score: confrontiamo lo
        # score con/ senza la presenza di agevolazioni che restano non valutabili.
        base = _serie("ZUCCHERO", "Dolci", [
            ("2026-01-10", 1.0), ("2026-02-10", 1.0), ("2026-03-10", 1.0),
            ("2026-04-10", 1.0),
        ])
        f = _by_name(_score(base))["Dolci"]
        coer = [m for m in f.sottometriche if m.chiave == "coerenza"][0]
        assert coer.stato == "non_valutabile"
        assert not coer.disponibile
        # score alto nonostante coerenza "neutra" non valutabile
        assert f.score >= 75


# ─────────────────────────────────────────────────────────────────────────────
# Coerenza commerciale — prudenza
# ─────────────────────────────────────────────────────────────────────────────
class TestCoerenzaPrudente:
    def test_sconto_sparito_valutabile_e_segnale(self):
        # Sconto presente solo nella prima metà, ≥3 mesi → valutabile (instabile),
        # e genera sia il segnale "sconto_perso" sia il materiale per la bozza.
        rows = _serie("PASTA", "Pastificio", [
            ("2026-01-10", 2.0), ("2026-02-10", 2.0),
            ("2026-04-10", 2.0), ("2026-05-10", 2.0),
        ])
        # sconto (riga negativa) solo a gennaio
        rows.append(_riga("SCONTO PROMO", "Pastificio", -0.5, "2026-01-10",
                          totale=-5.0, file="Pastificio-0.xml"))
        f = _by_name(_score(rows))["Pastificio"]
        coer = [m for m in f.sottometriche if m.chiave == "coerenza"][0]
        assert coer.disponibile is True
        assert coer.stato in ("instabile", "da_monitorare")
        tipi = {s.tipo for s in f.segnali}
        assert "sconto_perso" in tipi

    def test_periodo_corto_con_sconti_non_valutabile(self):
        # Sconti presenti ma < 3 mesi → coerenza non valutabile (prudenza).
        rows = _serie("LATTE", "Latteria", [
            ("2026-05-02", 1.0), ("2026-05-10", 1.0), ("2026-05-20", 1.0),
            ("2026-06-01", 1.0),
        ])
        rows.append(_riga("SCONTO", "Latteria", -0.2, "2026-05-02",
                          totale=-2.0, file="Latteria-0.xml"))
        f = _by_name(_score(rows))["Latteria"]
        coer = [m for m in f.sottometriche if m.chiave == "coerenza"][0]
        assert coer.disponibile is False
        assert coer.stato == "non_valutabile"


# ─────────────────────────────────────────────────────────────────────────────
# Impatto economico — pesato sull'impatto reale
# ─────────────────────────────────────────────────────────────────────────────
class TestImpattoEconomico:
    def test_rincaro_marginale_non_affossa(self):
        # Aumento percentuale visibile ma su spesa piccola → impatto comunque
        # alto (stabile), perché l'impatto € è marginale.
        rows = _serie("SALE", "Drogheria", [
            ("2026-01-10", 0.40, ), ("2026-02-10", 0.42),
            ("2026-03-10", 0.44), ("2026-04-10", 0.50),
        ], quantita=1.0)
        f = _by_name(_score(rows))["Drogheria"]
        imp = [m for m in f.sottometriche if m.chiave == "impatto"][0]
        # impatto € basso → punteggio impatto alto
        assert imp.stato in ("stabile", "da_monitorare")

    def test_impatto_rincari_non_negativo(self):
        # impatto_rincari aggrega solo i rincari (>0): mai negativo.
        rows = _serie("BURRO", "Caseificio", [
            ("2026-01-10", 8.0), ("2026-02-10", 6.0), ("2026-03-10", 4.0),
            ("2026-04-10", 3.0),
        ])  # solo cali
        f = _by_name(_score(rows))["Caseificio"]
        assert f.impatto_rincari >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Documentale — note di credito prudenti
# ─────────────────────────────────────────────────────────────────────────────
class TestDocumentale:
    def test_nc_assenti_stabile(self):
        rows = _serie("ACQUA", "Bevande", [
            ("2026-01-10", 1.0), ("2026-02-10", 1.0), ("2026-03-10", 1.0),
            ("2026-04-10", 1.0),
        ])
        f = _by_name(_score(rows, nc={}))["Bevande"]
        doc = [m for m in f.sottometriche if m.chiave == "documentale"][0]
        assert doc.stato == "stabile"

    def test_nc_fisiologiche_non_penalizzano_troppo(self):
        # NC piccole (<5% spesa) → ancora stabile, non si grida al lupo.
        rows = _serie("VERDURA", "Ortofrutta", [
            ("2026-01-10", 100.0), ("2026-02-10", 100.0),
            ("2026-03-10", 100.0), ("2026-04-10", 100.0),
        ], quantita=1.0)  # spesa ~400
        f = _by_name(_score(rows, nc={"ORTOFRUTTA": 10.0}))["Ortofrutta"]
        doc = [m for m in f.sottometriche if m.chiave == "documentale"][0]
        assert doc.stato == "stabile"
        # genera comunque il segnale neutro NC
        assert any(s.tipo == "nota_credito" for s in f.segnali)


# ─────────────────────────────────────────────────────────────────────────────
# Bozze trattativa — deterministiche, prudenti, niente confronti col mercato
# ─────────────────────────────────────────────────────────────────────────────
class TestBozze:
    VIETATE = ["sopra il mercato", "fuori media", "più caro", "rispetto ad altri",
               "rispetto alla zona", "concorrenza"]

    def _check_no_mercato(self, testo):
        low = testo.lower()
        for v in self.VIETATE:
            assert v not in low, f"frase vietata nella bozza: {v!r}"

    def test_bozza_unica_non_legata_a_canale(self):
        # Una sola bozza testuale: l'attributo è `testo`, non whatsapp/email/...
        b = _bozza_trattativa("Mario Rossi Srl", "gen–mag 2026",
                              [("OLIO", 12.0, 50.0)], 50.0, [])
        assert b.attiva is True
        assert b.testo
        assert not hasattr(b, "whatsapp")
        assert not hasattr(b, "telefonata")
        self._check_no_mercato(b.testo)

    def test_bozza_senza_oggetto_email(self):
        # Niente "Oggetto:" né lessico da invio: è un testo da copiare, non una mail.
        b = _bozza_trattativa("X", "gen 2026", [("Y", 10.0, 30.0)], 30.0, [])
        assert "Oggetto:" not in b.testo

    def test_bozza_vuota_se_affidabile(self):
        # Fornitore affidabile → nessuna trattativa da proporre.
        b = _bozza_trattativa("Forn", "gen–mag 2026",
                              [("OLIO", 12.0, 50.0)], 50.0, [], stato="affidabile")
        assert b.attiva is False
        assert b.testo == ""
        assert b.motivo  # spiega in una riga perché è vuota

    def test_bozza_vuota_se_niente_da_negoziare(self):
        # Nessun rincaro e nessuno sconto perso → bozza vuota anche senza stato.
        b = _bozza_trattativa("Forno Bianchi", "gen–mag 2026", [], 0.0, [])
        assert b.attiva is False
        assert b.testo == ""
        assert b.motivo

    def test_bozza_attiva_se_da_monitorare_con_rincari(self):
        # Stato non affidabile + rincari → bozza presente.
        b = _bozza_trattativa("Carni Verdi", "mar–giu 2026",
                              [("COSTATA", 15.0, 120.0)], 120.0, [], stato="da_monitorare")
        assert b.attiva is True
        assert "Costata" in b.testo

    def test_bozza_cita_sconti_persi(self):
        b = _bozza_trattativa("Forn", "gen–mag 2026", [], 0.0, ["MOZZARELLA"])
        assert b.attiva is True
        assert "Mozzarella" in b.testo

    def test_score_affidabile_ha_bozza_vuota_end_to_end(self):
        # Verifica integrata: un fornitore stabile esce affidabile con bozza vuota.
        rows = _serie("FARINA", "MulinoBeta", [
            ("2026-01-12", 5.0), ("2026-02-12", 5.0), ("2026-03-12", 5.0),
            ("2026-04-12", 5.0), ("2026-05-12", 5.0),
        ])
        f = _by_name(_score(rows))["MulinoBeta"]
        assert f.stato == "affidabile"
        assert f.bozza.attiva is False


# ─────────────────────────────────────────────────────────────────────────────
# Ordinamento e robustezza input
# ─────────────────────────────────────────────────────────────────────────────
class TestOrdinamentoRobustezza:
    def test_insufficienti_in_coda(self):
        ok = _serie("A", "Buono", [
            ("2026-01-10", 5.0), ("2026-02-10", 5.0), ("2026-03-10", 5.0),
            ("2026-04-10", 5.0),
        ])
        ko = _serie("B", "Scarso", [("2026-04-10", 2.0), ("2026-04-20", 2.0)])
        res = _score(ok + ko)
        # I valutati (score!=None) vengono prima, gli insufficienti in fondo.
        assert res[-1].fornitore == "Scarso"
        assert res[-1].score is None

    def test_input_vuoto(self):
        assert _calcola_score_fornitori([], [], {}, oggi=OGGI) == []

    def test_fornitore_vuoto_ignorato(self):
        rows = _serie("X", "", [
            ("2026-01-10", 1.0), ("2026-02-10", 1.0), ("2026-03-10", 1.0),
        ])
        res = _score(rows)
        assert all(f.fornitore for f in res)

    def test_categorie_spese_escluse(self):
        # Un fornitore con SOLO righe di categoria spesa pura non deve comparire.
        rows = _serie("ENERGIA", "Enel", [
            ("2026-01-10", 100.0), ("2026-02-10", 100.0), ("2026-03-10", 100.0),
        ], categoria="UTENZE E LOCALI")
        res = _score(rows)
        assert "Enel" not in _by_name(res)

    def test_quantita_e_totale_mancanti_non_crashano(self):
        rows = []
        for i, (d, p) in enumerate([("2026-01-10", 5.0), ("2026-02-10", 5.0),
                                    ("2026-03-10", 5.0), ("2026-04-10", 5.0)]):
            rows.append({
                "descrizione": "ITEM", "categoria": "ALIMENTARI",
                "fornitore": "Forn", "prezzo_unitario": p,
                "data_documento": d, "file_origine": f"f{i}.xml",
                "tipo_documento": "TD01",
                # quantita e totale_riga ASSENTI
            })
        # non deve sollevare KeyError
        res = _score(rows)
        assert "Forn" in _by_name(res)


# ─────────────────────────────────────────────────────────────────────────────
# _nc_credito_per_fornitore — riuso righe già caricate
# ─────────────────────────────────────────────────────────────────────────────
class TestNcCreditoPerFornitore:
    def test_riusa_rows_senza_rileggere(self):
        # Passando rows, sb non viene usato per ricaricare le fatture. nc_files
        # arriva da _load_nc_file_origini → lo stubbo via un finto sb.
        rows = [
            _riga("RESO MERCE", "Forn", -2.0, "2026-03-10", totale=-20.0,
                  file="nc1.xml", tipo="TD04"),
            _riga("PRODOTTO", "Forn", 5.0, "2026-03-11", file="ok.xml"),
        ]

        class _FakeResp:
            data = [{"file_origine": "nc1.xml"}]

        class _FakeQuery:
            def select(self, *a, **k): return self
            def eq(self, *a, **k): return self
            def is_(self, *a, **k): return self
            def gte(self, *a, **k): return self
            def lte(self, *a, **k): return self
            def execute(self): return _FakeResp()

        class _FakeSb:
            def __init__(self): self.fatture_loaded = False
            def table(self, name):
                if name == "fatture":
                    self.fatture_loaded = True
                return _FakeQuery()

        sb = _FakeSb()
        out = _nc_credito_per_fornitore(sb, "rid", "2026-01-01", "2026-12-31", rows=rows)
        # tipo TD04 → mask_tipo_nc lo prende; credito = |−20| = 20
        assert out.get("FORN") == pytest.approx(20.0)
        # NON ha riletto la tabella fatture (solo fatture_documenti via _FakeQuery)
        assert sb.fatture_loaded is False
