"""Fase F del piano consulente (08/10/2026): prezzi scesi e fatture arrivate.

Decisioni di Mattia dell'8/10 per un briefing meno scarno:
- **prezzi scesi**: «il fornitore X ha abbassato Y». Il motore dei rincari
  (`calcola_alert`) calcolava gia' anche i ribassi e li scartava; ora lo
  specchio di `_alert_prodotti` li tiene, con lo stesso filtro di rilevanza e
  la stessa soglia del cliente, piu' la freschezza (acquisto negli ultimi 7
  giorni: misurato l'8/10, da 0 a 2 per sede in due settimane);
- **fatture arrivate, sempre**: prima si dicevano solo se mancavano MOL e
  incasso di ieri; ora si accodano anche a quelli.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import services.daily_briefing_service as dbs
import services.fastapi_worker as fw
import services.price_impact_service as pis
from tests.test_briefing_raccolta_notifiche import (  # noqa: F401  (fixture)
    RID, USER, _FakeSB, _topics, prezzi, stub,
)

OGGI = pd.Timestamp("2026-10-08")


def _alert(prodotto, perc, impatto, giorni_fa=2, fornitore="FORN"):
    return {"Prodotto": prodotto, "Fornitore": fornitore, "Aumento_Perc": perc,
            "Impatto_Stimato": impatto,
            "Data": (OGGI - pd.Timedelta(days=giorni_fa)).strftime("%Y-%m-%d")}


def _ribassi(righe, soglia=5.0, pareto=None, preferiti=None):
    df = pd.DataFrame(righe)
    pareto = {pis._pareto_key(r["Prodotto"]) for r in righe} if pareto is None else pareto
    return pis._ribassi_prodotti(df, soglia, pareto, preferiti, oggi=OGGI)


# ── Il motore: quali ribassi ──────────────────────────────────────────────

def test_ribasso_fresco_su_prodotto_che_pesa():
    out = _ribassi([_alert("SALMONE", -12.04, -85.4)])
    assert out == [{"nome": "SALMONE", "fornitore": "FORN", "ribasso_pct": 12.0,
                    "risparmio_mese": 85.0}]


@pytest.mark.parametrize("giorni_fa,atteso", [(7, 1), (8, 0)])
def test_solo_acquisti_degli_ultimi_sette_giorni(giorni_fa, atteso):
    assert len(_ribassi([_alert("SALMONE", -12, -85, giorni_fa=giorni_fa)])) == atteso


@pytest.mark.parametrize("perc,atteso", [(-5.0, 1), (-4.9, 0)])
def test_soglia_del_cliente(perc, atteso):
    assert len(_ribassi([_alert("SALMONE", perc, -85)])) == atteso


def test_i_rincari_non_sono_ribassi():
    assert _ribassi([_alert("SALMONE", 12, 85)]) == []


def test_impatto_non_negativo_non_e_un_risparmio():
    assert _ribassi([_alert("SALMONE", -12, 0.0)]) == []


def test_fuori_dalla_fascia_che_pesa_non_si_dice():
    """I marginali (limoni & co.) restano fuori, come per i rincari."""
    assert _ribassi([_alert("LIMONI", -40, -2)], pareto={"SALMONE"}) == []


def test_modalita_solo_preferiti():
    righe = [_alert("SALMONE", -12, -85), _alert("TONNO", -20, -150)]
    pref = {pis._pref_match_key("SALMONE", "FORN")}
    out = _ribassi(righe, pareto=set(), preferiti=pref)
    assert [r["nome"] for r in out] == ["SALMONE"]


def test_ordinati_per_risparmio():
    righe = [_alert("SALMONE", -30, -20), _alert("TONNO", -6, -150), _alert("RISO", -10, -60)]
    assert [r["nome"] for r in _ribassi(righe)] == ["TONNO", "RISO", "SALMONE"]


def test_il_motore_li_restituisce_accanto_ai_rincari():
    """Un solo `calcola_alert` per rincari e ribassi."""
    df_alert = pd.DataFrame([
        {**_alert("SALMONE", -12, -85, giorni_fa=1), "Categoria": "PESCE"},
        {**_alert("TONNO", 9, 40, giorni_fa=1), "Categoria": "PESCE"},
    ])
    df = pd.DataFrame([{"DataDocumento": pd.Timestamp.now().strftime("%Y-%m-%d"),
                        "Descrizione": "SALMONE", "TotaleRiga": 100, "Categoria": "PESCE"}])
    pareto = {"SALMONE", "TONNO"}
    with patch.object(pis, "carica_e_prepara_dataframe", return_value=df), \
         patch.object(pis, "calcola_alert", return_value=df_alert) as ca, \
         patch.object(pis, "_prodotti_pareto", return_value=pareto), \
         patch.object(pis, "_leggi_soglia_perc_cliente", return_value=5.0), \
         patch.object(pis, "_leggi_solo_preferiti", return_value=False), \
         patch.object(pis, "_alert_tag", return_value=[]):
        out = pis.calcola_alert_prezzi_impatto(USER, RID, supabase_client=object())
    assert ca.call_count == 1
    assert [a["nome"] for a in out["alerts"]] == ["TONNO"]
    assert [r["nome"] for r in out["ribassi"]] == ["SALMONE"]


# ── La raccolta del briefing ──────────────────────────────────────────────

RIB = {"count": 0, "top": None,
       "ribassi": [{"nome": "SALMONE", "fornitore": "FORN", "ribasso_pct": 12.0,
                    "risparmio_mese": 85.0}]}


def _raccogli(stub, **kw):
    stub("_briefing_osservazioni", lambda *a, **k: [])
    stub("_briefing_osservazioni_pv", lambda *a, **k: [])
    return fw._briefing_raccogli_notifiche(USER, RID, _FakeSB(), **kw)


def test_ribasso_diventa_osservazione(stub, prezzi):
    prezzi(RIB)
    out = _raccogli(stub, includi_osservazioni=True)
    rec = [n for n in out if n["topic_key"] == "prezzo_sceso"]
    assert len(rec) == 1 and rec[0]["severity"] == "success"
    assert rec[0]["payload"] == RIB["ribassi"][0]


def test_ribasso_solo_dal_percorso_completo(stub, prezzi):
    prezzi(RIB)
    out = _raccogli(stub, includi_osservazioni=False)
    assert all(n["topic_key"] != "prezzo_sceso" for n in out)


def test_ribassi_spenti_non_si_dicono(stub, prezzi):
    prezzi(RIB)
    stub("_get_assistant_preferences", lambda *a, **k: _topics("prezzo_sceso"))
    out = _raccogli(stub, includi_osservazioni=True)
    assert all(n["topic_key"] != "prezzo_sceso" for n in out)


def test_alert_spento_ma_ribassi_accesi_il_motore_gira(stub, prezzi):
    chiamate = prezzi({**RIB, "count": 1, "top": {"nome": "X", "aumento_pct": 9}})
    stub("_get_assistant_preferences", lambda *a, **k: _topics("price_alert"))
    out = _raccogli(stub, includi_osservazioni=True)
    assert chiamate == [True]
    assert [n["topic_key"] for n in out if n["topic_key"] in ("price_alert", "prezzo_sceso")] \
        == ["prezzo_sceso"]


def test_tutti_e_due_spenti_il_motore_non_gira(stub, prezzi):
    chiamate = prezzi(RIB)
    stub("_get_assistant_preferences", lambda *a, **k: _topics("price_alert", "prezzo_sceso"))
    _raccogli(stub, includi_osservazioni=True)
    assert chiamate == []


def test_senza_ribassi_niente_riga(stub, prezzi):
    prezzi({"count": 0, "top": None, "ribassi": []})
    out = _raccogli(stub, includi_osservazioni=True)
    assert all(n["topic_key"] != "prezzo_sceso" for n in out)


def test_e_nel_configuratore_anche_per_i_negozi():
    voci = {k: lbl for (k, lbl, _b, _d) in fw._CONFIG_TOPICS}
    assert voci["prezzo_sceso"] == "Prezzi scesi"
    assert "prezzo_sceso" not in fw._TOPIC_OFF_PER_SETTORE["retail"]


# ── Il testo dei prezzi scesi ─────────────────────────────────────────────

OSS_PREZZO = {"topic_key": "prezzo_sceso", "severity": "success",
              "payload": {"nome": "SALMONE NORVEGESE", "fornitore": "ITTICA ROSSI",
                          "ribasso_pct": 12.0, "risparmio_mese": 85.0}}


@pytest.mark.parametrize("payload,attesa", [
    (OSS_PREZZO["payload"],
     "🏷️ Prezzo sceso: «SALMONE NORVEGESE» di «ITTICA ROSSI» costa il 12,0% in meno, circa € 85 al mese."),
    ({"nome": "SALMONE", "fornitore": "", "ribasso_pct": 6.5, "risparmio_mese": 0.4},
     "🏷️ Prezzo sceso: «SALMONE» costa il 6,5% in meno."),
    ({"nome": "", "ribasso_pct": 6.5}, ""),
])
def test_frase(payload, attesa):
    assert dbs._osservazione_frase({"topic_key": "prezzo_sceso", "payload": payload}) == attesa


def test_entra_nel_briefing_e_tiene_il_verde():
    snap = dbs._build_snapshot([OSS_PREZZO])
    assert "«SALMONE NORVEGESE»" in snap["narrative"]
    assert snap["tutto_ok"] is True


def test_spenta_non_si_dice():
    snap = dbs._build_snapshot([OSS_PREZZO], topics_disabled=["prezzo_sceso"])
    assert "SALMONE" not in snap["narrative"]


def test_i_nomi_non_vanno_all_ai():
    bullet = dbs._osservazione_frase(OSS_PREZZO)
    anon, mappa = dbs._anonymize_bullets([bullet])
    assert "SALMONE" not in anon[0] and "ITTICA" not in anon[0]
    assert dbs._deanonymize(anon[0], mappa) == bullet


def test_l_ai_non_puo_perdere_la_percentuale():
    assert set(dbs._numeri_obbligatori([OSS_PREZZO])) == dbs._numeri_di("12,0")


# ── Le fatture arrivate, sempre ───────────────────────────────────────────

INCASSO = {"id": "b", "topic_key": "buona_notizia", "severity": "success",
           "payload": {"tipo": "incasso_ieri", "incasso": 497, "giorno_settimana": "mercoledì"}}
FATTURE = {"n_fatture": 3, "importo": 2400.0, "righe_da_controllare": 0}


def _buona(principale, fatture=FATTURE, errore=None):
    with patch.object(fw, "_buona_notizia_principale", return_value=principale), \
         patch.object(fw, "_fatture_arrivate_ieri_sdi",
                      side_effect=errore, return_value=fatture) as fa:
        return fw._briefing_buona_notizia(USER, RID, MagicMock()), fa


def test_le_fatture_si_accodano_all_incasso():
    rec, _ = _buona({**INCASSO, "payload": dict(INCASSO["payload"])})
    assert rec["payload"]["fatture_ieri"] == {"n_fatture": 3, "importo": 2400.0}


def test_le_fatture_si_accodano_al_mol():
    mol = {"topic_key": "buona_notizia", "payload": {"tipo": "mol_mese", "mese": "settembre"}}
    rec, _ = _buona(mol)
    assert rec["payload"]["fatture_ieri"]["n_fatture"] == 3


def test_le_fatture_gia_buona_notizia_non_si_raddoppiano():
    fb = {"topic_key": "buona_notizia", "payload": {"tipo": "fatture_arrivate", "n_fatture": 3}}
    rec, fa = _buona(fb)
    assert "fatture_ieri" not in rec["payload"]
    fa.assert_not_called()


def test_senza_fatture_ieri_niente_coda():
    rec, _ = _buona({**INCASSO, "payload": dict(INCASSO["payload"])}, fatture={"n_fatture": 0, "importo": 0.0, "righe_da_controllare": 0})
    assert "fatture_ieri" not in rec["payload"]


def test_senza_buona_notizia_niente():
    assert _buona(None)[0] is None


def test_un_errore_sulle_fatture_lascia_la_buona_notizia():
    rec, _ = _buona({**INCASSO, "payload": dict(INCASSO["payload"])}, errore=RuntimeError("giu'"))
    assert rec["payload"]["tipo"] == "incasso_ieri" and "fatture_ieri" not in rec["payload"]


def _con_fatture(rec):
    return {**rec, "payload": {**rec["payload"], "fatture_ieri": {"n_fatture": 3, "importo": 2400.0}}}


def test_il_testo_dice_incasso_e_fatture():
    snap = dbs._build_snapshot([_con_fatture(INCASSO)])
    assert "Ieri (mercoledì) sono entrati € 497 di incasso." in snap["narrative"]
    assert "Ieri sono arrivate 3 fatture per € 2.400, già registrate." in snap["narrative"]


def test_il_bullet_per_l_ai_dice_incasso_e_fatture():
    b = dbs._buona_notizia_bullet(_con_fatture(INCASSO)["payload"])
    assert "€ 497" in b and "3 fatture per € 2.400" in b


def test_l_ai_non_puo_perdere_le_fatture():
    with patch.object(dbs, "_narrate_with_ai", return_value="ok") as narra:
        dbs._build_snapshot([_con_fatture(INCASSO)], use_ai=True)
    assert set(dbs._numeri_di("2.400")) <= set(narra.call_args.args[2])


def test_senza_coda_il_testo_resta_quello_di_prima():
    assert dbs._buona_notizia_frase(INCASSO["payload"]) == \
        "Ieri (mercoledì) sono entrati € 497 di incasso."
    assert dbs._numeri_fatture_ieri(INCASSO) == []
