"""Fase 3 — il gate di affidabilita' per TUTTE le fonti.

Fino alla Fase 2 il controllo esisteva solo per l'AI (3,6% delle righe): memoria e
dizionario scrivevano senza passare da alcun gate. Qui si verifica che il gate
esista, che sia conservativo come la misura ha imposto, e soprattutto che NON
declassi cio' che non deve.

Nessun mock: `valuta_fiducia` e' pura. E' un requisito, non una comodita' — la
trappola nota di CLAUDE.md e' un test che mocka il client e non prova nulla.
"""

from pathlib import Path

import pytest

from services.ai_service import (
    _FONTI_CERTE,
    _FONTI_PROBABILI,
    _fiducia_per_fonte,
    valuta_fiducia,
)

RADICE = Path(__file__).resolve().parents[1]


# ── Le regole del gate, una per una ────────────────────────────────────────

@pytest.mark.parametrize("categoria", ["", None, "Da Classificare"])
def test_riga_in_coda_non_ha_fiducia(categoria):
    """Una riga senza categoria non ha una fiducia: ha un'assenza."""
    assert valuta_fiducia("L7_dizionario", categoria, "QUALSIASI COSA") is None


def test_provenienza_assente_resta_legacy():
    """Vincolo S3: 39.224 righe storiche non hanno provenienza.

    Se l'assenza diventasse `da_verificare`, l'intero storico diverrebbe dubbio e
    il MOL di aprile cambierebbe mesi dopo. Assente = legacy = certa, sempre.
    """
    assert valuta_fiducia(None, "CARNE", "PETTO DI POLLO") is None
    assert valuta_fiducia("", "CARNE", "PETTO DI POLLO") is None


@pytest.mark.parametrize("fonte", sorted(_FONTI_CERTE))
def test_fonte_certa_non_e_mai_declassata(fonte):
    """Un umano o una regola certificata ha deciso: il gate non lo discute.

    Vale ANCHE su una descrizione illeggibile: declassare una riga appena corretta
    dal cliente sarebbe l'opposto di cio' che la tracciabilita' serve a garantire.
    """
    assert valuta_fiducia(fonte, "CARNE", "1 ACCONTO") == "certa"
    assert valuta_fiducia(fonte, "CARNE", "XZ4 TRSP") == "certa"


@pytest.mark.parametrize("fonte", sorted(_FONTI_PROBABILI))
def test_fonte_probabile_su_descrizione_illeggibile_va_verificata(fonte):
    """L'unica riga nuova di logica dell'intera fase."""
    assert valuta_fiducia(fonte, "UTENZE E LOCALI", "1 ACCONTO") == "da_verificare"


@pytest.mark.parametrize("fonte", sorted(_FONTI_PROBABILI))
def test_fonte_probabile_su_descrizione_leggibile_resta_probabile(fonte):
    assert valuta_fiducia(fonte, "PESCE", "SALMONE AFFUMICATO 200G") == "probabile"


def test_senza_descrizione_non_si_declassa():
    """Senza il testo non si puo' dubitare: inventare un dubbio e' peggio che non averlo."""
    assert valuta_fiducia("L7_dizionario", "PESCE") == "probabile"
    assert _fiducia_per_fonte("L7_dizionario", "PESCE") == "probabile"


def test_fonte_sconosciuta_va_verificata():
    assert valuta_fiducia("L99_inventata", "PESCE", "SALMONE 5-6") == "da_verificare"


# ── I casi reali che hanno deciso la forma del gate ────────────────────────

def test_casi_reali_che_il_gate_deve_pescare():
    """Descrizioni vere che nessun umano puo' categorizzare senza aprire la fattura.

    Sono le righe di maggiore importo fra le 280 declassate (misura 1/9/2026):
    "1 ACCONTO" vale 14.000 EUR, "COMMISSION" 13.715 EUR.
    """
    for desc, cat in [
        ("1 ACCONTO", "UTENZE E LOCALI"),
        ("COMMISSION", "SERVIZI E CONSULENZE"),
        ("SALDO", "MANUTENZIONE E ATTREZZATURE"),
        ("RICARICHE", "UTENZE E LOCALI"),
        ("ALIMENTARI", "SCATOLAME E CONSERVE"),
    ]:
        assert valuta_fiducia("L3_globale", cat, desc) == "da_verificare", desc


def test_il_silenzio_del_dizionario_non_e_un_dubbio():
    """Il piano voleva declassare tutto cio' che il deterministico non conferma:
    8,6% delle righe, 364.000 EUR. La misura lo ha rovesciato — queste categorie
    le ha decise la memoria e sono CORRETTE, il dizionario semplicemente non le copre.
    """
    for desc, cat in [
        ("TARIFFA DI VENDITA PUN F1", "UTENZE E LOCALI"),
        ("DIVANI E ANGOLI PER ARREDAMENTO", "MANUTENZIONE E ATTREZZATURE"),
        ("ADDEBITO CAUZIONI", "SERVIZI E CONSULENZE"),
    ]:
        assert valuta_fiducia("L3_globale", cat, desc) == "probabile", desc


def test_il_dissenso_del_deterministico_non_declassa():
    """Su queste righe il nucleo deterministico dissente dalla categoria salvata —
    e ha torto lui: su "KG5 KETCHUP" dice MANUTENZIONE (regola `fornitura_durevole`),
    su "DOPPIO CONCENTRATO DI POMODORO" dice VERDURE. Un gate che declassasse il
    dissenso genererebbe soprattutto falsi allarmi.
    """
    for desc, cat in [
        ("KG5 KETCHUP TOPFOOD SECCHIO", "SALSE E CREME"),
        ("DOPPIO CONCENTRATO DI POMODORO 12X440G", "SCATOLAME E CONSERVE"),
        ("UNAGI SAUCE NIPPON SHOKKEN 6*2KG", "SALSE E CREME"),
    ]:
        assert valuta_fiducia("L2_locale", cat, desc) == "certa", desc
        assert valuta_fiducia("L3_globale", cat, desc) != "da_verificare", desc


# ── Il vincolo "nessun numero visto dal cliente cambia" ────────────────────

def test_margini_non_guardano_needs_review():
    """La Fase 3 non puo' cambiare un numero cliente perche' non ne ha la via.

    Questa guardia impedisce a una fase futura di accoppiare margini e coda per
    distrazione: se qualcuno introduce `needs_review` nei margini, deve essere una
    decisione presa (Fase 4, dietro flag), non un effetto collaterale.
    """
    sorgente = (RADICE / "services" / "margine_service.py").read_text(encoding="utf-8")
    assert "needs_review" not in sorgente


def test_il_gate_non_decide_needs_review():
    """Il gate produce una fiducia e nient'altro: non tocca la coda del cliente."""
    import inspect

    sorgente = inspect.getsource(valuta_fiducia)
    assert "needs_review" not in sorgente


# ── Il percorso PDF/Vision (debito di Fase 2, chiuso qui) ──────────────────

def test_percorso_pdf_registra_la_provenienza():
    """Era l'unico percorso che classificava senza dire chi aveva deciso: le sue
    righe arrivavano a DB con le colonne NULL, cioe' trattate come certe."""
    sorgente = (RADICE / "services" / "invoice_service.py").read_text(encoding="utf-8")
    assert "_pdf_fonte, _pdf_fiducia = ultima_provenienza()" in sorgente

    ai = (RADICE / "services" / "ai_service.py").read_text(encoding="utf-8")
    assert "def _ret_ocp(" in ai


def test_ottieni_categoria_prodotto_azzera_la_provenienza_precedente():
    """Senza il reset, un'uscita non tracciata lascerebbe in circolo la provenienza
    di una riga PRECEDENTE: il canale laterale mentirebbe invece di tacere."""
    from services import ai_service

    ai_service._PROVENIENZA_CORRENTE.set(("L2_locale", "certa"))
    try:
        ai_service.ottieni_categoria_prodotto("QUALCOSA", user_id=None)
    except Exception:
        pass
    fonte, _fiducia = ai_service.ultima_provenienza()
    assert fonte != "L2_locale"


# ── I chiamanti passano davvero il contesto ────────────────────────────────

@pytest.mark.parametrize(
    "percorso, atteso",
    [
        ("services/upload_handler.py", "valuta_fiducia(\n"),
        ("worker/queue_processor.py", "_valuta_fiducia_safe(fonte, categoria, desc, _forn)"),
        ("services/fastapi_worker.py", "valuta_fiducia(\n"),
    ],
)
def test_i_chiamanti_passano_la_descrizione(percorso, atteso):
    """Un gate che riceve solo (fonte, categoria) non puo' dubitare di nulla:
    tornerebbe al comportamento pre-Fase 3 senza che nessun test se ne accorga.
    """
    sorgente = (RADICE / percorso).read_text(encoding="utf-8")
    assert atteso in sorgente
    assert "_fiducia_per_fonte" not in sorgente
