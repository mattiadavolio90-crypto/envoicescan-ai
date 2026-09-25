"""Il worker decide il cliente dall'XML, su un Postgres vero (passo 0-bis).

I test unitari usano un finto; qui la STESSA funzione del worker
(`_risolvi_cliente`) gira col builder tradotto in SQL (`ClientSQL`), sullo
schema del DB live e coi suoi vincoli: `chk_fatture_queue_tenant_consistency`
rifiuterebbe una riga scritta male, e la query delle sedi incontra davvero i
dati di un altro cliente.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

U1 = "0b150000-0000-4000-8000-000000000001"
U2 = "0b150000-0000-4000-8000-000000000002"
SEDE_A = "0b150000-0000-4000-8000-00000000000a"
SEDE_B = "0b150000-0000-4000-8000-00000000000b"
SEDE_ALTRO = "0b150000-0000-4000-8000-00000000000c"
PIVA = "07863990961"
PIVA_ALTRO = "12345678903"
ID = 990001


def _fattura(piva, indirizzo, civico, cap, comune):
    return (
        '<?xml version="1.0" encoding="UTF-8"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2" versione="FPR12">'
        "<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese>"
        f"<IdCodice>{piva}</IdCodice></IdFiscaleIVA></DatiAnagrafici>"
        f"<Sede><Indirizzo>{indirizzo}</Indirizzo><NumeroCivico>{civico}</NumeroCivico><CAP>{cap}</CAP><Comune>{comune}</Comune></Sede>"
        "</CessionarioCommittente></FatturaElettronicaHeader><FatturaElettronicaBody>"
        "<DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Data>2026-09-20</Data>"
        "<Numero>77</Numero><ImportoTotaleDocumento>122.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>"
        "</FatturaElettronicaBody></p:FatturaElettronica>"
    )


def _semina(db_sql, sedi_u1=((SEDE_A, "via roma 5 20100 milano"),), altro_cliente=True):
    with db_sql.cursor() as cur:
        for uid, email in ((U1, "a@0bis.test"), (U2, "b@0bis.test")):
            cur.execute(
                "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, %s, 'x', 'T')",
                (uid, email),
            )
        for sid, match in sedi_u1:
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, indirizzo_match) "
                "VALUES (%s, %s, 'Sede', %s, TRUE, %s)",
                (sid, U1, PIVA, match),
            )
        if altro_cliente:
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo, indirizzo_match) "
                "VALUES (%s, %s, 'Altro', %s, TRUE, 'via roma 5 20100 milano')",
                (SEDE_ALTRO, U2, PIVA_ALTRO),
            )
        cur.execute(
            "INSERT INTO public.fatture_queue (id, event_id, piva_raw, status, attempt_count, max_attempts, "
            "next_retry_at, locked_by, locked_at, source, payload_meta) "
            "VALUES (%s, 'evt-0bis-sql', 'UNKNOWN', 'processing', 8, 8, now(), 'w-1', now(), 'invoicetronic', "
            "'{\"resource_id\": 96551, \"api_error\": \"HTTP 403\"}'::jsonb)",
            (ID,),
        )


def _item():
    return {"id": ID, "event_id": "evt-0bis-sql", "payload_meta": {"resource_id": 96551, "api_error": "HTTP 403"}}


def _riga(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "SELECT status, user_id::text, ristorante_id::text, piva_raw, attempt_count, locked_by, "
            "xml_content IS NOT NULL, payload_meta FROM public.fatture_queue WHERE id = %s",
            (ID,),
        )
        return cur.fetchone()


def _risolvi(db_sql, xml, worker_id="w-1"):
    from tests.helpers_supabase_sql import ClientSQL
    from worker.queue_processor import _risolvi_cliente

    return _risolvi_cliente(ClientSQL(db_sql), _item(), xml, _item()["payload_meta"], worker_id)


def test_una_sede_la_riga_prende_il_cliente_e_resta_in_lavorazione(db_sql):
    _semina(db_sql)
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Qualunque", "1", "00100", "Roma"))
    assert esito[:3] == (U1, SEDE_A, PIVA)
    status, uid, rid, piva, tentativi, lock, _, meta = _riga(db_sql)
    assert (status, uid, rid, piva, lock) == ("processing", U1, SEDE_A, PIVA, "w-1")
    assert meta["resource_id"] == 96551 and meta["numero_fattura"] == "77"


def test_la_piva_di_un_altro_cliente_non_e_mai_la_nostra(db_sql):
    """La P.IVA in fattura e' dell'altro cliente: la fattura va a lui, non al
    cliente che ha un indirizzo simile."""
    _semina(db_sql)
    esito = _risolvi(db_sql, _fattura(PIVA_ALTRO, "Via Roma", "5", "20100", "Milano"))
    assert esito[:3] == (U2, SEDE_ALTRO, PIVA_ALTRO)


def test_piu_sedi_ambigue_la_riga_passa_da_assegnare_e_il_vincolo_la_accetta(db_sql):
    _semina(db_sql, sedi_u1=((SEDE_A, "via roma 5 20100 milano"), (SEDE_B, "viale monza 10 20127 milano")))
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Sede Legale", "99", "00100", "Roma"))
    assert esito.status == "skip"
    status, uid, rid, piva, tentativi, lock, ha_xml, meta = _riga(db_sql)
    assert (status, uid, rid, piva, tentativi, lock, ha_xml) == ("da_assegnare", U1, None, PIVA, 0, None, True)
    assert meta["routing"]["mode"] == "manual" and meta["nome_file"] == "webhook_evt-0bis-sql.xml"


def test_piva_sconosciuta_torna_prelevabile_quando_il_cliente_registra_la_sede(db_sql, scalare):
    """Il caso che senza azzerare i tentativi resterebbe fermo per sempre: la
    riga era all'8° tentativo, il trigger su ristoranti la rimette pending
    senza toccare attempt_count, e claim_batch_for_processing vuole
    attempt_count < max_attempts."""
    _semina(db_sql, sedi_u1=(), altro_cliente=False)
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Roma", "5", "20100", "Milano"))
    assert esito.status == "skip"
    assert _riga(db_sql)[:5] == ("unknown_tenant", None, None, PIVA, 0)

    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
            "VALUES (%s, %s, 'Nuova', %s, TRUE)",
            (SEDE_A, U1, PIVA),
        )
    assert _riga(db_sql)[:3] == ("pending", U1, SEDE_A)
    with db_sql.cursor() as cur:
        cur.execute("SELECT id FROM public.claim_batch_for_processing('w-2', 10)")
        assert [r[0] for r in cur.fetchall()] == [ID]


def test_la_riga_presa_da_un_altro_worker_non_si_tocca(db_sql):
    _semina(db_sql, sedi_u1=((SEDE_A, "via roma 5 20100 milano"), (SEDE_B, "viale monza 10 20127 milano")))
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Sede Legale", "99", "00100", "Roma"), worker_id="w-altro")
    assert esito.status == "skip" and "non piu' in lavorazione" in esito.error
    assert _riga(db_sql)[:6] == ("processing", None, None, "UNKNOWN", 8, "w-1")


def test_le_sedi_disattivate_non_contano(db_sql):
    _semina(db_sql)
    with db_sql.cursor() as cur:
        cur.execute("UPDATE public.ristoranti SET attivo = FALSE WHERE id = %s", (SEDE_A,))
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Roma", "5", "20100", "Milano"))
    assert esito.status == "skip"
    assert _riga(db_sql)[0] == "unknown_tenant"


def test_sede_registrata_mentre_il_worker_decide_viene_agganciata_lo_stesso(db_sql, monkeypatch):
    """La corsa trovata dalla revisione: il worker legge 0 sedi, il cliente
    registra la sede (il trigger cerca righe unknown_tenant e non trova la
    nostra, ancora processing), poi il worker parcheggia. Senza la chiamata a
    resolve_unknown_tenant dopo il parcheggio la riga restava ferma per sempre."""
    from worker import queue_processor as qp

    _semina(db_sql, sedi_u1=(), altro_cliente=False)
    originale = qp.routing_coda.decidi_cliente

    def decide_e_intanto_arriva_la_sede(xml, sedi):
        esito = originale(xml, sedi)
        with db_sql.cursor() as cur:
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                "VALUES (%s, %s, 'Arrivata adesso', %s, TRUE)",
                (SEDE_A, U1, PIVA),
            )
        return esito

    monkeypatch.setattr(qp.routing_coda, "decidi_cliente", decide_e_intanto_arriva_la_sede)
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Roma", "5", "20100", "Milano"))
    assert esito.status == "skip"
    assert _riga(db_sql)[:3] == ("pending", U1, SEDE_A)


def test_piva_su_piu_account_la_riga_tiene_xml_e_piva_ma_nessun_cliente(db_sql):
    _semina(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
            "VALUES (%s, %s, 'Stessa P.IVA, altro account', %s, TRUE)",
            (SEDE_B, U2, PIVA),
        )
    esito = _risolvi(db_sql, _fattura(PIVA, "Via Roma", "5", "20100", "Milano"))
    assert esito.status == "retry" and "account diversi" in esito.error
    status, uid, rid, piva, tentativi, lock, ha_xml, meta = _riga(db_sql)
    assert (status, uid, rid, piva, ha_xml) == ("processing", None, None, PIVA, True)
    assert meta["cliente_dal_worker"]["esito"] == "piu_account" and meta["numero_fattura"] == "77"
