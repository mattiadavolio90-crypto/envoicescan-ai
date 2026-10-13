"""La lista «Oggi» dell'admin e il riepilogo Telegram del mattino: dati veri in
forma (quelli degli endpoint di salute), nessun mock di Supabase."""
from __future__ import annotations

from datetime import datetime, timezone

from services import admin_attenzione_service as att

ADESSO = datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc)

CLIENTI = [
    {"id": "u1", "nome_ristorante": "Trattoria", "nome_gruppo": None, "email": "t@x.it", "attivo": True,
     "last_seen_at": "2026-10-12T09:00:00+00:00", "created_at": "2026-07-01T00:00:00+00:00",
     "trial": None, "sedi": [{"id": "r1"}]},
    {"id": "u2", "nome_ristorante": "Bar", "nome_gruppo": "CATENA", "email": "b@x.it", "attivo": True,
     "last_seen_at": "2026-10-12T09:00:00+00:00", "created_at": "2026-07-01T00:00:00+00:00",
     "trial": {"active": True, "days_remaining": 1}, "sedi": [{"id": "r2"}, {"id": "r3"}]},
    {"id": "u3", "nome_ristorante": "Nuovo", "nome_gruppo": None, "email": "n@x.it", "attivo": False,
     "last_seen_at": None, "created_at": "2026-10-05T00:00:00+00:00", "trial": None, "sedi": []},
    {"id": "u4", "nome_ristorante": "Appena creato", "nome_gruppo": None, "email": "a@x.it", "attivo": False,
     "last_seen_at": None, "created_at": "2026-10-12T00:00:00+00:00", "trial": None, "sedi": []},
]


def _p(qid, status, **kw):
    return {"queue_id": qid, "status": status, "piva_raw": "01234567890", "numero": "12",
            "importo": 1234.5, "created_at": f"2026-10-1{qid % 3}T08:00:00+00:00", "last_error": None, **kw}


def _voci(**kw):
    return att.componi_voci(adesso=ADESSO, clienti=CLIENTI, **kw)


def _per_chiave(voci):
    return {v["chiave"]: v for v in voci}


def test_ogni_stato_di_fattura_ha_la_sua_azione():
    fatture = {
        "items": [{"user_id": "u2", "nome": "CATENA",
                   "problemi": [_p(1, "da_assegnare"), _p(2, "failed", last_error="404"), _p(3, "dead")]}],
        "orfane": [_p(4, "unknown_tenant", piva_raw="99999999999"), _p(5, "dead")],
    }
    v = _per_chiave(_voci(fatture=fatture))
    assert v["fattura:1"]["azione"] == {"tipo": "assegna_sede", "queue_id": 1, "user_id": "u2"}
    assert v["fattura:1"]["gravita"] == "oggi" and v["fattura:1"]["cliente"] == "CATENA"
    assert v["fattura:2"]["azione"] == {"tipo": "riprova", "queue_id": 2}
    assert "404" in v["fattura:2"]["dettaglio"]
    assert v["fattura:3"]["titolo"] == "Fattura bloccata dopo i tentativi"
    assert v["fattura:4"]["azione"] == {"tipo": "assegna_piva", "queue_id": 4, "piva": "99999999999"}
    assert v["fattura:4"]["cliente_id"] is None
    assert v["fattura:5"]["azione"]["tipo"] == "riprova"
    assert "€ 1.234,50" in v["fattura:1"]["dettaglio"]
    assert "P.IVA" not in v["fattura:1"]["dettaglio"]
    assert "P.IVA 99999999999" in v["fattura:4"]["dettaglio"]


def test_la_fattura_da_smistare_dice_dove_va_consegnata():
    fatture = {"items": [{"user_id": "u2", "nome": "CATENA",
                          "problemi": [_p(1, "da_assegnare", indirizzo="Via Roma 5, Milano")]}], "orfane": []}
    assert _per_chiave(_voci(fatture=fatture))["fattura:1"]["dettaglio"] == "n. 12 · € 1.234,50 · consegna: Via Roma 5, Milano"


def test_i_critici_vengono_prima_e_ognuno_dal_piu_vecchio():
    fatture = {"items": [{"user_id": "u1", "nome": "Trattoria", "problemi": [
        {**_p(10, "da_assegnare"), "created_at": "2026-10-01T00:00:00+00:00"},
        {**_p(11, "failed"), "created_at": "2026-10-12T00:00:00+00:00"},
        {**_p(12, "failed"), "created_at": "2026-10-03T00:00:00+00:00"},
    ]}], "orfane": []}
    chiavi = [v["chiave"] for v in _voci(fatture=fatture) if v["chiave"].startswith("fattura:")]
    assert chiavi == ["fattura:12", "fattura:11", "fattura:10"]


def test_ricavi_fermi_buchi_e_sani():
    ricavi = {"items": [
        {"ristorante_id": "r1", "nome_ristorante": "Trattoria", "stato": "critico", "giorni_silenzio": 4,
         "n_buchi": 0, "coda_problemi": 0, "ultima_data": "2026-10-09"},
        {"ristorante_id": "r2", "nome_ristorante": "Bar 1", "stato": "warning", "giorni_silenzio": 1,
         "n_buchi": 1, "coda_problemi": 0, "ultima_data": "2026-10-12"},
        {"ristorante_id": "r3", "nome_ristorante": "Bar 2", "stato": "ok", "giorni_silenzio": 0,
         "n_buchi": 0, "coda_problemi": 0},
    ]}
    v = _per_chiave(_voci(ricavi=ricavi))
    assert v["ricavi:r1"]["titolo"] == "Ricavi fermi da 4 giorni"
    assert v["ricavi:r1"]["gravita"] == "critico" and v["ricavi:r1"]["cliente_id"] == "u1"
    assert v["ricavi:r1"]["link"] == "/admin/clienti/u1?tab=sedi"
    assert v["ricavi:r2"]["titolo"] == "Mancano i ricavi di 1 giorno"
    assert v["ricavi:r2"]["gravita"] == "oggi" and v["ricavi:r2"]["cliente"] == "CATENA"
    assert "ricavi:r3" not in v


def test_mai_arrivati_e_coda_bloccata():
    ricavi = {"items": [
        {"ristorante_id": "r1", "stato": "critico", "giorni_silenzio": None, "n_buchi": 0, "coda_problemi": 0},
        {"ristorante_id": "r2", "stato": "critico", "giorni_silenzio": 0, "n_buchi": 0, "coda_problemi": 2},
    ]}
    v = _per_chiave(_voci(ricavi=ricavi))
    assert v["ricavi:r1"]["titolo"] == "Nessun ricavo mai arrivato dal gestionale"
    assert v["ricavi:r2"]["titolo"] == "Import dei ricavi bloccato"


def test_email_ricavi_e_mittente_sconosciuto():
    imp = {"items": [
        {"id": "e1", "status": "unknown_sender", "email_sender": "cassa@x.it", "attachment_name": "a.xls"},
        {"id": "e2", "status": "dead", "last_error": "file vuoto"},
        {"id": "e3", "status": "done"},
    ]}
    v = _per_chiave(_voci(ricavi_import=imp))
    assert v["import:e1"]["azione"] == {"tipo": "collega_mittente"}
    assert v["import:e1"]["gravita"] == "oggi"
    assert v["import:e2"]["gravita"] == "critico" and v["import:e2"]["azione"] is None
    assert "import:e3" not in v


def test_sopra_soglia_una_volta_per_sede_nei_mesi_d_avviso():
    consumi = {"mesi_avviso": ["2026-10", "2026-09"], "righe": [
        {"ristorante_id": "r1", "mese": "2026-10", "sede": "Trattoria", "totale": 60, "limite": 50, "sopra_soglia": True},
        {"ristorante_id": "r1", "mese": "2026-09", "sede": "Trattoria", "totale": 55, "limite": 50, "sopra_soglia": True},
        {"ristorante_id": "r2", "mese": "2026-08", "sede": "Bar", "totale": 99, "limite": 50, "sopra_soglia": True},
        {"ristorante_id": "r3", "mese": "2026-10", "sede": "Bar 2", "totale": 10, "limite": 50, "sopra_soglia": False},
    ]}
    voci = [v for v in _voci(consumi=consumi) if v["chiave"].startswith("soglia:")]
    assert [v["chiave"] for v in voci] == ["soglia:r1"]
    assert voci[0]["dettaglio"] == "Trattoria · 60 su 50 a 2026-10"


def test_attivazione_in_sospeso_solo_dopo_tre_giorni_e_prova_in_scadenza():
    v = _per_chiave(_voci())
    assert v["attivazione:u3"]["link"] == "/admin/clienti/u3?tab=account"
    assert "attivazione:u4" not in v
    assert v["prova:u2"]["titolo"] == "La prova finisce domani"
    assert "prova:u1" not in v


def test_la_prova_avvisa_da_due_giorni_prima_non_da_tre():
    def con_prova(giorni):
        c = {**CLIENTI[0], "trial": {"active": True, "days_remaining": giorni}}
        return _per_chiave(att.componi_voci(adesso=ADESSO, clienti=[c]))
    assert con_prova(2)["prova:u1"]["titolo"] == "La prova finisce fra 2 giorni"
    assert con_prova(0)["prova:u1"]["titolo"] == "La prova finisce oggi"
    assert "prova:u1" not in con_prova(3)


def test_categorie_richieste_e_allarmi():
    richieste = [
        {"id": "l1", "stato": "nuovo", "servizio_label": "Consulenza HACCP", "contatto_email": "x@y.it",
         "created_at": "2026-10-12T00:00:00+00:00"},
        {"id": "l2", "stato": "gestito", "servizio_label": "Altro"},
    ]
    allarmi = [{"chiave": "server_giu", "gravita": "critico", "testo": "Il server non risponde",
                "aperto_at": "2026-10-13T09:00:00+00:00", "link": None}]
    v = _per_chiave(_voci(n_categorie=1, richieste=richieste, allarmi=allarmi))
    assert v["categorie"]["titolo"] == "1 descrizione da classificare"
    assert v["richiesta:l1"]["azione"] == {"tipo": "richiesta", "id": "l1"}
    assert "richiesta:l2" not in v
    assert v["allarme:server_giu"]["gravita"] == "critico"
    assert "categorie" not in _per_chiave(_voci(n_categorie=0))


def test_problemi_per_cliente():
    voci = [{"cliente_id": "u1"}, {"cliente_id": "u1"}, {"cliente_id": None}, {"cliente_id": "u2"}]
    assert att.problemi_per_cliente(voci) == {"u1": 2, "u2": 1}


def test_finestra_del_riepilogo_con_ora_legale_e_solare():
    # 13/10 ora legale: 06 UTC = 08 Roma; 07 UTC = 09 Roma — entrambi dentro
    assert att.e_ora_del_riepilogo(datetime(2026, 10, 13, 6, 5, tzinfo=timezone.utc)) is True
    assert att.e_ora_del_riepilogo(datetime(2026, 10, 13, 7, 5, tzinfo=timezone.utc)) is True
    # 15/12 ora solare: 06 UTC = 07 Roma (fuori), 07 UTC = 08 Roma (dentro)
    assert att.e_ora_del_riepilogo(datetime(2026, 12, 15, 6, 5, tzinfo=timezone.utc)) is False
    assert att.e_ora_del_riepilogo(datetime(2026, 12, 15, 7, 5, tzinfo=timezone.utc)) is True
    assert att.e_ora_del_riepilogo(datetime(2026, 12, 15, 9, 0, tzinfo=timezone.utc)) is False


def test_la_chiave_del_riepilogo_e_il_giorno_di_roma():
    # 23:30 UTC del 12/10 e' gia' il 13/10 a Roma
    assert att.chiave_riepilogo(datetime(2026, 10, 12, 23, 30, tzinfo=timezone.utc)) == "riepilogo:2026-10-13"


def test_ieri_e_il_giorno_di_roma():
    inizio, fine = att.finestra_ieri(datetime(2026, 10, 13, 6, 0, tzinfo=timezone.utc))
    assert inizio == "2026-10-12T00:00:00+02:00" and fine == "2026-10-13T00:00:00+02:00"


def test_testo_del_riepilogo():
    voci = [
        {"gravita": "critico", "cliente": "Trattoria", "titolo": "Ricavi fermi da 4 giorni"},
        {"gravita": "oggi", "cliente": None, "titolo": "3 descrizioni da classificare"},
    ]
    t = att.testo_riepilogo(voci, {"fatture_ieri": 12, "fatture_mese": 40, "costo_ai_mese": 1.234}, "https://app.oneflux.it/admin")
    assert t.splitlines() == [
        "☀️ Buongiorno. Oggi 2 cose da fare, 1 urgente.",
        "🔴 Trattoria: Ricavi fermi da 4 giorni",
        "🟠 3 descrizioni da classificare",
        "",
        "Ieri 12 fatture arrivate · 40 nel mese · costo AI del mese $ 1.23",
        "https://app.oneflux.it/admin",
    ]


def test_riepilogo_vuoto_e_lungo():
    assert att.testo_riepilogo([], {}, "u").splitlines()[0] == "☀️ Buongiorno. Oggi nell'admin non c'e' niente da fare."
    tante = [{"gravita": "oggi", "cliente": None, "titolo": f"v{i}"} for i in range(11)]
    righe = att.testo_riepilogo(tante, {}, "u").splitlines()
    assert righe[0] == "☀️ Buongiorno. Oggi 11 cose da fare."
    assert "… e altre 3" in righe
    assert sum(1 for r in righe if r.startswith("🟠")) == att.MAX_RIGHE_RIEPILOGO


# ─── L'endpoint del riepilogo: orario, una volta al giorno, forza ──────────

class _RPC:
    def __init__(self, risposta):
        self.risposta, self.chiamate = risposta, []

    def rpc(self, nome, parametri):
        self.chiamate.append((nome, parametri))
        risposta = self.risposta

        class _R:
            def execute(self_inner):
                return type("Res", (), {"data": risposta})()
        return _R()


def _endpoint(monkeypatch, *, ora_utc, risposta="invia", forza=False, telegram_ok=True):
    import services.fastapi_worker  # noqa: F401 — carica i moduli condivisi
    import services.routers.admin as admin
    import services.telegram_service as tg

    sb = _RPC(risposta)
    inviati = []
    monkeypatch.setattr(att, "adesso_roma", lambda: datetime(2026, 10, 13, ora_utc, 5, tzinfo=timezone.utc))
    monkeypatch.setattr(admin, "get_supabase_client", lambda *a, **k: sb)
    monkeypatch.setattr(admin, "_raccogli_attenzione", lambda _sb: {
        "voci": [{"gravita": "oggi", "cliente": None, "titolo": "3 descrizioni da classificare"}],
        "numeri": {"fatture_ieri": 2}, "_errors": []})
    monkeypatch.setattr(tg, "invia_messaggio", lambda testo, silenzioso=False: inviati.append((testo, silenzioso)) or telegram_ok)
    return admin.admin_riepilogo_telegram(forza=forza), sb, inviati


def test_fuori_orario_non_fa_niente(monkeypatch):
    esito, sb, inviati = _endpoint(monkeypatch, ora_utc=4)
    assert esito["inviato"] is False and esito["motivo"] == "fuori orario"
    assert sb.chiamate == [] and inviati == []


def test_alle_otto_manda_una_volta_silenzioso(monkeypatch):
    esito, sb, inviati = _endpoint(monkeypatch, ora_utc=6)
    assert esito["inviato"] is True
    assert sb.chiamate == [("admin_allarme_segnala", {"p_chiave": "riepilogo:2026-10-13", "p_gravita": "oggi", "p_problema": True})]
    assert len(inviati) == 1 and inviati[0][1] is True
    assert "3 descrizioni da classificare" in inviati[0][0]


def test_il_secondo_giro_della_mattina_non_lo_rimanda(monkeypatch):
    esito, _sb, inviati = _endpoint(monkeypatch, ora_utc=7, risposta="zitto")
    assert esito == {"inviato": False, "motivo": "gia' inviato oggi"}
    assert inviati == []


def test_forza_manda_anche_fuori_orario_senza_consumare_il_giorno(monkeypatch):
    esito, sb, inviati = _endpoint(monkeypatch, ora_utc=15, forza=True)
    assert esito["inviato"] is True and len(inviati) == 1
    assert sb.chiamate == []


def test_telegram_che_rifiuta_e_un_errore_e_libera_il_giorno(monkeypatch):
    """Il giorno e' segnato «inviato» prima dell'invio: se Telegram rifiuta lo
    si libera, cosi' il giro delle 07 UTC ci riprova invece di dire «gia' fatto»."""
    import pytest
    from fastapi import HTTPException
    import services.routers.admin as admin

    chiamate = []
    originale = _RPC.rpc

    def _rpc(self, nome, parametri):
        chiamate.append(parametri)
        return originale(self, nome, parametri)
    monkeypatch.setattr(_RPC, "rpc", _rpc)
    with pytest.raises(HTTPException) as e:
        _endpoint(monkeypatch, ora_utc=6, telegram_ok=False)
    assert e.value.status_code == 502
    assert [c["p_problema"] for c in chiamate] == [True, False]
    assert {c["p_chiave"] for c in chiamate} == {"riepilogo:2026-10-13"}
    del admin


def test_le_azioni_di_oggi_svuotano_la_lista_in_cache():
    import services.fastapi_worker  # noqa: F401
    import services.routers.admin as admin
    from fastapi.routing import APIRoute

    azioni = {
        ("POST", "/api/admin/fatture-queue/assegna-piva"), ("POST", "/api/admin/fatture-queue/riprova"),
        ("POST", "/api/admin/fatture-queue/assegna-sede"), ("POST", "/api/admin/ragione-sociale-map"),
        ("DELETE", "/api/admin/ragione-sociale-map/{mapping_id}"), ("PATCH", "/api/admin/marketplace/leads/{lead_id}"),
    }
    trovate = set()
    for r in admin.router.routes:
        if isinstance(r, APIRoute):
            for m in r.methods:
                if (m, r.path) in azioni and any(d.call is admin._dimentica_attenzione for d in r.dependant.dependencies):
                    trovate.add((m, r.path))
    assert trovate == azioni

    admin._ADMIN_CACHE.set("attenzione", {"voci": ["vecchia"]})
    dip = admin._dimentica_attenzione()
    next(dip)
    assert admin._ADMIN_CACHE.get("attenzione") is None


def test_una_fattura_senza_cliente_fallita_al_download_si_riprova_non_si_assegna():
    """Passo 0-bis (25/09/2026, prima in lib/coda-fatture.ts): «Assegna a…»
    aggiorna solo le righe unknown_tenant, su una riga failed/dead toccava 0
    righe e la fattura restava ferma. «Riprova» la fa riscaricare."""
    orfane = [_p(1, "failed"), _p(2, "dead"), _p(3, "unknown_tenant")]
    v = _per_chiave(_voci(fatture={"items": [], "orfane": orfane}))
    assert v["fattura:1"]["azione"]["tipo"] == "riprova"
    assert v["fattura:2"]["azione"]["tipo"] == "riprova"
    assert v["fattura:3"]["azione"]["tipo"] == "assegna_piva"


def test_negli_altri_stati_nessuna_voce():
    orfane = [_p(i, s) for i, s in enumerate(["pending", "processing", "done", "scartata", "", None], start=20)]
    assert not [v for v in _voci(fatture={"items": [], "orfane": orfane}) if v["chiave"].startswith("fattura:")]


def test_oggi_dice_quando_l_ultimo_caricamento_non_si_e_letto(monkeypatch):
    import services.fastapi_worker  # noqa: F401
    import services.routers.admin as admin

    cliente = {**CLIENTI[0], "salute_incompleta": True}
    monkeypatch.setattr(admin, "admin_lista_clienti", lambda: [cliente])
    for nome in ("admin_sistema_invoicetronic_salute", "admin_sistema_ricavi_salute", "admin_sistema_ricavi_import",
                 "_compute_admin_consumi", "_conta_categorie_da_controllare", "_richieste_nuove", "_conta_documenti"):
        monkeypatch.setattr(admin, nome, lambda *a, **k: (_ for _ in ()).throw(RuntimeError("giu'")))
    admin._ADMIN_CACHE.invalidate()

    class _SB:
        def table(self, _nome):
            raise RuntimeError("giu'")

    dati = admin._raccogli_attenzione(_SB())
    assert any("ultimo caricamento" in e for e in dati["_errors"])
    assert not [v for v in dati["voci"] if v["chiave"].startswith("attivazione:")]



def test_sdi_attivo_ma_muto_da_quattordici_giorni():
    def con_sedi(*sedi, **kw):
        c = {**CLIENTI[1], "sedi": list(sedi), **kw}
        return _per_chiave(att.componi_voci(adesso=ADESSO, clienti=[c]))
    muta = {"id": "r2", "nome_ristorante": "Bar 1", "sdi_attivo": True, "ultimo_caricamento_at": "2026-09-29T10:00:00+00:00"}
    v = con_sedi(muta)
    assert v["sdi:r2"]["titolo"] == "SDI attivo ma nessuna fattura da 14 giorni"
    assert v["sdi:r2"]["ristorante_id"] == "r2" and v["sdi:r2"]["link"] == "/admin/clienti/u2?tab=sedi"
    assert "sdi:r2" not in con_sedi({**muta, "ultimo_caricamento_at": "2026-09-30T10:00:00+00:00"})
    assert con_sedi({**muta, "ultimo_caricamento_at": None})["sdi:r2"]["titolo"] == "SDI attivo ma nessuna fattura mai arrivata"
    assert "sdi:r2" not in con_sedi({**muta, "sdi_attivo": False})
    assert "sdi:r2" not in con_sedi(muta, attivo=False)
    assert "sdi:r2" not in con_sedi(muta, salute_incompleta=True)


def test_le_voci_di_una_sede_portano_la_sede():
    ricavi = {"items": [{"ristorante_id": "r1", "stato": "critico", "giorni_silenzio": 4, "n_buchi": 0, "coda_problemi": 0}]}
    assert _per_chiave(_voci(ricavi=ricavi))["ricavi:r1"]["ristorante_id"] == "r1"
    consumi = {"mesi_avviso": ["2026-10"], "righe": [{"ristorante_id": "r1", "mese": "2026-10", "totale": 60, "limite": 50, "sopra_soglia": True}]}
    assert _per_chiave(_voci(consumi=consumi))["soglia:r1"]["ristorante_id"] == "r1"
    assert _per_chiave(_voci(n_categorie=2))["categorie"]["ristorante_id"] is None
