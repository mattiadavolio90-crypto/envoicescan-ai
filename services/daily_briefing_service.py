"""Servizio Daily Briefing: genera e salva uno snapshot giornaliero delle notifiche.

Responsabilità:
- get_today_briefing   : legge snapshot di oggi da daily_briefing_state
- generate_and_save_briefing : costruisce snapshot deterministico + upsert su DB
- _build_snapshot      : logica pura di composizione bullets (no AI)

Quota bullet: 3 slot L1 (severity=error) + 2 slot L2 (warning/info).
Nessuna promozione di slot tra livelli.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
import re as _re
import hashlib

from config.logger_setup import get_logger

try:
    from zoneinfo import ZoneInfo
    _TZ_ROME = ZoneInfo("Europe/Rome")
except ImportError:
    _TZ_ROME = None

logger = get_logger('daily_briefing')

# ============================================================
# COSTANTI
# ============================================================

# Versione della LOGICA del briefing. Va incrementata a OGNI modifica che cambia
# come il briefing viene costruito (testi, conteggi, soglie, regole). Lo snapshot
# salvato la porta dentro: al load, se la versione salvata e' diversa da questa, lo
# snapshot e' STANTIO (generato dal codice vecchio) e va rigenerato — senza dover
# svuotare la cache a mano dopo ogni deploy. Vedi snapshot_is_stale().
#
# STORICO bump (per non perdere il filo):
#   1 -> baseline
#   2 -> 23/06: righe da controllare = totale, canale SDI da flag, tono testi
#   3 -> 25/06: costo personale mancante su TUTTI i mesi dell'anno (conteggio+range)
#   5 -> 28/06: "da controllare" conta PRODOTTI DISTINTI (non righe), per combaciare
#               col numero che il cliente vede in Analisi Fatture (fix 6 vs 4)
#   8 -> 21/07: safety net classifica_con_ai consulta la regola-fornitore mono-cat
#               (whitelist) sulle righe che la GPT lascia Da Classificare
#   9 -> 21/07: "CARTA PESCE"/"CARTA PER RAVIOLI" (imballo) non vengono piu' rubate
#               dalla regola forte PESCE/dizionario RAVIOLI (cert. SUSHILAND Villa Guardia)
#  10 -> 21/07: SAKE distinto bere(DISTILLATI)/cucina(SCATOLAME); "PESCE <animale
#               di terra>" non e' piu' PESCE; "FILTRO OLIO" officina -> MANUTENZIONE
#               (cert. SUSHILAND Vimodrone/San Giuliano)
_BRIEFING_CODE_VERSION = 12

# Quanto resta valido uno snapshot prima di essere comunque rigenerato (anche se
# nulla l'ha invalidato esplicitamente). Copre i dati che cambiano DURANTE il
# giorno senza un evento di invalidazione (es. righe classificate, fatture
# elaborate dal worker async): senza TTL il cliente vedrebbe il numero della
# mattina fino a mezzanotte. 30 min e' un buon compromesso freschezza/costo
# (la generazione pesante gira comunque in background, non blocca la Home).
_BRIEFING_TTL_MINUTI = 30

# Numero massimo di card mostrate in "Da fare oggi". Oltre questo numero,
# il resto resta nella pagina Avvisi (link "Vedi tutti"). Decisione Mattia 19/06:
# l'andamento sta nel testo del briefing, le card sono SOLO cose da fare -> 4.
_MAX_CARD = 4

# Topic che rappresentano un DATO STRUTTURALE MANCANTE del mese: senza questi i
# numeri di margine/MOL sono FALSI. Solo questi gateano il verde "tutto a posto":
# se ce n'e' anche solo uno, NON si puo' dire che e' tutto in ordine, a prescindere
# dal taglio a _MAX_CARD. Sono le stesse voci strutturali della card Salute.
# NB: incasso_mancante (rumore quotidiano: l'incasso di ieri si inserisce a fine
# giornata) e uncategorized_rows (task, non dato strutturale) NON sono qui: restano
# normali card da fare e non bloccano il verde quando sono l'unica cosa rimasta.
_TOPIC_DATO_MANCANTE_LABEL = {
    "fatturato_mancante": "il fatturato del mese",
    "costo_personale_mancante": "il costo del personale",
    "fatture_mancanti": "le fatture costo",
}

# Topic che il cliente NON puo' spegnere dal configuratore: sono guasti tecnici
# (perdita dati) e vanno sempre mostrati. Decisione Mattia (Step 6).
_TOPIC_NON_DISATTIVABILI = frozenset({'upload_failed', 'upload_ricavi_failed'})

# Un singolo interruttore del configuratore copre piu' topic del briefing quando
# appartengono allo stesso TEMA. Es: l'avviso "Scadenze" (key 'scadenza_superata')
# governa anche 'scadenza_imminente' — l'utente che spegne "Scadenze" si aspetta
# di non vedere ne' quelle superate ne' quelle in arrivo.
_TOPIC_SPENTO_ESTENDE: Dict[str, frozenset] = {
    'scadenza_superata': frozenset({'scadenza_superata', 'scadenza_imminente'}),
}


def espandi_topic_spenti(topics_disabled) -> set:
    """Espande le key spente del configuratore alle key 'figlie' dello stesso tema.

    Centralizzato: usato sia dal briefing (_build_snapshot) sia dal filtro
    notifiche (_filtra_notifiche_topic_spenti nel worker), cosi' un interruttore
    spegne ovunque tutti i topic del suo tema. Input malformato -> set vuoto.
    """
    if not isinstance(topics_disabled, (list, set, tuple)):
        return set()
    spenti: set = set()
    for t in topics_disabled:
        key = str(t)
        spenti |= set(_TOPIC_SPENTO_ESTENDE.get(key, frozenset({key})))
    return spenti

# Gerarchia TEMATICA delle card (decisa da Mattia, doc Punto 1/2).
# Regola d'oro: prima il TEMA, poi la gravita' DENTRO lo stesso tema.
# "Un upload mancato e' sempre piu' importante di un rincaro del 1000%."
# (piu' basso = prima). I numeri lasciano spazio per i topic futuri:
#   upload_ricavi_failed (Step 5) ~ 15, tra upload fatture e prezzi.
_TOPIC_PRIORITY: Dict[str, int] = {
    'onboarding':               -2,   # -2. Benvenuto cliente nuovo (apertura, prima di tutto)
    'rientro_assenza':          -1,   # -1. Bentornato al rientro (apertura, prima di tutto)
    'buona_notizia':             0,   # 0. Apertura positiva (NON e' una card to-do)
    'upload_failed':            10,   # 1. Upload fatture fallito
    'upload_ricavi_failed':     15,   # 2. Upload ricavi fallito (solo se mappato)
    'price_alert':              20,   # 3. Alert prezzi
    'uncategorized_rows':       30,   # 4. Righe dubbie da controllare
    'fatture_mancanti':         35,   #    Nessuna fattura caricata di recente (dato primario)
    'fatturato_mancante':       40,   # 5. Fatturato mancante (mese)
    'incasso_mancante':         45,   #    Incasso di ieri mancante (giorno), stesso tema
    'costo_personale_mancante': 50,   # 6. Costo personale mancante
    'scadenza_superata':        60,   # 7. Scadenze (superate prima delle imminenti)
    'scadenza_imminente':       61,   #    e imminenti subito dopo, stesso tema
    'coperti_anomalia':         65,   #    Anomalia coperti di ieri (segnale, non to-do)
    'appuntamento_imminente':   70,   # 8. Appuntamenti agenda (importanza medio/bassa: ultimo)
}

# Azione primaria suggerita per topic: (label_cta, pagina_destinazione).
# La pagina e' un fallback usato quando la notifica non porta un action_page
# proprio. La Home renderizza il bottone come link generico alla pagina.
_TOPIC_ACTION: Dict[str, tuple] = {
    'rientro_assenza':          ('Scopri come ti aiutiamo', '/assistenza?servizio=assistenza_continuativa'),
    'scadenza_superata':        ('Controlla scadenze',   '/scadenziario'),
    'upload_failed':            ('Riprova upload',        '/analisi-fatture'),
    'fatture_mancanti':         ('Vai a Analisi Fatture', '/analisi-fatture'),
    'upload_ricavi_failed':     ('Controlla ricavi',      '/margini'),
    'scadenza_imminente':       ('Vedi scadenze',         '/scadenziario'),
    'fatturato_mancante':       ('Inserisci fatturato',   '/margini'),
    'incasso_mancante':         ('Inserisci incasso',     '/margini'),
    'costo_personale_mancante': ('Inserisci costo',       '/margini'),
    'price_alert':              ('Controlla prezzi',      '/prezzi'),
    # Deep-link: apre direttamente il tab Articoli gia' filtrato sulle righe da
    # controllare (needs_review). La classificazione si fa qui, in Analisi
    # Fatture — NON in Analisi e Tag (quella e' per i tag custom). Prima la CTA
    # portava a /analisi-e-tag: pagina sbagliata, l'utente non trovava cosa fare.
    'uncategorized_rows':       ('Controlla righe',       '/analisi-fatture?tab=articoli&verifica=1'),
    'coperti_anomalia':         ('Vedi coperti',          '/margini?tab=coperti'),
    'appuntamento_imminente':   ('Vedi agenda',           '/agenda'),
}


# ============================================================
# HELPERS INTERNI
# ============================================================

def _euro_it(valore: float) -> str:
    """Formatta un importo in stile italiano: 11543 -> '11.543'."""
    return f"{int(round(valore)):,}".replace(",", ".")


def _euro_it_cent(valore: float) -> str:
    """Formatta un importo con 2 decimali in stile italiano: 27.5 -> '27,50'.
    Per importi dove i centesimi contano (es. scontrino medio)."""
    s = f"{valore:,.2f}"  # '1,234.50'
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def _buona_notizia_bullet(payload: Dict[str, Any]) -> str:
    """Bullet deterministico dell'apertura positiva (MOL in crescita o incasso ieri).

    Numeri gia' corretti dal backend: l'AI li riscrivera' solo in tono. Nessun
    confronto fuorviante nell'incasso (solo l'eco del dato di ieri); il confronto
    c'e' SOLO nel MOL, su orizzonte pulito (mese chiuso vs mese chiuso).
    """
    tipo = str(payload.get('tipo') or '')
    if tipo == 'mol_mese':
        mese = str(payload.get('mese') or '').capitalize()
        mol = _euro_it(float(payload.get('mol') or 0))
        delta = payload.get('delta_pct')
        prec = str(payload.get('mese_prec') or '').lower()
        prep = "ad" if prec[:1] in ("a", "o") else "a"
        base = f"\U0001F525 {mese} chiuso con € {mol} di margine"
        if delta is not None and prec:
            base += f", +{float(delta):.1f}% rispetto {prep} {prec}"
        return base + "."
    if tipo == 'perdita_in_calo':
        mese = str(payload.get('mese') or '').capitalize()
        perdita = _euro_it(float(payload.get('perdita') or 0))
        prec = str(payload.get('mese_prec') or '').lower()
        prep = "ad" if prec[:1] in ("a", "o") else "a"
        return (
            f"\U0001F4AA {mese} in miglioramento: la perdita è scesa a € {perdita}"
            f" rispetto {prep} {prec}."
        )
    if tipo == 'incasso_ieri':
        incasso = _euro_it(float(payload.get('incasso') or 0))
        giorno = str(payload.get('giorno_settimana') or '').strip()
        if giorno:
            base = f"\U0001F4B0 Ieri ({giorno}) sono entrati € {incasso} di incasso"
        else:
            base = f"\U0001F4B0 Ieri sono entrati € {incasso} di incasso"
        verso = str(payload.get('cfr_verso') or '')
        media = payload.get('cfr_media')
        if verso and media is not None:
            media_it = _euro_it(float(media))
            if verso == 'in_linea':
                base += f", in linea con la media {('dei ' + giorno) if giorno else 'del giorno'} (~€ {media_it})"
            else:
                dp = payload.get('cfr_delta_pct')
                dir_txt = "sopra" if verso == 'sopra' else "sotto"
                base += f", {dp}% {dir_txt} la media {('dei ' + giorno) if giorno else 'del giorno'} (~€ {media_it})"
        base += "."
        coperti = payload.get('coperti')
        sm = payload.get('scontrino_medio')
        if coperti and sm:
            base += f" {int(coperti)} coperti, scontrino medio € {_euro_it_cent(float(sm))}"
            dp = payload.get('scontrino_delta_pct')
            if dp is not None:
                su = bool(payload.get('scontrino_su'))
                base += f" ({dp}% {'sopra' if su else 'sotto'} la media del mese)"
            base += "."
        return base
    if tipo == 'fatture_arrivate':
        return _fatture_arrivate_frase(payload)
    return ""


def _fatture_arrivate_frase(payload: Dict[str, Any]) -> str:
    """Accenno alle fatture comparse ieri (apertura positiva per le sedi SDI che
    non inseriscono l'incasso, es. OFFSIDE). Un paio di numeri (quante + importo)
    e, se ci sono, le righe da controllare — che rimandano alla card sotto.

    ANTI-RIDONDANZA (piano 22/07, Strada A): OGGI non esiste una card "fatture
    ricevute via SDI" in Home, quindi l'accenno puo' portare gli importi. Se un
    giorno nasce quella card (Strada B), qui si toglie l'importo e si rimanda alla
    card ("sono arrivate fatture nuove, le trovi qui sotto"), come gia' fa
    price_alert col suo dettaglio: un solo posto possiede i numeri, il briefing
    accenna. Cambia solo questo template, non la logica.
    """
    n = int(payload.get('n_fatture') or 0)
    importo = _euro_it(float(payload.get('importo') or 0))
    da_contr = int(payload.get('righe_da_controllare') or 0)
    if n <= 0:
        return ""
    if n == 1:
        base = f"\U0001F4E5 Ieri è arrivata una fattura per € {importo}, già registrata"
    else:
        base = f"\U0001F4E5 Ieri sono arrivate {n} fatture per € {importo}, già registrate"
    if da_contr == 1:
        base += "; una riga è da controllare, la trovi qui sotto"
    elif da_contr > 1:
        base += f"; {da_contr} righe sono da controllare, le trovi qui sotto"
    return base + "."


def _rientro_bullet(payload: Dict[str, Any]) -> str:
    """Bullet del bentornato di rientro. Il bentornato e' per tutti; l'amo soft
    dell'Assistenza si aggiunge SOLO se offri_assistenza (Salute rossa)."""
    base = "\U0001F44B Bentornato! Da un po' non ci si vedeva."
    if payload.get('offri_assistenza'):
        # Amo SOFT, in coda e senza pressione: e' un'offerta, non un rimprovero.
        base += " Se vuoi, possiamo gestire noi l'app e i tuoi dati al posto tuo."
    return base


def _onboarding_frase(payload: Dict[str, Any]) -> str:
    """Frase di benvenuto per il cliente NUOVO (ancora senza dati). Tono sobrio e
    accogliente: spiega che per partire servono i primi dati, senza allarmare."""
    return (
        "\U0001F44B Benvenuto in ONEFLUX. Qui troverai ogni giorno la sintesi del "
        "tuo locale. Per iniziare bastano i primi dati."
    )


def _today_rome() -> date:
    """Restituisce la data odierna nel fuso Europe/Rome."""
    if _TZ_ROME:
        return datetime.now(tz=_TZ_ROME).date()
    return date.today()


def _severity_max(notifications: List[Dict[str, Any]]) -> str:
    """Restituisce la severità più alta tra le notifiche passate."""
    best = 'info'
    for n in notifications:
        sev = str(n.get('severity') or '')
        if sev == 'error':
            return 'error'
        if sev == 'warning':
            best = 'warning'
    return best


def notifications_fingerprint(notifications: List[Dict[str, Any]]) -> str:
    """Restituisce fingerprint stabile del set notifiche attive.

    Usata per capire se il briefing e' gia' allineato allo stato corrente.
    """
    if not notifications:
        return ''
    parts: List[str] = []
    for n in notifications:
        topic = str(n.get('topic_key') or '')
        # price_alert e' calcolato live con un budget di 4s: su clienti grandi a
        # volte rientra e a volte va in timeout, quindi id/title/source_event_at
        # cambiano tra una richiesta e l'altra. Se li includessimo, il fingerprint
        # cambierebbe di continuo -> rigenerazione briefing + chiamata OpenAI a
        # ogni load instabile. Per questo topic teniamo solo la presenza (stabile
        # entro la giornata).
        if topic == 'price_alert':
            parts.append("price_alert|present")
            continue
        parts.append(
            "|".join([
                str(n.get('id') or ''),
                topic,
                str(n.get('source_type') or ''),
                str(n.get('dedupe_key') or ''),
                str(n.get('title') or ''),
                str(n.get('source_event_at') or ''),
            ])
        )
    raw = "\n".join(sorted(parts))
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()


def _is_actionable(notif: Dict[str, Any]) -> bool:
    """Filtro 'azionabile E utile' (decisione Mattia, doc Punto 2 §3-bis).

    Una notifica diventa card SOLO se il cliente puo' fare qualcosa di concreto
    E il dato e' davvero rilevante. Il rumore (count 0, payload vuoto, upload
    manuale) resta nella pagina Notifiche, fuori dalla Home. Zero rumore.
    """
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}

    # Upload fatture: card SOLO se automatico (Invoicetronic). Il caricamento
    # manuale lo vede il cliente mentre carica -> mai card.
    if topic == 'upload_failed':
        source = str(notif.get('source_type') or payload.get('source') or '').lower()
        if source and source in ('manuale', 'manual', 'user'):
            return False
        return bool(payload.get('count') or _parse_count_from_title(str(notif.get('title') or '')))

    # Topic basati su un conteggio: card solo se il conteggio e' > 0.
    if topic in ('scadenza_superata', 'scadenza_imminente', 'price_alert', 'uncategorized_rows'):
        count = (payload.get('count')
                 or payload.get('uncategorized_rows')
                 or _parse_count_from_title(str(notif.get('title') or '')))
        return bool(count and int(count) > 0)

    # Topic generati dal backend solo quando il problema esiste davvero:
    # azionabili per definizione (fatturato/personale mancante, ricavi auto KO,
    # incasso di ieri mancante).
    if topic in ('fatturato_mancante', 'incasso_mancante', 'costo_personale_mancante',
                 'upload_ricavi_failed', 'fatture_mancanti'):
        return True

    # Promemoria appuntamenti: card solo se c'e' almeno un appuntamento oggi.
    if topic == 'appuntamento_imminente':
        return bool((payload.get('count') or 0))

    # Anomalia coperti: generata dal backend solo su scostamento forte -> sempre
    # azionabile quando presente (il filtro di rilevanza e' gia' a monte).
    if topic == 'coperti_anomalia':
        return True

    # Topic sconosciuti/tecnici: fuori dalla Home (solo pagina Notifiche).
    return False


def _bullet_for(notif: Dict[str, Any]) -> str:
    """Genera il testo del bullet per una notifica usando payload quando disponibile."""
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}
    title = str(notif.get('title') or '')

    if topic == 'onboarding':
        return _onboarding_frase(payload)

    if topic == 'buona_notizia':
        return _buona_notizia_bullet(payload)

    if topic == 'rientro_assenza':
        return _rientro_bullet(payload)

    if topic == 'scadenza_superata':
        count = payload.get('count')
        totale = payload.get('totale')
        if count and totale is not None:
            parola = 'fattura scaduta' if count == 1 else 'fatture scadute'
            return f"\u26a0\ufe0f {count} {parola} per \u20ac {totale:,.2f} \u2014 controlla il pagamento."
        return f"\u26a0\ufe0f {title}"

    if topic == 'upload_failed':
        count = payload.get('count')
        if count:
            parola = 'fattura non \u00e8 stata caricata' if count == 1 else 'fatture non sono state caricate'
            return f"\u274c {count} {parola} \u2014 riprova o contatta il supporto."
        return f"\u274c {title}"

    if topic == 'upload_ricavi_failed':
        giorni = payload.get('giorni_senza')
        if giorni:
            return (
                f"\U0001F4B6 I ricavi automatici non arrivano da {giorni} giorni "
                f"\u2014 controlla l'invio dal gestionale."
            )
        return f"\U0001F4B6 I ricavi automatici non stanno arrivando \u2014 controlla l'invio dal gestionale."

    if topic == 'scadenza_imminente':
        count = payload.get('count')
        totale = payload.get('totale')
        if count and totale is not None:
            parola = 'fattura in scadenza' if count == 1 else 'fatture in scadenza'
            return f"\U0001F4C5 {count} {parola} entro 7 giorni per \u20ac {totale:,.2f}."
        return f"\U0001F4C5 {title}"

    if topic == 'fatture_mancanti':
        if str(payload.get('tipo') or '') == 'mese_senza_costi':
            mese = payload.get('mese')
            coda = f"di {mese} " if mese else ""
            return (
                f"\U0001F4C4 Mancano le fatture costo {coda}\u2014 il food cost di "
                f"quel mese risulta 0 e il margine non \u00e8 reale."
            )
        if str(payload.get('fase') or '') == 'onboarding':
            if str(payload.get('canale') or '') == 'sdi':
                return "\U0001F4C4 Stai iniziando: appena la ricezione automatica \u00e8 attiva le fatture compaiono qui."
            return "\U0001F4C4 Stai iniziando: carica le prime fatture per vedere food cost e margini."
        if str(payload.get('canale') or '') == 'sdi':
            return "\U0001F4C4 Non stanno arrivando fatture dal flusso automatico \u2014 verifica la ricezione."
        return "\U0001F4C4 Non ci sono fatture caricate di recente \u2014 senza i costi d'acquisto food cost e margini non sono calcolabili."

    if topic == 'fatturato_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if mese and anno:
            return f"\U0001F4CA Il fatturato di {mese} {anno} non \u00e8 ancora stato inserito."
        return f"\U0001F4CA {title}"

    if topic == 'incasso_mancante':
        return "\U0001F4B6 L'incasso di ieri non \u00e8 ancora stato inserito \u2014 mettilo per tenere i margini aggiornati."

    if topic == 'costo_personale_mancante':
        descr = payload.get('descrizione')
        n_mesi = int(payload.get('n_mesi') or 0)
        if descr and n_mesi >= 2:
            return f"\U0001F465 Costo del personale mancante in {descr}."
        mese = payload.get('mese')
        anno = payload.get('anno')
        if mese and anno:
            return f"\U0001F465 Il costo del personale di {mese} {anno} non \u00e8 ancora stato inserito."
        return f"\U0001F465 {title}"

    if topic == 'price_alert':
        count = payload.get('count')
        top_product = payload.get('top_product')
        top_pct = payload.get('top_increase_pct')
        impatto = payload.get('impatto_mese')
        # 'tag' = categoria/raggruppamento (es. "BAR, CAFFE'"), non un prodotto.
        is_tag = str(payload.get('top_tipo') or '') == 'tag'
        if count:
            # Intestazione: una sola voce -> "Prezzo/Categoria in aumento";
            # piu' voci -> "Alert prezzi su N prodotti/categorie".
            if count == 1:
                intro = "Categoria in aumento" if is_tag else "Prezzo in aumento"
            else:
                plurale = 'categorie' if is_tag else 'prodotti'
                intro = f"Alert prezzi su {count} {plurale}"
            base = f"\U0001F4C8 {intro}"
            # Formato uniforme '\u2014 <Nome> +NN%': consente all'anonimizzazione di
            # catturare SEMPRE il nome (prodotto o tag) prima dell'invio a OpenAI.
            if top_product and top_pct is not None:
                base += f" \u2014 {top_product} +{top_pct:.1f}%"
                if impatto:
                    base += f" (\u2248\u20ac{int(impatto)}/mese)"
            elif top_product:
                base += f" \u2014 {top_product}"
            return base + "."
        return f"\U0001F4C8 {title}"

    if topic == 'uncategorized_rows':
        count = payload.get('uncategorized_rows') or payload.get('count')
        if count:
            voce = 'prodotto da controllare' if count == 1 else 'prodotti da controllare'
            return f"\U0001F3F7\ufe0f {count} {voce}."
        return f"\U0001F3F7\ufe0f {title}"

    if topic == 'appuntamento_imminente':
        count = payload.get('count') or 0
        primo = str(payload.get('primo') or '').strip()
        ora = str(payload.get('ora') or '').strip()
        if count == 1:
            dettaglio = f"{ora + ' — ' if ora else ''}{primo}" if primo else "un appuntamento"
            return f"\U0001F4C5 Oggi hai {dettaglio}."
        if count > 1:
            extra = f", a partire da {ora + ' — ' if ora else ''}{primo}" if primo else ""
            return f"\U0001F4C5 Oggi hai {count} appuntamenti in agenda{extra}."
        return f"\U0001F4C5 {title}"

    # Fallback generico: restituisce il titolo della notifica
    return title


def _action_for(notif: Dict[str, Any]) -> Dict[str, Any]:
    """Genera l'azione strutturata che la Home offre per una notifica.

    Il frontend usa questo dict per rendere la card azionabile:
    - id            : id notifica (per il dismiss "Ignora")
    - topic_key     : topic, per icona/colore lato UI
    - severity      : error|warning|info|success
    - testo         : bullet gia' composto (riusa _bullet_for)
    - cta_label     : etichetta del bottone primario
    - cta_page      : pagina di destinazione (action_page della notifica se
                      presente, altrimenti fallback per topic)
    """
    topic = str(notif.get('topic_key') or '')
    cta_label, fallback_page = _TOPIC_ACTION.get(topic, ('Apri', '/dashboard'))
    # action_page della notifica usato come override SOLO se gia' path Next
    # (inizia con "/"): i path legacy Streamlit ("pages/...", "Dashboard")
    # romperebbero la nav, quindi si ricade sul fallback per topic.
    raw_page = str(notif.get('action_page') or '')
    cta_page = raw_page if raw_page.startswith('/') else fallback_page

    return {
        'id':        str(notif.get('id') or ''),
        'topic_key': topic,
        'severity':  str(notif.get('severity') or 'info'),
        'testo':     _bullet_for(notif),
        'cta_label': cta_label,
        'cta_page':  cta_page,
    }


def _parse_count_from_title(title: str) -> Optional[int]:
    """Estrae il numero tra parentesi da titoli come 'Scadenze superate (300)'."""
    m = _re.search(r'\((\d+)\)', title)
    return int(m.group(1)) if m else None


def _parse_mese_anno_from_title(title: str):
    """Estrae (mese, anno) da titoli come '... di Aprile 2026 ...'."""
    m = _re.search(r'di ([A-Za-zÀ-ú]+)\s+(\d{4})', title)
    if m:
        return m.group(1).capitalize(), int(m.group(2))
    return None, None


def _parse_products_from_price_alert_text(text: str) -> List[str]:
    """Estrae fino a 3 prodotti da testi legacy tipo 'Prodotti: A, B, C'."""
    if not text:
        return []
    m = _re.search(r'Prodotti?:\s*(.+)$', text, flags=_re.IGNORECASE)
    if not m:
        return []
    raw = m.group(1).strip().rstrip('.')
    parts = [p.strip() for p in raw.split(',') if p and p.strip()]
    return parts[:3]


def _narrative_phrase_for(notif: Dict[str, Any]) -> str:
    """Frase narrativa con contesto e motivazione per un singolo topic."""
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}
    title = str(notif.get('title') or '')

    if topic == 'scadenza_superata':
        count = payload.get('count') or _parse_count_from_title(title)
        if count:
            parola = 'scadenza superata' if count == 1 else 'scadenze superate'
            return (
                f"Abbiamo {count} {parola}: controlla di aver confermato il pagamento "
                f"o di aver impostato la giusta data di scadenza."
            )
        return f"{title}."

    if topic == 'upload_failed':
        count = payload.get('count') or _parse_count_from_title(title)
        if count:
            if count == 1:
                return (
                    "Una fattura non \u00e8 stata caricata correttamente: riprova l'upload "
                    "o contatta il supporto per non perdere nessun documento."
                )
            return (
                f"{count} fatture non sono state caricate correttamente: riprova l'upload "
                "o contatta il supporto per non perdere nessun documento."
            )
        return f"{title}."

    if topic == 'upload_ricavi_failed':
        giorni = payload.get('giorni_senza')
        if giorni:
            return (
                f"I ricavi automatici dal gestionale non arrivano da {giorni} giorni: "
                f"controlla l'invio, senza fatturato i margini non sono aggiornati."
            )
        return (
            "I ricavi automatici dal gestionale non stanno arrivando: controlla l'invio, "
            "senza fatturato i margini non sono aggiornati."
        )

    if topic == 'fatture_mancanti':
        if str(payload.get('tipo') or '') == 'mese_senza_costi':
            mese = payload.get('mese')
            coda = f"di {mese} " if mese else ""
            return (
                f"Mancano le fatture costo {coda}: il food cost di quel mese "
                "risulta 0, quindi il margine che vedi non è reale. Appena "
                "arrivano i conti tornano veri."
            )
        if str(payload.get('fase') or '') == 'onboarding':
            if str(payload.get('canale') or '') == 'sdi':
                return (
                    "Stai iniziando: appena la ricezione automatica è attiva le "
                    "fatture compaiono qui da sole e food cost e margini si "
                    "calcolano. Per ora è tutto regolare."
                )
            return (
                "Stai iniziando: carica le prime fatture d'acquisto e food cost "
                "e margini si calcolano da soli. Per ora è tutto regolare."
            )
        if str(payload.get('canale') or '') == 'sdi':
            return (
                "Non stanno arrivando fatture dal flusso automatico: vale la pena "
                "verificare la ricezione, senza i costi d'acquisto food cost e "
                "margini non sono calcolabili."
            )
        return (
            "Non ci sono fatture caricate di recente: senza i costi d'acquisto "
            "non si possono calcolare food cost e margini reali."
        )

    if topic == 'coperti_anomalia':
        # Il title backend e' gia' completo (es. "Ieri 120 coperti, 40% in piu'
        # della media della settimana scorsa"): lo riusiamo come frase.
        return f"{title.rstrip('.')}." if title else "Ieri i coperti si sono scostati molto dalla media."

    if topic == 'scadenza_imminente':
        count = payload.get('count') or _parse_count_from_title(title)
        totale = payload.get('totale')
        if count:
            parola = 'fattura scade' if count == 1 else 'fatture scadono'
            base = f"{count} {parola} entro i prossimi 7 giorni"
            if totale is not None:
                base += f" (\u20ac\u00a0{int(totale):,})".replace(',', '.')
            return base + ": \u00e8 il momento giusto per verificare che i pagamenti siano in ordine."
        return f"{title}."

    if topic == 'fatturato_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if not (mese and anno):
            mese, anno = _parse_mese_anno_from_title(title)
        if mese and anno:
            return (
                f"Il fatturato di {mese} {anno} non \u00e8 ancora stato inserito: "
                f"aggiornarlo ti permette di vedere in tempo reale come stai andando."
            )
        return f"{title}."

    if topic == 'incasso_mancante':
        return (
            "L'incasso di ieri non l'hai ancora inserito: bastano pochi secondi "
            "dal telefono e i tuoi margini restano sempre aggiornati."
        )

    if topic == 'costo_personale_mancante':
        # Multi-mese (decisione 25/06): se manca in piu' mesi, dirne il numero e il
        # periodo invece di citarne solo uno. payload['descrizione'] e' gia' la
        # forma compatta ("5 mesi (gen-mag)", "aprile e maggio", "maggio").
        descr = payload.get('descrizione')
        n_mesi = int(payload.get('n_mesi') or 0)
        if descr and n_mesi >= 2:
            return (
                f"Il costo del personale manca in {descr}: "
                f"senza, MOL e margini di quei mesi non sono affidabili."
            )
        mese = payload.get('mese')
        anno = payload.get('anno')
        if not (mese and anno):
            mese, anno = _parse_mese_anno_from_title(title)
        if mese and anno:
            return (
                f"Il costo del personale di {mese} {anno} manca ancora: "
                f"senza di esso MOL e percentuali di margine non sono affidabili."
            )
        return f"{title}."

    if topic == 'price_alert':
        # Decisione Mattia 19/06: nel briefing si ACCENNA soltanto che ci sono
        # prodotti/categorie con prezzi cambiati da controllare; il dettaglio
        # (nome, %, impatto/mese) sta gia' nella card / negli avvisi sotto. Qui
        # NON ripetiamo nomi propri ne' numeri del singolo prodotto.
        count = payload.get('count') or _parse_count_from_title(title)
        is_tag = str(payload.get('top_tipo') or '') == 'tag'
        if count and count > 1:
            voci = 'categorie' if is_tag else 'prodotti'
            return (
                f"Ci sono {count} {voci} con prezzi in aumento da controllare: "
                "trovi il dettaglio qui sotto."
            )
        soggetto = 'una categoria' if is_tag else 'un prodotto'
        return (
            f"C'è {soggetto} con il prezzo in aumento da controllare: "
            "trovi il dettaglio qui sotto."
        )
        return f"{title}."

    if topic == 'uncategorized_rows':
        count = payload.get('uncategorized_rows') or payload.get('count') or _parse_count_from_title(title)
        if count:
            # Tono rassicurante: niente numero crudo nella voce dell'assistente
            # (il conteggio sta nella card "Da fare oggi" sotto). Una riga vs molte.
            if count == 1:
                return (
                    "C'\u00e8 una riga da controllare: "
                    "trovi il dettaglio qui sotto."
                )
            return (
                "Ci sono alcune righe da controllare: "
                "trovi il dettaglio qui sotto."
            )
        return f"{title}."

    if topic == 'coperti_anomalia':
        return f"\U0001F465 {title}" if title else "\U0001F465 Coperti di ieri fuori media."

    return f"{title}."


def _buona_notizia_frase(payload: Dict[str, Any]) -> str:
    """Frase narrativa (template) per l'apertura positiva. Niente confronti
    fuorvianti: l'incasso e' pura eco del dato di ieri."""
    tipo = str(payload.get('tipo') or '')
    if tipo == 'mol_mese':
        mese = str(payload.get('mese') or '').capitalize()
        mol = _euro_it(float(payload.get('mol') or 0))
        delta = payload.get('delta_pct')
        prec = str(payload.get('mese_prec') or '').lower()
        prep = "ad" if prec[:1] in ("a", "o") else "a"
        if delta is not None and prec:
            return f"{mese} si è chiuso con € {mol} di margine, +{float(delta):.1f}% rispetto {prep} {prec}."
        return f"{mese} si è chiuso con € {mol} di margine."
    if tipo == 'perdita_in_calo':
        mese = str(payload.get('mese') or '').capitalize()
        perdita = _euro_it(float(payload.get('perdita') or 0))
        prec = str(payload.get('mese_prec') or '').lower()
        prep = "ad" if prec[:1] in ("a", "o") else "a"
        return (
            f"{mese} è in miglioramento: la perdita è scesa a € {perdita} "
            f"rispetto {prep} {prec}."
        )
    if tipo == 'incasso_ieri':
        incasso = _euro_it(float(payload.get('incasso') or 0))
        giorno = str(payload.get('giorno_settimana') or '').strip()
        # Apertura: "Ieri (martedì) sono entrati € X". Il giorno aiuta a leggere il
        # confronto ("sopra la media dei martedì") ed è un dato, non un confronto.
        if giorno:
            base = f"Ieri ({giorno}) sono entrati € {incasso} di incasso"
        else:
            base = f"Ieri sono entrati € {incasso} di incasso"

        # Confronto con la media dello stesso giorno-settimana (se disponibile).
        verso = str(payload.get('cfr_verso') or '')
        media = payload.get('cfr_media')
        if verso and media is not None:
            media_it = _euro_it(float(media))
            gg = f"i {giorno}" if giorno else "gli altri giorni uguali"
            if verso == 'in_linea':
                base += f", in linea con {gg} (media ~€ {media_it})"
            else:
                dp = payload.get('cfr_delta_pct')
                dir_txt = "sopra" if verso == 'sopra' else "sotto"
                base += f", {dp}% {dir_txt} la media {('dei ' + giorno) if giorno else 'del giorno'} (~€ {media_it})"
        base += "."

        # Coperti + scontrino medio, se il dato esiste (contesto).
        coperti = payload.get('coperti')
        sm = payload.get('scontrino_medio')
        if coperti and sm:
            frase_cop = f" {int(coperti)} coperti, scontrino medio € {_euro_it_cent(float(sm))}"
            dp = payload.get('scontrino_delta_pct')
            if dp is not None:
                su = bool(payload.get('scontrino_su'))
                frase_cop += f" ({dp}% {'sopra' if su else 'sotto'} la media del mese)"
            base += frase_cop + "."
        return base
    if tipo == 'fatture_arrivate':
        return _fatture_arrivate_frase(payload)
    return ""


def _compose_narrative(
    selected: List[Dict[str, Any]],
    severity_max: str,
    apertura_buona: Optional[Dict[str, Any]] = None,
    apertura_rientro: Optional[Dict[str, Any]] = None,
    apertura_onboarding: Optional[Dict[str, Any]] = None,
) -> str:
    """Compone il testo narrativo colloquiale con apertura, corpo e chiusura.

    Gestisce la fusione di fatturato_mancante + costo_personale_mancante
    quando si riferiscono allo stesso mese/anno. Le aperture, se presenti, vanno
    in testa nell'ordine: prima il bentornato di rientro, poi la buona notizia,
    poi le to-do (decisione Mattia: prima il contesto, poi il bene, poi la rogna).
    Per un cliente NUOVO (onboarding) l'apertura e' SOLO il benvenuto, seguito dai
    primi passi (le card dati-mancanti).
    """
    if apertura_onboarding is not None:
        benvenuto = _onboarding_frase(apertura_onboarding.get('payload') or {})
        if not selected:
            return benvenuto
        passi = "; ".join(_narrative_phrase_for(n).rstrip(".") for n in selected)
        return f"{benvenuto}\nPer partire: {passi}."

    rientro = _rientro_bullet(apertura_rientro.get('payload') or {}) if apertura_rientro else ""
    buona = _buona_notizia_frase(apertura_buona.get('payload') or {}) if apertura_buona else ""
    # Aperture concatenate, ognuna sulla sua riga, nell'ordine voluto.
    apertura = "\n".join(p for p in (rientro, buona) if p)

    if not selected:
        if apertura:
            # C'e' un'apertura (rientro e/o buona notizia) ma niente da fare.
            return f"{apertura}\nPer oggi non c'è nulla da sistemare."
        return "Tutto in ordine per oggi, niente da sistemare."

    sentences: List[str] = []
    skip_topics: set = set()

    # Fusione fatturato + costo personale stesso mese/anno. NON si fonde se il
    # personale e' multi-mese (n_mesi>=2): la frase fusa parla di un singolo mese
    # e perderebbe l'informazione "in N mesi". In quel caso restano due frasi.
    fat = next((n for n in selected if n.get('topic_key') == 'fatturato_mancante'), None)
    costo = next((n for n in selected if n.get('topic_key') == 'costo_personale_mancante'), None)
    costo_multi = costo is not None and int((costo.get('payload') or {}).get('n_mesi') or 0) >= 2
    if fat and costo and not costo_multi:
        fp = fat.get('payload') or {}
        cp = costo.get('payload') or {}
        fat_mese = fp.get('mese') or _parse_mese_anno_from_title(str(fat.get('title') or ''))[0]
        fat_anno = fp.get('anno') or _parse_mese_anno_from_title(str(fat.get('title') or ''))[1]
        cp_mese  = cp.get('mese') or _parse_mese_anno_from_title(str(costo.get('title') or ''))[0]
        cp_anno  = cp.get('anno') or _parse_mese_anno_from_title(str(costo.get('title') or ''))[1]
        if fat_mese and fat_mese == cp_mese and fat_anno and fat_anno == cp_anno:
            mese, anno = fat_mese, fat_anno
            sentences.append(
                f"Il fatturato e il costo del personale di {mese} {anno} non li hai ancora inseriti: "
                f"se li inserisci puoi scoprire quanto stai marginando e se stai migliorando!"
            )
            skip_topics = {'fatturato_mancante', 'costo_personale_mancante'}

    for n in selected:
        if n.get('topic_key') in skip_topics:
            continue
        sentences.append(_narrative_phrase_for(n))

    body = "\n".join(sentences)
    if apertura:
        # Prima il bene, poi la rogna (decisione Mattia): apriamo con la buona
        # notizia e poi passiamo alle cose da chiudere. Tono sobrio, niente
        # incoraggiamenti di chiusura.
        return f"{apertura}\nDa sistemare oggi:\n{body}"
    return f"Da sistemare oggi:\n{body}"


# ============================================================
# NARRAZIONE AI (strato finale, anonimizzato, con fallback)
# ============================================================

# Regola d'oro: l'AI NON calcola numeri. Le riceve gia' calcolate nei bullet
# deterministici e li riscrive solo in tono colloquiale. I nomi propri
# (prodotti/fornitori) vengono anonimizzati prima della chiamata e ripristinati
# nella risposta, per non inviarli mai a OpenAI.

_NARRATION_SYSTEM_PROMPT = (
    "Sei l'assistente AI di un gestionale per ristoratori. Tono: SOBRIO, "
    "professionale e asciutto, come un bravo consulente di gestione che riferisce "
    "i fatti con chiarezza. NON sei un coach motivazionale. Ricevi un elenco di "
    "cose da fare oggi, gia' scritte con numeri e dettagli corretti. Riscrivile in "
    "un briefing breve e chiaro, in italiano, dando del tu. REGOLE FERREE: "
    "1) Non inventare, modificare o aggiungere NESSUN numero, importo, "
    "percentuale, data o nome: usa solo quelli che ti vengono dati. "
    "2) Non aggiungere voci non presenti nell'elenco. "
    "3) Massimo 3 frasi, sobrie e informative. NIENTE entusiasmo, NIENTE "
    "incoraggiamenti, NIENTE frasi motivazionali di chiusura ('continua cosi'', "
    "'sei sulla strada giusta', 'diamo il massimo', 'affronta la giornata con "
    "energia' e simili: VIETATE). Vai dritto al punto. "
    "3-bis) VIETATI gli aggettivi enfatici ovunque, anche sulle buone notizie: "
    "mai 'fantastico', 'incredibile', 'ottimo', 'straordinario', 'che bello', "
    "'che notizia'. Un margine in crescita si riferisce con un fatto neutro "
    "(es. 'A maggio il margine e' stato di X, +Y% su aprile'), senza esclamazioni. "
    "3-ter) Se la PRIMA voce e' una buona notizia (margine in crescita, perdita "
    "che si riduce, incasso, fatture arrivate — emoji 🔥 💪 💰 o 📥), riportala per "
    "prima con tono FATTUALE, poi passa alle cose da sistemare. Non INVENTARE "
    "confronti sull'incasso: ma se il bullet ti fornisce gia' un confronto (es. "
    "giorno della settimana, media dei martedi', coperti, scontrino medio), "
    "riportalo cosi' com'e' — e' un dato calcolato, NON tagliarlo. Non aggiungerne "
    "di tuoi. Per l'apertura 'fatture arrivate' (📥): riporta quante fatture e "
    "l'importo cosi' come dati, e se il bullet dice che ci sono righe da "
    "controllare rimanda alla card sotto SENZA ripetere quante — quel dettaglio "
    "vive nelle card, come per l'alert prezzi. "
    "3-quater) Se la PRIMA voce e' un bentornato (emoji 👋), apri con un saluto "
    "breve e pacato, senza enfasi. Se include un'offerta di aiuto, riportala UNA "
    "volta sola, gentile e senza insistere: mai una pressione ne' un rimprovero. "
    "3-quinquies) STRUTTURA in un discorso unico con filo conduttore: PRIMA "
    "l'andamento (com'e' andata: incasso, margine quando indicato), POI cosa c'e' "
    "da fare. Collega le due parti con naturalezza, non come due blocchi staccati. "
    "3-sexies) PRUDENZA sui dati incompleti: se tra le voci risulta che mancano "
    "dati (fatturato, costi, fatture, incassi), NON trarre conclusioni sui margini "
    "e indica che servono quei dati per un quadro corretto. Mai un giudizio "
    "positivo o negativo sulla gestione quando i dati sono incompleti. "
    "3-septies) ALERT PREZZI: nel briefing accenna SOLO che ci sono prodotti con "
    "variazioni di prezzo (aumenti o cali) da controllare, rimandando alle card / "
    "agli avvisi per il dettaglio. NON ripetere nel testo il nome del prodotto, la "
    "percentuale del singolo prodotto ne' l'impatto in euro/mese: quei numeri stanno "
    "gia' nella card sotto. Esempio buono: 'Ci sono alcuni prodotti con prezzi in "
    "aumento da controllare'. Esempio da EVITARE: '...1/2 PROSC.COTTO +11,1%, circa "
    "7 euro al mese...'. "
    "3-octies) LINGUAGGIO UMANO E DIRETTO: niente burocratese. VIETATE formule come "
    "'e' necessario gestire', 'si rende necessario', 'assicurati di procedere con le "
    "necessarie modifiche', 'provvedi a'. Parla come una persona: 'controlla', "
    "'da' un'occhiata a', 'ci sono X da sistemare'. "
    "4) Al massimo 1 emoji, solo se utile; spesso meglio nessuna. Mai dentro i "
    "numeri. Niente punti esclamativi se non strettamente necessari. "
    "5) Mantieni intatti i segnaposto tipo <<P1>> o <<F1>> se presenti. "
    "Restituisci solo il testo del briefing, senza elenchi puntati."
)


def _anonymize_bullets(bullets: List[str]) -> tuple:
    """Sostituisce nomi propri (prodotti/fornitori) con segnaposto.

    Heuristica conservativa: anonimizza i nomi prodotto presenti nei bullet
    di price_alert (gli unici che contengono nomi propri nel set attuale),
    riconoscendoli dal pattern reale prodotto da _bullet_for:
    '… — <Nome> +XX%' (em-dash). Restituisce (bullets_anonimi, mappa_ripristino).
    """
    mapping: Dict[str, str] = {}
    out: List[str] = []
    counter = 0
    for b in bullets:
        # SOLO i bullet price_alert contengono nomi propri (prodotti/categorie):
        # li riconosco dall'emoji 📈 iniziale. Limitare a questi evita di
        # anonimizzare per sbaglio parole comuni dopo un em-dash in altri bullet
        # (es. "… — controlla.").
        if b.lstrip().startswith("\U0001F4C8"):
            # Cattura il nome dopo l'em-dash: '— <Nome> +NN%' oppure '— <Nome>.'
            # (a fine stringa). Vale per prodotti e categorie: stesso delimitatore.
            m = _re.search(r'—\s+(.+?)(?:\s+\+\d|\s*\.?\s*$)', b)
            if m:
                nome = m.group(1).strip().rstrip('.').strip()
                if nome:
                    counter += 1
                    ph = f"<<P{counter}>>"
                    mapping[ph] = nome
                    b = b.replace(nome, ph)
        out.append(b)
    return out, mapping


def _deanonymize(text: str, mapping: Dict[str, str]) -> str:
    for ph, nome in mapping.items():
        text = text.replace(ph, nome)
    return text


def _narrate_with_ai(bullets: List[str], fallback: str) -> str:
    """Genera la narrativa con GPT a partire dai bullet deterministici.

    Anonimizza, chiama gpt-4o-mini, ripristina i nomi, traccia i costi.
    Qualsiasi errore -> ritorna il fallback (template _compose_narrative).
    """
    if not bullets:
        return fallback
    try:
        from services.ai_service import _get_openai_client, _resolve_ristorante_id
        anon, mapping = _anonymize_bullets(bullets)
        user_msg = "Cose da fare oggi:\n" + "\n".join(f"- {b}" for b in anon)

        client = _get_openai_client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _NARRATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=220,
            temperature=0.5,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return fallback

        try:
            usage = response.usage
            if usage:
                from services.ai_cost_service import track_ai_usage
                track_ai_usage(
                    operation_type='daily_briefing',
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    ristorante_id=_resolve_ristorante_id(),
                    item_count=len(bullets),
                )
        except Exception as exc:
            logger.warning("tracking costo briefing AI fallito: %s", exc)

        return _deanonymize(text, mapping)
    except Exception as exc:
        logger.warning("narrazione AI fallita, uso fallback template: %s", exc)
        return fallback


# ============================================================
# LOGICA SNAPSHOT (pura, testabile)
# ============================================================

def _build_snapshot(
    notifications: List[Dict[str, Any]],
    use_ai: bool = False,
    topics_disabled: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Costruisce lo snapshot giornaliero.

    - Deduplica per topic_key (tiene la prima occorrenza, le notifiche arrivano
      ordinate per source_event_at DESC da get_inbox_notifications)
    - Filtra: tiene solo le notifiche azionabili E utili (_is_actionable)
    - Ordina per GERARCHIA TEMATICA (_TOPIC_PRIORITY): prima il tema, poi la
      gravita' dentro lo stesso tema. Niente piu' split rossi/gialli.
    - Taglia a _MAX_CARD card; il resto resta nella pagina Notifiche.

    La pipeline e' deterministica fino ai bullet/azioni. Se use_ai=True la
    narrativa finale viene riscritta da GPT (anonimizzato, con fallback al
    template); con use_ai=False resta il template _compose_narrative.
    """
    seen_topics: Dict[str, Dict[str, Any]] = {}
    for n in notifications:
        t = str(n.get('topic_key') or '')
        if t and t not in seen_topics:
            seen_topics[t] = n

    # Topic spenti dal configuratore (Step 6), espansi alle key dello stesso tema
    # (es. "Scadenze" spegne superata + imminente). I topic non disattivabili
    # (upload falliti) restano sempre attivi anche se finiti in lista per errore.
    spenti = {
        t for t in espandi_topic_spenti(topics_disabled)
        if t not in _TOPIC_NON_DISATTIVABILI
    }

    # Aperture: estratte a parte. NON sono card "Da fare oggi" (non si ignorano,
    # non hanno CTA-card) e non contano per 'tutto_ok': sono il contesto con cui
    # l'AI apre il briefing. Restano fuori da candidati/azioni.
    #  - onboarding: benvenuto al cliente nuovo (senza dati), prima di tutto.
    #  - rientro_assenza: bentornato dopo un'assenza.
    #  - buona_notizia: il fatto fresco positivo (MOL/incasso).
    onboarding = seen_topics.get('onboarding')
    rientro = seen_topics.get('rientro_assenza') if 'rientro_assenza' not in spenti else None
    buona_notizia = seen_topics.get('buona_notizia') if 'buona_notizia' not in spenti else None

    # Solo topic noti (presenti nella gerarchia), non spenti, E azionabili/utili.
    # Le aperture sono escluse qui: sono narrativa, non to-do.
    _APERTURE = {'onboarding', 'rientro_assenza', 'buona_notizia'}
    candidati = [
        n for n in seen_topics.values()
        if str(n.get('topic_key') or '') in _TOPIC_PRIORITY
        and str(n.get('topic_key') or '') not in _APERTURE
        and str(n.get('topic_key') or '') not in spenti
        and _is_actionable(n)
    ]

    # Ordinamento per gerarchia tematica pura, poi gravita' come tie-break.
    _SEV_RANK = {'error': 0, 'warning': 1, 'info': 2, 'success': 3}
    ordinati = sorted(
        candidati,
        key=lambda n: (
            _TOPIC_PRIORITY.get(str(n.get('topic_key', '')), 99),
            _SEV_RANK.get(str(n.get('severity') or 'info'), 2),
        ),
    )

    selected = ordinati[:_MAX_CARD]
    bullets = [_bullet_for(n) for n in selected]
    azioni = [_action_for(n) for n in selected]
    sev_max = _severity_max(notifications)

    # Dati mancanti: calcolati su TUTTI i candidati azionabili (non solo le 4 card
    # selezionate), perche' un dato mancante in posizione 5+ verrebbe tagliato ma
    # NON deve far comparire il verde "tutto a posto". Senza questi i numeri di
    # margine/MOL sono falsi: il verde si spegne se la lista non e' vuota.
    dati_mancanti = [
        _TOPIC_DATO_MANCANTE_LABEL[str(n.get('topic_key'))]
        for n in ordinati
        if str(n.get('topic_key') or '') in _TOPIC_DATO_MANCANTE_LABEL
    ]
    # Dedup mantenendo l'ordine di priorita'.
    dati_mancanti = list(dict.fromkeys(dati_mancanti))

    # Aperture come primi bullet per l'AI (anonimizzati come gli altri), cosi' la
    # narrativa inizia dal contesto e poi passa alle to-do. Per un cliente NUOVO
    # (onboarding) l'apertura e' SOLO il benvenuto: rientro e buona notizia non
    # hanno senso senza dati. Altrimenti: prima il bentornato, poi la buona notizia
    # (decisione Mattia: "prima il bene, poi la rogna").
    if onboarding is not None:
        aperture_bullets = [_bullet_for(onboarding)]
        template_narrative = _compose_narrative(
            selected, sev_max, apertura_onboarding=onboarding,
        )
    else:
        aperture_bullets = [
            _bullet_for(n) for n in (rientro, buona_notizia) if n is not None
        ]
        template_narrative = _compose_narrative(
            selected, sev_max, apertura_rientro=rientro, apertura_buona=buona_notizia,
        )
    bullets_ai = aperture_bullets + bullets
    if use_ai and (selected or onboarding or rientro or buona_notizia):
        narrative = _narrate_with_ai(bullets_ai, template_narrative)
    else:
        narrative = template_narrative

    # Il fingerprint include i topic spenti: cambiando le preferenze il briefing
    # cached si invalida anche se le notifiche sono identiche.
    fingerprint = notifications_fingerprint(notifications)
    if topics_disabled:
        fingerprint += "|" + ",".join(sorted(str(t) for t in topics_disabled))

    return {
        'bullets': bullets,
        'azioni': azioni,
        # Verde "tutto a posto" SOLO se nessuna card da fare E nessun dato mancante
        # E non e' un cliente nuovo (onboarding): un dato mancante o una sede senza
        # dati rendono falso/prematuro il verde trionfale.
        'tutto_ok': len(selected) == 0 and len(dati_mancanti) == 0 and onboarding is None,
        'dati_mancanti': dati_mancanti,
        'narrative': narrative,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'notif_count': len(notifications),
        'notif_fingerprint': fingerprint,
        'severity_max': sev_max,
        # Versione della logica che ha prodotto questo snapshot: se al load non
        # combacia con _BRIEFING_CODE_VERSION, lo snapshot e' di un codice vecchio
        # e va rigenerato (auto-invalidazione su deploy). Vedi snapshot_is_stale().
        'code_version': _BRIEFING_CODE_VERSION,
    }


# ============================================================
# CRUD
# ============================================================

def snapshot_is_stale(snapshot: Optional[Dict[str, Any]]) -> bool:
    """True se lo snapshot in cache NON va piu' servito e va rigenerato.

    Due motivi, entrambi a costo zero (nessuna query):
      1) DEPLOY: lo snapshot e' stato prodotto da una versione diversa della
         logica (code_version != _BRIEFING_CODE_VERSION). Cosi' un deploy che
         cambia testi/conteggi/regole invalida da solo gli snapshot vecchi —
         niente piu' svuotamento manuale della cache dopo ogni rilascio.
      2) TTL: lo snapshot e' piu' vecchio di _BRIEFING_TTL_MINUTI. Copre i dati
         che cambiano DURANTE il giorno senza un evento di invalidazione (righe
         classificate, fatture elaborate in background): senza questo il cliente
         vedrebbe il numero della mattina fino a mezzanotte.

    Best-effort: su snapshot malformato o data illeggibile -> stantio (rigenera),
    mai servire qualcosa di dubbio.
    """
    if not snapshot:
        return True
    # 1) Versione logica
    try:
        if int(snapshot.get('code_version') or 0) != _BRIEFING_CODE_VERSION:
            return True
    except (TypeError, ValueError):
        return True
    # 2) TTL sull'istante di scrittura (created_at del record DB, fallback generated_at)
    ts = snapshot.get('_db_created_at') or snapshot.get('generated_at')
    if not ts:
        return True
    try:
        scritto = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if scritto.tzinfo is None:
            scritto = scritto.replace(tzinfo=timezone.utc)
        eta_min = (datetime.now(timezone.utc) - scritto).total_seconds() / 60.0
        return eta_min >= _BRIEFING_TTL_MINUTI
    except (ValueError, TypeError):
        return True


def get_today_briefing(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Optional[Dict[str, Any]]:
    """Legge lo snapshot di oggi da daily_briefing_state.

    Restituisce il dict snapshot se esiste, None altrimenti.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return None
    try:
        today = _today_rome().isoformat()
        resp = (
            supabase_client.table('daily_briefing_state')
            .select('snapshot,created_at')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('generated_for_date', today)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            snap = dict(rows[0].get('snapshot') or {})
            snap['_db_created_at'] = rows[0].get('created_at')
            return snap
        return None
    except Exception as exc:
        logger.error("Errore get_today_briefing: %s", exc)
        return None


def get_latest_briefing(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> Optional[Dict[str, Any]]:
    """Legge lo snapshot PIU' RECENTE (anche di un giorno passato).

    Serve al fast-path "mai bloccante": se manca lo snapshot di OGGI, invece di
    pagare in linea il ricalcolo pesante (alert prezzi + OpenAI) e rischiare il
    timeout del frontend, serviamo subito l'ultimo briefing disponibile (al
    massimo di ieri) e rigeneriamo quello di oggi in background. Lo snapshot
    restituito porta '_stale': True cosi' il chiamante sa che e' un ripiego.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return None
    try:
        resp = (
            supabase_client.table('daily_briefing_state')
            .select('snapshot,created_at,generated_for_date')
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .order('generated_for_date', desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows:
            snap = dict(rows[0].get('snapshot') or {})
            snap['_db_created_at'] = rows[0].get('created_at')
            snap['_stale'] = True
            return snap
        return None
    except Exception as exc:
        logger.error("Errore get_latest_briefing: %s", exc)
        return None


def generate_and_save_briefing(
    user_id: str,
    ristorante_id: str,
    notifications: List[Dict[str, Any]],
    supabase_client=None,
    topics_disabled: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Genera snapshot deterministico dalle notifiche e lo salva su DB.

    Upsert su (user_id, ristorante_id, generated_for_date).
    Restituisce lo snapshot salvato, None in caso di errore.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return None
    try:
        today = _today_rome()
        snapshot = _build_snapshot(notifications, use_ai=True, topics_disabled=topics_disabled)
        snapshot['generated_for_date'] = today.isoformat()

        record = {
            'user_id':            user_id,
            'ristorante_id':      ristorante_id,
            'generated_for_date': today.isoformat(),
            'snapshot':           snapshot,
            'updated_at':         datetime.now(timezone.utc).isoformat(),
        }
        (
            supabase_client.table('daily_briefing_state')
            .upsert(record, on_conflict='user_id,ristorante_id,generated_for_date')
            .execute()
        )
        logger.info(
            "Briefing generato per ristorante_id=%s data=%s bullets=%d",
            ristorante_id, today.isoformat(), len(snapshot['bullets']),
        )
        return snapshot
    except Exception as exc:
        logger.error("Errore generate_and_save_briefing: %s", exc)
        return None


def invalidate_today_briefing(
    user_id: str,
    ristorante_id: str,
    supabase_client=None,
) -> None:
    """Cancella lo snapshot di OGGI cosi' la prossima Home lo rigenera.

    L'endpoint /api/home/briefing serve lo snapshot del giorno in cache-first
    (senza ricalcolare gli alert prezzi, per non sforare il timeout di 8s del
    frontend). Quando cambiano i dati che il briefing racconta — nuove fatture
    caricate, ricavi/costi inseriti — quello snapshot diventa stantio: va
    invalidato qui, agli EVENTI, invece di rigenerare ad ogni render.

    Best-effort: un errore qui non deve mai bloccare l'operazione che l'ha
    triggerato (upload/inserimento). Al peggio il briefing si aggiorna il giorno
    dopo, come prima del fast-path.
    """
    if not user_id or not ristorante_id or supabase_client is None:
        return
    try:
        today = _today_rome().isoformat()
        (
            supabase_client.table('daily_briefing_state')
            .delete()
            .eq('user_id', user_id)
            .eq('ristorante_id', ristorante_id)
            .eq('generated_for_date', today)
            .execute()
        )
    except Exception as exc:
        logger.warning("invalidate_today_briefing fallita (non bloccante): %s", exc)
