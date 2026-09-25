"""Configurazione e registro dell'invio al commercialista, su un Postgres vero (fase B).

E' il DATABASE a impedire i doppioni al commercialista e l'invio a un indirizzo
non autorizzato: qui si prova che la migration li impedisca davvero, uno per uno.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.sql

MIGRATION = next(
    (Path(__file__).resolve().parents[1] / "supabase" / "migrations").glob("*_invio_commercialista.sql")
)
U1 = "1c0c0000-0000-4000-8000-000000000001"
U2 = "1c0c0000-0000-4000-8000-000000000002"
SEDE_1 = "1c0c0000-0000-4000-8000-0000000000a1"
SEDE_2 = "1c0c0000-0000-4000-8000-0000000000a2"
PIVA = "07863990961"
EMAIL = "studio@commercialista.test"
ORA = "2026-09-25 10:00:00+00"


@pytest.fixture
def psycopg():
    return pytest.importorskip("psycopg")


def _esegui(db_sql, sql, *params):
    # Un savepoint per istruzione: dopo un rifiuto atteso il test continua. La
    # transazione esterna va aperta prima: senza, transaction() ne apre una vera
    # e la COMMITTA, e le righe sopravvivono al rollback della fixture.
    psycopg = pytest.importorskip("psycopg")
    if db_sql.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
        db_sql.execute("SELECT 1")
    with db_sql.transaction(), db_sql.cursor() as cur:
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        return cur.fetchall() if cur.description else None


def _semina(db_sql, altra_sede_stessa_piva=False):
    for uid, email in ((U1, "u1@ic.test"), (U2, "u2@ic.test")):
        _esegui(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    _esegui(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'A', %s, TRUE)", SEDE_1, U1, PIVA)
    if altra_sede_stessa_piva:
        _esegui(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, PIVA)


def _config(db_sql, attiva=True, email=EMAIL, consenso_email=None, company=1756, piva=PIVA, user=U1):
    righe = _esegui(
        db_sql,
        "INSERT INTO public.invio_commercialista_config (user_id, piva, invoicetronic_company_id, email_destinatario, "
        "frequenza, data_partenza, attivo, consenso_ricevuto, consenso_data, consenso_email) "
        "VALUES (%s, %s, %s, %s, 'mensile', '2026-07-01', %s, %s, %s, %s) RETURNING id",
        user, piva, company, email, attiva, attiva, '2026-09-20' if attiva else None,
        (consenso_email if consenso_email is not None else email) if attiva else None,
    )
    return righe[0][0]


def _invio(db_sql, cid, tipo, dal, al, stato="richiesto", da="admin", creata=ORA, destinatario=EMAIL,
           user=U1, piva=PIVA, company=1756, **extra):
    colonne = ["config_id", "user_id", "piva", "invoicetronic_company_id", "destinatario", "tipo",
               "periodo_dal", "periodo_al", "stato", "richiesto_da", "creata_at", *extra]
    valori = [cid, user, piva, company, destinatario, tipo, dal, al, stato, da, creata, *extra.values()]
    righe = _esegui(
        db_sql,
        f"INSERT INTO public.invio_commercialista_invii ({', '.join(colonne)}) VALUES ({', '.join(['%s'] * len(valori))}) RETURNING id",
        *valori,
    )
    return righe[0][0]


def _stato(db_sql, iid, stato, **extra):
    campi = ", ".join(["stato = %s", *[f"{k} = %s" for k in extra]])
    _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campi} WHERE id = %s", stato, *extra.values(), iid)


TENTATA = "2026-09-25 10:05:00+00"


def _inviato(db_sql, cid, tipo, dal, al):
    iid = _invio(db_sql, cid, tipo, dal, al)
    _stato(db_sql, iid, "in_corso", email_tentata_at=TENTATA)
    _stato(db_sql, iid, "inviato")
    return iid


# ─── Configurazione ──────────────────────────────────────────────────────────

def test_una_configurazione_completa_si_attiva(db_sql, scalare):
    _semina(db_sql)
    _config(db_sql)
    assert scalare("SELECT attivo FROM public.invio_commercialista_config") is True


@pytest.mark.parametrize("campo", ["consenso_ricevuto", "consenso_data", "invoicetronic_company_id", "data_partenza"])
def test_senza_un_requisito_non_si_attiva(db_sql, psycopg, campo):
    _semina(db_sql)
    cid = _config(db_sql)
    valore = "false" if campo == "consenso_ricevuto" else "NULL"
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, f"UPDATE public.invio_commercialista_config SET {campo} = {valore} WHERE id = %s", cid)


def test_il_consenso_vale_per_l_email_per_cui_e_stato_dato(db_sql, psycopg):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql, consenso_email="altro@studio.test")


def test_cambiare_email_toglie_consenso_e_attivazione(db_sql):
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET email_destinatario = 'nuovo@studio.test' WHERE id = %s", cid)
    riga = _esegui(db_sql, "SELECT attivo, consenso_ricevuto, consenso_data, consenso_email, disattivata_at IS NOT NULL "
                           "FROM public.invio_commercialista_config WHERE id = %s", cid)[0]
    assert riga == (False, False, None, None, True)


@pytest.mark.parametrize("email", ["Studio@Commercialista.test", " studio@commercialista.test", "senza-chiocciola", "a@b"])
def test_email_normalizzata_e_plausibile(db_sql, psycopg, email):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql, attiva=False, email=email)


def test_piva_di_un_altro_cliente_rifiutata(db_sql, psycopg):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql, user=U2)


def test_piva_anche_di_un_altro_account_rifiutata(db_sql, psycopg):
    _semina(db_sql, altra_sede_stessa_piva=True)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql)


def test_piva_rimasta_su_piva_ristoranti_di_un_altro_account_rifiutata(db_sql, psycopg):
    """piva_ristoranti non segue lo spostamento di una sede: il controllo guarda
    anche li'."""
    _semina(db_sql)
    _esegui(db_sql, "INSERT INTO public.piva_ristoranti (user_id, ristorante_id, piva, nome_ristorante) VALUES (%s, %s, %s, 'vecchia')",
            U2, SEDE_1, PIVA)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql)


def test_una_configurazione_attiva_si_spegne_anche_se_la_piva_ora_e_condivisa(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, PIVA)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    assert scalare("SELECT attivo FROM public.invio_commercialista_config WHERE id = %s", cid) is False


@pytest.mark.parametrize("campo,valore", [("piva", "'12345678903'"), ("user_id", f"'{U2}'"), ("invoicetronic_company_id", "99")])
def test_cliente_piva_e_company_non_cambiano(db_sql, psycopg, campo, valore):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, f"UPDATE public.invio_commercialista_config SET {campo} = {valore} WHERE id = %s", cid)


def test_il_company_id_si_scrive_una_volta(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql, attiva=False, company=None)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET invoicetronic_company_id = 1756 WHERE id = %s", cid)
    assert scalare("SELECT invoicetronic_company_id FROM public.invio_commercialista_config WHERE id = %s", cid) == 1756


def test_una_sola_configurazione_per_piva(db_sql, psycopg):
    _semina(db_sql)
    _config(db_sql)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _config(db_sql, attiva=False, company=None)


# ─── Registro: doppioni impossibili ──────────────────────────────────────────

def test_il_tipo_e_obbligatorio(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.NotNullViolation):
        _invio(db_sql, cid, None, "2026-07-01", "2026-07-31")


def test_un_solo_invio_in_volo(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _invio(db_sql, cid, "prova", "2026-08-01", "2026-08-31")


def test_un_esito_incerto_blocca_nuovi_invii(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    _stato(db_sql, iid, "esito_incerto", email_tentata_at="2026-09-25 10:05:00+00")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _invio(db_sql, cid, "prova", "2026-08-01", "2026-08-31")


def test_un_solo_primo_riuscito_anche_con_date_diverse(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _invio(db_sql, cid, "primo", "2026-08-01", "2026-08-31")


def test_dopo_un_errore_il_primo_si_ritenta(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "errore", motivo="download fallito")
    _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii WHERE tipo = 'primo'") == 2


def test_ordinario_solo_dopo_un_primo_riuscito(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "ordinario", "2026-08-01", "2026-08-31", da="notturno")


def test_ordinario_riparte_dal_giorno_dopo_l_ultimo_inviato(db_sql, psycopg, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    for dal in ("2026-08-02", "2026-07-31"):
        with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.ExclusionViolation)):
            _invio(db_sql, cid, "ordinario", dal, "2026-08-31", da="notturno")
    _invio(db_sql, cid, "ordinario", "2026-08-01", "2026-08-31", da="notturno")
    assert scalare("SELECT public.invio_commercialista_ultimo_giorno(%s)", cid).isoformat() == "2026-07-31"


def test_periodi_sovrapposti_rifiutati(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    with pytest.raises((psycopg.errors.UniqueViolation, psycopg.errors.ExclusionViolation)):
        _invio(db_sql, cid, "primo", "2026-07-15", "2026-08-15")
    with pytest.raises(psycopg.errors.ExclusionViolation):
        _esegui(db_sql, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                        "destinatario, tipo, periodo_dal, periodo_al, stato, richiesto_da, creata_at) VALUES "
                        "(%s, %s, %s, 1756, %s, 'primo', '2026-07-15', '2026-08-15', 'errore', 'admin', %s)",
                cid, U1, PIVA, EMAIL, ORA)


def test_il_reinvio_resta_dentro_il_gia_inviato(db_sql, psycopg, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "reinvio", "2026-07-15", "2026-08-05")
    iid = _invio(db_sql, cid, "reinvio", "2026-07-10", "2026-07-20")
    _stato(db_sql, iid, "in_corso", email_tentata_at=TENTATA)
    _stato(db_sql, iid, "inviato")
    assert scalare("SELECT public.invio_commercialista_ultimo_giorno(%s)", cid).isoformat() == "2026-07-31", \
        "il reinvio non sposta il cursore"


def test_le_prove_non_spostano_il_cursore(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "prova", "2026-07-01", "2026-09-20")
    _stato(db_sql, iid, "in_corso")
    _stato(db_sql, iid, "prova_ok")
    assert scalare("SELECT public.invio_commercialista_ultimo_giorno(%s)", cid) is None


# ─── Registro: date ──────────────────────────────────────────────────────────

def test_mai_un_periodo_che_arriva_a_oggi_a_roma(db_sql, psycopg, scalare):
    """Il 31/12 alle 23:30 UTC a Roma e' gia' il 1° gennaio: il periodo puo'
    arrivare al 31/12, non al 1/1. (Il 2025: creata_at nel futuro e' rifiutata.)"""
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "prova", "2025-12-01", "2026-01-01", creata="2025-12-31 23:30:00+00")
    _invio(db_sql, cid, "prova", "2025-12-01", "2025-12-31", creata="2025-12-31 23:30:00+00")
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii") == 1


def test_mai_oltre_i_due_anni(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "prova", "2024-09-24", "2024-09-30")
    _invio(db_sql, cid, "prova", "2024-09-25", "2024-09-30")


# ─── Registro: stati ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("da,a", [("richiesto", "inviato"), ("richiesto", "prova_ok"), ("inviato", "richiesto"),
                                  ("inviato", "errore"), ("errore", "in_corso"), ("bloccato", "in_corso")])
def test_transizioni_vietate(db_sql, psycopg, da, a):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    percorso = {"richiesto": [], "inviato": ["in_corso", "inviato"], "errore": ["errore"], "bloccato": ["in_corso", "bloccato"]}[da]
    for passo in percorso:
        _stato(db_sql, iid, passo, **({"email_tentata_at": TENTATA} if (da, passo) == ("inviato", "in_corso") else {}))
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, a)


def test_esito_incerto_si_chiarisce(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    _stato(db_sql, iid, "esito_incerto", email_tentata_at="2026-09-25 10:05:00+00")
    _stato(db_sql, iid, "inviato")
    assert scalare("SELECT public.invio_commercialista_ultimo_giorno(%s)", cid).isoformat() == "2026-07-31"


def test_email_partita_non_diventa_errore_senza_un_rifiuto_certo(db_sql, psycopg, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso", email_tentata_at="2026-09-25 10:05:00+00")
    for status in (None, 500, 201):
        with pytest.raises(psycopg.errors.CheckViolation):
            _stato(db_sql, iid, "errore", brevo_http_status=status)
    _stato(db_sql, iid, "errore", brevo_http_status=400)
    assert scalare("SELECT stato FROM public.invio_commercialista_invii WHERE id = %s", iid) == "errore"


def test_una_prova_non_diventa_mai_inviata(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "inviato")


def test_prova_ok_solo_per_le_prove(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "prova_ok")


@pytest.mark.parametrize("tipo", ["primo", "reinvio", "prova"])
def test_il_notturno_fa_solo_ordinari(db_sql, psycopg, tipo):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, tipo, "2026-07-01", "2026-07-31", da="notturno")


@pytest.mark.parametrize("campo,valore", [("periodo_dal", "'2026-06-30'"), ("destinatario", "'altro@x.test'"),
                                          ("invoicetronic_company_id", "99"), ("creata_at", "now()"),
                                          ("tipo", "'reinvio'"), ("user_id", f"'{U2}'")])
def test_un_invio_registrato_non_cambia(db_sql, psycopg, campo, valore):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campo} = {valore} WHERE id = %s", iid)


# ─── Retention, cancellazione, permessi, bucket ──────────────────────────────

def test_la_pulizia_toglie_le_email_vecchie_e_lascia_le_recenti(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    vecchio = _invio(db_sql, cid, "prova", "2025-05-01", "2025-05-31", creata="2025-06-01 10:00:00+00")
    _stato(db_sql, vecchio, "in_corso")
    _stato(db_sql, vecchio, "prova_ok")
    recente = _invio(db_sql, cid, "prova", "2026-08-01", "2026-08-31")
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 1
    assert scalare("SELECT destinatario FROM public.invio_commercialista_invii WHERE id = %s", vecchio) is None
    assert scalare("SELECT destinatario FROM public.invio_commercialista_invii WHERE id = %s", recente) == EMAIL


def test_la_pulizia_toglie_l_email_delle_configurazioni_spente_da_tempo(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 0, "spenta da poco: resta"
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET disattivata_at = now() - interval '91 days' WHERE id = %s", cid)
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 1
    assert _esegui(db_sql, "SELECT email_destinatario, consenso_email FROM public.invio_commercialista_config WHERE id = %s", cid)[0] == (None, None)


def test_la_pulizia_non_scende_sotto_i_30_giorni(db_sql, psycopg):
    with pytest.raises(psycopg.errors.RaiseException):
        _esegui(db_sql, "SELECT public.purge_invio_commercialista(10, 90)")


def test_cancellare_la_configurazione_lascia_la_traccia_fino_alla_pulizia(db_sql, scalare):
    """Il registro resta (senza configurazione) come traccia di cosa e' andato a
    chi, fino alla retention: serve per riassegnare una P.IVA a un altro account."""
    _semina(db_sql)
    cid = _config(db_sql)
    recente = _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    vecchio = _invio(db_sql, cid, "prova", "2025-05-01", "2025-05-31", stato="errore", creata="2025-06-01 10:00:00+00")
    _esegui(db_sql, "DELETE FROM public.invio_commercialista_config WHERE id = %s", cid)
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii WHERE config_id IS NULL") == 2
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 1
    assert [r[0] for r in _esegui(db_sql, "SELECT id FROM public.invio_commercialista_invii")] == [recente]
    assert vecchio != recente


def test_cancellare_l_account_cancella_configurazione_e_registro(db_sql, scalare):
    """La privacy promette l'eliminazione a cascata di tutto alla cancellazione
    dell'account: vale anche per la traccia degli invii."""
    _semina(db_sql)
    cid = _config(db_sql)
    _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    _esegui(db_sql, "DELETE FROM public.ristoranti WHERE user_id = %s", U1)
    _esegui(db_sql, "DELETE FROM public.users WHERE id = %s", U1)
    assert scalare("SELECT count(*) FROM public.invio_commercialista_config") == 0
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii") == 0


def test_senza_configurazione_non_si_registra_niente(db_sql, psycopg):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, None, "prova", "2026-07-01", "2026-07-31")


@pytest.mark.parametrize("tabella", ["invio_commercialista_config", "invio_commercialista_invii"])
@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_toccano_le_tabelle(db_sql, scalare, ruolo, tabella):
    if not scalare("SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo):
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    _esegui(db_sql, f"GRANT ALL ON public.{tabella} TO {ruolo}")
    assert scalare(f"SELECT has_table_privilege(%s, 'public.{tabella}', 'SELECT')", ruolo) is True
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    for permesso in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert scalare(f"SELECT has_table_privilege(%s, 'public.{tabella}', %s)", ruolo, permesso) is False, permesso


@pytest.mark.parametrize("funzione", ["purge_invio_commercialista(integer, integer)",
                                      "invio_commercialista_autorizzato(uuid, text)",
                                      "invio_commercialista_ultimo_giorno(uuid)"])
@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_eseguono_le_funzioni(db_sql, scalare, ruolo, funzione):
    if not scalare("SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo):
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    _esegui(db_sql, f"GRANT EXECUTE ON FUNCTION public.{funzione} TO {ruolo}")
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    assert scalare(f"SELECT has_function_privilege(%s, 'public.{funzione}', 'EXECUTE')", ruolo) is False


def test_un_bucket_gia_pubblico_torna_privato(db_sql, scalare):
    """Il bucket puo' esistere gia' (ricavi-xls e' nato a mano): la migration lo
    riporta privato. Lo schema storage qui e' finto e vive nella transazione."""
    _esegui(db_sql, "CREATE SCHEMA IF NOT EXISTS storage")
    _esegui(db_sql, "CREATE TABLE storage.buckets (id text PRIMARY KEY, name text, public boolean, "
                    "file_size_limit bigint, allowed_mime_types text[])")
    _esegui(db_sql, "INSERT INTO storage.buckets VALUES ('invii-commercialista', 'invii-commercialista', true, NULL, NULL)")
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    assert _esegui(db_sql, "SELECT public, file_size_limit, allowed_mime_types FROM storage.buckets")[0] == \
        (False, 52428800, ["application/zip"])


def test_la_migration_e_rieseguibile(db_sql, scalare):
    _semina(db_sql)
    _config(db_sql)
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    assert scalare("SELECT count(*) FROM public.invio_commercialista_config") == 1


def test_il_worker_la_chiama_col_suo_parametro(db_sql, scalare, monkeypatch):
    """Il giro giornaliero chiama ogni pulizia con {"p_retention_days": giorni}:
    qui la stessa chiamata, coi giorni presi dall'elenco del worker."""
    import sys
    from tests.helpers_supabase_sql import ClientSQL

    monkeypatch.delenv("WORKER_ENABLED", raising=False)
    sys.modules.pop("worker.run", None)
    import worker.run as wr

    giorni = dict(wr._PURGE_RETENTION_GDPR)["purge_invio_commercialista"]
    assert giorni == 365
    _semina(db_sql)
    cid = _config(db_sql)
    vecchio = _invio(db_sql, cid, "prova", "2025-05-01", "2025-05-31", creata="2025-06-01 10:00:00+00")
    risultato = ClientSQL(db_sql).rpc("purge_invio_commercialista", {"p_retention_days": giorni}).execute()
    assert risultato.data == 1
    assert scalare("SELECT destinatario FROM public.invio_commercialista_invii WHERE id = %s", vecchio) is None


def test_piva_di_nessuna_sede_rifiutata(db_sql, psycopg):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _config(db_sql, attiva=False, piva="11111111111")


# ─── Review della fase B: solo invii autorizzati (B1) ────────────────────────

def test_si_registra_solo_verso_l_indirizzo_col_consenso(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31", destinatario="estraneo@evil.test")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31", destinatario=None)


@pytest.mark.parametrize("modifica", ["attivo = false", "sospesa_at = now()"])
def test_configurazione_spenta_o_sospesa_non_registra_invii(db_sql, psycopg, modifica):
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, f"UPDATE public.invio_commercialista_config SET {modifica} WHERE id = %s", cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")


def test_la_prova_si_registra_anche_prima_dell_attivazione(db_sql, scalare):
    """La prova non spedisce: serve proprio prima di attivare."""
    _semina(db_sql)
    cid = _config(db_sql, attiva=False)
    _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii") == 1


@pytest.mark.parametrize("campo,valore", [("user", U2), ("piva", "12345678903"), ("company", 99)])
def test_l_invio_copia_la_sua_configurazione(db_sql, psycopg, campo, valore):
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31", **{campo: valore})


def test_spegnere_la_configurazione_ferma_la_presa(db_sql, psycopg, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "in_corso")
    _stato(db_sql, iid, "errore", motivo="configurazione spenta")
    assert scalare("SELECT stato FROM public.invio_commercialista_invii WHERE id = %s", iid) == "errore"


def test_cambiare_email_ferma_l_email_in_partenza(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET email_destinatario = 'nuovo@studio.test' WHERE id = %s", cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET email_tentata_at = now() WHERE id = %s", iid)


def test_una_prova_non_tenta_mai_l_email(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET email_tentata_at = now() WHERE id = %s", iid)


# ─── Review della fase B: un'email partita resta partita (B2) ────────────────

def _partita(db_sql, cid):
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso", email_tentata_at="2026-09-25 10:05:00+00")
    return iid


def test_email_partita_non_diventa_bloccata(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "bloccato", motivo="guardia")


@pytest.mark.parametrize("campo,primo,poi", [
    ("email_tentata_at", "'2026-09-25 10:05:00+00'", "NULL"),
    ("email_tentata_at", "'2026-09-25 10:05:00+00'", "'2026-09-25 11:00:00+00'"),
    ("brevo_http_status", "503", "NULL"),
    ("brevo_message_id", "'<m1@brevo>'", "'<m2@brevo>'"),
])
def test_l_esito_dell_email_si_scrive_una_volta(db_sql, psycopg, scalare, campo, primo, poi):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campo} = {primo} WHERE id = %s", iid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campo} = {poi} WHERE id = %s", iid)
    assert scalare(f"SELECT {campo} IS NOT NULL FROM public.invio_commercialista_invii WHERE id = %s", iid) is True


def test_azzerare_l_email_tentata_non_libera_il_periodo(db_sql, psycopg):
    """La sonda della review: errore + email_tentata_at azzerata, poi lo stesso
    periodo di nuovo. Il primo passo e' gia' rifiutato."""
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET stato = 'errore', email_tentata_at = NULL WHERE id = %s", iid)
    with pytest.raises((psycopg.errors.UniqueViolation, psycopg.errors.ExclusionViolation)):
        _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")


def test_esito_incerto_chiarito_come_non_partito_libera_il_periodo(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    _stato(db_sql, iid, "esito_incerto")
    _stato(db_sql, iid, "errore", chiarito_non_partito_at="2026-09-25 12:00:00+00", motivo="admin: non arrivata")
    _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii WHERE tipo = 'primo'") == 2


def test_si_chiarisce_come_non_partito_solo_un_esito_incerto(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "errore", chiarito_non_partito_at="2026-09-25 12:00:00+00")
    _stato(db_sql, iid, "inviato")
    # Senza email tentata un esito incerto non esiste piu' (ici_spedito_con_email_chk):
    # il chiarimento senza email si prova sull'unica strada rimasta, l'INSERT.
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "reinvio", "2026-07-01", "2026-07-31", stato="errore",
               chiarito_non_partito_at="2026-09-25 12:00:00+00")


def test_il_chiarimento_non_si_riscrive(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    _stato(db_sql, iid, "esito_incerto")
    _stato(db_sql, iid, "errore", chiarito_non_partito_at="2026-09-25 12:00:00+00")
    # Un'altra data e non NULL: NULL lo fermerebbe gia' ici_email_partita_chk.
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET chiarito_non_partito_at = now() WHERE id = %s", iid)


# ─── Review della fase B: garanzie senza un test (B3) ────────────────────────

@pytest.mark.parametrize("da,a", [("in_corso", "richiesto"), ("esito_incerto", "bloccato"),
                                  ("esito_incerto", "in_corso")])
def test_transizioni_vietate_che_rispedirebbero(db_sql, psycopg, da, a):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    for passo in {"in_corso": ["in_corso"], "esito_incerto": ["in_corso", "esito_incerto"]}[da]:
        _stato(db_sql, iid, passo, **({"email_tentata_at": TENTATA} if passo == "in_corso" else {}))
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, a)


@pytest.mark.parametrize("campo,valore", [("periodo_al", "'2026-08-31'"), ("config_id", "gen_random_uuid()"),
                                          ("piva", "'12345678903'")])
def test_un_invio_registrato_non_cambia_neanche_qui(db_sql, psycopg, campo, valore):
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campo} = {valore} WHERE id = %s", iid)


def test_chi_ha_chiesto_l_invio_non_cambia(db_sql, psycopg):
    """Su un ordinario: da notturno ad admin nessun CHECK protesta, solo il trigger."""
    _semina(db_sql)
    cid = _config(db_sql)
    _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    iid = _invio(db_sql, cid, "ordinario", "2026-08-01", "2026-08-31", da="notturno")
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET richiesto_da = 'admin' WHERE id = %s", iid)


def test_attivare_ricontrolla_la_piva(db_sql, psycopg):
    """Creata spenta quando la P.IVA era solo del cliente, poi condivisa: non si accende."""
    _semina(db_sql)
    cid = _config(db_sql, attiva=False)
    _esegui(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, PIVA)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_config SET email_destinatario = %s, consenso_ricevuto = true, "
                        "consenso_data = '2026-09-20', consenso_email = %s, data_partenza = '2026-07-01', attivo = true "
                        "WHERE id = %s", EMAIL, EMAIL, cid)


def test_sospendere_riesce_anche_con_la_piva_condivisa_e_riattivare_ricontrolla(db_sql, psycopg, scalare):
    """E' la guardia dell'esecutore a sospendere, proprio quando la P.IVA e' passata
    anche a un altro account: il trigger non deve impedirglielo."""
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, PIVA)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET sospesa_at = now(), sospesa_motivo = 'piva_non_solo_del_cliente' WHERE id = %s", cid)
    assert scalare("SELECT sospesa_at IS NOT NULL FROM public.invio_commercialista_config WHERE id = %s", cid) is True
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "UPDATE public.invio_commercialista_config SET sospesa_at = NULL WHERE id = %s", cid)


def test_riattivare_azzera_la_data_di_disattivazione(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET attivo = false WHERE id = %s", cid)
    _esegui(db_sql, "UPDATE public.invio_commercialista_config SET attivo = true WHERE id = %s", cid)
    assert scalare("SELECT disattivata_at FROM public.invio_commercialista_config WHERE id = %s", cid) is None


def test_l_ordinario_dopo_due_anni_riparte_dal_limite(db_sql, psycopg, scalare):
    """L'ultimo invio riuscito e' di tre anni fa: si riparte da oggi meno 2 anni,
    non dal giorno dopo (quei documenti Invoicetronic non li ha piu')."""
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2023-06-01", "2023-06-10", creata="2023-06-15 10:00:00+00")
    _stato(db_sql, iid, "in_corso", email_tentata_at="2023-06-15 10:05:00+00")
    _stato(db_sql, iid, "inviato")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "ordinario", "2023-06-11", "2024-09-30", da="notturno")
    _invio(db_sql, cid, "ordinario", "2024-09-25", "2024-09-30", da="notturno")
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii WHERE tipo = 'ordinario'") == 1


# ─── Review della fase B: rilievi non bloccanti ──────────────────────────────

def test_l_email_del_consenso_e_normalizzata(db_sql, psycopg):
    _semina(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "INSERT INTO public.invio_commercialista_config (user_id, piva, consenso_email) VALUES (%s, %s, ' Studio@X.test')", U1, PIVA)


def test_non_si_reinvia_prima_del_primo_invio(db_sql, psycopg):
    _semina(db_sql)
    cid = _config(db_sql)
    _inviato(db_sql, cid, "primo", "2026-07-10", "2026-07-31")
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "reinvio", "2026-07-01", "2026-07-15")
    _invio(db_sql, cid, "reinvio", "2026-07-10", "2026-07-15")


def test_creata_at_nel_futuro_rifiutata(db_sql, psycopg):
    """Coi limiti sulle date calcolati da creata_at, una data futura li sposterebbe."""
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _esegui(db_sql, "INSERT INTO public.invio_commercialista_invii (config_id, user_id, piva, invoicetronic_company_id, "
                        "destinatario, tipo, periodo_dal, periodo_al, richiesto_da, creata_at) VALUES "
                        "(%s, %s, %s, 1756, %s, 'prova', '2026-07-01', now()::date, 'admin', now() + interval '2 days')",
                cid, U1, PIVA, EMAIL)


def test_la_pulizia_toglie_l_email_delle_configurazioni_mai_accese(db_sql, scalare):
    _semina(db_sql)
    ferma = _esegui(db_sql, "INSERT INTO public.invio_commercialista_config (user_id, piva, email_destinatario, aggiornata_at) "
                            "VALUES (%s, %s, %s, now() - interval '91 days') RETURNING id", U1, PIVA, EMAIL)[0][0]
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 1
    assert scalare("SELECT email_destinatario FROM public.invio_commercialista_config WHERE id = %s", ferma) is None


# ─── Seconda review della fase B: il registro non dimentica ──────────────────

def test_config_id_non_si_azzera_a_mano(db_sql, psycopg):
    """Con la configurazione viva, config_id a NULL toglierebbe la riga dal
    cursore e dai controlli: il suo periodo si potrebbe rispedire."""
    _semina(db_sql)
    cid = _config(db_sql)
    inviato = _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    in_volo = _invio(db_sql, cid, "reinvio", "2026-07-01", "2026-07-10")
    _stato(db_sql, in_volo, "in_corso", email_tentata_at=TENTATA)
    for iid in (inviato, in_volo):
        with pytest.raises(psycopg.errors.CheckViolation):
            _esegui(db_sql, "UPDATE public.invio_commercialista_invii SET config_id = NULL WHERE id = %s", iid)


def test_service_role_non_cancella_il_registro(db_sql, psycopg, scalare):
    """Cancellare una riga inviata farebbe ripartire l'ordinario da quel periodo.
    Su Supabase le default privileges danno ALL a service_role: si simula, poi la
    migration lo toglie. Pulizia (SECURITY DEFINER) e cascate funzionano ancora."""
    if not scalare("SELECT count(*) FROM pg_roles WHERE rolname = 'service_role'"):
        pytest.skip("ruolo service_role assente nello snapshot")
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _inviato(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _esegui(db_sql, "GRANT ALL ON public.invio_commercialista_invii TO service_role")
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    for permesso in ("DELETE", "TRUNCATE"):
        assert scalare("SELECT has_table_privilege('service_role', 'public.invio_commercialista_invii', %s)", permesso) is False
    _esegui(db_sql, "SET LOCAL ROLE service_role")
    try:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            _esegui(db_sql, "DELETE FROM public.invio_commercialista_invii WHERE id = %s", iid)
        assert _esegui(db_sql, "SELECT public.purge_invio_commercialista(365, 90)")[0][0] == 0
        _esegui(db_sql, "DELETE FROM public.invio_commercialista_config WHERE id = %s", cid)
        assert _esegui(db_sql, "SELECT current_user")[0][0] == "service_role"
    finally:
        _esegui(db_sql, "RESET ROLE")
    assert scalare("SELECT config_id FROM public.invio_commercialista_invii WHERE id = %s", iid) is None


def test_la_pulizia_risparmia_le_configurazioni_attive(db_sql, scalare):
    """Ferma da 91 giorni ma accesa: email e consenso restano."""
    _semina(db_sql)
    cid = _esegui(
        db_sql,
        "INSERT INTO public.invio_commercialista_config (user_id, piva, invoicetronic_company_id, email_destinatario, "
        "data_partenza, attivo, consenso_ricevuto, consenso_data, consenso_email, aggiornata_at) "
        "VALUES (%s, %s, 1756, %s, '2026-07-01', true, true, '2026-06-01', %s, now() - interval '91 days') RETURNING id",
        U1, PIVA, EMAIL, EMAIL,
    )[0][0]
    assert scalare("SELECT public.purge_invio_commercialista(365, 90)") == 0
    assert _esegui(db_sql, "SELECT attivo, email_destinatario FROM public.invio_commercialista_config WHERE id = %s", cid)[0] == (True, EMAIL)


def test_un_esito_incerto_diventa_errore_solo_col_chiarimento(db_sql, psycopg):
    """Un 4xx scritto dopo, su una riga andata in timeout, liberava il periodo."""
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _partita(db_sql, cid)
    _stato(db_sql, iid, "esito_incerto")
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, "errore", brevo_http_status=400)


@pytest.mark.parametrize("stato", ["inviato", "esito_incerto"])
def test_inviato_o_incerto_solo_con_l_email_tentata(db_sql, psycopg, stato):
    """E' il tentativo d'email che il trigger autorizza: senza, il controllo si saltava."""
    _semina(db_sql)
    cid = _config(db_sql)
    iid = _invio(db_sql, cid, "primo", "2026-07-01", "2026-07-31")
    _stato(db_sql, iid, "in_corso")
    with pytest.raises(psycopg.errors.CheckViolation):
        _stato(db_sql, iid, stato)
