"""L'AI muta non deve piu' passare per successo (cert. "Costi comuni di gruppo" 24/08).

STORICO: su Railway WORKER_BASE_URL e' settata anche nel processo queue-worker, quindi
classifica_via_worker_con_confidenza faceva una POST HTTP del worker verso se stesso,
falliva, e classifica_con_ai degradava in silenzio al fallback deterministico. La lista
restituita aveva forma e lunghezza corrette, quindi:
  - il chiamante non poteva distinguerla da una risposta riuscita;
  - la condizione di uscita dal retry (len(categorie) == len(chunk)) era soddisfatta
    al primo giro e i 3 tentativi con backoff non scattavano mai;
  - il log diceva "auto-classificazione completata".
Risultato: 795 righe atterrate con ZERO chiamate in ai_usage_events e 93 rimaste
"Da Classificare" per un mese senza che nessuno se ne accorgesse.
"""
import inspect

import pytest

from services import ai_service
from worker import queue_processor as qp


def test_flag_degrado_si_alza_se_ai_non_risponde(monkeypatch):
    """Se la chiamata GPT esplode, classifica_con_ai risponde comunque ma segnala."""
    ai_service.reset_ai_degradata()
    assert ai_service.ai_degradata() is False

    monkeypatch.setattr(
        ai_service, "_get_openai_client",
        lambda *a, **k: (_ for _ in ()).throw(ValueError("API Key OpenAI mancante")),
    )
    cats, confs = ai_service.classifica_con_ai(
        ["MOZZARELLA FIORDILATTE KG 1"], return_confidenze=True,
    )
    # Il best-effort deterministico resta (non si rompe il salvataggio)...
    assert len(cats) == 1 and len(confs) == 1
    # ...ma ora il degrado e' leggibile dal chiamante.
    assert ai_service.ai_degradata() is True


def test_flag_si_azzera_a_ogni_chiamata(monkeypatch):
    """Un degrado precedente non deve far scartare una risposta valida successiva."""
    ai_service._ai_ctx_degradata.set(True)
    monkeypatch.setattr(ai_service, "_chiama_gpt_classificazione",
                        lambda *a, **k: (["LATTICINI"], ["alta"]))
    ai_service.classifica_con_ai(["MOZZARELLA"], return_confidenze=True)
    assert ai_service.ai_degradata() is False


def test_retry_non_esce_piu_al_primo_giro_se_ai_muta():
    """La condizione di uscita dal retry deve considerare anche il degrado."""
    src = inspect.getsource(qp._auto_classify_saved_rows)
    assert "ai_degradata()" in src, "il retry ignora il degrado AI"
    assert "and not _ai_muta" in src, (
        "uscita dal retry basata solo sulla lunghezza della lista: "
        "una AI muta verrebbe di nuovo scambiata per successo"
    )


def test_queue_worker_forza_il_path_locale():
    """Senza force_local_worker_path il worker chiama se stesso via HTTP."""
    src = inspect.getsource(qp)
    assert "force_local_worker_path(True)" in src, (
        "manca force_local_worker_path: con WORKER_BASE_URL settata il queue-worker "
        "fa una POST verso se stesso e l'AI non viene mai interrogata"
    )
    assert "set_ai_context(" in src, (
        "manca set_ai_context: senza, ai_usage_events resta vuoto e il problema "
        "diventa invisibile"
    )


def test_auto_classify_riporta_le_righe_senza_risposta_ai():
    """La funzione deve dire QUANTE righe sono state classificate senza AI."""
    src = inspect.getsource(qp._auto_classify_saved_rows)
    assert "return updated_rows, chunk_ai_muta" in src, (
        "il chiamante non puo' sapere che la classificazione e' degradata"
    )


@pytest.mark.parametrize("descrizione,attesa", [
    ("AMMINISTRAZIONE DEL PERSONALE CEDOLINI ELABORATI - APRILE", "SERVIZI E CONSULENZE"),
    ("AMMINISTRAZIONE DEL PERSONALE CEDOLINI ELABORATI - 14 MENSILIT", "SERVIZI E CONSULENZE"),
    ("BENZINA // CARBURANTE AUTOTRAZIONE", "UTENZE E LOCALI"),
    ("PRIME BUSINESS ANNUAL MEMBERSHIP FEE - BASIC", "SERVIZI E CONSULENZE"),
    ("RIADDEBITO TASSA DI PROPRIETA'", "SERVIZI E CONSULENZE"),
    # Falso positivo da evitare: e' un prodotto per il veicolo, non carburante.
    ("ADDITIVO PROTETTIVO BENZINA", "MANUTENZIONE E ATTREZZATURE"),
])
def test_costi_di_struttura_riconosciuti_dal_dizionario(descrizione, attesa):
    """Righe di sede tecnica che prima nessuna regola copriva."""
    dz = ai_service.applica_correzioni_dizionario(descrizione, "Da Classificare")
    rf, _ = ai_service.applica_regole_categoria_forti(descrizione, dz)
    assert (rf or dz) == attesa


def test_riaddebito_non_e_piu_keyword_morta():
    """Il boundary destro dei pattern rendeva 'RIADDEB' incapace di matchare la
    parola estesa: la keyword esisteva ma non ha mai funzionato."""
    assert ai_service.applica_correzioni_dizionario(
        "RIADDEBITO TASSA DI PROPRIETA'", "Da Classificare",
    ) == "SERVIZI E CONSULENZE"


def test_mesi_collassano_sulla_stessa_chiave_di_memoria():
    """Una correzione manuale su un mese deve valere per tutti gli altri undici."""
    from utils.text_utils import normalizza_descrizione as n
    base = "AMMINISTRAZIONE DEL PERSONALE CEDOLINI ELABORATI - {}"
    chiavi = {n(base.format(m)) for m in
              ("GENNAIO", "APRILE", "DICEMBRE", "14 MENSILIT")}
    assert len(chiavi) == 1, f"mesi non collassati: {chiavi}"


def test_normalizzazione_mesi_non_rompe_i_prodotti_food():
    """Il resto della descrizione deve restare intatto e categorizzabile."""
    from utils.text_utils import normalizza_descrizione as n
    assert "BIRRA" in n("PER CONSUMO FUSTI BIRRA MORETTI MESE APRILE")
    assert ai_service.applica_correzioni_dizionario(
        "PER CONSUMO FUSTI BIRRA MORETTI MESE APRILE", "Da Classificare",
    ) == "BIRRE"


def test_servizi_e_consulenze_e_confermabile_dal_runtime():
    """Era hard-coded come 'mai confermabile': ogni riga di consulenza poteva essere
    scritta solo con GPT 'alta', e un 'media' finiva Da Classificare."""
    assert qp._categoria_deterministica_runtime("CONSULENZA FISCALE") == "SERVIZI E CONSULENZE"
    assert qp._runtime_conferma_categoria("CONSULENZA FISCALE", "SERVIZI E CONSULENZE") is True


def test_da_classificare_resta_non_confermabile():
    """L'unico valore che il runtime non deve mai confermare (regola di dominio #1)."""
    assert qp._categoria_deterministica_runtime("XKCD9931 ZZZ") is None
    assert qp._runtime_conferma_categoria("QUALSIASI", "Da Classificare") is False


def test_tutti_i_return_di_auto_classify_sono_tuple():
    """Gli early-return ("nessuna riga da classificare") devono rispettare il
    contratto della tupla: un `return 0` nudo farebbe esplodere l'unpacking nel
    chiamante proprio nel caso piu' comune, quello in cui non c'e' nulla da fare."""
    import ast
    src = inspect.getsource(qp._auto_classify_saved_rows)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and node.value is not None:
            assert isinstance(node.value, ast.Tuple), (
                f"return non-tupla alla riga {node.lineno} di _auto_classify_saved_rows"
            )
