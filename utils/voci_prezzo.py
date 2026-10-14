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


def una_riga_per_documento(
    df,
    *,
    chiavi,
    file,
    data,
    prezzo,
    quantita,
    unita=None,
    somme=(),
    massimo=(),
):
    """Un acquisto per documento: le righe dello stesso prodotto nella stessa
    fattura diventano una.

    Lo stesso prodotto su piu' righe della stessa fattura contava come piu'
    acquisti: l'«ultimo» e il «penultimo» potevano stare nella stessa fattura
    (ORTOFRUTTA 2,88 -> 3,83 -> 2,88 nella 39/FA, screenshot di Mattia del
    14/10/2026) e, misurato in catena, su 2.947 prodotti in 556 lo erano.

    - Gruppo: `chiavi` (sede, prodotto, fornitore) + `file` + `data` + unita'
      di misura (UPPER/TRIM). Unita' diverse nella stessa fattura NON si fondono
      (decisione di Mattia, 14/10/2026: un cartone mediato con un pezzo da' un
      prezzo senza senso e spegnerebbe «Confezione diversa?»).
    - Prezzo: media ponderata sulle quantita' positive (`quantita` mancante =
      1), media semplice se nessuna lo e'; arrotondato a 6 decimali come nella
      RPC. Non totale/quantita': sul live 803 righe se ne scostano oltre l'1%
      (sconti in riga).
    - `quantita` e le colonne in `somme` si sommano, quelle in `massimo`
      prendono il massimo (in ordine di codepoint, come `COLLATE "C"` in SQL),
      tutte le altre il valore della prima riga.
    - Righe senza `file` restano acquisti a se'.
    - Il risultato e' ordinato per chiavi, data, file, unita' con un
      ordinamento stabile: lo stesso spareggio della RPC `gruppo_prezzi_catena`.
    """
    import pandas as pd

    chiavi = list(chiavi)
    if df.empty:
        return df.copy()
    lavoro = df.copy()
    lavoro["__q"] = pd.to_numeric(lavoro[quantita], errors="coerce").fillna(1.0)
    lavoro["__p"] = pd.to_numeric(lavoro[prezzo], errors="coerce").fillna(0.0)
    # Pesano solo le quantita' positive: uno storno (quantita' negativa nella
    # stessa fattura) darebbe un prezzo d'acquisto negativo.
    lavoro["__qp"] = lavoro["__q"].where(lavoro["__q"] > 0, 0.0)
    lavoro["__pq"] = lavoro["__p"] * lavoro["__qp"]
    lavoro["__u"] = (
        lavoro[unita].fillna("").astype(str).str.strip().str.upper() if unita else ""
    )
    senza_file = lavoro[file].isna() | (lavoro[file].astype(str).str.strip() == "")
    lavoro["__f"] = lavoro[file].where(~senza_file, "").astype(str)
    lavoro["__solo"] = pd.Series(range(len(lavoro)), index=lavoro.index).where(senza_file, -1)
    lavoro["__d"] = lavoro[data].astype(str)
    lavoro["__pos"] = range(len(lavoro))

    gruppo = chiavi + ["__f", "__d", "__u", "__solo"]
    speciali = {"__q", "__qp", "__p", "__pq", "__u", "__f", "__d", "__solo", "__pos", quantita, prezzo, file, data}
    if unita:
        speciali.add(unita)
    altre = [c for c in lavoro.columns if c not in gruppo and c not in speciali]
    da_sommare = [c for c in altre if c in somme]
    da_massimo = [c for c in altre if c in massimo]
    prime = [c for c in altre if c not in somme and c not in massimo] + [data] + ([unita] if unita else [])
    for c in da_sommare:
        lavoro[c] = pd.to_numeric(lavoro[c], errors="coerce")
    # Il massimo sul testo, gruppo per gruppo, pandas lo fa in Python (4 s su
    # 40.000 righe): passa dal rango, che si confronta in C, e torna al testo.
    valori_massimo = {}
    for c in da_massimo:
        testo = lavoro[c].where(lavoro[c].isna(), lavoro[c].astype(str))
        lavoro[c] = testo.rank(method="dense")
        presenti = testo.notna()
        valori_massimo[c] = dict(zip(lavoro.loc[presenti, c], testo[presenti]))

    g = lavoro.groupby(gruppo, sort=False, dropna=False)
    out = g[["__q", "__qp", "__pq"]].sum()
    out["__p"] = g["__p"].mean()
    if da_sommare:
        out[da_sommare] = g[da_sommare].sum(min_count=1)
    if da_massimo:
        out[da_massimo] = g[da_massimo].max()
        for c in da_massimo:
            out[c] = out[c].map(valori_massimo[c]).astype(object)
            out.loc[out[c].isna(), c] = None
    prima = g["__pos"].min()
    out[prime] = lavoro[prime].iloc[prima.to_numpy()].to_numpy()
    out = out.reset_index()
    out[quantita] = out["__q"]
    # Arrotondato a 6 decimali come `round(..., 6)` nella RPC: senza, 1,71 x 40
    # / 40 in virgola mobile fa 1,7100000000000002, e un calo di esattamente il
    # 5% scendeva a 4,99999% e spariva dal PV ma non dalla catena (trovato il
    # 14/10/2026 su PASTO DI GRANO di H.D. ITALIA).
    ponderato = out["__pq"] / out["__qp"].where(out["__qp"] > 0, 1.0)
    out[prezzo] = ponderato.where(out["__qp"] > 0, out["__p"]).round(6)
    out[file] = out["__f"].where(out["__solo"] < 0, None)
    out = out.sort_values(chiavi + ["__d", "__f", "__u", "__solo"], kind="mergesort")
    return out.drop(columns=["__q", "__qp", "__p", "__pq", "__u", "__f", "__d", "__solo"], errors="ignore").reset_index(drop=True)


def chiave_documento(riga, *, file="file_origine", data="data_documento", unita="unita_misura", indice=None):
    """La chiave di «un acquisto» per righe in forma di dizionario, gemella di
    `una_riga_per_documento`: file + data + unita' (UPPER/TRIM). Una riga senza
    file e' un acquisto a se' (serve `indice`, unico per riga)."""
    f = str(riga.get(file) or "")
    u = str(riga.get(unita) or "").strip().upper()
    d = str(riga.get(data) or "")
    if not f.strip():
        return ("", d, u, indice)
    return (f, d, u, None)


def prezzo_documento(righe, *, prezzo="prezzo_unitario", quantita="quantita"):
    """Il prezzo di un acquisto (righe dello stesso prodotto nella stessa
    fattura), gemello di `una_riga_per_documento` per chi lavora su dizionari:
    media ponderata sulle quantita' positive delle righe a prezzo positivo
    (quantita' mancante = 1), media semplice se nessuna e' positiva, 6 decimali.
    None se nessuna riga ha un prezzo positivo (solo omaggi)."""
    validi = []
    for r in righe:
        try:
            p = float(r.get(prezzo))
        except (TypeError, ValueError):
            continue
        if not p > 0:
            continue
        q = r.get(quantita)
        try:
            q = 1.0 if q is None else float(q)
        except (TypeError, ValueError):
            q = 1.0
        validi.append((p, q))
    if not validi:
        return None
    positivi = [(p, q) for p, q in validi if q > 0]
    if positivi:
        return round(sum(p * q for p, q in positivi) / sum(q for _, q in positivi), 6)
    return round(sum(p for p, _ in validi) / len(validi), 6)
