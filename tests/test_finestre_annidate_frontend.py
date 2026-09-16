"""Chiudere due finestre alternate non lascia stato appeso.

Perche' esiste
==============
Portando "Spreco per categoria" fuori dal Dialog di "Margini e coperti" (una
modale alla volta invece di due impilate) e' comparso un difetto nuovo, che il
code-reviewer ha trovato e che nessun test vedeva: il componente in Catena e'
montato SEMPRE (`sintesi-catena.tsx:583` passa `open` come prop, non lo
renderizza condizionalmente), quindi il flag della finestra secondaria non viene
mai azzerato da uno smontaggio.

Prima della modifica il problema non esisteva: la secondaria stava dentro
l'albero del Dialog padre e spariva con lui.

Il caso che rompe
=================
Chiudere la coppia mentre la secondaria e' ancora segnata aperta. Alla
riapertura successiva l'utente chiede "Margini e coperti" e si ritrova davanti
"Categorie" — una finestra che non ha aperto lui. E' il motivo per cui
`mostraSecondaria` controlla ANCHE `aperta`, e non solo il proprio flag.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "lib/finestre-annidate"


def _stato(aperta, secondaria):
    return {"aperta": aperta, "secondariaAperta": secondaria}


def _mostra(stato):
    """(principale, secondaria) come le renderizzerebbe il componente."""
    return esegui_ts(
        MODULO,
        "emit([m.mostraPrincipale(input), m.mostraSecondaria(input)]);",
        argomento=stato,
        richiede=["mostraPrincipale", "mostraSecondaria"],
    )


def test_tutto_chiuso_non_mostra_niente():
    assert _mostra(_stato(False, False)) == [False, False]


def test_solo_la_principale():
    assert _mostra(_stato(True, False)) == [True, False]


def test_la_secondaria_copre_la_principale():
    """Una alla volta: e' la correzione delle due modali impilate."""
    assert _mostra(_stato(True, True)) == [False, True]


def test_il_flag_sopravvissuto_non_apre_niente():
    """Il difetto trovato dalla review.

    Chiusa la coppia con la secondaria ancora segnata aperta, il componente
    resta montato col flag a true. Alla riapertura l'utente deve vedere la
    principale, non la secondaria — e finche' `aperta` e' false non deve vedere
    proprio nulla.
    """
    assert _mostra(_stato(False, True)) == [False, False]


def test_mai_due_finestre_insieme():
    """L'invariante che da' il nome alla correzione: su OGNI combinazione di
    stato, al massimo una finestra e' a schermo. Se un domani qualcuno
    ricollegasse le due condizioni, questo test cade prima dell'utente."""
    for aperta in (True, False):
        for secondaria in (True, False):
            principale, sec = _mostra(_stato(aperta, secondaria))
            assert not (principale and sec), f"due finestre con {aperta=} {secondaria=}"


def test_a_finestre_chiuse_niente_e_a_schermo():
    """Nessuno stato con `aperta` false puo' mostrare qualcosa."""
    for secondaria in (True, False):
        assert _mostra(_stato(False, secondaria)) == [False, False]
