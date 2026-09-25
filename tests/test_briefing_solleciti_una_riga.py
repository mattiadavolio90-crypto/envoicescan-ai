"""Fase 4, secondo pezzo — i solleciti di dati diventano UNA riga.

Misurato sul DB live il 23-24/09/2026: «il fatturato non e' stato inserito»
apriva 31 briefing su 43, e una sede riceveva due paragrafi (fatture del mese +
personale di due mesi) come notizia del giorno. Le card restano una per dato,
con la loro CTA; nel racconto i dati mancanti diventano una riga in coda alle
cose da fare: «Per completare il quadro mancano …».

Restano frase propria le fatture che NON ARRIVANO (flusso automatico fermo,
sede in avvio): sono un possibile guasto o un primo passo, non un dato da
completare.
"""
import os
from unittest.mock import patch

os.environ.setdefault("WORKER_DEV_MODE", "1")
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "x")

import services.daily_briefing_service as dbs  # noqa: E402
import services.fastapi_worker as fw  # noqa: E402
from tests.test_costi_auto_fatture_mol import _FakeQuery  # noqa: E402


def _n(topic, payload=None, title="", severity="warning"):
    return {"topic_key": topic, "severity": severity, "payload": payload or {}, "title": title}


FATTURE_AGOSTO = _n("fatture_mancanti", {"tipo": "mese_senza_costi", "mese": "agosto"})
PERSONALE_LUG_AGO = _n("costo_personale_mancante", {"descrizione": "luglio e agosto", "n_mesi": 2})
FATTURATO_AGOSTO = _n("fatturato_mancante", {"mese": "agosto", "anno": 2026})
# Forma VERA del payload di _briefing_dati_mensili_mancanti con un solo mese.
PERSONALE_AGOSTO = _n("costo_personale_mancante", {
    "mese": "agosto", "anno": 2026, "mesi": [8], "n_mesi": 1, "descrizione": "agosto"})
INCASSO_IERI = _n("incasso_mancante")
RIGHE = _n("uncategorized_rows", {"count": 10})
SDI_FERMO = _n("fatture_mancanti", {"canale": "sdi"})


def test_il_caso_di_produzione_diventa_una_riga():
    """Una sede, 23/09: fatture di agosto + personale di luglio e agosto erano due
    paragrafi con la loro motivazione. Ora una riga, e nessun "Da sistemare"."""
    snap = dbs._build_snapshot([FATTURE_AGOSTO, PERSONALE_LUG_AGO])
    assert snap["narrative"] == (
        "Per completare il quadro mancano le fatture costo di agosto e il costo "
        "del personale di luglio e agosto: finché non ci sono, margini e food "
        "cost non sono completi."
    )
    # Le card restano una per dato, con la loro CTA.
    assert [a["topic_key"] for a in snap["azioni"]] == ["fatture_mancanti", "costo_personale_mancante"]


def test_la_riga_va_in_coda_alle_cose_da_fare():
    snap = dbs._build_snapshot([FATTURATO_AGOSTO, RIGHE])
    righe = snap["narrative"].split("\n")
    assert righe[0] == "Da sistemare oggi:"
    assert righe[1].startswith("Ci sono alcune righe da controllare")
    assert righe[2] == (
        "Per completare il quadro manca il fatturato di agosto 2026: finché non "
        "c'è, margini e food cost non sono completi."
    )
    assert len(righe) == 3


def test_fatturato_e_personale_dello_stesso_mese_si_dicono_insieme():
    snap = dbs._build_snapshot([FATTURATO_AGOSTO, PERSONALE_AGOSTO, INCASSO_IERI])
    assert snap["narrative"].startswith(
        "Per completare il quadro mancano il fatturato e il costo del personale "
        "di agosto 2026 e l'incasso di ieri:"
    )


def test_la_frase_fusa_da_sola_e_plurale():
    """Due dati in una voce: "mancano ... ci sono", anche senza altre voci."""
    assert dbs._build_snapshot([FATTURATO_AGOSTO, PERSONALE_AGOSTO])["narrative"] == (
        "Per completare il quadro mancano il fatturato e il costo del personale "
        "di agosto 2026: finché non ci sono, margini e food cost non sono completi."
    )


def test_la_fusione_non_guarda_le_maiuscole():
    """Una notifica persistita scrive "Agosto", una live "agosto"."""
    fat = _n("fatturato_mancante", {"mese": "Agosto", "anno": 2026})
    narr = dbs._build_snapshot([fat, PERSONALE_AGOSTO])["narrative"]
    # Fusi nonostante la maiuscola; e dal 25/09 il mese a meta' frase e'
    # minuscolo anche quando la notifica lo porta maiuscolo.
    assert "il fatturato e il costo del personale di agosto 2026" in narr


class _SB:
    def __init__(self, righe):
        self._righe = righe

    def table(self, name):
        return _FakeQuery(self._righe if name == "margini_mensili" else [], table=name)


def test_dal_producer_vero_il_mese_del_personale_e_quello_mancante():
    """5 ottobre: settembre non si reclama ancora (dal 15), agosto manca davvero.
    Il payload diceva "settembre" (il mese precedente) e il briefing fondeva col
    fatturato di settembre: «il fatturato e il costo del personale di settembre»,
    un mese sbagliato detto con sicurezza."""
    righe = [
        {"ristorante_id": "rid-p", "anno": 2026, "mese": m, "fatturato_iva10": 1000.0,
         "fatturato_iva22": 0, "altri_ricavi_noiva": 0,
         "costo_dipendenti": 0 if m == 8 else 500.0, "costo_personale_extra": 0}
        for m in range(1, 9)
    ]
    # La data si fissa come fanno i presidi della fase 1: il producer legge
    # `datetime.datetime.now` con un import locale.
    from tests.test_briefing_solleciti_calendario import _oggi
    with _oggi(5, mese=10):
        notif = fw._briefing_dati_mensili_mancanti(
            "rid-p", _SB(righe), {"incasso_mancante", "coperti_anomalia"})
    per = next(n for n in notif if n["topic_key"] == "costo_personale_mancante")
    assert per["payload"]["mese"] == "agosto" and per["payload"]["mesi"] == [8]
    assert "agosto" in per["title"]
    narr = dbs._build_snapshot(notif)["narrative"]
    assert narr.startswith(
        "Per completare il quadro mancano il fatturato di settembre 2026 e il "
        "costo del personale di agosto 2026:"
    ), narr
    assert "il fatturato e il costo del personale" not in narr


def test_mesi_diversi_non_si_fondono():
    snap = dbs._build_snapshot([FATTURATO_AGOSTO, PERSONALE_LUG_AGO])
    assert "il fatturato di agosto 2026 e il costo del personale di luglio e agosto:" in snap["narrative"]


def test_concordanza_singolare_e_plurale():
    assert dbs._build_snapshot([INCASSO_IERI])["narrative"] == (
        "Per completare il quadro manca l'incasso di ieri: finché non c'è, "
        "margini e food cost non sono completi."
    )
    assert dbs._build_snapshot([FATTURE_AGOSTO])["narrative"].startswith(
        "Per completare il quadro mancano le fatture costo di agosto: finché non ci sono,"
    )


def test_le_fatture_che_non_arrivano_restano_una_frase_propria():
    """Un flusso automatico fermo e' un possibile guasto: non si confonde con un
    dato da inserire."""
    snap = dbs._build_snapshot([SDI_FERMO, FATTURATO_AGOSTO])
    righe = snap["narrative"].split("\n")
    assert righe[0] == "Da sistemare oggi:"
    assert righe[1].startswith("Non stanno arrivando fatture dal flusso automatico")
    assert righe[2].startswith("Per completare il quadro manca il fatturato di agosto 2026")


def test_con_un_apertura_la_riga_segue():
    buona = {"topic_key": "buona_notizia", "payload": {"tipo": "incasso_ieri", "incasso": 1000}}
    righe = dbs._build_snapshot([buona, FATTURATO_AGOSTO])["narrative"].split("\n")
    assert righe[0].startswith("Ieri sono entrati € 1.000")
    assert righe[1].startswith("Per completare il quadro manca il fatturato")
    assert len(righe) == 2


def test_al_cliente_nuovo_i_primi_passi_restano_come_prima():
    onb = {"topic_key": "onboarding", "payload": {}}
    narr = dbs._build_snapshot([onb, FATTURATO_AGOSTO])["narrative"]
    assert "Per partire: Il fatturato di agosto 2026 non è ancora stato inserito" in narr
    assert "Per completare il quadro" not in narr


def _bullets_ai(notifiche):
    with patch.object(dbs, "_narrate_with_ai", return_value="AI") as spia:
        dbs._build_snapshot(notifiche, use_ai=True)
    return spia.call_args.args[0]


def test_all_ai_i_solleciti_arrivano_come_una_voce_in_coda():
    """Con un bullet per dato il modello li ripeteva come notizia del giorno."""
    bullets = _bullets_ai([FATTURE_AGOSTO, RIGHE, PERSONALE_LUG_AGO])
    assert bullets[-1] == (
        "\U0001F9E9 Per completare il quadro mancano le fatture costo di agosto e il "
        "costo del personale di luglio e agosto: finché non ci sono, margini e "
        "food cost non sono completi."
    )
    assert len(bullets) == 2
    assert not any("Mancano le fatture costo" in b or "personale manca" in b for b in bullets)


def test_all_ai_il_cliente_nuovo_riceve_i_bullet_di_prima():
    onb = {"topic_key": "onboarding", "payload": {}}
    bullets = _bullets_ai([onb, FATTURATO_AGOSTO])
    assert not any(b.startswith("\U0001F9E9") for b in bullets)
    assert len(bullets) == 2
