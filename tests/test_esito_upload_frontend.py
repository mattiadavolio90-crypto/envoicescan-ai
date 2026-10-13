"""Scartata (arancio) o non caricata (rossa): l'esito di un file nella finestra
«Carica fatture» (`apps/web/src/lib/esito-upload.ts`).

Un doppione e' sempre scartato: il cliente non deve fare niente. Il 12/10/2026
`duplicate_document` usciva in rosso col codice grezzo, contato «non caricata»,
ritentato a ogni «Carica N file» e con l'avviso «1 file non e' stato caricato»
alla chiusura: il cliente pensava a un guasto.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/esito-upload"
RICHIEDE = ["classificaEsitoUpload"]


def _esito(data, ok=True, http=200):
    return esegui_ts(
        MODULO,
        "emit(m.classificaEsitoUpload(input.ok, input.http, input.data))",
        argomento={"ok": ok, "http": http, "data": data},
        richiede=RICHIEDE,
    )


@pytest.mark.parametrize("errore", [
    "ALREADY_LOADED:IT01879020517A2026_g7KVL (1).xml",
    "ALREADY_LOADED:",
    "duplicate_document",
])
def test_ogni_doppione_e_scartato_non_in_errore(errore):
    e = _esito({"success": False, "error": errore})
    assert e["status"] == "skipped", e
    assert e.get("skip_motivo") == "ALREADY_LOADED"
    assert e.get("error") is None, "un doppione non porta un messaggio d'errore"


def test_piva_estranea_e_scartata():
    e = _esito({"success": False, "error": "PIVA_NESSUNA_SEDE"})
    assert e == {"status": "skipped", "skip_motivo": "PIVA_NESSUNA_SEDE"}


def test_ambiguo_nuovo_va_in_coda():
    e = _esito({"success": True, "routing_status": "ambiguo", "queue_created": True})
    assert e["status"] == "queued"


def test_ambiguo_gia_in_coda_e_scartato_anche_se_success_e_true():
    e = _esito({"success": True, "routing_status": "ambiguo", "queue_created": False})
    assert e == {"status": "skipped", "skip_motivo": "GIA_IN_CODA"}


def test_successo():
    assert _esito({"success": True, "righe_salvate": 10})["status"] == "success"


@pytest.mark.parametrize("errore", ["NESSUNA_SEDE_CONFIGURATA", "no_data", "File non leggibile"])
def test_un_errore_vero_resta_rosso(errore):
    e = _esito({"success": False, "error": errore})
    assert e == {"status": "error", "error": errore}


def test_http_non_ok_e_errore_col_dettaglio():
    e = _esito({"detail": "Formato non supportato"}, ok=False, http=422)
    assert e == {"status": "error", "error": "Formato non supportato"}


def test_http_non_ok_senza_corpo_dice_il_codice():
    e = _esito({}, ok=False, http=502)
    assert e == {"status": "error", "error": "HTTP 502"}


def test_la_finestra_usa_la_lib_e_non_una_copia_della_mappa():
    """La lib conta solo se la finestra la chiama: una seconda mappa inline
    tornerebbe a decidere da sola (ed era quella a non conoscere il doppione)."""
    from pathlib import Path

    sorgente = (
        Path(__file__).resolve().parents[1]
        / "apps/web/src/app/(app)/analisi-fatture/upload-modal.tsx"
    ).read_text(encoding="utf-8")
    assert "classificaEsitoUpload(res.ok, res.status, data)" in sorgente
    assert 'startsWith("ALREADY_LOADED:")' not in sorgente
    assert '"PIVA_NESSUNA_SEDE"' not in sorgente.split("{entry.status === \"skipped\"")[0], (
        "la classificazione degli scarti e' tornata dentro upload-modal.tsx"
    )
