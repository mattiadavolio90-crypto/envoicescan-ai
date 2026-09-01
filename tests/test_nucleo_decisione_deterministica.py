"""Fase 1 — un solo motore di decisione (audit categorizzazione 1/9/2026).

Il repo componeva `dizionario + regole forti` in NOVE punti diversi, con tre
semantiche divergenti:

  ordine A (dizionario -> regole)   categorizza_con_memoria L7, admin.py:809/1415
  ordine B (regole -> dizionario)   classifica_con_ai (safety net + 3 fallback)
  in OR, non in pipeline            admin.py:1140
  solo regole forti                 fastapi_worker.py:370 (scriveva a DB!)

Un commento nel sorgente affermava che A e B fossero equivalenti. Non lo erano.

MISURA (tutte le 6.959 descrizioni distinte a DB, 1/9/2026): i due ordini divergono
su TRE righe, e l'ordine A vince su tutte e tre. Sono cibo per gatti:

    CATISFACTION POLLO-GR 60     A: Da Classificare [pet_food_non_alimento]
                                 B: CARNE
    CATISFACTION MANZO-GR 60     idem
    CATISFACTION SALMONE-GR 60   A: Da Classificare / B: PESCE

Con le regole per prime, il dizionario non arriva mai a parlare: la regola
`pet_food_non_alimento` — che esiste apposta — non viene consultata, e il cibo per
gatti entra nel food cost del ristorante. A DB quelle tre righe stanno in
"Da Classificare": e' l'ordine A ad averle prodotte, ed e' quello adottato.

Non e' una scelta fra due semantiche difendibili: una e' misurabilmente migliore.
"""
from __future__ import annotations

import inspect

import pytest

from services.ai_service import decisione_deterministica


class TestOrdineDizionarioPoiRegole:
    """I tre casi che separano i due ordini. Se un domani qualcuno reinvertisse
    l'ordine 'perche' le regole sono piu' precise', questi test lo fermerebbero."""

    @pytest.mark.parametrize("descrizione", [
        "CATISFACTION POLLO-GR 60",
        "CATISFACTION MANZO-GR 60",
        "CATISFACTION SALMONE-GR 60",
    ])
    def test_pet_food_non_entra_nel_food_cost(self, descrizione):
        cat, _motivo, _conf = decisione_deterministica(descrizione)
        assert cat == "Da Classificare", (
            "col pet food classificato come CARNE/PESCE il food cost del ristorante "
            "include cibo per gatti"
        )

    def test_il_motivo_della_regola_e_riportato(self):
        """Il motivo alimenta log e tracciabilita' (Fase 2): non va perso."""
        cat, motivo, _conf = decisione_deterministica("BLACK BURGER 150G")
        assert cat == "CARNE"
        assert motivo


class TestContrattoDelNucleo:
    def test_riga_ignota_resta_in_coda_senza_motivo_ne_confidenza(self):
        cat, motivo, conf = decisione_deterministica("ZZQX 4471 RIF. CONTRATTO")
        assert (cat, motivo, conf) == ("Da Classificare", None, None)

    def test_descrizione_vuota_non_solleva(self):
        assert decisione_deterministica("")[0] == "Da Classificare"

    def test_regola_forte_vale_alta_il_dizionario_vale_media(self):
        """La confidenza distingue ancora le due fonti, perche' il gate a valle la
        usa: una regola forte e' un'affermazione certificata, il dizionario e' un
        match di keyword. Unificare l'ordine non doveva appiattire questo."""
        _c, motivo_regola, conf_regola = decisione_deterministica("BLACK BURGER 150G")
        assert motivo_regola and conf_regola == "alta"

        cat_diz, motivo_diz, conf_diz = decisione_deterministica("PASTA PENNE RIGATE 500G")
        assert cat_diz == "PASTA E CEREALI"
        assert motivo_diz is None and conf_diz == "media"


class TestNessunaPipelineParallelaSopravvissuta:
    """Il valore della Fase 1 non e' il nucleo in se': e' che NESSUNO ricomponga
    piu' la pipeline per conto proprio. Questi test falliscono se una nuova
    ricomposizione rientra dalla finestra."""

    @pytest.mark.parametrize("modulo,funzione", [
        ("services.upload_handler", "_categoria_affidabile"),
        ("worker.queue_processor", "_categoria_deterministica_runtime"),
    ])
    def test_i_gate_passano_dal_nucleo(self, modulo, funzione):
        import importlib

        mod = importlib.import_module(modulo)
        src = inspect.getsource(getattr(mod, funzione))
        assert "applica_correzioni_dizionario" not in src
        assert "applica_regole_categoria_forti" not in src

    def test_classifica_con_ai_non_ricompone_la_pipeline(self):
        from services import ai_service

        src = inspect.getsource(ai_service.classifica_con_ai)
        # L'ordine invertito viveva qui in quattro punti (safety net + 3 fallback
        # d'errore): tutti sostituiti dal nucleo.
        assert 'applica_regole_categoria_forti(desc, "Da Classificare")' not in src
        assert src.count("decisione_deterministica(desc)") >= 4

    def test_admin_non_ha_piu_la_regola_deprecata(self):
        """admin.py:809 escludeva ancora SERVIZI E CONSULENZE — regola deprecata il
        24/08 ovunque tranne li'. Era la divergenza piu' vecchia delle nove."""
        from pathlib import Path

        src = Path("services/routers/admin.py").read_text(encoding="utf-8")
        assert '("Da Classificare", "SERVIZI E CONSULENZE", cat_attuale)' not in src

    def test_il_worker_notturno_consulta_anche_il_dizionario(self):
        """fastapi_worker.py:370 SCRIVE A DB usando le sole regole forti: una riga
        che il dizionario sapeva classificare restava in coda per sempre."""
        from pathlib import Path

        src = Path("services/fastapi_worker.py").read_text(encoding="utf-8")
        assert 'applica_regole_categoria_forti(desc, "Da Classificare")' not in src


class TestNonRegressioneSulCatalogoReale:
    """Le uniche righe che l'unificazione doveva cambiare sono le mozzarelle in
    vaschetta (vedi test_vaschetta_contenitore_o_cibo.py). Campione di controllo
    trasversale: se l'unificazione avesse spostato altro, si vedrebbe qui."""

    @pytest.mark.parametrize("descrizione,attesa", [
        ("SALMONE AFFUMICATO 200G", "PESCE"),
        ("BLACK BURGER 150G", "CARNE"),
        ("ACQUA PANNA 0,75", "ACQUA"),
        ("THE S.BENEDETTO LIM 33 CLX24 LAT SLEEK", "BEVANDE"),
        ("UI2 QI ACQUA POTABILE", "UTENZE E LOCALI"),
        ("CARTA PER RAVIOLI", "MATERIALE DI CONSUMO"),
        ("VASCHETTA SUSHI FIORI C+C 225X100 H50 400PZ", "MATERIALE DI CONSUMO"),
        ("MOZZARELLA FIOR DI LATTE GR 250 VASCHETTA KG 1", "LATTICINI"),
    ])
    def test_categoria_stabile(self, descrizione, attesa):
        assert decisione_deterministica(descrizione)[0] == attesa


class TestPercorsoPdfNonSaltaIlDizionario:
    """D12 — `ottieni_categoria_prodotto` (percorso PDF/Vision) consultava le sole
    memorie e poi restituiva "Da Classificare", buttando via dizionario e regole.
    Il suo docstring dichiarava «allineata con categorizza_con_memoria» allineando
    3 livelli su 8: lo stesso "SALMONE" da XML dava PESCE, da PDF restava in coda.

    Impatto ATTUALE nullo e va detto: a DB tutte e 39.143 le righe provengono da
    XML/P7M, nessuna da PDF. E' un difetto latente — il primo cliente che carica un
    PDF ne prenderebbe l'intero colpo, e il nucleo sa classificare il 78,6% delle
    descrizioni distinte del catalogo.
    """

    @pytest.fixture
    def _senza_memorie(self, monkeypatch):
        """Isola il livello sotto esame: senza memorie caricate, ciò che risponde
        e' esattamente il runtime deterministico aggiunto in fondo."""
        from services import ai_service

        monkeypatch.setattr(ai_service, "_disable_global_memory", True, raising=False)
        monkeypatch.setattr(
            ai_service, "carica_memoria_completa",
            lambda *a, **k: None, raising=False,
        )
        monkeypatch.setattr(
            ai_service, "_memoria_cache",
            {"loaded": True, "_loaded_user_ids": {"u1"}, "classificazioni_manuali": {},
             "prodotti_utente": {}, "prodotti_utente_norm": {}, "prodotti_master": {},
             "prodotti_master_canon": {}},
            raising=False,
        )
        return ai_service

    @pytest.mark.parametrize("descrizione,attesa", [
        ("SALMONE AFFUMICATO 200G", "PESCE"),
        ("PASTA PENNE RIGATE 500G", "PASTA E CEREALI"),
        ("MOZZARELLA FIOR DI LATTE GR 250 VASCHETTA KG 1", "LATTICINI"),
    ])
    def test_riga_nota_al_dizionario_non_resta_in_coda(
        self, _senza_memorie, descrizione, attesa
    ):
        assert _senza_memorie.ottieni_categoria_prodotto(descrizione, "u1") == attesa

    def test_riga_ignota_resta_in_coda(self, _senza_memorie):
        got = _senza_memorie.ottieni_categoria_prodotto("ZZQX 4471 RIF. CONTRATTO", "u1")
        assert got == "Da Classificare"

    def test_xml_e_pdf_danno_la_stessa_risposta(self, _senza_memorie):
        """La prova che il difetto e' chiuso: stessa descrizione, stesso esito."""
        via_pdf = _senza_memorie.ottieni_categoria_prodotto("SALMONE AFFUMICATO 200G", "u1")
        via_xml = decisione_deterministica("SALMONE AFFUMICATO 200G")[0]
        assert via_pdf == via_xml == "PESCE"
