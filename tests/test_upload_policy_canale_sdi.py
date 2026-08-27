"""Guardia §27/§3c — la policy date NON si applica al canale SDI, e questa e'
una DECISIONE, non una dimenticanza.

`services/upload_policy.py` (creato in §27) blocca il caricamento di fatture
troppo vecchie. E' agganciata all'upload MANUALE (`fastapi_worker.upload_invoice`)
e deliberatamente NON al canale SDI (`worker/queue_processor.py`): una fattura
recapitata dal Sistema di Interscambio arriva per legge, non e' un "caricamento"
scelto dal cliente, e la UI admin descrive il flag come "Impedisce caricamento
fatture dell'anno scorso". Scartarla la farebbe sparire senza che nessuno
l'abbia chiesto.

Esposizione misurata sul DB live (27/8/2026, invariata dal §27):
  davide.pizzata.78@gmail.com  blocco_mesi_precedenti=true   0 record in coda SDI
  offsidesp@gmail.com          blocco_mesi_precedenti=false  426 record in coda
Nessun cliente e' oggi esposto alla differenza fra i due canali.

Questi test FISSANO il comportamento attuale. Se un domani qualcuno agganciasse
la policy al queue processor, diventerebbero rossi: e' il segnale per rileggere
questa decisione, non un fallimento da nascondere.
"""
import inspect


def test_upload_manuale_applica_la_policy():
    """Il canale scelto dal cliente e' quello che la policy governa."""
    import services.fastapi_worker as fw

    src = inspect.getsource(fw.upload_invoice)
    assert "valuta_policy_data" in src, (
        "l'upload manuale deve applicare la policy date"
    )


def test_canale_sdi_non_applica_la_policy():
    """Comportamento attuale, deliberato: il queue processor non blocca per data.

    Se questo test diventa rosso, la decisione di prodotto e' cambiata: va
    aggiornato il verbale (STORICO §27) insieme al codice.
    """
    from pathlib import Path

    qp = Path(__file__).resolve().parents[1] / "worker" / "queue_processor.py"
    testo = qp.read_text(encoding="utf-8")
    assert "valuta_policy_data" not in testo, (
        "il canale SDI ha iniziato ad applicare la policy date: era una scelta "
        "esplicita non farlo (fattura recapitata per legge != caricamento). "
        "Se e' voluto, aggiorna STORICO §27 e questo test."
    )
    assert "upload_policy" not in testo


def test_la_policy_esiste_ed_e_isolata():
    """La regola vive in un modulo suo, non duplicata nei due canali."""
    from services import upload_policy

    assert hasattr(upload_policy, "valuta_policy_data")
    assert hasattr(upload_policy, "messaggio_blocco")
