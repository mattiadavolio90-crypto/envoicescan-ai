# PIANO HOME / BRIEFING v2 — decisioni 19/06

Specifica concordata con Mattia per il potenziamento della Home (briefing, card,
avvisi) di singolo punto vendita e catena. È il piano di lavoro: l'implementazione
parte solo dopo conferma, e il deploy va fatto **fuori orario** (clienti in uso di
giorno) svuotando poi la cache briefing.

Stato voci: ✅ deciso · ❓ ancora da decidere · 🔧 da verificare in codice prima.

---

## 0. Regola trasversale
**Ogni avviso spegnibile rispetta il toggle a monte:** se il toggle è spento, la
funzione che lo calcola **non gira proprio** (non si limita a nascondere il
risultato). Vale per scadenze, prezzi, coperti, ecc. ✅

**Deploy:** mai deployare nuove implementazioni senza permesso esplicito di Mattia
(decide lui le eccezioni); posso deployare da solo solo per fix fisiologici / blocchi
app. Deploy serale + pulizia cache briefing. ✅

---

## 0-BIS. BUG PRIORITARIO — "Tutto in ordine" verde falso (DA FARE PER PRIMO)
Causa: il verde NON è gated sulla Salute.
- **Backend**: `tutto_ok = len(selected) == 0` guarda solo le card da fare, non la
  Salute né i dati mancanti.
- **Frontend**: `tuttoOk = tutto_ok || visibili.length === 0` → archiviando a mano
  tutte le card si ottiene il verde anche con dati incompleti.

**Fix:** "Tutto in ordine" SOLO se nessuna card da fare **E** Salute non rossa/gialla
**E** nessun dato mancante. Altrimenti, con 0 card ma dati incompleti, messaggio
neutro: "Nessuna azione urgente, ma per il quadro completo mancano: …". Inoltre le
card "dati mancanti" NON archiviabili in Home (come già negli Avvisi). ✅ PRIORITÀ 0

---

## 1. I tre ruoli (scopi distinti)

| | Briefing (testo) | Card (Home) | Avvisi (pagina) |
|---|---|---|---|
| Scopo | raccontare la giornata | agire sulle cose chiave | registro completo |
| Forma | frase narrata, filo unico | riquadri con 1 azione | lista archiviabile |
| Contenuto | andamento + sintesi to-do | solo cose da fare | tutto, anche minori |
| Quante | 1 discorso | **max 4** | illimitate |

- **Campanella in alto: eliminata.** Si accede agli avvisi da Home → pagina
  **"Avvisi"** (nome univoco, da confermare). ✅
- L'**andamento** (incasso di ieri, MOL quando è il momento, salute) sta **nel
  testo del briefing**, non occupa card. ✅
- Le **card** sono SOLO cose da fare, **max 4**. ✅ (leva: eventualmente 5)
- Coerenza: ogni card esiste anche in Avvisi; Avvisi ha in più le minori. Mai
  contraddizioni tra i tre. ✅

---

## 2. Struttura del briefing (punto s5)
Un **unico discorso con filo conduttore**, in due momenti:
1. **Andamento** — com'è andata (incasso di ieri; MOL solo a fine/inizio mese; salute).
2. **Da fare** — cosa manca/va sistemato.
Cucito insieme, non due blocchi staccati. Le regole attuali (priorità, gate, max
card) restano: cambia solo la narrazione che le lega. ✅

---

## 3. Avvisi — condizioni aggiornate

| Avviso | Regola nuova | Stato |
|---|---|---|
| Scadenze fornitori | calcolate solo se toggle attivo | ✅ |
| Incasso di ieri mancante | solo se NON in modalità mensile E la sede ha già storia di incassi giornalieri | ✅ |
| Righe dubbie | testo "da **controllare**" (non categorizzare); card mostra **solo il numero totale** + link a tab Articoli filtrata sulle dubbie | ✅ 🔧 (verificare filtro tab) |
| Fatture costo mancanti | segnalare dopo **7 giorni** dall'ultima fattura (era 30) | ✅ |
| Ricavi automatici assenti | soglia = **giorni di chiusura settimanali** dal configuratore (0 sempre aperto → 1g; 1 → 2g; …) | ✅ (nuovo campo configuratore) |
| Anomalia coperti | scostamento **≥20%** (era 30%) vs **media del mese in corso** | ✅ |

---

## 4. MOL e "buona notizia" (punti s4, s4.4)
- Durante il mese in corso: **non si parla di MOL** (fatture incomplete → falso). ✅
- Si parla di MOL **solo a fine/inizio mese**, sul mese **chiuso**, come **dato di
  fatto**: "è finito giugno, il MOL di giugno è migliore di maggio". ✅
- **Finestra:** ultimo giorno del mese (anteprima, tono prudente "si sta
  chiudendo…") + **primi 7 giorni** del mese nuovo (a mese chiuso, tono netto). ✅
- Niente festeggiamento del MOL in corso; al massimo accenno prudente "il MOL
  sembra in miglioramento, se tutti i costi sono caricati". ✅
- Scontrino medio "notevole": soglia da 15% → **10%**. ✅

---

## 5. Catena

### Principio: la catena è MACRO, il PV è DETTAGLIO ✅
La catena dà info d'insieme e **indirizza** ("vai a sistemare il PV X: mancano dati /
task importanti"). NON spiega il dettaglio del cosa fare: quello lo si vede entrando
nel PV. Mai duplicare in catena le istruzioni operative del PV.

### Completezza per PRESENZA DI DATI, non per % salute ✅
Una sede entra nel confronto margini solo se ha **tutti e tre**:
1. fatturato (mensile o giornaliero),
2. costi da fatture caricate (F&B),
3. costo personale almeno mensile in Ricavi e Margini.
Extra (spese personale, ecc.) non obbligatori.

### Stessa cascata del PV — i dati mancanti vengono PRIMA ✅
- **dati incompleti** → si parla **prima dei dati mancanti** (e di QUALE PV), perché
  senza quelli food cost e MOL sono **falsi**: NON mostrarli come veri;
- ci sono fatture F&B → si può parlare di **food cost e 1° margine** del gruppo;
- ci sono anche personale + spese generali → si può parlare di **MOL** del gruppo.
Le voci scendono a cascata sottraendo dal fatturato (food → 1° margine → MOL).

### Cosa sistemare in catena (tappa dedicata, riusa la logica PV)
Stato oggi: briefing gruppo + 2 card (Conti, Salute) + segnali (solo 3 tipi:
margine_calo, prezzi_sopra, ricavi_mancanti) + ranking PV.
- **Briefing gruppo**: già gateato (18/06). Allinearlo al nuovo modello macro/indirizzo.
- **"Tutto sotto controllo" (card segnali)**: STESSO bug del verde PV → gate su
  salute + presenza dati dei PV. Non dire "tutto ok" se un PV ha dati mancanti.
- **Nuovo segnale "dati mancanti per PV"**: la catena deve dire "al PV X manca il
  fatturato / il personale / le fatture costo → vai a sistemare". Oggi NON esiste.
- **Card "I conti del gruppo"**: applicare la cascata → se i PV non hanno i costi,
  niente MOL/food gonfiati; mostrare invece "dati incompleti, completa i PV: …".

---

## 5-BIS. Cliente NUOVO (onboarding) ✅
Cliente senza dati (es. 1° luglio, zero fatture) NON deve vedere un briefing
vuoto/rotto né un falso verde. Briefing di **benvenuto** dedicato finché mancano i
dati base: "Benvenuto. Per partire: carica le prime fatture / inserisci il fatturato
di maggio…", con i primi passi come card. Si disattiva da solo quando i dati
arrivano.

## 5-TER. Briefing ascoltabile ✅
Pulsante 🔊 che legge il testo del briefing. Fase 1: **Web Speech API** del browser
(`speechSynthesis`) — gratis, offline, voce di sistema. Fase 2 (futura, opzionale):
TTS premium (OpenAI/ElevenLabs) se serve voce più naturale.

## 5-QUATER. Sobrietà narrazione ✅
Il prompt è già sobrio (vieta entusiasmo, aggettivi enfatici, frasi motivazionali,
limita emoji). Aggiungere SOLO la **regola di prudenza sui dati incompleti**: se i
dati del periodo non sono completi, parlarne con cautela e non trarre conclusioni
(es. niente MOL durante il mese; "se tutti i costi sono caricati").

---

## 6. Decisioni finali
- ✅ Nome pagina avvisi: **"Avvisi"**.
- ✅ Card Home: **max 4** (l'andamento è nel testo, non occupa card).
- 🔧 Verificare che la tab Articoli abbia già il filtro "righe dubbie" per il link.
- 🔧 Verificare dove vive il configuratore assistente per aggiungere "giorni di
  chiusura settimanali".

---

## 7. Ordine di lavoro proposto (un pezzo per volta, deploy fuori orario, su OK Mattia)
0. **[PRIORITÀ] Fix "Tutto in ordine" verde falso** — gate su Salute + dati mancanti
   (backend + frontend), card dati-mancanti non archiviabili in Home.
1. Soglie rapide (coperti 20%/mese, fatture 7gg, scontrino 10%) — basso rischio.
2. Testo "da controllare" + numero + link tab Articoli.
3. Incasso di ieri: nuova condizione (no mensile + storia incassi).
4. Toggle-gating delle funzioni (scadenze e altre).
5. Struttura briefing in due momenti (andamento → da fare) + MOL solo fine/inizio mese
   + prudenza dati incompleti nel prompt.
6. Configuratore: giorni di chiusura settimanali → soglia ricavi auto.
7. **Catena (tappa piena, riusa la logica PV):**
   - gate "tutto sotto controllo" su salute + presenza dati dei PV;
   - nuovo segnale "dati mancanti per PV" (vai a sistemare il PV X);
   - card "I conti del gruppo" a cascata (no MOL/food gonfiati se dati incompleti);
   - briefing gruppo in modalità MACRO/indirizzo (non duplica il dettaglio del PV).
8. Card max 4 + eliminazione campanella + pagina Avvisi rinominata.
9. Cliente nuovo (onboarding) + briefing ascoltabile (Web Speech).
