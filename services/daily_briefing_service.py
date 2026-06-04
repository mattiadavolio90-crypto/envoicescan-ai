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

# Numero massimo di card mostrate in "Da fare oggi". Oltre questo numero,
# il resto resta nella pagina Notifiche (link "Vedi tutte"). Decisione Mattia.
_MAX_CARD = 5

# Topic che il cliente NON puo' spegnere dal configuratore: sono guasti tecnici
# (perdita dati) e vanno sempre mostrati. Decisione Mattia (Step 6).
_TOPIC_NON_DISATTIVABILI = frozenset({'upload_failed', 'upload_ricavi_failed'})

# Gerarchia TEMATICA delle card (decisa da Mattia, doc Punto 1/2).
# Regola d'oro: prima il TEMA, poi la gravita' DENTRO lo stesso tema.
# "Un upload mancato e' sempre piu' importante di un rincaro del 1000%."
# (piu' basso = prima). I numeri lasciano spazio per i topic futuri:
#   upload_ricavi_failed (Step 5) ~ 15, tra upload fatture e prezzi.
_TOPIC_PRIORITY: Dict[str, int] = {
    'upload_failed':            10,   # 1. Upload fatture fallito
    'upload_ricavi_failed':     15,   # 2. Upload ricavi fallito (solo se mappato)
    'price_alert':              20,   # 3. Alert prezzi
    'uncategorized_rows':       30,   # 4. Righe da classificare
    'fatturato_mancante':       40,   # 5. Fatturato mancante (mese)
    'incasso_mancante':         45,   #    Incasso di ieri mancante (giorno), stesso tema
    'costo_personale_mancante': 50,   # 6. Costo personale mancante
    'scadenza_superata':        60,   # 7. Scadenze (superate prima delle imminenti)
    'scadenza_imminente':       61,   #    e imminenti subito dopo, stesso tema
}

# Azione primaria suggerita per topic: (label_cta, pagina_destinazione).
# La pagina e' un fallback usato quando la notifica non porta un action_page
# proprio. La Home renderizza il bottone come link generico alla pagina.
_TOPIC_ACTION: Dict[str, tuple] = {
    'scadenza_superata':        ('Controlla scadenze',   '/scadenziario'),
    'upload_failed':            ('Riprova upload',        '/analisi-fatture'),
    'upload_ricavi_failed':     ('Controlla ricavi',      '/margini'),
    'scadenza_imminente':       ('Vedi scadenze',         '/scadenziario'),
    'fatturato_mancante':       ('Inserisci fatturato',   '/margini'),
    'incasso_mancante':         ('Inserisci incasso',     '/margini'),
    'costo_personale_mancante': ('Inserisci costo',       '/margini'),
    'price_alert':              ('Controlla prezzi',      '/prezzi'),
    'uncategorized_rows':       ('Classifica righe',      '/analisi-e-tag'),
}


# ============================================================
# HELPERS INTERNI
# ============================================================

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
        parts.append(
            "|".join([
                str(n.get('id') or ''),
                str(n.get('topic_key') or ''),
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
    if topic in ('fatturato_mancante', 'incasso_mancante', 'costo_personale_mancante', 'upload_ricavi_failed'):
        return True

    # Topic sconosciuti/tecnici: fuori dalla Home (solo pagina Notifiche).
    return False


def _bullet_for(notif: Dict[str, Any]) -> str:
    """Genera il testo del bullet per una notifica usando payload quando disponibile."""
    topic = str(notif.get('topic_key') or '')
    payload = notif.get('payload') or {}
    title = str(notif.get('title') or '')

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

    if topic == 'fatturato_mancante':
        mese = payload.get('mese')
        anno = payload.get('anno')
        if mese and anno:
            return f"\U0001F4CA Il fatturato di {mese} {anno} non \u00e8 ancora stato inserito."
        return f"\U0001F4CA {title}"

    if topic == 'incasso_mancante':
        return "\U0001F4B6 L'incasso di ieri non \u00e8 ancora stato inserito \u2014 mettilo per tenere i margini aggiornati."

    if topic == 'costo_personale_mancante':
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
            righe = 'riga richiede' if count == 1 else 'righe richiedono'
            return f"\U0001F3F7\ufe0f {count} {righe} classificazione manuale."
        return f"\U0001F3F7\ufe0f {title}"

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
        count = payload.get('count') or _parse_count_from_title(title)
        top_product = payload.get('top_product')
        top_pct = payload.get('top_increase_pct')
        # 'tag' = categoria/raggruppamento (es. "BAR, CAFFE'"), non un prodotto:
        # va chiamato "categoria", altrimenti il testo dice "prodotto" e tra
        # parentesi cita una categoria -> incomprensibile.
        is_tag = str(payload.get('top_tipo') or '') == 'tag'
        body = str(notif.get('body') or '')
        legacy_products = _parse_products_from_price_alert_text(body)
        if not top_product and legacy_products:
            top_product = legacy_products[0]
            if not count:
                count = len(legacy_products)
        impatto = payload.get('impatto_mese')
        if count:
            if count == 1 and top_product:
                # Una sola voce: la nomino direttamente, niente "soprattutto"
                # (che implicherebbe un elenco con count > 1).
                if is_tag:
                    soggetto = f"La categoria {top_product} è aumentata"
                else:
                    soggetto = f"Il prezzo di {top_product} è aumentato"
                if top_pct is not None:
                    soggetto += f" del +{top_pct:.1f}%"
                    if impatto:
                        soggetto += f", circa €{int(impatto)} in più al mese"
                return soggetto + ": vale la pena controllare se puoi rinegoziare o cambiare fornitore."

            # Piu' voci: numero + la piu' pesante come esempio.
            base = f"Ho notato che {count} voci sono aumentate di prezzo in modo che pesa davvero"
            if top_product:
                qualifica = "categoria" if is_tag else "prodotto"
                base += f" (il {qualifica} più pesante è {top_product}"
                if top_pct is not None:
                    base += f", +{top_pct:.1f}%"
                    if impatto:
                        base += f", circa €{int(impatto)} in più al mese"
                base += ")"
            return base + ": vale la pena controllare se puoi rinegoziare o cambiare fornitore."
        return f"{title}."

    if topic == 'uncategorized_rows':
        count = payload.get('uncategorized_rows') or payload.get('count') or _parse_count_from_title(title)
        if count:
            righe = 'riga attende' if count == 1 else 'righe attendono'
            return (
                f"{count} {righe} classificazione manuale: "
                f"categorizzarle rende i tuoi report pi\u00f9 precisi e affidabili."
            )
        return f"{title}."

    return f"{title}."


def _compose_narrative(selected: List[Dict[str, Any]], severity_max: str) -> str:
    """Compone il testo narrativo colloquiale con apertura, corpo e chiusura.

    Gestisce la fusione di fatturato_mancante + costo_personale_mancante
    quando si riferiscono allo stesso mese/anno.
    """
    if not selected:
        return "Ciao! ✅\nTutto in ordine per oggi, niente da sistemare. Buon lavoro! 👍"

    sentences: List[str] = []
    skip_topics: set = set()

    # Fusione fatturato + costo personale stesso mese/anno
    fat = next((n for n in selected if n.get('topic_key') == 'fatturato_mancante'), None)
    costo = next((n for n in selected if n.get('topic_key') == 'costo_personale_mancante'), None)
    if fat and costo:
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
    return f"Ciao! 👋 Vediamo cosa c'è da sistemare oggi:\n{body}\nForza, ce la fai! 🔥"


# ============================================================
# NARRAZIONE AI (strato finale, anonimizzato, con fallback)
# ============================================================

# Regola d'oro: l'AI NON calcola numeri. Le riceve gia' calcolate nei bullet
# deterministici e li riscrive solo in tono colloquiale. I nomi propri
# (prodotti/fornitori) vengono anonimizzati prima della chiamata e ripristinati
# nella risposta, per non inviarli mai a OpenAI.

_NARRATION_SYSTEM_PROMPT = (
    "Sei l'assistente AI di un gestionale per ristoratori: sveglio, positivo e "
    "motivante, come un bravo consulente che ti da' una spinta. Ricevi un elenco "
    "di cose da fare oggi, gia' scritte con numeri e dettagli corretti. "
    "Riscrivile in un briefing colloquiale, caldo e diretto, in italiano, dando "
    "del tu. REGOLE FERREE: "
    "1) Non inventare, modificare o aggiungere NESSUN numero, importo, "
    "percentuale, data o nome: usa solo quelli che ti vengono dati. "
    "2) Non aggiungere voci non presenti nell'elenco. "
    "3) Massimo 4 frasi, scorrevoli e con un po' di energia (non burocratiche). "
    "Apri in modo amichevole e chiudi con un incoraggiamento breve. "
    "4) Usa 2-4 emoji pertinenti per dare ritmo (es. 📊 💰 ⏰ ✅ 🔥 👍), "
    "ma senza esagerare e mai dentro i numeri. "
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

    # Topic spenti dal configuratore (Step 6). I topic non disattivabili
    # (upload falliti) restano sempre attivi anche se finiti in lista per errore.
    spenti = {
        t for t in (topics_disabled or [])
        if t not in _TOPIC_NON_DISATTIVABILI
    }

    # Solo topic noti (presenti nella gerarchia), non spenti, E azionabili/utili.
    candidati = [
        n for n in seen_topics.values()
        if str(n.get('topic_key') or '') in _TOPIC_PRIORITY
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

    template_narrative = _compose_narrative(selected, sev_max)
    if use_ai and selected:
        narrative = _narrate_with_ai(bullets, template_narrative)
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
        'tutto_ok': len(selected) == 0,
        'narrative': narrative,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'notif_count': len(notifications),
        'notif_fingerprint': fingerprint,
        'severity_max': sev_max,
    }


# ============================================================
# CRUD
# ============================================================

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
