"""Consumi mensili per sede e confronto con la soglia del piano (pannello admin).

Logica PURA: nessuna query, nessun client Supabase. Le RPC (`admin_consumi_mensili`,
`admin_ai_mensile`) fanno l'aggregazione nel DB; qui si combinano le righe con
l'anagrafica sede e si decide chi e' sopra soglia.

La separazione e' voluta: la soglia e' una condizione su un confronto numerico, e
in questo progetto una guardia su soglia gia' e' passata inosservata perche'
testata solo attraverso un mock che rispondeva comunque. Tenendo la decisione in
funzioni pure la si prova sui valori veri, senza simulare il DB.
"""
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from config.constants import PIANO_LIMITI_FATTURE_MESE, PIANO_LIMITE_FATTURE_DEFAULT

PIANO_DEFAULT = "base"


def piano_effettivo(sede_piano: Optional[str], account_piano: Optional[str]) -> str:
    """Piano della sede, altrimenti dell'account, altrimenti 'base'.

    Stessa catena di _resolve_piano_effettivo nel worker, ma senza I/O. Serve
    davvero: 2 clienti su 7 hanno account e sede su piani diversi (account 'free'
    con sede 'base'), quindi leggere il piano dall'account darebbe il limite sbagliato.
    """
    for candidato in (sede_piano, account_piano):
        if candidato and str(candidato).strip():
            return str(candidato).lower().strip()
    return PIANO_DEFAULT


def limite_piano(piano: Optional[str]) -> int:
    """Fatture/mese incluse nel piano. Un piano sconosciuto ricade sul default."""
    chiave = (piano or "").lower().strip()
    return PIANO_LIMITI_FATTURE_MESE.get(chiave, PIANO_LIMITE_FATTURE_DEFAULT)


def sopra_soglia(totale: int, limite: int) -> bool:
    """True quando il mese ha superato il limite del piano.

    Strettamente maggiore: consumare esattamente il monte incluso NON e' uno
    sforamento (200 su 200 e' dentro, 201 e' fuori).
    """
    return totale > limite


def costruisci_righe(
    consumi: Iterable[Dict[str, Any]],
    ai: Iterable[Dict[str, Any]],
    sedi: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Unisce conteggi fatture, consumi AI e anagrafica sede in righe sede x mese.

    `sedi` porta gia' solo le sedi ammesse (non tecniche, non admin): una riga di
    consumo che non trova la sua sede viene scartata, cosi' un filtro applicato a
    monte non puo' essere aggirato da questa funzione.
    """
    per_sede = {str(s["id"]): s for s in sedi}

    ai_index: Dict[tuple, Dict[str, Any]] = {}
    for r in ai:
        ai_index[(str(r.get("ristorante_id")), r.get("mese"))] = r

    righe: List[Dict[str, Any]] = []
    for r in consumi:
        rid = str(r.get("ristorante_id"))
        sede = per_sede.get(rid)
        if sede is None:
            continue

        piano = piano_effettivo(sede.get("piano"), sede.get("account_piano"))
        limite = limite_piano(piano)
        tot = int(r.get("tot") or 0)
        uso_ai = ai_index.get((rid, r.get("mese")), {})

        righe.append({
            "ristorante_id": rid,
            "sede": sede.get("nome_ristorante") or "",
            "email": sede.get("email") or "",
            "mese": r.get("mese"),
            "manuali": int(r.get("manuali") or 0),
            "sdi": int(r.get("sdi") or 0),
            "totale": tot,
            "piano": piano,
            "limite": limite,
            "sopra_soglia": sopra_soglia(tot, limite),
            "ai_richieste": int(uso_ai.get("richieste") or 0),
            "ai_token": int(uso_ai.get("token") or 0),
            "ai_costo": round(float(uso_ai.get("costo") or 0.0), 4),
        })

    righe.sort(key=lambda x: (x["mese"], x["totale"]), reverse=True)
    return righe


def conta_sopra_soglia(righe: Iterable[Dict[str, Any]], mesi: Iterable[str]) -> int:
    """Sedi sopra soglia nei mesi indicati — il numero del badge rosso in home admin.

    Prende le stesse righe che la pagina mostra, cosi' badge e tabella non possono
    divergere.

    Accetta piu' di un mese di proposito: guardando solo il mese CORRENTE il badge
    si azzera ogni primo del mese e uno sforamento chiuso il 31 non verrebbe mai
    visto (il 1/9/2026 il mese corrente era vuoto mentre agosto era a 214/200).
    Una sede sforata piu' mesi conta una volta sola: il badge conta sedi, non mesi.
    """
    voluti = set(mesi)
    return len({
        r.get("ristorante_id")
        for r in righe
        if r.get("mese") in voluti and r.get("sopra_soglia")
    })


def primo_mese_finestra(oggi: date, mesi: int) -> date:
    """Primo giorno del mese piu' vecchio da includere in una finestra di N mesi.

    Aritmetica sui mesi, non sui giorni: sottrarre `31 * (mesi - 1)` giorni eccede
    sempre, perche' i mesi da 31 giorni non sono tutti (con mesi=12 si scaricavano
    13 mesi, con mesi=2 se ne scaricavano 3 in 5 mesi su 12). L'eccesso non
    sballava i numeri — il badge filtra per mese esatto e la tabella mostrava solo
    righe in piu' — ma rendeva `mesi` un contratto che il codice non rispettava.
    """
    mesi = max(int(mesi), 1)
    indice = oggi.year * 12 + (oggi.month - 1) - (mesi - 1)
    return date(indice // 12, indice % 12 + 1, 1)


def mesi_badge(mese_corrente: str) -> List[str]:
    """Mese corrente + precedente, nel formato 'YYYY-MM' usato dalle RPC."""
    anno, mese = (int(x) for x in mese_corrente.split("-"))
    prec_anno, prec_mese = (anno - 1, 12) if mese == 1 else (anno, mese - 1)
    return [mese_corrente, f"{prec_anno:04d}-{prec_mese:02d}"]
