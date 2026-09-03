"""`card-segnali.tsx` resta senza test di logica, e questo file dice perché.

**Esclusione motivata, non una svista.** L'ultima passata su `catena/` lasciava
110 righe scoperte e le classificava «fetch + JSX». Ri-lette riga per riga il
03/09/2026: è esatto. I tre soli candidati all'estrazione in `lib/` non
sopravvivono all'esame:

1. `ICONA[s.tipo] ?? AlertTriangle` — lookup su un literal di 4 chiavi, nessun
   ramo da provare; il valore è un **componente React**, che in `lib/` non si
   può asserire senza renderizzare.
2. la guardia anti-race `my === reqRef.current` — vive su `useRef`. Estrarla
   vorrebbe dire inventare un contenitore di stato che il codice oggi non ha:
   indirezione creata per il test, non per il prodotto.
3. `loadError && !data` — decide *cosa mostrare*, cioè rendering. Ricade nella
   stessa esclusione strutturale già dichiarata per tutto il React del progetto
   (nessun runner in `apps/web/`: `deploy-vercel.yml` scatta su `apps/web/**`,
   e un test farebbe partire un deploy).

**Quello che invece un test lo merita**, ed è qui sotto: la card esiste per
avvisare, e l'unica regressione che conta è che un errore di rete diventi
silenzio rassicurante. Il commento nel sorgente lo dichiara («Un errore qui NON
può diventare "tutto sotto controllo"»); questi test lo legano, perché un
commento non è un presidio.

**Limite dichiarato:** fotografia strutturale sul sorgente, come
`test_catena_config_guardia_salva.py`. Prova che i rami esistono e sono
distinti, non che React li renderizzi.
"""
import pathlib
import re

import pytest

_SORGENTE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "apps/web/src/app/(app)/catena/card-segnali.tsx"
)


@pytest.fixture(scope="module")
def testo() -> str:
    return _SORGENTE.read_text(encoding="utf-8")


def test_un_errore_non_diventa_tutto_sotto_controllo(testo):
    """LA regressione che conta su questa card.

    `segnali.length === 0` è vero sia quando non c'è niente da segnalare sia
    quando il fetch è fallito (`data` resta null). Se il ramo d'errore sparisse,
    un disservizio mostrerebbe «Tutto sotto controllo, nessuna segnalazione» —
    una rassicurazione falsa su una card che esiste per allarmare.
    """
    i_errore = testo.find("loadError && !data")
    i_vuoto = testo.find("segnali.length === 0")

    assert i_errore != -1, (
        "il ramo d'errore è sparito da card-segnali: un fetch fallito ricadrebbe "
        "sul ramo 'nessuna segnalazione' e mostrerebbe «Tutto sotto controllo» "
        "mentre i punti vendita non sono stati controllati affatto"
    )
    assert i_vuoto != -1, "il ramo 'nessuna segnalazione' è sparito"
    assert i_errore < i_vuoto, (
        "il ramo 'nessuna segnalazione' viene prima di quello d'errore: un "
        "errore di rete verrebbe mostrato come «Tutto sotto controllo»"
    )


def test_l_errore_offre_un_riprova(testo):
    """Senza retry l'utente resta su una card cieca fino al reload della pagina."""
    assert re.search(r"onClick=\{carica\}", testo), (
        "il pulsante «Riprova» non richiama più `carica`: dopo un errore la card "
        "resta vuota e l'utente non ha modo di riprovare"
    )


def test_la_richiesta_ignora_le_risposte_sorpassate(testo):
    """La guardia anti-race, tenuta ferma qui perché in `lib/` non è estraibile.

    Senza `my === reqRef.current`, una risposta lenta di una richiesta vecchia
    sovrascrive quella nuova: la card mostra i segnali di uno stato precedente.
    """
    assert "++reqRef.current" in testo, (
        "il contatore di richiesta non viene più incrementato: due `carica()` "
        "sovrapposte non sono più distinguibili"
    )
    assert testo.count("my === reqRef.current") == 3, (
        "le tre guardie anti-race (then/catch/finally) non sono più tre: una "
        "risposta sorpassata può sovrascrivere lo stato della richiesta corrente"
    )


def test_niente_logica_pura_da_estrarre(testo):
    """La fotografia che giustifica l'esclusione.

    Se qualcuno aggiunge qui un calcolo (una soglia, un ordinamento, un
    aggregato), questo test diventa rosso: quella logica va in `lib/` e testata,
    non lasciata in un `.tsx` sotto l'ombrello di questa esclusione.
    """
    for vietato, perche in [
        (r"\.sort\(", "un ordinamento"),
        (r"\.reduce\(", "un aggregato"),
        (r"\.filter\(", "un filtro"),
    ]:
        assert not re.search(vietato, testo), (
            f"card-segnali.tsx ora contiene {perche}: non è più «fetch + JSX». "
            "L'esclusione motivata di questo file non vale più — estrai la "
            "logica in `lib/` e testala lì (vedi lib/catena-costi-gruppo.ts)"
        )
