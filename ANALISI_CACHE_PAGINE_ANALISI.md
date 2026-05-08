# 📊 ANALISI COMPLETA DEI CACHE NELLE PAGINE DI ANALISI
**Data: 8 maggio 2026**

---

## 🔍 RIEPILOGO ESECUTIVO

Ho analizzato tutte le pagine di analisi (`1_calcolo_margine.py`, `2_foodcost.py`, `3_controllo_prezzi.py`, `4_analisi_personalizzata.py`) e il codebase correlato. Ho identificato **10 cache decorator** che caricano dati di fatture, di cui:
- **7 cache** caricate dal DB delle fatture
- **3 cache** caricate da tabelle correlate (tag, ingredienti, costanti)
- **5 cache** INVALIDATE correttamente quando date cambiano
- **5 cache** CON PROBLEMI POTENZIALI di invalidazione

---

## 📋 CACHE TROVATI: DETTAGLIO COMPLETO

### 1️⃣ **_carica_fatture_da_supabase()**
- **📍 Pagina/File:** [services/db_service.py](services/db_service.py#L110)
- **🏷️ Decorator:** `@st.cache_data(ttl=120, show_spinner=False)`
- **📦 Cosa carica:** Tutte le fatture dell'utente con colonne essenziali (data_documento, fornitore, descrizione, importi, categoria, etc.)
- **🔗 Usato da:** `carica_e_prepara_dataframe()` → utilizzato da TUTTE le pagine di analisi
- **❌ Invalidazione quando data_documento cambia?** **SÌ, MA SOLO SE:**
  - Si chiama esplicitamente `clear_fatture_cache()` dopo `aggiorna_data_competenza_fattura()`
  - La cache scade naturalmente dopo 120s (TTL)
- **⚠️ Problemi identificati:**
  - Se l'utente modifica una data di fattura e **non effettua st.rerun()**, la cache rimane stale fino a 120s
  - Non c'è un meccanismo automatico per invalidare quando `data_documento` o `data_competenza` cambiano in real-time
  
**🔧 Come è invalidata attualmente:**
```python
def clear_fatture_cache() -> None:
    """Invalida solo la cache fatture (non tutte le cache Streamlit)."""
    _carica_fatture_da_supabase.clear()           # ✅ Questa cache
    get_fatture_stats.clear()                      # ✅ Stats correlata
    calcola_costi_automatici_per_anno.clear()      # ✅ Margini
    carica_costi_per_categoria.clear()             # ✅ Analisi avanzate
```

**📍 Dove viene chiamata:**
- [app.py](app.py#L2842) - Dopo `aggiorna_data_competenza_fattura()`
- [app.py](app.py#L359) - All'upload di file
- [app.py](app.py#L426) - Eliminazione fatture
- [utils/app_controllers.py](utils/app_controllers.py#L1149) - Svuotamento massivo

---

### 2️⃣ **get_price_alert_threshold()**
- **📍 Pagina/File:** [services/db_service.py](services/db_service.py#L41)
- **🏷️ Decorator:** `@st.cache_data(ttl=120, show_spinner=False)`
- **📦 Cosa carica:** Soglia alert prezzo dell'utente da `users.price_alert_threshold`
- **🔗 Usato da:** [pages/3_controllo_prezzi.py](pages/3_controllo_prezzi.py)
- **❌ Invalidazione quando data cambia?** **NO** (non è legato a date di fatture)
- **✅ Status:** Corretto - invalidata quando salvata con `set_price_alert_threshold()`

---

### 3️⃣ **get_fatture_stats()**
- **📍 Pagina/File:** [services/db_service.py](services/db_service.py#L1171)
- **🏷️ Decorator:** `@st.cache_data(ttl=60, show_spinner=False)`
- **📦 Cosa carica:** 
  - `num_uniche`: numero fatture uniche (file_origine distinti)
  - `num_righe`: numero totale righe/prodotti
- **🔗 Usato da:** Dashboard principale [app.py](app.py), stats box
- **❌ Invalidazione quando data cambia?** **SÌ, tramite clear_fatture_cache()** ✅
- **⚠️ Nota:** TTL corto (60s) mitiga il rischio, ma dipende da `clear_fatture_cache()` esplicita

---

### 4️⃣ **calcola_costi_automatici_per_anno()**
- **📍 Pagina/File:** [services/margine_service.py](services/margine_service.py#L30)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner="Calcolo costi da fatture...")`
- **📦 Cosa carica:** Costi F&B e Spese Generali aggregati per mese da fatture per un anno
- **🔗 Usato da:** [pages/1_calcolo_margine.py](pages/1_calcolo_margine.py) - Tab "CALCOLO"
- **❌ Invalidazione quando data_documento cambia?** **SÌ, tramite clear_fatture_cache()** ✅
- **⏰ Problemi potenziali:**
  - TTL 300s (5 minuti) è lungo: se utente modifica data, potrebbe veder vecchi dati per ~5min
  - Dipende da che `st.rerun()` sia chiamato dopo la modifica

**Parametri della cache:**
```python
calcola_costi_automatici_per_anno(user_id: str, ristorante_id: str, anno: int)
# Hashable: user_id, ristorante_id, anno
# Se utente cambia anno nel UI, crea nuovo entry cache (nessun problema)
```

---

### 5️⃣ **carica_costi_per_categoria()**
- **📍 Pagina/File:** [services/margine_service.py](services/margine_service.py#L110)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner="Caricamento dati per analisi...")`
- **📦 Cosa carica:** Fatture F&B raggruppate per categoria e mese per un periodo data_from → data_to
- **🔗 Usato da:** [pages/1_calcolo_margine.py](pages/1_calcolo_margine.py) - Tab "ANALISI AVANZATE"
- **❌ Invalidazione quando data_documento cambia?** **SÌ, tramite clear_fatture_cache()** ✅
- **⏰ Problemi potenziali:**
  - I parametri `date_from` e `date_to` sono **hashable** e determinano cache hit/miss
  - Se utente sposta il range di date nel UI, crea NEW cache entry (buono)
  - Se utente modifica una data di fattura **dentro** il range, la cache non viene invalidata finché non scade (300s)

**Scenario problematico:**
```
1. Utente vede analisi: 2026-04-01 → 2026-04-30 (cache creata con TTL 300s)
2. Utente modifica fattura da 2026-04-15 a 2026-04-20
3. Dashboard mostra vecchi dati fino a cache scadenza (max 5 min)
4. clear_fatture_cache() invalida, ma st.rerun() è necessario
```

---

### 6️⃣ **get_articoli_da_fatture()**
- **📍 Pagina/File:** [pages/2_foodcost.py](pages/2_foodcost.py#L238)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner="Caricamento articoli dalle fatture...")`
- **📦 Cosa carica:** Articoli unici da fatture con ultimo prezzo, estratti per descrizione
- **🔗 Usato da:** [pages/2_foodcost.py](pages/2_foodcost.py) - Ricette e Foodcost workspace
- **🚨 Invalidazione quando data_documento cambia?** **NO - PROBLEMA CRÍTICO**
- **⚠️ Non è invalidata da `clear_fatture_cache()`** ❌

**Invalidazione manuale:**
```python
def invalidate_workspace_cache():
    """Invalida SOLO le cache specifiche del workspace, senza toccare le altre pagine."""
    get_articoli_da_fatture.clear()
    get_ricette_come_ingredienti.clear()
    _get_ingredienti_workspace_cached.clear()
```

**Dove viene chiamata:**
- [pages/2_foodcost.py](pages/2_foodcost.py#L40) - Interna alla pagina (non dalla dashboard)
- Accesso globale: nessun meccanismo in app.py

**🔧 Problema: Se utente modifica una fattura nella dashboard e poi va a Foodcost, gli articoli rimangono stale per 5 minuti!**

---

### 7️⃣ **get_ricette_come_ingredienti()**
- **📍 Pagina/File:** [pages/2_foodcost.py](pages/2_foodcost.py#L328)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner=False)`
- **📦 Cosa carica:** Ricette salvate (SEMILAVORATI) disponibili come ingredienti
- **🔗 Usato da:** [pages/2_foodcost.py](pages/2_foodcost.py) - Dropdown ingredienti
- **❌ Invalidazione quando data_documento cambia?** **NO - NON NECESSARIA** ✅
  - Ricette non contengono date di fatture, sono dati statici dell'utente
  - Invalidata solo se utente crea/modifica ricetta (tramite `invalidate_workspace_cache()`)

---

### 8️⃣ **_get_ingredienti_workspace_cached()**
- **📍 Pagina/File:** [pages/2_foodcost.py](pages/2_foodcost.py#L371)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner=False)`
- **📦 Cosa carica:** Ingredienti workspace (manuali/test) per un ristorante
- **🔗 Usato da:** [pages/2_foodcost.py](pages/2_foodcost.py) - Foodcost workspace
- **❌ Invalidazione quando data_documento cambia?** **NO - NON NECESSARIA** ✅
  - Dati statici dell'utente, non correlati alle fatture

---

### 9️⃣ **get_custom_tags()**
- **📍 Pagina/File:** [services/db_service.py](services/db_service.py#L1640)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner=False)`
- **📦 Cosa carica:** Tag personalizzati dell'utente per il ristorante corrente
- **🔗 Usato da:** [pages/4_analisi_personalizzata.py](pages/4_analisi_personalizzata.py)
- **❌ Invalidazione quando data_documento cambia?** **NO - NON NECESSARIA** ✅
  - Tag sono configurazioni, non dipendono da fatture
  - Invalidati quando tag creato/modificato tramite `clear_tags_cache()`

**Invalidazione dedicata:**
```python
def clear_tags_cache():
    get_custom_tags.clear()
    get_custom_tag_prodotti.clear()
```

---

### 🔟 **get_descrizioni_distinte()**
- **📍 Pagina/File:** [services/db_service.py](services/db_service.py#L1680)
- **🏷️ Decorator:** `@st.cache_data(ttl=300, show_spinner=False)`
- **📦 Cosa carica:** Descrizioni distinte fatture per l'utente (aggregazione per `descrizione_key`)
- **🔗 Usato da:** [pages/4_analisi_personalizzata.py](pages/4_analisi_personalizzata.py) - Ricerca live tag
- **🚨 Invalidazione quando data_documento cambia?** **NO - PROBLEMA CRÍTICO**
- **⚠️ Non è invalidata da `clear_fatture_cache()` né da `clear_tags_cache()`** ❌

**Scenario problematico:**
```
1. Utente carica 100 fatture → cache get_descrizioni_distinte creata
2. Utente aggiunge 10 nuove fatture via upload
3. Pagina 4 (Analisi) non vede le nuove descrizioni per ~5 min
4. clear_fatture_cache() invalida carica_fatture... ma NON get_descrizioni_distinte!
```

---

### 1️⃣1️⃣ **_get_openai_client()**
- **📍 Pagina/File:** [services/ai_service.py](services/ai_service.py#L1876)
- **🏷️ Decorator:** `@st.cache_resource` (singleton per sessione)
- **📦 Cosa carica:** Client OpenAI inizializzato e cached
- **🔗 Usato da:** Categorizzazione AI in tutta l'app
- **❌ Invalidazione quando data_documento cambia?** **NO - NON NECESSARIA** ✅
  - È un client di sistema, non correlato a dati di fatture

---

## 🚨 PROBLEMI CRITICI IDENTIFICATI

### ⚠️ PROBLEMA #1: Cache di articoli non invalidata tra pagine
**Severità:** 🔴 **ALTA**

- **Cache interessate:**
  - `get_articoli_da_fatture()` (TTL 300s)
  - `get_descrizioni_distinte()` (TTL 300s)
  
- **Scenario d'errore:**
  ```
  1. Utente in Dashboard (app.py) modifica fattura: data 2026-04-01 → 2026-04-20
  2. clear_fatture_cache() invalida _carica_fatture_da_supabase ✅
  3. Utente clicca su pagina "2_foodcost" (Foodcost workspace)
  4. get_articoli_da_fatture() viene richiamato → cache HIT (TTL non scaduto)
  5. ❌ Mostra articoli STALE per fino a 5 minuti
  ```

- **Root cause:** 
  - `clear_fatture_cache()` invalida SOLO `_carica_fatture_da_supabase` e `get_fatture_stats`
  - Non invalida funzioni cached in **altre pagine** (`2_foodcost.py`, `4_analisi_personalizzata.py`)
  - Non c'è invalidazione cross-pagina coordinata

---

### ⚠️ PROBLEMA #2: Cache di margini rimane stale se utente non fa st.rerun()
**Severità:** 🟡 **MEDIA**

- **Cache interessate:**
  - `calcola_costi_automatici_per_anno()` (TTL 300s)
  - `carica_costi_per_categoria()` (TTL 300s)

- **Scenario d'errore:**
  ```
  1. Utente in pagina 1_calcolo_margine visualizza margini 2026
  2. Torna a Dashboard, modifica fattura: categoria FOOD → SPESE GENERALI
  3. clear_fatture_cache() invalida... ma non fa st.rerun() automaticamente
  4. Utente torna a pagina 1_calcolo_margine
  5. ❌ Vecchia cache hit se ancora entro 300s
  6. Margini mostrati sono ERRATI finché cache non scade
  ```

---

### ⚠️ PROBLEMA #3: No invalidazione cross-pagina centralizzata
**Severità:** 🟡 **MEDIA**

Attualmente:
- `clear_fatture_cache()` in [db_service.py](services/db_service.py#L1248) invalida subset limitato
- Nessun meccanismo che invalidi TUTTE le cache che dipendono da fatture atomicamente
- Ogni pagina ha propria logica di invalidazione locale (`invalidate_workspace_cache()`)

---

## ✅ CACHE CORRETTAMENTE INVALIDATE

| Cache | Invalidata quando? | Metodo |
|-------|-------------------|--------|
| `_carica_fatture_da_supabase()` | Data/Categoria/Fornitore cambia | `clear_fatture_cache()` + `st.rerun()` |
| `get_fatture_stats()` | File aggiunto/rimosso | `clear_fatture_cache()` + `st.rerun()` |
| `calcola_costi_automatici_per_anno()` | Fattura modificata | `clear_fatture_cache()` + `st.rerun()` |
| `carica_costi_per_categoria()` | Periodo cambia o fattura modificata | `clear_fatture_cache()` + `st.rerun()` |
| `get_price_alert_threshold()` | Utente salva soglia | `set_price_alert_threshold().clear()` |

---

## 🔴 CACHE CON INVALIDAZIONE INCOMPLETA

| Cache | Problema | TTL | Impatto |
|-------|----------|-----|--------|
| `get_articoli_da_fatture()` | Niente in `clear_fatture_cache()`; solo locale in foodcost | 300s | Articoli stale tra pagine |
| `get_descrizioni_distinte()` | Niente in `clear_fatture_cache()`; niente in `clear_tags_cache()` | 300s | Descrizioni stale in analisi personalizzata |
| `get_custom_tags()` | Solo invalidato via `clear_tags_cache()`, non automatico su upload | 300s | Tags possono veder vecchi dati |

---

## 🛠️ SUGGERIMENTI DI IMPLEMENTAZIONE

### Soluzione #1: Estendi clear_fatture_cache() per invalidare TUTTE le cache correlate

**File da modificare:** [services/db_service.py](services/db_service.py#L1248)

```python
def clear_fatture_cache() -> None:
    """Invalida TUTTE le cache che dipendono da fatture."""
    logger.debug(f"[CACHE] clear_fatture_cache() chiamata — ts={time.time():.3f}")
    
    # 📌 TIER 1: Cache in db_service
    _carica_fatture_da_supabase.clear()
    get_fatture_stats.clear()
    get_descrizioni_distinte.clear()  # 🆕 AGGIUNTO
    
    # 📌 TIER 2: Cache in margine_service
    try:
        from services.margine_service import calcola_costi_automatici_per_anno, carica_costi_per_categoria
        calcola_costi_automatici_per_anno.clear()
        carica_costi_per_categoria.clear()
    except Exception:
        pass
    
    # 📌 TIER 3: Cache in pages/2_foodcost.py  
    try:
        from pages.pages_2_foodcost import (  # o importare dinamicamente
            get_articoli_da_fatture, 
            invalidate_workspace_cache
        )
        invalidate_workspace_cache()  # invalida tutte 3 funzioni in foodcost
    except Exception:
        logger.debug("Impossibile invalidare cache foodcost da db_service (normal in analytics pages)")
```

**Problema:** Import circolare potenziale (db_service → pages → db_service)

**Soluzione alternativa (migliore):** Usare pattern callback
```python
# In pages/2_foodcost.py
from services.db_service import register_cache_invalidator

register_cache_invalidator('invalidate_workspace_cache', invalidate_workspace_cache)

# In services/db_service.py
_invalidators = {}
def register_cache_invalidator(name: str, func):
    _invalidators[name] = func

def clear_fatture_cache() -> None:
    # ... codice esistente ...
    
    # Chiama tutti i callback registrati
    for name, func in _invalidators.items():
        try:
            func()
        except Exception as e:
            logger.debug(f"Invalidatore '{name}' fallito: {e}")
```

---

### Soluzione #2: Aggiungi st.rerun() automatico dopo modifiche data

**File da modificare:** [app.py](app.py#L2842)

```python
if st.button("💾 Salva", type="primary", use_container_width=True):
    with st.spinner("Aggiornamento data in corso..."):
        esito = aggiorna_data_competenza_fattura(
            file_origine=fattura_selezionata['File'],
            user_id=user_id,
            data_competenza=data_competenza.isoformat(),
            ristoranteid=st.session_state.get('ristorante_id'),
        )
        if esito.get("success"):
            clear_fatture_cache()
            invalida_cache_memoria()
            st.success(f"✅ Competenza impostata su {_mesi_it[mese_selezionato]} {_anno_corrente}")
            st.session_state.pop('fattura_data_editor_file', None)
            time.sleep(0.1)  # Ridotto da 0.2
            st.rerun()  # ✅ Già presente - BUONO
        else:
            st.error(f"❌ Errore: {esito.get('error', 'errore sconosciuto')}")
```

**Status:** ✅ Già implementato correttamente

---

### Soluzione #3: Aggiungi cache versioning con DB

**Status:** ✅ Già implementato in v5.4
- Tabella `cache_version` monitora modifiche su `prodotti_master`, `classificazioni_manuali`, etc.
- **Nota:** Non monitora ancora modifiche a `fatture.data_documento` o `fatture.categoria`

**Possibile estensione:**
```sql
-- Aggiungere trigger su 'fatture' per invalidazione cross-process
CREATE OR REPLACE FUNCTION public.fn_bump_fatture_cache()
RETURNS TRIGGER AS $$
BEGIN
    -- Quando una fattura cambia, incrementa versione
    UPDATE public.cache_version 
    SET version = version + 1, updated_at = now()
    WHERE key = 'fatture_dataset';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_bump_fatture_on_change
AFTER INSERT OR UPDATE OR DELETE ON public.fatture
FOR EACH STATEMENT EXECUTE FUNCTION fn_bump_fatture_cache();
```

Poi in Python:
```python
def _carica_fatture_da_supabase(user_id: str, ristorante_id=None):
    # Controlla versione cache prima di usare TTL
    current_db_version = get_remote_cache_version('fatture_dataset')
    if 'fatture_version_seen' in st.session_state and \
       st.session_state.fatture_version_seen == current_db_version:
        # Cache locale ancora valida, riusa
        pass
    else:
        # Versione cambiata, forza ricaricamento
        ...
```

---

## 📊 MATRICE DI IMPATTO

```
┌─────────────────────────────────────────────────────────────┐
│ CACHE                              │ Pagina       │ Rischio   │
├────────────────────────────────────┼──────────────┼───────────┤
│ _carica_fatture_da_supabase        │ app.py       │ BASSO ✅  │
│ get_articoli_da_fatture            │ 2_foodcost   │ ALTO 🔴   │
│ get_descrizioni_distinte           │ 4_analisi    │ ALTO 🔴   │
│ calcola_costi_automatici_per_anno  │ 1_margine    │ MEDIO 🟡  │
│ carica_costi_per_categoria         │ 1_margine    │ MEDIO 🟡  │
│ get_custom_tags                    │ 4_analisi    │ BASSO ✅  │
│ get_ricette_come_ingredienti       │ 2_foodcost   │ BASSO ✅  │
│ _get_ingredienti_workspace_cached  │ 2_foodcost   │ BASSO ✅  │
│ get_price_alert_threshold          │ 3_prezzi     │ BASSO ✅  │
│ get_fatture_stats                  │ app.py       │ BASSO ✅  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 AZIONI CONSIGLIATE (PRIORITÀ)

### 🔴 **P0 - CRITICO** (Implementare immediatamente)
1. Estendi `clear_fatture_cache()` per invalidare `get_descrizioni_distinte()` 
2. Aggiungi registro callback per permettere a `pages/2_foodcost.py` di registrare invalidatori

### 🟡 **P1 - IMPORTANTE** (Implementare entro 1 settimana)
3. Aggiungi trigger DB per bump versione quando `fattura.data_documento` cambia
4. Aggiungi test di invalidazione cross-pagina con scenario "modifica fattura → visita altra pagina"

### 🟢 **P2 - NICE-TO-HAVE** (Backlog)
5. Riduci TTL di cache analisi da 300s a 120s per exposure minore
6. Aggiungi dashboard di monitoring cache hit/miss rate
7. Considera incrementare cache to session state con clear esplicito su page change

---

## 📎 RIFERIMENTI NEL CODEBASE

**File principali:**
- [services/db_service.py](services/db_service.py) - Definizione cache, `clear_fatture_cache()`
- [services/margine_service.py](services/margine_service.py) - Cache costi margini
- [pages/2_foodcost.py](pages/2_foodcost.py) - Cache workspace non sincronizzate
- [app.py](app.py) - Punti di invalidazione durante caricamento/modifica
- [migrations/068_create_cache_version.sql](migrations/068_create_cache_version.sql) - Cache versioning

**Funzioni critiche di invalidazione:**
- `clear_fatture_cache()` @ [db_service.py:1248](services/db_service.py#L1248)
- `invalidate_workspace_cache()` @ [2_foodcost.py:40](pages/2_foodcost.py#L40)
- `clear_tags_cache()` @ [db_service.py:1820](services/db_service.py#L1820)

---

**Documento generato da: Copilot**  
**Ultimo aggiornamento: 8 maggio 2026**
