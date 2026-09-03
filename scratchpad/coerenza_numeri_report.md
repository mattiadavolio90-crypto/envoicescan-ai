# Verifica di quadratura dei numeri fra le pagine — report

**Data:** 03/09/2026 · **Sessione:** read-only (nessuna modifica a codice o DB)
**Prompt di riferimento:** `docs/storico/AUDIT_ONEFLUX_STATO_2026-07_PROSSIMA_SESSIONE_COERENZA_NUMERI.md`
**Perimetro eseguito:** catena OFFSIDE per intero (OFFSIDE SPORTS PUB, OVERTIME, sede
tecnica «Costi comuni di gruppo»), mesi 2026-01→08, confronti A–E; SUSHILAND (3 sedi:
sincronia ricavi, quadratura costi, «Da Classificare»); LAND DEI SAPORI (partita doppia
riparto); TIME CAFE (switch upload). Fuori perimetro dichiarato in fondo.

Ogni cifra qui sotto è stata misurata a DB in sessione (03/09), non ripresa da documenti.

---

## 0. Come le pagine ottengono i numeri (mappa dei percorsi, verificata sul codice)

| Percorso | Codice | Fonde l'override mensile? | Costi |
|---|---|---|---|
| Pagina Margini (analisi) | `services/routers/margini.py:get_margini_analisi` (riga ~1116) | ✅ `_load_mensile_overrides` (r. 1151) | RPC live |
| Home card «I tuoi conti» | `fastapi_worker.py:_merge_override_mensile` + `_kpi_periodo` (r. 7322/7347) | ✅ | live |
| Aggregatori worker (sparkline, totali) | `fastapi_worker.py:_aggrega_mensili_margini` / `_aggrega_totali_margini` (r. 8466/8526) | ✅ | live |
| Catena (overview, margini-coperti) | `services/routers/gruppo.py:_aggrega_sedi_mensili` (r. ~171) — punto unico con test | ✅ | live |
| Catena — salute/completezza | RPC `gruppo_salute_componenti` + `_applica_override_netto` (gruppo.py r. 560) | ✅ (compensata a valle) | — |
| Catena — segnale «margine in calo» | `gruppo.py:1671-1709` | ❌ **legge lo snapshot** | — |
| `/api/margini/analisi-centri` | `margini.py:get_analisi_centri` (r. ~511) | ❌ legge `fatturato_netto` snapshot | — **endpoint senza consumatori UI** |
| Briefing giornaliero | riceve il payload da `_kpi_periodo` (non ricalcola) | ✅ (eredita) | eredita |

Chiave di lettura: per i clienti in «modalità mensile» (OFFSIDE: 7 mesi; OVERTIME: 7)
il fatturato vero vive in `ricavi_modalita_mensile` e `margini_mensili.fatturato_*`
resta 0 o stantio. Ogni lettore deve fondere l'override: **tutti i percorsi vivi lo
fanno, tranne il segnale «margine in calo»** (e l'endpoint morto).

---

## A. Fatturato / ricavi del mese

- **OFFSIDE / OVERTIME**: fonte unica = override mensile; tutti i percorsi vivi la
  fondono → Home, Margini, Catena e briefing leggono gli stessi ricavi. ✅
- **Copie stantie** in `margini_mensili` (innocue finché nessun lettore le usa, ma
  misurate): OVERTIME maggio `fatturato_iva10` 35.775,84 vs override 35.864,79;
  `altri_ricavi_noiva` diverge in TUTTI i mesi 01–06; **luglio: 0,00 vs 29.889,00
  reali**. OFFSIDE: 0 su tutti i mesi (mai scritto, coerente col design).
- **SUSHILAND (3 sedi, ricavi giornalieri)**: sincronia trigger
  `sync_margini_mensili_from_ricavi` verificata mese per mese — **zero scarti** fra
  somma dei giornalieri e `margini_mensili`. ✅

Query tipo (sincronia):
```sql
SELECT ristorante_id, extract(month FROM data) AS mese,
       sum(fatturato_iva10), sum(fatturato_iva22), sum(altri_ricavi_noiva)
FROM ricavi_giornalieri WHERE extract(year FROM data)=2026 GROUP BY 1,2
-- confrontato con margini_mensili: nessuna riga in disaccordo
```

## B. Costi F&B del mese

- **Analisi Fatture ↔ Margini**: coincidono **al centesimo** su ogni mese chiuso per
  OFFSIDE e OVERTIME. Unico scarto: settembre in corso, 85,92 € «Da Classificare»
  su OFFSIDE — divergenza legittima (regola di dominio 1), visibile dal filtro.
- **Partita doppia del riparto (catena OFFSIDE)**: per ognuno dei 9 mesi ×2 sedi,
  quota da `riparto_costi_catena_quote` = `margini_mensili.quote_riparto_*`
  (**18/18, delta 0,00**), e la somma delle quote di un mese = somma di
  `totale_riga` delle fatture `ripartita_su_gruppo` della sede tecnica in quel mese
  (es. gennaio 10.272,32+6.052,88 = 16.325,20). ✅
- **LAND DEI SAPORI**: 2 righe ripartite (gennaio, 5,00+451,30 = 456,30 €) =
  quote in `margini_mensili` dell'utente (456,30 €). Nessun costo orfano. ✅

## C. Spese Generali

- Stessa triangolazione di B, quadra (le 4 categorie spese da
  `config/constants.py:CATEGORIE_SPESE_GENERALI`; food = catch-all, RPC
  `costi_automatici_mensili` allineata al percorso Python `_calcola_costi_auto_per_mese`).
- **Guardrail NOTE**: righe «📝 NOTE E DICITURE» con importo ≠ 0: **zero** su tutte
  le sedi verificate. ✅

## D. 1° Margine e MOL

Home e pagina Margini ricalcolano con la stessa formula dalle stesse fonti → coincidono
per costruzione (verificato sul codice, non solo sul commento). Le **soglie colore**
sono unificate: la tabella locale del client è stata rimossa (commento esplicito in
`calcolo-tab.tsx` r. 827), la valutazione arriva dal worker.

**Conto economico ricostruito (catena OFFSIDE, mesi con ricavi):**

| Sede | Mese | Netto | MOL vero | MOL fotografato | FC ÷lordo (Home) | FC ÷netto (Margini) |
|---|---|---|---|---|---|---|
| OFFSIDE | 01 | 55.447,73 | −9.634,24 | −21.305,32 | 41,0% | 44,6% |
| OFFSIDE | 02 | 69.178,14 | 22.714,63 | −20.662,29 | **35,9%** | **39,1%** |
| OFFSIDE | 03 | 66.161,40 | 21.735,89 | −12.176,97 | **35,7%** | **38,8%** |
| OFFSIDE | 04 | 52.812,05 | 14.285,03 | −13.172,05 | 33,0% | 35,9% |
| OFFSIDE | 05 | 58.960,23 | 23.363,12 | −12.043,83 | 28,8% | 31,4% |
| OFFSIDE | 06 | 50.145,95 | 11.765,67 | −12.440,12 | **37,2%** | **40,5%** |
| OFFSIDE | 07 | 49.462,73 | 6.613,00 | −22.567,77 | 23,5% | 25,7% |
| OVERTIME | 01 | 28.075,14 | 81,79 | +14.158,93 | 25,7% | 28,2% |
| OVERTIME | 02 | 65.771,27 | 28.398,01 | **+50.834,52** | 30,0% | 32,9% |
| OVERTIME | 03 | 37.682,05 | 9.462,02 | +27.616,98 | 32,3% | 35,5% |
| OVERTIME | 04 | 27.177,83 | −187,20 | +15.745,59 | 33,1% | 36,2% |
| OVERTIME | 05 | 34.021,50 | 10.107,79 | +24.352,03 | 24,2% | 26,5% |
| OVERTIME | 06 | 27.334,60 | 2.174,06 | +16.524,63 | 36,9% | 40,4% |
| OVERTIME | 07 | 29.105,82 | −10.274,89 | −20.668,02 | 26,1% | 28,6% |

- «MOL vero» = ricostruzione con la formula delle pagine vive (override + costi auto
  live + quote + personale). «MOL fotografato» = colonna `margini_mensili.mol`.
- **In grassetto i 3 mesi in cui il colore del food cost si ribalta** attorno alla
  soglia 38%: Home sotto, Margini sopra. Scarto ÷lordo vs ÷netto: 2,2–3,6 punti su
  tutti i 14 mesi (conferma e aggiorna la misura del 27/8 annotata in
  `fastapi_worker.py:7386-7392`).
- Agosto (entrambe le sedi): costi presenti, ricavi non ancora inseriti → MOL
  negativo «corretto ma incompleto» su tutte le pagine; il segnale «dati mancanti»
  della catena copre il caso.

## E. Catena vs somma delle sedi

Verificato a livello di formula: `_aggrega_sedi_mensili` è il punto unico condiviso da
overview e margini-coperti, stessa formula del PV, con test dedicati
(`tests/test_gruppo_aggrega_sedi.py`, incluso il caso «override vince sullo snapshot»).
Il percorso salute/completezza compensa la RPC con `_applica_override_netto`.
**Non eseguito** il confronto numerico runtime (richiederebbe di eseguire gli endpoint).
Il MEDIUM catena-tag era già chiuso e verificato a DB il 3/9 (fuori scope da prompt).

## F. Prezzi

Solo una verifica puntuale: `prezzo_medio_tag` **oggi è consumato** dal client
(`analisi-e-tag-client.tsx:1313-1324`) — il finding §25 «arriva e viene scartato» è
superato. Triangolazione completa dei prezzi NON eseguita (fuori perimetro).

---

## Findings (in ordine di peso)

1. **BUG — Segnale «margine in calo» della catena mai funzionante**
   (`services/routers/gruppo.py:1671-1709`). Legge `margini_mensili.mol_perc` con gate
   `fatturato_netto > 0`, entrambi snapshot. Misurato: `mol_perc` valorizzato solo per
   3 clienti su 9 (LAND 6/9 mesi, TIME CAFE 4/6, ambiente test) — **nessuna sede di
   catena ce l'ha**. OFFSIDE: netto snapshot 0 su tutti i mesi → tutti scartati;
   OVERTIME + 3 SUSHILAND: gate superato ma confronto 0-vs-0. Il segnale non è mai
   potuto scattare per le uniche due catene reali (i suoi unici destinatari). La
   stessa classe di bug è stata corretta in tre percorsi fratelli
   (`_aggrega_sedi_mensili`, `_applica_override_netto`, segnale «ricavi mancanti»):
   questo è l'unico rimasto indietro.

2. **DECISIONE DI PRODOTTO — food cost ÷lordo vs ÷netto.** Home/catena/briefing
   dividono per il lordo, la pagina Margini per il netto (2,2–3,6 pt di scarto; colore
   ribaltato in 3 mesi su 7 per OFFSIDE — righe in grassetto nella tabella D). Il
   codice la dichiara «decisione di prodotto» da prendere sui tre punti insieme
   (`fastapi_worker.py:7386-7392`, `gruppo.py:71`, `margini.py:273/1196/1298`).

3. **STRUTTURALE — snapshot economico di `margini_mensili` inaffidabile per
   costruzione.** Tre scrittori incoerenti: `save_margini` scrive tutto;
   `sync_margini_mensili_from_ricavi` solo fatturato+netto; la RPC
   `riparto_quote_mensili` ricalcola netto/PM/MOL **dallo snapshot, cieca
   all'override**, e non scrive mai le percentuali. Valori misurati: OVERTIME febbraio
   MOL fotografato +50.834 vs +28.398 vero; OFFSIDE febbraio −20.662 vs +22.715.
   Lettori attuali: solo il segnale del finding 1 e l'endpoint morto
   `/api/margini/analisi-centri` (0 consumatori UI) — mina per il primo che li collega.

4. **CONFLITTO DI REGOLE (minore) — tab Calcolo vs tab Analisi della pagina
   Margini.** Le quote riparto includono le righe «Da Classificare» della sede tecnica
   (deliberato, motivato in `supabase/migrations/20260724220000_riparto_quote_per_categoria.sql`);
   la proiezione per centro `_righe_quote_gruppo` le esclude (deliberato, regola 1,
   `fastapi_worker.py:8234-8240`). Divergenza fra i due tab: 13–592 €/mese (sede
   tecnica OFFSIDE, misurata mese per mese). Due regole giuste che si contraddicono:
   serve scegliere una rappresentazione.

5. **LATENTI (oggi innocui, misurati):**
   - `_calcola_costi_auto_per_mese` usa `.neq("ripartita_su_gruppo", True)`
     (NULL-unsafe: scarterebbe le righe NULL) dove la RPC usa
     `NOT COALESCE(...,FALSE)`. Oggi 0 righe NULL su 39.420 → nessuna divergenza.
   - Copie stantie del fatturato in `margini_mensili` per i clienti in modalità
     mensile (vedi §A).
   - Endpoint `analisi-centri`: morto e per giunta legge lo snapshot.

6. **Il prezzo dell'onestà, quantificato (non è un bug: è la regola 1).** Righe «Da
   Classificare» escluse dai margini ma visibili in Analisi Fatture — massimi mensili:
   SUSHILAND SAN GIULIANO giugno **3.865,55 €** (36 righe) e aprile **−2.967,61 €**
   (nota di credito non classificata → MOL sottostimato); SUSHILAND VILLA GUARDIA
   luglio 581,32 €; LAND giugno −1.595,97 €, luglio 293,61 €. Si aggancia alla fase 4
   del `docs/piani/PIANO_CATEGORIZZAZIONE.md` (delta per sede da portare a Mattia).

## Finding del ciclo 07 risultati superati (verificati oggi)

- Soglie colore MOL: unificate, la tabella locale del client è stata rimossa.
- `prezzo_medio_tag`: consumato dal client.
- Switch `blocco_mesi_precedenti`: non più morto — la regola vive in
  `services/upload_policy.py`, applicata dal worker, con test.

## Riepilogo per sede

| Sede | Verdetto |
|---|---|
| OFFSIDE SPORTS PUB | ✅ quadra, modulo la decisione lordo/netto (finding 2) e agosto senza ricavi inseriti |
| OVERTIME | ✅ quadra (idem); copie stantie in `margini_mensili` documentate |
| Sede tecnica gruppo | ✅ riparto in partita doppia perfetta; conflitto tab Calcolo/Analisi (finding 4) |
| SUSHILAND ×3 | ✅ quadra; «Da Classificare» pesa fino a 3.865 €/mese (finding 6); segnale catena mai attivo (finding 1) |
| LAND DEI SAPORI | ✅ riparto 456,30 € in pareggio |
| TIME CAFE | ✅ switch upload riparato; non ripassata per intero (fuori perimetro) |

## Fuori perimetro (dichiarato)

Triangolazione Prezzi completa (F); CASATI 14 (caso coperto by-design dal merge
override — citato nel docstring di `_merge_override_mensile`); confronto numerico
runtime catena-vs-somma-sedi; Edge Functions; qualunque fix. **La remediation è una
decisione di Mattia, in sessioni separate.**
