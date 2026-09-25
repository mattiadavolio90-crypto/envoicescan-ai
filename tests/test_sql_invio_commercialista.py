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


def _invio(db_sql, cid, tipo, dal, al, stato="richiesto", da="admin", creata=ORA, **extra):
    colonne = ["config_id", "user_id", "piva", "invoicetronic_company_id", "destinatario", "tipo",
               "periodo_dal", "periodo_al", "stato", "richiesto_da", "creata_at", *extra]
    valori = [cid, U1, PIVA, 1756, EMAIL, tipo, dal, al, stato, da, creata, *extra.values()]
    righe = _esegui(
        db_sql,
        f"INSERT INTO public.invio_commercialista_invii ({', '.join(colonne)}) VALUES ({', '.join(['%s'] * len(valori))}) RETURNING id",
        *valori,
    )
    return righe[0][0]


def _stato(db_sql, iid, stato, **extra):
    campi = ", ".join(["stato = %s", *[f"{k} = %s" for k in extra]])
    _esegui(db_sql, f"UPDATE public.invio_commercialista_invii SET {campi} WHERE id = %s", stato, *extra.values(), iid)


def _inviato(db_sql, cid, tipo, dal, al):
    iid = _invio(db_sql, cid, tipo, dal, al)
    _stato(db_sql, iid, "in_corso")
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
    _stato(db_sql, iid, "in_corso")
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
    arrivare al 31/12, non al 1/1."""
    _semina(db_sql)
    cid = _config(db_sql)
    with pytest.raises(psycopg.errors.CheckViolation):
        _invio(db_sql, cid, "prova", "2026-12-01", "2027-01-01", creata="2026-12-31 23:30:00+00")
    _invio(db_sql, cid, "prova", "2026-12-01", "2026-12-31", creata="2026-12-31 23:30:00+00")
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
        _stato(db_sql, iid, passo)
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


def test_cancellare_il_cliente_cancella_configurazione_e_registro(db_sql, scalare):
    _semina(db_sql)
    cid = _config(db_sql)
    _invio(db_sql, cid, "prova", "2026-07-01", "2026-07-31")
    _esegui(db_sql, "DELETE FROM public.ristoranti WHERE user_id = %s", U1)
    _esegui(db_sql, "DELETE FROM public.users WHERE id = %s", U1)
    assert scalare("SELECT count(*) FROM public.invio_commercialista_invii") == 0
    assert scalare("SELECT count(*) FROM public.invio_commercialista_config") == 0


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


@pytest.mark.parametrize("ruolo", ["anon", "authenticated"])
def test_i_ruoli_pubblici_non_eseguono_la_pulizia(db_sql, scalare, ruolo):
    if not scalare("SELECT count(*) FROM pg_roles WHERE rolname = %s", ruolo):
        pytest.skip(f"ruolo {ruolo} assente nello snapshot")
    _esegui(db_sql, f"GRANT EXECUTE ON FUNCTION public.purge_invio_commercialista(integer, integer) TO {ruolo}")
    _esegui(db_sql, MIGRATION.read_text(encoding="utf-8"))
    assert scalare(
        "SELECT has_function_privilege(%s, 'public.purge_invio_commercialista(integer, integer)', 'EXECUTE')", ruolo
    ) is False


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
