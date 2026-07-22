# Piano — Briefing dinamico e contestuale

> Redatto 22/07/2026, rivisto dopo verifica delle INERENZE (cosa la Home già
> mostra, per non creare doppioni). Obiettivo: trasformare il briefing Home da
> "lista di dati nudi" a "sintesi con contesto". Il problema non è la scrittura AI
> (volutamente sobria, non può inventare): sono i **segnali deterministici** in
> ingresso a essere poveri di confronto. Si arricchiscono quelli, a monte dell'AI.

## Principio guida (non violare)
- **L'AI non calcola, racconta.** Ogni numero/confronto nasce nel backend come
  bullet deterministico; l'AI lo riscrive solo in tono.
- **Niente confronti fuorvianti** (motivo del divieto originale): SOLO il confronto
  robusto = media dello stesso giorno-della-settimana. Baseline corta → silenzio.
- **Zero rumore** e **zero ridondanza con le card sotto**: il briefing NON ripete
  ciò che una card della Home già dice per esteso.
- Ad ogni modifica: **bump `_BRIEFING_CODE_VERSION`** (auto-invalida la cache).

---

## Inerenze verificate (cosa la Home mostra OGGI) — 22/07
La Home (`dashboard/page.tsx`) contiene in ordine:
1. **Briefing** (`home-briefing.tsx`) — testo AI + card "Da fare oggi" (max 4).
2. **Widget notifiche** (solo il contatore non letto).
3. **Card KPI "I tuoi conti"** (`kpi-block.tsx`) + **Card Salute**.

**NON esiste oggi** una card "fatture ricevute via SDI" in Home: era solo
pianificata (`PIANO_RIEPILOGO_FATTURE_NUOVE.md`, ora rimosso dalla root; memoria
`piano-riepilogo-fatture-nuove`), **mai implementata** (verificato nel codice).
→ Conseguenza diretta sulla Fase 3 (sotto).

Dati DB (22/07): SUSHILAND ×3 sedi = 202 gg incasso+coperti, ultimo 21/07.
OFFSIDE = SDI attivo, **0 ricavi giornalieri** (inserisce mensilmente), 311 righe
fattura. Pattern settimanale Mariano stabile (SD 15-20%) → confronto giorno-settimana valido.

---

## FASE 1 — Apertura incasso contestuale

**Regola del contenuto (tua decisione):** l'apertura mostra il confronto e i
coperti/scontrino **solo se quei dati esistono**. Se ci sono i coperti → incasso +
confronto + coperti + scontrino. Se NON ci sono i coperti → solo l'incasso (+
confronto giorno-settimana se la baseline c'è). Nessun campo inventato, degrado
graduale.

**File:** `services/fastapi_worker.py` — `_briefing_buona_notizia` (blocco incasso
~riga 4584); `services/daily_briefing_service.py` — `_buona_notizia_bullet` +
`_buona_notizia_frase` (blocco `incasso_ieri`).

### 1a. Confronto media stesso giorno-della-settimana
Nuovo helper `_incasso_confronto_giorno_settimana(ristorante_id, sb, ieri_d, netto_ieri)`:
- Media degli ultimi stessi-giorni-settimana (es. tutti i martedì), finestra ~90 gg,
  ieri escluso. **Requisito ≥4 occorrenze**, altrimenti `None` (niente confronto).
- Ritorna `{media, delta_pct, verso}`. "in linea" se |delta| < ~8% (niente enfasi).

### 1b. Coperti + scontrino SOLO se presenti
Nuovo helper `_coperti_scontrino_ieri()` che ritorna `(coperti, scontrino_medio)`
SOLO se `coperti` di ieri è valorizzato e > 0. Se manca → non si aggiunge nulla.
Non tocca `_scontrino_medio_significativo` (che resta per il caso "anomalia forte").

### 1c. Payload (tutti i campi extra opzionali)
```
{ tipo:'incasso_ieri', incasso,
  giorno_settimana?, cfr_media?, cfr_delta_pct?, cfr_verso?,   # 1a se baseline ok
  coperti?, scontrino_medio? }                                  # 1b se coperti presenti
```

### 1d. Template (esempi)
- Con coperti: *"Ieri (martedì) sono entrati € 13.824, sopra la media dei martedì
  (~12.300), con 420 coperti e scontrino medio di 32,90 €."*
- Senza coperti (es. OFFSIDE se avesse incasso giornaliero): *"Ieri sono entrati
  € X, in linea con gli altri martedì."*
- Baseline corta e niente coperti: *"Ieri sono entrati € X."* (come oggi).

**Ridondanza con "I tuoi conti"?** No: la card KPI mostra il mese (food cost, MOL,
fatturato mensile), il briefing parla del **giorno di ieri**. Orizzonti diversi,
nessun doppione. Coperti/scontrino di ieri non sono nella card KPI (verificato:
`kpi-block.tsx` è mensile). C'è un tab Coperti in Margini, ma è pagina separata.

**Bump versione. Rischio: basso.**

---

## FASE 2 — price_alert affidabile + SOLO preferiti/tag  *(spiegazione del "punto 2")*

**A cosa serve / qual è il problema:** nel briefing esiste già la voce "prezzi in
aumento da controllare" (topic `price_alert`), che dovrebbe accennare a prodotti E
tag con rincari rilevanti. Il motore che la calcola (`calcola_alert_prezzi_impatto`)
gira nel path sincrono con un **budget di 4 secondi**; se sfora, viene **saltato in
silenzio** (worker:5798) e la voce sparisce. Su SUSHILAND (4.500–5.600 righe/sede)
è proprio il cliente con più dati — quindi più variazioni prezzo reali — a rischiare
di non vederla mai. **Non è una feature nuova: è far funzionare in modo affidabile
una voce che oggi c'è ma si auto-annulla sui clienti grandi.** Ecco perché nello
screenshot non compare nulla sui prezzi.

### 2a. Ambito prodotti = SOLO preferiti + tag costruiti (tua decisione 22/07)
Decisione: **da ora in poi, per TUTTI i clienti**, l'alert prezzi considera come
prodotti **solo quelli segnati come preferiti** (stella nel tab Variazione prezzi /
Osservatorio) più i **tag costruiti**. Niente più "fascia Pareto automatica" su
prodotti qualsiasi.

Il codice per farlo **esiste già**: `_alert_prodotti(preferiti_keys=...)` filtra sui
soli preferiti, e il ramo Pareto scatta solo se il flag
`assistant_preferences.alert_prezzi_solo_preferiti` è spento
(`price_impact_service.py` righe 340-408). Serve solo **rendere quel comportamento il
default per tutti**, non riscrivere il motore.

Implementazione (da valutare in fase di scrittura, la più pulita):
- rendere `_leggi_solo_preferiti()` di fatto sempre vero (default `True` / ignorare il
  flag e forzare la modalità preferiti). Il ramo Pareto (`_prodotti_pareto`) diventa
  codice morto → si può rimuovere o lasciare dietro un flag di sicurezza spento.

**Conseguenza da esplicitare (NON silenziosa):** un cliente senza nessuna stella
messa vedrà alert prezzi **solo sui tag**; senza stelle né tag, **nessun alert
prezzi** finché non segna un preferito o costruisce un tag. È il comportamento
voluto (zero rumore su prodotti a caso), ma va comunicato: se un cliente "non vede
più i prezzi" è perché non ha preferiti/tag, non è un bug.

### 2b. Affidabilità su clienti grandi (precalcolo, non "alzare il timeout")
1. Profilare `services/price_impact_service.py` sulle 3 sedi SUSHILAND: capire dov'è
   il costo (query? loop Python? N+1? `_alert_tag` è il pezzo lento noto). La modalità
   "solo preferiti" è già più leggera del Pareto (meno prodotti da valutare).
2. Spostare il calcolo nel **job async** `_briefing_rigenera_async` (worker:5978),
   che gira DOPO la risposta: lì nessuno aspetta, il budget può salire senza
   rallentare la Home. Il risultato entra nello snapshot e al load successivo è
   istantaneo dalla cache.
3. Confermare che l'alert su **tag** (`top_tipo=='tag'`, già supportato worker:5793)
   emerga: il codice c'è, va verificato che non sia il timeout a mangiarlo.

**Rischio: medio** (profiling prima; tocca price_impact_service + pipeline async).
Nota: 2a cambia il comportamento anche della **pagina Prezzi** (stesso motore), non
solo del briefing — coerente e voluto.

---

## FASE 3 — Apertura per sedi SDI senza incasso giornaliero (OFFSIDE)  ✅ FATTA
### con vincolo ANTI-RIDONDANZA esplicito

> **Implementata 22/07** (non ancora deployata). Helper
> `_fatture_arrivate_ieri_sdi` in `services/fastapi_worker.py` (blocco 3 di
> `_briefing_buona_notizia`, dopo l'incasso) + `_fatture_arrivate_frase` in
> `services/daily_briefing_service.py` (usata da bullet e frase). Versione briefing
> bumpata a **12**. Test: `tests/test_briefing_fatture_arrivate.py` (11).

**Problema:** OFFSIDE ha SDI attivo ma 0 ricavi giornalieri → nessuna apertura
positiva mai. Il suo dato dinamico sono le fatture ricevute via SDI.

**Chiarimento tuo (punto 3):** NON deve essere ridondante con la card "fatture
ricevute via SDI" in Home. **Verificato: quella card NON esiste ancora** (solo
pianificata). Quindi oggi non c'è ridondanza *reale* — ma c'è un rischio *futuro*.

**Decisione tua 22/07: Strada A — SOLO il briefing che accenna, per ora.**
La card fatture (Strada B, `PIANO_RIEPILOGO_FATTURE_NUOVE.md`) si valuta **dopo** aver
chiuso le 3 fasi, riaprendo quel documento.

- **Strada A (scelta):** l'apertura del briefing annuncia le fatture arrivate
  ("Ieri sono arrivate 3 fatture per € 1.240, già categorizzate; 2 hanno righe da
  controllare"). L'accenno può avere un paio di numeri finché la card non esiste.
  **Regola scritta nel codice/prompt fin da ora:** se in futuro nasce la card
  dedicata, il briefing **rimanda alla card e non ripete gli importi** (una frase
  breve: "sono arrivate fatture nuove, le trovi qui sotto"), esattamente come già
  fa oggi il price_alert col suo dettaglio. Così quando si aprirà la Strada B non si
  riscrive la logica del briefing, si toglie solo qualche numero dall'accenno.

**Il principio è unico:** un solo posto possiede il DETTAGLIO
(importi/fornitori). Se nasce la card, il dettaglio è suo e il briefing solo accenna.
Finché la card non c'è, il briefing può dare l'accenno con un paio di numeri, senza
diventare un elenco.

**Da verificare sui dati OFFSIDE prima di scrivere il testo:** finestra ("ultime
24h" vs "dall'ultimo briefing"), e cosa conta come "arrivata" (created_at vs data
ricezione SDI in `payload_meta`). **Rischio: medio.**

> Nota inerenza: la Feature 1 di quel piano (sopprimere l'alert "fatture mancanti"
> per canale SDI, `_briefing_fatture_mancanti` worker:4983) è indipendente da questo
> lavoro ma tematicamente vicina: se si tocca l'apertura SDI, valutare insieme che
> l'alert di ASSENZA e l'annuncio di PRESENZA non si contraddicano (uno dice "non
> arrivano", l'altro "ne sono arrivate 3") nello stesso giorno.

---

## Ordine di esecuzione (deciso 22/07)
1. **Fase 1** ✅ — impatto massimo, rischio minimo, risolve il cuore.
2. **Fase 2** ✅ — solo preferiti/tag per tutti (2a) + precalcolo async (2b).
3. **Fase 3** ✅ — Strada A: solo briefing che accenna.
4. **DOPO le 3 fasi** ← *siamo qui* — riaprire `PIANO_RIEPILOGO_FATTURE_NUOVE.md`
   e valutare la card fatture (Strada B).

Ogni fase deployabile da sola (bump versione + svuota cache sede di test).
Test da aggiornare: quelli su `_build_snapshot` / `buona_notizia` /
`_compose_narrative` (i template cambiano forma). Guardrail
`test_documentazione_onesta.py` se si citano simboli nei doc.

## Cosa NON si tocca
- Layer AI e prompt (resta sobrio; riceve bullet più ricchi).
- Regola "l'AI non calcola".
- Divieto di confronti fuorvianti (si aggiunge SOLO il confronto robusto).
- Pipeline `_build_snapshot` / priorità / max 4 card.

## Mappa inerenze (per non creare doppioni)
| Nuovo contenuto briefing | Dove vive già un'info simile | Come si evita il doppione |
|---|---|---|
| Incasso ieri + confronto giorno | — (KPI card è mensile) | Orizzonti diversi: giorno vs mese |
| Coperti/scontrino ieri | tab Coperti in /margini (storico) | Briefing = solo ieri, 1 riga; pagina = analisi |
| Prezzi in aumento (Fase 2) | dettaglio in /prezzi + card sotto | Briefing accenna, il resto ha i numeri |
| Fatture arrivate (Fase 3) | card SDI **non ancora esistente** | Regola: se nasce la card, briefing solo accenna |
| Fatture mancanti SDI | `_briefing_fatture_mancanti` | Non contraddire "assenza" vs "presenza" |
