"""Email settimanale dell'assistente — la struttura (fase 7a, 24/09/2026).

Il contenuto lo studia Mattia a parte (7b): qui si prova la catena di montaggio,
e soprattutto cio' che IMPEDISCE un invio sbagliato:
- le tre sicure: `dry_run`, `EMAIL_SETTIMANALE_ATTIVA`, e il registro con UNIQUE
  (qui simulato; il vincolo vero e' provato su Postgres in
  test_sql_email_settimanale.py);
- chi la riceve e chi no (disiscritti, admin, inattivi, senza sedi);
- l'ora: lunedi' alle 7 di ROMA, nei due regimi CET/CEST, dove il calendario
  UTC e quello di Roma divergono;
- la disiscrizione firmata, fail-closed senza segreto;
- l'HTML che non si fida dei nomi.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Dict, List
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from services import email_settimanale_service as svc

ROMA = ZoneInfo("Europe/Rome")
UID = "11111111-1111-4111-8111-111111111111"
UID_B = "22222222-2222-4222-8222-222222222222"
SEGRETO = "segreto-di-prova"
LUNEDI_7 = datetime(2026, 9, 28, 7, 30, tzinfo=ROMA)


@pytest.fixture(autouse=True)
def segreto(monkeypatch):
    monkeypatch.setenv(svc.ENV_SEGRETO, SEGRETO)
    monkeypatch.delenv(svc.ENV_INVIO_ATTIVO, raising=False)


# ── Calendario ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("utc, atteso", [
    # estate (CEST, +2): 05:35 UTC = 07:35 a Roma, 06:35 UTC = 08:35 — entrambe dentro
    (datetime(2026, 9, 28, 5, 35, tzinfo=timezone.utc), True),
    (datetime(2026, 9, 28, 6, 35, tzinfo=timezone.utc), True),
    # inverno (CET, +1): 05:35 UTC = 06:35 a Roma (fuori), 06:35 UTC = 07:35
    (datetime(2026, 11, 2, 5, 35, tzinfo=timezone.utc), False),
    (datetime(2026, 11, 2, 6, 35, tzinfo=timezone.utc), True),
    # un cron in ritardo di due ore resta dentro (d'inverno: 08:50 UTC = 09:50)
    (datetime(2026, 11, 2, 8, 50, tzinfo=timezone.utc), True),
    (datetime(2026, 11, 2, 9, 5, tzinfo=timezone.utc), False),
])
def test_almeno_uno_dei_due_cron_lavora_in_entrambi_i_regimi(utc, atteso):
    """Il cron gira alle 05:35 e alle 06:35 UTC. La finestra e' sull'ora di
    ROMA: un controllo sull'ora UTC sbaglierebbe in uno dei due regimi. Quando
    lavorano entrambi, i doppi li ferma il registro (test piu' sotto)."""
    assert svc.e_ora_di_invio(utc.astimezone(ROMA)) is atteso


@pytest.mark.parametrize("adesso, atteso", [
    (datetime(2026, 9, 28, 7, 0, tzinfo=ROMA), True),
    (datetime(2026, 9, 28, 9, 59, tzinfo=ROMA), True),
    (datetime(2026, 9, 28, 6, 59, tzinfo=ROMA), False),
    (datetime(2026, 9, 28, 10, 0, tzinfo=ROMA), False),
    (datetime(2026, 9, 29, 7, 30, tzinfo=ROMA), False),   # martedi'
    (datetime(2026, 9, 27, 7, 30, tzinfo=ROMA), False),   # domenica
])
def test_solo_il_lunedi_dalle_7_alle_10(adesso, atteso):
    assert svc.e_ora_di_invio(adesso) is atteso


@pytest.mark.parametrize("giorno, lunedi", [
    (date(2026, 9, 28), date(2026, 9, 28)),
    (date(2026, 10, 4), date(2026, 9, 28)),
    (date(2026, 1, 1), date(2025, 12, 29)),
])
def test_la_settimana_e_il_suo_lunedi(giorno, lunedi):
    assert svc.lunedi_della_settimana(giorno) == lunedi


@pytest.mark.parametrize("valore, atteso", [("1", True), (" 1 ", True), ("", False),
                                            ("0", False), ("true", False), ("si", False)])
def test_l_invio_si_accende_solo_con_1(monkeypatch, valore, atteso):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, valore)
    assert svc.invio_attivo() is atteso


# ── Disiscrizione firmata ───────────────────────────────────────────────────

def test_il_token_giusto_passa():
    assert svc.verifica_token(UID, svc.token_disiscrizione(UID)) is True


def test_il_token_di_un_altro_utente_non_passa():
    assert svc.verifica_token(UID_B, svc.token_disiscrizione(UID)) is False


def test_un_token_alterato_non_passa():
    t = svc.token_disiscrizione(UID)
    alterato = ("0" if t[0] != "0" else "1") + t[1:]
    assert svc.verifica_token(UID, alterato) is False


def test_un_token_firmato_con_un_altro_segreto_non_passa(monkeypatch):
    t = svc.token_disiscrizione(UID)
    monkeypatch.setenv(svc.ENV_SEGRETO, "un-altro")
    assert svc.verifica_token(UID, t) is False


@pytest.mark.parametrize("uid, tok", [("", "x"), (UID, ""), (None, "x"), (UID, None),
                                      (UID, "è" * 64), (UID, "ﬀ")])
def test_id_o_token_vuoti_o_strani_non_passano(uid, tok):
    """Anche un token non ASCII: compare_digest su stringhe solleverebbe
    TypeError, cioe' un 500 invece di un «link non valido» (review del 24/09)."""
    assert svc.verifica_token(uid, tok) is False


def test_senza_segreto_non_si_firma_e_non_si_verifica(monkeypatch):
    t = svc.token_disiscrizione(UID)
    monkeypatch.delenv(svc.ENV_SEGRETO)
    with pytest.raises(RuntimeError):
        svc.token_disiscrizione(UID)
    assert svc.verifica_token(UID, t) is False


def test_i_due_link_portano_alla_pagina_e_all_api():
    pagina = svc.link_disiscrizione(UID)
    api = svc.link_disiscrizione(UID, api=True)
    assert pagina.startswith("https://app.oneflux.it/disiscrizione?")
    assert api.startswith("https://app.oneflux.it/api/email/disiscrizione?")
    for link in (pagina, api):
        assert f"u={UID}" in link and f"t={svc.token_disiscrizione(UID)}" in link


# ── Destinatari ─────────────────────────────────────────────────────────────

def _u(uid=UID, **kw):
    base = {"id": uid, "email": f"{uid[:4]}@cliente.it", "attivo": True, "ruolo": "cliente",
            "email_settimanale": True, "nome_referente": "Anna"}
    base.update(kw)
    return base


def _s(uid=UID, rid="r1", nome="Trattoria", **kw):
    base = {"id": rid, "user_id": uid, "nome_ristorante": nome, "attivo": True, "sede_tecnica": False}
    base.update(kw)
    return base


def _ids(dest):
    return [d.user_id for d in dest]


def test_il_cliente_attivo_con_una_sede_la_riceve():
    dest = svc.scegli_destinatari([_u()], [_s()])
    assert _ids(dest) == [UID]
    assert dest[0].nome == "Anna" and dest[0].sedi == [{"id": "r1", "nome": "Trattoria"}]


@pytest.mark.parametrize("utente, motivo", [
    (_u(email_settimanale=False), "disiscritto"),
    (_u(attivo=False), "account disattivato"),
    (_u(ruolo="admin"), "admin per ruolo"),
    (_u(email="MD@oneflux.it"), "admin per email, maiuscole comprese"),
    (_u(email=""), "senza email"),
])
def test_chi_non_la_riceve(utente, motivo):
    assert svc.scegli_destinatari([utente], [_s()]) == [], motivo


def test_preferenza_assente_vale_accesa():
    """Default della colonna: una riga senza il campo non e' una disiscrizione."""
    u = _u()
    del u["email_settimanale"]
    assert _ids(svc.scegli_destinatari([u], [_s()])) == [UID]


@pytest.mark.parametrize("sede", [_s(attivo=False), _s(sede_tecnica=True), _s(uid=UID_B)])
def test_senza_una_sede_vera_non_la_riceve(sede):
    assert svc.scegli_destinatari([_u()], [sede]) == []


def test_la_catena_riceve_una_email_con_tutte_le_sue_sedi():
    dest = svc.scegli_destinatari(
        [_u(nome_referente=None, nome_gruppo="Gruppo Sushi")],
        [_s(rid="r2", nome="Zeta"), _s(rid="r1", nome="Alfa"), _s(rid="r3", nome="Tecnica", sede_tecnica=True)],
    )
    assert len(dest) == 1
    assert dest[0].nome == "Gruppo Sushi"
    assert [s["nome"] for s in dest[0].sedi] == ["Alfa", "Zeta"]


# ── Sezioni e composizione ──────────────────────────────────────────────────

def _dest(nome="Anna", sedi=None):
    return svc.Destinatario(user_id=UID, email="anna@cliente.it", nome=nome,
                            sedi=sedi if sedi is not None else [{"id": "r1", "nome": "Trattoria"}])


def test_una_sezione_che_fallisce_tace_e_le_altre_parlano():
    def rotta(d, g):
        raise RuntimeError("giu'")

    frasi = svc.calcola_frasi(_dest(), date(2026, 9, 28),
                              [rotta, lambda d, g: "  prima  ", lambda d, g: "", lambda d, g: None])
    assert frasi == ["prima"]


def test_il_segnaposto_parla_solo_se_ci_sono_sedi_con_un_nome():
    assert svc._sezione_segnaposto(_dest(sedi=[{"id": "r1", "nome": ""}]), date(2026, 9, 28)) is None
    assert "Trattoria" in svc._sezione_segnaposto(_dest(), date(2026, 9, 28))


def test_l_html_non_si_fida_di_nomi_e_frasi():
    email = svc.componi_email(_dest(nome="<b>Anna</b>"), ["Sede <script>x</script>"])
    assert "<script>" not in email["html"] and "&lt;script&gt;" in email["html"]
    assert "<b>Anna</b>" not in email["html"] and "&lt;b&gt;Anna&lt;/b&gt;" in email["html"]


def test_ogni_email_porta_la_disiscrizione_nel_testo_e_nelle_intestazioni():
    email = svc.componi_email(_dest(), ["Una frase."])
    token = svc.token_disiscrizione(UID)
    assert token in email["html"] and token in email["testo"]
    assert email["headers"]["List-Unsubscribe"] == f"<{svc.link_disiscrizione(UID, api=True)}>"
    assert email["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "https://app.oneflux.it/dashboard" in email["html"]
    assert "Una frase." in email["testo"]


# ── Cosa arriva davvero a Brevo ─────────────────────────────────────────────

def _payload_brevo(monkeypatch, **kw):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from services import email_service
    monkeypatch.setenv("BREVO_API_KEY", "k")
    post = MagicMock(return_value=SimpleNamespace(status_code=201, text=""))
    monkeypatch.setattr("requests.post", post)
    assert email_service.brevo_send("a@b.it", "Anna", "Oggetto", "<p>x</p>", **kw) is True
    return post.call_args.kwargs["json"]


def test_intestazioni_e_testo_arrivano_a_brevo(monkeypatch):
    """I test del lavoro fingono `brevo_send`: senza questo, un `brevo_send`
    che dimentica le intestazioni lasciava partire email senza la
    disiscrizione con un clic (mutante sopravvissuto il 24/09)."""
    email = svc.componi_email(_dest(), ["Una frase."])
    payload = _payload_brevo(monkeypatch, headers=email["headers"], text_body=email["testo"])
    assert payload["headers"] == email["headers"]
    assert payload["textContent"] == email["testo"]


def test_le_email_di_prima_restano_come_erano(monkeypatch):
    """Onboarding e reset non passano intestazioni ne' testo: il payload deve
    restare quello di sempre."""
    payload = _payload_brevo(monkeypatch)
    assert "headers" not in payload and "textContent" not in payload


# ── Il lavoro del lunedi': le sicure ────────────────────────────────────────

class _Q:
    def __init__(self, sb, tabella):
        self.sb, self.tabella, self.filtri, self._op, self._dati = sb, tabella, {}, "select", None

    def select(self, *_a, **_k):
        return self

    def eq(self, col, val):
        self.filtri[col] = val
        return self

    def in_(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def range(self, *_a):
        return self

    def limit(self, *_a):
        return self

    def insert(self, dati):
        self._op, self._dati = "insert", dati
        return self

    def update(self, dati):
        self._op, self._dati = "update", dati
        return self

    def execute(self):
        sb = self.sb
        if self._op == "insert":
            chiave = (self._dati["user_id"], self._dati["settimana"])
            if chiave in sb.registro:
                raise Exception('duplicate key value violates unique constraint (23505)')
            sb.registro[chiave] = dict(self._dati)
            sb.scritture.append(("insert", self.tabella, dict(self._dati)))
            return type("R", (), {"data": [self._dati]})()
        if self._op == "update":
            sb.scritture.append(("update", self.tabella, dict(self._dati), dict(self.filtri)))
            if self.tabella == "email_settimanale_invii":
                chiave = (self.filtri["user_id"], self.filtri["settimana"])
                sb.registro[chiave].update(self._dati)
            return type("R", (), {"data": []})()
        righe = sb.utenti if self.tabella == "users" else sb.sedi
        if "id" in self.filtri:
            righe = [r for r in righe if r["id"] == self.filtri["id"]]
        return type("R", (), {"data": righe})()


class _SB:
    def __init__(self, utenti, sedi):
        self.utenti, self.sedi = utenti, sedi
        self.registro: Dict[tuple, Dict[str, Any]] = {}
        self.scritture: List[tuple] = []

    def table(self, nome):
        return _Q(self, nome)


@pytest.fixture
def invii(monkeypatch):
    chiamate = []

    def _finto(to_email, to_name, subject, html_body, **kw):
        chiamate.append({"to": to_email, "subject": subject, **kw})
        return True

    monkeypatch.setattr("services.email_service.brevo_send", _finto)
    return chiamate


def _sb():
    return _SB([_u(), _u(UID_B, email="b@cliente.it")],
               [_s(), _s(uid=UID_B, rid="r9", nome="Osteria")])


def test_dry_run_non_spedisce_e_non_scrive_nulla(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=True)
    assert invii == [] and sb.scritture == []
    assert r["composte"] == 2 and r["inviate"] == 0


def test_invio_spento_non_spedisce_non_scrive_e_non_compone(invii, monkeypatch):
    """Con dry_run=false (come chiama il cron) e la variabile spenta: nulla.
    Nemmeno il registro, o la prova occuperebbe la settimana dell'invio vero; e
    nemmeno la composizione, che senza il segreto della disiscrizione (arriva in
    7c) conterebbe errori e farebbe scattare l'avviso Telegram ogni lunedi'."""
    monkeypatch.delenv(svc.ENV_SEGRETO)
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    assert invii == [] and sb.scritture == []
    assert r["invio_attivo"] is False and r["motivo"] == "invio spento"
    assert r["composte"] == 0 and r["errori"] == 0 and r["destinatari"] == 0


def test_invio_acceso_spedisce_una_email_a_testa_e_la_registra(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    assert sorted(c["to"] for c in invii) == ["1111@cliente.it", "b@cliente.it"]
    assert all(c["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click" for c in invii)
    assert r["inviate"] == 2
    assert {k: v["stato"] for k, v in sb.registro.items()} == {
        (UID, "2026-09-28"): "inviata", (UID_B, "2026-09-28"): "inviata",
    }


def test_il_secondo_giro_della_stessa_settimana_non_rispedisce(monkeypatch, invii):
    """Il cron gira due volte il lunedi' (e puo' essere lanciato a mano): il
    registro fa si' che la seconda volta nessuno riceva niente."""
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    invii.clear()
    r = svc.esegui(sb, adesso=datetime(2026, 10, 1, 9, 0, tzinfo=ROMA), dry_run=False)
    assert invii == []
    assert r["gia_gestite"] == 2 and r["inviate"] == 0


def test_la_settimana_dopo_si_riparte(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    invii.clear()
    svc.esegui(sb, adesso=datetime(2026, 10, 5, 7, 30, tzinfo=ROMA), dry_run=False)
    assert len(invii) == 2


def test_niente_da_dire_non_spedisce_e_occupa_la_settimana(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False, sezioni=[lambda d, g: None])
    assert invii == []
    assert r["niente_da_dire"] == 2
    assert {v["stato"] for v in sb.registro.values()} == {"saltata"}


def test_brevo_che_rifiuta_diventa_errore(monkeypatch):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    monkeypatch.setattr("services.email_service.brevo_send", lambda *a, **k: False)
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    assert r["errori"] == 2 and r["inviate"] == 0
    assert {v["stato"] for v in sb.registro.values()} == {"errore"}


def test_senza_segreto_nessuna_email_parte_senza_disiscrizione(monkeypatch, invii):
    """Un'email periodica senza il link per smettere di riceverla non deve
    partire: la composizione fallisce PRIMA di prendere la settimana."""
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    monkeypatch.delenv(svc.ENV_SEGRETO)
    sb = _sb()
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    assert invii == [] and sb.registro == {}
    assert r["errori"] == 2


def test_un_errore_del_registro_ferma_solo_quel_cliente(monkeypatch, invii):
    """Un errore del registro diverso dal duplicato: quel cliente salta la
    settimana (nessun invio senza la riga), gli altri ricevono la loro."""
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    sb = _sb()
    vero = svc._prendi_la_settimana

    def _rotto_per_uno(sb_, user_id, *a, **k):
        if user_id == UID:
            raise RuntimeError("timeout PostgREST")
        return vero(sb_, user_id, *a, **k)

    monkeypatch.setattr(svc, "_prendi_la_settimana", _rotto_per_uno)
    r = svc.esegui(sb, adesso=LUNEDI_7, dry_run=False)
    assert [c["to"] for c in invii] == ["b@cliente.it"]
    assert r["errori"] == 1 and r["inviate"] == 1


def test_un_errore_del_registro_senza_niente_da_dire_non_ferma_gli_altri(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    chiamate = []

    def _rotto_per_uno(sb_, user_id, *a, **k):
        chiamate.append(user_id)
        if user_id == UID:
            raise RuntimeError("timeout PostgREST")
        return True

    monkeypatch.setattr(svc, "_prendi_la_settimana", _rotto_per_uno)
    r = svc.esegui(_sb(), adesso=LUNEDI_7, dry_run=False, sezioni=[lambda d, g: None])
    assert sorted(chiamate) == sorted([UID, UID_B])
    assert r["errori"] == 1 and r["niente_da_dire"] == 1 and invii == []


def test_solo_un_utente(monkeypatch, invii):
    monkeypatch.setenv(svc.ENV_INVIO_ATTIVO, "1")
    svc.esegui(_sb(), adesso=LUNEDI_7, dry_run=False, solo_user_id=UID_B)
    assert [c["to"] for c in invii] == ["b@cliente.it"]


def test_la_disiscrizione_spegne_solo_col_token_giusto():
    sb = _sb()
    assert svc.disiscrivi(sb, UID, "sbagliato") is False
    assert sb.scritture == []
    assert svc.disiscrivi(sb, UID, svc.token_disiscrizione(UID)) is True
    assert sb.scritture == [("update", "users", {"email_settimanale": False}, {"id": UID})]


def test_anteprima_senza_segreto_lo_dice_invece_di_rompersi(monkeypatch, invii):
    """Lo strumento della 7b non deve rispondere 500 se il segreto non c'e'
    (review del 24/09): dice perche' l'email non si comporrebbe."""
    monkeypatch.delenv(svc.ENV_SEGRETO)
    a = svc.anteprima(_sb(), UID, adesso=LUNEDI_7)
    assert a["riceverebbe"] is False and svc.ENV_SEGRETO in a["motivo"]
    assert a["frasi"] and invii == []


def test_anteprima_admin_rifiuta_un_id_che_non_e_un_uuid(monkeypatch):
    from fastapi import HTTPException
    from services.routers import admin
    monkeypatch.setattr(admin, "get_supabase_client", lambda: _sb())
    with pytest.raises(HTTPException) as e:
        admin.admin_email_settimanale_anteprima("non-un-uuid")
    assert e.value.status_code == 400
    assert admin.admin_email_settimanale_anteprima(UID)["riceverebbe"] is True


def test_anteprima_non_scrive_e_non_spedisce(invii):
    sb = _sb()
    a = svc.anteprima(sb, UID, adesso=LUNEDI_7)
    assert a["riceverebbe"] is True and "Trattoria" in a["frasi"][0]
    assert invii == [] and sb.scritture == []
    assert svc.anteprima(_SB([_u(email_settimanale=False)], [_s()]), UID, adesso=LUNEDI_7)["riceverebbe"] is False


# ── Gli ingressi HTTP ───────────────────────────────────────────────────────

def test_endpoint_fuori_orario_non_lavora(monkeypatch):
    from services.routers import email_settimanale as rt
    chiamate = []
    monkeypatch.setattr(rt.svc, "adesso_roma", lambda: datetime(2026, 9, 29, 7, 30, tzinfo=ROMA))
    monkeypatch.setattr(rt.svc, "esegui", lambda *a, **k: chiamate.append(k) or {})
    r = rt.email_settimanale_esegui(dry_run=False)
    assert r["eseguito"] is False and chiamate == []


def test_endpoint_all_ora_giusta_lavora_e_passa_i_parametri(monkeypatch):
    from services.routers import email_settimanale as rt
    chiamate = []
    monkeypatch.setattr(rt.svc, "adesso_roma", lambda: LUNEDI_7)
    monkeypatch.setattr(rt, "_get_supabase_client", lambda: "sb")
    monkeypatch.setattr(rt.svc, "esegui", lambda sb, **k: chiamate.append((sb, k)) or {"inviate": 0})
    r = rt.email_settimanale_esegui(dry_run=False, solo_user_id=UID)
    assert r["eseguito"] is True
    assert chiamate == [("sb", {"adesso": LUNEDI_7, "dry_run": False, "solo_user_id": UID})]


def test_endpoint_dry_run_e_il_default(monkeypatch):
    import inspect
    from services.routers import email_settimanale as rt
    assert inspect.signature(rt.email_settimanale_esegui).parameters["dry_run"].default is True


def test_endpoint_forza_scavalca_solo_l_ora(monkeypatch):
    from services.routers import email_settimanale as rt
    chiamate = []
    monkeypatch.setattr(rt.svc, "adesso_roma", lambda: datetime(2026, 9, 29, 15, 0, tzinfo=ROMA))
    monkeypatch.setattr(rt, "_get_supabase_client", lambda: "sb")
    monkeypatch.setattr(rt.svc, "esegui", lambda sb, **k: chiamate.append(k) or {})
    assert rt.email_settimanale_esegui(forza=True)["eseguito"] is True
    assert chiamate[0]["dry_run"] is True


def test_endpoint_disiscrizione_con_token_sbagliato_risponde_400(monkeypatch):
    from fastapi import HTTPException
    from services.routers import email_settimanale as rt
    sb = _sb()
    monkeypatch.setattr(rt, "_get_supabase_client", lambda: sb)
    with pytest.raises(HTTPException) as e:
        rt.email_disiscrizione(rt.DisiscrizioneBody(u=UID, t="no"))
    assert e.value.status_code == 400 and sb.scritture == []
    assert rt.email_disiscrizione(rt.DisiscrizioneBody(u=f" {UID} ", t=svc.token_disiscrizione(UID))) == {"ok": True}


def test_i_tre_ingressi_sono_montati_e_dietro_le_guardie():
    import services.fastapi_worker as fw
    from services.routers import admin, email_settimanale as rt
    rotte = {r.path: r for r in fw.app.routes if hasattr(r, "path")}
    for p in ("/api/interno/email-settimanale", "/api/email/disiscrizione",
              "/api/admin/email-settimanale/anteprima"):
        assert p in rotte, p
    dip = lambda r: {d.call for d in r.dependant.dependencies}  # noqa: E731
    assert rt._verify_worker_key in dip(rotte["/api/interno/email-settimanale"])
    assert rt._verify_worker_key in dip(rotte["/api/email/disiscrizione"])
    assert admin._verify_admin in dip(rotte["/api/admin/email-settimanale/anteprima"])


# ── La preferenza nelle Impostazioni ────────────────────────────────────────

def test_la_preferenza_si_salva_dalle_impostazioni(monkeypatch):
    from services.routers import account
    scritture = []

    class _T:
        def update(self, d):
            scritture.append(d)
            return self

        def eq(self, *a):
            return self

        def execute(self):
            return None

    monkeypatch.setattr(account, "_resolve_user_from_token", lambda a: {"id": UID})
    monkeypatch.setattr(account, "_get_supabase_client", lambda: type("S", (), {"table": lambda s, n: _T()})())
    r = account.account_preferenze(account.PreferenzeBody(email_settimanale=False), authorization="Bearer x")
    assert r == {"ok": True, "email_settimanale": False}
    assert scritture == [{"email_settimanale": False}]
    account.account_preferenze(account.PreferenzeBody(email_settimanale=True), authorization="Bearer x")
    assert scritture[-1] == {"email_settimanale": True}
