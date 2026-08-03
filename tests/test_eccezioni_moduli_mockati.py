"""Guardia sui rami `except` che dipendono da eccezioni di moduli mockati.

Problema dimostrato nell'audit Test del 3/8/2026: `tests/conftest.py` sostituisce
`openai`, `requests`, `tenacity`... con `MagicMock()`. Un attributo di un
MagicMock NON e' una classe che eredita da BaseException, quindi:

    except (openai.RateLimitError, ...):   ->  TypeError: catching classes that
                                               do not inherit from BaseException

Il ramo di gestione errori non viene MAI eseguito sotto la suite: un test che
copre quel percorso non verifica il retry, verifica un TypeError. E siccome
`RETRIABLE_ERRORS_PARSING` e' una tupla valutata da sinistra a destra, nemmeno
il `ValueError` finale — che e' una classe REALE — viene raggiunto.

Il codice di produzione e' corretto (in produzione `openai` e' la libreria vera):
il difetto e' nell'ambiente di test. Questi test lo rendono visibile e verificano
il comportamento con le librerie REALI — che sono installate nel venv, quindi la
premessa del conftest ("moduli non disponibili nell'ambiente test puro") oggi e'
falsa.
"""
import importlib
import sys

import pytest


def _con_modulo_reale(nome):
    """Rimpiazza temporaneamente il mock del conftest con il modulo vero.

    Stesso pattern gia' usato per `xmltodict` in test_invoice_service.py, ma con
    ripristino in `finally`: se non si rimette il mock, i test successivi che
    importano quel modulo cambierebbero comportamento a seconda dell'ordine.
    """
    mock_precedente = sys.modules.get(nome)
    sys.modules.pop(nome, None)
    try:
        return importlib.import_module(nome), mock_precedente
    except Exception:
        if mock_precedente is not None:
            sys.modules[nome] = mock_precedente
        raise


def _ripristina(nome, mock_precedente):
    if mock_precedente is not None:
        sys.modules[nome] = mock_precedente
    else:
        sys.modules.pop(nome, None)


def test_retriable_errors_parsing_non_e_catturabile_sotto_mock():
    """Documenta il difetto: con `openai` mockato, il `@retry` di
    `_chiama_gpt_classificazione` non puo' catturare nulla.

    Se un giorno il conftest smettera' di mockare `openai` (o il codice usera'
    eccezioni reali), questo test diventera' rosso: e' il segnale per cancellarlo
    insieme al workaround, non un fallimento da nascondere.
    """
    import services.ai_service as ai

    with pytest.raises(TypeError, match="do not inherit from BaseException"):
        try:
            raise ValueError("glitch del modello")
        except ai.RETRIABLE_ERRORS_PARSING:
            pytest.fail("irraggiungibile: la tupla contiene MagicMock")


def test_con_openai_reale_le_eccezioni_retriabili_sono_classi_vere():
    """Con la libreria vera (quella che gira in produzione) la tupla e'
    catturabile e il `ValueError` finale viene preso davvero."""
    openai_reale, mock_prec = _con_modulo_reale("openai")
    try:
        retriabili = (
            openai_reale.RateLimitError,
            openai_reale.APITimeoutError,
            openai_reale.APIConnectionError,
            openai_reale.APIError,
            ValueError,
        )
        for exc in retriabili:
            assert isinstance(exc, type) and issubclass(exc, BaseException), exc

        preso = False
        try:
            raise ValueError("glitch del modello")
        except retriabili:
            preso = True
        assert preso, "in produzione il ValueError deve far scattare il retry"
    finally:
        _ripristina("openai", mock_prec)


def test_timeout_brevo_gestito_con_requests_reale():
    """`auth_service.invia_codice_reset` distingue il Timeout dagli altri errori
    per dare un messaggio diverso all'utente. Sotto il mock quel ramo esplode in
    TypeError e finisce nell'`except Exception` sottostante: il messaggio
    specifico non e' mai stato verificato."""
    _requests_reale, mock_prec = _con_modulo_reale("requests")
    try:
        # `requests.exceptions` e' un SOTTOMODULO: se `requests` era gia' in
        # sys.modules (altri test fanno il proprio unmock e lo lasciano li'),
        # import_module lo restituisce senza garantire che il sottomodulo sia
        # stato caricato. Va importato esplicitamente.
        eccezioni = importlib.import_module("requests.exceptions")
        assert issubclass(eccezioni.Timeout, BaseException)
        preso = False
        try:
            raise eccezioni.Timeout("brevo lento")
        except eccezioni.Timeout:
            preso = True
        assert preso
    finally:
        _ripristina("requests", mock_prec)


def test_moduli_mockati_sono_in_realta_installati():
    """La premessa del conftest e' che questi moduli non siano disponibili.
    Oggi lo sono tutti: il conftest sta oscurando librerie reali e funzionanti.

    Se un giorno uno di questi sparisse dai requirements, questo test lo direbbe
    subito invece di lasciar credere che il mock sia una necessita'.
    """
    installati = []
    for nome in ("openai", "requests", "argon2", "xmltodict", "supabase", "tenacity"):
        try:
            _mod, mock_prec = _con_modulo_reale(nome)
        except ImportError:
            # `_con_modulo_reale` ha gia' rimesso il mock nel ramo d'errore.
            continue
        installati.append(nome)
        _ripristina(nome, mock_prec)

    assert installati, "nessun modulo reale trovato: ambiente di test inatteso"
    assert "openai" in installati and "requests" in installati
