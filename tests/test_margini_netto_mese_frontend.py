"""`fetchNettoMese` sceglie fra due fonti di ricavi, e la scelta vale decine di migliaia di euro.

La tabella `ricavi_giornalieri` e' grezza: quando il mese e' in modalita' "mensile"
l'override in `ricavi_modalita_mensile` ha la precedenza, e le righe giornaliere
rimaste sono dati orfani. Il gate che decide e' UNA riga
(`if (modalita?.modalita === "mensile")`), e finora non aveva un test.

**L'esposizione e' misurata, non stimata.** Interrogando il DB di produzione il
31/08/2026 (join `ricavi_modalita_mensile` x `ricavi_giornalieri` sullo stesso
mese-sede, netto calcolato con lo stesso scorporo del codice):

    giugno 2026:  override 73.322 EUR  vs  giornalieri 3.227 EUR
    maggio 2026:  override 80.550 EUR  vs  giornalieri 80.551 EUR

Su giugno il ramo sbagliato mostra **70.095 EUR** di differenza. Non solleva
nessun errore: mostra solo un numero. E' la classe di difetto piu' costosa del
progetto, la stessa di F7 e F1.

**Perche' `null` e `0` non sono la stessa cosa.** Il commento a `periodi.ts:121`
lo dichiara e questo file lo prova: `netto: null` significa "la lettura e'
fallita", `netto: 0` significa "zero vero". Il chiamante (`analisi-tab.tsx:151`,
`setField`) usa questo valore come **base delle percentuali che l'utente salva a
DB**: quando l'errore veniva degradato a 0, ogni percentuale digitata valeva
0 EUR. Il difetto e' gia' stato corretto una volta; i mutanti A3/A4/A7 qui sotto
esistono perche' non torni.

**Come si testa una funzione che fa `fetch`.** L'helper `esegui_ts` stubba
`globalThis.fetch` a `throw` nel prologo (rete vietata nei test). Ma il prologo
viene concatenato PRIMA dell'espressione, quindi l'espressione puo' riassegnare
`globalThis.fetch` con uno stub proprio: e' quello che fa `_netto()` qui sotto.
Non serve estrarre nulla dal modulo, e non serve toccare `helpers_ts.py`.
Tecnica riusabile per qualunque funzione async del frontend.

Attenzione per chi estende questo file: se lo stub dimentica un ramo, node muore
con un `TypeError` dentro il sottoprocesso e pytest riporta
`assert returncode == 0` con lo stderr di node — non un assert leggibile. Il
messaggio vero e' in fondo allo stderr.
"""
import pytest

from tests.helpers_ts import esegui_ts

MODULO = "app/(app)/margini/periodi"

# Lo stub registra anche le URL chiamate: alcuni difetti (la finestra giornaliera
# che sfora nel mese dopo) non cambiano il netto quando la risposta e' finta, e
# si vedono SOLO guardando cosa e' stato chiesto.
_STUB = """
const urls = [];
globalThis.fetch = async (url) => {
  urls.push(String(url));
  const r = String(url).includes("/api/ricavi/modalita") ? input.mod : input.giorn;
  if (!r.ok) return { ok: false };
  return { ok: true, json: async () => r.body };
};
emit({ res: await m.fetchNettoMese(input.anno, input.mese), urls });
"""


def _netto(anno=2026, mese=6, mod=None, giorn=None):
    """Chiama fetchNettoMese con le due risposte HTTP sotto controllo.

    `mod` / `giorn` sono {"ok": bool, "body": ...}: `ok=False` simula una
    risposta HTTP non-2xx, che sui due rami ha significati diversi.
    """
    return esegui_ts(
        MODULO,
        _STUB,
        argomento={
            "anno": anno,
            "mese": mese,
            "mod": mod if mod is not None else {"ok": True, "body": None},
            "giorn": giorn if giorn is not None else {"ok": True, "body": None},
        },
        richiede=["fetchNettoMese", "scorporoNetto"],
    )


def _mensile(iva10=0, iva22=0, altri=0):
    return {"ok": True, "body": {
        "modalita": "mensile",
        "fatturato_iva10": iva10,
        "fatturato_iva22": iva22,
        "altri_ricavi_noiva": altri,
    }}


# Gli importi sono scelti perche' il netto atteso sia un intero esatto: 1.10*8=8.80
# scorporato da' 8, 1.22*16=19.52 da' 16, e `altri` non si scorpora. Netto = 56.
# Cosi' un addendo che sparisce o che passa dall'aliquota sbagliata si legge dal
# totale senza ambiguita' su QUALE dei tre sia (8, 16, 32 sono potenze di 2).
_IVA10, _IVA22, _ALTRI = 1.10 * 8, 1.22 * 16, 32
_NETTO_ATTESO = 56


def test_override_mensile_vince_sui_giornalieri():
    """Il gate misurato a 70.095 EUR su giugno 2026.

    Le due fonti riportano numeri DIVERSI apposta: se il gate cade, il test
    legge il valore giornaliero e lo dice.
    """
    r = _netto(mod=_mensile(_IVA10, _IVA22, _ALTRI),
               giorn={"ok": True, "body": {"totale_netto": 9999}})

    assert r["res"] == {"netto": _NETTO_ATTESO, "mensile": True}, (
        "l'override mensile non ha la precedenza: la pagina mostrerebbe i "
        "giornalieri, che sotto un override sono dati orfani. Su giugno 2026 "
        "questo vale 3.227 EUR invece di 73.322 EUR"
    )


def test_senza_override_si_usano_i_giornalieri():
    r = _netto(mod={"ok": True, "body": None},
               giorn={"ok": True, "body": {"totale_netto": 3227}})
    assert r["res"] == {"netto": 3227, "mensile": False}


def test_modalita_diversa_da_mensile_non_attiva_il_gate():
    """`modalita` presente ma != "mensile" deve cadere sul ramo giornaliero.

    Uccide il mutante `if (true)`: con un body presente ma modalita' diversa,
    un gate sempre acceso scorporerebbe campi assenti e darebbe 0.
    """
    r = _netto(mod={"ok": True, "body": {"modalita": "giornaliera"}},
               giorn={"ok": True, "body": {"totale_netto": 512}})
    assert r["res"] == {"netto": 512, "mensile": False}, (
        "il gate si attiva su una modalita' che non e' 'mensile'"
    )


def test_lettura_fallita_e_zero_vero_restano_distinti():
    """LA distinzione che questo file esiste per proteggere.

    Un mese senza ricavi caricati e una lettura fallita danno numeri diversi:
    0 e null. Il chiamante usa il valore come base delle percentuali salvate a
    DB, quindi un errore degradato a 0 faceva valere 0 EUR ogni percentuale.
    """
    fallita = _netto(giorn={"ok": False})
    zero_vero = _netto(giorn={"ok": True, "body": {}})

    assert fallita["res"] == {"netto": None, "mensile": False}, (
        "una lettura fallita torna un numero invece di null: l'errore si "
        "traveste da mese senza incassi"
    )
    assert zero_vero["res"] == {"netto": 0, "mensile": False}, (
        "un mese davvero senza ricavi torna null invece di 0: il chiamante "
        "non riesce piu' a distinguere 'non lo so' da 'zero'"
    )
    assert fallita["res"]["netto"] is not zero_vero["res"]["netto"]


def test_override_con_campi_mancanti_non_produce_nan():
    """`?? 0` su ogni addendo: un campo assente vale zero, non NaN.

    NaN non solleva: si propaga silenzioso in ogni somma a valle.
    """
    r = _netto(mod={"ok": True, "body": {"modalita": "mensile",
                                         "fatturato_iva22": 1.22 * 16}})
    assert r["res"] == {"netto": 16, "mensile": True}, (
        "un campo assente nell'override produce NaN invece di 0"
    )


@pytest.mark.parametrize("anno,mese,ultimo", [
    (2024, 2, "29"),   # bisestile
    (2026, 2, "28"),   # non bisestile
    (2026, 6, "30"),
    (2026, 12, "31"),
    (2026, 1, "31"),
])
def test_la_finestra_giornaliera_copre_esattamente_il_mese(anno, mese, ultimo):
    """La URL si asserisce perche' il netto, con risposte finte, non cambierebbe.

    `new Date(anno, mese, 0)` e' l'ultimo giorno del mese richiesto (mese e'
    1-based qui, e il giorno 0 rende l'ultimo del mese precedente a `mese+1`).
    Un off-by-one qui chiede al server un mese sbagliato: nessun errore, dati
    di un altro periodo.
    """
    r = _netto(anno=anno, mese=mese, giorn={"ok": True, "body": {"totale_netto": 1}})
    giorn_url = next(u for u in r["urls"] if "/api/ricavi/giornalieri" in u)
    mm = f"{mese:02d}"

    assert f"data_da={anno}-{mm}-01" in giorn_url, (
        f"la finestra non parte dal primo del mese: {giorn_url}"
    )
    assert f"data_a={anno}-{mm}-{ultimo}" in giorn_url, (
        f"la finestra non finisce l'ultimo giorno di {mese}/{anno} (atteso "
        f"{ultimo}): sfora nel mese adiacente. URL: {giorn_url}"
    )


def test_entrambe_le_fonti_vengono_interrogate():
    """Le due fetch partono in parallelo: se una sparisce, un ramo e' irraggiungibile."""
    r = _netto(giorn={"ok": True, "body": {"totale_netto": 1}})
    assert len(r["urls"]) == 2, f"chiamate inattese: {r['urls']}"
    assert any("/api/ricavi/modalita?anno=2026&mese=6" in u for u in r["urls"])
    assert any("/api/ricavi/giornalieri?" in u for u in r["urls"])


def test_override_fallito_non_blocca_il_ramo_giornaliero():
    """Sul ramo `modalita` il null e' legittimo ("nessun override"), non un errore.

    Asimmetria voluta rispetto ai giornalieri, dichiarata nei commenti del
    sorgente: qui `.catch(() => null)`, li' `.catch(() => undefined)`.
    """
    r = _netto(mod={"ok": False}, giorn={"ok": True, "body": {"totale_netto": 64}})
    assert r["res"] == {"netto": 64, "mensile": False}, (
        "un override non leggibile impedisce di leggere i giornalieri"
    )
