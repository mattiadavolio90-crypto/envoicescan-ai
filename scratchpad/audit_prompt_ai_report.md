# Audit prompt AI — `config/` (voce §3 #2) — 03/09/2026

**Perimetro misurato:** `config/` = 2.389 righe all'apertura (2.396 alla chiusura,
+7 del fix): `constants.py` 2.043 → 2.050, `prompt_ai_potenziato.py` 311,
`logger_setup.py` 31, `__init__.py` 4. Il prompt e i due file piccoli letti
integralmente; il dizionario (1.268 → 1.273 chiavi) validato al 100% via script
(chiavi, valori, codifica byte-level), non letto a occhio riga per riga.

**Metodo:** lettura + validazione programmatica incrociata prompt ↔ costanti ↔
codice consumatore (`ai_service.py`, `queue_processor.py`, `upload_handler.py`)
↔ dati reali di produzione (Supabase `vthikmfpywilukizputn`).

---

## Cosa regge (misurato, non dedotto)

1. **Coerenza strutturale piena prompt ↔ costanti.** 29 categorie ufficiali
   (25 F&B + 4 spese), tutte e 29 con definizione nel prompt; zero categorie nel
   prompt fuori lista. Dizionario 1.268 voci, regole fornitore (12), unità di
   misura (5), alias legacy (7), centri di produzione: **ogni valore è una
   categoria valida**, zero refusi.
2. **Zero categorie estranee in produzione.** Su tutte le righe attive di
   `fatture`: nessuna categoria fuori dalla lista ufficiale
   (+ `Da Classificare` + NOTE). Il constraint e la validazione runtime tengono.
3. **La contraddizione interna del prompt è neutralizzata dal codice, per
   disegno.** Il prompt chiede due cose in tensione: la regola 6 e la «REGOLA
   ASSOLUTA» dicono «se non riconosci → Da Classificare», la sezione formato dice
   «DEVI classificare ogni articolo… anche con confidence bassa scegli comunque».
   Non è un buco: il gate a valle accetta solo `alta` non-dubbia o categoria
   confermata dal runtime deterministico; `bassa` e `media` non confermate
   tornano `Da Classificare` + coda. Il gate è lo stesso su entrambi i percorsi
   (coda: `worker/queue_processor.py` blocco «PRINCIPIO rev. 24/06»; upload:
   `services/upload_handler.py::_categoria_affidabile`). Verificato a DB: le
   uniche fonti AI scritte sono `AI_alta`/`AI_confermata`, zero righe da fonte
   debole.
4. **Parsing risposta robusto.** Mappatura per `idx` esplicito (niente
   slittamenti), idx mancanti → `Da Classificare` + log, categorie inventate →
   recupero deterministico, troncamento `finish_reason=length` loggato,
   `temperature=0.1`, `response_format=json_object`, tracking costi per
   ristorante, deadline/budget sui retry.

## Difetto trovato e CHIUSO in sessione

**12 chiavi del dizionario erano mojibake** (doppia codifica UTF-8 nei byte del
file): `BACCALÃ€`, `WÃœRSTEL`, `RAGÃ™`, `CAFFÃˆ`, `TÃˆ`, `TIRAMISÃ™`, `BIGNÃˆ`,
`CONTABILITÃ€`, `PUBBLICITÃ€`, `INDENNITÃ€`, `ELETTRICITÃ€`, `MACCHINA CAFFÃˆ` —
pattern compilati con `re.escape`, quindi **non potevano matchare nessuna
descrizione reale**. Più 4 chiavi accentate corrette ma ugualmente irraggiungibili
(`GRUYÈRE`, `CAPACITÀ`, `SOUFFLÉ`, `BAMBÙ`) e il `€` corrotto in
`REGEX_NUMERI_UNITA`.

**Impatto misurato — quasi nullo oggi, concreto domani:**
- **0 righe su tutto il DB di produzione contengono un carattere accentato**:
  le fatture elettroniche XML/P7M arrivano senza accenti (o con l'apostrofo:
  `RAGU'`, `CAFFE'`). Quindi anche le chiavi accentate *corrette* non matchano.
- Copertura persa reale: 6 chiavi senza gemello piano nel dizionario. A DB solo
  `RAGU` esiste (8 righe, ~191 €; 7 già in SALSE E CREME per altre vie, 1 in
  CARNE — divergente dall'intento del dizionario, 59,70 €). BACCALA,
  CONTABILITA, ELETTRICITA, MACCHINA CAFFE: 0 righe oggi.
- Innesco futuro: il percorso PDF/Vision **conserva gli accenti** e nessuna riga
  a DB proviene ancora da PDF — il primo cliente PDF avrebbe preso il colpo.

**Fix (committato in questa sessione):**
- riparate le 21 righe corrotte di `config/constants.py` (round-trip
  cp1252→UTF-8: 12 chiavi + regex `€` + 8 commenti);
- aggiunti 5 gemelli piani per la forma reale in fattura: `BACCALA`, `RAGU`,
  `CONTABILITA`, `ELETTRICITA`, `MACCHINA CAFFE` (NON `TE`: troppo corto, il tè
  in fattura è `THE`, già chiave);
- presidio `tests/test_constants.py::TestDizionarioEncoding`: guardia
  anti-mojibake sulle chiavi (dato, non sorgente) + 10 casi comportamentali su
  `applica_correzioni_dizionario` (forma piana/apostrofo E forma accentata).
  **Provato per mutazione**: ri-corrotta una chiave e rimosso un gemello → 3
  rossi; ripristino → verde. Suite correlate: 3.330 + 284 test verdi.

## Rilievi minori (annotati, non fix)

- **2 righe legacy `Da Classificare` con `needs_review=false`** (SUSHILAND Villa
  Guardia, coppia acconto/storno ±5.392,02 € a somma zero, giugno, pre-Fase 2).
  Violano l'invariante «ogni Da Classificare va in coda»; restano comunque
  visibili dal filtro per categoria. Dati, non codice: si sistemano se/quando
  Mattia vuole una passata di riallineamento dati.
- **Il prompt conta «26 categorie F&B»** includendo MATERIALE DI CONSUMO, che per
  le costanti è spesa generale (25+4). Il totale 29 torna e il raggruppamento non
  raggiunge mai l'output: cosmetico, dentro il solo prompt.
- **Commento stale** in `ai_service.py` (limite «128k di gpt-4o-mini» mentre il
  modello è `gpt-4.1-mini` da decisione A/B 5/7): fuori perimetro `config/`,
  solo annotato.
- `normalizza_descrizione` elimina la parola `BAR` («ZUCCHERO BAR» → «ZUCCHERO»):
  perde un indizio di contesto per l'AI, ma la keyword `ZUCCHERO` e le regole
  VARIE BAR coprono i casi visti. Non misurabile un impatto oggi.

## Fuori perimetro dichiarato

I prompt AI che vivono FUORI da `config/`: il prompt del briefing giornaliero
(`daily_briefing_service.py`, voce §3 #4) e l'eventuale prompt chat/assistente
(router, voce §3 #6). `KPI_SOGLIE`/`COPERTI_ALERT` sono letti qui come dati (la
soglia food cost 38 combacia con quella citata dal rilievo Q2) ma il loro uso è
del briefing: si auditano con la voce #4.
