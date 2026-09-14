"""Lo script che misura CHI decide la categoria funziona davvero.

Perche' questo presidio esiste
==============================
`scripts/audit_chi_decide_la_categoria.py` risponde alla domanda che ha
riscritto la lente L4: sulle righe con provenienza, l'AI decide l'1,3% e il
94,8% e' gia' deciso prima del modello. E' una misura che si rifara' fra mesi,
e uno script di misura che si rompe in silenzio e' peggio di nessuno script:
la prossima persona leggerebbe un errore, o peggio un numero sbagliato.

Qui gira sullo schema vero (Postgres reale + il client Supabase tradotto in SQL
di `tests/helpers_supabase_sql.py`): se una colonna cambia nome o la catena di
query non e' piu' valida, questo test lo dice.

Non asserisce il valore di produzione (cambia ogni giorno): asserisce che i
conteggi siano quelli dei dati seminati, che e' la parte che puo' rompersi.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.sql

UTENTE = "11111111-1111-4111-8111-111111111111"
SEDE = "22222222-2222-4222-8222-222222222222"

# 5 righe: 1 decisa dall'AI, 2 prima del modello, 1 dall'umano, 1 senza provenienza
FONTI = ["AI_alta", "L2_locale", "L2_locale", "correzione_cliente", None]


def _semina(db_sql):
    with db_sql.cursor() as cur:
        cur.execute(
            "INSERT INTO public.users (id, email, password_hash, nome_ristorante) "
            "VALUES (%s, 'prova@oneflux.test', 'x', 'Prova')",
            (UTENTE,),
        )
        cur.execute(
            "INSERT INTO public.ristoranti (id, user_id, nome_ristorante, "
            "partita_iva, attivo) VALUES (%s, %s, 'Sede', '01234567890', true)",
            (SEDE, UTENTE),
        )
        for numero, fonte in enumerate(FONTI):
            cur.execute(
                "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
                "numero_riga, data_documento, fornitore, descrizione, categoria, "
                "quantita, prezzo_unitario, totale_riga, categoria_fonte, "
                "categoria_fiducia) VALUES (%s, %s, 'prova.xml', %s, '2026-03-10', "
                "'Fornitore', 'riga', 'CARNE', 1, 10.00, 10.00, %s, 'certa')",
                (UTENTE, SEDE, numero, fonte),
            )


def _esegui(db_sql, monkeypatch, capsys) -> str:
    from tests.helpers_supabase_sql import ClientSQL
    import scripts.audit_chi_decide_la_categoria as modulo

    monkeypatch.setattr(modulo, "get_supabase_client", lambda: ClientSQL(db_sql))
    assert modulo.main() == 0
    return capsys.readouterr().out


def test_lo_script_gira_sullo_schema_vero(db_sql, monkeypatch, capsys):
    _semina(db_sql)
    out = _esegui(db_sql, monkeypatch, capsys)
    assert "CHI DECIDE LA CATEGORIA" in out


def test_separa_l_ai_da_chi_decide_prima(db_sql, monkeypatch, capsys):
    """E' la riga che ha riscritto la lente: va contata giusta."""
    _semina(db_sql)
    out = _esegui(db_sql, monkeypatch, capsys)
    assert "AI                                1    25.0%" in out
    assert "deciso prima del modello          2    50.0%" in out
    assert "umano                             1    25.0%" in out


def test_dichiara_sempre_la_base_della_percentuale(db_sql, monkeypatch, capsys):
    """Una percentuale senza la sua base non e' una misura.

    La riga senza provenienza NON entra nel denominatore delle quote (4, non 5),
    ma il totale delle attive resta stampato: senza, un 25% non sarebbe leggibile.
    """
    _semina(db_sql)
    out = _esegui(db_sql, monkeypatch, capsys)
    assert "righe attive:                  5" in out
    assert "Su 4 righe con provenienza:" in out


def test_non_conta_le_righe_nel_cestino(db_sql, monkeypatch, capsys):
    """Il soft delete e' una regola di dominio: una riga cestinata non e' attiva."""
    _semina(db_sql)
    with db_sql.cursor() as cur:
        cur.execute(
            "UPDATE public.fatture SET deleted_at = now() WHERE categoria_fonte = %s",
            ("AI_alta",),
        )
    out = _esegui(db_sql, monkeypatch, capsys)
    assert "righe attive:                  4" in out
    assert "Su 3 righe con provenienza:" in out
    assert "Quota decisa dall'AI: 0.0%" in out


def test_la_paginazione_non_perde_righe(db_sql, monkeypatch, capsys):
    """Con piu' di una pagina il conteggio deve tornare comunque.

    `range()` senza `ORDER BY` ripete e perde righe in silenzio, e il totale puo'
    tornare lo stesso (misurato il 10/09/2026: 653 id mancanti su 3.067). Qui si
    semina una pagina e mezza e si controlla che il totale sia quello vero: senza
    questo test l'assenza di `.order("id")` non sarebbe osservabile, perche' gli
    altri casi stanno tutti in una pagina sola.
    """
    import scripts.audit_chi_decide_la_categoria as modulo

    _semina(db_sql)
    extra = modulo.PAGINA + 7
    with db_sql.cursor() as cur:
        cur.executemany(
            "INSERT INTO public.fatture (user_id, ristorante_id, file_origine, "
            "numero_riga, data_documento, fornitore, descrizione, categoria, "
            "quantita, prezzo_unitario, totale_riga, categoria_fonte, "
            "categoria_fiducia) VALUES (%s, %s, 'molte.xml', %s, '2026-03-10', "
            "'Fornitore', 'riga', 'CARNE', 1, 10.00, 10.00, 'L2_locale', 'certa')",
            [(UTENTE, SEDE, n) for n in range(100, 100 + extra)],
        )

    out = _esegui(db_sql, monkeypatch, capsys)
    # 4 seminate con provenienza + le extra, tutte contate una volta sola
    assert f"Su {4 + extra} righe con provenienza:" in out
    riga = next(r for r in out.splitlines() if "deciso prima del modello" in r)
    assert str(2 + extra) in riga, riga

    # Nota onesta sul limite di questo test: togliere `.order("id")` dallo script
    # NON lo fa fallire. Misurato affiancando le due versioni su 1.500 righe:
    # stessi 1.500 id distinti, zero mancanti. Una tabella appena seminata dentro
    # una transazione, senza scritture concorrenti, torna comunque in ordine
    # fisico. La divergenza del 10/09/2026 (653 id persi su 3.067) richiede una
    # tabella che cambia sotto la paginazione: non riproducibile qui.
    # `.order("id")` resta nello script perche' la' fuori quel caso e' reale.
