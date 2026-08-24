"""`file_origine_gruppo` sugli articoli MISTI (righe proprie del PV + quota di gruppo).

Un articolo misto è quello comprato sia direttamente dal punto vendita sia via
documento di struttura ripartito. Correggerne la categoria richiede DUE scritture:
le righe proprie (categoria-batch, filtra per ristorante_id del PV) e il documento di
gruppo (riga-categoria, righe sulla sede tecnica).

Prima `file_origine_gruppo` veniva esposto solo quando `solo_gruppo` era True: sul
misto restava None, il frontend cadeva sul solo categoria-batch e la quota di gruppo
restava sulla categoria vecchia — continuando a pesare nel secchio MOL sbagliato
senza che nulla lo segnalasse. Qui si blocca quella regressione.
"""
import services.routers.fatture as fatture


def _riga(id_, desc, gruppo=False, file_origine=None, totale=10.0):
    return {
        "id": id_,
        "descrizione": desc,
        "categoria": "CARNE",
        "fornitore": "FORNITORE X",
        "totale_riga": totale,
        "quantita": 1,
        "prezzo_unitario": totale,
        "data_documento": "2026-08-10",
        "created_at": "2026-08-10T10:00:00+00:00",
        "needs_review": False,
        "ripartita_su_gruppo": gruppo,
        "file_origine": file_origine,
        "unita_misura": "KG",
    }


def _aggrega(rows):
    """Esegue la sola aggregazione di get_articoli_aggregati, senza rete/DB."""
    import services.routers.fatture as f
    from unittest.mock import MagicMock, patch

    sb = MagicMock()
    sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = (
        MagicMock(data={"nuovi_da": "2026-01-01T00:00:00+00:00"})
    )
    with patch.multiple(
        f,
        _resolve_user_from_token=MagicMock(return_value={"id": "user-1"}),
        _resolve_ristorante_id=MagicMock(return_value="pv-1"),
        _get_supabase_client=MagicMock(return_value=sb),
        _fetch_fatture_rows=MagicMock(return_value=rows),
    ):
        return f.get_articoli_aggregati(authorization="Bearer x").articoli


def test_articolo_misto_espone_file_origine_gruppo():
    """Il caso della regressione: senza questo, la quota di gruppo non veniva corretta."""
    rows = [
        _riga(1, "HAMBURGER", gruppo=False),
        _riga(-2, "HAMBURGER", gruppo=True, file_origine="IT123_struttura.xml"),
    ]
    art = next(a for a in _aggrega(rows) if a.descrizione == "HAMBURGER")
    assert art.ripartita_su_gruppo is True
    assert art.solo_gruppo is False, "ha anche righe proprie del PV"
    assert art.file_origine_gruppo == "IT123_struttura.xml", (
        "il misto deve dire su QUALE documento di struttura agire"
    )


def test_articolo_solo_gruppo_invariato():
    rows = [_riga(-1, "CANONE", gruppo=True, file_origine="IT999_canone.xml")]
    art = next(a for a in _aggrega(rows) if a.descrizione == "CANONE")
    assert art.solo_gruppo is True
    assert art.file_origine_gruppo == "IT999_canone.xml"


def test_articolo_senza_gruppo_non_espone_documento():
    rows = [_riga(1, "PANE", gruppo=False)]
    art = next(a for a in _aggrega(rows) if a.descrizione == "PANE")
    assert art.ripartita_su_gruppo is False
    assert art.solo_gruppo is False
    assert art.file_origine_gruppo is None


def test_file_origine_gruppo_ignora_righe_gruppo_senza_documento():
    """Se la prima riga di gruppo non porta file_origine si prende la prima che ce l'ha:
    prenderla posizionalmente restituiva None e riapriva il buco."""
    rows = [
        _riga(1, "OLIO", gruppo=False),
        _riga(-2, "OLIO", gruppo=True, file_origine=None),
        _riga(-3, "OLIO", gruppo=True, file_origine="IT777_struttura.xml"),
    ]
    art = next(a for a in _aggrega(rows) if a.descrizione == "OLIO")
    assert art.file_origine_gruppo == "IT777_struttura.xml"
