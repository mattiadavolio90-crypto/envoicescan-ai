"""In catena l'anteprima di una fattura legge la sede della fattura.

Perche' esiste
==============
`/api/scadenziario/anteprima` cerca le righe nella sede della sessione. Dalla
vista di gruppo (`/catena/fatture`) la fattura e' quasi sempre di un'altra sede:
l'anteprima rispondeva «Nessuna riga trovata.» (audit di ottobre 2026, 2.542
documenti su 2 catene). Con un omonimo `file_origine` sulla sede di sessione
avrebbe mostrato le righe di un altro documento.

In vista sede l'URL resta quello di prima: l'endpoint di gruppo richiede la
pagina Catena, che un account a sede singola o un sotto-utente senza Catena
non hanno.
"""
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from tests.helpers_ts import esegui_ts

MODULO = "lib/scadenziario"
CLIENT = (
    Path(__file__).resolve().parent.parent
    / "apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx"
)


def _url(doc, catena):
    return esegui_ts(
        MODULO,
        "emit(m.urlAnteprimaFattura(input.doc, input.catena));",
        {"doc": doc, "catena": catena},
        richiede=["urlAnteprimaFattura"],
    )


def test_in_catena_chiede_la_sede_della_fattura():
    url = _url({"file_origine": "IT01 & co.xml", "ristorante_id": "rB"}, True)
    parti = urlsplit(url)
    assert parti.path == "/api/gruppo/prezzi/fattura"
    assert parse_qs(parti.query) == {"ristorante_id": ["rB"], "file_origine": ["IT01 & co.xml"]}


def test_in_vista_sede_resta_l_anteprima_della_sessione():
    url = _url({"file_origine": "IT01 & co.xml", "ristorante_id": "rB"}, False)
    parti = urlsplit(url)
    assert parti.path == "/api/scadenziario/anteprima"
    assert parse_qs(parti.query) == {"file_origine": ["IT01 & co.xml"]}


def test_in_catena_senza_sede_ripiega_sull_anteprima_della_sessione():
    url = _url({"file_origine": "a.xml"}, True)
    assert urlsplit(url).path == "/api/scadenziario/anteprima"


def test_il_dialog_dello_scadenziario_usa_la_funzione():
    sorgente = CLIENT.read_text(encoding="utf-8")
    assert "fetch(urlAnteprimaFattura(doc, modalitaCatena))" in sorgente
    assert "fetch(`/api/scadenziario/anteprima" not in sorgente
