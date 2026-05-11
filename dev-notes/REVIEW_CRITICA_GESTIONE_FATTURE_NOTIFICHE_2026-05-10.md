# REVIEW CRITICA - proposta vs codice reale

Data: 10/05/2026
Scope: confronto bidirezionale tra proposta architetturale e stato reale codebase OH YEAH! Hub, senza implementazione codice.

---

## Sezione A - Verifica aderenza proposta al codice reale

### A.1 Expander "Gestione Fatture" in app.py vs app_controllers.py

Verdetto: PARZIALMENTE CORRETTO - la proposta dice "duplicato", la realta e piu sottile.

- app.py: with st.container(key="expander_gestione_fatture") -> st.expander("Apri per gestire le Fatture Caricate (Elimina / Modifica Data)"). Stile verde. Include "Modifica Data". E il percorso attivo.
- utils/app_controllers.py: stesso key="expander_gestione_fatture", etichetta "Apri per gestire le Fatture Caricate (Elimina)" (no Modifica Data). Stile arancione.
- La funzione render_dashboard_ui in utils/app_controllers.py non e mai chiamata da app.py: blocco dead code di refactor parziale.

Implicazioni:
- La proposta deve sostituire (non replicare) solo la versione di app.py.
- La versione in app_controllers.py va eliminata nel refactor (riduce confusione, evita key collision future).
- Se la nuova pagina crea un expander omonimo, usare key dedicata tipo gfn_expander_gestione_fatture.

### A.2 Pattern bottoni vs st.tabs in dashboard

Verdetto: CONFERMATO. La proposta e corretta.

- components/dashboard_renderer.py usa bottoni + st.session_state.sezione_attiva + st.rerun(), non st.tabs.
- pages/gestione_account.py usa st.tabs: conferma che tabs e accettato in pagine semplici, ma il pattern dashboard resta button-based.
- Rischio concreto: collisione chiavi session_state se la nuova pagina riusa sezione_attiva/is_loading.

Indicazione:
- Nella nuova pagina usare namespace dedicato: gfn_sezione_attiva, gfn_is_loading, ecc.

### A.3 estrai_dati_da_xml e salva_fattura_processata

Verdetto: IN PARTE SBAGLIATA nella proposta iniziale (signature change non necessario).

Fatti:
- estrai_dati_da_xml(file_caricato, user_id=None) restituisce List[Dict].
- Non esiste header_meta separato: i campi header (tipo_documento, Totale_Documento, Totale_Imponibile, Totale_IVA, Data_Documento, Fornitore, piva_cessionario, ecc.) sono replicati su ogni riga.
- salva_fattura_processata(nome_file, dati_prodotti, ...) riceve gia tutto e gestisce idempotenza delete+insert.
- DatiPagamento non e parsato oggi (zero match in codebase).

Conseguenza:
- Nessun refactor firma necessario.
- upsert_fattura_documento va chiamata dentro salva_fattura_processata leggendo header da dati_prodotti[0].
- Nuovi campi pagamento/scadenza possono essere aggiunti nei dict riga durante parse (replicati), senza rompere API interne.

### A.4 Worker - stessa pipeline

Verdetto: CORRETTA.

- worker/queue_processor.py usa le stesse funzioni estrai_dati_da_xml e salva_fattura_processata.
- Inserendo upsert documento in salva_fattura_processata, copertura automatica manual upload + worker Invoicetronic.

### A.5 clear_fatture_cache e cache esistenti

Verdetto: PARZIALMENTE CORRETTA.

- clear_fatture_cache oggi gia pulisce get_descrizioni_distinte (quindi il punto storico della doc ANALISI_CACHE era gia risolto).
- Restano da introdurre clear per nuove cache documenti/scadenze/regole fornitore.
- Asset critico gia presente: migration 068 con cache_version e trigger di bump cross-process.

Indicazione:
- Estendere cache_version con chiavi nuove (fatture_documenti, fornitori_pagamenti_config) invece di inventare token session ad-hoc.

### A.6 Notifiche - rendering e tipologie

Verdetto: INCOMPLETA nella proposta iniziale.

Conferme:
- In app.py ci sono 6 builder usati per notifiche operative:
  - build_monthly_data_notifications
  - build_upload_outcome_notifications
  - build_upload_quality_notifications
  - build_price_alert_notifications
  - build_credit_note_notifications
  - build_td24_date_notifications
- Esiste inoltre _render_auto_invoice_notice (notifica Invoicetronic dall'ultimo login), separata dai 6 builder.
- Persistenza dismiss gia gestita da users.dismissed_notification_ids.

Impatto:
- Nella nuova pagina vanno spostate sia notifiche operative sia auto_invoice_notice.
- Non serve tabella notifiche_eventi per dismiss persistence.

### A.7 Numero migration

Verdetto: CONFERMATO.

- Ultima migration presente: 068.
- Prossimo numero libero: 069.

### A.8 Pattern RLS

Verdetto: CONFERMATO (con sfumatura).

- Pattern repository: RLS attiva e accesso pratico via service_role (custom auth app).
- Per nuove tabelle usare pattern fatture_queue: RLS enabled, no policy user-facing.

### A.9 Struttura reale fatture

Verdetto: CORRETTA a grandi linee, ma con semplificazioni possibili.

Campi header gia esistono in fatture:
- tipo_documento
- totale_documento
- totale_imponibile
- totale_iva
- data_documento
- data_competenza
- data_consegna
- fornitore
- file_origine
- deleted_at

Impatto:
- Backfill fatture_documenti e diretto con aggregazione per (user_id, ristorante_id, file_origine), senza riparsare XML storici.

### A.10 ANALISI_CACHE_PAGINE_ANALISI.md

Verdetto: PARZIALMENTE NON ALLINEATA (doc storica in parte superata).

- Punto get_descrizioni_distinte non invalidata: gia risolto in codice attuale.
- Per il nuovo refactor, il tema vero resta allineamento invalidazioni cross-page/cross-process per nuove tabelle.
- Soluzione migliore: riuso pattern cache_version (migrazione 068).

---

## Sezione B - Rischi non coperti

### B.1 Trial limits

- trial_active/trial_activated_at esistono.
- Va deciso se la nuova pagina (pagamenti/scadenze/regole) sia disponibile in trial.
- Raccomandazione pragmatica MVP: disponibile anche in trial (no branch extra).

### B.2 Multi-ristorante

- Cambio ristorante in app.py pulisce cache e resetta stato.
- Va esteso con clear cache nuove e reset chiavi gfn_*.
- Regole fornitore da mantenere per (user_id, ristorante_id), non globali.

### B.3 GDPR export e delete account

- pages/gestione_account.py gestisce export e cascade delete su molte tabelle.
- Mancano nuove tabelle in entrambi i flussi:
  - fatture_documenti
  - fornitori_pagamenti_config

### B.4 Cestino

- Soft-delete/ripristino oggi agiscono su fatture.
- Va aggiunta propagazione su fatture_documenti.deleted_at (via trigger DB o service layer coerente).

### B.5 Concorrenza worker/UI

- ON CONFLICT su UNIQUE e atomico in PostgreSQL.
- Rischio principale e performance bulk update pagata/non pagata.
- Azione: usare update bulk unico per lista IDs.

### B.6 Tipi documento oltre TD04

- Lista tipi supportati ampia (TD01, TD02, TD04, TD05, TD06, TD07, TD16-20, TD24-27).
- Regola proposta segno_compensazione = -1 solo per TD04 resta corretta per MVP.

### B.7 Session state collisions

- Streamlit session_state condiviso cross-pages.
- Chiavi sensibili gia esistenti: sezione_attiva, is_loading, last_upload_notification_context, auto_invoice_notice.
- Nuova pagina deve usare prefisso gfn_ rigido.

### B.8 Cache scope per utente

- @st.cache_data keyed anche da parametri funzione (incl. user_id/ristorante_id).
- Nessun rischio nuovo di leak tra utenti introdotto dal refactor, se i parametri restano completi.

---

## Sezione C - Decisioni aperte

### C.1 Multipli DettaglioPagamento

- Mancano evidenze test fixture nel repo.
- Scelta consigliata MVP: usare scadenza piu lontana sempre (senza eccezione TD04).

### C.2 Dove calcolare scadenza_effettiva

Opzioni:
- A) Python service layer su write (consigliata)
- B) Trigger PL/pgSQL
- C) View calcolata on-read

Scelta consigliata: A (piu coerente col codebase e piu testabile in pytest).

### C.3 Normalizzazione fornitore

- Non esiste normalizza_fornitore dedicata.
- Usare priorita matching:
  1) piva_fornitore normalizzata (primaria)
  2) normalizza_stringa(fornitore) fallback

### C.4 Helper UI bottoni-nav

- Non esiste helper riusabile gia pronto.
- Per 2 punti d'uso previsti, consigliato copia-adatta senza astrazione prematura.

### C.5 Notifica scadenze imminenti

- Proposta: soglia 7 giorni.
- Aggiungere anche notifica scadute non pagate (piu prioritaria).

### C.6 Feature flag pagina nuova

- Pattern st.secrets.get e presente nel repo.
- Per MVP si puo evitare feature flag e rilasciare per step incrementali.

---

## Sezione D - Proposta finale integrata

### D.1 Discrepanze con severita

1) Doppio expander: in realta uno attivo + uno dead code
- Severita: Importante

2) Signature refactor parser/salvataggio non necessario
- Severita: Importante

3) Esistono gia cache_version e dismissed_notification_ids (riuso obbligato)
- Severita: Bloccante

4) Mancato riferimento iniziale a auto_invoice_notice
- Severita: Importante

5) Campi header gia presenti in fatture
- Severita: Minore

6) Propagazione soft-delete/ripristino verso fatture_documenti da progettare esplicitamente
- Severita: Importante

7) GDPR export/delete non aggiornati per nuove tabelle
- Severita: Importante

8) Collisione session_state senza prefisso gfn_
- Severita: Importante

### D.2 Integrazioni obbligatorie

- Riusare cache_version con nuove chiavi e trigger bump.
- Aggiungere propagazione deleted_at verso fatture_documenti.
- Estendere GDPR export e delete cascade con nuove tabelle.
- Spostare anche auto_invoice_notice nella nuova pagina.
- Rimuovere dead code app_controllers relativo al vecchio expander.
- Aggiungere notifica scadute non pagate oltre imminenti.

### D.3 Semplificazioni approvate

- Niente tabella notifiche_eventi.
- Niente cambio firme funzioni core upload.
- Niente trigger DB complessi per scadenza_effettiva in MVP.
- Niente helper UI generico ora.
- Niente feature flag obbligatoria in MVP.

### D.4 Schema finale fatture_documenti (MVP consigliato)

Colonne principali:
- id (uuid pk)
- user_id, ristorante_id, file_origine (unique tripla)
- fornitore, piva_fornitore, numero_documento
- data_documento, data_competenza, tipo_documento
- totale_documento, totale_imponibile, totale_iva
- segno_compensazione (check -1/+1)
- scadenza_xml, giorni_termini_xml
- scadenza_override, scadenza_effettiva, scadenza_source
- pagata, pagata_at, pagata_by, note_pagamento
- source_origin (manual/invoicetronic)
- created_at, updated_at, deleted_at

Index consigliati:
- (user_id, ristorante_id, deleted_at, scadenza_effettiva)
- (user_id, ristorante_id, pagata, scadenza_effettiva) where deleted_at is null
- (user_id, ristorante_id, piva_fornitore)

### D.5 Schema finale fornitori_pagamenti_config

Colonne:
- id (uuid pk)
- user_id, ristorante_id
- piva_fornitore nullable
- fornitore_norm nullable
- giorni_pagamento (0..365)
- data_riferimento (data_documento/fine_mese/fine_mese_successivo)
- attiva, note
- created_at, updated_at

Vincoli:
- almeno uno tra piva_fornitore e fornitore_norm valorizzato
- unique index parziali separati per piva e per fornitore_norm fallback

### D.6 Function signatures canoniche

- upsert_fattura_documento(user_id, ristorante_id, file_origine, payload, supabase_client=None) -> dict
- get_documenti(user_id, ristorante_id, pagata=None, only_overdue=False, days_until_due=None, fornitore_filter=None) -> list[dict]
- set_pagato_bulk(doc_ids, pagata, user_id, supabase_client=None) -> dict
- set_override_scadenza(doc_id, scadenza, user_id, supabase_client=None) -> dict
- clear_documenti_cache() -> None

- calcola_scadenza_effettiva(header: dict, regola_fornitore: dict | None) -> tuple[date | None, str]
- recompute_scadenze_per_regola(user_id, ristorante_id, regola_id, supabase_client=None) -> int
- get_scadenziario(user_id, ristorante_id, range_days=None, only_unpaid=True) -> list[dict]

- upsert_regola_fornitore(...) -> dict
- list_regole(user_id, ristorante_id) -> list[dict]
- disattiva_regola(regola_id, user_id) -> dict
- find_regola_for_documento(...) -> dict | None

- build_scadenze_alert_notifications(user_id, ristorante_id, days_window=7, reference_dt=None) -> list[dict]

### D.7 Migration plan finale

- 069_create_fatture_documenti.sql
  - tabella, indici, RLS, cache_version key + bump trigger
  - trigger propagazione deleted_at da fatture

- 070_create_fornitori_pagamenti_config.sql
  - tabella, vincoli, indici, RLS
  - cache_version key + bump trigger

- 071_backfill_fatture_documenti.sql
  - insert aggregato da fatture per file_origine (no inventare scadenze storiche)

### D.8 Step plan operativo aggiornato

1) Migrations 069-071 + validazione conti
2) Parser DatiPagamento + upsert documento dentro salva_fattura_processata
3) Nuova pagina skeleton + sezione Avvisi (incl. auto_invoice_notice)
4) Spostamento Gestione Fatture da app.py + cleanup dead code app_controllers
5) Sezione Pagamenti/Scadenze (bulk pagata + override)
6) Sezione Regole Fornitore + ricalcolo mirato
7) GDPR export/delete update + notifica scadute/imminenti
8) Test regressione + tuning cache_version

---

## Sezione E - Domande esplicite da risolvere PRIMA di Step 3

Prima di autorizzare il via a Step 3 (Nuova pagina skeleton + sezione Avvisi), queste 3 domande devono essere risolte per garantire implementazione davvero meccanica e zero ambiguità:

### E.1 Pattern import e setup nelle pagine esistenti

**Domanda:** Mostrami come page_setup.py e sidebar_helper.py vengono chiamati nelle pagine esistenti (es. gestione_account.py) — copierò lo stesso pattern di init nella nuova pagina.

**Risposta:**

Pattern coerente da replicare in `pages/5_gestione_fatture_e_notifiche.py`:

```python
import streamlit as st
import time

# 1. PATCH API Streamlit (subito dopo import st)
from utils.streamlit_compat import patch_streamlit_width_api
patch_streamlit_width_api()

# 2. IMPORT SERVICES / CONFIG
from services.db_service import clear_fatture_cache
from services import get_supabase_client
from config.logger_setup import get_logger

# 3. IMPORT UI HELPERS
from utils.sidebar_helper import render_sidebar, render_oh_yeah_header
from utils.ui_helpers import hide_sidebar_css

# 4. PAGE CONFIG (prima di ogni st.* call)
st.set_page_config(
    page_title="Gestione Fatture e Notifiche",
    page_icon="📋",
    initial_sidebar_state="expanded"
)

# 5. LOGGER
logger = get_logger('gestione_fatture_notifiche')

# 6. HIDE SIDEBAR SE NON LOGGATO
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    hide_sidebar_css()

# 7. VERIFICA AUTENTICAZIONE (prima di tutto il resto)
if 'logged_in' not in st.session_state or not st.session_state.logged_in:
    st.switch_page("app.py")
    st.stop()

# 8. CARICA USER E DATI SESSION
user = st.session_state.user_data
is_admin = st.session_state.get('user_is_admin', False)

# 9. SUPABASE CLIENT (try/except)
try:
    supabase = get_supabase_client()
except Exception as e:
    st.error("⛔ Errore di connessione al database. Riprova tra qualche minuto.")
    logger.exception("Errore connessione Supabase: %s", e)
    st.stop()

# 10. RENDER SHARED COMPONENTS
render_sidebar(user)
render_oh_yeah_header()

# 11. PAGE TITLE
st.markdown("""
<h2 style="font-size: clamp(2rem, 4.5vw, 2.8rem); font-weight: 700; margin: 0; margin-bottom: 10px;">
    📋 <span style="background: linear-gradient(...); -webkit-background-clip: text; ...">Gestione Fatture e Notifiche</span>
</h2>
""", unsafe_allow_html=True)
```

**Key points:**
- Sempre `patch_streamlit_width_api()` PRIMA di qualsiasi altro import/uso
- `set_page_config` PRIMA di render_sidebar
- `get_logger()` centralizzato
- Autenticazione e stop se non loggato
- `hide_sidebar_css()` se sessione scaduta
- Try/except su Supabase con logger.exception

### E.2 Componenti UI pre-stilizzate riusabili

**Domanda:** Nel CSS in static/, ci sono classi già pronte per badge colorati o card KPI che posso riusare per la sezione Pagamenti e Scadenze?

**Risposta:**

Sì! Componenti CSS pronti in `static/layout.css`:

**1. KPI CARD (perfetto per contatori pagamenti/scadenze)**
```css
.kpi-card {
    background: linear-gradient(135deg, rgba(248, 249, 250, 0.95), rgba(233, 236, 239, 0.95));
    padding: clamp(0.75rem, 2vw, 1.25rem);
    border-radius: 12px;
    border: 1px solid rgba(206, 212, 218, 0.5);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.kpi-label { color: #2563eb; font-weight: 600; font-size: clamp(0.7rem, 1.6vw, 0.85rem); }
.kpi-value { color: #1e40af; font-size: clamp(1.3rem, 3.5vw, 1.75rem); font-weight: 700; }
```

**2. COLORI PREDEFINITI per Column (nth-child selectors)**
```
Column 1: Blue    (#2196f3, #e3f2fd background)
Column 2: Green   (#4caf50, #e8f5e9 background)
Column 3: Orange  (#ff9800, #fff3e0 background)
Column 4: Red     (#f44336, #ffebee background)
```

**Per scadenziario UI, usare così:**
```python
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric(label="📥 Pagati", value=pagati_count)  # Blue
with col2:
    st.metric(label="⏳ Imminenti (7gg)", value=imminenti_count)  # Green
with col3:
    st.metric(label="⚠️ Scaduti non pagati", value=scaduti_count)  # Orange
with col4:
    st.metric(label="📋 Totali", value=totali_count)  # Red
```

Streamlit applica automaticamente gli stili Metric (già definiti in layout.css) con colori per colonna.

**3. PULSANTI E DOWNLOAD**
- Primary button: `button[kind="primary"]` → azzurro #0ea5e9
- Download button: `[data-testid="stDownloadButton"] button` → verde #28a745
- Secondary button: `button[kind="secondary"]` → grigio light
Tutti gia stylizzati, zero configurazione.

### E.3 Reset cross-page alla selezione ristorante

**Domanda:** Quando l'utente cambia ristorante dalla sidebar mentre è sulla nuova pagina, quale callback o check garantisce il reset completo delle chiavi gfn_* e l'invalidazione della cache documenti?

**Risposta:**

Il reset oggi avviene in [app.py](app.py#L2000-L2015) al cambio ristorante_id:

```python
# Da app.py righe ~1989-2020
if selected_ristorante['id'] != st.session_state.ristorante_id:
    # ... fetch dati ...
    
    # RESET STATE KEYS — lista completa:
    for _stale_key in ['uploaded_files', 'upload_context', 'df_cache', 'stats_database',
                       'last_selected_files', 'force_reload', 'force_empty_until_upload',
                       'files_errori_report', 'last_upload_summary', 
                       'last_upload_notification_context', 'ultimo_upload_ids',
                       'ingredienti_temp', 'ricetta_edit_mode', 'ricetta_edit_data',
                       '_fonte_pm_cache']:
        st.session_state.pop(_stale_key, None)
    
    # CLEAR CACHES
    clear_fatture_cache()  # già pulisce tutto tranne quelle non rls-controlled
    
    # SALVA ULTIMO RISTORANTE
    supabase.table('users').update({'ultimo_ristorante_id': selected_ristorante['id']}).eq('id', user['id']).execute()
    
    # RERUN
    st.rerun()
```

**Per la nuova pagina, aggiungere:**

Creare helper in `utils/ristorante_helper.py` (già esiste, già ha `add_ristorante_filter`):

```python
def reset_ristorante_session_state():
    """Pulisce tutte le chiavi session_state specifiche di un ristorante."""
    # Clear gfn_* keys della nuova pagina
    for key in list(st.session_state.keys()):
        if key.startswith('gfn_'):
            st.session_state.pop(key, None)
    # Clear documenti/scadenze/fornitori caches (da creare in servizi)
    try:
        from services.documenti_service import clear_documenti_cache
        from services.fornitori_config_service import clear_fornitori_cache
        from services.scadenze_service import clear_scadenze_cache
        clear_documenti_cache()
        clear_fornitori_cache()
        clear_scadenze_cache()
    except Exception as e:
        logger.warning(f"Errore clear cache specifiche: {e}")
```

Poi in `utils/ristorante_helper.py`, nella funzione che gestisce il cambio (o nel suo wrapper):

```python
def on_ristorante_changed():
    """Callback unico per reset cross-app."""
    clear_fatture_cache()  # Già presente in app.py
    reset_ristorante_session_state()  # Nuovo
    # ... resto logica salvataggioultimo_ristorante_id, rerun ...
```

**Verificare:** La sidebar che cambia ristorante deve essere in ENTRAMBE le pagine,Chiama lo stesso callback.
Nel nuovo refactor Step 4, centralizzare il callback in un'unica funzione per evitare duplicazione.

---

## Chiusura

Il piano sopra rende l'implementazione meccanica, evita over-engineering, e sfrutta al massimo i pattern gia consolidati nel repository (service_role, cache_version, dismiss notifiche persistente).

Una volta risolte le 3 domande della Sezione E, Step 3 puo procedere senza blocchi.

---

## Sezione G - Specifica operativa piano D.8 (Step-by-step dettagliato)

### STEP 1: Migrations 069/070/071
**Status:** ✅ COMPLETATO (migrations approvate in file)

**Decisioni finali approvate (11/05/2026):**

1. Naming definitivo in `fatture_documenti`: mantenere `piva_fornitore`.
    - In Sezione G usare `piva_fornitore` ovunque per l'header documento.
    - Mapping parser: `fatture.piva_cedente` (riga) -> `fatture_documenti.piva_fornitore` (header).

2. `scadenza_source` normalizzato lato parser:
    - Se esiste `DataScadenzaPagamento` -> source `xml`.
    - Se esistono solo `GiorniTerminiPagamento` -> source `xml` (non `xml_giorni`).
    - CHECK definitivo previsto: `('override','fornitore','xml','none')`.

3. Rimozione CHECK su `scadenza_xml >= data_documento` dalla migration 069.
    - Motivazione: non bloccare casi reali di scadenza antecedente.

---

### STEP 2: Parser DatiPagamento + upsert documento

**DOVE AGGIUNGERE PARSING:**

- **File:** `services/invoice_service.py`
- **Funzione:** `estrai_dati_da_xml(file_caricato, user_id: str = None)` — linea 543
- **Posizione esatta:** Dopo estrazione tipo_documento (linea ~700), PRIMA del loop `for idx, riga in enumerate(linee, start=1):` (linea ~820)

**PSEUDOCODICE ESTRAZIONE DATI HEADER (NUOVO BLOCCO — linea ~750-800):**

Aggiungere PRIMA del parsing DatiPagamento:

```
ESTRAZIONE DATI FORNITORE:
  # P.IVA cedente (fornitore che emette la fattura)
    piva_fornitore = safe_get(
      fattura,
      ['FatturaElettronicaHeader', 'CedentePrestatore', 'DatiAnagrafici', 'IdFiscaleIVA', 'IdCodice'],
      default=None,
      keep_list=False
  )
  # Normalizza: solo cifre, max 11 caratteri
    IF piva_fornitore:
            piva_fornitore = str(piva_fornitore).strip()[:11]  # Tutela da P.IVA malformate
  
  # Nome fornitore normalizzato (usa funzione consolidata estrai_fornitore_xml())
  # già estratto linea 703: fornitore = estrai_fornitore_xml(fattura)
  # (nessuna modifica, già presente)
  
  # fornitore_norm: versione normalizzata MAIUSCOLO di fornitore
  fornitore_norm = fornitore.upper() if fornitore else 'SCONOSCIUTO'
```

**PSEUDOCODICE PARSING DatiPagamento:**

```
NUOVE VARIABILI (dopo linea 800):
  _pagamenti_global = None  # DatiPagamento senza RiferimentoNumeroLinea
  _pagamenti_per_riga = {}   # riga_numero → {scadenza_xml, giorni_termini}
  # NOTA: metodo_pagamento_xml viene estratto ma NON salvato in DB (future_use per Step 8+)

IF TipoDocumento IN ('TD01', 'TD04', 'TD05', 'TD06', 'TD07', 'TD16..27', 'TD24'):
    dati_gen = FatturaElettronicaBody.DatiGenerali
    dati_pagamento_raw = dati_gen.get('DatiPagamento')
    
    IF dati_pagamento_raw:
        IF NOT isinstance(dati_pagamento_raw, list):
            dati_pagamento_raw = [dati_pagamento_raw]
        
        FOR dati_pag IN dati_pagamento_raw:
            # future_use: ModalitaPagamento = dati_pag.get('ModalitaPagamento')
            DettaglioPagamento = dati_pag.get('DettaglioPagamento')  # LISTA
            
            IF NOT isinstance(DettaglioPagamento, list):
                DettaglioPagamento = [DettaglioPagamento]
            
            scadenza_data_list = []      # DateScadenzaPagamento assolute (YYYY-MM-DD)
            giorni_termini_list = []     # GiorniTerminiPagamento (INT)
            
            FOR DetaglioPag IN DettaglioPagamento:  # PUO' ESSERE MULTIPLO
                DataScadenzaPagamento = DetaglioPag.get('DataScadenzaPagamento')  # YYYY-MM-DD
                GiorniTerminiPagamento = DetaglioPag.get('GiorniTerminiPagamento')  # INT
                
                IF DataScadenzaPagamento:
                    scadenza_data_list.append(DataScadenzaPagamento)
                
                IF GiorniTerminiPagamento:
                    giorni_termini_list.append(int(GiorniTerminiPagamento))
            
            # GERARCHIA SCADENZA (NON è max() indipendente):
            # 1. Se DataScadenzaPagamento esiste → usare data assoluta (max per coprire multipli)
            # 2. Se SOLO GiorniTerminiPagamento → usare giorni (verrà calcolata data_documento + giorni)
            # 3. Se nessuno → scadenza_xml = NULL, giorni_termini = NULL
            
            scadenza_xml_finale = None
            giorni_termini_finale = None
            
            IF scadenza_data_list:
                # Data assoluta ha priorità: scegli la più lontana (max)
                scadenza_xml_finale = max(scadenza_data_list)
                # Ignora giorni se abbiamo data assoluta
                giorni_termini_finale = None
            ELIF giorni_termini_list:
                # Solo giorni termini
                scadenza_xml_finale = None
                giorni_termini_finale = max(giorni_termini_list)  # Scegli più giorni
            # ELSE: entrambi NULL → scadenza_xml_finale e giorni_termini_finale restano NULL
            
            RiferimentoNumeroLinea = dati_pag.get('RiferimentoNumeroLinea')
            
            IF RiferimentoNumeroLinea IS NULL:
                _pagamenti_global = {
                    'scadenza_xml': scadenza_xml_finale,
                    'giorni_termini': giorni_termini_finale
                    # future_use: 'metodo_pagamento': metodo_pag_xml (NON salvare in fatture_documenti v1)
                }
            ELSE:
                IF NOT isinstance(RiferimentoNumeroLinea, list):
                    RiferimentoNumeroLinea = [RiferimentoNumeroLinea]
                FOR NumLinea IN RiferimentoNumeroLinea:
                    _pagamenti_per_riga[int(NumLinea)] = {
                        'scadenza_xml': scadenza_xml_finale,
                        'giorni_termini': giorni_termini_finale
                    }
```

**INTEGRAZIONE NEL LOOP RIGHE (linea ~1040):**

All'interno del `for idx, riga in enumerate(linee, start=1):`:

```
_num_linea_xml = int(riga.get('NumeroLinea') or 0)
_pag_data = _pagamenti_per_riga.get(_num_linea_xml) or _pagamenti_per_riga.get(idx) or _pagamenti_global or {}

scadenza_xml = _pag_data.get('scadenza_xml')
giorni_termini_xml = _pag_data.get('giorni_termini')
# future_use: metodo_pagamento_xml = _pag_data.get('metodo_pagamento')  # NON salvare attualmente
```

**FLUSSO DATI HEADER verso upsert_fattura_documento:**

Dopo il loop righe, prima di ritornare righe_prodotti, assicurare che dati_prodotti[0] (header di riga) contenga TUTTI questi campi estratti:

```
# Nella struttura della PRIMA riga (dati_prodotti[0]) aggiungere:
dati_prodotti[0]['scadenza_xml'] = scadenza_xml_finale  # estratto da DatiPagamento
dati_prodotti[0]['giorni_termini_xml'] = giorni_termini_finale  # estratto da DatiPagamento
dati_prodotti[0]['piva_fornitore'] = piva_fornitore  # P.IVA fornitore (emittente)
dati_prodotti[0]['fornitore_norm'] = fornitore_norm  # fornitore MAIUSCOLO normalizzato
dati_prodotti[0]['tipo_documento'] = tipo_documento  # già presente
dati_prodotti[0]['totale_documento'] = totale_documento  # già presente
dati_prodotti[0]['totale_imponibile'] = totale_imponibile  # già presente
dati_prodotti[0]['totale_iva'] = totale_iva  # già presente
dati_prodotti[0]['data_documento'] = data_documento  # già presente
```

**FLUSSO DATI COMPLETO:**

1. `estrai_dati_da_xml()` legge header XML:
   - Estrae tipo_documento, data_documento, totali (imponibile, IVA, documento)
   - Estrae fornitore via `estrai_fornitore_xml()` e lo normalizza in fornitore_norm
    - Estrae piva_fornitore (IdCodice da CedentePrestatore.DatiAnagrafici.IdFiscaleIVA)
   - Parsa DatiPagamento → calcola scadenza_xml, giorni_termini_xml
    - Normalizza `scadenza_source='xml'` sia per DataScadenzaPagamento sia per GiorniTerminiPagamento

2. Parser popola dati_prodotti[0] (header riga) con: tipo_documento, data_documento, totali, fornitore, piva_fornitore, fornitore_norm, scadenza_xml, giorni_termini_xml

3. Loop righe: per ogni riga, estrae scadenza_xml/giorni_termini da _pagamenti_per_riga dict

4. `estrai_dati_da_xml()` ritorna righe_prodotti list con tutti i dati

5. `salva_fattura_processata(nome_file, dati_prodotti, ...)` riceve righe_prodotti
    - Insert bulk righe in tabella fatture (salva fornitore per ogni riga; `piva_cedente` resta colonna riga storica)
   - **DOPO insert verifica integrità**: Chiama `upsert_fattura_documento(dati_prodotti[0], user_id, ristorante_id)` 

6. `upsert_fattura_documento()` estrae header da dati_prodotti[0]:
    - file_origine, piva_fornitore, fornitore_norm, numero_documento, data_documento, tipo_documento
   - totale_documento, totale_imponibile, totale_iva
   - scadenza_xml, giorni_termini_xml
   - Calcola segno_compensazione (TD04 → -1, altrimenti 1)
   - UPSERT su fatture_documenti con chiave (user_id, ristorante_id, file_origine)

**Cache da invalidare:**
- `clear_fatture_cache()` (già presente dopo insert fatture)
- Nuova: `clear_documenti_cache()` (dopo upsert_fattura_documento in documenti_service.py)

**VERIFICA BACKFILL MIGRATION 071:**

Migration 071 legge fatture (righe) e aggrega per (user_id, ristorante_id, file_origine):
- piva_fornitore: recupera da `fatture.piva_cedente` (prima riga non-NULL della tripla)
    (Nota: naming intenzionale: sorgente riga `piva_cedente` -> target header `piva_fornitore`)
- fornitore_norm: recupera come UPPER(fornitore) da prima riga della tripla

**AZIONE (CONFERMATA):** mantenere l'approccio già definito:
- migration 069.5 aggiunge `piva_cedente` su `fatture`
- migration 071 usa `piva_cedente` per popolare `fatture_documenti.piva_fornitore`

---

### STEP 2.B: Nuove funzioni documenti_service.py

**FILE:** `services/documenti_service.py` (nuovo)

**FUNZIONE 0: get_cache_version(key: str, supabase_client)**

Legge la versione corrente della cache dal DB (non da session_state).

```
Firma: get_cache_version(key: str, supabase_client) -> int

Implementazione:
  try:
      response = supabase_client.table("cache_version")
          .select("version")
          .eq("key", key)
          .execute()
      return response.data[0]["version"] if response.data else 0
  except Exception as e:
      logger.warning(f"Cache version read fallito per key={key}: {e}")
      return 0
  
Uso in get_documenti_list():
  1. Leggi current_version = get_cache_version("fatture_documenti", supabase_client)
  2. Leggi local_version = st.session_state.get("gfn_documenti_cache_version", 0)
  3. IF current_version != local_version:
       -> Invalida cache locale, ricaricare da DB
       -> Aggiorna st.session_state.gfn_documenti_cache_version = current_version
     ELSE:
       -> Usa cache locale se disponibile
```

**FUNZIONI 1-6:** Restanti funzioni (come da specifica originaria di Step 2):
  1. `upsert_fattura_documento()`
  2. `get_documenti_list()`
  3. `set_pagato_bulk()`
  4. `set_override_scadenza()`
  5. `clear_documenti_cache()`
  6. (futura: altre funzioni di supporto)

---

### STEP 2.C: Centralizzazione upsert in upload_handler.py

**FILE:** `services/upload_handler.py` (modifica — NEW file di modifica)

**PUNTO DI INSERIMENTO:** Linea 1347 in `handle_uploaded_files()`, DENTRO il blocco `if result["success"]:`

**FLUSSO ATTUALE (linee 1332-1360):**
```
if result["success"]:                          # linea 1332
    file_processati += 1                       # 1333
    righe_batch += result["righe"]             # 1334
    if result["location"] == "supabase":
        salvati_supabase += 1
    elif result["location"] == "json":
        salvati_json += 1
    
    if 'force_empty_until_upload' in st.session_state:
        del st.session_state.force_empty_until_upload
    
    file_ok.append(file.name)                  # linea 1347 ← PUNTO DI INSERIMENTO
```

**CODICE DA AGGIUNGERE (dopo linea 1347, prima di TD04 detection):**

```
    # NUOVO: Upsert documento in fatture_documenti (supporta sia XML che Vision)
    try:
        if isinstance(items, list) and len(items) > 0 and items[0]:
            from services.documenti_service import upsert_fattura_documento
            upsert_fattura_documento(
                items[0],  # header row con campi estratti
                user_id=st.session_state.get('user_data', {}).get('id'),
                ristorante_id=st.session_state.get('ristorante_id'),
                supabase_client=supabase
            )
    except Exception as doc_err:
        logger.warning(
            f"⚠️ DOCUMENTO ORFANO: {file.name} — righe salvate in fatture "
            f"ma documento non creato in fatture_documenti. "
            f"Errore: {doc_err}"
        )
        # NON propagare errore — upload rimane SUCCESS, righe fatture già salvate
```

**NOTA IMPORTANTE:** Il try/except SEPARATO garantisce che:
- Se `salva_fattura_processata()` fallisce → upload BLOCCATO (result["success"]=False), nessun upsert
- Se `upsert_fattura_documento()` fallisce → WARNING loggato, NESSUN blocco, upload rimane SUCCESS
- Righe fatture SEMPRE salvate prima del tentativo upsert
- Recovery possibile via migration 071 se upsert fallisce

**CONVERGENZA:** Questo punto di inserimento (linea 1347) è COMUNE sia per XML che per Vision (PDF/JPG/PNG) perché:
1. Entrambi i path convergono a `salva_fattura_processata(nome_file, items, silent=True, ...)` — linea 1329
2. Entrambi popola `items` (list[dict]) con headers nella prima riga — items[0]
3. Upsert operi su items[0] indipendentemente dalla fonte (XML o Vision)

---

## RIEPILOGO FILE STEP 2 (AGGIORNATO):

✏️ **Modifica:** `services/invoice_service.py`
  - Funzione 1A: `estrai_dati_da_xml()` — linea 543 (parsing DatiPagamento + header fields)
  - Funzione 1B: `salva_fattura_processata()` — linea 1402 (chiama upsert DOPO verifica integrità)

✏️ **Modifica:** `services/upload_handler.py`
  - Linea 1347 in `handle_uploaded_files()` — centralizzato upsert_fattura_documento() per XML + Vision

✨ **Crea:** `services/documenti_service.py`
  - Funzione 0: `get_cache_version()` — lettura versione cache da DB
  - Funzione 1-6: upsert_fattura_documento, get_documenti_list, set_pagato_bulk, set_override_scadenza, clear_documenti_cache, ...

---

### STEP 3: Skeleton pagina + Sezione Avvisi

**FILE PRINCIPALE:** `pages/5_gestione_fatture_e_notifiche.py` (nuovo)

**SETUP PATTERN (dal template E.1):**
- Lines 1-30: Patch Streamlit, import, page_config, logger, hide_sidebar_css, auth check
- Lines 31-50: Carica user/admin flag, get_supabase_client
- Lines 51-60: render_sidebar + render_oh_yeah_header
- Lines 61-80: Page title markdown

**CHIAVI SESSION_STATE (gfn_ namespace):**

| Chiave | Tipo Python | Valore iniziale | Set quando | Reset quando |
|---|---|---|---|---|
| `gfn_sezione_attiva` | str | `'avvisi'` | Utente clicca bottone nav | Cambio ristorante OR reset_ristorante_session_state() |
| `gfn_is_loading_scadenzario` | bool | False | Durante fetch scadenziario | Completamento fetch |
| `gfn_is_loading_regole` | bool | False | Durante fetch regole | Completamento fetch |
| `gfn_documenti_cache_version` | int | 0 | Al render (leggi da cache_version.version) | Se version DB > locale |
| `gfn_regole_cache_version` | int | 0 | Al render (leggi da cache_version.version) | Se version DB > local |
| `gfn_selected_documento_id` | str or None | None | Utente clicca riga scadenziario | Completamento azione (flag pagato/override) |
| `gfn_form_regola_visible` | bool | False | Utente clicca "+ Aggiungi Regola" | Salvataggio o cancellazione form |
| `gfn_form_regola_data` | dict | {} | Form compilation | Form reset o submit |
| `gfn_override_scadenza_editing` | str or None | None | Utente clicca "Modifica Scadenza" | Salvataggio override |

**RESET GFN_* AL CAMBIO RISTORANTE:**

Riga da aggiungere in **app.py**, linea 2020 (dopo `clear_fatture_cache()` nel blocco cambio ristorante):

```python
# Linea 2020 (DOPO clear_fatture_cache()):
# RESET nuova pagina gfn_* keys
for _gfn_key in list(st.session_state.keys()):
    if _gfn_key.startswith('gfn_'):
        st.session_state.pop(_gfn_key, None)
# Invalida cache nuove tabelle
try:
    from services.documenti_service import clear_documenti_cache
    from services.fornitori_config_service import clear_fornitori_cache
    clear_documenti_cache()
    clear_fornitori_cache()
except Exception as _e:
    logger.warning(f"Errore clear cache specifiche: {_e}")
```

**LOADING COMPORTAMENTO:**

Per ogni sezione principale (Avvisi, Pagamenti, Regole):
- **Spinner di caricamento** (linea check: `if st.session_state.gfn_is_loading_X: st.spinner("...")`)
- **Dopo caricamento:** render tabella/form coerente con pattern dashboard (buttons + sezione_attiva, non tabs)
- **Fallback empty state:** "Nessun record disponibile" con emoji appropriata

---

### STEP 4: Cleanup dead code

**FILE: utils/app_controllers.py**

Eliminare completamente la funzione (linee 1176-1685):
```
LINEE ESATTE DA RIMUOVERE:
  1176-1685: intera funzione render_dashboard_ui()
             (incluso docstring, logica, helper innestati)
```

**FILE: app.py**

Rimuovere la RIGA DI COMMENTO che elenca il path non usato:
```
LINEA ~1177 (in app.py): cerca commento tipo "# render_dashboard_ui(supabase, logger, user)"
                         e rimuovilo se presente
```

Verificare che `render_sidebar` e `render_oh_yeah_header` siano ancora importati e usati (lo sono).

**Conseguenza:** `app_controllers.py` rimane utile per `mostra_pagina_login`, `load_and_setup_session`, `render_sidebar_and_header`, ma `render_dashboard_ui` sparisce.

---

### STEP 5: Sezione Pagamenti e Scadenze

**Nella stessa pagina `pages/5_gestione_fatture_e_notifiche.py`**, aggiungere la TAB/BOTTONE "Pagamenti":

**UI Wireframe testuale:**

```
┌─ 3 BOTTONI NAVIGAZIONE ─────────────────────────────┐
│ [🚨 AVVISI]  [💳 PAGAMENTI]  [⚙️ REGOLE FORNITORE]   │
└────────────────────────────────────────────────────┘

SEZIONE PAGAMENTI E SCADENZE:
┌─ KPI ROW (4 colonne, colori CSS layout.css) ────────┐
│ Col1 (Blue):   📥 Pagati: 42                         │
│ Col2 (Green):  ⏳ Imminenti (7gg): 15                │
│ Col3 (Orange): ⚠️ Scaduti non pagati: 8              │
│ Col4 (Red):    📋 Totali: 120                        │
└────────────────────────────────────────────────────┘

FILTRI:
  🔍 Fornitore: [dropdown all fornitori]
  📅 Data da/a: [datepicker range]
  ☑️ Solo non pagati: [checkbox]

TABELLA SCADENZIARIO:
  Colonne: File | Fornitore | Data Scadenza | GG Rimasti | Importo | Pagato [toggle] | Azioni [menu]
  
  Row example:
    | INV-2026-001.xml | FASTWEB | 2026-05-17 | 7gg | €450,00 | ☑️ | [Modifica] [Pagato]
    | INV-2026-002.xml | TIM     | 2026-05-10 | 0gg ❌ | €320,00 | ☐️ | [Modifica] [Pagato]
  
AZIONI RIGA:
  - "Modifica Scadenza": apre modal con datepicker, salva override
  - "Pagato": toggle boolean pagata=true, scrive pagata_at=now()
  - Bulk action: checkbox row → "Segna tutti come pagati" button

```

**Comportamento al salvataggio (sia toggle pagato, sia override scadenza):**

1. UI: `st.spinner("Aggiornamento in corso...")` mostra progressione
2. Service layer chiama `set_pagato_bulk()` o `set_override_scadenza()`
3. Service scrive su DB (fatture_documenti)
4. Service ricalcola scadenza_effettiva se necessario
5. Trigger DB bumpa cache_version['fatture_documenti']
6. UI: `st.success("✅ Aggiornamento completato")` + reset gfn_selected_documento_id
7. UI: `st.rerun()` per ricarica tabella

---

### STEP 6: Sezione Regole Fornitore

**NELLA STESSA PAGINA**, aggiungere la TAB/BOTTONE "Regole Fornitore":

**UI Wireframe testuale:**

```
┌─ INTESTAZIONE + BOTTONE ────────────────────────────┐
│ ⚙️ Gestisci Regole Pagamento per Fornitore           │
│ [+ Aggiungi Nuova Regola] button (primary, blue)     │
└────────────────────────────────────────────────────┘

TABELLA REGOLE ATTIVE:
  Colonne: P.IVA / Fornitore | Giorni | Riferimento | Attiva | Azioni
  
  Row:
    | 12345678901 / FASTWEB | 30gg | Data Documento | ✓ (toggle) | [Modifica] [Elimina]
    | N/A / "Telecom Italia" | 60gg | Fine Mese | ✓ | [Modifica] [Elimina]

FORM INSERIMENTO/MODIFICA (modal o expander):
  [P.IVA Fornitore]           [text input, 11 cifre]  (preferiamo questo)
  ─ oppure ─
  [Nome Fornitore]            [autocomplete da fatture precedenti]
  
  [Giorni Pagamento]          [number input, 0-365]  [giorni]
  
  [Data Riferimento]          [dropdown 3 scelte]
    • Data Documento (default)
    • Fine Mese
    • Fine Mese Successivo
  
  [Note (opzionale)]          [text area]
  
  [☐️ Attiva]                 [checkbox, default TRUE]
  
  [Salva] [Annulla]

COMPORTAMENTO AL SALVATAGGIO:
  1. Valida: P.IVA XOR Nome, giorni_pagamento tra 0-365
  2. st.spinner("Salvataggio regola...")
  3. Chiama upsert_regola_fornitore()
  4. Service scrive su DB (fornitori_pagamenti_config)
  5. Service chiama recompute_scadenze_per_regola(regola_id)
     → st.info(f"📊 Ricalcolate scadenze: {N} documenti aggiornati")
  6. Trigger DB bumpa cache_version['fornitori_pagamenti_config']
  7. UI: st.success("✅ Regola salvata") + modal chiude
  8. Ricarica tabella regole

COMPORTAMENTO AL DISATTIVAZIONE (toggle):
  1. User clicca toggle "Attiva" → diventa FALSE
  2. Service: UPDATE ... SET attiva=false
  3. Service: recompute_scadenze_per_regola() cancella scadenza_source='fornitore' (torna a 'none')
  4. st.info("📊 Scadenze ricanculate: {N} documenti")
```

---

### STEP 7: GDPR Export e Delete Cascade

**FILE: pages/gestione_account.py**

**SEZIONE EXPORT (linee 175-410):**

Aggiungere dopo la query `upload_events` (linea ~290):

```python
# LINEA ~295 (NUOVO BLOCCO):
# Query 7: fatture_documenti con paginazione
# DESIGN CHOICE: NON filtriamo per ristorante_id perché l'export GDPR deve includere
# TUTTI i documenti associati all'utente su tutti i suoi ristoranti.
# Questo è coerente con l'art. 15 GDPR (Diritto di accesso) che richiede
# TUTTI i dati personali detenuti dal titolare, indipendentemente da logica aziendale.
# La cascata DELETE (Step 7 cascade delete) usa DELETE.eq('user_id', user_id)
# senza filtro ristorante_id perché l'utente che richiede cancellazione deve avere
# la propria cancellazione completa: RLS + policy app layer garantiscono
# che l'utente possa SOLO cancellare fatture del PROPRIO ristorante (via UI),
# ma GDPR delete deve essere "totale per utente" a livello tecnico.
try:
    fd_export = []
    offset = 0
    page_size = 1000
    while True:
        fd_query = supabase.table('fatture_documenti').select(
            'file_origine, fornitore, piva_fornitore, numero_documento, '
            'data_documento, totale_documento, scadenza_xml, scadenza_override, '
            'scadenza_effettiva, pagata, pagata_at, created_at'
        ).eq('user_id', user_id)\
         .is_('deleted_at', 'null')\
         .order('created_at', desc=False)\
         .range(offset, offset + page_size - 1)\
         .execute()
        rows = fd_query.data or []
        if not rows:
            break
        fd_export.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    if fd_export:
        export_data["fatture_documenti"] = fd_export
except Exception as e:
    logger.warning(f"Errore query fatture_documenti export: {e}")

# Query 8: fornitori_pagamenti_config con paginazione
try:
    frn_export = []
    offset = 0
    page_size = 1000
    while True:
        frn_query = supabase.table('fornitori_pagamenti_config').select(
            'piva_fornitore, fornitore_norm, giorni_pagamento, '
            'data_riferimento, attiva, note, created_at'
        ).eq('user_id', user_id)\
         .eq('attiva', True)\
         .order('created_at', desc=False)\
         .range(offset, offset + page_size - 1)\
         .execute()
        rows = frn_query.data or []
        if not rows:
            break
        frn_export.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    if frn_export:
        export_data["fornitori_pagamenti_config"] = frn_export
except Exception as e:
    logger.warning(f"Errore query fornitori_pagamenti_config export: {e}")
```

**SEZIONE DELETE CASCADE (linee 475-525):**

Aggiungere due righe nella lista `tables_to_clean` (che parte linea ~480) in **Step 7**, dopo stabilizzazione Step 6:

```python
# LINEA ~495 (AGGIUNGERE A tables_to_clean):
    ('fatture_documenti', 'user_id'),
    ('fornitori_pagamenti_config', 'user_id'),

# (DOPO la riga ('ristoranti', 'user_id'))
```

**Decisione di rollout (11/05/2026):**
- Non implementare ora la delete cascade di queste due tabelle.
- Inserire subito un TODO comment nel piano di implementazione Step 7 (non nel codice in questa fase).
- Eseguire la modifica in `pages/gestione_account.py` solo dopo Step 6 stabile.

**CONFERMA DELETE STRATEGY:**

Per GDPR Art. 17 (Right to be Forgotten), DELETE.eq('user_id', user_id) **È SUFFICIENTE** (senza filtro ristorante_id):

- ✅ **Motivo 1 — RLS + Policy coerenti:**
  Tutte le tabelle nuove (fatture_documenti, fornitori_pagamenti_config) hanno RLS ENABLE 
  senza policy (service_role only), stesso pattern di fatture/fatture_queue.
  La colonna ristorante_id esiste per app-layer filtering, ma il DELETE by user_id
  viene eseguito con service_role key (admin) e può cancellare l'intero storico utente
  senza vincoli di ristorante.

- ✅ **Motivo 2 — Completezza legale:**
  GDPR richiede che la cancellazione sia TOTALE per l'utente in un unico request,
  non frammentata per ristorante. Le tabelle hanno chiave composta (user_id, ristorante_id),
  quindi DELETE.eq('user_id', user_id) rimuove TUTTE le righe indipendentemente da ristorante_id.

- ✅ **Motivo 3 — Soft-delete consistency:**
  Sia fatture che fatture_documenti supportano soft-delete (deleted_at).
  Nel DELETE cascade (admin purge), non usiamo soft-delete: usiamo .delete() fisico
  perché è richiesta cancellazione legale, non archivio.

**NESSUN'ALTRA CASCATA NECESSARIA.** Il trigger `fn_propagate_deleted_at_fatture()`
(che mappa soft-delete da fatture → fatture_documenti) NON è rilevante qui:
la GDPR delete è hard delete, non soft.

Verifica esatta: il codice oggi è:
```python
tables_to_clean = [
    ('prodotti_utente', 'user_id'),
    ...
    ('ristoranti', 'user_id'),  # ← AGGIUNGI DOPO QUESTA
]
```

---

### STEP 8: Test regressione + integrazione cache_version

**Azioni opzionali nel MVP (Step 8 conclusivo):**

1. Verificare che tutte le cache_version keys siano presenti:
   - 'memoria_classificazione' (mig 068)
   - 'fatture_documenti' (mig 069)
   - 'fornitori_pagamenti_config' (mig 070)

2. Python test per `calcola_scadenza_effettiva()`:
   - Test con diverse combinazioni (override > fornitore > xml > none)
   - Test TD04 con segno_compensazione -1

3. Pytest per upsert_fattura_documento con Supabase locale

4. **TEST INTEGRAZIONE CROSS-PAGE (manuale + automatizzabile):**

   **Scenario:** Dopo `set_pagato_bulk()` sulla pagina `5_gestione_fatture_e_notifiche.py`, 
   verificare che `get_fatture_per_dashboard()` (usato da dashboard.py) restituisca 
   dati aggiornati SENZA riavvio app Streamlit.

   **Struttura test (MANUALE):**
   ```
   1. Apri Streamlit app (http://localhost:8501)
   2. Naviga a "2_Dashboard Analisi"
      → Verificare che KPI iniziale mostra N righe fatture (es. 120)
   3. Apri pagina "5_Gestione Fatture e Notifiche"
   4. Sezione Pagamenti: seleziona 5 fatture non pagate
   5. Clicca "Segna come Pagati" → spinner → success message
   6. TORNA a "2_Dashboard Analisi" (click sidebar)
   7. Verificare: KPI righe fatture è ora N-5 (senza reload, senza F5)
      → Se SUCCESSO: cache cross-page funziona ✅
      → Se FALLIMENTO: cache non invalidata correttamente ❌
   ```

   **Struttura test (AUTOMATIZZABILE - Pytest + Supabase):**
   ```python
   # File: tests/test_sync_cross_page.py
   
   def test_pagato_bulk_invalidates_dashboard_cache(supabase_test_client):
       """Verifica che set_pagato_bulk() invalida cache dashboard senza reload."""
       
       # Setup
       user_id = "test-user-123"
       ristorante_id = "test-rest-1"
       
       # 1. Carica fatture documento di test (5 record, pagata=false)
       test_rows = [...]  # Lista 5 dict fatture_documenti
       supabase_test_client.table('fatture_documenti').insert(test_rows).execute()
       
       # 2. Leggi cache versione PRIMA (es. version=1)
       version_before = supabase_test_client.table('cache_version')\
           .select('version').eq('key', 'fatture_documenti')\
           .single().execute().data['version']
       
       # 3. Esegui set_pagato_bulk() con i 5 record
       from services.documenti_service import set_pagato_bulk
       set_pagato_bulk(
           documento_ids=['doc1', 'doc2', 'doc3', 'doc4', 'doc5'],
           user_id=user_id,
           supabase=supabase_test_client
       )
       
       # 4. Verifica che trigger ha bumped version (es. version=2)
       version_after = supabase_test_client.table('cache_version')\
           .select('version').eq('key', 'fatture_documenti')\
           .single().execute().data['version']
       
       assert version_after > version_before, "Trigger non ha bumped cache_version"
       
       # 5. Simulazione Streamlit: leggi session_state[gfn_documenti_cache_version]
       #    e confronta con versione DB
       #    (in app reale, st.session_state['gfn_documenti_cache_version'] sarà < version_after)
       #    → Streamlit invalidà cache e chiama get_fatture_per_dashboard()
       
       # 6. Verifica dati: count(pagata=true) per la tripla user/rist
       pagati = supabase_test_client.table('fatture_documenti')\
           .select('id', count='exact')\
           .eq('user_id', user_id)\
           .eq('ristorante_id', ristorante_id)\
           .eq('pagata', True)\
           .execute()
       
       assert pagati.count == 5, f"Atteso 5 pagati, trovati {pagati.count}"
       
       # 7. Bonus: verificare che dashboard_service richiama il nuovo count
       from services.margine_service import get_fatture_stats
       stats = get_fatture_stats(user_id, ristorante_id, supabase=supabase_test_client)
       
       assert stats['totale_pagati'] >= 5, "Dashboard stats non sincronizzate"
   ```

   **Criteri di "done":**
   - ✅ Version bump registrato in cache_version table dopo set_pagato_bulk()
   - ✅ Dashboard legge version bumped e invalida locale cache
   - ✅ KPI dashboard riflette dati aggiornati senza F5
   - ✅ Test Pytest passa senza app restart

5. Manuale: verificare dashboard non regredisce (KPI, espander gestione fatture rimane)

---

**END SPECIFICA STEP-BY-STEP D.8**

---

## Sezione H — Revisione critica pre-Step 2

Dopo lettura approfondita di Sezione G, invoice_service.py (estrai_dati_da_xml, salva_fattura_processata), db_service.py (pattern servizi), migration 069 (trigger), identifico 6 aree critiche.

### H.1 LACUNE nella specifica Step 2 che potrebbero causare bug in prod

**Lacuna 1: Campo metodo_pagamento_xml orfano**

Nel pseudocodice Step 2, il parser estrae `metodo_pagamento_xml = ModalitaPagamento` e lo salva in `_pag_data` dict:
```
'metodo_pagamento': ModalitaPagamento  # SALVA PER FUTURE USE
```

Ma nella migrazione 069, **fatture_documenti NON ha colonna per metodo_pagamento**. Il campo viene ignorato lato DB.

**Impatto:** Confusione durante implementazione: dove salvo metodo_pagamento? Serve nuova colonna o è davvero solo "future use"?

**Soluzione:** Chiarire nella specifica Step 2:
```
METODO_PAGAMENTO: Estrai da ModalitaPagamento ma NON salvare in DB (ancora).
Future enhancement: aggiungere colonna fatture_documenti.metodo_pagamento + regole per "Bonifico entro 30gg", "Assegno", ecc.
Per ora: estrai, loga, ignora.
```

---

**Lacuna 2: Priorità DataScadenzaPagamento vs GiorniTerminiPagamento inesplicita**

Il pseudocodice accumula ENTRAMBI in liste separate:
```
scadenza_csv_list.append(DataScadenzaPagamento)       # data assoluta
giorni_csv_list.append(GiorniTerminiPagamento)        # delta giorni
```

Poi sceglie max() di entrambe INDIPENDENTEMENTE:
```
scadenza_xml_finale = max(scadenza_csv_list)          # max data
giorni_termini_finale = max(giorni_csv_list)          # max giorni
```

**Problema:** Se XML ha:
- DettaglioPagamento 1: DataScadenzaPagamento = 2026-05-20 (e GiorniTerminiPagamento = NULL)
- DettaglioPagamento 2: GiorniTerminiPagamento = 60 (e DataScadenzaPagamento = NULL)

Risultato: scadenza_xml_finale = 2026-05-20, giorni_termini_finale = 60. Ma quale usa calcola_scadenza_effettiva?

**Soluzione:** Specifica Step 2 deve dire:

```
GERARCHIA SCADENZA:
1. Se DataScadenzaPagamento esiste → usare quella (assoluta)
2. Se SOLO GiorniTerminiPagamento esiste → calcolare data_documento + N giorni lato Python
3. Se entrambi assenti → scadenza_xml = NULL, giorni_termini_xml = NULL

Pseudocodice corretto:
  IF DataScadenzaPagamento_list:
      scadenza_xml_finale = max(DataScadenzaPagamento_list)
      giorni_termini_finale = None  # ignora giorni se abbiamo data assoluta
  ELSE IF GiorniTerminiPagamento_list:
      scadenza_xml_finale = None
      giorni_termini_finale = max(GiorniTerminiPagamento_list)
      # Nota: calcolo data avverrà in calcola_scadenza_effettiva lato Python
  ELSE:
      scadenza_xml_finale = None
      giorni_termini_finale = None
```

---

**Lacuna 3: Estrazione piva_fornitore NON inclusa in pseudocodice**

Nel codice attuale invoice_service.py, esistono funzioni:
- `estrai_fornitore_xml()` — legge CedentePrestatore.Denominazione
- `estrai_piva_cessionario_xml()` — legge CessionarioCommittente.IdCodice

Ma il pseudocodice Step 2 NON menciona dove/come estrarre `piva_fornitore` che è colonna in fatture_documenti.

**Lettura codice attuale linea 746-760:**
```python
fornitore = estrai_fornitore_xml(fattura)
piva_cessionario = estrai_piva_cessionario_xml(fattura)  # Destinatario della fattura
```

Deve essere estratto ANCHE `piva_cedente` (P.IVA mittente fattura):
```python
piva_fornitore = estrai_piva_cedente_xml(fattura)  # CedentePrestatore.IdFiscaleIVA.IdCodice
```

**Soluzione:** Aggiungere al pseudocodice Step 2, PRIMA del loop righe:
```
piva_fornitore = estrai_piva_cedente_xml(fattura)  # 11 cifre normalizzate
```

E nel loop: aggiungere ai dict righe per passaggio a upsert_fattura_documento.

---

### H.2 EDGE CASE NON COPERTI dal pseudocodice attuale

**Edge Case 1: Fatture P7M (file compresso)**

Scenario: Utente carica `Fattura_2026_05.xml.p7m` (firma digitale).

Lo stream attuale (Streamlit → estrai_dati_da_xml) riceve il file compresso, NON il file XML puro.

**Impatto:** estrai_dati_da_xml prova a parsare XML su bytes compresso → fallisce.

**Nota:** Questo è CALLER responsibility, non Step 2. Il worker FastAPI o Streamlit DEVE decomprimere P7M prima di passare a estrai_dati_da_xml. Step 2 assume input è sempre XML puro.

**Action:** Documentare in Step 2 che questo è fuori scope. I.e. "P7M decompression è responsabilità del layer invocante (worker/Streamlit)".

---

**Edge Case 2: Fatture estratte da PDF via Vision AI**

Scenario: PDF invoice → Vision AI estrae righe → salva_fattura_processata riceve list[dict] SenzA dati_prodotti[0] con header XML (type_documento, totale_documento, scadenza_xml, etc.).

**Impatto:** Vision AI NON parser DatiPagamento da PDF (nessun XML structure), quindi scadenza_xml sempre NULL.

**Esperienza utente:** Fatture PDF hanno scadenza_source='none', solo regole fornitore/override potranno calcolare scadenza.

**Action:** Design coerente — Step 2 NON deve cambiar nulla. Vision AI rimane fuori Step 2. Le righe estratte da Vision arrivano come list[dict] minimale, fatture_documenti viene upsertato con scadenza_xml=NULL, scadenza_source='none'. ✅

---

**Edge Case 3: Fattura ricaricata 3 volte nella stessa sessione**

Scenario: Utente carica `Fattura_2026_05.xml`, poi lo ricerca accidentalmente e ricarica 2 volte.

Flusso salva_fattura_processata:
1. Prima upload: DELETE fatture WHERE file_origine='Fattura_2026_05.xml' (nulla trovata) → INSERT 10 righe → upsert_fattura_documento
2. Secondo upload (stesso file): DELETE fatture WHERE file_origine='Fattura_2026_05.xml' (trova 10 righe, elimina) → INSERT 10 righe → upsert_fattura_documento con ON CONFLICT (user_id, ristorante_id, file_origine) DO NOTHING

**Attualmente:** fatture_documenti è upsertato con chiave univoca (user_id, ristorante_id, file_origine), ma il pseudocodice NON menziona ON CONFLICT handling.

**Impatto:** Se upsert fallisce (error su colonna, constraint violation), fatture sono già salvate ma documento non aggiornato.

**Soluzione:** Specificare in Step 2 che upsert_fattura_documento usa:
```sql
INSERT INTO fatture_documenti (...) VALUES (...)
ON CONFLICT (user_id, ristorante_id, file_origine) 
DO UPDATE SET scadenza_xml = EXCLUDED.scadenza_xml, 
              giorni_termini_xml = EXCLUDED.giorni_termini_xml,
              updated_at = now();
```

Quindi idempotente per il file_origine. ✅

---

**Edge Case 4: Timeout di rete a metà upsert_fattura_documento**

Scenario: Dopo INSERT fatture OK, durante upsert_fattura_documento la connessione Supabase timeout.

**Impatto:** Righe salvate in fatture, ma fatture_documenti parziale o assente.

**Recovery:** Non automatico in Step 2. Migration 071 backfill ricrea fatture_documenti da fatture al startup successivo.

**Soluzione:** Step 2 NON deve aggiungere retry logic. Lasciare il fallimento loggato. Migration 071 è il recovery asincrono. Documento: "Step 2 non è transazionale; fallimenti upsert_fattura_documento vengono ricalcolati via migration 071 backfill al prossimo deployment."

---

### H.3 ORDINE OPERAZIONI: Quando chiamare upsert_fattura_documento?

Lettura del codice salva_fattura_processata linea 1430-1560:

1. **Linea ~1517:** DELETE fatture existing (idempotenza)
2. **Linea ~1522:** INSERT righe fatture bulk
3. **Linea ~1527:** Verifica integrità → confronta righe parsed vs righe DB
4. **Linea ~1530+:** Log upload_event

**DOMANDA:** Dove inserire `upsert_fattura_documento(dati_prodotti[0], user_id, ristorante_id, supabase)`?

**OPZIONE A (PRIMA INSERT fatture):**
- Pro: Atomico — se upsert_fattura_documento fallisce, niente INSERT (rollback transazione?)
- Con: salva_fattura_processata non usa transazioni Supabase (REST API), quindi non atomico comunque

**OPZIONE B (DOPO INSERT fatture, PRIMA verifica integrità):**
- Pro: Nessuna riga orfana se upsert fallisce (righe almeno in fatture)
- Con: Ritarda verifica integrità

**OPZIONE C (DOPO verifica integrità, nel blocco log upload_event):**
- Pro: Verifica già passata, garantisce integrità righe fatture
- Con: Se upsert fallisce, upload_event è già loggato come SUCCESS (potrebbe essere misleading)

**RACCOMANDAZIONE: OPZIONE C (DOPO verifica integrità)**

**Ordine corretto:**
```python
# Linea 1527: verifica integrità
verifica = verifica_integrita_fattura(...)

# Linea 1530: NUOVO — Upsert documento (DOPO verifica OK)
if verifica and verifica["integrita_ok"]:
    try:
        upsert_fattura_documento(
            dati_prodotti[0],
            user_id=user_id,
            ristorante_id=ristorante_id,
            supabase_client=supabase_client
        )
    except Exception as doc_err:
        logger.error(f"Errore upsert fatture_documenti per {nome_file}: {doc_err}")
        # NON fallire il salvataggio, recovery via migration 071

# Linea 1545+: Log upload_event come SUCCESS (righe OK, documento best-effort)
log_upload_event(status="SAVED_OK", ...)
```

**Motivo:** Verifica integrità garantisce che le righe fatture sono COERENTI con input, quindi safe upsert documento.

---

### H.4 SERVIZI MANCANTI: Cosa riusare da db_service.py?

Lettura db_service.py linea 1-300 mostra il pattern consolidato:

**Pattern 1: Letture cached con @st.cache_data**
```python
@st.cache_data(ttl=120, show_spinner=False)
def _carica_fatture_da_supabase(user_id: str, ristorante_id=None):
    """Cached query."""
    logger.info(f"📊 LOAD START: user_id={user_id}")
    ...
    return df
```

**Pattern 2: Metodo pubblico che invoca cached + force_refresh**
```python
def carica_e_prepara_dataframe(user_id, force_refresh=False, supabase_client=None):
    if force_refresh:
        _carica_fatture_da_supabase.clear()
    df = _carica_fatture_da_supabase(user_id, ristorante_id)
    ...
    return df
```

**Pattern 3: Try/except con logger.error per scritture**
```python
def set_price_alert_threshold(user_id, threshold_pct, supabase_client=None):
    try:
        supabase_client.table("users").update(...).eq(...).execute()
        get_price_alert_threshold.clear()  # Invalida cache
        return True
    except Exception as e:
        logger.error(f"Errore: {e}")
        return False
```

**PATTERN DA RIUSARE in nuovi servizi:**

```python
# documenti_service.py
from config.logger_setup import get_logger
logger = get_logger('documenti')

@st.cache_data(ttl=120, show_spinner=False)
def _get_documenti_cached(user_id: str, ristorante_id: str):
    """Cached lettura fatture_documenti."""
    ...
    return df

def get_documenti_list(user_id, ristorante_id, force_refresh=False, supabase_client=None):
    """Pubblica: carica documento con cache."""
    if force_refresh:
        _get_documenti_cached.clear()
    return _get_documenti_cached(user_id, ristorante_id)

def clear_documenti_cache():
    """Invalida cache per cache_version sync."""
    _get_documenti_cached.clear()

def upsert_fattura_documento(header_dict, user_id, ristorante_id, supabase_client=None):
    """Upsert un documento, ritorna bool."""
    if supabase_client is None:
        from services import get_supabase_client
        supabase_client = get_supabase_client()
    
    try:
        supabase_client.table('fatture_documenti').upsert([{
            'user_id': user_id,
            'ristorante_id': ristorante_id,
            'file_origine': header_dict.get('file_origine'),
            ...
        }]).execute()
        clear_documenti_cache()
        return True
    except Exception as e:
        logger.error(f"Errore upsert documento: {e}")
        return False
```

**SERVIZI DA CREARE:**

1. **documenti_service.py**: get_documenti_list(), upsert_fattura_documento(), set_pagato_bulk(), set_override_scadenza(), clear_documenti_cache()
2. **scadenze_service.py**: calcola_scadenza_effettiva(), recompute_scadenze_per_regola(), clear_scadenze_cache()
3. **fornitori_config_service.py**: upsert_regola_fornitore(), get_regole_fornitore(), delete_regola(), clear_fornitori_cache()

Tutti seguono il pattern db_service.py (cache + try/except + logger).

---

### H.5 MIGRATION 069: Trigger di propagazione deleted_at verificato

**Lettura migration 069, linea 174-195:**

```sql
-- TRIGGER: Propaga deleted_at da fatture su fatture_documenti
CREATE OR REPLACE FUNCTION public.fn_propagate_deleted_at_fatture()
RETURNS TRIGGER
...
END;
$$;

REVOKE ALL ON FUNCTION public.fn_propagate_deleted_at_fatture() FROM public, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.fn_propagate_deleted_at_fatture() TO service_role;

DROP TRIGGER IF EXISTS trg_propagate_deleted_at_fatture ON public.fatture;
CREATE TRIGGER trg_propagate_deleted_at_fatture
    AFTER UPDATE OF deleted_at ON public.fatture
    FOR EACH ROW EXECUTE FUNCTION public.fn_propagate_deleted_at_fatture();
```

**VERIFICA:**
- ✅ Function definita PRIMA di trigger (linea 174-192)
- ✅ Trigger creato DOPO function (linea 195)
- ✅ REVOKE/GRANT corretti (service_role only)
- ✅ Logica corretta: IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at → propaga a fatture_documenti
- ✅ Tripla (user_id, ristorante_id, file_origine) usata per match

**STATO:** ✅ CORRETTO E ORDINATO CORRETTAMENTE

---

### H.6 COSA MIGLIOREREI NELLA SPECIFICA

**Miglioramento 1: Chiarire il flusso cache_version durante sessione**

Step 3 introduce chiave `gfn_documenti_cache_version` inizializzata a 0. Step 2 dice di usare `clear_documenti_cache()` ma NON specifica il loop di invalidazione cross-process.

**Scenario produttivo:**
1. User apre app, sessione_state gfn_documenti_cache_version=0
2. User naviga a "5_Gestione Fatture", render → legge cache_version.version DA DB → es. version=5
3. Stampa: st.session_state['gfn_documenti_cache_version'] = 5
4. Step 5: set_pagato_bulk() → trigger bumpa version a 6
5. User torna a "5_Gestione Fatture" (stessa sessione), render → legge version=6 DA DB
6. Confronta: 6 > 5 → invalida cache, ricarica

**Specifica manca:** Pseudocodice del loop di "check version" nel render di Step 5. Deve dire:

```python
# Ogni render di Sezione Pagamenti in Step 5
current_version_db = supabase.table('cache_version')\
    .select('version')\
    .eq('key', 'fatture_documenti')\
    .single()\
    .execute().data['version']

if current_version_db > st.session_state.get('gfn_documenti_cache_version', 0):
    logger.info(f"📊 Cache invalidata: {st.session_state['gfn_documenti_cache_version']} → {current_version_db}")
    clear_documenti_cache()
    st.session_state['gfn_documenti_cache_version'] = current_version_db

documenti_df = get_documenti_list(user_id, ristorante_id)  # Legge cache invalidata
```

---

**Miglioramento 2: Documentare il caso "documento orfano"**

Se upsert_fattura_documento fallisce DOPO INSERT fatture:
- Fatture sono in DB, integrità verificata
- fatture_documenti è assente o parziale
- User non sa (upload_event loggato come SUCCESS)
- UI mostra righe in dashboard, ma non in "Pagamenti" (perché fatture_documenti assente)

**Impatto UX:** Utente vede righe fatture conteggiati, ma non trova documenti in scadenziario → confusione.

**Recovery:** Migration 071 backfill ricalcola doc orfani al deployment successivo. Nel frattempo:

**Soluzione:**  Aggiunger log event di warning se upsert fallisce:
```python
try:
    upsert_fattura_documento(...)
except Exception as doc_err:
    logger.warning(f"⚠️ DOCUMENTO ORFANO: {nome_file} — righe salvate ma documento no. Recovery via migration 071")
    # Non propagare errore, upload_event rimane SUCCESS
```

Documento Step 2 deve dire: "Se upsert_fattura_documento fallisce, NON bloccare. Righe fatture restano integre. I documenti orfani saranno ricalcolati da migration 071 backfill al deployment successivo."

---

**Miglioramento 3: Semplificare pseudocodice Step 2 con gerarchia scadenza esplicita**

Attualmente il pseudocodice sceglie max() indipendentemente. Meglio fare:

```
PSEUDOCODICE SEMPLIFICATO:

PARSING DatiPagamento (PRIMA loop righe):
  _scadenza_xml_finale = None
  _giorni_termini_finale = None
  
  FOR DettaglioPagamento IN list:
      DataScadenza = get('DataScadenzaPagamento')
      GiorniTermini = get('GiorniTerminiPagamento')
      
      IF DataScadenza:
          _scadenza_xml_finale = max(_scadenza_xml_finale, DataScadenza)  # usa data assoluta
      ELIF GiorniTermini:
          _giorni_termini_finale = max(_giorni_termini_finale, GiorniTermini)
      # Se entrambi assenti, niente

  # Nel loop righe: usa _scadenza_xml_finale e _giorni_termini_finale
  scadenza_xml = _scadenza_xml_finale
  giorni_termini_xml = _giorni_termini_finale
  # Nota: Se scadenza_xml=NULL e giorni_xml esiste, calcolo data = data_documento + giorni_xml avverrà in calcola_scadenza_effettiva()
```

Più chiaro: data assoluta ha priorità, se manca usa giorni termini.

---

## Conclusione Sezione H

**RISULTATO REVISIONE:**
- ✅ Ordine operazioni CORRETTO: upsert_fattura_documento DOPO verifica integrità
- ✅ Migration 069 trigger ORDINATO CORRETTAMENTE
- ✅ Pattern servizi REPLICABILE da db_service.py
- 🟡 **Lacune 3 da colmare**: metodo_pagamento orfano, gerarchia scadenza, piva_fornitore estratto
- 🟡 **3 Edge case coperti:** P7M (out-of-scope), PDF Vision AI (OK), ricarica (OK)
- 🟡 **2 Miglioramenti suggeriti:** Cache version loop esplicito, documentazione documento orfano

**AZIONE PRIMA DI STEP 2:** Aggiornare pseudocodice con:
1. Escludere metodo_pagamento da salvataggio (o aggiungere colonna fatture_documenti)
2. Gerarchia scadenza: data assoluta > giorni termini > none
3. Estrarre e aggiungere piva_fornitore al flusso

Poi Step 2 implementation è safe.

---

### F.1 Test fixtures XML
**Decisione:** Creare 5 fixture in `tests/fixtures/xml/`:
- `td01_singolo_con_data_scadenza.xml` — DatiPagamento con DataScadenzaPagamento
- `td01_singolo_con_giorni_termini.xml` — DatiPagamento con GiorniTerminiPagamento
- `td01_multipli_dettaglio_pagamento.xml` — 3 scadenze diverse, usare la piu lontana
- `td04_nota_credito_senza_dati_pagamento.xml` — TD04 con scadenza_xml = NULL
- `td01_senza_dati_pagamento.xml` — nessun DatiPagamento, scadenza_xml = NULL

Struttura documentata, creazione rimandata a Step 2 (test per parse DatiPagamento).

### F.2 Test strategy
**Decisione:** Replicare pattern test esistenti.
- `calcola_scadenza_effettiva()` e pure Python → test in pytest senza DB, con fixture dict.
- `upsert_fattura_documento()` e co. → test con Supabase locale localhost:54321 (gia in pytest.ini).
- Nessun mock, nessun mock Supabase — tutto reale su istanza test locale.

### F.3 Ricalcolo scadenza quando regola fornitore cambia
**Decisione: OPZIONE A — Ricalcolo immediato.**

Implementare `recompute_scadenze_per_regola(user_id, ristorante_id, regola_id)` che:
- Ricalcola SOLO fatture con `scadenza_source='fornitore'` (non override, non xml).
- Fatture con `scadenza_source='override'` MAI toccate (priorità massima utente).
- Fatture con `scadenza_source='xml'` NON toccate (regola non sovrascrive retroattivamente).
- Fatture con `scadenza_source='none'` rivalutate e aggiornate se ora esiste regola applicabile.

Effetto: disattivare/modificare una regola riflette istantaneamente su scadenziario.

### F.4 Visibilità pagina nella sidebar
**Decisione:** Pagina visibile per tutti gli utenti dalla sidebar (no feature flag).

In `pages/admin.py`, esiste un tab di visibilita per le pagine secondarie (come gia per altre pagine).
**Azione:** Documenta quale tab in admin.py gestisce page-visibility e come va esteso per la nuova pagina.
(TODO Step 8: aggiungere configurazione in admin.py).

### F.5 Cache multi-utente Streamlit Cloud
**Decisione:** Nessuna modifica necessaria.

Il bump `cache_version` è corretto cross-utente perché `@st.cache_data` è gia keyed su `(user_id, ristorante_id)`.
Ogni utente rilegge propria cache con nuovo version token → zero rischio data leak.

### F.6 Worker durante migration 069
**Decisione:** Nessun downtime necessario se 069 rispetta l'ordine.

Ordine obbligatorio in 069:
1. CREATE OR REPLACE FUNCTION fn_propagate_deleted_at_fatture()
2. CREATE TRIGGER trg_propagate_deleted_at_fatture ... EXECUTE FUNCTION fn_propagate_deleted_at_fatture()
3. CREATE OR REPLACE FUNCTION fn_bump_cache_version_fatture_documenti()
4. CREATE TRIGGER trg_bump_cache_fat_doc ... EXECUTE FUNCTION fn_bump_cache_version_fatture_documenti()

(Verificare 069 rispetta questo ordine — ✅ confermato nel file).

Worker running durante 069 non causa problemi: funzione creata prima di trigger.

### F.7 Backfill performance (migration 071)
**Decisione:** Strategia batch per reggere scale future (500k+ record).

Obbligatorio in 071:
1. CREATE INDEX CONCURRENTLY idx_fatture_backfill ON fatture(user_id, ristorante_id, file_origine) WHERE deleted_at IS NULL;
2. Backfill in batch da 1000 documenti (file_origine) alla volta usando DO $$ loop PL/pgSQL con COMMIT intermedi.
3. Query aggregata: DISTINCT ON (file_origine) ordinato per created_at ASC (prima riga = rappresentante header).
4. ON CONFLICT (user_id, ristorante_id, file_origine) DO NOTHING (idempotenza).
5. VACUUM ANALYZE fatture_documenti; alla fine.
6. DROP INDEX idx_fatture_backfill;
7. Query verifica finale: COUNT(*) deve = COUNT(DISTINCT file_origine) da fatture WHERE deleted_at IS NULL.

### F.8 Ordine applicazione migrations in produzione
**Decisione:** Manuale, sequenziale, con verifica fra step.

Passo 1: Applica 069 → SELECT COUNT(*) FROM fatture_documenti; (tabella esiste, vuota)
Passo 2: Applica 070 → SELECT COUNT(*) FROM fornitori_pagamenti_config; (tabella esiste, vuota)
Passo 3: Applica 071 → SELECT COUNT(*) FROM fatture_documenti; (deve = COUNT(DISTINCT file_origine) con deleted_at IS NULL)

MAI batch automatico. Nessuna atomicità cross-file.

### F.9 Service layer: ownership calcola_scadenza_effettiva
**Decisione:** Centralizzazione in `services/scadenze_service.py`.

- `scadenze_service.py` contiene `calcola_scadenza_effettiva()` + `recompute_scadenze_per_regola()`.
- `documenti_service.py` importa da scadenze_service (dipendenza unidirezionale).
- Zero circular import.

### F.10 Notifiche dal worker
**Decisione:** Solo UI-side, nessuna persistenza worker.

- `build_scadenze_alert_notifications()` calcolata solo al render della nuova pagina.
- Worker NON invia email, NON genera notifiche persistenti.
- Scadenziario rimane sempre aggiornato (calcolato da scadenza_effettiva in tempo reale).

---
