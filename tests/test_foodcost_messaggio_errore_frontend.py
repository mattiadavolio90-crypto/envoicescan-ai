"""Il motivo del rifiuto arriva all'utente, non solo nei log.

`calcola_ricetta` (services/foodcost_service.py) prima saltava in silenzio una
riga ingrediente non calcolabile e restituiva un foodcost piu' basso del vero.
Ora rifiuta con 422 e nel `detail` dice QUALE ingrediente non torna — ma il
messaggio serve a qualcosa solo se arriva a schermo: due punti del frontend
facevano `throw new Error()` e mostravano un generico "Errore salvataggio".

Qui si esegue il TypeScript **vero** con node (tests/helpers_ts.py), non una
copia della logica. Casi coperti perche' sono quelli che capitano davvero:
- FastAPI usa `detail` come stringa (HTTPException) e come array di oggetti
  (validazione Pydantic): il secondo, passato a un toast, stampa
  "[object Object]";
- la risposta puo' non essere JSON affatto (502/504 di Railway, pagina HTML):
  il chiamante passa `null` e ci si deve poter cadere sopra senza rompere.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/foodcost"
RICHIEDE = ("messaggioErroreRisposta",)


def _msg(corpo, fallback="Errore salvataggio"):
    return esegui_ts(
        MODULO,
        "emit(m.messaggioErroreRisposta(input.corpo, input.fallback));",
        {"corpo": corpo, "fallback": fallback},
        richiede=RICHIEDE,
    )


def test_detail_stringa_arriva_all_utente():
    corpo = {"detail": "Impossibile calcolare il costo di SALSA: could not convert string to float"}
    assert "SALSA" in _msg(corpo)


def test_senza_detail_resta_il_messaggio_generico():
    assert _msg({"altro": "x"}) == "Errore salvataggio"


def test_corpo_non_json_non_rompe_il_toast():
    """Il chiamante fa `.catch(() => null)` su una risposta non-JSON."""
    assert _msg(None) == "Errore salvataggio"


def test_detail_array_di_pydantic_non_stampa_object_object():
    """422 di validazione: detail e' una lista di oggetti, non una stringa."""
    corpo = {"detail": [{"loc": ["body", "righe", 0], "msg": "field required", "type": "value_error"}]}
    out = _msg(corpo)
    assert "object Object" not in out
    assert "field required" in out


def test_detail_stringa_vuota_non_svuota_il_toast():
    """Un detail vuoto non deve produrre un toast senza testo."""
    assert _msg({"detail": "   "}) == "Errore salvataggio"


@pytest.mark.parametrize("corpo", [None, {}, {"detail": None}, {"detail": []}, {"detail": 42}, "stringa"])
def test_mai_una_stringa_vuota_qualunque_sia_il_corpo(corpo):
    out = _msg(corpo)
    assert isinstance(out, str) and out.strip(), f"toast vuoto per {corpo!r}"
