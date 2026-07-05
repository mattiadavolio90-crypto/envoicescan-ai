# ONEFLUX — Pipeline AI: Classificazione, Parsing e Briefing

Versione: 6.0 | Aggiornamento: 5 Giugno 2026

Questo documento descrive nel dettaglio la logica di classificazione AI delle fatture,
il parsing dei diversi formati file, il sistema di memoria e il briefing AI giornaliero.

---

## 1. Architettura della Classificazione

### 5 livelli di priorità

```
┌─────────────────────────────────────────────────────────────┐
│                PRIORITÀ CLASSIFICAZIONE                      │
│                                                             │
│  1. MEMORIA ADMIN (classificazioni_manuali)                 │
│     Priorità: MASSIMA                                       │
│     Scope: Globale per tutti i clienti                      │
│     Trigger: Admin modifica da pannello Qualità AI          │
│                                                             │
│  2. MEMORIA LOCALE (prodotti_utente)                        │
│     Priorità: ALTA                                          │
│     Scope: Solo per il cliente specifico                    │
│     Trigger: Cliente modifica categoria manualmente         │
│                                                             │
│  3. MEMORIA GLOBALE (prodotti_master)                       │
│     Priorità: MEDIA                                         │
│     Scope: Tutti i clienti                                  │
│     Trigger: AI e dizionario salvano risultati              │
│                                                             │
│  4. DIZIONARIO KEYWORD (config/constants.py)                │
│     600+ regole deterministiche: "SALMONE" → PESCE         │
│     Priorità alimenti > contenitori                         │
│                                                             │
│  5. AI GPT-4.1-mini (ultima risorsa)                        │
│     Batch da 50 articoli, prompt con 31 categorie           │
│     Retry con exponential backoff (tenacity)                │
└─────────────────────────────────────────────────────────────┘
```

### Flusso completo durante upload

```
File caricato
    │
    ▼
invoice_service.py — parsing (XML/P7M/PDF/Vision)
    │
    ├── Pre-step: check cache in-memory thread-safe
    │   └── Admin cache > Locale cache > Globale cache
    │
    ├── Step 1: Dizionario keyword (600+ regole)
    │   └── Match → salva risultato
    │
    ├── Step 2: AI batch via worker_client
    │   ├── Prova FastAPI Worker (se WORKER_BASE_URL configurato)
    │   └── Fallback automatico su classifica_con_ai() locale
    │
    ├── Salvataggio batch: upsert memoria globale (keyword + AI)
    │
    ├── UPDATE DB: batch aggiornamento categorie su `fatture`
    │
    └── Fallback: secondo tentativo dizionario per articoli rimasti
```

### Routing confidenza (sull'ingest)

Il routing avviene in `upload_handler.py` e `worker/queue_processor.py` via `classifica_via_worker_con_confidenza()`:

| Confidenza | `needs_review` | Comportamento |
|-----------|---------------|---------------|
| `altissima` | `False` | Bypassa coda admin. Es: hit memoria admin, sconti/omaggi verificati, diciture sicure €0 |
| `alta` | `False` | Bypassa coda admin. Es: hit memoria locale/globale forte, keyword forte |
| `media` | `True` | Pre-classificato MA in coda admin per review. Es: dizionario fallback, GPT con bassa certezza |
| `bassa` | `True` | Fallback canonico + coda admin |

**Guardrail BUG1:** nessuna dicitura con prezzo > 0 entra in memoria globale.

---

## 2. Cache In-Memory Thread-Safe

```python
_memoria_cache = {
    'prodotti_utente':          {},  # {user_id: {descrizione: categoria}}
    'prodotti_master':          {},  # {descrizione: categoria}
    'classificazioni_manuali':  {},  # {descrizione: {categoria, is_dicitura}}
    'version': 0,                    # Incrementato ad ogni invalidazione
    'loaded': False
}
```

- **Caricamento lazy**: 1 volta per sessione, 3 query DB totali
- **Thread-safe**: `threading.Lock()` — no race condition su accessi concorrenti
- **Invalidazione**: esplicita dopo ogni modifica (`invalida_cache_memoria()`)
- **Cross-process**: `cache_version` su DB + trigger SQL → ogni worker controlla la versione e invalida la propria cache se incrementata
- **Eliminazione N+1**: una sola lettura bulk all'avvio, poi tutto in-memory

---

## 3. Le 31 Categorie

### Food & Beverage (25)

| # | Categoria | Esempi |
|---|-----------|--------|
| 1 | ACQUA | Acqua naturale, frizzante |
| 2 | AMARI/LIQUORI | Limoncello, Baileys, Sambuca |
| 3 | BEVANDE | Coca Cola, Aranciata, Succhi |
| 4 | BIRRE | Lager, Weiss, Stout |
| 5 | CAFFÈ E THE | Espresso, Capsule, Tisane, Camomilla |
| 6 | CARNE | Pollo, Manzo, Vitello, Salsiccia |
| 7 | DISTILLATI | Vodka, Gin, Whisky, Grappa |
| 8 | FRUTTA | Mele, Arance, Fragole, Avocado |
| 9 | GELATI | Gelato, Sorbetto, Semifreddo |
| 10 | LATTICINI | Parmigiano, Mozzarella, Burrata, Tofu |
| 11 | OLIO E CONDIMENTI | Olio EVO, Aceto Balsamico |
| 12 | PASTICCERIA | Torte, Cannoli, Cheesecake, Tiramisù |
| 13 | PESCE | Salmone, Gamberi, Calamari, Polpo |
| 14 | PRODOTTI DA FORNO | Pane, Focaccia, Baguette, Pizza |
| 15 | SALSE E CREME | Pesto, Ragù, Besciamella, Ketchup |
| 16 | SALUMI | Prosciutto, Mortadella, Speck, Pancetta |
| 17 | SCATOLAME E CONSERVE | Pelati, Tonno, Fagioli, Olive |
| 18 | SECCO | Pasta, Riso, Farina, Zucchero |
| 19 | SHOP | Sigarette, Caramelle, Snack, Gomme |
| 20 | SPEZIE E AROMI | Pepe, Origano, Curry, Zafferano |
| 21 | SUSHI VARIE | Nori, Panko, Wasabi, Tobiko, Tempura |
| 22 | UOVA | Uova fresche, biologiche |
| 23 | VARIE BAR | Ghiaccio, Zucchero bustine |
| 24 | VERDURE | Insalata, Pomodori, Zucchine, Funghi |
| 25 | VINI | Prosecco, Chianti, Barolo, Champagne |

### Materiali (1)

| 26 | MATERIALE DI CONSUMO | Tovaglioli, Pellicola, Guanti, Detersivo, Bicchieri |

### Spese Operative (3)

| 27 | SERVIZI E CONSULENZE | Commercialista, HACCP, POS, Marketing |
| 28 | UTENZE E LOCALI | Bollette, Affitto, Telefono, Gas |
| 29 | MANUTENZIONE E ATTREZZATURE | Riparazione forno, Lavastoviglie, Arredi |

### Speciali (2)

| 30 | 📝 NOTE E DICITURE | SOLO per righe con `totale_riga == 0` |
| 31 | Da Clasificare | **VIETATA** dal constraint DB — fallback: "SERVIZI E CONSULENZE" |

### Centri di Produzione (aggregazione macro)

| Centro | Categorie incluse |
|--------|-------------------|
| FOOD | Carne, Pesce, Latticini, Salumi, Uova, Scatolame, Olio, Secco, Verdure, Frutta, Salse, Prodotti da Forno, Spezie, Sushi |
| BEVERAGE | Acqua, Bevande, Caffè e The, Varie Bar |
| ALCOLICI | Birre, Vini, Distillati, Amari/Liquori |
| DOLCI | Pasticceria, Gelati |
| SHOP | Solo centro di costo |
| MATERIALE DI CONSUMO | Materiale di Consumo |

---

## 4. Dizionario Keyword (`config/constants.py`)

600+ regole deterministiche organizzate per categoria. Esempi:

```python
KEYWORD_RULES = {
    "PESCE":    ["salmone", "gambero", "calamaro", "polpo", "branzino", "orata", ...],
    "CARNE":    ["pollo", "manzo", "vitello", "salsiccia", "macinato", ...],
    "BIRRE":    ["birra", "lager", "weiss", "ipa", "stout", ...],
    "SECCO":    ["pasta", "riso", "farina", "zucchero", "sale", "lenticchie", ...],
    # ...
}
```

**Regole speciali:**
- `SALSICCIA` → CARNE (non SALUMI)
- `MATERIALE DI CONSUMO` è considerato F&B nelle aggregazioni
- Brand in `brand_ambigui` con `aggiunto_automaticamente=True` → bypass dizionario → diretto a GPT

**Priorità:** alimenti > contenitori. Es: "BUSTE PASTA" → SECCO (non MATERIALE DI CONSUMO).

---

## 5. Prompt GPT-4.1-mini

File: `config/prompt_ai_potenziato.py`

Il prompt fornisce a GPT-4.1-mini:
- Lista completa 31 categorie con descrizione dettagliata
- 3+ esempi reali per categoria
- Istruzioni per formati tipici fattura italiano (abbreviazioni, unità di misura)
- Regole speciali (SALSICCIA→CARNE, MATERIALE DI CONSUMO, ecc.)
- Output atteso: JSON con array `categorie` allineato 1:1 con l'input

```python
# Esempio output GPT
{
  "categorie": [
    "CARNE",
    "PESCE",
    "LATTICINI",
    # ...una per ogni articolo inviato
  ]
}
```

**Batch:** 50 articoli per chiamata API (bilanciamento costo/latenza).
**Retry:** `tenacity` con exponential backoff su errori OpenAI (rate limit, timeout).
**Sanitizzazione input:** rimozione control char + truncate a 300 char prima di inviare.

---

## 6. Sistema Quarantena

Le descrizioni con `totale_riga == 0` vengono classificate (come "📝 NOTE E DICITURE") ma **NON salvate** in memoria globale (`prodotti_master`). Questo previene che diciture, bolle di consegna e righe informative inquinino la memoria condivisa tra tutti i clienti.

Regola critica: `"📝 NOTE E DICITURE"` è consentita SOLO su righe con prezzo = 0. Su qualsiasi importo > 0 va usata una categoria reale.

---

## 7. Brand Ambigui (Machine Learning)

La tabella `brand_ambigui` traccia automaticamente i brand che vengono corretti frequentemente in categorie diverse.

**Logica automatica:**
1. Ogni correzione manuale di categoria → incrementa `num_correzioni` per il brand
2. Se brand ha ≥3 correzioni su ≥2 categorie diverse con `tasso_correzione > 20%`:
   → `aggiunto_automaticamente = TRUE`
   → il dizionario lo bypassa completamente
   → passa direttamente a GPT-4.1-mini per massima flessibilità

**Esempio:** un fornitore che vende sia carne che verdure → il brand viene marcato come ambiguo → GPT decide categoria per categoria basandosi sul contesto della descrizione.

---

## 8. Parsing Fatture Elettroniche

### Pipeline XML (FatturaPA)

File: `services/invoice_service.py`

```
1. Lettura file (byte stream)
2. Rilevamento encoding: prolog XML → charset-normalizer → fallback UTF-8
3. Parsing: xmltodict.parse() → dizionario Python (defusedxml per XXE protection)
4. Estrazione metadati: data, tipo documento (TD01/TD04/...), fornitore
5. Validazione P.IVA: cedente/prestatore vs ristorante attivo
6. Estrazione righe DettaglioLinee:
   - Descrizione (pulizia caratteri corrotti)
   - Quantità, Prezzo Unitario, IVA%
   - Sconto percentuale (campo dedicato)
   - Unità di misura normalizzata (KG, LT, PZ, CF…)
   - Codice articolo (se presente)
7. Filtro diciture: regex pattern bolla, righe < 3 lettere
8. Calcolo prezzo effettivo: totale_riga / quantità (gestisce sconti)
9. Categorizzazione immediata: check memoria cache → keyword → "Da Classificare"
10. Salvataggio batch: UPSERT su `fatture` con dedup per file_origine + numero_riga
```

### Estrazione P7M (Firma Digitale CAdES)

**Metodo 1 — ASN.1/CMS** (preferito):
```python
from asn1crypto import cms
content_info = cms.ContentInfo.load(contenuto_bytes)
signed_data = content_info['content']
xml_bytes = signed_data['encap_content_info']['content'].native
```

**Metodo 2 — Pattern matching** (fallback):
- Ricerca pattern `<?xml` o `<FatturaElettronica` nel binario
- Estrazione fino al tag di chiusura corrispondente
- Validazione con `xml.etree.ElementTree`

### Parsing PDF

1. `PyMuPDF (fitz)` estrae testo dal PDF
2. Se testo insufficiente (PDF scansionato): fallback OpenAI Vision
3. Vision: immagine convertita in base64 + prompt strutturato per estrazione dati fattura

### Parsing Immagini (JPG/PNG)

OCR via OpenAI Vision API: immagine in base64 + prompt estrazione strutturato.

### Tipi Documento Gestiti

| Codice | Tipo | Trattamento |
|--------|------|-------------|
| TD01 | Fattura | Importi positivi normali |
| TD02 | Acconto su fattura | Importi positivi |
| TD04 | Nota di Credito | **Importi invertiti** (negativi) |
| TD05 | Nota di Debito | Importi positivi |
| TD06 | Parcella | Importi positivi |
| TD16–TD27 | Autofatture/Integrazioni | Importi positivi |

---

## 9. Briefing AI Giornaliero

File: `services/daily_briefing_service.py`

### Architettura

```
GET /api/home/briefing
    │
    ├── Check cache: daily_briefing_state
    │   ├── Se data = oggi E fingerprint notifiche invariato → restituisce cache
    │   └── Altrimenti → rigenera
    │
    ├── Raccolta dati (tutto Python, nessun numero inventato dall'AI):
    │   ├── Notifiche attive (filtrate, dedup, max 5)
    │   ├── KPI periodo: fatturato, food cost, MOL, scadenze
    │   ├── Alert prezzi ordinati per impatto €/mese
    │   └── Stato salute (4 voci a peso uguale)
    │
    ├── Anonimizzazione: nomi prodotti → segnaposto (mai inviati a OpenAI)
    │
    ├── Generazione narrativa AI (gpt-4o-mini):
    │   ├── Saluto adattivo all'ora (fuso Europe/Rome)
    │   ├── Usa SOLO il nome referente (mai la ragione sociale)
    │   ├── Bullet con numeri già calcolati dal backend
    │   └── Fallback template se AI non risponde
    │
    └── Salva in daily_briefing_state + aggiorna fingerprint
```

**Regola d'oro:** L'AI non calcola mai numeri — il backend Python calcola, l'AI racconta.

### Pipeline deterministica

1. **Dedup per topic**: una sola card per tipo di avviso (es. una card "prezzi" anche con 5 alert)
2. **Filtro "azionabile E utile"**: solo notifiche che richiedono un'azione concreta
3. **Gerarchia tematica**: scadenze urgenti > alert prezzi > dati mancanti > info
4. **Max 5 card**: non sovraccaricare il ristoratore

---

## 10. Calcolo Alert Prezzi

File: `services/price_impact_service.py`

Ordina gli alert prezzi per **impatto economico €/mese** (non solo per variazione %).

```
Per ogni prodotto con variazione > soglia:
    impatto_mensile = (prezzo_attuale - prezzo_storico) × quantità_media_mese
    
Ordina: TOP impact descending
```

Usato da:
- `GET /api/home/alert-prezzi` (Home AI)
- `GET /api/prezzi/alert` (pagina Prezzi)
- Notifiche in-app (tipo "Alert prezzi > soglia")

**Soglia personalizzabile:** `users.price_alert_threshold` (default 5%, range 1%–50%)

---

## 11. Analisi e Tag (Tag Analytics)

File: `services/tag_analytics_service.py` + `tag_suggestion_service.py`

### KPI per tag

Per ogni custom tag selezionato:
- Spesa totale nel periodo
- Incidenza % sul totale F&B
- Ultimo prezzo medio
- N. prodotti distinti associati
- N. fornitori distinti

### Trend prezzi

Serie temporale del prezzo medio mensile per i prodotti del tag. Recharts sul frontend.

### Analisi fornitori

Per ogni fornitore che compare nei prodotti del tag: totale speso, n. prodotti, incidenza %.

### Suggerimenti tag automatici

Algoritmo `tag_suggestion_service.py`:

1. **`_get_product_root`**: estrae la radice del nome (primo token significativo, len≥4, no cifre, no stopword)
2. **`new_tag`**: cluster di prodotti con radice comune (min 3 prodotti, min 5 occorrenze) → suggerisce nuovo tag
3. **`extend_tag`**: radice già presente in un tag esistente (min 2 occorrenze) → suggerisce di aggiungere prodotti al tag esistente

**Rimosso:** fuzzy matching e aggregazione per unità di misura (causavano troppi falsi positivi).

---

## 12. Tracking Costi AI

File: `services/ai_cost_service.py`

Ogni chiamata OpenAI registra un evento in `ai_usage_events`:

```python
track_ai_usage(
    ristorante_id=...,
    user_id=...,
    operation_type="categorization",  # pdf / briefing / chat / other
    prompt_tokens=...,
    completion_tokens=...,
    model="gpt-4o-mini",
    source_file=...
)
```

**Prezzi per modello** (`_MODEL_TARIFFE` in `ai_cost_service.py`):
- GPT-4o-mini (briefing): Input $0.15 / Output $0.60 per 1M token
- GPT-4.1-mini (categorizzazione, chat): Input $0.40 / Output $1.60 per 1M token

**Budget chat AI:**
- Free: 0 domande/giorno
- Base: 10 | Plus: 20 | Pro: 30
- Target Pro: ≤ €3/mese

**Admin Panel** (`/admin/sistema` → Costi AI): aggregazione per cliente/ristorante, periodi 7/30/90 giorni, quota vision giornaliera per ristorante.

---

*AI Pipeline v6.0 — 5 Giugno 2026*
