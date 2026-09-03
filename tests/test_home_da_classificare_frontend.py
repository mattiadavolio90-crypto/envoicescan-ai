"""La card «Righe da classificare» della Home: la logica di stato, eseguita davvero.

`lib/home-da-classificare.ts` decide cosa vede il cliente: verde solo a zero
righe VERE, errore quando il dato manca (mai il verde — la lezione di
card-segnali), contatore + € quando c'è da fare. Qui si esegue il modulo vero
con node (tests/helpers_ts.py): il rendering della card resta fuori, come per
tutta la logica frontend.
"""
from tests.helpers_ts import esegui_ts

MODULO = "lib/home-da-classificare"
RICHIESTE = ("statoCardDaClassificare", "vociSenzaClassificate")


def _stato(argomento):
    return esegui_ts(
        MODULO,
        "emit(m.statoCardDaClassificare(input));",
        argomento=argomento,
        richiede=RICHIESTE,
    )


def test_salute_nulla_e_errore_non_verde():
    """Worker giù: la card non può dire «tutto classificato»."""
    assert _stato(None) == {"stato": "errore"}


def test_dato_assente_e_errore_non_verde():
    """Backend vecchio o query fallita lato worker (da_classificare null/assente)."""
    assert _stato({"da_classificare": None}) == {"stato": "errore"}
    assert _stato({}) == {"stato": "errore"}


def test_zero_righe_e_il_verde_che_insegna():
    out = _stato({"da_classificare": {"righe": 0, "importo": 0}})
    assert out["stato"] == "ok"
    assert out["titolo"] == "Tutte le righe sono classificate"


def test_righe_presenti_contatore_importo_e_deep_link():
    # 12.400 e non 1.240: il CLDR italiano raggruppa le migliaia solo da 5 cifre
    # in su (minimumGroupingDigits=2), quindi 1240 -> "1240 €" È corretto e un
    # assert su "1.240" boccerebbe il comportamento vero di tutta l'app.
    out = _stato({"da_classificare": {"righe": 12, "importo": 12400}})
    assert out["stato"] == "righe"
    assert out["titolo"] == "12 righe da classificare"
    assert "12.400" in out["sottotitolo"]
    assert "esclusi da margini e food cost" in out["sottotitolo"]
    assert out["href"] == "/analisi-fatture?tab=articoli&verifica=1"


def test_una_riga_sola_parla_al_singolare():
    out = _stato({"da_classificare": {"righe": 1, "importo": 59.7}})
    assert out["titolo"] == "1 riga da classificare"
    assert out["sottotitolo"].endswith("non la sistemi")


def test_la_promozione_toglie_solo_la_voce_classificate():
    """Desktop: la voce esce dall'elenco della card Salute (il dato vive nella
    card grande). Le altre voci restano, nello stesso ordine — e l'indice non
    passa di qui: è calcolato dal backend."""
    voci = [
        {"key": "fatture", "label": "Fatture caricate", "ok": True, "dettaglio": "", "cta_page": None},
        {"key": "classificate", "label": "Righe classificate", "ok": False, "dettaglio": "", "cta_page": None},
        {"key": "personale", "label": "Costo personale", "ok": True, "dettaglio": "", "cta_page": None},
    ]
    out = esegui_ts(
        MODULO,
        "emit(m.vociSenzaClassificate(input).map((v) => v.key));",
        argomento=voci,
        richiede=RICHIESTE,
    )
    assert out == ["fatture", "personale"]
