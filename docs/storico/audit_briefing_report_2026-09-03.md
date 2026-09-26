# Audit briefing giornaliero — `daily_briefing_service.py` (voce §3 #4) — 03/09/2026

**Perimetro:** `services/daily_briefing_service.py`, 1.637 righe all'apertura
(letto integralmente), + verifica incrociata con i chiamanti nel worker
(raccolta notifiche, cache-first, rigenerazione async) e col DB di produzione
(`daily_briefing_state`: 42 snapshot, 24 dal 20/8).

## Cosa regge (misurato)

- **L'impianto è solido**: pipeline deterministica (bullet/card/azioni) + strato
  AI solo per il tono, coi numeri calcolati a monte; nomi propri anonimizzati
  prima di OpenAI e ripristinati dopo; fallback al template su ogni errore.
- **La validazione della narrativa (v18) funziona in produzione**: su 24
  snapshot recenti, 0 violazioni di tono, 0 esclamativi, 0 numeri fuori posto.
  Il rilievo «le regole di tono sono violate in produzione» (memoria di un ciclo
  precedente) è **invecchiato**: era pre-validazione.
- **`LOGICA_BRIEFING.md` è allineato al codice**: ri-misurate le 11 leve della
  tabella §9 — max card 4 ✓, rientro 7gg ✓, scontrino 10% ✓, coperti 20% ✓,
  fatture 7gg ✓, novità 7gg ✓, arretrato 20 ✓, ricavi chiusura+1 ✓, TTL 30' ✓,
  salute 80/50 ✓, catena ≥50 ✓. Anche il rilievo «6 su 11 sbagliate» in memoria
  è invecchiato. Unica imprecisione trovata e corretta: «una settimana di
  storico» per l'anomalia coperti → sono **4 giorni con coperti**
  (`min_giorni_baseline`).
- **Cache a tre reti**: `code_version` (auto-invalidazione su deploy), TTL 30',
  invalidazione a eventi (14 call site). Il `notifications_fingerprint` è solo
  diagnostico e il codice lo dichiara.

## Chiuso in sessione (bump `_BRIEFING_CODE_VERSION` 20 → 21)

1. **Importi delle scadenze in formato inglese** (`{totale:,.2f}` →
   «€ 1,234.50») nei bullet `scadenza_superata`/`scadenza_imminente`: migliaia e
   decimali invertiti per un lettore italiano. **Latente**: 0 bullet scadenze su
   42 snapshot in cache — ma il primo cliente con una scadenza in card l'avrebbe
   letto. Fix con `_euro_it_cent` + 3 test (incluso il caso reale 4,4 M€).
2. **Il validatore ora scarta anche l'entusiasmo vietato** (regola 3/3-bis:
   'fantastico', 'continua così', ' ottimo'...): prima controllava solo numeri
   inventati e burocratese, e il divieto di tono viveva solo nel prompt — che il
   burocratese aveva già dimostrato non bastare. Misurati 0 casi su 42 snapshot
   (il prompt oggi regge), ma la rete adesso c'è. 7 test, incluso il non-match
   su «ottimizzare».
   **Provato per mutazione**: f-string inglese reintrodotta → 2 rossi; lista
   entusiasmo rimossa → 5 rossi. Suite briefing+salute: 390 verdi.

## Annotato, non aperto

- **Le notifiche scadenza non vengono generate dall'1/6** (7 record totali in
  `notification_inbox`, ultimo 01/06) mentre lo scadenziario ha dati veri
  (4,4 M€). Il generatore vive fuori da questo file: da verificare nella voce
  §3 #5 (worker) / #6 (router notifiche). Se è spento deliberatamente, va
  scritto dove si decide; se è rotto, il fix è di quella dimensione.
- `severity_max` è calcolata sull'elenco notifiche NON filtrato (un topic spento
  con severity error la alza comunque), ma **nessun componente UI la legge**
  (solo dichiarazioni di tipo): campo morto lato client, nessun impatto.
- Il modello della narrazione è `gpt-4o-mini` fisso (non `ONEFLUX_AI_MODEL`):
  scelta economica sensata per una riscrittura di tono, annotata.
- `get_latest_briefing` serve il fast-path col flag `_stale` anche su snapshot
  di code_version vecchia: trade-off dichiarato nel codice (mai bloccare la
  Home), la rigenerazione parte subito in background.
