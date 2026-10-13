"""Cosa NON e' un prezzo da confrontare: una sola definizione per tutta l'app.

La usano l'Osservatorio del PV e la scheda «Prezzi» di catena
(`services/routers/prezzi.py`, `gruppo.py`, e la RPC `gruppo_prezzi_catena` che
ne ha la gemella in SQL) e gli avvisi prezzi (`db_service.calcola_alert`: Home,
chat, notifiche dopo il caricamento, briefing). Due definizioni avevano gia'
fatto dire alla Home cose che l'Osservatorio non mostrava.

1. Le CAUZIONI non hanno un prezzo unitario: un deposito sui vuoti vale 0,03 o
   960 EUR a seconda dei fusti consegnati. Su OFFSIDE «ADDEBITO CAUZIONI» (in
   VARIE BAR per scelta del cliente, che non si tocca) portava l'impatto/mese
   dell'Osservatorio da +55 a -599 EUR. La lista e' stretta di proposito,
   misurata l'11/10/2026 su tutto il DB: «CAUZION» colpisce solo depositi,
   mentre «VUOTO» prende i croissant vuoti e «TRASPORTO» il mango «trasporto
   aereo».
2. Un prezzo che SALTA di 10 volte o piu' fra due acquisti non e' un rincaro:
   e' cambiata la confezione (bottiglia/cassa) o l'unita' (kg/cartone).
   Misurato sulle due catene: 7 variazioni su 333 e 1 su 27, tutte cosi', che
   spostavano l'impatto/mese di 1.400 EUR.
3. Il NUMERO D'ORDINE scritto nel nome del prodotto non fa un prodotto diverso:
   LA GE' GE' (pesce) appende «ORDER 2025916 (1014546)» a ogni consegna, e il
   raggruppamento per nome esatto faceva di 1.140 righe su 2.520 altrettante
   serie da un acquisto, senza mai una variazione ne' un avviso (misurato il
   13/10/2026: 70 nomi diversi per 19 prodotti veri; nessun altro fornitore
   scrive cosi'). La chiave del prodotto lo toglie; il nome a video pure. La
   RPC `gruppo_prezzi_catena` fa lo stesso in SQL (`\m` al posto di `\b`).

`utils/` non importa `services/`: lo possono importare tutti senza cicli.
"""
from __future__ import annotations

import re

VOCE_NON_PREZZO_REGEX = r"CAUZION"

SALTO_DA_CONTROLLARE = 10.0

# «ORDER 2025916 (1014546)», «ORDER 2009323(1005322)», «ORDER 41484 (122741) BRAVO»:
# la parola ORDER, il numero, e fra parentesi il riferimento opzionale.
NUMERO_ORDINE_REGEX = r"\s*\bORDER\s*\d+(\s*\(\s*\d+\s*\))?"
_NUMERO_ORDINE = re.compile(NUMERO_ORDINE_REGEX, re.IGNORECASE)


def maschera_voce_non_prezzo(descrizioni):
    """Serie booleana: True sulle descrizioni che non hanno un prezzo unitario."""
    return descrizioni.astype(str).str.upper().str.contains(VOCE_NON_PREZZO_REGEX, na=False, regex=True)


def togli_numero_ordine(descrizione) -> str:
    """La descrizione senza il numero d'ordine del fornitore, con il suo case."""
    return _NUMERO_ORDINE.sub("", str(descrizione)).strip()


def chiave_prodotto(descrizione) -> str:
    """Chiave di confronto di un prodotto: UPPER+TRIM senza numero d'ordine."""
    return togli_numero_ordine(descrizione).upper()


def chiavi_prodotto(descrizioni):
    """`chiave_prodotto` su una serie pandas."""
    return descrizioni.astype(str).str.replace(_NUMERO_ORDINE, "", regex=True).str.strip().str.upper()


def salto_da_controllare(a: float, b: float) -> bool:
    """True se fra i due prezzi c'e' un fattore `SALTO_DA_CONTROLLARE` o piu'."""
    a, b = abs(float(a)), abs(float(b))
    if min(a, b) <= 0:
        return max(a, b) > 0
    return max(a, b) / min(a, b) >= SALTO_DA_CONTROLLARE
