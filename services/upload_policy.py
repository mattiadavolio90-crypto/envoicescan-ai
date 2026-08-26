"""Policy sulle date dei documenti caricati.

Le due regole (blocco anno precedente, blocco mesi precedenti) esistevano solo
dentro `upload_handler.handle_uploaded_files`, cioe' il percorso Streamlit, che
non e' piu' raggiungibile: il frontend Next.js carica via POST /api/upload/invoice
sul worker, dove i controlli non erano mai stati portati. Il risultato e' che i
flag in `pagine_abilitate` erano interruttori spenti — un cliente reale aveva
`blocco_mesi_precedenti: true` credendolo attivo.

Qui la regola sta in un posto solo, senza dipendere da `st.session_state`, cosi'
il worker la applica davvero e i test la esercitano direttamente.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional, Tuple

BLOCCO_ANNO = "anno_precedente"
BLOCCO_MESE = "mese_precedente"

BLOCCO_ANNO_KEY = "blocco_anno_precedente"
BLOCCO_MESI_KEY = "blocco_mesi_precedenti"


def _parse_data_documento(value: Any) -> Optional[date]:
    """Data del documento come `date`, o None se assente/illeggibile.

    None significa "non decidibile": il chiamante lascia passare. Bloccare su una
    data non parsabile trasformerebbe un difetto di parsing in una fattura
    rifiutata, che e' il danno peggiore fra i due.
    """
    if value in (None, "", "N/A", "None"):
        return None
    if isinstance(value, date):
        return value
    try:
        import pandas as pd

        dt = pd.to_datetime(value, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.date()
    except Exception:
        return None


def _mese_precedente(oggi: date) -> Tuple[int, int]:
    return (oggi.year - 1, 12) if oggi.month == 1 else (oggi.year, oggi.month - 1)


def valuta_policy_data(
    data_documento: Any,
    pagine_abilitate: Optional[Dict[str, Any]],
    is_admin: bool = False,
    is_trial: bool = False,
    oggi: Optional[date] = None,
) -> Optional[str]:
    """Restituisce il tipo di blocco applicabile, o None se la fattura passa.

    Admin (anche in impersonificazione) bypassano sempre: e' il canale con cui si
    correggono i caricamenti storici dei clienti.

    I trial hanno una policy propria (mese corrente + precedente) che coincide con
    `blocco_mesi_precedenti`, quindi per loro quel flag non aggiunge nulla e non
    viene valutato due volte.
    """
    if is_admin:
        return None

    data = _parse_data_documento(data_documento)
    if data is None:
        return None

    oggi = oggi or date.today()
    cfg = pagine_abilitate if isinstance(pagine_abilitate, dict) else {}

    # Default True come nel percorso storico. Il confronto NON e' `data.year <
    # oggi.year` secco: a gennaio bloccherebbe le fatture di dicembre, che e' il
    # caso normale (arrivano quasi tutte nelle prime settimane dell'anno dopo).
    # Nel percorso storico non si vedeva perche' quel codice non girava; qui gira,
    # e il 1/1/2027 avrebbe rifiutato dicembre 2026 a TUTTI i clienti — nessuno ha
    # la chiave configurata, quindi tutti prendono il default.
    # Il mese precedente resta sempre ammesso; a decidere su di esso e' semmai
    # blocco_mesi_precedenti, che e' la regola piu' stretta e piu' esplicita.
    if cfg.get(BLOCCO_ANNO_KEY, True) and data.year < oggi.year:
        if (data.year, data.month) != _mese_precedente(oggi):
            return BLOCCO_ANNO

    consenti_mese_prec = is_trial or bool(cfg.get(BLOCCO_MESI_KEY, False))
    if consenti_mese_prec:
        ammessi = {(oggi.year, oggi.month), _mese_precedente(oggi)}
        if (data.year, data.month) not in ammessi:
            return BLOCCO_MESE

    return None


MESSAGGI = {
    BLOCCO_ANNO: (
        "ANNO PRECEDENTE — La data documento ({data}) è precedente al 1 Gennaio "
        "{anno}. È possibile caricare solo fatture dell'anno corrente."
    ),
    BLOCCO_MESE: (
        "MESE NON CONSENTITO — La data documento ({data}) non rientra nei mesi "
        "consentiti: {mese_prec} o {mese_corr}. È possibile caricare solo "
        "fatture del mese corrente o del mese precedente."
    ),
}


def messaggio_blocco(kind: str, data_documento: Any, oggi: Optional[date] = None) -> str:
    """Testo mostrato al cliente, per intero e cosi' com'e'.

    Il frontend NON lo interpreta: `upload-modal.tsx` stampa `entry.error` grezzo.
    I prefissi `ANNO PRECEDENTE` / `MESE NON CONSENTITO` restano per continuita'
    con il percorso storico ed erano letti da `upload_handler._get_policy_block_kind`,
    che oggi e' codice morto — non sono un contratto con la UI.
    """
    from config.constants import MESI_ITA

    oggi = oggi or date.today()
    prev_anno, prev_mese = _mese_precedente(oggi)
    # MESI_ITA e' un dict 1-indexed (1='GENNAIO'), non una lista: il "- 1" del
    # blocco storico in upload_handler nominava il mese sbagliato. Non se n'era
    # accorto nessuno perche' quel percorso non veniva piu' eseguito.
    # L'anno va accanto a OGNI mese: a gennaio i due mesi ammessi stanno in anni
    # diversi ("Dicembre 2026 o Gennaio 2027") e un anno solo ne indicava uno falso.
    return MESSAGGI[kind].format(
        data=data_documento,
        anno=oggi.year,
        mese_corr=f"{MESI_ITA[oggi.month].capitalize()} {oggi.year}",
        mese_prec=f"{MESI_ITA[prev_mese].capitalize()} {prev_anno}",
    )
