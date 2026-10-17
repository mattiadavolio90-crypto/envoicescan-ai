"""La guardia anti-doppione per identita' vuole una fattura vera, su un Postgres vero.

`_trova_documento_duplicato_per_identita` cercava solo in `fatture_documenti`. Il
backfill da cartella del 12/5/2026 aveva scritto 19 testate di dicembre 2025 per
file che non erano mai entrati (nessuna riga in `fatture`): caricando una di quelle
fatture con un nome file diverso, la guardia l'avrebbe rifiutata come «gia'
caricata». Una testata conta come doppione solo se il suo file ha righe attive
nella stessa sede.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

U1 = "0d0b0000-0000-4000-8000-000000000001"
SEDE = "0d0b0000-0000-4000-8000-00000000000a"
ALTRA_SEDE = "0d0b0000-0000-4000-8000-00000000000b"
PIVA = "00813270154"
NUMERO = "11889/V1/2026"
DATA = "2026-03-19"
HEADER = {"piva_cedente": PIVA, "numero_documento": NUMERO, "Data_Documento": DATA, "tipo_documento": "TD01"}


def _semina(db_sql, righe_in=None, cestinate=False, oscurate=False, tipo="TD01"):
    """Una testata `VECCHIO.xml` in SEDE con l'identita' di HEADER; le sue righe,
    se `righe_in` e' una sede, stanno li'."""
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) VALUES (%s, 'd@dop.test', 'x', 'T')",
            (U1,),
        )
        for sid in (SEDE, ALTRA_SEDE):
            cur.execute(
                "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, partita_iva, attivo) "
                "VALUES (%s, %s, 'Sede', '07863990961', TRUE)",
                (sid, U1),
            )
        cur.execute(
            "INSERT INTO public.fatture_documenti (user_id, ristorante_id, file_origine, fornitore, "
            "piva_fornitore, numero_documento, data_documento, tipo_documento, totale_documento) "
            "VALUES (%s, %s, 'VECCHIO.xml', 'COMAVICOLA', %s, %s, %s, %s, 35)",
            (U1, SEDE, PIVA, NUMERO, DATA, tipo),
        )
        if righe_in:
            cur.execute(
                "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
                "fornitore, descrizione, totale_riga, categoria, piva_cedente, oscurata, deleted_at) "
                "VALUES (%s, %s, 'VECCHIO.xml', 1, %s, 'COMAVICOLA', 'COSCE POLLO', 35, 'CARNE', %s, %s, "
                "CASE WHEN %s THEN now() END)",
                (U1, righe_in, DATA, PIVA, oscurate, cestinate),
            )


def _guardia(db_sql, nome_file="NUOVO.xml", header=HEADER):
    from services.invoice_service import _trova_documento_duplicato_per_identita
    from tests.helpers_supabase_sql import ClientSQL

    return _trova_documento_duplicato_per_identita(ClientSQL(db_sql), U1, SEDE, nome_file, header)


def test_testata_con_righe_e_un_doppione(db_sql):
    _semina(db_sql, righe_in=SEDE)
    trovato = _guardia(db_sql)
    assert trovato is not None and trovato["file_origine"] == "VECCHIO.xml"


def test_testata_senza_righe_non_blocca_il_caricamento(db_sql):
    """Il caso delle 19 testate del backfill."""
    _semina(db_sql)
    assert _guardia(db_sql) is None


def test_righe_in_un_altra_sede_non_fanno_doppione_qui(db_sql):
    """Il caso OVERTIME/OFFSIDE: la testata e' rimasta in una sede, le righe in un'altra."""
    _semina(db_sql, righe_in=ALTRA_SEDE)
    assert _guardia(db_sql) is None


def test_righe_nel_cestino_non_fanno_doppione(db_sql):
    _semina(db_sql, righe_in=SEDE, cestinate=True)
    assert _guardia(db_sql) is None


def test_fattura_esclusa_dai_conti_resta_un_doppione(db_sql):
    """Escludere una fattura (oscurata) non la toglie dal programma: ricaricarla
    con un altro nome la raddoppierebbe."""
    _semina(db_sql, righe_in=SEDE, oscurate=True)
    assert _guardia(db_sql) is not None


def test_controllo_stesso_file_e_altro_tipo_non_sono_doppioni(db_sql):
    """Controllo positivo dei filtri che c'erano gia': con le righe presenti."""
    _semina(db_sql, righe_in=SEDE)
    assert _guardia(db_sql, nome_file="VECCHIO.xml") is None
    assert _guardia(db_sql, header={**HEADER, "tipo_documento": "TD04"}) is None


def test_backfill_da_cartella_salta_i_file_senza_righe(db_sql, tmp_path, monkeypatch):
    """L'origine delle 19 testate: lo script scriveva una testata per ogni file
    della cartella. Ora solo per quelli con righe attive nella sede indicata;
    un file con righe in un'altra sede o solo nel cestino resta fuori."""
    import sys

    from scripts import backfill_documenti_da_cartella as bf
    from tests.helpers_supabase_sql import ClientSQL

    _semina(db_sql, righe_in=SEDE)
    with db_sql.cursor() as cur:
        cur.execute("DELETE FROM public.fatture_documenti WHERE user_id = %s", (U1,))
        for nome, sede, cestinata in (("ALTRA.xml", ALTRA_SEDE, False), ("CESTINO.xml", SEDE, True)):
            cur.execute(
                "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, numero_riga, data_documento, "
                "fornitore, descrizione, totale_riga, categoria, deleted_at) "
                "VALUES (%s, %s, %s, 1, %s, 'X', 'Y', 10, 'CARNE', CASE WHEN %s THEN now() END)",
                (U1, sede, nome, DATA, cestinata),
            )
    for nome in ("VECCHIO.xml", "MAI_ENTRATO.xml", "ALTRA.xml", "CESTINO.xml"):
        (tmp_path / nome).write_bytes(b"<x/>")

    monkeypatch.setattr(bf, "get_supabase_client", lambda: ClientSQL(db_sql))
    monkeypatch.setattr(bf, "_extract_rows_from_file", lambda path, user_id: [
        {"Fornitore": "COMAVICOLA", "piva_cedente": PIVA, "numero_documento": path.stem,
         "Data_Documento": DATA, "tipo_documento": "TD01", "Totale_Documento": 35}
    ])
    monkeypatch.setattr(sys, "argv", [
        "backfill", "--folder", str(tmp_path), "--user-id", U1, "--ristorante-id", SEDE, "--apply",
    ])
    assert bf.main() == 0

    with db_sql.cursor() as cur:
        cur.execute("SELECT file_origine FROM public.fatture_documenti WHERE user_id = %s", (U1,))
        assert [r[0] for r in cur.fetchall()] == ["VECCHIO.xml"]
