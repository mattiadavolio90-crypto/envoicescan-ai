"""La guardia che impedisce di salvare una config non caricata.

`config-assistente-catena.tsx` parte con `segnali`/`pv` a `[]`, e `[]` e' anche
il valore che il POST manda quando l'utente non ha escluso niente. I due stati
sono **indistinguibili guardando il payload** — lo dice gia'
`test_fotografa_liste_vuote_producono_liste_vuote` in
`test_catena_costi_gruppo_frontend.py`. Salvare mentre si e' nel primo stato
riattiva in silenzio tutto cio' che l'utente aveva escluso.

**Chi difende cosa, oggi (misurato il 03/09/2026).** Non e' `segnaliDisattivati`
/`pvEsclusi`: su `[]` qualunque loro mutazione da' `[]` (mutante *impossibile*,
non sopravvissuto). La difesa e' in due punti, e sono entrambi necessari:

  1. `caricaConfig().catch` -> `setLoadError(true)`     (riga ~55)
  2. `<Button onClick={salva} disabled={... || loadError}>` (riga ~195)

Togliere UNO dei due riapre il buco, e nessun test dell'area lo vedeva: questo
file lega i due punti fra loro.

**Perche' un test sul sorgente, qui.** La guardia vive dentro un componente
React, e `esegui_ts` non entra nei `.tsx` (helpers_ts.py: solo logica pura).
Estrarre `disabled={saving || loading || loadError}` in `lib/` per poterlo
testare sarebbe indirezione inventata per il test, non per il codice. Il test e'
quindi una **fotografia strutturale**, con il limite dichiarato: prova che i due
presidi esistono e sono collegati, non che React li renderizzi. E' la stessa
scelta gia' fatta da `test_il_dialog_hardcoda_ancora_le_aliquote`.

**Il perimetro che la guardia NON copre**, verificato sul backend il 03/09:
una risposta `200` con liste vuote lascerebbe il Salva abilitato. Oggi e'
irraggiungibile — `_resolve_gruppo` (services/routers/gruppo.py:674) solleva 400
sotto le 2 sedi, e `segnali` nasce da `_SEGNALI_CATALOGO`, mai vuoto — quindi
resta una fotografia, non un fix.
"""
import pathlib
import re

import pytest

_SORGENTE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/catena/config-assistente-catena.tsx"
)


@pytest.fixture(scope="module")
def testo() -> str:
    return _SORGENTE.read_text(encoding="utf-8")


def test_il_fallimento_del_load_alza_la_bandiera(testo):
    """Primo dei due presidi: senza questo, `loadError` resta false e il Salva
    e' abilitato su una config mai caricata."""
    catch = re.search(r"\.catch\(\(\)\s*=>\s*\{(.*?)\}\)", testo, re.S)
    assert catch is not None, (
        "il .catch di caricaConfig e' sparito: un load fallito non viene piu' "
        "intercettato e il componente resta con le liste vuote iniziali"
    )
    assert "setLoadError(true)" in catch.group(1), (
        "il .catch non alza piu' loadError: salvare dopo un load fallito "
        "manderebbe liste vuote, che il backend legge come 'niente escluso' — "
        "riattivando in silenzio i PV e i segnali esclusi dall'utente"
    )


def test_il_salva_e_disabilitato_quando_il_load_e_fallito(testo):
    """Secondo presidio. La bandiera senza il `disabled` non difende niente."""
    bottone = re.search(r"<Button\s+onClick=\{salva\}[^>]*?disabled=\{([^}]*)\}", testo, re.S)
    assert bottone is not None, (
        "il pulsante Salva non ha piu' un attributo `disabled`: la guardia sulle "
        "liste vuote e' scomparsa"
    )
    condizione = bottone.group(1)
    assert "loadError" in condizione, (
        f"il Salva non guarda piu' loadError (condizione: `{condizione}`): "
        "diventa possibile salvare una configurazione mai caricata"
    )


def test_lo_stato_iniziale_delle_due_liste_e_vuoto(testo):
    """Il presupposto che rende necessaria la guardia.

    Se un giorno lo stato iniziale diventasse `null` invece di `[]`, la
    distinzione 'non caricato' / 'niente escluso' esisterebbe nei dati e questa
    guardia d'interfaccia diventerebbe ridondante — allora questo file va
    riletto, non semplicemente aggiornato.
    """
    for stato in ("segnali", "pv"):
        assert re.search(rf"const \[{stato}, set\w+\] = useState<[^>]+>\(\[\]\)", testo), (
            f"lo stato `{stato}` non parte piu' da `[]`: se ora parte da null la "
            "guardia loadError potrebbe essere sostituita da un controllo sui dati"
        )
