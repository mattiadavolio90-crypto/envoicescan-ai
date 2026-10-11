"""Fase K (10/10/2026): il nuovo elenco delle categorie, provato dove decide.

Decisioni di Mattia:
  * nasce RAPPRESENTANZA, spesa generale (pranzo con un cliente, pasto fuori);
  * SHOP si chiama RIVENDITA (stesso contenuto, nome che si capisce);
  * SUSHI VARIE non esiste piu': ogni prodotto giapponese sta nella famiglia di
    cio' che e' (alghe in VERDURE, wasabi in SPEZIE E AROMI, tobiko in PESCE...);
  * tutto il sake e' VINI, da bere e da cucina.
Il totale resta 29 (24 F&B + 5 spese generali).

Una categoria vive in molti posti (costanti, dizionario, regole, prompt, memoria,
centri di costo, client). Questi test la seguono nei posti dove DECIDE qualcosa,
eseguendo il codice: un elenco che cita la parola giusta ma non la usa resterebbe
verde su un assert sul testo.
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import services.ai_service as ai_mod
from config.constants import (
    CATEGORIE_ABOLITE,
    CATEGORIE_FOOD_BEVERAGE,
    CATEGORIE_SPESE_GENERALI,
    CENTRI_DI_PRODUZIONE,
    SETTORE_RETAIL,
    TUTTE_LE_CATEGORIE,
)
from config.prompt_ai_potenziato import (
    PROMPT_CLASSIFICAZIONE_AI,
    PROMPT_CLASSIFICAZIONE_RETAIL,
)
from tests.helpers_ts import WEB_SRC, esegui_ts

_FIXTURE = Path(__file__).parent / "fixtures" / "fase_k_prodotti_giapponesi.json"
_CASI = json.loads(_FIXTURE.read_text(encoding="utf-8"))["casi"]


# ── i prodotti giapponesi, sulle descrizioni reali ──────────────────────────

@pytest.mark.parametrize("descrizione,attesa", sorted(_CASI.items()))
def test_ogni_prodotto_va_nella_sua_famiglia(descrizione, attesa):
    """Il nucleo deterministico intero (dizionario + regole forti), come l'ingest.

    Le descrizioni sono quelle delle righe e delle memorie che stavano in SUSHI
    VARIE (65 + le memorie), il sake, il mirin, la salsa unagi e l'olio di sesamo
    trovati a DB il 10/10, piu' i prodotti tipici della mappa di Mattia.
    """
    categoria, _motivo, _conf = ai_mod.decisione_deterministica(descrizione)
    assert categoria == attesa, f"{descrizione!r}: {categoria} invece di {attesa}"


@pytest.mark.parametrize("descrizione", [
    "BICCHIERI SAKE CERAMICA 6PZ",
    "CARAFFA SAKE 300ML",
    "SET SAKE TOKKURI OCHOKO",
    "TAZZINE SAKE 6PZ",
    "SERVIZIO SAKE CERAMICA",
])
def test_gli_oggetti_da_sake_non_sono_vino(descrizione):
    """La regola del sake sta in cima, prima delle stoviglie: senza eccezione un
    servizio da sake finirebbe fra i vini (e nel food cost delle bevande)."""
    categoria, _motivo, _conf = ai_mod.decisione_deterministica(descrizione)
    assert categoria != "VINI", descrizione


@pytest.mark.parametrize("descrizione,non_deve_essere", [
    # le parole devono stare vicine: un grissino con olio e sesamo e' un grissino
    ("GRISSINI ALL'OLIO E SESAMO", "OLIO E CONDIMENTI"),
    ("TARALLI SESAMO E OLIO", "OLIO E CONDIMENTI"),
    ("FOCACCIA OLIO E SESAMO", "OLIO E CONDIMENTI"),
    ("TARALLI OLIO SESAMO", "OLIO E CONDIMENTI"),
    ("PANE OLIO SESAMO", "OLIO E CONDIMENTI"),
    # l'anguilla venduta con la sua salsa e' pesce
    ("ANGUILLA UNAGI CON SALSA", "SALSE E CREME"),
    # "SHOT" non e' "SHOOTS": un bicchierino non e' una conserva
    ("BAMBOO SHOT GLASS", "SCATOLAME E CONSERVE"),
    # la chiave delle foglie di bambu' vuole la taglia: la menta non e' un piatto
    ("FOGLIE FRESCA DI MENTA", "MATERIALE DI CONSUMO"),
    # pesce e carne impanati restano pesce e carne (regola dei composti)
    ("GAMBERI PANKO 1KG", "PASTA E CEREALI"),
    ("POLLO PANKO", "PASTA E CEREALI"),
])
def test_le_regole_nuove_non_prendono_troppo(descrizione, non_deve_essere):
    """Casi trovati dal revisore di K1: regole forti che prendevano troppo, e
    non negoziabili, quindi senza nemmeno passare dalla coda di revisione."""
    categoria, _motivo, _conf = ai_mod.decisione_deterministica(descrizione)
    assert categoria != non_deve_essere, f"{descrizione!r} finisce in {categoria}"


# ── l'elenco ─────────────────────────────────────────────────────────────────

def test_rappresentanza_e_una_spesa_generale():
    assert "RAPPRESENTANZA" in CATEGORIE_SPESE_GENERALI
    assert "RAPPRESENTANZA" not in CATEGORIE_FOOD_BEVERAGE


def test_rivendita_prende_il_posto_di_shop():
    assert "RIVENDITA" in CATEGORIE_FOOD_BEVERAGE
    assert "SHOP" not in TUTTE_LE_CATEGORIE


def test_sushi_varie_non_esiste_piu():
    assert "SUSHI VARIE" in CATEGORIE_ABOLITE
    assert not (CATEGORIE_ABOLITE & set(TUTTE_LE_CATEGORIE))


def test_il_totale_resta_29_senza_doppioni():
    assert len(TUTTE_LE_CATEGORIE) == 29
    assert len(set(TUTTE_LE_CATEGORIE)) == 29


def test_le_copie_derivate_seguono_le_spese_generali():
    """Prezzi e tag escludono le spese generali: RAPPRESENTANZA compresa, o un
    pranzo con un cliente entrerebbe negli avvisi di rincaro e nei tag food."""
    from services import tag_suggestion_service
    from services.routers import prezzi

    assert set(prezzi._CATEGORIE_SPESE_PREZZI) == set(CATEGORIE_SPESE_GENERALI)
    assert set(CATEGORIE_SPESE_GENERALI) <= tag_suggestion_service._CATEGORIE_ESCLUSE


def test_ogni_categoria_fb_sta_in_un_solo_centro_di_costo():
    """Una categoria F&B fuori dai centri sparisce dall'analisi per centro."""
    nei_centri = [c for cats in CENTRI_DI_PRODUZIONE.values() for c in cats]
    assert len(nei_centri) == len(set(nei_centri))
    assert set(nei_centri) == set(CATEGORIE_FOOD_BEVERAGE)
    assert CENTRI_DI_PRODUZIONE["RIVENDITA"] == ["RIVENDITA"]
    assert "SHOP" not in CENTRI_DI_PRODUZIONE


def test_il_worker_usa_gli_stessi_centri_delle_costanti(monkeypatch):
    # Da solo il file non ha la chiave del worker: senza, l'import solleva.
    monkeypatch.setenv("WORKER_DEV_MODE", "1")
    import services.fastapi_worker as fw

    assert fw._CENTRI_DI_PRODUZIONE == CENTRI_DI_PRODUZIONE


def test_ogni_centro_ha_la_sua_icona_e_il_suo_campo_nell_andamento():
    from services.routers import margini

    assert set(margini._ICONE_CENTRI) == set(CENTRI_DI_PRODUZIONE)
    for modello in (margini.AndamentoMese, margini.FatturatoCentriGiornoItem):
        campi = set(modello.model_fields)
        assert "rivendita" in campi and "shop" not in campi, modello.__name__


# ── memoria e risposte AI con i nomi vecchi ─────────────────────────────────

def test_il_vecchio_nome_shop_diventa_rivendita():
    assert ai_mod._normalize_category_name("SHOP") == "RIVENDITA"


def _query(data):
    q = MagicMock()
    for m in ["select", "eq", "neq", "gte", "lte", "is_", "order", "range", "or_", "in_", "limit"]:
        getattr(q, m).return_value = q
    q.execute.return_value = SimpleNamespace(data=data)
    return q


def _carica(tabelle):
    """Carica la cache della memoria da un DB finto: {tabella: righe}."""
    ai_mod.invalida_cache_memoria()
    supabase = MagicMock()
    supabase.table.side_effect = lambda nome: _query(tabelle.get(nome, []))
    return ai_mod.carica_memoria_completa("user-k", supabase_client=supabase), supabase


@pytest.fixture
def cache_pulita():
    ai_mod.invalida_cache_memoria()
    yield
    ai_mod.invalida_cache_memoria()


def test_la_memoria_locale_salta_le_categorie_abolite(cache_pulita):
    cache, _ = _carica({"prodotti_utente": [
        {"descrizione": "YAKI NORI MISURAKI (A) 10X140G ( )", "categoria": "SUSHI VARIE"},
        {"descrizione": "CARAMELLE GOLIA", "categoria": "SHOP"},
    ]})
    locale = cache["prodotti_utente"]["user-k"]
    assert "YAKI NORI MISURAKI (A) 10X140G ( )" not in locale
    assert locale["CARAMELLE GOLIA"] == "RIVENDITA"


def test_la_memoria_globale_salta_le_categorie_abolite(cache_pulita):
    voce = {"confidence": "alta", "verified": True, "consecutive_correct_classifications": 0}
    cache, _ = _carica({"prodotti_master": [
        {**voce, "descrizione": "WAKAME SECCO (MISURAKI)", "categoria": "SUSHI VARIE"},
        {**voce, "descrizione": "GOMME DAYGUM", "categoria": "SHOP"},
    ]})
    assert "WAKAME SECCO (MISURAKI)" not in cache["prodotti_master"]
    assert "WAKAME SECCO (MISURAKI)" not in cache["prodotti_master_hint"]
    assert cache["prodotti_master"]["GOMME DAYGUM"] == "RIVENDITA"


def test_la_memoria_admin_salta_le_categorie_abolite(cache_pulita):
    cache, _ = _carica({"classificazioni_manuali": [
        {"descrizione": "TOBIKO ROSSO", "categoria_corretta": "SUSHI VARIE", "is_dicitura": False},
        {"descrizione": "SPEDIZIONE", "categoria_corretta": None, "is_dicitura": True},
        {"descrizione": "MARS BAR", "categoria_corretta": "SHOP", "is_dicitura": False},
    ]})
    manuali = cache["classificazioni_manuali"]
    assert "TOBIKO ROSSO" not in manuali
    assert manuali["SPEDIZIONE"]["is_dicitura"] is True
    assert manuali["MARS BAR"]["categoria"] == "RIVENDITA"


def test_una_voce_abolita_in_memoria_non_decide_la_riga(cache_pulita):
    """Il punto vero: con la voce saltata decide il dizionario, non la memoria."""
    desc = "YAKI NORI MISURAKI (A) 10X140G ( )"
    _cache, supabase = _carica({"prodotti_utente": [{"descrizione": desc, "categoria": "SUSHI VARIE"}]})
    categoria = ai_mod.categorizza_con_memoria(
        descrizione=desc, prezzo=50.0, quantita=1, user_id="user-k",
        supabase_client=supabase, pending_local_saves=[],
    )
    assert categoria == "VERDURE"


@pytest.mark.parametrize("descrizione,memoria_vecchia,attesa", [
    ("MIZKAN MIRIN 18L Y", "SALSE E CREME", "OLIO E CONDIMENTI"),
    ("OLIO SESAMO 1,8LT", "SPEZIE E AROMI", "OLIO E CONDIMENTI"),
    ("UNAGI SAUCE NIPPON SHOKKEN 6*2KG", "PESCE", "SALSE E CREME"),
    ("SAKE IN SCATOLE MISURAKI", "DISTILLATI", "VINI"),
])
def test_le_regole_della_fase_k_battono_la_memoria_vecchia(cache_pulita, descrizione, memoria_vecchia, attesa):
    """Sul live la memoria dei clienti porta ancora le categorie di prima (sake in
    DISTILLATI, mirin in SALSE...): le regole nuove devono essere non negoziabili,
    o la voce vecchia deciderebbe ogni fattura nuova."""
    _cache, supabase = _carica({"prodotti_utente": [{"descrizione": descrizione, "categoria": memoria_vecchia}]})
    categoria = ai_mod.categorizza_con_memoria(
        descrizione=descrizione, prezzo=40.0, quantita=1, user_id="user-k",
        supabase_client=supabase, pending_local_saves=[],
    )
    assert categoria == attesa


def _risposta_ai(categorie):
    payload = {"risultati": [{"idx": i, "categoria": c, "confidence": "alta"}
                             for i, c in enumerate(categorie)]}
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)),
                                 finish_reason="stop")],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10),
    )
    return client


@pytest.fixture
def _niente_tracking_costi(monkeypatch):
    import services.ai_cost_service as cost

    monkeypatch.setattr(cost, "track_ai_usage", lambda *a, **k: None)


def test_l_ai_che_risponde_shop_viene_rinominata(_niente_tracking_costi):
    """Un nome vecchio e' la stessa categoria: si rinomina, non si butta la risposta.

    La descrizione e' scelta fra quelle che il nucleo deterministico NON riconosce:
    con "CARAMELLE" il recupero deterministico darebbe RIVENDITA anche senza la
    rinomina, e il test resterebbe verde col difetto (mutante sopravvissuto).
    """
    descrizione = "ARTICOLO BANCO 0042"
    assert ai_mod.decisione_deterministica(descrizione)[0] == "Da Classificare"
    risultati = ai_mod._chiama_gpt_classificazione([descrizione], _risposta_ai(["SHOP"]))
    assert risultati == ["RIVENDITA"]


def test_l_ai_che_risponde_sushi_varie_non_passa(_niente_tracking_costi):
    risultati = ai_mod._chiama_gpt_classificazione(["YAKI NORI 10X125G"], _risposta_ai(["SUSHI VARIE"]))
    assert risultati == ["VERDURE"]


def test_per_un_negozio_rivendita_non_e_una_categoria(_niente_tracking_costi):
    """La merce di un negozio e' ARTICOLO DI VENDITA: RIVENDITA e' dei ristoranti."""
    risultati = ai_mod._chiama_gpt_classificazione(
        ["CARAMELLE ASSORTITE"], _risposta_ai(["RIVENDITA"]), settore=SETTORE_RETAIL,
    )
    assert risultati == ["Da Classificare"]


# ── il prompt ────────────────────────────────────────────────────────────────

def _voci_numerate(prompt):
    return [m.group(1).strip() for m in re.finditer(r"^\s*\d+\. \*\*([^*]+)\*\* -", prompt, re.M)]


def test_il_prompt_dei_ristoranti_elenca_esattamente_le_29():
    """In due direzioni: nessuna categoria senza definizione, nessuna voce morta."""
    voci = set(_voci_numerate(PROMPT_CLASSIFICAZIONE_AI))
    assert voci == set(TUTTE_LE_CATEGORIE), (
        f"solo nel prompt: {sorted(voci - set(TUTTE_LE_CATEGORIE))}; "
        f"senza definizione: {sorted(set(TUTTE_LE_CATEGORIE) - voci)}"
    )


@pytest.mark.parametrize("prompt", [PROMPT_CLASSIFICAZIONE_AI, PROMPT_CLASSIFICAZIONE_RETAIL],
                         ids=["ristoranti", "retail"])
def test_nessun_prompt_propone_sushi_varie(prompt):
    assert "SUSHI VARIE" not in prompt


@pytest.mark.parametrize("frase", [
    r"SAKE \(da bere e da cucina\) → VINI",
    r"alghe \(NORI, YAKI NORI, WAKAME, KOMBU\) → VERDURE",
    r"TOBIKO, MASAGO, IKURA, KATSUOBUSHI[^\n]*→ PESCE",
    r"MIRIN, ACETO DI RISO, OLIO DI SESAMO → OLIO E CONDIMENTI",
    r"COPERTO, PASTI COMPLETI, PRANZO o CENA DI LAVORO[^\n]*→ RAPPRESENTANZA",
])
def test_il_prompt_dei_ristoranti_dice_le_decisioni_di_mattia(frase):
    """Il prompt e' l'unica cosa che l'AI legge: la mappa decisa da Mattia deve
    starci scritta, non solo nel dizionario."""
    assert re.search(frase, PROMPT_CLASSIFICAZIONE_AI), frase


def test_il_prompt_retail_vieta_rivendita():
    """RIVENDITA e' la parola che un'AI userebbe per la merce di un negozio, che
    invece e' ARTICOLO DI VENDITA."""
    divieto = next(r for r in PROMPT_CLASSIFICAZIONE_RETAIL.splitlines() if r.startswith("❌ NON usare MAI \"FOOD\""))
    assert '"RIVENDITA"' in divieto


# ── il client ────────────────────────────────────────────────────────────────

def test_il_client_ha_lo_stesso_elenco_del_server():
    tutte = esegui_ts("lib/admin", "emit(m.CATEGORIE_TUTTE);")
    assert set(tutte) == set(TUTTE_LE_CATEGORIE) | {"📝 NOTE E DICITURE"}


def test_ogni_categoria_ha_la_sua_icona_nel_client():
    """Senza voce la riga mostra il segnaposto generico al posto dell'icona."""
    icone = esegui_ts("app/(app)/analisi-fatture/periodi", "emit(Object.keys(m.CATEGORIA_ICONS));")
    mancanti = set(TUTTE_LE_CATEGORIE) - set(icone)
    assert not mancanti, f"categorie senza icona: {sorted(mancanti)}"
    assert not (CATEGORIE_ABOLITE & set(icone))


def test_ogni_centro_ha_il_suo_colore_nel_client():
    """Il grafico dell'analisi avanzata colora per centro: senza chiave la serie
    resta senza colore. CENTRO_COLOR sta in un .tsx, che node non esegue: si legge
    il blocco della costante."""
    testo = (WEB_SRC / "app/(app)/margini/analisi-tab.tsx").read_text(encoding="utf-8")
    blocco = re.search(r"const CENTRO_COLOR[^{]*\{(.*?)\};", testo, re.S)
    assert blocco, "CENTRO_COLOR non trovato in margini/analisi-tab.tsx"
    chiavi = set(re.findall(r"^\s*([A-Z]+):", blocco.group(1), re.M))
    assert chiavi == set(CENTRI_DI_PRODUZIONE)


# ── la rivendita resta fuori dallo spreco per coperto (catena) ───────────────

def test_lo_spreco_di_catena_lascia_fuori_la_rivendita():
    """Le sigarette rivendute non sono materia prima di cucina: fuori dal costo
    per coperto. Col nome vecchio nell'insieme escluso RIVENDITA ci rientrerebbe."""
    from unittest.mock import patch

    from services.routers import gruppo

    sb = MagicMock()
    q = MagicMock()
    for m in ("select", "in_", "eq", "lte", "order", "limit"):
        getattr(q, m).return_value = q
    q.execute.return_value = MagicMock(data=[{"ristorante_id": "a", "anno": 2026, "mese": 6, "coperti": 100}])
    sb.table.return_value = q
    rpc = MagicMock()
    rpc.execute.return_value = MagicMock(data=[
        {"ristorante_id": "a", "anno": 2026, "mese": 6, "categoria": "PESCE", "totale": 500.0},
        {"ristorante_id": "a", "anno": 2026, "mese": 6, "categoria": "RIVENDITA", "totale": 300.0},
    ])
    sb.rpc.return_value = rpc
    fw = MagicMock()
    fw._righe_quote_gruppo.return_value = []

    with patch.object(gruppo, "_resolve_gruppo",
                      return_value=(sb, "u1", [{"id": "a"}], "Gruppo", {"a": "PV a"}, ["a"])), \
         patch.object(gruppo, "_anno_mese_corrente", return_value=(2026, 6)), \
         patch.object(gruppo, "_completezza_dati_pv", return_value={}), \
         patch.object(gruppo, "_costi_mese_per_sede", return_value={"a": 800.0}), \
         patch.object(gruppo, "_fw", return_value=fw):
        resp = gruppo.gruppo_spreco_categorie(mese=6, authorization="Bearer t")

    assert [r.categoria for r in resp.righe] == ["PESCE"]
