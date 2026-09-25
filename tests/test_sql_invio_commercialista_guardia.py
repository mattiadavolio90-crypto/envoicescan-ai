"""La guardia dell'invio al commercialista contro il database vero (fase B).

Le due verifiche che leggono OneFlux: la P.IVA e' solo del cliente (su
ristoranti E piva_ristoranti) e la coda locale conferma l'elenco di
Invoicetronic. Girano con ClientSQL: stesse query del codice, Postgres vero,
due clienti.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.sql

U1 = "2d0d0000-0000-4000-8000-000000000001"
U2 = "2d0d0000-0000-4000-8000-000000000002"
SEDE_1 = "2d0d0000-0000-4000-8000-0000000000a1"
SEDE_2 = "2d0d0000-0000-4000-8000-0000000000a2"
PIVA = "07863990961"
ALTRA = "12345678903"
AZIENDA = 1756
ADESSO = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _cur(db_sql, sql, *params):
    with db_sql.cursor() as cur:
        cur.execute(sql, params or None)


def _semina(db_sql):
    for uid, email in ((U1, "g1@ic.test"), (U2, "g2@ic.test")):
        _cur(db_sql, "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')", uid, email)
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'A', %s, TRUE)", SEDE_1, U1, PIVA)
    _cur(db_sql, "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) VALUES (%s, %s, 'B', %s, TRUE)", SEDE_2, U2, ALTRA)


def _coda(db_sql, id_, user, piva, meta, creata="2026-09-01 10:00:00+00", sede=None):
    stato = "done" if user else "failed"
    _cur(
        db_sql,
        "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, user_id, ristorante_id, source, payload_meta, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'invoicetronic', %s::jsonb, %s)",
        id_, f"evt-g-{id_}", piva, stato, user, sede if user else None, json.dumps(meta), creata,
    )


def _sb(db_sql):
    from tests.helpers_supabase_sql import ClientSQL
    return ClientSQL(db_sql)


# ─── Proprieta' della P.IVA ──────────────────────────────────────────────────

def test_piva_solo_del_cliente_passa(db_sql):
    from services.invio_commercialista_guardia import controlla_proprieta_piva
    _semina(db_sql)
    controlla_proprieta_piva(_sb(db_sql), PIVA, U1)


def test_piva_chiesta_per_un_altro_cliente_blocca(db_sql):
    from services.invio_commercialista_guardia import GuardiaViolata, controlla_proprieta_piva
    _semina(db_sql)
    with pytest.raises(GuardiaViolata, match="piva_non_solo_del_cliente"):
        controlla_proprieta_piva(_sb(db_sql), PIVA, U2)


def test_sede_spostata_a_un_altro_account_blocca(db_sql):
    """piva_ristoranti resta al vecchio account quando la sede passa a un altro:
    la guardia guarda entrambe le tabelle."""
    from services.invio_commercialista_guardia import GuardiaViolata, controlla_proprieta_piva
    _semina(db_sql)
    _cur(db_sql, "UPDATE public.ristoranti SET user_id = %s WHERE id = %s", U2, SEDE_1)
    for chi in (U1, U2):
        with pytest.raises(GuardiaViolata):
            controlla_proprieta_piva(_sb(db_sql), PIVA, chi)


def test_piva_senza_sedi_blocca(db_sql):
    from services.invio_commercialista_guardia import GuardiaViolata, controlla_proprieta_piva
    _semina(db_sql)
    with pytest.raises(GuardiaViolata):
        controlla_proprieta_piva(_sb(db_sql), "11111111111", U1)


# ─── La coda conferma l'elenco ───────────────────────────────────────────────

def _controlla(db_sql, ids):
    from services.invio_commercialista_guardia import controlla_coda
    controlla_coda(_sb(db_sql), U1, PIVA, AZIENDA, set(ids), adesso=ADESSO)


def test_la_coda_conferma_l_elenco(db_sql):
    _semina(db_sql)
    _coda(db_sql, 1, U1, PIVA, {"resource_id": 101, "invoicetronic_company_id": AZIENDA}, sede=SEDE_1)
    _coda(db_sql, 2, U1, PIVA, {"resource_id": 102}, sede=SEDE_1)
    _coda(db_sql, 3, U2, ALTRA, {"resource_id": 999, "invoicetronic_company_id": 2000}, sede=SEDE_2)
    _controlla(db_sql, {101, 102, 103})


def test_elenco_senza_una_fattura_gia_arrivata_blocca(db_sql):
    """Chiave o azienda sbagliata: l'elenco e' plausibile ma non contiene cio'
    che OneFlux ha gia' visto arrivare."""
    from services.invio_commercialista_guardia import GuardiaViolata
    _semina(db_sql)
    _coda(db_sql, 1, U1, PIVA, {"resource_id": 101, "invoicetronic_company_id": AZIENDA}, sede=SEDE_1)
    with pytest.raises(GuardiaViolata, match="elenco_senza_fatture_gia_arrivate"):
        _controlla(db_sql, set())


def test_riga_senza_cliente_dell_azienda_conta_anche_lei(db_sql):
    from services.invio_commercialista_guardia import GuardiaViolata
    _semina(db_sql)
    _coda(db_sql, 1, None, "UNKNOWN", {"resource_id": 105, "invoicetronic_company_id": AZIENDA})
    with pytest.raises(GuardiaViolata):
        _controlla(db_sql, {101})
    _controlla(db_sql, {105})


def test_azienda_con_fatture_di_un_altro_cliente_blocca(db_sql):
    from services.invio_commercialista_guardia import GuardiaViolata
    _semina(db_sql)
    _coda(db_sql, 1, U2, ALTRA, {"resource_id": 101, "invoicetronic_company_id": AZIENDA}, sede=SEDE_2)
    with pytest.raises(GuardiaViolata, match="azienda_con_fatture_di_un_altro_cliente"):
        _controlla(db_sql, {101})


def test_fatture_del_cliente_su_un_altra_azienda_bloccano(db_sql):
    from services.invio_commercialista_guardia import GuardiaViolata
    _semina(db_sql)
    _coda(db_sql, 1, U1, PIVA, {"resource_id": 101, "invoicetronic_company_id": 3000}, sede=SEDE_1)
    with pytest.raises(GuardiaViolata, match="fatture_del_cliente_su_un_altra_azienda"):
        _controlla(db_sql, {101})


def test_righe_vecchie_e_senza_resource_id_non_contano(db_sql):
    _semina(db_sql)
    _coda(db_sql, 1, U1, PIVA, {"resource_id": 101}, creata="2024-09-01 10:00:00+00", sede=SEDE_1)
    _coda(db_sql, 2, U1, PIVA, {"injected": True}, sede=SEDE_1)
    _controlla(db_sql, set())


def test_piva_rimasta_solo_in_piva_ristoranti_blocca(db_sql):
    """Sede cancellata ma riga rimasta in piva_ristoranti: senza una sede vera
    la P.IVA non e' del cliente."""
    from services.invio_commercialista_guardia import GuardiaViolata, controlla_proprieta_piva
    _semina(db_sql)
    _cur(db_sql, "UPDATE public.piva_ristoranti SET piva = %s WHERE ristorante_id = %s", "22222222222", SEDE_1)
    with pytest.raises(GuardiaViolata, match="piva_non_solo_del_cliente"):
        controlla_proprieta_piva(_sb(db_sql), "22222222222", U1)
