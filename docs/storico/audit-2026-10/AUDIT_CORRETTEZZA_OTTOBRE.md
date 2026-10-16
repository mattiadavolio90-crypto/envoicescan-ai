# Audit di correttezza — ottobre 2026

**14-15/10/2026** · audit in sola lettura sulle funzioni che producono numeri, permessi e risposte dell'assistente, concentrato su ciò che è cambiato dopo le lenti L1-L9 (14-17/09/2026): 440 commit dal 14/09.

**Per chi è.** Per Mattia, che decide quali fix fare e in che ordine, e per le sessioni che faranno i fix: ogni scheda contiene file, righe, fix proposto e test che impedirebbe al difetto di tornare.

## In una pagina

**40 difetti confermati da un secondo agente, nessuno smentito.** Uno solo è grave: l'archivio «Per mese» di Gestione Fatture somma le note di credito come se fossero fatture, su 5 account su 6.

| Esito | Quanti |
|---|---|
| Difetti confermati | 40 |
| — gravità alta | 1 |
| — gravità media | 17 |
| — gravità bassa | 22 |
| Falsi allarmi verificati e scartati | 8 |
| Incerti | 2 |

Per tipo: 28 sono bug veri, 9 sono «stessa parola per due numeri diversi» (si risolvono con un'etichetta, non toccando il calcolo), 3 sono periodi non dichiarati a video.

**Quello che conta sapere:**

- **I numeri di fondo tornano.** Costi automatici, MOL, food cost, note di credito nei margini, righe «Da Classificare» fuori dai margini: ricalcolati da SQL indipendente su quattro account, coincidono al centesimo con la funzione del DB e col codice delle pagine.
- **I difetti stanno nei bordi.** Un totale d'archivio che non sottrae le note di credito, un mese dichiarato «completo» da 100 € inseriti a mano, la stessa parola «Fatturato» per lordo e netto, una chat a cui si chiede di dividere per il lordo.
- **Sotto-utenti: nessuna falla di isolamento.** I difetti trovati hanno platea zero oggi, perché in produzione non c'è ancora nessun sotto-utente; sono da chiudere prima che arrivi il primo.
- **La chat manda a OpenAI nomi di fornitori, prodotti e referente** mentre `SICUREZZA_GDPR.md` §8 dichiara un'anonimizzazione che esiste solo nel briefing. Si corregge il codice o il documento: è una decisione di Mattia.

## Come è stato fatto

| Fase | Agenti | Modello | Cosa |
|---|---|---|---|
| 0 — ambiente e mappe | 3 esploratori | Fable 5.1 | delta git dal 14/09, lettura di `INDICE_LENTI_L1_L9.md`, `AUDIT_COPERTURA.md`, `AUDIT_BILANCIO_LUGLIO_SETTEMBRE.md`, `COERENZA_VISIVA_ANALISI_CARICO.md`; mappa file:riga dei quattro filoni |
| Trova | 9 finder + 1 critico | Fable 5.1 (6), Opus (3 su codice) | quattro account reali, max 4 agenti sul DB insieme |
| Verifica | 11 | Opus (10), Fable (contraddizioni) | ogni difetto rivisto da un agente diverso da chi l'ha trovato |

- **Account usati, per ID.** Catena A `51015cc8-078c-4e92-86b4-113e62e16d38` (5 sedi, 2.582 documenti), catena B `2f3f93a1-c1f4-4804-858e-a161e6f36f3f` (3 sedi più una tecnica, alimentata fino al 13/10), sede singola viva `79920814-082f-4d93-bf64-54bafbfbb708`, sede singola ferma da luglio `802967b0-2aed-40f0-8d42-81076f44bb17`.
- **Sola lettura.** Ogni query è stata eseguita dentro `BEGIN READ ONLY; …; COMMIT;`, provato all'inizio con `transaction_read_only = on`. Le funzioni del DB sono state chiamate solo dopo averne letto il corpo. Nessun endpoint del worker o di Vercel è stato chiamato, nessuna chiamata a OpenAI.
- **Seconda verifica.** I 5 difetti nati come gravi hanno avuto un agente ciascuno, codice più misura a DB. I medi sono stati verificati a lotti per area. I difetti trovati in modo indipendente da 2-4 finder diversi hanno avuto solo un controllo di stato a HEAD e di gravità: la convergenza vale già come seconda verifica.
- **Costo.** Fase Trova 2,42 milioni di token, fase Verifica 1,13 milioni. Due avvii precedenti della verifica, a 38 agenti, sono stati fermati prima di lavorare: il primo per un errore nello script, il secondo per la chiusura della sessione.

## Le discrepanze di settembre: com'è oggi

Il documento `DOCUMENTAZIONE/COERENZA_VISIVA_ANALISI_CARICO.md` del 16/09 elencava otto numeri che non tornavano sulla catena A. Ricontrollati uno per uno.

| Discrepanza del 16/09 | Oggi | Prova |
|---|---|---|
| «Costi gestione» 151.211 € nel riquadro, 511.211 € in tabella | **Risolta.** L'etichetta non esiste più: il riquadro dice «Spese Generali», la riga combinata dice «− Spese Generali + Personale» | grep su `apps/web/src`: solo commenti e demo |
| «Scadute 641.555 €» contro «Da pagare 430.340 €» | **Non più possibile.** Scadute più senza scadenza è uguale a Da pagare al centesimo (sede `cc016821`: 665.885,04 + 118.339,56 = 784.224,60). Il 430.340 di allora non è ricostruibile: i dati sono cambiati | SQL con le regole di `computeKpi` |
| Contatore «426 su 581» | **Risolta.** Contatore e «Seleziona tutte» usano la stessa popolazione: oggi 563 e 563 | presidio `test_scadenziario_contatore_frontend.py` |
| Home «447.728 − 0 − 0 − 0 = 416.798» | **Ancora così.** La card mette il fatturato lordo IVA sopra un MOL calcolato sul netto, senza dirlo | difetto `K07` |
| Margine 39% / 68% / 100% su tre pagine | **Periodi ora dichiarati.** Home dice il mese, catena dice «gen-ott (parziale)», Margini dice «Nessun giudizio» quando mancano costi. Resta la card MOL verde sopra quel «Nessun giudizio» | difetto `K10` |
| «2.582 fatture totali» contro «Seleziona tutte (2.545)» | **Risolta.** Oggi contatore e «Seleziona tutte» danno entrambi 2.437 nella vista gruppo | contraddizione sciolta, vedi sotto |
| «101 prodotti / 19.050 €» contro «100 / 582 €» | **Tre popolazioni con etichette simili**: prodotti da controllare, euro esclusi dai margini, chip «Solo da verificare». Il «582 €» della Home oggi non è reso da nessun componente | difetto `F1a-06`, bassa |
| «Media periodo 7,66 €» contro «Prezzo medio 7,83 €» | **Due formule diverse**: media semplice dei prezzi del giorno contro media pesata sulla spesa | difetto `F1a-07`, bassa |

Dei punti che il documento lasciava «da verificare»: la sede mai avviata della catena A ha la card vuota e resta fuori dal ranking, quindi non abbassa la media del gruppo. Il prezzo anomalo a −97,1% e la pagina Prezzi **non** sono stati riguardati in questo audit.


## I difetti confermati, dal più grave

La tabella riassuntiva per gravità è in fondo. Ogni scheda riporta la prova di chi ha trovato il difetto e quella, indipendente, di chi lo ha verificato. Le prove complete dei finder stanno in `allegati/FINDING_COMPLETI.md`.

### 1. Archivio «Per mese»: le note di credito sono sommate come fatture

`K01` · trovato da F1e-07, F1c-03, F1d-01, F4-08

| | |
|---|---|
| Filone | 1 — Quadrature numeriche + 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **alta** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Gestione Fatture (sede) e Catena → Fatture (riusa ScadenziarioClient), vista `lista_mensile`: intestazione di ogni mese con «N» documenti e «X €». Tutti gli account con NC o fatture escluse.

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `79920814-082f-4d93-bf64-54bafbfbb708`, `802967b0-2aed-40f0-8d42-81076f44bb17`

**Platea misurata in verifica.** Il difetto delle note di credito tocca 5 account su 6 con dati: 149 note di credito, tutte mostrate con importo positivo (nessuna negativa), per 44.897,89 EUR. Per account: 51015cc8 106 NC, 37.453,54 EUR; 2f3f93a1 27, 4.817,30; 802967b0 12, 2.105,60; 79920814 2, 474,10; 080004f3 2, 47,35; a8094f9a 0. Rispetto al netto lo scarto e' 2 x 44.897,89 = 89.795,78 EUR, su 25 mesi-sede toccati. Per account i mesi toccati sono 7/7, 9/10, 5/7, 2/8 e 2/5. La sovrastima massima di un'intestazione di mese e' 13,4% (79920814), 10,7% (802967b0), 5,1% (2f3f93a1), 2,7% (51015cc8) e 0,9% (080004f3). Il caso «escluse dentro il totale» ha oggi 1 solo documento, 382,83 EUR, sull'account 080004f3. Le pagate sono 564 documenti, ma la loro inclusione e' deliberata.

**Atteso contro mostrato.** Dataset sintetico: mostrato «4 documenti · 2.600 €»; atteso 1 / 1.100 € (solo aperte) o 800 € (nettizzando la NC) a seconda della definizione, mai 2.600.

**Prova del finder.** Eseguito con node lib/scadenziario.ts su 4 documenti (NC 300 €, esclusa 500 €, pagata 700 €, aperta 1.100 €): documentiCalendario = filtraDocumenti(periodo «tutti») include l'esclusa (scadenziario-client.tsx:1775-1783; matchDocumento :692 salta i filtri di stato con «tutti»); raggruppaPerMeseFattura (lib :840-876) non esclude nulla → intestazione «4 / 2.600 €» (client :285 `docs.reduce(totale_documento)`, :308 `{docs.length}`, :313 formatEuro(totale)). Il segno: totale_documento viene da fatture_documenti.totale_documento = ImportoTotaleDocumento dell'XML (documenti_service.py:810-813; invoice_service.py:872-875), positivo anche per TD04: l'inversione di segno (invoice_service.py:1015+) tocca solo le righe. Con solo le aperte sarebbe 1 / 1.100; nettizzando la NC 800.

**Prova indipendente della verifica.** Codice a HEAD (ultimo commit sui file citati: 4e44c781 del 09/10): l'intestazione del mese in AgendaSection fa `docs.reduce((s,d)=>s+(d.totale_documento||0),0)` e raggruppaPerMeseFattura calcola `totale` nello stesso modo. Nessuno dei due guarda is_nota_credito o oscurata. In lista_mensile gruppiMensili viene da documentiCalendario, cioe' filtraDocumenti con periodo «tutti», che non esclude nulla. La riga del documento mostra formatEuro(totale_documento) senza segno e senza badge per le note di credito.

Riproduzione mia con node (esegui_ts su lib/scadenziario, TZ Europe/Rome): fattura 300, NC 100, pagata 700 ed esclusa 500, tutte nello stesso mese. Esce count 4 e totale 1600, quindi la NC e' sommata.

Origine del segno: get_documenti_scadenziario usa fatture_documenti.totale_documento quando c'e' ed e' diverso da 0, altrimenti la somma delle righe. Ho letto il corpo live di scadenziario_fatture_aggregate con pg_get_functiondef: somma totale_riga, non filtra oscurata, non inverte il segno.

Query SQL mia in sola lettura, che ricostruisce l'importo mostrato documento per documento su tutti gli account: tutte le 149 note di credito hanno l'importo mostrato maggiore di 0. Per 51015cc8 le note di credito valgono 37.453,54 EUR e lo scarto e' 74.907,08 EUR, le stesse cifre di F1d-01.

Il test tests/test_scadenziario_vista_mensile_frontend.py passa (15 passed) ma usa solo documenti con is_nota_credito=False e oscurata=False, quindi resta verde col bug: il difetto non e' presidiato.

**Correzioni della verifica.** 1) Il nucleo e' confermato: nell'intestazione del mese le note di credito sono sommate col segno positivo. Lo stesso vale per la riga, che non ha segno ne' badge NC (F4-08). La platea va letta su tutti gli account: 5 su 6, 44.897,89 EUR di NC e 89.795,78 EUR di scarto rispetto al netto. Non e' solo C+D (F1c-03) ne' A+C (F1d-01).

2) Va RIMOSSA dal perimetro la parte «pagate incluse». E' una scelta deliberata e dichiarata a video: il testo d'aiuto della pagina dice «Archivio fatture = tutte le fatture per mese di emissione, senza scadenze: serve per consultarle, non per pagarle». Il «debito aperto» non e' la grandezza di quella vista. L'atteso «1 / 1.100 solo aperte» di F1e-07 e il «debito aperto 0,00» di F1c-03 sono quindi refutati.

3) Le escluse sono un caso dubbio, non un bug confermato. La migration 20260912075621_oscura_fattura.sql dice che la lista di Gestione Fatture deve continuare a mostrarle e che scadenziario_fatture_aggregate e' deliberatamente non filtrata. Pero' la stessa regola dice «chi conta soldi filtra oscurata=false», e il totale del mese conta soldi: e' un problema di etichetta, oggi su 1 solo documento da 382,83 EUR.

4) Gravita' alta, perche' e' un numero sbagliato a video su clienti reali oggi. L'effetto relativo pero' e' contenuto, dallo 0,9% al 13,4% di un'intestazione mensile, e riguarda un subtotale d'archivio, non un KPI. Se il criterio fosse l'impatto sulle decisioni, la gravita' sarebbe media.

5) Il presidio vero e' un test node: una fattura da 300 e una NC da 100 nello stesso mese devono dare 200, non 400.

**Deliberato dove.** Pagate incluse: e' deliberato, nel testo d'aiuto di apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx alla riga 2140 («Archivio fatture = tutte le fatture... serve per consultarle, non per pagarle»). Escluse presenti nella lista: deliberato nella migration supabase/migrations/20260912075621_oscura_fattura.sql, righe 18-20 e 53-55. Il segno positivo delle note di credito non e' deliberato da nessuna parte: la vista Scadenzario le mette in un bucket noteCredito a parte, l'Archivio no.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1775-1783`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:201-205`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2046-2049 (gruppiMensili da documentiCalendario: nessuna esclusione)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2047`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2515-2535 (ramo lista_mensile)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2516-2520`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2516-2535 (vista lista_mensile usa gruppiMensili senza filtro)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:284-285`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:284-285 (AgendaSection: totale = docs.reduce)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:285`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:285-308 (AgendaSection: totale = docs.reduce, badge docs.length)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:308`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:313`
- `apps/web/src/lib/scadenziario.ts:840-876`
- `apps/web/src/lib/scadenziario.ts:840-887 (raggruppaPerMeseFattura: nessuna esclusione, totale = somma di tutti i docs)`
- `apps/web/src/lib/scadenziario.ts:875`
- `apps/web/src/lib/scadenziario.ts:875-876 (totale = somma di tutti i totale_documento)`
- `services/documenti_service.py:159`
- `services/documenti_service.py:788-791`
- `services/documenti_service.py:808-814 (totale = header, lordo IVA)`
- `services/documenti_service.py:810-813`
- `services/documenti_service.py:810-816 (totale_documento preferisce fatture_documenti, positivo anche per TD04)`
- `services/invoice_service.py:872-875`

**Fix proposto (non applicato).** In raggruppaPerMeseFattura sottrarre le NC, cioe' totale -= totale_documento quando is_nota_credito; in alternativa mostrarle a parte. AgendaSection deve leggere g.totale invece di rifare la somma nel .tsx. In DocumentoRow mostrare il badge NC e l'importo col segno meno. Per le escluse: lasciarle fuori dal totale del mese, oppure dichiarare «comprese le escluse».

**Presidio di test proposto.** Estendere tests/test_scadenziario_vista_mensile_frontend.py con un TD04 (is_nota_credito True, 100) accanto a un TD01 da 300 nello stesso mese: atteso 200. Mutante: tornare a `s + d.totale_documento` deve far fallire il test. Se si decide di escludere le oscurate, un secondo caso con oscurata True.

**Già presidiato da.** Nessun presidio sul segno. tests/test_scadenziario_vista_mensile_frontend.py, eseguito oggi con 15 passed, fissa solo documenti TD01 positivi e non oscurati: verde sul bug.

---

### 2. Spesa per PV (catena): la fattura ripartita che vive su un PV e' contata intera E come quote → 456,30 € doppi

`F1a-02` · trovato da F1a-02

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Catena → finestra «Spesa per PV» (gruppo_spesa_pivot + _righe_quote_gruppo), colonna del PV fd7ac484 e grand total, periodo che include gennaio 2026; Analisi Fatture del PV fd7ac484 (righe reali 456,30 + riga proiettata quota 114,08).

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `fd7ac484-b562-498d-a6d1-00c4c6fd09dd`

**Platea misurata in verifica.** 1 account, 2 righe ripartite su un PV non tecnico, 456,30 EUR contati due volte nel pivot di gennaio 2026.

**Atteso contro mostrato.** Gen 2026, PV fd7ac484: atteso SERVIZI 5.970,70 + quota 1,25 e UTENZE 33.798,69 + quota 112,83; mostrato 5.975,70 + 1,25 e 34.249,99 + 112,83 (grand total +456,30).

**Prova del finder.** L'account non ha una sede tecnica (ristoranti.sede_tecnica = false su tutte e 5). L'unico riparto (riparto_costi_catena gen 2026, importo 456,30, origine fattura IT08172050968_0ofr3.xml.p7m) ha le 2 righe (5,00 SERVIZI + 451,30 UTENZE) su fatture con ristorante_id = fd7ac484 e ripartita_su_gruppo = true; quote: 4 PV × (1,25 + 112,83) = 456,30. RPC gruppo_spesa_pivot (corpo live letto con pg_get_functiondef: nessun filtro su ripartita_su_gruppo) chiamata per gen 2026 sui 4 PV: fd7ac484 SERVIZI 5.975,70 e UTENZE 34.249,99; stessa somma senza righe ripartite: 5.970,70 e 33.798,69 (delta 5,00 + 451,30). gruppo.py:1448-1461 aggiunge poi le quote (114,08 per PV) → il grand total porta 456,30 due volte. costi_automatici_mensili (margini/Home) invece esclude le ripartite: li' e' corretto.

**Prova indipendente della verifica.** SQL READ ONLY: righe fatture attive con ripartita_su_gruppo=true su ristoranti con sede_tecnica=false = 2, somma 456,30. pg_get_functiondef: gruppo_spesa_pivot NON contiene 'ripartita' (costi_automatici_mensili si'). gruppo.py:1444-1461 aggiunge poi le quote di _righe_quote_gruppo per ogni PV.

**Correzioni della verifica.** Gravita' media invece di bassa: e' un numero sbagliato a video su un cliente reale oggi, ma di 456,30 EUR su un totale mensile di decine di migliaia.

**File e righe.**

- `services/fastapi_worker.py:10437-10448 (_build_fatture_base_query: nessun filtro ripartita) e :10608-10625 (proiettate aggiunte)`
- `services/routers/gruppo.py:1444-1461 (_righe_quote_gruppo aggiunte dopo la RPC)`
- `supabase/migrations/20260912075621_oscura_fattura.sql:360-380 (gruppo_spesa_pivot senza NOT ripartita_su_gruppo)`

**Fix proposto (non applicato).** Aggiungere `AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)` in gruppo_spesa_pivot (e verificare gruppo_peso_categoria / gruppo_spreco_fb_categorie, stessa famiglia `totale_riga > 0`, non controllate qui); in Analisi Fatture del PV che ospita la fattura ripartita, escludere le righe reali quando esistono le proiettate (o marcare la riga come «ripartita, conteggiata via quota»).

**Presidio di test proposto.** Test -m sql: fattura con ripartita_su_gruppo = true su un PV + quote sui PV → gruppo_spesa_pivot non la ritorna; mutante: togliere il filtro → rosso.

**Già presidiato da.** tests/test_gruppo_spesa_pivot_quote.py assume la fattura sulla sede tecnica.

---

### 3. 19 header fatture_documenti senza righe (dic 2025, 59.368 €) fanno comparire «Dicembre 2025 (19 fatture)» nel filtro periodo di Analisi Fatture su un mese che non ha righe

`F1a-04` · trovato da F1a-04

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Analisi Fatture → filtro periodo «mese specifico» (filtri-periodo.tsx:131 «{label} ({count} fatture)») del PV fd7ac484; lo scadenziario non li mostra (RPC su fatture).

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `fd7ac484-b562-498d-a6d1-00c4c6fd09dd`

**Platea misurata in verifica.** 1 sede, 19 header fatture_documenti senza righe, 59.368,37 EUR (dicembre 2025).

**Atteso contro mostrato.** Atteso: nessun «Dicembre 2025» nel filtro (0 righe). Mostrato: «Dicembre 2025 (19 fatture)».

**Prova del finder.** fatture_documenti attivi dell'account: 2.601; documenti distinti in fatture attive: 2.582. I 19 in piu' sono tutti di fd7ac484, data_documento 09–31/12/2025, totale_documento 59.368,37 €, e NON hanno nessuna riga in fatture (nemmeno soft-deleted: con_righe_cancellate = 0); min(data_documento) delle righe di fd7ac484 = 01/01/2026. /api/fatture/mesi-disponibili (routers/fatture.py:326-360) conta fatture_documenti → lista «Dicembre 2025, 19»; selezionandolo /api/fatture/kpi e articoli (su fatture) tornano vuoti.

**Prova indipendente della verifica.** SQL READ ONLY: fatture_documenti attivi senza alcuna riga in fatture (stesso user_id+file_origine) = 19, totale_documento 59.368,37. HEAD routers/fatture.py:326-360: mesi-disponibili conta fatture_documenti, non fatture.

**Correzioni della verifica.** Gravita' media: un mese con conteggio '19 fatture' a video porta a pagine vuote su un cliente reale oggi. Da capire anche perche' esistano 19 header senza righe (sintomo a monte, forse import parziale).

**File e righe.**

- `apps/web/src/app/(app)/analisi-fatture/filtri-periodo.tsx:131`
- `services/routers/fatture.py:326-360 (get_mesi_disponibili su fatture_documenti)`

**Fix proposto (non applicato).** Costruire i mesi disponibili dalle righe (fatture, deleted_at IS NULL) o da una JOIN con fatture; e capire perche' 19 header di dicembre sono rimasti senza righe (upload interrotto dopo l'insert dell'header?) — eventuale pulizia e' una scrittura, fuori da questo audit.

**Presidio di test proposto.** Test su get_mesi_disponibili con un header senza righe: il mese non compare (o compare con count 0); mutante: tornare a contare fatture_documenti → rosso.

**Già presidiato da.** Nessuno.

---

### 4. Home: pochi euro manuali in altri_costi_fb rendono «completo» un mese senza fatture

`K03` · trovato da F1a-01

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Home «I tuoi conti» (desktop e /m/briefing, stesso KpiBlock) della sede 0dca4d1f-0caa-419a-b869-25bd98f424e1, mese mostrato oggi = Settembre 2026 (ultimo mese completo, worker:9926-9935). Anche la tabella Margini della stessa sede: la colonna Set non e' «senza costi» (meseSenzaCosti) e _mesi_senza_costi conta 4 mesi su 10 invece di 5.

**Clienti coinvolti (ID).** `0dca4d1f-0caa-419a-b869-25bd98f424e1`, `51015cc8-078c-4e92-86b4-113e62e16d38`

**Platea misurata in verifica.** Un solo caso in tutto il DB. Query mia su margini_mensili, tutti gli account, mesi chiusi prima del 01/10/2026: lordo > 0, F&B automatico ricalcolato dalle fatture = 0 (stessi filtri dell'RPC costi_automatici_mensili: deleted_at NULL, non oscurata, non Da Classificare, non ripartita_su_gruppo, categorie diverse da spese e NOTE) e altri_costi_fb + quote_riparto_fb > 0. Risultato: 1 riga, user 51015cc8, sede 0dca4d1f, 2026/9, lordo 414.392,23, netto 386.299,74, manuale 100,00, quote 0, auto 0, food cost 0,03%. Settembre 2026 è proprio il mese che la Home mostra oggi, 15/10, come ultimo mese completo. Le altre 3 sedi dello stesso account (5444e918, cc016821, fd7ac484), stesso mese, hanno manuale 0, auto 0 e 0 righe di fattura a settembre: per loro costi_mancanti è true. La sede 0dca4d1f ha l'ultima fattura al 30/06/2026 e 0 righe a settembre.

**Atteso contro mostrato.** Atteso: MOL giallo con banner «Mancano le fatture costo di settembre» (come le altre 3 sedi). Mostrato (dedotto dal codice): MOL 386.200 € in verde, Food cost 0%, nessun banner.

**Prova del finder.** margini_mensili 2026/9 sede 0dca4d1f: fatturato_iva10 309.017,38 + altri 105.374,85 (lordo 414.392,23, netto 386.299,74), costi_fb_auto live (RPC costi_automatici_mensili) = nessuna riga per settembre (ultima fattura 30/06), altri_costi_fb = 100,00 (updated_at 06/10), spese 0, personale 0. _kpi_periodo (worker:9798-9868): fb = 0 + 100 + 0 = 100 → costi_mancanti = (414.392 > 0 and 100 <= 0) = False; has_data True; food_cost_pct = round(100/386.299,74*100,1) = 0,0; mol = 386.199,74 (100,0%). tintContiPV (lib/catena-confronti.ts:371-381): costi_mancanti false, incasso_fuori_norma assente → «verde». Il banner «Mancano le fatture costo» (kpi-block.tsx:101-114) e' condizionato a kpi.costi_mancanti → non appare. Le altre 3 sedi, stesso mese, stessa assenza di fatture ma altri_costi_fb = 0 → costi_mancanti true, giallo + banner. La voce Salute «Fatture caricate» (_costi_automatici_mese, worker:8458) guarda i soli costi AUTO → per la stessa sede e lo stesso mese dice che manca la merce: la stessa pagina si contraddice.

**Prova indipendente della verifica.** 1) Codice a HEAD, fastapi_worker.py:9819-9866, nessun commit successivo lo tocca: fb = auto + altri_costi_fb + quote_riparto_fb e costi_mancanti = fatturato > 0 and fb <= 0. Ho estratto _kpi_periodo con ast e l'ho eseguita da sola, senza client. Con iva10 309.017,38, altri ricavi 105.374,85 e altri_costi_fb 100 restituisce costi_mancanti False, food_cost_pct 0.0, mol 386.199,74. Con altri_costi_fb 0 restituisce costi_mancanti True. 2) tintContiPV (catena-confronti.ts:369-379): con costi_mancanti false e mol >= 0 il risultato è «verde». Il banner di kpi-block.tsx:101 dipende da kpi.costi_mancanti, quindi qui non compare. 3) _costi_automatici_mese (worker:8458-8499) restituisce solo cfb dall'RPC, senza altri_costi_fb né quote. La Salute dice quindi «manca la merce» per lo stesso mese che il KPI dà per completo: la contraddizione sulla stessa pagina c'è davvero. 4) Deliberato solo in parte. Il commit a7d32625 del 23/09, decisione di Mattia, fa guardare la soglia ai soli costi F&B e considera le quote di riparto F&B come mese completo. Non dice niente sul F&B manuale minuscolo e non decide che Salute (solo automatico) e KPI (automatico + manuale + quote) debbano divergere. Anzi, il commento di _costi_automatici_mese sostiene che Salute e KPI «non si contraddicono mai», e questo è falso. 5) Presidio: tests/test_margini_giudizio_dati_incompleti.py e tests/test_margini_mese_senza_costi_frontend.py usano sempre altri_costi_fb = 0.0. Nessun test copre un F&B manuale piccolo né l'allineamento fra Salute e KPI.

**Correzioni della verifica.** 1) Gravità da alta a media. Il caso è uno solo in tutto il DB (1 sede, 1 mese) e nasce da un importo F&B inserito a mano, non da un calcolo sbagliato: il MOL mostrato è quello che dicono i dati, manca solo l'avviso. Va detto che è visibile oggi sulla Home di un cliente reale, con food cost 0,0% e MOL verde. 2) Il difetto centrale non è la soglia assoluta ma la divergenza fra le gemelle: _costi_automatici_mese (Salute e avviso) conta solo l'automatico, mentre _kpi_periodo, _mesi_senza_costi (su costi_fb_totali) e meseSenzaCosti contano anche manuale e quote. Il commento del 23/09 che le dichiara allineate è falso. La stessa divergenza vale anche per quote_riparto_fb, che la Salute non conta: platea non misurata qui. 3) Il fix con una soglia relativa (es. 5% del netto) è una decisione di dominio nuova di Mattia e non va presentato come allineamento. In alternativa si possono allineare le quattro gemelle sullo stesso predicato. 4) Il valore di 100,00 € manuali (updated_at 06/10 03:08, aggiornato in blocco con le altre sedi) potrebbe essere un segnaposto o una prova del cliente: da chiarire con Mattia prima di trattarlo come dato vero.

**Deliberato dove.** Commit a7d32625 (23/09/2026, «114 EUR di utenze dichiaravano completo un mese senza merce»), con i commenti in fastapi_worker.py:9859-9865, routers/margini.py:921-931 e margini-aggregati.ts:254-259: è deliberato che la soglia guardi i soli costi F&B e che le quote di riparto F&B completino il mese. Non è deliberato che un F&B manuale qualunque, anche di 100 € su 386.000 €, completi il mese, né che la Salute escluda manuale e quote.

**File e righe.**

- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:72-114`
- `apps/web/src/lib/catena-confronti.ts:371-381 (tintContiPV)`
- `apps/web/src/lib/margini-aggregati.ts:256-259 (meseSenzaCosti)`
- `services/fastapi_worker.py:8458-8500 (_costi_automatici_mese, solo auto)`
- `services/fastapi_worker.py:9798-9868 (_kpi_periodo, costi_mancanti = fatturato > 0 and fb <= 0 con fb che include altri_costi_fb)`
- `services/routers/margini.py:921-934 (_mesi_senza_costi su costi_fb_totali)`

**Fix proposto (non applicato).** Prima la decisione di dominio di Mattia: il F&B manuale completa il mese sempre, solo sopra una soglia relativa al netto, o mai. Poi le quattro gemelle si muovono insieme: _kpi_periodo.costi_mancanti, _mesi_senza_costi, meseSenzaCosti e _costi_automatici_mese. Oggi quest'ultima esclude manuale e quote mentre le altre tre li includono.

**Presidio di test proposto.** Un caso che separa i due mondi, da eseguire su tutte e quattro le gemelle: riga con ricavi 414.392, auto 0, altri_costi_fb 100, con l'esito atteso secondo la decisione presa. Un test di coerenza che, sulla stessa riga, verifichi che Salute (_costi_automatici_mese) e KPI (costi_mancanti) diano lo stesso verdetto. Da provare per mutazione su ciascuna gemella.

**Già presidiato da.** Nessun test copre il caso. tests/test_margini_giudizio_dati_incompleti.py e tests/test_margini_mese_senza_costi_frontend.py fissano sempre altri_costi_fb a 0.0.

---

### 5. Card MOL di Margini verde sopra «Nessun giudizio»

`K10` · trovato da F1e-03

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Ricavi e Margini, KpiBar in cima alla pagina (sede). La Home, sullo stesso mese, mette il MOL in giallo via tintContiPV. Tutti gli account con un mese a ricavi senza fatture merce.

**Platea misurata in verifica.** Stima a DB del 15/10/2026 (fatturato da ricavi_modalita_mensile/margini_mensili, F&B = righe fatture non spese e non NOTE + altri_costi_fb + quote_riparto_fb, anno 2026, mesi 1-10): 6 sedi hanno almeno un mese con ricavi e F&B a zero. Sono 5444e918 (mesi 1,2,7,8,9,10), cc016821 (1,2,8,9,10), 0dca4d1f (1,2,7,8,10), e6743667 (3,4,5,6), fd7ac484 (8,9,10) e 09011cdd (10). Per queste, su un periodo che include quei mesi, il gauge dice «Nessun giudizio» mentre la card MOL e' verde se il MOL e' >= 0. Le sedi 86300227, bdda08d1, dcf1996e e f16aebe5 risultano a 0.

**Atteso contro mostrato.** Mese con ricavi 50.000 e costi F&B 0: card MOL verde; gauge sotto «Nessun giudizio: mancano costi»; Home sullo stesso mese MOL giallo.

**Prova del finder.** kpi-bar.tsx:208 `const molTone: Tone = kpi.mol >= 0 ? "positivo" : "negativo"`; il tipo KpiData (kpi-bar.tsx:9-28) e MarginiKpiResponse (margini.py:1463-1480) non hanno nessun campo costi_mancanti/mesi_senza_costi: il client non può saperlo. _mesi_senza_costi ha un solo chiamante, get_margini_analisi (margini.py:1403), che sostituisce il giudizio con «Nessun giudizio» (:941,:954). Per confronto tintContiPV eseguita con node: {mol:1300,costi_mancanti:true} → giallo; la KpiBar non ha quel ramo.

**Prova indipendente della verifica.** HEAD (ultimo commit sui file citati: c5b4b8ac del 14/10, che non tocca kpi-bar) mostra kpi-bar.tsx:208 `const molTone: Tone = kpi.mol >= 0 ? "positivo" : "negativo"`. KpiData non ha nessun campo costi_mancanti/mesi_senza_costi. get_margini_kpi (margini.py:1492) usa _aggrega_mensili_margini (fastapi_worker.py:11006), che conta solo mesi_attivi e non i mesi senza F&B. _mesi_senza_costi ha come unico chiamante get_margini_analisi (margini.py:1403). lib/kpi-margini-tab.ts PER_TAB.calcolo = [Fatturato Netto, Margine Lordo, MOL], quindi la card MOL appare proprio nel tab Marginalita', lo stesso del gauge «Nessun giudizio» e della tabella. Lì valueColorCls(…, incompleto) spegne gia' il verde, con un commento che cita la contraddizione «a 400px di distanza» (calcolo-tab.tsx:107-115). Il gate esiste per tabella e gauge ma non per la KpiBar: non e' una scelta deliberata, e' una dimenticanza dello stesso fix.

**Correzioni della verifica.** Nessuna correzione sostanziale. Va precisato che la card MOL appare solo nel tab «calcolo» (Marginalita'), cioe' nello stesso tab del gauge: la contraddizione e' sulla stessa schermata. Platea misurata: 6 sedi con almeno un mese 2026 a ricavi e F&B zero.

**File e righe.**

- `apps/web/src/app/(app)/margini/kpi-bar.tsx:208`
- `apps/web/src/app/(app)/margini/kpi-bar.tsx:9-28`
- `apps/web/src/lib/catena-confronti.ts:369-379`
- `services/routers/margini.py:1403`
- `services/routers/margini.py:1463-1480`
- `services/routers/margini.py:921`

**Fix proposto (non applicato).** Come proposto dal finder: get_margini_kpi espone mesi_senza_costi (riusando _mesi_senza_costi o la stessa soglia fb<=0 sui mesi con netto>0) e la KpiBar sceglie il tono con una funzione in lib, che torna neutro o incerto quando il valore e' > 0.

**Presidio di test proposto.** Test node sulla funzione di tono (mutante: togliere il ramo dei mesi senza costi) e test worker su get_margini_kpi con un mese a ricavi e F&B zero.

**Già presidiato da.** Nessun presidio sul tono della KpiBar. test_kpi_margini_tab_frontend.py copre solo la selezione delle tessere; il gate «Nessun giudizio» e' presidiato solo su get_margini_analisi.

---

### 6. Home della sede ferma mostra un mese a incasso zero

`K13` · trovato da F1c-01

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Home desktop (card «I tuoi conti», kpi-block.tsx) e /m/briefing (stesso fetchKpi+KpiBlock) dell'account D = user 802967b0-2aed-40f0-8d42-81076f44bb17 / sede 86300227-53c3-4193-9b45-761b3654e889. C non e' toccato (settembre ha incasso).

**Clienti coinvolti (ID).** `802967b0-2aed-40f0-8d42-81076f44bb17`, `86300227-53c3-4193-9b45-761b3654e889`

**Platea misurata in verifica.** Misurato il 15/10/2026 su tutte le sedi: ricostruito il mese scelto da home_kpi, cioe' il primo mese da settembre all'indietro con fatturato>0 o fb>0 o spese>0 o personale>0. Due sedi mostrano oggi un mese a incasso zero. (1) 86300227 (user 802967b0): Luglio, con fatturato 0, fb 0, spese 89,08 e personale 0; agosto e settembre non hanno righe in margini_mensili ne' costi. (2) 09011cdd (user 080004f3): Agosto, con fatturato 0, fb 234,33, spese 460,43 e MOL circa −694,76. Per questa il confronto non scatta (luglio vuoto); e' una sede che non ha mai inserito incassi tranne 1.050 € in ottobre (mese in corso). Le altre otto sedi mostrano settembre con fatturato > 0. Su quattro sedi di 51015cc8 settembre ha F&B 0, ma lì scatta gia' costi_mancanti: e' un altro ramo.

**Atteso contro mostrato.** Mostrato: «Luglio» MOL −89 €, Spese generali 89 € con ↓97,9% verde, sparkline −100,3%. Atteso: «Giugno» MOL 36.003 € (o luglio dichiarato senza incasso, senza frecce).

**Prova del finder.** Oggi 15/10/2026: home_kpi parte da settembre (nessuna riga margini_mensili, costi 0 → has_data False), agosto idem, luglio: margini_mensili assente, RPC costi 2026-07 = fb 0,00 / spese 89,08 (13 righe, query ricalcolo) → has_data = (lordo>0 or fb>0 or spese>0 or personale>0) = True → mese mostrato «Luglio». _kpi_periodo(7): fatturato 0, netto 0, food_cost None, personale 0, spese 89,08, mol −89,08, costi_mancanti = (0>0 and ...) = False. Confronto: giugno has_data (override 80.655 → netto 73.322,73; fb 13.058,88; spese 4.180,61; pers 20.080; MOL 36.003,24) → confronto_label «vs giugno»; spese_delta = (89,08−4.180,61)/4.180,61 = −97,9% → kpi-block Trend buonoSeSu=false, delta giu' → tinta VERDE (sopprimi solo se spese===0); mol_delta = −100,2% (grigio perche' MOL<0); fatturato/personale soppressi (==0). incasso_fuori_norma(luglio): netto 0 → None → nessun avviso; confronto_escluso: giugno 73.322,73 vs mediana 73.896,91 → non fuori norma → il confronto resta. tintContiPV: costi_mancanti False, fuori_norma non true, mol<0 → ROSSO. Sparkline mol_mensile gen→lug: 31.296,09 / 16.505,43 / 28.438,79 / 37.347,38 / 38.947,67 / 36.003,24 / −89,08 → calcolaSparkline ytdPct = (−89,08−31.296,09)/31.296,09 = −100,3%, linea rossa: esattamente il «falso crollo» che il commento a worker:10024 dice di voler evitare. Il briefing si protegge da questo caso (_mesi_confrontabili, worker:6777: fatturato<=0 → False), la Home e la chat no.

**Prova indipendente della verifica.** Query mia con costi_automatici_mensili (funzione STABLE, SQL di sola lettura, corpo letto prima di chiamarla) su 802967b0/86300227/2026: luglio food 0 e spese 89,08; agosto e settembre senza righe; giugno food 13.058,88 e spese 4.180,61. In margini_mensili non c'e' riga per luglio-settembre; il personale di giugno e' 20.080 e c'e' un override di giugno a 80.655. Codice a HEAD in fastapi_worker.py: has_data = fatturato>0 or fb>0 or spese>0 or personale>0 (riga 9867); il loop alle righe 9947-9956 sceglie il primo mese con has_data; costi_mancanti = fatturato>0 and fb<=0 e' False con fatturato 0, quindi i delta non vengono azzerati. kpi-block.tsx sopprime il Trend spese solo se spese_generali===0. La sparkline include ogni mese con has_data. Nessun commento dichiara deliberata la scelta di un mese di sole spese: il commento del loop parla di «ultima fotografia reale», quello della sparkline di evitare «un falso crollo». Le cifre del finder (MOL −89,08, spese −97,9% vs giugno) tornano con i dati letti.

**Correzioni della verifica.** Perimetro da allargare: oggi le sedi toccate sono due, non una. Oltre a 86300227 c'e' 09011cdd (user 080004f3), con la Home su «Agosto», incasso 0 e MOL negativo pari ai soli costi. Lì pero' mancano le frecce (luglio senza dati) e la sparkline non ha un falso crollo, perche' la sede non ha mai avuto incassi registrati: e' la variante «account senza incassi», meno grave. Il fix proposto (scegliere un mese con fatturato>0 o fb>0) per 09011cdd sceglierebbe comunque agosto (fb 234,33), quindi serve anche il ramo «incasso mancante» dichiarato. Gravita' media confermata.

**File e righe.**

- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:138-157 (Trend spese: sopprimi solo se ===0)`
- `apps/web/src/lib/catena-confronti.ts:319-336 (ytdPct)`
- `services/fastapi_worker.py:10024-10033 (sparkline)`
- `services/fastapi_worker.py:9866-9867 (has_data include un mese di sole spese)`
- `services/fastapi_worker.py:9929-9940 (loop che sceglie il mese)`
- `services/fastapi_worker.py:9990-10021 (confronto e fuori norma: netto 0 → None)`

**Fix proposto (non applicato).** In home_kpi (e nel loop gemello della chat) aggiungere `incasso_mancante` (fatturato==0 sul mese mostrato, non in corso): azzera i delta, esclude il punto dalla sparkline e mostra l'avviso. In alternativa saltare i mesi con fatturato 0 quando esiste un mese precedente con incasso, entro i 6 mesi.

**Presidio di test proposto.** Test pytest su home_kpi con giugno pieno e luglio con sole spese 89 €: atteso periodo «Giugno», oppure incasso_mancante True con spese_delta_pct None e luglio fuori da mol_mensile. Mutante: rimettere la condizione attuale.

**Già presidiato da.** Nessun presidio sulla Home per il mese di sole spese. test_home_kpi_sparkline.py usa mesi con fatturato>0; test_briefing_onesta_fatturato_zero.py copre solo il briefing.

---

### 7. Catena: anteprima fattura letta dalla sede di sessione

`K15` · trovato da F4-09

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** /catena/fatture: dettaglio di qualsiasi fattura con ristorante_id diverso dalla sede attiva del login, sede tecnica compresa.

**Platea misurata in verifica.** Due account catena con fatture: 2f3f93a1 (569 documenti distinti, 412 con ristorante_id diverso da users.ultimo_ristorante_id) e 51015cc8 (2.582 documenti, 2.130 fuori dalla sede di sessione). Per questi l'anteprima nel dettaglio di /catena/fatture → Scadenze scrive «Nessuna riga trovata.». Omonimi di file_origine fra sedi dello stesso utente: 0 per entrambi, quindi il ramo «righe di un altro documento» oggi non ha platea. Nessuna fuga di dati: la query filtra comunque user_id. La sede di sessione e' approssimata con ultimo_ristorante_id.

**Prova del finder.** PeekDialog chiama `/api/scadenziario/anteprima?file_origine=…` senza ristorante_id (:784). Il proxy route.ts inoltra il solo file_origine e il worker get_anteprima_fattura usa _resolve_ristorante_id(user) (routers/scadenziario.py:243-246), poi filtra .eq('ristorante_id', sede di sessione). Una fattura di un'altra sede dà quindi 0 righe, e il dialog scrive «Nessuna riga trovata.» (:904-905). Con un omonimo sulla sede attiva mostra le righe e il totale di quell'altro documento. Esiste già l'endpoint giusto, /api/gruppo/prezzi/fattura?ristorante_id=&file_origine=, usato da components/fatture/anteprima-fattura-dialog.tsx:61-64.

**Prova indipendente della verifica.** Codice a HEAD (ultimo commit sui file: 4e44c781 del 9/10). catena/fatture/page.tsx:101 rende ScadenziarioClient con modalitaCatena. scadenziario-client.tsx:784 chiama fetch(`/api/scadenziario/anteprima?file_origine=…`) senza ristorante_id, mentre le altre azioni dello stesso componente (pagata, scadenza, oscura: righe 1830-1917) passano doc.ristorante_id. route.ts inoltra il solo file_origine con workerHeaders, che manda solo Authorization e X-Worker-Key, senza sede. scadenziario.py:239-260 risolve _resolve_ristorante_id(user) (ristorante_id, poi ultimo_ristorante_id, poi la prima sede attiva) e filtra .eq('ristorante_id', ...). Il bottone «Anteprima fattura» (riga 884) non e' condizionato a modalitaCatena. Ho cercato una giustificazione deliberata e non c'e'.

**Correzioni della verifica.** Nessuna sul meccanismo. Platea: 2.542 documenti di 2 account catena; caso omonimi a platea zero oggi.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:777-788`
- `apps/web/src/app/api/scadenziario/anteprima/route.ts:7-12`
- `services/routers/scadenziario.py:239-260`

**Fix proposto (non applicato).** In PeekDialog usare /api/gruppo/prezzi/fattura?ristorante_id=&file_origine= quando doc.ristorante_id e' presente, come anteprima-fattura-dialog.tsx, oppure riusare quel componente.

**Presidio di test proposto.** Test sulla funzione che costruisce l'URL dell'anteprima, estratta in lib ed eseguita con node: con ristorante_id deve includerlo. Va provato per mutazione.

**Già presidiato da.** Nessuno: test_anteprima_fattura_frontend.py copre Analisi Fatture → Articoli, non lo scadenziario.

---

### 8. Chat: 429 di OpenAI letto come limite raggiunto

`K16` · trovato da F3-02

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Home (desktop) e /m/chat, sia vista sede sia catena: tutti gli account, quando OpenAI risponde RateLimitError.

**Platea misurata in verifica.** Tutti gli account con la chat, ma solo quando OpenAI risponde RateLimitError. La frequenza non si misura da DB: il worker non registra i 429 di OpenAI in nessuna tabella. È raro, ma quando succede la casella resta bloccata fino al ricaricamento della pagina.

**Prova del finder.** _chat_loop_openai trasforma RateLimitError in HTTPException 429 'Servizio temporaneamente sovraccarico...' (fw:4591). Il client chiama quotaEsaurita(status, data) (assistente-provider.tsx:152), che su qualsiasi 429 senza 'questo mese' restituisce 'giorno' (home-chat.ts:138-143). Eseguito con node: quotaEsaurita(429,{error:'Servizio temporaneamente sovraccarico...'}) dà 'giorno'. statoCrediti({90,900}, server alle=1000, risposta alle=2000 finita='giorno') dà esaurite=true, testo 'Limite di oggi raggiunto — si azzera a mezzanotte', rimasti=894. La casella resta bloccata (use-conversazione.ts bloccato = inCorso || esaurite) finché un ricaricamento della pagina non porta una lettura server più recente.

**Prova indipendente della verifica.** Il worker trasforma _OAIRateLimit in HTTPException 429 (fw:4590-4591). Il proxy apps/web/src/app/api/chat/route.ts riporta lo stesso status e mette detail in error. assistente-provider.tsx:152 chiama quotaEsaurita(res.status, data). Eseguito con node tramite tests/helpers_ts.esegui_ts: quotaEsaurita(429, {error:'Servizio temporaneamente sovraccarico. Riprova tra qualche secondo.'}) restituisce 'giorno'. statoCrediti({90,900}, server alle=1000, risposta alle=2000 con finita='giorno') restituisce esaurite=true e testo 'Limite di oggi raggiunto — si azzera a mezzanotte', con rimasti=897.

**Correzioni della verifica.** Nessuna sulla sostanza. tests/test_home_chat_frontend.py::test_429_senza_messaggio_ripiega_sul_giorno fissa proprio il ripiego che produce il blocco.

**File e righe.**

- `apps/web/src/components/home/assistente-provider.tsx:149-153`
- `apps/web/src/components/home/use-conversazione.ts:36-37`
- `apps/web/src/lib/home-chat.ts:138-143`
- `apps/web/src/lib/home-chat.ts:420-435`
- `services/fastapi_worker.py:4590-4591`

**Fix proposto (non applicato).** Rispondere 503 per il sovraccarico di OpenAI, oppure far riconoscere a quotaEsaurita solo i due testi della quota.

**Presidio di test proposto.** quotaEsaurita(429, testo del sovraccarico) deve essere null. Aggiungere un test sul worker che lo status del sovraccarico sia diverso da 429.

**Già presidiato da.** Nessuno. Il test esistente presidia il comportamento opposto.

---

### 9. query_margini: guasto presentato come nessun dato

`K19` · trovato da F3-05

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Chat sede (desktop e /m) e catena (query_margini con sede) durante un errore Supabase o RPC: tutti gli account con la pagina margini.

**Platea misurata in verifica.** Tutti gli account con la pagina margini, ma solo durante un errore di lettura (Supabase o RPC). La frequenza non si misura da DB: l'except non scrive log (fw:5317-5318, nessun logger). Raro, ma fuorviante per definizione.

**Prova del finder.** Dentro _anno() un'eccezione su carica_margini_anno o calcola_costi_automatici_per_anno_sql diventa ({}, {}, {}) (fw:5346-5354). _kpi_periodo dà quindi has_data False e il mese sparisce. Eseguito _chat_query_margini estratto via AST, con margine_service finto che solleva RuntimeError('timeout supabase'): risultato {'mesi': []}, identico a un cliente senza margini, senza campo errore. Il prompt di sede dice 'se uno strumento torna vuoto, dillo' e §6 di CHAT_ASSISTENTE.md ('Onestà sui guasti') vieta proprio di far passare un guasto per assenza di dati.

**Prova indipendente della verifica.** A HEAD in _anno() (fw:5311-5319) l'except Exception mette ({}, {}, {}) in cache senza log. Con dizionari vuoti _kpi_periodo dà has_data False per ogni mese e la funzione restituisce {'mesi': []}, uguale al caso 'sede senza margini' (fw:5303-5304). Lo stesso file, nella fase F (fw:5972-5974), restituisce invece un 'errore' esplicito. Grep sui test: _chat_query_margini compare in test_audit_bug_passata2, test_chat_catena_sede e test_fase_e_incasso_fuori_norma, e nessuno copre il guasto di carica_margini_anno.

**Correzioni della verifica.** Nessuna sostanziale. In più rispetto al finder: il guasto non lascia nemmeno una riga di log, quindi è invisibile anche lato operativo.

**File e righe.**

- `services/fastapi_worker.py:5305-5359`

**Fix proposto (non applicato).** In caso di eccezione restituire {'errore': 'dato non leggibile...'} come la fase F, e loggare.

**Presidio di test proposto.** Test con carica_margini_anno che solleva: deve uscire 'errore', non 'mesi': []. Va provato per mutazione.

**Già presidiato da.** Nessuno per _chat_query_margini.

---

### 10. confronto_prezzi fra unità di misura diverse

`K20` · trovato da F3-06

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Chat sede e catena (confronto_prezzi con sede), desktop e /m, quando la ricerca tollerante trova lo stesso prodotto in formati diversi da fornitori diversi.

**Platea misurata in verifica.** Platea reale e ampia. Ho ripetuto la ricerca del tool (ilike su descrizione o categoria, ultimi 180 giorni, prezzo_unitario > 0, ultima riga per fornitore) per sede su 11 termini comuni. Le sedi con almeno 2 fornitori la cui unità scelta è diversa sono: caff 9/9, olio 8/9, pane 8/8, acqua 7/8, latte 7/8, pomodor 6/6, uova 5/5, zucchero 5/5 (KG contro PZ), mozzarella 2/2, burro 1/1, farina 1/4. Una parte sono sinonimi (PZ/NUM./NR/NU), ma molte coppie sono unità davvero diverse: KG/PZ, LT./NUM., CT/KG/PZ, CL/KG.

**Prova del finder.** Ho eseguito _chat_confronto_prezzi estratto via AST, con utils/voci_prezzo.py vero e sb finto, su 3 righe: A 'MOZZARELLA FIOR DI LATTE KG' 8,00 €/KG, B 'MOZZARELLA 125G' 1,20 €/PZ, C 'MOZZARELLA BUFALA CT 3KG' 36,00 €/CT. Output in ordine B (1,2), A (8,0), C (36,0) con i soli campi fornitore, prezzo, data, descrizione: unita_misura è letta (fw:5418) ma non restituita (fw:5458-5468). La descrizione dello strumento dice 'per trovare il migliore' (fw:5546). Il modello direbbe B più conveniente, mentre al kg costa 9,60 contro 8,00. Differenza e % di risparmio restano al modello. La frequenza sui dati reali non è misurata (filone senza DB).

**Prova indipendente della verifica.** A HEAD (dopo 149b3538 e c5b4b8ac del 14/10) _chat_confronto_prezzi legge unita_misura (fw:5418) e la usa solo per spareggiare nel max (fw:5447). L'output per fornitore contiene solo prezzo, data e descrizione (fw:5458-5462), ed è ordinato per prezzo senza tenere conto dell'unità (fw:5465-5468). Le misure vengono da una mia query DISTINCT ON (termine, sede, fornitore) ordinata per data desc su fatture.

**Correzioni della verifica.** La frequenza ora è misurata: quasi tutte le sedi con almeno 2 fornitori. Nel perimetro andrebbe distinta la parte dei sinonimi di unità (PZ/NUM./NR), che non falsano il confronto, dalle unità davvero incompatibili.

**Nota della sintesi.** Il commit 149b3538 del 14/10 sera (dopo la fase Trova) ha cambiato quale prezzo sceglie confronto_prezzi (ultima fattura, prezzo ponderato), ma il risultato consegnato al modello non contiene ancora l'unita' di misura e l'ordinamento resta fra unita' diverse: il difetto e' ancora presente a HEAD.

**File e righe.**

- `services/fastapi_worker.py:5407-5468`
- `services/fastapi_worker.py:5544-5557`

**Fix proposto (non applicato).** Restituire unita_misura per ogni voce e confrontare o ordinare solo dentro la stessa unità normalizzata (sinonimi PZ/NR/NUM. uniti), calcolando nel tool la differenza per gruppo.

**Presidio di test proposto.** Test con righe KG e PZ: ogni voce porta l'unità e l'ordinamento non mescola gruppi diversi. Va provato per mutazione.

**Già presidiato da.** Nessuno. tests/test_chat_confronto_prezzi_per_fattura.py usa unita_misura nei dati ma non ne verifica l'uscita.

---

### 11. query_scadenze senza i totali che la descrizione promette

`K21` · trovato da F3-07

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Chat sede (pagina scadenziario) e catena (query_scadenze con sede), desktop e /m. Riguarda gli account con più di 30 documenti aperti.

**Platea misurata in verifica.** 7 sedi su 11 con documenti hanno più di 30 documenti aperti, cioè non pagati e non note di credito (stima per file_origine con un join su fatture_documenti): fd7ac484 1.019, cc016821 563, 5444e918 450, 0dca4d1f 429, 86300227 319, f7bba05f 35, bdda08d1 31. Per queste sedi la domanda «quanto devo a X» non trova risposta nei dati del tool.

**Prova del finder.** La descrizione promette 'quanto devo a X', 'scadenze questa settimana' (fw:5504-5506). Ho eseguito _chat_query_scadenze estratto via AST su 55 documenti aperti: 25 di Y ottobre, 4 di X il 20/10, 8 di X a dicembre, 10 di Z senza data, 5 di X senza data, 3 di X scaduti a settembre. Mostrate 30 voci su 55, totale_da_pagare 19.600, nota di troncamento presente, nessun campo per fornitore o per periodo. Debito vero verso X 16.600 contro 2.100 sommando le voci mostrate. 'Questa settimana' (15-21/10): vero 6.500 contro 1.700 calcolabile dalle voci mostrate. Le scadute non hanno un flag e la differenza di date resta al modello. La nota dice di non presentare l'elenco come esaustivo: questo mitiga ma lascia la domanda senza risposta.

**Prova indipendente della verifica.** A HEAD la descrizione del tool (fw:5500-5506) promette 'quanto devo a X' e 'scadenze questa settimana'. _chat_query_scadenze (fw:4843-4926) restituisce al massimo 30 voci (_CHAT_SCADENZE_LIMIT=30, fw:4832) più totale_da_pagare complessivo, e non ha argomento fornitore né periodo né totali per gruppo. La nota di troncamento c'è e mitiga. La platea è una mia query su fatture e fatture_documenti; è una stima, perché il filtro sulle note di credito per tipo_documento TD04/TD08 approssima is_nota_credito.

**Correzioni della verifica.** Nessuna sostanziale. Le cifre di platea sono approssimate, ma l'ordine di grandezza (centinaia di documenti aperti contro 30 mostrati) rende certa l'impossibilità di rispondere.

**File e righe.**

- `services/fastapi_worker.py:4843-4926`
- `services/fastapi_worker.py:5500-5514`

**Fix proposto (non applicato).** Argomenti opzionali fornitore e da/a, filtro applicato prima del troncamento, totali filtrati e totale scaduto calcolati su tutte le voci.

**Presidio di test proposto.** Test con più di 30 voci: con fornitore=X il totale coincide con la somma di tutti i documenti di X.

**Già presidiato da.** tests/test_chat_query_scadenze.py presidia solo il troncamento onesto e il totale complessivo.

---

### 12. Doc GDPR e privacy: anonimizzazione della chat dichiarata ma assente

`K23` · trovato da F3-10, F3-11

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Documentazione tecnica interna (chi decide su GDPR e sicurezza). Il comportamento reale riguarda tutti gli account che usano la chat.

**Platea misurata in verifica.** Tutti gli account che usano la chat (a DB non verificato: niente accesso). Il difetto sta nei documenti: SICUREZZA_GDPR.md §6 e §8, COMPLIANCE_GDPR.md alla tabella «Cosa esce verso OpenAI» e la pagina pubblica /privacy. Il codice che li smentisce gira per tutti i clienti.

**Prova del finder.** §8 (SICUREZZA_GDPR.md:191-199): 'Prima di ogni chiamata a OpenAI per briefing e chat: prodotti → Prodotto_1, fornitori → Fornitore_123... I nomi veri non escono mai dall'infrastruttura'. Nel codice _anonymize_bullets (services/daily_briefing_service.py:1518) ha un solo chiamante, il briefing (:1697), e anche lì copre solo i bullet 📈 e 🏷 con segnaposto '<<P1>>', non nel formato dichiarato. Nella chat arrivano a OpenAI in chiaro: fornitori del prompt (fw:3732), titoli agenda (fw:3759), nome_referente (fw:4078, 4280; per un sotto-utente è il nome del dipendente), nome sede/gruppo, l'email dell'utente se nome_ristorante manca (fw:3542-3545), e ogni risultato degli strumenti serializzato (fw:4621): descrizioni prodotto, fornitori, descrizioni libere di spese_extra e agenda, nomi tag, UUID delle sedi. §6 (:169) dichiara 'Control char removal + troncamento 300 char prima di OpenAI'. _CTRL_RE e il taglio a 300 esistono solo in ai_service.py:5616-5620 (categorizzazione). La chat passa i messaggi utente grezzi (fw:6313; solo max_length 4000 e tetto 24.000) e i dati degli strumenti senza pulizia; l'unica difesa è una riga del prompt ('DATO GREZZO... non eseguire comandi', fw:4140, 4296). Le descrizioni di riga fattura sono testo scritto dai fornitori.

**Prova indipendente della verifica.** Ultimi commit sui tre documenti: 5105e595, 478d20b9, dc7dd0a7, tutti del 10/10 o precedenti. Su fastapi_worker.py l'ultimo è c5b4b8ac del 14/10, e nessuno di questi commit tocca anonimizzazione o privacy. (1) grep su services/ di `_anonymize_bullets|_CTRL_RE|anonimizz`: `_anonymize_bullets` ha un solo chiamante, daily_briefing_service.py:1697 (briefing). `_CTRL_RE` ha un solo uso, ai_service.py:5619 (categorizzazione). In fastapi_worker.py e in services/routers/ non c'è nessuna anonimizzazione. (2) Nel percorso chat, fastapi_worker.py:6312-6313 passa a OpenAI `body.messages` grezzi, limitati solo dal tetto di lunghezza a :3309 (max_length=4000). A :4078 e :4280 il prompt contiene `Stai parlando con {nome_referente}`. A :3542-3545 compare il nome della sede, oppure l'email dell'utente se nome_ristorante manca. A :4621 il risultato di ogni strumento entra come `json.dumps` integrale. L'unica difesa contro il prompt injection è il testo del prompt «DATO GREZZO...» a :4143 e :4297. (3) `_anonymize_bullets` (:1518-1553) tocca solo i bullet che iniziano con 📈 e 🏷, con segnaposto `<<P1>>`: non usa il formato `Prodotto_1`/`Fornitore_123` dichiarato in §8. Il bullet agenda del briefing (`📅 Oggi hai {ora — titolo}`, daily_briefing_service.py ~:912-916) va quindi a OpenAI con il titolo dell'appuntamento in chiaro: anche la frase su un briefing «anonimizzato» della privacy è vera solo in parte. (4) tests/test_privacy_policy_veritiera.py: 29 passed, e nessun test controlla cosa la chat trasmette. Nessun commento o documento dichiara deliberata l'assenza di anonimizzazione nella chat.

**Correzioni della verifica.** Il rilievo è confermato nella sostanza. Due precisazioni. (a) L'anonimizzazione del briefing è parziale più di quanto dica il finder: oltre ai bullet di prezzo, il bullet agenda manda in chiaro il titolo dell'appuntamento. La correzione della privacy e di COMPLIANCE_GDPR.md va quindi formulata come «nomi di prodotti e fornitori nei segnali di prezzo» e deve dichiarare i titoli degli appuntamenti. (b) La gravità media regge per il valore legale e di trasparenza (informativa pubblica incompleta su tutti gli account). Non è un numero sbagliato a video. Scegliere fra correggere i documenti e implementare la pseudonimizzazione nella chat è una decisione di Mattia.

**Deliberato dove.** Da nessuna parte. Il riferimento più vicino è BRIEFING_HOME.md:69 e :226, che descrive correttamente l'anonimizzazione dei soli nomi fra «» e del bullet 📈 nel briefing, senza nominare la chat.

**File e righe.**

- `DOCUMENTAZIONE/tecnica/SICUREZZA_GDPR.md:169`
- `DOCUMENTAZIONE/tecnica/SICUREZZA_GDPR.md:191-199`
- `apps/web/src/app/(legal)/privacy/page.tsx:229-255`
- `docs/COMPLIANCE_GDPR.md:51-58`
- `services/ai_service.py:5616-5620`
- `services/daily_briefing_service.py:1518-1553`
- `services/daily_briefing_service.py:1697`
- `services/fastapi_worker.py:3732`
- `services/fastapi_worker.py:3759`
- `services/fastapi_worker.py:4078`
- `services/fastapi_worker.py:4621`
- `services/fastapi_worker.py:6313`

**Fix proposto (non applicato).** Riscrivere §8 di SICUREZZA_GDPR.md: briefing pseudonimizzato solo nei segnali di prezzo; chat in chiaro, con l'elenco dei dati trasmessi. Limitare la riga «Prompt injection» di §6 alla categorizzazione e citare per la chat la sola difesa reale (istruzione nel prompt). Aggiornare COMPLIANCE_GDPR.md e privacy/page.tsx con le categorie reali: domanda dell'utente, nome di chi scrive, righe fattura e fornitori interrogati dagli strumenti, scadenze, appuntamenti, spese annotate, tag, nomi delle sedi. Le alternative (pseudonimizzare la chat, oppure correggere solo i documenti) vanno decise da Mattia.

**Presidio di test proposto.** Un test che costruisce il prompt di sede (_build_chat_system_prompt) con un nome_referente e un fornitore noti e verifica che compaiano in chiaro, coerente con i documenti. Inoltre una mappa strumento→categoria dichiarata in test_privacy_policy_veritiera, così uno strumento nuovo in _CHAT_TOOLS_SEDE o _CHAT_TOOLS_GRUPPO senza dichiarazione fa fallire il test. Da provare per mutazione.

**Già presidiato da.** Nessun presidio. tests/test_privacy_policy_veritiera.py (29 verdi) verifica che OpenAI sia nominato come fornitore, non cosa riceve. test_documentazione_onesta verifica simboli e percorsi, non l'affermazione di §8.

---

### 13. TTS: cookie non validato e dati verso Google

`K26` · trovato da F2b-4, F2a-4

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Chi preme «Ascolta» nel riquadro assistente: Home desktop (riquadro-assistente.tsx:81), /m/briefing (mobile-briefing.tsx:113) e la Home di catena mobile (mobile-catena.tsx:87). Tutti gli account con briefing, titolari e sotto-utenti.

**Platea misurata in verifica.** Tutti gli account che premono «Ascolta» sul briefing (Home desktop, /m/briefing, Home catena mobile). Il testo inviato contiene il nome del referente e le cifre del briefing. Il proxy e' aperto a chiunque imposti un cookie oneflux_session qualsiasi.

**Prova del finder.** api/tts/route.ts:54-56 controlla solo che il cookie oneflux_session esista: nessuna verifySession, il valore è libero. :58-71 prende q (fino a 600 caratteri) e lo manda in GET a https://translate.google.com/translate_tts, endpoint non ufficiale. ascolta-button.tsx:68 passa testo = `${briefing.saluto}. ${briefing.narrativa}`. Il saluto è _saluto_per_ora(nome) (fastapi_worker.py:6434), con nome = user['nome_referente'] (:9326), che per un sotto-utente è il suo nome (sotto_utenti_service.sovrapponi). La lista dei sub-responsabili della privacy ((legal)/privacy/page.tsx:172-210: Supabase, OpenAI, Brevo, Vercel, Railway) non nomina Google: grep -i 'google' su app/(legal) → 0 risultati. Inoltre, con un cookie qualsiasi, la route resta un proxy TTS aperto verso Google.

**Prova indipendente della verifica.** A HEAD api/tts/route.ts:54-56 controlla solo che il cookie esista (nessuna verifySession), poi fa un fetch GET a translate.google.com/translate_tts con q (fino a 600 caratteri). Ultimo commit sul file 2acf303f del 29/7. grep -rli 'google' in app/(legal): 0 file, e SICUREZZA_GDPR.md non nomina Google ne' il TTS. L'unico riferimento nei test e' test_regole_dominio_guardia.py:523-533, che la elenca come route con logica non-auth senza validare il token.

**Correzioni della verifica.** Nessuna sul merito. Gravita' media (non bassa come in F2a-4) perche' dati personali (il nome) e cifre aziendali vanno a un terzo non dichiarato nella privacy.

**Deliberato dove.** Il TTS Google e' una scelta deliberata (commit d30ef4b9 «voce briefing gratis … via TTS Google»), ma non e' dichiarato come sub-responsabile, e la mancata validazione della sessione non e' motivata da nessuna parte.

**File e righe.**

- `apps/web/src/app/(legal)/privacy/page.tsx:172-210`
- `apps/web/src/app/api/tts/route.ts:53-71`
- `apps/web/src/app/api/tts/route.ts:55-58`
- `apps/web/src/components/ascolta-button.tsx:68`
- `services/fastapi_worker.py:6434`
- `services/fastapi_worker.py:9326`
- `tests/test_regole_dominio_guardia.py:523-533`

**Fix proposto (non applicato).** verifySession prima del fetch. Dichiarare Google nella privacy oppure passare a speechSynthesis del dispositivo; togliere il nome dal testo inviato.

**Presidio di test proposto.** Estendere tests/test_regole_dominio_guardia.py (ROUTE_NON_PROXY_DICHIARATE già elenca tts) con un test che esegua la logica di auth della route: cookie inventato → 401. Più un controllo che ogni host esterno chiamato da app/api compaia nella privacy.

**Già presidiato da.** nessuno

---

### 14. Prompt chat sede: percentuali sul fatturato lordo

`K05` · trovato da F3-01

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Chat della Home sede, desktop e /m, e query_margini anche dalla chat di catena. Riguarda tutti gli account che hanno la pagina margini e chiedono «il personale/MOL va bene?». Gli ID non si possono separare senza DB, quindi va considerato strutturale per tutti.

**Platea misurata in verifica.** Settembre 2026, cioè l'ultimo mese completo che home_kpi passa alla chat al 15/10. Lo misura una query mia su margini_mensili, con l'override di ricavi_modalita_mensile e i costi presi da fatture con la stessa logica della RPC costi_automatici_mensili: 7 sedi hanno fatturato > 0. 4 di queste (account 51015cc8, sedi fd7ac484/0dca4d1f/5444e918/cc016821) hanno F&B, spese e personale a 0: sono costi_mancanti, quindi il MOL % è senza senso con qualunque base (100% sul netto, 92,7-93,3% sul lordo). Le altre 3 sedi su 2 account hanno costi reali e in 2 casi su 3 cambia la fascia del benchmark. bdda08d1 (account 2f3f93a1): MOL 12,0% sul netto, «nella norma»; 11,0% sul lordo, «basso». dcf1996e (account 2f3f93a1): personale 35,9% sul netto, «critico»; 32,8% sul lordo, «elevato». f16aebe5 (account 79920814): personale 57,2% contro 52,0%, MOL -50,8% contro -46,2%, spese 66,3% contro 60,2%, ma la fascia resta la stessa. Il rapporto lordo/netto misurato va da 1,0723 a 1,1000, quindi lo scarto è del 7-10% relativo, non sempre circa 1,10.

**Prova del finder.** Il blocco KPI del prompt passa 'Fatturato: €{kpi.fatturato}' (fw:3693). Quel valore è il LORDO, iva10+iva22+altri (_kpi_periodo fw:9812); il MOL invece è calcolato sul netto. Le soglie del prompt dicono 'MOL % (margine operativo lordo ÷ fatturato)' e 'Costo personale % (costo personale ÷ fatturato)' (fw:4048, 4051). La pagina Margini fa personale_perc=pers/netto e mol_perc=mol/netto (services/routers/margini.py:1526-1527). Ho eseguito _kpi_periodo, estratto via AST, con iva10=50.000, iva22=5.000, personale 15.000, F&B 14.000, spese 9.000: fatturato 55.000, netto 49.552,91, MOL 11.552,91. Sulla pagina: personale 30,27% (fascia 'elevato'), MOL 23,31%, spese 18,16%. Con la formula che il prompt dà al modello: personale 27,27% (fascia 'norma'), MOL 21,01%, spese 16,36%. Lo scarto è sistematico (lordo/netto ≈ 1,10) e fa cambiare fascia di benchmark. query_margini restituisce lo stesso fatturato lordo senza il netto (fw:5332).

**Prova indipendente della verifica.** Codice a HEAD, dopo i commit del 14/10 su fastapi_worker.py. Il blocco KPI della chat di sede (fastapi_worker.py:3693) passa al modello «Fatturato: €{kpi.fatturato}». In _kpi_periodo (:9812) quel valore è iva10+iva22+altri, cioè il lordo. In HomeKpiResponse (:2631) il campo netto non c'è, quindi il modello non lo riceve. Le soglie del prompt (:4048-4055) dicono «MOL % (margine operativo lordo ÷ fatturato)», e lo stesso vale per personale e spese. Il prompt dà soltanto importi in euro e un esempio di divisione su «€516.152 di fatturato» (:4131), quindi l'unico denominatore che il modello ha è il lordo. Il tool query_margini (:5329-5336) restituisce fatturato (lordo), food_cost_pct e mol, senza netto e senza percentuali. La pagina Margini divide invece per il netto (routers/margini.py:1526-1527: personale_perc, mol_perc e spese_perc su netto). Il food cost è l'unica percentuale già calcolata sul netto, per decisione di Mattia del 4/9 (commento a :9839). Non è una scelta deliberata: il blocco viene dal commit b182c4fa del 2/6/2026 e non ho trovato decisioni nei doc (grep su DOCUMENTAZIONE/docs per chat+lordo: 0 risultati). Nessun presidio: tests/ non contiene test che confrontino le percentuali del prompt con margini.py; il concetto compare solo in una fixture del prompt e in test_margine_service.py. Cifre: le ho rimisurate con una SQL READ ONLY scritta da me, mesi 8 e 9 del 2026, riportate in platea_oggi.

**Correzioni della verifica.** 1) Il rapporto lordo/netto sui dati reali va da 1,072 a 1,100 (vale 1,10 solo con ricavi tutti al 10%). 2) Platea reale a settembre 2026: 3 sedi su 2 account con costi; sulle altre 4 sedi i costi sono a zero e il MOL % non ha senso con nessuna base. Due cambi di fascia misurati: MOL di bdda08d1 da «norma» a «basso», personale di dcf1996e da «critico» a «elevato». Nei rischi va detto anche che il lordo può migliorare il giudizio sul personale: dcf1996e, critico sulla pagina, nella chat esce solo «elevato». 3) Gravità da alta a media: il numero sbagliato non lo stampa il codice, lo ottiene il modello dividendo, e solo quando il cliente chiede un giudizio. Il codice gli dà però solo il lordo come denominatore. 4) La chat di catena (:4187) ha le stesse soglie «÷ fatturato» e usa query_margini con il fatturato lordo: va nello stesso fix.

**Deliberato dove.** Non deliberato. Per il food cost la base netta è una decisione esplicita del 4/9/2026 (commento in _kpi_periodo), che rende ancora più incoerente lasciare MOL, personale e spese sul lordo. Il lordo è dichiarato solo come «headline mostrato sulla card», non come base delle percentuali.

**File e righe.**

- `services/fastapi_worker.py:3693-3697`
- `services/fastapi_worker.py:4045-4055`
- `services/fastapi_worker.py:4131`
- `services/fastapi_worker.py:5329-5336`
- `services/fastapi_worker.py:9812-9846`
- `services/routers/margini.py:1526-1527`

**Fix proposto (non applicato).** Aggiungere a HomeKpiResponse e al blocco KPI del prompt personale_pct, spese_pct e mol_pct calcolati sul netto, come margini.py:1526-1527, oppure almeno la riga «Fatturato netto (IVA esclusa)». Riscrivere le soglie in «÷ fatturato netto (IVA esclusa)» nel prompt di sede (:4045-4055) e in quello di catena (:4187). Aggiungere netto e le percentuali sul netto anche ai risultati di query_margini.

**Presidio di test proposto.** Un test che costruisce il prompt di sede e il risultato di query_margini con margini sintetici (iva10 e iva22 non nulli). Deve verificare che le percentuali di personale, MOL e spese esposte siano uguali a quelle di margini_kpi o get_margini_analisi sugli stessi dati. Va provato per mutazione sostituendo netto con lordo in _kpi_periodo.

**Già presidiato da.** Nessuno. Il grep su tests/ per «÷ fatturato», «MOL %» e «netto» nei test_chat* non trova confronti tra la base delle percentuali del prompt e quella della pagina Margini.

---

### 15. Chat query_margini: mesi a fatturato 0 e niente costi_mancanti

`K06` · trovato da F1e-11, F1b-03, F1c-02

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Chat (sede e catena via ristorante_id): risposta dell'AI su «com'è andato il MOL». Account con un mese a ricavi inseriti e fatture merce non ancora caricate.

**Clienti coinvolti (ID).** `2f3f93a1-c1f4-4804-858e-a161e6f36f3f`, `802967b0-2aed-40f0-8d42-81076f44bb17`, `bdda08d1-9490-486c-adfb-dd05cbddc25c`, `dcf1996e-f430-4549-8505-902b169f6bab`

**Platea misurata in verifica.** Ottobre 2026 è il mese in corso, quindi 'parziale'. 3 sedi hanno fatture di ottobre e zero righe in ricavi_giornalieri: bdda08d1 (6.941,22 EUR), f7bba05f (836,91 EUR) e dcf1996e (4.062,93 EUR). Per loro la chat riceve fatturato 0 e un MOL negativo pari ai soli costi. Altre 5 sedi hanno ricavi di ottobre e nessuna riga fattura di ottobre: fd7ac484, 5444e918, 0dca4d1f, cc016821 e 09011cdd. Per loro il mese ha costi_mancanti, ma la chat riceve un MOL gonfiato senza alcun flag. Totale: 8 sedi su 16 sul mese corrente.

**Atteso contro mostrato.** Mese con ricavi 40.000 netti e costi 0: la chat riceve mol ≈ 40.000 − personale, food_cost_pct 0.0, nessun avviso; la Home lo mostra giallo con banner.

**Prova del finder.** fastapi_worker.py:5330-5337: chiavi `mese, fatturato, food_cost_pct, mol, parziale`; :5355-5358 aggiunge solo `incasso_fuori_norma`/`nota`. _kpi_periodo calcola `costi_mancanti` (:9868) e la Home lo usa per colorare in giallo e sopprimere i delta (:9991-9995, tintContiPV); il briefing tace (_briefing_mese_chiuso). La descrizione del tool (:5519-5524) non avverte. Un mese con costi_mancanti arriva all'AI come MOL positivo e food cost 0% senza spiegazione.

**Prova indipendente della verifica.** A HEAD (ultimo commit sul file c5b4b8ac, 14/10) _chat_query_margini, fw:5292-5359, costruisce il mese con le sole chiavi mese, fatturato, food_cost_pct, mol e parziale. Poi aggiunge soltanto incasso_fuori_norma e nota. costi_mancanti è calcolato in _kpi_periodo (fw:9866) ma non viene passato. Il fallimento 'nessun test' è confermato: grep costi_mancanti in tests/test_chat_*.py e in test_fase_e_incasso_fuori_norma.py restituisce 0. Platea misurata con una mia query su ricavi_giornalieri e fatture dal 2026-10-01, raggruppata per sede.

**Correzioni della verifica.** La gravità unica è media. Va aggiunta una mitigazione che nessuno dei tre finder ha citato: il prompt contiene _blocco_merce_zero (fw:4059-4060), che già dice al modello «food cost 0% con fatturato presente = mancano i costi; se manca anche il fatturato di' che mancano i ricavi». La parte food cost è quindi coperta dal prompt. Restano scoperti il MOL, che il prompt non invalida, e il mese a fatturato 0 con MOL negativo, presentato come «parziale = mancano giorni». Il perimetro di oggi è il mese in corso di 8 sedi, non solo le 2 di 2f3f93a1 più D/luglio.

**File e righe.**

- `services/fastapi_worker.py:4103-4108`
- `services/fastapi_worker.py:5322-5338`
- `services/fastapi_worker.py:5324-5341`
- `services/fastapi_worker.py:5330-5337`
- `services/fastapi_worker.py:5355-5358`
- `services/fastapi_worker.py:9843-9855`
- `services/fastapi_worker.py:9868`
- `services/fastapi_worker.py:9991-9995`

**Fix proposto (non applicato).** Aggiungere al mese costi_mancanti e un flag senza_incasso (fatturato 0 e costi > 0), ciascuno con una nota. Nel prompt: con questi flag il MOL non va commentato.

**Presidio di test proposto.** Test su _chat_query_margini con margini mockati, provato per mutazione togliendo la chiave.

**Già presidiato da.** Nessun presidio sul comportamento. Il prompt mitiga solo il food cost 0% (fw:4059-4060).

---

### 16. «Fatturato» lordo e netto con la stessa parola

`K07` · trovato da F1e-01, F1a-05

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Home card «I tuoi conti» (sede e /m/briefing, stesso KpiBlock): tessera «Fatturato» senza indicazione IVA, periodo in meta = `kpi.periodo_label` («Settembre» o «Ottobre · in corso»); Ricavi e Margini KpiBar: «Fatturato Netto» con sotto «lordo X», chip «Anno in corso»; Catena → Sintesi: «Fatturato (IVA incl.)» con meta `overview.periodo_label`; Catena → Analisi → Margini e coperti: colonna «Fatturato» (netto, dichiarato solo nel tooltip); chat tool query_margini: chiave `fatturato` lorda, descrizione dice solo «fatturato». Tutti gli account; nessun ID misurabile in questo filone (solo codice).

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `5444e918-8616-464c-a109-5d8aba226805`, `cc016821-e749-4323-9568-3781c69384d3`, `fd7ac484-b562-498d-a6d1-00c4c6fd09dd`

**Platea misurata in verifica.** Tutti gli account con ricavi: la Home (desktop e /m) mostra «Fatturato» lordo IVA accanto a un MOL calcolato sul netto; nessuna dichiarazione della base IVA in kpi-block.tsx.

**Atteso contro mostrato.** Stesso mese: Home mostra lordo (iva10+iva22+altri), Margini mostra netto (iva10/1.10+iva22/1.22+altri) con il lordo in sottotitolo; a parità di dati il numero Home è il «lordo» della card Margini, ma il cliente legge due «Fatturato» diversi.

**Prova del finder.** Home: kpi-block.tsx:122-124 `label="Fatturato"` senza suffisso, valore `kpi.fatturato`; worker _kpi_periodo (fastapi_worker.py:9800-9813) `fatturato = iva10 + iva22 + altri` (lordo) e `netto = iva10/1.10 + iva22/1.22 + altri`; periodo_label a :10043-10045. Margini: kpi-bar.tsx:219 `label: "Fatturato Netto", numeric: kpi.fatturato_netto, sub: lordo …`. Catena Sintesi: sintesi-catena.tsx:238 `label="Fatturato (IVA incl.)"` su `kpi.fatturato` = gruppo.py:1227 `fatturato=round(tot_lordo, 2)`. Catena Margini e coperti: scheda-margini-coperti.tsx:65-67 `label: "Fatturato"` tooltip «al netto dell'IVA» su gruppo.py:1621 `fatturato=round(netto, 2)`. Chat: fastapi_worker.py:5332 `"fatturato": k["fatturato"]` (lordo da _kpi_periodo), descrizione tool :5519-5524 «Andamento di fatturato, food cost % e MOL». Due superfici con la sola parola «Fatturato» (Home lordo, catena Margini e coperti netto) e la chat che riceve il lordo mentre la pagina Margini titola il netto.

**Prova indipendente della verifica.** HEAD beba1ce9. kpi-block.tsx:124 label="Fatturato" senza qualificatore (ultimo commit c0d71023 dell'8/10). margini/kpi-bar.tsx:219 «Fatturato Netto» con sotto «lordo …»; sintesi-catena.tsx:238 «Fatturato (IVA incl.)». scheda-margini-coperti.tsx:66-67 «Fatturato» con tooltip netto, ma alla :308 la scheda dichiara in chiaro «netto IVA (i «conti del gruppo» mostrano il lordo, IVA inclusa)».

**Correzioni della verifica.** Il perimetro va ristretto: la scheda catena «Margini e coperti» dichiara il netto nel testo a video (scheda-margini-coperti.tsx:308), non solo nel tooltip. Le superfici senza dichiarazione della base restano la Home «I tuoi conti» (sede e /m) e il tool di chat query_margini, che passa il lordo con la chiave `fatturato`. Gravita' media confermata: per F1a-05 il caso Home e' 'bassa' solo perche' il banner dei costi mancanti attenua il MOL, ma la base IVA resta non dichiarata su tutti gli account.

**Deliberato dove.** Non deliberato per la Home; la catena dichiara la base in modo esplicito.

**File e righe.**

- `apps/web/src/app/(app)/catena/analisi/scheda-margini-coperti.tsx:65-67`
- `apps/web/src/app/(app)/catena/sintesi-catena.tsx:238`
- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:122-124`
- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:78`
- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:83-85,122-127`
- `apps/web/src/app/(app)/margini/kpi-bar.tsx:219`
- `services/fastapi_worker.py:10043-10045`
- `services/fastapi_worker.py:5332`
- `services/fastapi_worker.py:5519-5524`
- `services/fastapi_worker.py:9800-9813`
- `services/fastapi_worker.py:9806-9812`
- `services/routers/gruppo.py:1227`
- `services/routers/gruppo.py:1621`

**Fix proposto (non applicato).** Home: «Fatturato (IVA incl.)» o un sottotitolo con il netto; chat: rinominare la chiave in fatturato_lordo o aggiungere fatturato_netto e dirlo nella descrizione del tool.

**Presidio di test proposto.** Test frontend su un file di sorgente (tests/test_*_frontend.py con helpers_ts) che legge le etichette dei KPI «Fatturato» in kpi-block.tsx, sintesi-catena.tsx e scheda-margini-coperti.tsx e pretende il suffisso (IVA incl./netto) accanto alla parola; test worker che asserisce che il payload di _chat_query_margini contenga una chiave con la base IVA nel nome.

**Già presidiato da.** nessuno trovato

---

### 17. Spesa per PV scarta le righe negative, Analisi Fatture le nettizza

`K08` · trovato da F1a-03, F1e-06

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **media** |
| Verifica | confermato |

**Chi lo vede.** Catena → «Spesa per PV» (per categoria/fornitore) vs Analisi Fatture KPI «Spesa totale» di ogni PV; tutte e 4 le sedi con fatture dell'account.

**Clienti coinvolti (ID).** `0dca4d1f-0caa-419a-b869-25bd98f424e1`, `51015cc8-078c-4e92-86b4-113e62e16d38`, `5444e918-8616-464c-a109-5d8aba226805`, `cc016821-e749-4323-9568-3781c69384d3`, `fd7ac484-b562-498d-a6d1-00c4c6fd09dd`

**Platea misurata in verifica.** 2 account con piu' sedi e righe negative nel 2026: 51015cc8 (4 sedi, 122.398,82 € di righe negative, quanto dichiarato dal finder) e 2f3f93a1 (3 sedi, 16.968,66 €). Per quest'ultimo, l'effetto dipende dall'uso della vista catena.

**Atteso contro mostrato.** Stesse sedi, stesso periodo: catena 3.543.394,16 vs Analisi (somma 4 PV) 3.432.058,22.

**Prova del finder.** Periodo 01/01/2026→15/10/2026 (default di entrambe: Analisi anno_corrente gen→oggi; catena _periodo_da_query anno intero, ma non esistono righe oltre il 31/07). Replica SQL delle due definizioni. Catena (gruppo_spesa_pivot: totale_riga > 0, categoria <> 'Da Classificare', COALESCE(data_competenza,data_documento)) vs Analisi (/api/fatture/kpi: totale_riga <> 0, Da Classificare incluse, NOTE escluse, data_documento): 0dca4d1f 572.236,89 vs 553.914,91 (+18.321,98); 5444e918 569.856,03 vs 560.045,22 (+9.810,81); cc016821 705.730,79 vs 691.651,51 (+14.079,28); fd7ac484 1.695.570,45 vs 1.626.446,58 (+69.123,87). Totale +111.335,94 = righe negative scartate 122.398,82 (di cui in documenti TD04: 46.863,11 = 11.517,68 + 6.262,78 + 7.038,85 + 22.043,80; in fatture normali — sconti/abbuoni: 75.535,71 = 7.279,22 + 7.513,93 + 13.320,43 + 47.422,13) − Da Classificare positive escluse dalla catena 11.062,88 (474,92 + 3.965,90 + 6.280,00 + 342,06). Quadratura al centesimo per ogni sede. data_competenza mai diversa da data_documento (0 righe) e nessuna NOTE con importo > 0: le due basi di data non pesano. Note di credito: 106 documenti TD04 (20/17/18/51), totale_documento header 37.453,54 € (7.265,59 + 4.570,22 + 5.113,26 + 20.504,47), somma righe −35.237,13 (hanno anche 10 righe positive), segno_compensazione = −1 su 106/106.

**Prova indipendente della verifica.** Sul DB live pg_get_functiondef('gruppo_spesa_pivot') contiene 'totale_riga > 0' (posizione 830). Nel repo il filtro e' alle righe 290/374/401 di 20260912075621_oscura_fattura.sql, e gruppo.py:1449-1450 scarta le quote <= 0. La mia query sulle righe negative con COALESCE(data_competenza,data_documento) >= 2026-01-01 da' 122.398,82 € per 51015cc8, la stessa cifra del finder.

**Correzioni della verifica.** Nessuna correzione sui numeri. La platea va estesa a un secondo account multi-sede, 2f3f93a1, con 16.968,66 € di righe negative nel 2026.

**Deliberato dove.** Nessun commento nella RPC o in gruppo.py che motivi il filtro, e nessuna nota a video in scheda-spesa-pv.tsx (ultimo commit 190fa6d2 del 28/9).

**File e righe.**

- `apps/web/src/app/(app)/catena/analisi/scheda-spesa-pv.tsx:95`
- `services/fastapi_worker.py:10558-10600 (_fetch_fatture_rows su data_documento, Da Classificare incluse)`
- `services/routers/fatture.py:386-396 (_calc: rows_nonzero, somma netta)`
- `services/routers/fatture.py:393-400`
- `services/routers/gruppo.py:1084-1105 (_periodo_da_query default anno intero)`
- `services/routers/gruppo.py:1449-1451`
- `supabase/migrations/20260912075621_oscura_fattura.sql:374`
- `supabase/migrations/20260912075621_oscura_fattura.sql:374 (AND f.totale_riga > 0)`

**Fix proposto (non applicato).** Nettizzare la pivot (totale_riga <> 0 nella RPC con migration, togliere il continue in gruppo.py) oppure dichiarare «al lordo di note di credito e sconti» nella scheda.

**Presidio di test proposto.** Test -m sql su gruppo_spesa_pivot con una riga −50 e una +100 dello stesso PV: atteso 50 (se si nettizza) — mutante: rimettere `> 0` → 100 → rosso. In parallelo un test su get_fatture_kpi e sulla pivot con lo stesso dataset che asserisce l'uguaglianza delle due «spese».

**Già presidiato da.** nessuno

---

### 18. Soglie del MOL diverse fra Margini e catena

`K11` · trovato da F1e-02

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **media** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Ricavi e Margini → tab Analisi (gauge MOL con emoji e commento da _valuta_soglia_margine) e Catena → Analisi → Margini e coperti (pallino margineDot per PV). Il `colore` del ranking (gruppo.py _colore_margine) non è reso da nessun .tsx. Tutti gli account con catena.

**Platea misurata in verifica.** Account con piu' sedi in ristoranti: 3 (51015cc8 con 5 sedi, 2f3f93a1 con 3, 603f7125 con 2). Le viste catena (Analisi → Margini e coperti su desktop, ranking su /m) sono raggiungibili solo da loro. Non ho misurato quante sedi hanno oggi un MOL% nelle fasce discordanti (5-8, 12-15, 15-20).

**Atteso contro mostrato.** MOL 18%: Margini dice 🟡 «MOL nella norma», la catena mette il pallino verde; MOL 7%: Margini 🟠 «MOL basso», catena rosso.

**Prova del finder.** Eseguito con python -I (funzioni pure estratte via ast da routers/margini.py e routers/gruppo.py) e con node (lib/catena-confronti.ts): MOL 7% → Margini 🟠 «MOL basso» / catena margineDot bg-negativo (rosso); 10% → 🟠 / bg-incerto (giallo); 13% → 🟡 «MOL nella norma» / bg-incerto; 18% → 🟡 «MOL nella norma» / bg-positivo (verde); 25% → 🟢 / verde. Soglie: margini.py:860-865 (5,12,20,200); catena-confronti.ts:24-25 SOGLIA_MARGINE_VERDE=15, GIALLO=8 e margineDot :54-59; gruppo.py:328-340 _colore_margine (15/8) la cui docstring dice «stesse soglie di lettura dei conti PV», falso. _colore_margine finisce in RankingPV.colore (gruppo.py:1266) che nessun .tsx legge (grep `r.colore|ranking.*colore` vuoto): sintesi-catena.tsx:284 usa `pv.colore` della salute.

**Prova indipendente della verifica.** Eseguito con node via helpers_ts.esegui_ts su lib/catena-confronti: margineDot(7/10/13/18/25, false) = negativo, incerto, incerto, positivo, positivo. Con le soglie lette per AST da margini.py (_KPI_SOGLIE_MARGINI['mol']): 7 🟠, 10 🟠, 13 🟡, 18 🟡, 25 🟢. A MOL 18% il gauge di Margini dice 🟡 «nella norma» e la catena mette il verde; a 7% il gauge dice 🟠 «basso» e la catena il rosso. gruppo.py:160 conferma che margine_perc e' il MOL% del periodo. Nessun commento, documento o commit motiva le due scale: il commit 59a448dc ha solo estratto 15/8 in lib. La docstring di _colore_margine dice «stesse soglie di lettura dei conti PV», ed e' falsa.

**Correzioni della verifica.** Il finder sbaglia quando dice che il `colore` del ranking calcolato da _colore_margine «non e' reso da nessun .tsx». Lo rende /m: apps/web/src/app/(mobile)/m/briefing/mobile-catena.tsx:235-248 fa `overview.ranking.map` e colora pallino e percentuale con DOT/TXT[pv.colore], sotto il titolo «Ranking punti vendita per margine %». La scala 15/8 compare quindi a video in due punti (pallino desktop margineDot e ranking mobile), non in uno, e _colore_margine non si puo' cancellare: va riallineata. Va corretta anche la classificazione: non e' un calcolo sbagliato ma la stessa grandezza (MOL%) giudicata con due metri, cioe' «stessa etichetta per grandezze diverse».

**File e righe.**

- `apps/web/src/app/(app)/catena/analisi/scheda-margini-coperti.tsx:238`
- `apps/web/src/lib/catena-confronti.ts:24-25`
- `apps/web/src/lib/catena-confronti.ts:54-59`
- `services/routers/gruppo.py:1266`
- `services/routers/gruppo.py:328-340`
- `services/routers/margini.py:860-865`
- `services/routers/margini.py:965-977`

**Fix proposto (non applicato).** Una sola scala MOL, derivata dalle stesse costanti per margini.py, gruppo._colore_margine (usato da /m) e catena-confronti.ts. La decisione su quali soglie tenere spetta a Mattia.

**Presidio di test proposto.** Test incrociato sugli stessi valori (7, 13, 18): margineDot (node), _colore_margine e _valuta_soglia_margine devono dare la stessa fascia. Va provato per mutazione su ciascuna delle tre.

**Già presidiato da.** tests/test_catena_confronti_frontend.py:71 fissa 15/8 e tests/test_margini_soglie_settore.py fissa 5/12/20. Nessun test confronta le due scale.

---

### 19. GET /api/home/config è rotta comune: un sotto-utente senza Home riceve contatori e tetti AI dell'account, soglia alert prezzi e nome referente

`F2a-2` · trovato da F2a-2

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Sotto-utente senza Home (desktop e /m: il layout di /m la chiama su ogni pagina). Espone dati dell'account che le Impostazioni gli nascondono (regola «solo in meno», memoria 3/10). 0 sotto-utenti in produzione oggi.

**Platea misurata in verifica.** Zero: nessun sotto-utente a DB (sotto_utenti = 0, sessioni con sotto_utente_id = 0).

**Atteso contro mostrato.** atteso: niente tetti/crediti AI né soglia alert a chi non ha la Home; mostrato: chat_limite_giorno=150, chat_limite_mese=1500, price_alert_threshold=5.0

**Prova del finder.** Sonda test_sonda_home_config_senza_home: sotto-utente con la sola analisi_fatture: GET /api/home/briefing -> 403 (coerente), GET /api/home/config -> 200 con chat_ai_enabled, chat_limite_giorno=150, chat_limite_mese=1500, chat_crediti_oggi/mese/ricarica, price_alert_threshold=5.0, alert_prezzi_solo_preferiti, giorni_chiusura_settimanali, nome_referente, 15 topics con enabled. Codice: permessi_rotte.py:277 la dichiara in ROTTE_COMUNI; fastapi_worker.py:10083-10155 non distingue il sotto-utente e chiama _chat_quota_pool, _chat_budget_mensile_pool, _chat_crediti_stato (sempre col titolare) e get_price_alert_threshold. Nessun dato di fattura o di margine; i tetti rivelano il piano dell'account.

**Prova indipendente della verifica.** HEAD permessi_rotte.py:276-277: GET /api/home/config sta in ROTTE_COMUNI, deliberatamente ('il layout di /m la chiede su ogni pagina' per sapere se la chat e' accesa), ma la risposta porta anche tetti/crediti, soglia alert e nome referente.

**Correzioni della verifica.** La rotta comune e' deliberata e motivata (flag chat per /m); il difetto e' solo l'eccesso di campi. Platea zero oggi.

**File e righe.**

- `apps/web/src/app/(mobile)/m/layout.tsx:76-83`
- `services/fastapi_worker.py:10077-10155`
- `services/permessi_rotte.py:276-277`

**Fix proposto (non applicato).** Per un sotto-utente senza Home rispondere con un ConfigResponse ridotto (chat_ai_enabled=False, tetti e crediti a 0, topics=[], price_alert_threshold di default) oppure lasciare la rotta comune ma calcolare la parte AI/soglia solo se _su.ha_pagina(user, PAGINA_HOME); il layout di /m ha bisogno solo di chat_ai_enabled/chat_limite_giorno, che a chi non ha Home devono già dire «chat spenta».

**Presidio di test proposto.** Test -m sql: sotto-utente senza Home -> /api/home/config non contiene chat_limite_giorno>0, chat_limite_mese, crediti né price_alert_threshold dell'account; con Home -> uguale al titolare. Mutante: togliere il ramo ridotto.

**Già presidiato da.** Nessuno.

---

### 20. Il sotto-utente vede «Configura assistente» (Home e Home di catena), ma il salvataggio è vietato dal worker e il messaggio dice «Riprova»

`F2b-3` · trovato da F2b-3

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** /dashboard (sotto-utente con Home) e /catena (sotto-utente con Catena). Account non misurati.

**Platea misurata in verifica.** Zero: SQL READ ONLY su sotto_utenti = 0 righe, sessioni con sotto_utente_id = 0.

**Prova del finder.** dashboard/page.tsx:45 rende <ConfigAssistente> a chiunque abbia config. config-assistente.tsx:64 fa POST /api/home/config, che sta in ROTTE_VIETATE (permessi_rotte.py:290) → 403; su !res.ok il toast (:78) dice «Non sono riuscito a salvare le impostazioni. Riprova.». Stessa cosa in sintesi-catena.tsx:383 → config-assistente-catena.tsx:77 POST /api/gruppo/assistant-config, vietata (permessi_rotte.py:292), toast :92 «Riprova». Né i due componenti né le pagine controllano sotto_utente (grep 'sotto_utente' in apps/web/src: nessun uso in dashboard/catena/config-*). Il dialog mostra anche le preferenze del titolare: nome referente, soglia alert, giorni di chiusura, interruttore chat.

**Prova indipendente della verifica.** HEAD dashboard/page.tsx:45 rende ConfigAssistente senza controllo su sotto_utente; sintesi-catena.tsx:383 idem; permessi_rotte.py ROTTE_VIETATE contiene POST /api/home/config e POST /api/gruppo/assistant-config.

**Correzioni della verifica.** Platea oggi zero (nessun sotto-utente esistente): difetto latente.

**File e righe.**

- `apps/web/src/app/(app)/catena/config-assistente-catena.tsx:77-92`
- `apps/web/src/app/(app)/catena/sintesi-catena.tsx:383`
- `apps/web/src/app/(app)/dashboard/config-assistente.tsx:64-78`
- `apps/web/src/app/(app)/dashboard/page.tsx:45`
- `services/permessi_rotte.py:290-292`

**Fix proposto (non applicato).** Non rendere ConfigAssistente/ConfigAssistenteCatena quando session.user.sotto_utente; in alternativa, su 403 un messaggio «Impostazione dell'account: la cambia il titolare» come già fa articoli-tab per il riparto.

**Presidio di test proposto.** Funzione pura in lib (es. mostraConfigAssistente(user)) testata con node: false per sotto_utente, true per il titolare.

**Già presidiato da.** Nessuno.

---

### 21. Le guardie di pagina sono fail-open quando la sessione non è 'ok', e sulla navigazione client il layout (app) non gira: le tab spente dall'admin tornano visibili

`F2b-5` · trovato da F2b-5

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Tutte le pagine con requirePagina, requirePaginaConTab, requireHome, requireCatena e requireTabMobile, in navigazione SPA, quando /api/auth/me va in timeout o dà 5xx due volte ('unavailable') oppure il token è appena stato revocato ('invalid'). Titolari e sotto-utenti.

**Platea misurata in verifica.** Solo sessioni non 'ok' (scaduta, invalida o worker irraggiungibile) durante la navigazione client; nessun sotto-utente oggi.

**Prova del finder.** page-guard.ts:24, :41, :47 e :56 fanno return se session.status !== 'ok'. Il commento :16-20 assume che il layout giri prima, ma la documentazione di Next 16.2.6 inclusa nel repo (apps/web/node_modules/next/dist/docs/01-app/02-guides/authentication.md:1350) dice che i layout «don't re-render on navigation». Con Link (sidebar) l'(app)/layout.tsx:47-76 non rifà quindi il controllo. Eseguito con node lib/tab-flags: con sessione ok e pagine ['prezzi','tab_off_prezzi_score'], risolviTab(…,'score') = 'variazioni' e tabAttive = [variazioni,sconti,nc]; con sessione non ok (pagine=null, page-guard.ts:96), risolviTab(null,'prezzi','score') = 'score' e tabAttive = [variazioni,sconti,nc,score]. Le tab spente esistono solo nel frontend (il worker non le controlla), quindi /api/prezzi/score-fornitori risponde ai dati. Con 'invalid' la pagina si rende con blocchi vuoti (il worker dà 401) invece di andare al login: in apps/web/src non c'è una gestione globale del 401. I dati delle pagine non consentite restano protetti dal 403 del worker.

**Prova indipendente della verifica.** HEAD page-guard.ts:22-26, 39-58: return se session.status !== 'ok', con commento che delega al layout (fail-open dichiarato). Con sessione non ok pero' il worker risponde 401 ai dati: la tab spenta riappare ma senza dati.

**Correzioni della verifica.** Il finder afferma che /api/prezzi/score-fornitori 'risponde ai dati': con sessione scaduta o invalida il worker da' 401, quindi il caso realistico e' una tab vuota visibile, non dati esposti. Impatto cosmetico, fail-open dichiarato nel commento.

**File e righe.**

- `apps/web/src/app/(app)/layout.tsx:47-76`
- `apps/web/src/lib/auth.ts:96-120`
- `apps/web/src/lib/page-guard.ts:16-28`
- `apps/web/src/lib/page-guard.ts:39-58`
- `apps/web/src/lib/page-guard.ts:94-100`

**Fix proposto (non applicato).** Nelle guardie: 'invalid' → redirect('/login'); 'unavailable' → la pagina non si rende (throw o un componente di riprova), invece di proseguire con pagine=null.

**Presidio di test proposto.** Estrarre in lib la decisione delle guardie (status, user, flag) → {passa|404|redirect:x} e testarla con node: status 'unavailable' e 'invalid' non devono dare 'passa'. Provare per mutazione rimettendo il return.

**Già presidiato da.** tests/test_page_guard_tab_frontend.py solo con sessione valida.

---

### 22. lib/fatture.ts mette in cache 60 s mesi-disponibili e categorie con chiave sul token: dopo il cambio sede si vedono quelli della sede precedente

`F2b-6` · trovato da F2b-6

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** /analisi-fatture (selettore mesi, elenco categorie e «usate»), negli account multi-sede, titolari e sotto-utenti con più sedi, fino a 60 s dopo cambia-sede. Con sedi di settore diverso (retail/ristorazione) cambia anche l'elenco categorie ammesse. Account non misurati.

**Platea misurata in verifica.** Account multi-sede che cambiano sede in Analisi Fatture entro 60 s (piu' account oggi hanno piu' sedi).

**Prova del finder.** lib/fatture.ts:137-140: con revalidateSec si usa next:{revalidate}. fetchMesiDisponibili (:174-181) e fetchCategorie (:204-209) passano 60. In Next 16.2.6 la chiave della Data Cache (node_modules/next/dist/server/lib/incremental-cache/index.js:239-256) è [url, method, headers, …]: gli header contengono Authorization: Bearer <token> (lib/worker-config.ts:18-23) ma nessun riferimento alla sede, e l'URL non ha parametri di sede. Il worker invece risolve la sede dalla sessione: fatture.py:327-345 (.eq('ristorante_id', ristorante_id)) e :1046-1070. cambia-sede non cambia il token e non c'è revalidateTag/revalidatePath (grep 'revalidate' in apps/web/src: solo lib/fatture.ts). La sessione resta per persona (token diversi), quindi niente fuga fra persone.

**Prova indipendente della verifica.** HEAD lib/fatture.ts:138-140 usa next:{revalidate} quando revalidateSec e' passato; fetchMesiDisponibili passa 60 con URL senza parametri di sede; node_modules/next/.../incremental-cache/index.js:239-256: chiave = [url, method, headers...], con headers = Authorization del token, che non cambia con cambia-sede. Il worker risolve la sede dalla sessione.

**File e righe.**

- `apps/web/src/lib/fatture.ts:128-150`
- `apps/web/src/lib/fatture.ts:174-181`
- `apps/web/src/lib/fatture.ts:204-210`
- `services/routers/fatture.py:1046-1070`
- `services/routers/fatture.py:327-345`

**Fix proposto (non applicato).** Usare cache:'no-store' come tutte le altre letture; in alternativa includere la sede attiva nella chiave (es. ?sede=<sede_attiva_id> ignorato dal worker), oppure revalidateTag al cambio sede.

**Presidio di test proposto.** Presidio statico: in apps/web/src nessun fetch verso WORKER_URL con next.revalidate o force-cache senza la sede nella chiave; provarlo per mutazione su lib/fatture.ts.

**Già presidiato da.** Nessuno.

---

### 23. Logout e scadenza della sessione non svuotano sessionStorage: la conversazione con l'assistente (cifre e card) resta leggibile nella stessa scheda dopo l'uscita

`F2b-7` · trovato da F2b-7

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** Dispositivo condiviso (tablet di sala): titolare e dipendente nella stessa scheda, uno dopo l'altro. Desktop e /m.

**Platea misurata in verifica.** Browser condivisi in cui si fa logout senza chiudere la scheda; la UI della persona successiva non la mostra (chiave per persona).

**Prova del finder.** assistente-provider.tsx:105 salva la conversazione in sessionStorage sotto chiaveConversazione(idPersona) (home-chat.ts:364-369). handleLogout (app-sidebar.tsx:141-145), logout mobile (header-menu.tsx:94-98) e api/auth/logout/route.ts:8-30 cancellano solo i cookie: nessun sessionStorage.clear e nessun Clear-Site-Data (grep 'sessionStorage' nei tre file → 0). Il commento home-chat.ts:364 ammette che sessionStorage sopravvive al logout. La chiave per persona impedisce alla UI della persona successiva di mostrarla (test_la_conversazione_e_della_persona_non_dell_account), ma il dato resta in chiaro nel browser fino alla chiusura della scheda.

**Prova indipendente della verifica.** HEAD app-sidebar.tsx:141-147 handleLogout: fetch logout + router.push, nessun sessionStorage.clear; grep sessionStorage in src: nessuna pulizia al logout. home-chat.ts:364-366 dichiara che sessionStorage sopravvive al logout e mitiga solo con la chiave per utente.

**File e righe.**

- `apps/web/src/app/(mobile)/m/header-menu.tsx:94-98`
- `apps/web/src/app/api/auth/logout/route.ts:8-30`
- `apps/web/src/components/home/assistente-provider.tsx:88-110`
- `apps/web/src/components/nav/app-sidebar.tsx:141-145`
- `apps/web/src/lib/home-chat.ts:364-369`

**Fix proposto (non applicato).** Al logout rimuovere le chiavi 'oneflux:assistente:*' (o tutto sessionStorage) prima di router.push('/login'); in alternativa header Clear-Site-Data: "storage" sulla risposta di /api/auth/logout.

**Presidio di test proposto.** Funzione pura di pulizia in lib (lista delle chiavi da rimuovere) testata con node su uno Storage finto, chiamata da entrambi i logout.

**Già presidiato da.** tests/test_sotto_utente_frontend.py (chiavi distinte).

---

### 24. Home del sotto-utente: i link di KPI, Salute e «Da fare» portano a pagine che non ha (404)

`F2b-8` · trovato da F2b-8

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** /dashboard di un sotto-utente con Home ma senza margini, analisi_fatture o prezzi. Account non misurati.

**Platea misurata in verifica.** Zero: nessun sotto-utente a DB (sotto_utenti = 0).

**Prova del finder.** kpi-block.tsx:82, :103, :127, :144, :151, :158 hanno link fissi a /margini, /analisi-fatture e /prezzi. salute-card.tsx:38-40 usa v.cta_page arrivato dal worker (fastapi_worker.py:9673, :9681). home-da-fare.ts:59 usa a.cta_page delle azioni del briefing. Nessuno filtra per pagine_abilitate (grep pagine_abilitate in dashboard/ e components/home: solo page.tsx:169 per i trigger). Le pagine mancanti fanno notFound() via requirePagina (page-guard.ts:27). Mostrare i dati è una scelta («Home intera»); il link a un 404 no.

**Prova indipendente della verifica.** Link fissi in kpi-block.tsx e cta_page nella salute non filtrati per pagine_abilitate; requirePagina fa notFound (page-guard.ts:27). Count sotto_utenti = 0 via SQL READ ONLY.

**Correzioni della verifica.** Platea oggi zero: difetto latente.

**File e righe.**

- `apps/web/src/app/(app)/dashboard/kpi-block.tsx:82-158`
- `apps/web/src/app/(app)/dashboard/salute-card.tsx:38-46`
- `apps/web/src/lib/home-da-fare.ts:52-62`
- `apps/web/src/lib/page-guard.ts:27`

**Fix proposto (non applicato).** Passare pagine_abilitate a KpiBlock, SaluteCard e DaFareOggi e togliere il link (lasciando il testo) quando la pagina di destinazione è spenta, con lo stesso mapping percorso→flag di _PAGINA_DI_PERCORSO (permessi_rotte.py:359).

**Presidio di test proposto.** Funzione pura in lib hrefSeConsentito(href, pagine) testata con node, sullo stesso mapping usato da notifica_visibile lato worker.

**Già presidiato da.** Nessuno.

---

### 25. Archivio fatture: il chip «Solo scadute» resta visibile e attivabile ma non cambia l'elenco; checkbox di riga inerti e barra di azioni di massa visibile

`F4-07` · trovato da F4-07

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** /scadenziario e /catena/fatture, scheda Archivio fatture, che è la vista di apertura dal 09/10.

**Platea misurata in verifica.** Chi usa la vista Archivio (lista_mensile) dello scadenziario.

**Prova del finder.** gruppiMensili nasce da documentiCalendario, che ignora il periodo (:2046-2049). Esecuzione: con periodo='scadute' raggruppaPerMeseFattura(documentiCalendario) dà sempre 3/10/3 documenti, cioè tutti e 16. Il blocco Tutti/Solo scadute (:2335-2344) non è nascosto in lista_mensile, a differenza di Settimana e Mese (:2349, il cui commento dice proprio «un chip che si accende e non cambia l'elenco è peggio di un chip assente»). Il chip attivo fa anche comparire «Pulisci filtri». DocumentoRow disegna sempre la checkbox (:187-193), ma in Archivio onToggleSelect è `() => {}` (:2530), quindi il clic non fa niente. La barra «N selezionate / Segna pagate» (:2566) non ha guardia di vista e resta a video con una selezione fatta nello Scadenzario.

**Prova indipendente della verifica.** HEAD: gruppiMensili = raggruppaPerMeseFattura(documentiCalendario) (2046-2049), che ignora il periodo; blocco Tutti/Solo scadute senza guardia di vista (2335-2344); DocumentoRow disegna sempre la checkbox (187-193) e in Archivio onToggleSelect={() => {}} (2530); la barra azioni di massa (2566) dipende solo da selectedFileOrigini.size>0.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:187-193`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2046-2049`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2335-2349`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2529-2531`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2566`

**Fix proposto (non applicato).** Nascondere il gruppo Tutti/Solo scadute in lista_mensile, oppure azzerare il periodo entrando in Archivio. Non disegnare la checkbox quando mostraScadenze=false. Mostrare la barra di massa solo con view==='agenda'.

**Presidio di test proposto.** Guardia sul sorgente del ramo lista_mensile, da provare per mutazione.

**Già presidiato da.** Parziale: test_scadenziario_vista_mensile_frontend.py (solo il messaggio di elenco vuoto).

---

### 26. Esito parziale dell'azione di massa: il toast dice «Errore nel salvataggio» anche quando parte delle fatture è stata scritta

`F4-10` · trovato da F4-10

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** /scadenziario e /catena/fatture, barra «Segna pagate» / «Segna non pagate».

**Platea misurata in verifica.** Zero per il caso deterministico citato: query a DB, documenti attivi in fatture senza header in fatture_documenti = 0. Resta solo il fallimento transitorio di un gruppo.

**Prova del finder.** Codice. handleBulkPaga continua sui gruppi successivi dopo un ok:false (:1858 `continue`), scarta `aggiornate` e mostra solo toast.error + loadData (:1862). Il server scrive ogni file_origine singolarmente e restituisce ok=false se anche uno solo fallisce (routers/scadenziario.py:186-203). Dopo il reload il cliente si ritrova pagate le fatture riuscite sotto un messaggio di errore generico. Un fallimento deterministico c'è: un documento senza riga in fatture_documenti compare in lista (get_documenti_scadenziario parte da `fatture`, :640-641) ma segna_fattura_pagata dà «Fattura non trovata» (:609-613). Se un Seleziona tutte lo include, ogni Segna pagate termina in errore pur scrivendo le altre. Quanti siano oggi questi documenti non è misurato.

**Prova indipendente della verifica.** HEAD scadenziario-client.tsx:1857-1862: su ok:false si fa continue, poi toast.error('Errore nel salvataggio') + loadData scartando 'aggiornate'. SQL BEGIN READ ONLY: count(distinct user_id,ristorante_id,file_origine) di fatture attive senza fatture_documenti corrispondente = 0.

**Correzioni della verifica.** Il fallimento deterministico ipotizzato (documento in lista senza riga in fatture_documenti) ha platea 0 oggi: il difetto vale solo per errori transitori o parziali del worker.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1843-1872`
- `services/documenti_service.py:609-613`
- `services/routers/scadenziario.py:179-203`

**Fix proposto (non applicato).** Sommare aggiornate anche sui gruppi falliti, leggere `dettaglio` e mostrare «N segnate, M non riuscite» con i nomi dei falliti. Valutare se rendere selezionabili i documenti senza header.

**Presidio di test proposto.** Estrarre in lib una funzione che compone l'esito dai responsi per gruppo, con test node sul caso misto ok/ko.

**Già presidiato da.** Nessuno sul caso parziale.

---

### 27. Vista gruppo: «Svuota questa sede» non dice quale sede, compare anche quando quella sede non ha nulla nel cestino e risponde «Cestino svuotato»

`F4-11` · trovato da F4-11

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** /catena/fatture, pannello Cestino.

**Platea misurata in verifica.** Solo account con catena (vista di gruppo dello scadenziario) che usano il cestino.

**Prova del finder.** Codice. Il cestino di gruppo elenca le fatture di tutte le sedi (gruppo.py:1950-1953). Il bottone appare se cestinoItems.length>0 (:2186), con le scritte «Svuota questa sede» / «Elimini il cestino di questa sede?» (:2190, :2212) e nessun nome di sede. Il server svuota la sola sede di sessione (cestino.py:184-198 → _resolve_ristorante_id). Se gli elementi sono tutti di altre sedi, svuota_cestino ritorna success con righe_eliminate 0 (db_service.py:1968-1969) e il client mostra «Cestino svuotato» (:2007) con la lista invariata dopo loadCestino. Il riferimento a «questa sede» in una pagina di gruppo non individua la sede: l'utente non sa quali fatture stia cancellando definitivamente.

**Prova indipendente della verifica.** HEAD: il commento a 2183-2185 dichiara «In catena il bottone dice quale sede svuota», ma il testo resta «Elimini il cestino di questa sede?» senza nome (2190); handleCestinoSvuota mostra 'Cestino svuotato' su ogni success (2007); cestino.py:184-198 svuota solo la sede risolta da _resolve_ristorante_id. Il commento promette il nome della sede che il codice non mostra.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2001-2011`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2186-2212`
- `services/db_service.py:1968-1969`
- `services/routers/cestino.py:184-198`

**Fix proposto (non applicato).** Mettere il nome della sede attiva nell'etichetta e nella conferma, mostrare il bottone solo se fra gli elementi c'è quella sede, e usare righe_eliminate nel toast.

**Presidio di test proposto.** Guardia sul .tsx e test endpoint con mock esplicito sul conteggio 0.

**Già presidiato da.** Nessuno.

---

### 28. Calendario in browser conta le fatture escluse dai conti

`K02` · trovato da F1e-09, F1d-03, F4-04

| | |
|---|---|
| Filone | 1 — Quadrature numeriche + 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Gestione Fatture → vista Calendario (sede e catena): totale del giorno, intensità della casella, totale mese; sulla stessa pagina i KPI e «scaduteFuoriDalMese» la escludono. Account con fatture oscurate non pagate con scadenza.

**Platea misurata in verifica.** NON RIMISURATA: il DB non si raggiungeva. execute_sql ha fallito 4 volte su 4 con «getaddrinfo ENOTFOUND mcp-proxy.anthropic.com», compresa una COUNT banale su fatture.oscurata. L'unica cifra di platea disponibile è quella del finder F1d-03, che non ho verificato: 1 documento oscurato in tutto il DB (user 080004f3), 0 non pagati con scadenza a ottobre 2026 o successiva, quindi oggi nessuna casella del calendario sarebbe sbagliata. Il difetto si attiva però con un solo clic, «Escludi dai conti» su una fattura non pagata con scadenza nel mese: è una funzione in produzione, disponibile per ogni sede e per la catena. Query da rilanciare per chiudere la gravità: BEGIN READ ONLY; WITH osc AS (SELECT DISTINCT user_id, ristorante_id, file_origine FROM fatture WHERE oscurata AND deleted_at IS NULL) SELECT count(*), count(DISTINCT o.user_id), count(*) FILTER (WHERE fd.pagata IS NOT TRUE AND COALESCE(fd.scadenza_override, fd.scadenza_effettiva, fd.scadenza_xml) >= date '2026-10-01') FROM osc o LEFT JOIN fatture_documenti fd ON fd.file_origine=o.file_origine AND fd.ristorante_id=o.ristorante_id AND fd.deleted_at IS NULL; COMMIT;. Se il terzo conteggio è 0 la gravità scende a bassa; se è maggiore di 0 su un account reale sale ad alta.

**Atteso contro mostrato.** Dataset sintetico ottobre 2026: calendario mostra 1.600 € (500 il 21 + 1.100 il 23); atteso 1.100 € (solo il 23), come dà il worker.

**Prova del finder.** CalendarView (scadenziario-client.tsx:489-506) salta solo `doc.pagata` e `doc.is_nota_credito`; riceve documentiCalendario (:2562, :1775-1783) che include le oscurate (eseguito: filtraDocumenti con periodo «tutti» → oscurata inclusa = true). Replica della logica inline con node sul dataset: ottobre 2026 → {21: 500 (esclusa), 23: 1100}, totale 1.600; il worker /api/scadenziario/calendario (routers/scadenziario.py:143-151) salta anche `oscurata` → {23: 1100}; statoDocumento(osc) = «Escluse da te» (lib :560); computeKpi da_pagare_totale = 1100; scaduteFuoriDalMese esclude via statoDocumento (:600). La route Next api/scadenziario/calendario/route.ts esiste ma nessun .tsx la chiama (grep «api/scadenziario/calendario» fuori da route.ts vuoto).

**Prova indipendente della verifica.** CODICE A HEAD: ultimi commit sui tre file del 9/10, nessuna correzione. In apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx, CalendarView (righe 489-509, agg) e dayDocs (righe 528-536) saltano solo doc.pagata e doc.is_nota_credito. documentiCalendario (righe 1775-1783) usa filtraDocumenti con periodo «tutti», e matchDocumento in lib/scadenziario.ts non filtra oscurata (grep vuoto). Le altre viste della stessa pagina invece le escludono: computeKpi (lib righe 121 e 335), bucketizeDocumenti (riga 401), scaduteFuoriDalMese via statoDocumento. Le esclude anche il worker services/routers/scadenziario.py:148-153, con il commento «Esclusa dai conti = esclusa anche dalle scadenze». La route Next api/scadenziario/calendario/route.ts non ha chiamanti: grep su apps/web/src trova solo il file stesso.
ESECUZIONE MIA (node via tests/helpers_ts.esegui_ts su lib/scadenziario): 2 documenti di ottobre 2026, uno oscurato da 500 € il giorno 21 e uno normale da 1.100 € il 23. filtraDocumenti con periodo «tutti» restituisce [osc, ok]; la regola di CalendarView applicata sopra dà {21: 500, 23: 1100}, cioè 1.600 € a video. statoDocumento restituisce «Escluse da te» per il primo e «Da pagare» per il secondo, quindi i KPI della stessa pagina contano solo 1.100 €.
NON DELIBERATO: il test tests/test_scadenziario_calendario_fuori_mese_frontend.py:103 dice «Gli stessi tre esclusi del calendario e dei KPI»; l'autore credeva quindi che il calendario escludesse le oscurate. Nessun documento lo dichiara come scelta.
PRESIDIO: nessun test copre la griglia. test_scadenziario_filtri_frontend.py:430 fissa periodo «tutti» ma non le oscurate, e MAPPA_NUMERI elenca «calendario browser con oscurate» fra i punti non coperti da test.

**Correzioni della verifica.** 1) Gravità: non «alta» come in F1e-09. Non risulta un numero sbagliato a video su clienti reali: F1d-03 misura 0 casi (cifra non rimisurata da me, DB irraggiungibile). Fra le gravità dei finder scelgo media e non bassa per due ragioni: l'innesco è un'azione ordinaria del cliente, e quando scatta il calendario contraddice i KPI della stessa pagina. Se la query di platea conferma 0 resta bassa/media. 2) Perimetro: oltre alla griglia agg (righe 497-506) c'è anche dayDocs (righe 528-536): la lista del giorno selezionato mostra l'oscurata. Vale sia per la sede sia per la catena (/catena/fatture usa lo stesso componente). 3) Le righe del worker sono 148-153, non 143-151.

**Nota della sintesi.** Platea misurata dall'agente delle contraddizioni, perche' il refutatore di questo gruppo non raggiungeva il DB: in tutto il database c'e' 1 sola fattura esclusa dai conti (account 080004f3, 382,83 €, scadenza 02/06/2026, non pagata). Oggi compare solo navigando il calendario a giugno 2026: la gravita' scende a bassa. Il difetto resta vero e si attiva al primo «Escludi dai conti» su una fattura con scadenza futura.

**Deliberato dove.** Non è deliberato. Il commento del test calendario_fuori_mese:103 presume il contrario, e il worker esclude esplicitamente le oscurate con un commento motivato.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1775-1783`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2562`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:489-506`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:495-509`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:497-506 (CalendarView agg: manca `if (doc.oscurata) continue`)`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:528-536`
- `apps/web/src/app/api/scadenziario/calendario/route.ts`
- `apps/web/src/lib/scadenziario.ts:559-567 (statoDocumento esclude oscurata)`
- `apps/web/src/lib/scadenziario.ts:559-568`
- `apps/web/src/lib/scadenziario.ts:591-608`
- `services/routers/scadenziario.py:143-151`
- `services/routers/scadenziario.py:144-153`
- `services/routers/scadenziario.py:148-156 (endpoint calendario esclude oscurata)`

**Fix proposto (non applicato).** Estrarre in lib/scadenziario.ts una funzione di aggregazione del calendario per giorno, più la lista del giorno, basata su statoDocumento (contano solo «Scaduta» e «Da pagare»), e usarla sia in agg sia in dayDocs di CalendarView.

**Presidio di test proposto.** Test node sulla nuova funzione di lib: un'oscurata non pagata con scadenza nel mese non deve comparire né nelle caselle né nella lista del giorno. Va provato per mutazione togliendo l'esclusione delle oscurate. Va corretto anche il commento a test_scadenziario_calendario_fuori_mese_frontend.py:103, oggi falso.

**Già presidiato da.** Nessuno per la griglia e la lista del giorno: test_scadenziario_calendario_fuori_mese_frontend.py:102 copre solo scaduteFuoriDalMese, test_scadenziario_oscurate_frontend.py copre KPI, sezioni e sedi.

---

### 29. Vista gruppo: selezione e aggiornamento a video per solo file_origine

`K04` · trovato da F4-01, F4-02, F4-03

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Gestione Fatture vista di gruppo /catena/fatture, scheda Scadenzario. Non succede in vista sede (/scadenziario mono-sede: lì un file_origine compare una volta sola). Mobile: nessuna pagina scadenziario sotto (mobile)/m. Quali account siano toccati non è misurato: il compito escludeva il DB.

**Platea misurata in verifica.** Zero. Nessuna fattura oggi si trova su più sedi con lo stesso file_origine. Su fatture, raggruppando per (user_id, btrim(file_origine)) con count(distinct ristorante_id)>1, i casi sono 0 su 3645 coppie, contando anche le righe nel cestino. Gli account con più sedi sono 3, sede tecnica compresa: user 51015cc8, 5 sedi, 2582 file_origine attivi, 0 su più sedi; user 2f3f93a1, 3 sedi di cui 1 tecnica, 569 attivi, 0 su più sedi; user 603f7125, 2 sedi, nessuna fattura. Lo scadenziario di gruppo prende le righe solo dalla RPC scadenziario_fatture_aggregate, che legge fatture con deleted_at IS NULL, raggruppa per (file_origine, ristorante_id) e viene ciclata in documenti_service.py su agg.items(). Quindi oggi nessuna lista a video contiene due righe con lo stesso file_origine e i tre effetti descritti non si possono innescare. Su fatture_documenti ci sono 233 file_origine su più sedi, ma sono tutte intestazioni nel cestino: le attive sono 0, e non compaiono nell'elenco perché l'elenco nasce da fatture. Le 201 fatture attive con ripartita_su_gruppo restano ciascuna su una sola sede. Il caso però può nascere: il controllo dei doppioni al caricamento vale per singola sede (indice uq_fatture_dedup su user_id, ristorante_id, file_origine, numero_riga e _trova_documento_duplicato_per_identita con ristorante_id), quindi niente impedisce lo stesso nome file, per esempio un PDF caricato a mano, su due sedi dello stesso account.

**Prova del finder.** Eseguito con node lib/scadenziario.ts su un dataset sintetico in cui DUP2.xml è aperta su rA e su rB e DUP.xml è aperta su rA e pagata su rB. (a) Una spunta sulla riga di rA, cioè selezione {DUP2.xml}: pianoAzioneDiMassa → gruppi [{rA:[DUP2.xml]},{rB:[DUP2.xml]}], cambiano 2. La barra dice «1 selezionata», la conferma «2 fatture per 100 €». Con il filtro punto vendita = rA la riga di rB non è visibile (visibiliConFiltroA=[rA]) ma viene scritta lo stesso, perché il piano gira su `documenti` e non sui filtrati (client :1731-1738, voluto dal test :314). (b) Con Seleziona tutte su [X1@rA aperta, DUP@rA aperta, DUP@rB pagata], motivoAzioneSpenta(pianoNonPagate) restituisce null, quindi «Segna non pagate» è ACCESO. Invia {rB:[DUP.xml]} e la conferma dice «1 fattura per 120 € tornerà fra quelle da pagare, e la data di pagamento verrà rimossa». Sullo stesso dataset in mono-sede il pulsante è spento e i gruppi sono []. Lato server segna_fattura_pagata scrive pagata=false, pagata_at=null e pagata_manuale_at (documenti_service.py:557-570), e pagata_manuale_at spegne l'automatismo RID su quella fattura. (c) statoSelezioneSezione(Scadute, ['DUP2.xml']) dà selezionati=2: un clic spunta due righe.

**Prova indipendente della verifica.** CODICE A HEAD. Ultimo commit sui file 4e44c781 del 9/10. In lib/scadenziario.ts chiaviSelezionaTutte fa .map(d => d.file_origine), statoSelezioneSezione usa set.has(d.file_origine) e pianoAzioneDiMassa usa `if (!set.has(d.file_origine)) continue` e raggruppa per d.ristorante_id. Nel client, selectedFileOrigini è un Set<string> di soli file_origine. toggleSelect e toggleAll usano d.file_origine. handleBulkPaga calcola il piano su `documenti`, non sulla lista filtrata. handleSetScadenza aggiorna con `d.file_origine === doc.file_origine`, mentre handleElimina e handleSpostata filtrano con `d.file_origine !== doc.file_origine`. Il commento in handleOscura ammette il difetto in handleElimina e handleSetScadenza («preesistente, non allargato qui»): è riconosciuto, non deliberato.

ESECUZIONE NODE. Ho usato esegui_ts su lib/scadenziario con un dataset mio: X1 su rA aperta, DUP su rA aperta, DUP su rB pagata, DUP2 aperta su rA e su rB.
(a) Un piano con la sola selezione ['DUP2'] produce gruppi rA:[DUP2] e rB:[DUP2]: una spunta scrive su due sedi.
(b) Seleziona tutte dà le chiavi [X1, DUP, DUP2, DUP2]: sono 4, ma new Set ne conta 3. Il piano «non pagate» produce i gruppi [rB:[DUP]], con motivoAzioneSpenta uguale a null, quindi il pulsante è acceso e toglie il pagamento a DUP@rB, che nessuno ha selezionato. Il piano «pagate» dà cambiano=4 e giaCosi=1. In vista sede, con il dataset ridotto a rA, il piano «non pagate» dà gruppi [] e il motivo «Le fatture selezionate sono già tutte da pagare».
(c) statoSelezioneSezione sulle righe DUP2 con selezione ['DUP2'] dà selezionabili=2 e selezionati=2.

PRESIDI. pytest su test_scadenziario_azione_di_massa_frontend.py e test_scadenziario_contatore_frontend.py: 70 passati. Nessuno di questi test usa lo stesso file_origine su due sedi.

DB, sola lettura: query sopra, scritte da me.

**Correzioni della verifica.** Il meccanismo dei tre finding regge ed è riprodotto: F4-01 (selezione e azione di massa su tutte le sedi che hanno lo stesso file_origine), F4-02 (tre conteggi diversi) e F4-03 (handleElimina e handleSetScadenza aggiornano a video per solo file_origine). Va corretta la gravità: da alta, e da media per F4-02 e F4-03, a bassa per tutti e tre. Su tutti gli account con più sedi, sede tecnica inclusa, 0 file_origine su 3645 stanno su più di una sede, anche contando il cestino, quindi oggi nessun cliente può innescare i casi descritti. Resta un bug vero e latente, perché il controllo dei doppioni al caricamento vale per singola sede. Il perimetro «Quali account siano toccati non è misurato» va sostituito con «misurato il 15/10/2026: nessuno». Altre due precisazioni. Le 233 coppie su più sedi in fatture_documenti sono tutte nel cestino e non arrivano a video. handleSpostata ha la stessa chiave, ma in catena non si raggiunge: lo dice già il finder.

**Deliberato dove.** Non è deliberato. Il commento in handleOscura (scadenziario-client.tsx, circa :1927-1931) lo riconosce come difetto preesistente di handleElimina e handleSetScadenza, lasciato aperto.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1642`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1731-1738`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1798-1823`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1882-1891`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1907`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1927-1936`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2042`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2461-2464`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2566-2569`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2615-2620`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:319-324`
- `apps/web/src/lib/scadenziario.ts:158-160`
- `apps/web/src/lib/scadenziario.ts:189-201`
- `apps/web/src/lib/scadenziario.ts:225-250`
- `services/documenti_service.py:557-570`
- `services/routers/cestino.py:229-238`

**Fix proposto (non applicato).** Come propone il finder: usare la chiave `${ristorante_id ?? ''}|${file_origine}`, la stessa di applicaPagataAVideo, in chiaviSelezionaTutte, statoSelezioneSezione, pianoAzioneDiMassa (set.has), toggleSelect e toggleAll, e nel key/selected/onToggleSelect della riga (client :321-324). In handleElimina e handleSetScadenza, e per coerenza in handleSpostata, va usato il match di handleOscura (file_origine e ristorante_id). Priorità bassa: oggi la platea è nulla.

**Presidio di test proposto.** Test node in test_scadenziario_azione_di_massa_frontend.py con lo stesso file_origine su due sedi, da provare per mutazione riportando la chiave al solo file_origine. Tre casi. (1) Selezionare la riga di una sede produce gruppi solo per quella sede. (2) Con Seleziona tutte e un omonimo pagato sull'altra sede, il piano «non pagate» ha gruppi [] e motivoAzioneSpenta diverso da null. (3) chiaviSelezionaTutte(D).length deve essere uguale a new Set(chiavi).size e a cambiano.length, con giaCosi=0.

**Già presidiato da.** Nessuno. test_a_video_in_catena_la_chiave_include_la_sede copre solo applicaPagataAVideo. test_in_catena_raggruppa_per_sede usa file_origine tutti distinti. test_handle_bulk_paga_manda_solo_il_piano verifica che il piano giri su `documenti`, cosa compatibile con il fix.

---

### 30. Chat: crediti consumati su domande fallite

`K17` · trovato da F3-03

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Chat sede e catena, desktop e /m: tutti gli account. Con crediti del mese finiti si consuma la ricarica pagata.

**Platea misurata in verifica.** Dal 05/06/2026 (primo evento chat in ai_usage_events) a oggi ci sono 134 domande in chat_usage_log. 2 non hanno un evento 'chat' in ai_usage_events entro 90 secondi, quindi sono domande scalate senza risposta riuscita (o con il tracking fallito): 6 crediti in tutto, 0 da ricarica, 2 utenti (51015cc8 il 25/09, 080004f3 il 30/09). Nessun caso dal 01/10.

**Prova del finder.** La RPC chat_crediti_check_and_log fa INSERT in chat_usage_log prima della chiamata OpenAI (migration 20261010135911_chat_crediti_ricariche.sql:189; chiamata a fw:6220). I rifiuti prima della RPC non consumano: 403 sotto-utente (fw:6148-6151), 400 catena con una sola sede (fw:6159-6171), 403 piano free, catena spenta, chat spenta (fw:6188-6214); 429 della quota esce prima dell'INSERT (migration :161,181,185). Dopo la RPC non esiste compensazione: grep 'rimbors|storn|refund' in fastapi_worker.py dà 0 risultati. Gli 8 strumenti di sede non fase F non hanno try (AST: query_costi, scadenze, appuntamenti, ultimi_acquisti, trend, confronto con 0 try). Un'eccezione risale a esegui_tool (fw:4618) e diventa 502 (fw:4635); solo la fase F è protetta (fw:5960-5974). Eseguito con node: dopo 502 o 504 contatoreAggiornato(data senza crediti_oggi) restituisce i crediti di prima e statoCrediti mostra 'Ti restano 894 crediti', mentre il server ne ha scalati 3 (CHAT_CREDITI_PER_DOMANDA=3, fw:3048).

**Prova indipendente della verifica.** L'RPC _chat_crediti_consuma gira prima del loop OpenAI (fw:6218-6226). Dopo non c'è nessuno storno: grep rimbors|storn|refund in fastapi_worker.py dà 0. In _chat_esegui_tool_sede (fw:5913-5978) solo il ramo fase F ha try. Gli altri strumenti fanno risalire l'eccezione, che il generico except di _chat_loop_openai trasforma in 502 (fw:4632-4635). contatoreAggiornato senza crediti_oggi, eseguito con node, restituisce i crediti di prima. Misura a DB con una mia query: confronto di chat_usage_log con ai_usage_events(operation_type='chat'), che track_ai_usage scrive solo dopo il loop riuscito (fw:6338-6345, 6406-6416).

**Correzioni della verifica.** La gravità scende a bassa: in 4 mesi 2 domande su 134 (1,5%) e 6 crediti, nessuno di ricarica. Lo scenario «consuma la ricarica pagata» è possibile ma oggi ha zero casi. Il dato a DB è un limite superiore: una delle 2 potrebbe essere un fallimento del solo tracking dei costi.

**File e righe.**

- `apps/web/src/lib/home-chat.ts:149-159`
- `services/fastapi_worker.py:4580-4636`
- `services/fastapi_worker.py:5913-5978`
- `services/fastapi_worker.py:6218-6226`
- `supabase/migrations/20261010135911_chat_crediti_ricariche.sql:139-195`

**Fix proposto (non applicato).** Mettere un try per ogni strumento di sede, come per la fase F. Per i fallimenti dopo la RPC, aggiungere uno storno idempotente oppure una decisione documentata; nella risposta d'errore includere i crediti aggiornati.

**Presidio di test proposto.** Test su chat_ai con uno strumento che solleva un'eccezione: risposta 200 con l'errore passato al modello, oppure storno verificato.

**Già presidiato da.** Nessuno sui guasti dopo la RPC. tests/test_chat_catena_quota_non_consumata.py copre solo i rifiuti prima della RPC.

---

### 31. /m diario e turni aperte a chi ha solo Strumenti

`K24` · trovato da F2b-1

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** PWA /m (bottom-nav «Agenda» e «Movimenti»): qualunque sotto-utente con 'workspace' acceso e 'agenda' spenta. Un sotto-utente con la sola pagina Strumenti atterra proprio lì (primaTabMobile → /m/diario). Account toccati non misurati: il filone è solo codice, senza DB.

**Platea misurata in verifica.** Non misurata da me (niente accesso al DB). Per la misura del finder K27, sotto_utenti conta 0 righe, quindi la platea è zero. Il difetto scatta solo per un sotto-utente con 'workspace' acceso e 'agenda' spenta.

**Prova del finder.** Eseguito con node lib/sotto-utente.ts su {sotto_utente:true, pagine:['workspace']}: vedeTabMobile('/m/diario') = true, vedeTabMobile('/m/turni') = true, tabMobileNascoste = ['/m/briefing','/m/chat'], primaTabMobile = '/m/diario'. Le 20 rotte che chiamano mobile-diario.tsx (:101,:285,:320), mobile-spese.tsx (:113,:230,:262), mobile-incassi.tsx (:118,:231,:270) e mobile-turni.tsx (:210,:358,:368,:424,:704,:712,:876-879,:922) le ho estratte da services/permessi_rotte.py con ast e passate alla stessa regola di rotta_consentita (:339-348). Esito: 0 su 20 consentite con {workspace}; 20 su 20 con {agenda}; 3 su 20 con {workspace,margini} (solo /api/ricavi/giornalieri). PAGINE_PER_ROTTA dà _p(A) a workspace/diario, spese, personale e dipendenti (:154-184) fin dal primo commit 46ab02a6. Il commento di sotto-utente.ts:63-64 («che il worker apre con Agenda oppure Strumenti») è quindi falso. ha_pagina(user,'agenda') vuole pagine['agenda'] is True (sotto_utenti_service.py:241-251): non c'è nessun alias workspace→agenda.

**Prova indipendente della verifica.** Ultimo commit su sotto-utente.ts e permessi_rotte.py: 6eac8fb5 del 14/10; nessuno tocca questa regola. sotto-utente.ts:73 contiene `return pagine.includes("agenda") || pagine.includes("workspace");`, introdotto da bea4a451 il 30/9. Con node, via tests.helpers_ts.esegui_ts, sull'utente {sotto_utente:true, pagine_abilitate:['workspace']}: tabMobileNascoste = ['/m/briefing','/m/chat'] e primaTabMobile = '/m/diario'. Ho passato a rotta_consentita (Python, puro) le 29 rotte di PAGINE_PER_ROTTA con prefisso /api/workspace/{diario,spese,personale,dipendenti} o /api/ricavi/giornalieri: con le pagine {workspace} ne passano 0 su 29, con {agenda} 29 su 29. In tutta la storia di permessi_rotte.py (15 commit, da 46ab02a6) la regola su GET /api/workspace/diario è sempre stata _p(A). ha_pagina (sotto_utenti_service.py) vuole pagine.get(pagina) is True, senza alias da workspace ad agenda. mobile-diario.tsx, mobile-spese.tsx e mobile-turni.tsx chiamano le rotte /api/workspace/*. tests/test_sotto_utente_frontend.py:93 fissa il comportamento errato.

**Correzioni della verifica.** Classificazione e meccanismo sono corretti. La gravità scende da media a bassa per due ragioni. Il difetto è fail-closed: il worker risponde 403, nessun dato visibile a chi non deve, solo tab vuote o in errore. La platea è zero (0 sotto-utenti secondo il finder K27; da ri-misurare a DB). Una precisazione: la riga del test che fissa il comportamento errato è la :93 (`_nascoste(_su(["workspace"])) == ["/m/briefing", "/m/chat"]`), non la :95. Le rotte toccate sono 29 contando tutte quelle di diario, spese, personale, dipendenti e ricavi/giornalieri. Il finder ne conta 20, cioè quelle chiamate dai .tsx: la conclusione non cambia.

**Deliberato dove.** Non è deliberato in modo coerente. Il commento di sotto-utente.ts:63-64 dichiara che il worker apre quelle rotte «con Agenda oppure Strumenti», ma il worker non le ha mai aperte con Strumenti (_p(A) dal primo commit). È una premessa falsa, non una scelta.

**File e righe.**

- `apps/web/src/app/(mobile)/m/bottom-nav.tsx:18-19`
- `apps/web/src/app/(mobile)/m/diario/page.tsx:9`
- `apps/web/src/app/(mobile)/m/turni/page.tsx:10`
- `apps/web/src/lib/sotto-utente.ts:62-76`
- `apps/web/src/lib/sotto-utente.ts:83-88`
- `services/permessi_rotte.py:153-184`
- `services/permessi_rotte.py:99-102`
- `tests/test_sotto_utente_frontend.py:95`

**Fix proposto (non applicato).** In vedeTabMobile, TAB_MOBILE_AGENDA va con pagine.includes('agenda') soltanto, e si corregge il commento a :63-64. Va scartata l'alternativa di aprire le rotte con W: darebbe al sotto-utente più di quanto ha (vedi la regola «sotto-utente solo in meno»).

**Presidio di test proposto.** Correggere test_sotto_utente_frontend.py:93 in modo che con ['workspace'] risultino nascoste tutte e quattro le tab. Aggiungere un test di coerenza: per ogni tab mobile visibile con un insieme di pagine, le rotte chiamate dal suo .tsx devono passare rotta_consentita con quelle pagine. Da provare per mutazione, rimettendo la clausola `|| includes("workspace")`.

**Già presidiato da.** Nessun presidio. test_sotto_utente_frontend.py:93 asserisce il comportamento sbagliato e manca un test di coerenza TS↔Python.

---

### 32. Sotto-utente con Catena senza Home

`K25` · trovato da F2b-2, F2a-3

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi + 3 — Assistente e chat di catena |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Desktop, sidebar in vista catena (scelta di una sede) e /catena (pulsante «Apri PV» della sintesi). Mobile, menu ⋮ → «Vista catena». Tocca i sotto-utenti con pagine {catena, …} senza 'home': combinazione consentita da valida_permessi e dal pannello admin. Account non misurati: filone solo codice.

**Platea misurata in verifica.** 0 sotto-utenti in produzione: select count(*) from sotto_utenti = 0.

**Prova del finder.** Eseguito con node su {sotto_utente:true, num_sedi:2, pagine:['catena','analisi_fatture']}: haHome=false, haCatena=true, primaPaginaAbilitata()= '/catena'. app-sidebar.tsx:236, quando inChain, fa router.push('/dashboard') dopo cambiaSedeEAttendi; sintesi-catena.tsx:358/:411 fa vaiAlPV(id) con page='/dashboard'. /dashboard chiama requireHome (page-guard.ts:39-43) → redirect(primaPaginaAbilitata) = '/catena', e la sidebar riscrive il cookie 'chain' (:202-206). In vista catena la sidebar mostra solo le voci di catena (:282-321), non visibleNav: dalla UI il sotto-utente non arriva alle pagine di sede, salvo un avviso con action_page o un URL scritto a mano. Su mobile header-menu.tsx:68-73 scrive 'chain' e va a /m/briefing; requireTabMobile reindirizza a primaTabMobile ('/m/diario' con agenda, altrimenti '/m/impostazioni'). Il layout (m/layout.tsx:73,:102) calcola inChain = haCatena && cookie!='pv' e scrive «Tutti i punti vendita» sopra dati della sola sede attiva. valida_permessi (sotto_utenti_service.py:304-356) non vieta catena senza home.

**Prova indipendente della verifica.** Query DB: sotto_utenti conta 0 righe. Il codice citato (requireHome che reindirizza a primaPaginaAbilitata '/catena', vaiAlPV verso '/dashboard') non e' stato toccato dagli ultimi commit; la convergenza di due finder regge.

**Correzioni della verifica.** La gravita' media di F2b-2 scende a bassa perche' la platea oggi e' zero. Resta un bug vero per la combinazione catena senza home, che valida_permessi consente. F2a-3 (chat di catena senza Home) e' un'incoerenza di regola fra desktop e /m, anch'essa senza platea, e richiede una decisione di Mattia.

**Deliberato dove.** CHAT_ASSISTENTE.md:239-241 rende deliberata la chat di catena con la sola Catena, ma sotto_utenti_service.py:37 dice «Home = accesso all'AI»: le due frasi si contraddicono.

**File e righe.**

- `DOCUMENTAZIONE/tecnica/CHAT_ASSISTENTE.md:239-241`
- `apps/web/src/app/(app)/catena/page.tsx:62-65`
- `apps/web/src/app/(app)/catena/sintesi-catena.tsx:358-372`
- `apps/web/src/app/(app)/catena/sintesi-catena.tsx:411`
- `apps/web/src/app/(mobile)/m/header-menu.tsx:68-73`
- `apps/web/src/app/(mobile)/m/layout.tsx:102`
- `apps/web/src/app/(mobile)/m/layout.tsx:73`
- `apps/web/src/components/nav/app-sidebar.tsx:233-237`
- `apps/web/src/lib/page-guard.ts:39-43`
- `apps/web/src/lib/sotto-utente.ts:51-54`
- `apps/web/src/lib/sotto-utente.ts:63-71`
- `services/fastapi_worker.py:6149-6152`
- `services/permessi_rotte.py:213-214`

**Fix proposto (non applicato).** Il drill-down catena→PV deve atterrare sulla prima pagina di sede abilitata; su /m nascondere «Vista catena» a chi non ha la Home, oppure far rifiutare dal pannello admin la combinazione catena senza home.

**Presidio di test proposto.** Test node su lib/sotto-utente: per ogni combinazione con haCatena && !haHome, la destinazione del drill-down a un PV non è '/catena' né '/dashboard'. Va provato per mutazione rimettendo '/dashboard'.

**Già presidiato da.** sonda test_sonda_chat_catena_con_sola_catena_senza_home (solo per la parte chat)

---

### 33. Dismiss di una notifica non visibile al sotto-utente

`K27` · trovato da F2a-1

| | |
|---|---|
| Filone | 2 — Sotto-utenti e permessi |
| Classificazione | bug vero |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Titolare dell'account (campanella /notifiche, /m/notifiche, Home di catena /api/gruppo/notifiche): la notifica sparisce dalla sua inbox (include_dismissed=False). Nessun account toccato oggi: 0 sotto-utenti in produzione (SELECT count(*) FROM sotto_utenti = 0). Vale per qualunque account a cui l'admin crei un sotto-utente senza Home.

**Platea misurata in verifica.** Zero secondo il finder (sotto_utenti = 0 righe); non ri-misurato da me, niente accesso al DB. Riguarda un sotto-utente senza Home, che conosca l'uuid di una notifica della sua sede che porta a una pagina che non ha.

**Atteso contro mostrato.** atteso dismissed_at NULL (notifica non visibile al chiamante); ottenuto dismissed_at valorizzato e notifica sparita per il titolare

**Prova del finder.** Sonda su Postgres locale (scratchpad/audit/F2a/test_sonda.py::test_sonda_dismiss_senza_la_pagina_archivia_anche_per_il_titolare): sotto-utente con {analisi_fatture: True} su sede1, notifica con action_page='/margini' sulla stessa sede. GET /api/notifiche del sotto-utente NON la contiene (notifica_visibile la filtra), il titolare sì; POST /api/notifiche/{id}/dismiss dal sotto-utente -> 200; dismissed_at=2026-10-15 08:37:52 UTC; dopo, il titolare non la vede più (titolare_la_vede_dopo=False). Codice: fastapi_worker.py:2924-2929 filtra solo .eq(user_id).in_(ristorante_id, sedi_consentite), mai notifica_visibile; la lista (fw:2791-2793) e la catena (gruppo.py:2677-2678) la applicano. L'id è uuid (information_schema.columns notification_inbox.id = uuid), quindi serve conoscere l'id: lo sfruttamento pratico è basso ma l'inbox dell'account è condivisa e l'azione va oltre ciò che la lista concede.

**Prova indipendente della verifica.** dismiss_notifica (fastapi_worker.py:2913-2937; la riga è stata toccata l'ultima volta da 97d2d438 il 30/9) filtra solo `.eq("id").eq("user_id")` e, per un sotto-utente, `.in_("ristorante_id", sedi_consentite)`. Non chiama notifica_visibile. La lista invece la applica: fastapi_worker.py:2792-2793 e gruppo.py:2678. POST /api/notifiche/{notifica_id}/dismiss è in ROTTE_COMUNI (permessi_rotte.py:275), quindi è raggiungibile da qualunque sotto-utente; il commento a :263 dice «notifiche (filtrate per sede dall'endpoint)», solo per sede. notifica_visibile (:365-375) restituisce False per un sotto-utente senza Home quando la pagina di action_page non è sua. tests/test_sql_sotto_utenti.py::test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto (:903-916) copre solo la sede. Non ho eseguito la sonda SQL del finder (-m sql vietato): la conclusione viene dalla lettura dei filtri della query di UPDATE, che sono deterministici.

**Correzioni della verifica.** Il meccanismo è confermato. La gravità scende da media a bassa. La platea è zero. Lo sfruttamento richiede l'uuid di una notifica che il sotto-utente non vede: le uniche altre letture di notification_inbox che ho trovato restituiscono id filtrati (/api/notifiche e /api/gruppo/notifiche con notifica_visibile) oppure stanno dietro la Home (home_briefing, :8976), con cui le notifiche sono comunque tutte visibili. L'effetto è un'azione di scrittura su un dato non visibile (la notifica sparisce dall'inbox del titolare), non un dato mostrato a chi non deve.

**Deliberato dove.** Da nessuna parte. ROTTE_COMUNI dichiara il filtro per sede, non per pagina. La regola «sotto-utente solo in meno» vorrebbe azione e lista allineate.

**File e righe.**

- `services/fastapi_worker.py:2791-2793`
- `services/fastapi_worker.py:2908-2931`
- `services/permessi_rotte.py:365-376`

**Fix proposto (non applicato).** In dismiss_notifica, per un sotto-utente leggere prima la riga (id, action_page) con gli stessi filtri di user_id e sede, applicare notifica_visibile(user, action_page) e, se il risultato è False, rispondere 200 senza scrivere (come oggi per la sede altrui).

**Presidio di test proposto.** Un test -m sql accanto a test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto: sotto-utente con {analisi_fatture: True}, notifica con action_page '/margini' sulla sua sede, dismiss → 200, dismissed_at resta NULL e il titolare la vede ancora. Da provare per mutazione, togliendo il controllo notifica_visibile.

**Già presidiato da.** Solo per la sede: test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto. tests/test_permessi_rotte.py prova notifica_visibile da sola. Nessun test sul dismiss per pagina.

---

### 34. «Prodotti da controllare» (needs_review), «€ esclusi dai margini» (Da Classificare, netto) e chip «Solo da verificare» sono tre popolazioni con etichette vicine

`F1a-06` · trovato da F1a-06

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** Home → Salute voce «Righe classificate» e briefing (esclusi_importo); Analisi Fatture → chip «Solo da verificare» + KPI; sede cc016821 (e le altre 3).

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `cc016821-e749-4323-9568-3781c69384d3`

**Platea misurata in verifica.** Tutte le sedi con righe needs_review (cifre del finder su una sede: 89 prodotti vs 37 Da Classificare).

**Atteso contro mostrato.** Home: 89 prodotti / 582 € ; Analisi «Solo da verificare»: 156 righe / 14.286 € / 89 prodotti.

**Prova del finder.** cc016821 oggi: righe needs_review = 156, somma 14.286,41 €, descrizioni distinte 89 (worker:9596-9611 conta le descrizioni distinte needs_review → «89 prodotti da controllare»); righe categoria = 'Da Classificare' = 56, somma NETTA 582,02 € (= +6.280,00 − 5.697,98; _card_da_classificare worker:8533 somma con segno), 37 descrizioni distinte; il chip «Solo da verificare» di Analisi Fatture (routers/fatture.py:419: needs_review) mostra 156 righe / 14.286,41 €. Il «101 prodotti / 19.050 €» vs «100 / 582 €» del 16/09 e' la stessa coppia (needs_review vs Da Classificare) con dati di allora. Le 56 righe Da Classificare sono tutte needs_review (54 su 56 con importo ≠ 0 + 2 a zero), quindi la seconda e' un sottoinsieme della prima.

**Prova indipendente della verifica.** HEAD fastapi_worker.py:9596-9611 conta le descrizioni distinte con needs_review=true (commento 9591: scelta deliberata del 02/09 per allinearsi al briefing); routers/fatture.py chip 'Solo da verificare' = needs_review sulle righe; card Da Classificare = categoria. Popolazioni diverse e corrette, etichette vicine.

**File e righe.**

- `apps/web/src/app/(app)/analisi-fatture/articoli-tab.tsx:410 («Solo da verificare»)`
- `services/fastapi_worker.py:8533-8575 (_card_da_classificare: categoria = Da Classificare, somma con segno)`
- `services/fastapi_worker.py:9596-9618 (da_controllare = descrizioni distinte needs_review)`
- `services/routers/fatture.py:418-420 (solo_da_verificare = needs_review)`

**Fix proposto (non applicato).** Dichiarare le due grandezze: «N prodotti da controllare, di cui M senza categoria: X € netti (Y € di acquisti, Z € di storni) fuori dai margini». L'importo netto 582 € nasconde 6.280 € di acquisti esclusi.

**Presidio di test proposto.** Test sul testo della voce Salute/briefing che, con righe needs_review classificate e righe Da Classificare, nomina entrambe le cifre.

**Già presidiato da.** tests/test_home_card_da_classificare.py (solo il predicato).

---

### 35. Analisi e Tag: «Media periodo» (media semplice dei prezzi giornalieri) e «Prezzo medio / Rispetto alla media» (ponderata spesa/quantita') sono due formule

`F1a-07` · trovato da F1a-07

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** Analisi e Tag → grafico «Trend prezzi nel periodo» (Media periodo = trend.prezzo_medio_periodo) vs tabella Fornitori (colonna «Prezzo medio», intestazione «Rispetto alla media» = aggregati.prezzo_medio_tag) e KPI «Prezzo medio ponderato»; l'account ha 13 tag custom e 3 di gruppo.

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`

**Platea misurata in verifica.** Tutti gli utenti di Analisi e Tag con acquisti di quantita' diverse nello stesso giorno o periodo.

**Atteso contro mostrato.** Stesso tag, stessa risposta: Media periodo 10,00 €, Rispetto alla media 9,18 €.

**Prova del finder.** Esecuzione delle funzioni pure (services.tag_analytics_service, streamlit mockato, nessun client) su 2 righe KG: 01/03 10 kg a 9 € (90 €), 02/03 1 kg a 11 € (11 €): _compute_trend → prezzo_medio_periodo = 10,0 (media dei prezzi per giorno, tag_analytics_service.py:255); _compute_fornitori → prezzo_medio_tag = 9,1818 (101/11, :347); _compute_kpi → prezzo_medio_ponderato = 9,1818. Entrambe giuste, nomi vicini. Il «7,66 vs 7,83» del 16/09 e' questa differenza.

**Prova indipendente della verifica.** HEAD tag_analytics_service.py:255 prezzo_medio_periodo = mean(PrezzoTag); :340-347 prezzo_medio_tag = spesa_tot/qta_tot (ponderato, commento deliberato). Etichette a video: 'Media periodo' (client :206) vs 'Prezzo medio'/'Rispetto alla media' (:1032-1039). Due formule, nessuna dichiarazione.

**File e righe.**

- `apps/web/src/app/(app)/analisi-e-tag/analisi-e-tag-client.tsx:206,1032-1043`
- `services/tag_analytics_service.py:243-273 (_compute_trend: mean dei PrezzoTag giornalieri)`
- `services/tag_analytics_service.py:340-356 (_compute_fornitori: spesa_tot/qta_tot)`

**Fix proposto (non applicato).** Rinominare «Media periodo» in «Media dei prezzi giornalieri» (o usare la ponderata anche nel trend: nota che prezzo_medio_periodo alimenta price_impact_service, quindi cambiarla sposta gli alert prezzi della Home).

**Presidio di test proposto.** Test con due giorni a quantita' diverse (10 kg / 1 kg) che documenti la differenza voluta (o, se si unifica, l'uguaglianza); il mutante «media semplice → ponderata» oggi sopravvive al test esistente.

**Già presidiato da.** test_tag_audit_fix.py su un dataset dove le formule coincidono.

---

### 36. Scadenziario: base IVA mista fra totale documento e somma righe

`K12` · trovato da F1e-08, F1d-04

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Gestione Fatture (sede e catena): colonna importo, KPI Scadute/Da pagare, calendario, chat query_scadenze. Quanti documenti cadono nel fallback non è misurabile senza DB.

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `79920814-082f-4d93-bf64-54bafbfbb708`

**Platea misurata in verifica.** Totale da righe nette usato come ripiego quando manca fatture_documenti: 13 documenti su 3.645, su 4 account, per 5.594,99 €. Il flag totale_incoerente vale true su 3.580 documenti su 3.645, ma nessun .tsx lo legge.

**Atteso contro mostrato.** Fattura 1.000 + IVA 10%: con fatture_documenti mostra 1.100, senza mostra 1.000 nella stessa colonna.

**Prova del finder.** documenti_service.py:810-813: `totale_doc = extra.get("totale_documento")` (fatture_documenti, = ImportoTotaleDocumento XML, IVA inclusa: invoice_service.py:872-875), altrimenti `totale_righe` = somma totale_riga (netto IVA, NC negative). Il campo non porta traccia di quale base è stata usata (solo `totale_incoerente` per la divergenza). Margini e Analisi Fatture usano sempre le righe nette.

**Prova indipendente della verifica.** documenti_service.py:810-815 a HEAD e' invariato (totale_doc da fatture_documenti, altrimenti somma delle righe; totale_incoerente = abs(lordo - netto) > 0.01). La mia query (fatture attive raggruppate per user, ristorante e file_origine, in left join su fatture_documenti) conta 3.645 documenti: 13 senza totale_documento (5.594,99 € di righe) e 3.580 con lordo e somma righe divergenti. grep di totale_incoerente nei .tsx: 0 risultati.

**Correzioni della verifica.** La gravita' media di F1e-08 scende a bassa: la base mista riguarda 13 documenti su 3.645 (0,4%). Il flag totale_incoerente (F1d-04) e' vero quasi sempre, 3.580 su 3.645, quindi e' rotto per costruzione, ma non ha platea a video.

**Deliberato dove.** Il commento in documenti_service.py:809 dichiara deliberato il ripiego sulla somma delle righe, ma non dice che si mescolano basi IVA diverse.

**File e righe.**

- `apps/web/src/lib/scadenziario.ts:11`
- `services/documenti_service.py:810-815`
- `services/documenti_service.py:851-860`
- `services/invoice_service.py:872-875`

**Fix proposto (non applicato).** Marcare nel payload la base del totale, confrontare totale_documento con imponibile + IVA, oppure togliere totale_incoerente.

**Presidio di test proposto.** Test su get_documenti_scadenziario con un documento senza riga in fatture_documenti che asserisce il flag della base; conteggio a DB dei documenti attivi senza fatture_documenti (query di un altro filone).

**Già presidiato da.** nessuno

---

### 37. Card «Pagate (mese)»: filtro non dichiarato e pagate RID senza data

`K14` · trovato da F4-05, F1d-02

| | |
|---|---|
| Filone | 1 — Quadrature numeriche + 4 — Gestione Fatture |
| Classificazione | stessa etichetta per grandezze diverse |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** /scadenziario e /catena/fatture, viste Scadenzario e Calendario (le card sono nascoste solo in Archivio).

**Clienti coinvolti (ID).** `51015cc8-078c-4e92-86b4-113e62e16d38`, `79920814-082f-4d93-bf64-54bafbfbb708`

**Platea misurata in verifica.** Etichetta senza «(filtro)»: tutti gli utenti di Gestione Fatture che applicano un filtro. Fatture RID pagate senza pagata_at (stima mia: join con fornitori_pagamenti_config su modalita 'rid', partita IVA, senza scadenza_override e senza pagata_manuale_at): 57 documenti su 3 account; di questi, 3 sono di ottobre per 205,89 €, cioe' quelli che oggi mancano dalla card del mese.

**Prova del finder.** Gruppo senza filtri: computeKpi dà pagate_mese 2 / 720 €. Con un clic su Scadute (periodo='scadute') computeKpi(filtraDocumenti) dà pagate_mese 0 / 0 €, perché matchDocumento scarta ogni pagata quando periodo≠'tutti' (lib :692-693). Le altre tre card cambiano etichetta in «Scadute (filtro)», «Settimana (filtro)», «Da pagare (filtro)» (:2070, :2076, :2087). Pagate resta «Pagate (mese)» (:2095) e il cliente legge «0 € pagati questo mese». Con un filtro fornitore (Forn SCAD1) vale 0 anche lì, sempre senza etichetta.

**Prova indipendente della verifica.** scadenziario-client.tsx:1743 kpi = computeKpi(documentiFiltrati); :2095 label fisso «Pagate (mese)» mentre :2070/2076/2087 cambiano in «(filtro)»; lib/scadenziario.ts:692-693 scarta le pagate quando periodo != 'tutti'; :345-346 conta solo i documenti con pagata_at valorizzato. documenti_service.py:845-847 marca pagata=True per RID senza valorizzare pagata_at. La query DB da' 3 documenti di ottobre per 205,89 €, la stessa cifra di F1d-02.

**Correzioni della verifica.** Gravita' unificata a bassa: l'effetto del mese si limita a 205,89 € su un account, e lo zero da filtro e' fuorviante ma reversibile. Il commento a :2065 («consuntivo, non un filtro») contraddice il calcolo, che invece usa documentiFiltrati.

**Deliberato dove.** Il commento a scadenziario-client.tsx:2065 dichiara l'intento opposto al comportamento: non e' deliberato.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2068-2095`
- `apps/web/src/lib/scadenziario.ts:333-341 (computeKpi: pagate_mese solo se pagata_at >= primoMese)`
- `apps/web/src/lib/scadenziario.ts:339-351`
- `apps/web/src/lib/scadenziario.ts:692-694`
- `services/documenti_service.py:819 (pagata_at = _to_date_iso(extra.pagata_at) -> None per le RID)`
- `services/documenti_service.py:843-847 (RID forza pagata=True senza data)`

**Fix proposto (non applicato).** Calcolare pagate_mese sui documenti senza il filtro periodo (o etichetta «(filtro)») e valorizzare pagata_at per le RID (data documento o scadenza).

**Presidio di test proposto.** Test node: computeKpi(filtraDocumenti(D,{periodo:'scadute'})).pagate_mese_count == 0, e una guardia sul .tsx che l'etichetta di Pagate dipenda da filtriAttivi (oppure il test sulla funzione scelta).

**Già presidiato da.** nessuno trovato

---

### 38. In vista Calendario le card e i chip di periodo restano visibili e filtrano, ma il calendario li ignora

`F4-06` · trovato da F4-06

| | |
|---|---|
| Filone | 4 — Gestione Fatture |
| Classificazione | periodo non dichiarato |
| Gravità | **bassa** |
| Verifica | confermato |

**Chi lo vede.** /scadenziario e /catena/fatture, scheda Calendario.

**Platea misurata in verifica.** Tutti gli utenti di /scadenziario e /catena/fatture che aprono la scheda Calendario; nessun dato errato salvato.

**Prova del finder.** documentiCalendario (:1775-1783) passa periodo:'tutti' e non applica dataDa/dataA. I chip Settimana, Mese e date personalizzate sono nascosti solo in lista_mensile (:2349), e le card solo in lista_mensile (:2068). Esecuzione: dopo il clic su Scadute le card mostrano 4 / 1600 € (documentiFiltrati=6), mentre il calendario resta costruito su 16 documenti e mostra ancora il 18/10 (300 €, settimana) e il 25/10 (120 €). Il commento :1773-1774 dichiara che «i chip periodo sono specifici dell'agenda», ma a video restano accesi nel Calendario.

**Prova indipendente della verifica.** HEAD (nessun commit recente sul file dopo il 13/10): scadenziario-client.tsx:1773-1783 documentiCalendario usa periodo:'tutti'; i chip Tutti/Solo scadute (2335-2344) non hanno guardia di vista, Settimana/Mese sono nascosti solo con view==='lista_mensile' (2349). Commento 1773 dichiara il periodo specifico dell'agenda ma i chip restano accesi a video.

**File e righe.**

- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1773-1783`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2068`
- `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2335-2368`

**Fix proposto (non applicato).** Nascondere chip periodo e card cliccabili fuori da view agenda, o applicare il periodo al calendario.

**Presidio di test proposto.** Guardia sul .tsx provata per mutazione.

**Già presidiato da.** Nessuno.

---

### 39. Spesa di Analisi Fatture contro costi di Margini sullo stesso periodo

`K09` · trovato da F1e-05, F1b-02, F1c-04

| | |
|---|---|
| Filone | 1 — Quadrature numeriche |
| Classificazione | periodo non dichiarato |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Analisi Fatture (sede), KpiBar: «Spesa totale» e «Media al mese», chip periodo «Anno in corso», nessuna nota su base IVA, data o righe non classificate; a confronto con Costi F&B/Spese Generali della pagina Margini per lo stesso periodo. Tutti gli account con fatture.

**Clienti coinvolti (ID).** `2f3f93a1-c1f4-4804-858e-a161e6f36f3f`, `79920814-082f-4d93-bf64-54bafbfbb708`, `bdda08d1-9490-486c-adfb-dd05cbddc25c`, `dcf1996e-f430-4549-8505-902b169f6bab`

**Platea misurata in verifica.** Data di competenza diversa dal mese del documento: 229 righe di 1 solo account, 3.833,22 € in valore assoluto (misurato a DB). Righe Da Classificare con importo: 142 righe su 3 account. A queste si aggiungono i costi inseriti a mano in Margini, che Analisi Fatture per definizione non mostra.

**Atteso contro mostrato.** Per un mese con N righe Da Classificare e M righe con data_competenza diversa dalla data fattura, «Spesa totale» ≠ Costi F&B + Spese Generali di Margini della somma di quelle righe; quantità non misurabile senza DB.

**Prova del finder.** Le quattro differenze confermate nel codice: (1) data: _fetch_fatture_rows filtra `data_documento` (fastapi_worker.py:10602-10605) mentre i costi di Margini usano COALESCE(data_competenza,data_documento) (SQL costi_automatici_mensili 20260912075621_oscura_fattura.sql:120, Python _calcola_costi_auto_per_mese :10893-10896); (2) _build_fatture_base_query (:10436-10448) non ha `.neq("categoria", CATEGORIA_NON_CLASSIFICATA)` che i costi di Margini hanno (:10889, SQL :124); (3) _apply_tipo_prodotti_filter (:10452-10455) food_beverage = «non in CATEGORIE_SPESE_GENERALI_WORKER», quindi le Da Classificare cadono in F&B; (4) righe quote proiettate aggiunte (:10622-10641) mentre Margini le somma da quote_riparto_* (_kpi_periodo :9819-9828). Etichette: analisi-fatture/kpi-bar.tsx:71-72; chip analisi-fatture/filtri-periodo.tsx:93 «Anno in corso». NC nettizzate in entrambe (fatture.py:393-400). La stessa etichetta «Spesa totale» compare in catena scheda-tag-catena.tsx:453 su gruppo_tag_analisi che usa COALESCE(data_competenza,data_documento) (oscura_fattura.sql, def gruppo_tag_analisi righe 19-21 del corpo): stessa parola, altra data.

**Prova indipendente della verifica.** Query mia: count di fatture attive con date_trunc('month',data_competenza) <> date_trunc('month',data_documento) = 229 righe, 1 utente, 3.833,22 €. Il dato e' coerente con i 774,01 + 3.020,13 € del finder F1c-04 per aprile e maggio, e con le 229 righe su tutto il DB di F1b-02. Le Da Classificare con totale_riga <> 0 sono 142 righe su 3 utenti. analisi-fatture/kpi-bar.tsx:71 mostra la sola etichetta «Spesa totale», senza dichiarare la base.

**Correzioni della verifica.** La gravita' scende a bassa: sull'anno le parti automatiche coincidono (F1c-04), le differenze per mese toccano un solo account e il resto sono costi manuali, cioe' un'altra grandezza. F1e-05 indica quattro cause, ma oggi pesano quasi solo i costi manuali e lo spostamento di competenza di quel solo account. Non c'e' nessun numero da correggere, va solo dichiarato.

**Deliberato dove.** Nessuna dichiarazione a video.

**File e righe.**

- `apps/web/src/app/(app)/analisi-fatture/filtri-periodo.tsx:93`
- `apps/web/src/app/(app)/analisi-fatture/kpi-bar.tsx:71-72`
- `apps/web/src/app/(app)/catena/analisi/scheda-tag-catena.tsx:453`
- `services/fastapi_worker.py:10417-10430 (_build_fatture_base_query: nessun filtro Da Classificare)`
- `services/fastapi_worker.py:10436-10448`
- `services/fastapi_worker.py:10452-10455`
- `services/fastapi_worker.py:10577-10665`
- `services/fastapi_worker.py:10583-10587 (_fetch_fatture_rows: filtro su data_documento)`
- `services/fastapi_worker.py:10602-10605`
- `services/fastapi_worker.py:10622-10641`
- `services/fastapi_worker.py:10872-10931`
- `services/fastapi_worker.py:10925-10937 (_calcola_costi_auto_per_periodo: competenza con fallback documento, Da Classificare esclusa)`
- `services/riparto_service.py:443-540`
- `services/routers/fatture.py:367-489`
- `services/routers/fatture.py:393-399 (_calc: somma righe ≠0)`
- `services/routers/fatture.py:393-405`
- `supabase/migrations/20260912075621_oscura_fattura.sql:120-124`

**Fix proposto (non applicato).** Nota sul KPI di Analisi Fatture: «per data fattura, esclusi i costi inseriti a mano in Margini». Eventualmente escludere le quote proiettate Da Classificare.

**Presidio di test proposto.** Test worker con righe sintetiche (una con data_competenza nel mese successivo, una Da Classificare): get_fatture_kpi e _calcola_costi_auto_per_mese sullo stesso mese devono tornare totali che differiscono esattamente delle righe dichiarate; oggi non esiste nessun test sui totali di /api/fatture/kpi.

**Già presidiato da.** nessuno

---

### 40. Prompt: appuntamenti di oggi sul giorno UTC

`K18` · trovato da F3-04

| | |
|---|---|
| Filone | 3 — Assistente e chat di catena |
| Classificazione | periodo non dichiarato |
| Gravità | **bassa** |
| Verifica | confermato con correzioni |

**Chi lo vede.** Chat della Home sede, desktop e /m, per chi ha la pagina agenda e scrive fra 00:00 e 01:00 (CET) o 02:00 (CEST). Tutti gli account con eventi in diario_eventi.

**Platea misurata in verifica.** Zero oggi. Solo 1 sede in tutto il DB ha righe in diario_eventi, con 0 eventi negli ultimi 30 giorni. Su 135 domande in chat_usage_log, 1 cade nella finestra in cui il giorno di Roma e quello UTC divergono, e 0 di quelle riguardano una sede con eventi nel giorno di Roma o in quello UTC.

**Prova del finder.** Il prompt mette 'Oggi e' {oggi_str}' da _oggi_rome() (fw:3998-4001, relativo :475-478) e, nello stesso prompt, '## Appuntamenti di oggi' filtrati con data_evento = _date_ag.today() (fw:3742). Il server gira in UTC, lo dice la docstring di _oggi_rome (fw:46-47). Eseguito: alle 2026-10-15T22:30Z date.today() UTC = 2026-10-15 e _oggi_rome() = 2026-10-16, quindi il modello riceve 'Oggi è 16 ottobre' con gli appuntamenti del 15. CHAT_ASSISTENTE.md §6 punto 4 dice che a 'cosa ho oggi' risponde dal prompt senza chiamare lo strumento. Gemello minore: query_costi usa _date_q.today() per decidere 'mese_non_ancora_caricato' (fw:4808). Che i clienti scrivano di notte è documentato: 1 riga su 95 di chat_usage_log fra 00 e 02 di Roma (tests/test_chat_quota_giorno_di_roma.py docstring).

**Prova indipendente della verifica.** A HEAD fw:3742 usa oggi_ag = _date_ag.today().isoformat(), mentre il prompt scrive 'Oggi e'' da _oggi_rome(). La docstring di _oggi_rome (fw:43-52) dichiara che il server gira in UTC. Il gemello è fw:4808, dove _date_q.today() decide il mese corrente in query_costi. Platea misurata con una mia query su chat_usage_log e diario_eventi.

**Correzioni della verifica.** La gravità scende da media a bassa: il difetto è vero ma oggi non ha platea (agenda praticamente inutilizzata, domande notturne quasi nulle).

**File e righe.**

- `services/fastapi_worker.py:3735-3762`
- `services/fastapi_worker.py:43-52`
- `services/fastapi_worker.py:4806-4810`

**Fix proposto (non applicato).** Sostituire _date_ag.today() e _date_q.today() con _oggi_rome().

**Presidio di test proposto.** Test con date.today e _oggi_rome patchati su giorni diversi, provato per mutazione.

**Già presidiato da.** Nessuno.

---

## Falsi allarmi, verificati e scartati

Questi punti sono stati sollevati e poi controllati da un secondo agente: non sono difetti. Restano qui perché nessun audit futuro li riscopra come novità.

- **`F1a-08` margini_mensili: i totali salvati (costi_fb_auto, costi_spese_auto, mol, mol_perc) sono stantii o a zero, ma nessuna pagina li legge.** Il falso allarme regge. grep: costi_fb_auto/mol_perc in services compaiono solo in margine_service (scrittura e calcoli su df in memoria), nessuna lettura frontend; fetchMarginiAnno senza chiamanti. SQL READ ONLY: le sole funzioni che toccano margini_mensili e costi_fb_auto/mol_perc sono elimina_ricavi_noiva, ricavi_noiva_esclusi_guardia, riparto_quote_mensili (scrittori/guardie, nessun lettore a video).

- **`F1b-01` Mese in corso con 11.841 € di costi e 0 € di ricavi dentro i totali di Margini (anno corrente) e Catena (overview, ranking, margini-coperti).** L'agente delle contraddizioni ha misurato che il periodo e' dichiarato a video e che il comportamento e' deliberato (_label_anno_parziale, services/routers/gruppo.py, con la docstring che spiega perche' la catena somma fino al mese corrente parziale). Il lotto dei bassi lo aveva alzato a media: prevale la lettura con la prova del deliberato. Resta fra i falsi allarmi con la nota che ottobre, a ricavi 0, abbassa il MOL % dell'anno di circa 1,5 punti su un cliente.

- **`F1e-04` KPI_SOGLIE (constants) e _KPI_SOGLIE_MARGINI (routers/margini) differiscono solo nel tetto 100 vs 200 di mol/primo_margine: esito identico su ogni valore.** Il falso allarme regge: le due tabelle differiscono solo nel tetto dell'ultima tupla, ed entrambe le funzioni di valutazione ricadono su soglie[-1]; nessun chiamante di genera_commenti_kpi secondo il finder (non contraddetto).

- **`F1e-10` Due copie di calcolaPeriodo (Margini e Analisi Fatture): identiche sui preset che le pagine offrono, divergono solo su preset non raggiungibili dall'interfaccia.** Il falso allarme regge: le divergenze riguardano solo preset senza chip nell'interfaccia; entrambe le page usano oggiARoma.

- **`F1e-12` gruppo_salute_componenti chiama `netto` una somma lorda: oggi usata solo come presenza (> 0), ma il nome invita a dividerci sopra.** Il falso allarme regge: gruppo_salute_componenti live non e' stata ridefinita, e i consumatori in gruppo.py usano netto solo come >0 o <=0; nessuna divisione.

- **`F1e-13` Esclusione NOTE: SQL e pandas escludono solo '📝 NOTE E DICITURE', il Python di Margini anche 'NOTE E DICITURE' senza emoji e categoria vuota — la vuota non può esistere, la senza-emoji sì.** Il falso allarme regge. SQL READ ONLY su tutta fatture (deleted_at IS NULL): categoria='NOTE E DICITURE' (senza emoji) = 0 (anche con totale_riga qualsiasi); categoria NULL o vuota = 0; categoria 'Da Clasificare' con totale_riga<>0 = 0. La divergenza SQL/Python sulle NOTE senza emoji non ha righe a cui applicarsi.

- **`F1e-14` Percorsi senza chiamanti confermati: GET /api/margini (anno UTC, senza override), /api/dashboard/stats, GruppoKpi.spesa_fornitori e RankingPV.colore.** Il falso allarme regge. grep in apps/web/src: fetchMarginiAnno (lib/margini.ts:76) e fetchDashboardStats (lib/dashboard.ts:23) definite senza chiamanti; dashboard/page.tsx:102 commenta che fetchDashboardStats non e' piu' chiamata.

- **`F4-12` Manca la guardia TD04 sul server /pagata: nessun numero cambia (falso allarme).** Il falso allarme regge: i lettori di pagata elencati dal finder escludono le NC (TD04) prima o indipendentemente da pagata, e i test test_le_note_di_credito_non_sono_debiti / non_gonfiano_il_contatore lo presidiano; nessun contro-esempio trovato.

## Incerti: né confermati né smentiti

- **`F3-09` gruppo_spesa consegna al modello la pivot con chiavi UUID per sede, senza incidenza per sede, e il prompt chiede di confrontare per incidenze.** Senza una risposta reale della chat che sbagli sede o incidenza e' una questione di efficienza/qualita' del payload, non un errore dimostrato. Per decidere: una conversazione di produzione o di test con gruppo_spesa in cui il modello confonde le sedi o inventa incidenze. HEAD fastapi_worker.py:4538-4540 passa gruppo_spesa_pivot(...).model_dump() senza trasformazione; prompt :4287 chiede di confrontare per incidenze. La mappa pv[{id,nome}] e' presente, quindi il modello puo' rimappare gli UUID; il pivot di spesa non porta il fatturato, quindi l'incidenza sul fatturato richiede un altro tool.

- **`K22` Prompt: calcoli lasciati al modello.** Il perimetro va ristretto. L'unico difetto dimostrabile è che la regola della media giornaliera vale anche per i costi da fatture del mese corrente, con cui la media al giorno non ha senso. Il resto (impatto in euro, percentuali, delta calcolati dal modello) è un rischio di progettazione e non va classificato come bug finché un'esecuzione non mostra una risposta sbagliata. Per decidere servirebbe un eval della chat (sessioni chat-eval) su domande di confronto mese su mese dei costi, nel mese corrente. A HEAD il prompt contiene davvero la regola «PRIMA di qualsiasi confronto mese-su-mese... usa SEMPRE la media giornaliera» (fw:4103-4107), senza escludere i costi. Lo stesso prompt dice che il mese corrente è quasi sempre incompleto perché le fatture arrivano a fine mese (fw:4083), e chiede di «confrontare tu i totali» di due query_costi. Questa incoerenza nel testo del prompt c'è. Delegare l'aritmetica al modello è invece una scelta di progettazione dichiarata nel prompt, non un numero sbagliato dimostrato.

## Le contraddizioni fra agenti, sciolte

Sei volte due agenti della fase Trova avevano detto cose diverse sullo stesso punto. Un agente dedicato, con accesso al DB, le ha sciolte.

- **Vista gruppo account 51015cc8: contatore «Seleziona tutte»/contaDaPagare 2.461 (F1a) contro 2.437 (F1d)** Chi ha ragione: F1d. F1a (f) ha contato le pagate a DB (15) e non le 24 fatture che get_documenti_scadenziario marca pagata=True a lettura per la regola RID (documenti_service.py:845-848: scadenza_src == 'fornitore_rid' e pagata_manuale_at NULL). Verdetto su F1a (f): confermato_con_correzioni (2.461 -> 2.437). Numero vero: 2.437 = 2.582 documenti attivi - 106 NC - 0 oscurate - 15 pagate a DB - 24 pagate per regola RID (25 documenti RID, uno e' una NC gia' esclusa). Pagate effettive a video: 40 (15 + 25). Effetto sul report: Il punto 5 del doc va con UNA cifra: 2.437 fatture da pagare = «Seleziona tutte (2437)». Cancellare il 2.461 di F1a; aggiungere la nota che 25 documenti risultano pagati solo in lettura (regola RID), nessuno a DB. Nessun bug nuovo: e' la regola RID applicata dal worker, documentata nel codice.

- **Archivio «Per mese» di 51015cc8: F1d «7 mesi gen-lug 2026» contro i 19 header fatture_documenti di dicembre 2025 di F1a-04** Chi ha ragione: Entrambi, su due popolazioni diverse: non e' una contraddizione. Lo scadenziario (vista gruppo, archivio, calendario) parte dalla RPC scadenziario_fatture_aggregate su `fatture` (documenti_service.py:678-713) e usa fatture_documenti solo per arricchire (Step 3): un header senza righe non entra mai. Il filtro periodo di Analisi Fatture (/api/fatture/mesi-disponibili, routers/fatture.py:326-360) conta invece fatture_documenti. Verdetti: F1d verificato_ok confermato; F1a-04 confermato (gravita' bassa, platea 1 sede + 1 header su un'altra). Numero vero: Scadenziario gruppo e archivio di A: 2.582 documenti, mesi gen-lug 2026, 0 di dicembre 2025. Header orfani: 19 su fd7ac484 (data_documento 09-31/12/2025, 59.368,37 EUR, tipi TD01/TD04/TD24, 0 pagate) + 1 su dcf1996e (account 2f3f93a1, 30/06/2026, 187,08 EUR, invoicetronic) = 20 in tutto il DB. Effetto sul report: Tenere F1d (7 mesi) per lo scadenziario e F1a-04 per Analisi Fatture, scrivendo che sono due fonti: `fatture` (scadenziario) e `fatture_documenti` (filtro mesi). Aggiungere a F1a-04 l'origine (upload manuale del 12/5/2026, header senza righe) e la platea: 20 header orfani su 2 sedi, 59.555,45 EUR mai entrati in margini/scadenziario — e' anche un dato PERSO per il cliente (19 fatture di dicembre caricate e mai analizzate), non solo una voce in piu' nel filtro.

- **F1b-01 «periodo non dichiarato» (mese in corso con 11.841 EUR di costi e 0 ricavi nei totali di Margini e Catena) contro F1e e lo stesso F1b che verificano l'etichetta «gen-ott, ottobre in corso»** Chi ha ragione: F1e e il verificato_ok di F1b: il periodo E' dichiarato ed e' deliberato (_label_anno_parziale, gruppo.py:1067-1083, docstring: «La catena somma da gennaio al mese CORRENTE, che e' parziale ... l'etichetta dice sia l'arco sia che l'ultimo mese non e' finito»; Margini preset «1 gen -> 15 ott»). La classificazione «periodo non dichiarato» di F1b-01 e' sbagliata. Resta vero il fatto sotto: ottobre entra nei totali con soli costi e il ranking non lo isola (incompleti = netto annuo <= 0, gruppo.py:1247-1262, non il mese corrente). Verdetto: confermato_con_correzioni (classificazione «stessa etichetta per grandezze diverse / fuorviante», gravita' bassa, non bug). Numero vero: Ottobre 2026 account 2f3f93a1: ricavi 0 su tutti i canali (margini_mensili fatturato_netto 0,00, 0 override ricavi_modalita_mensile, 0 righe ricavi_giornalieri) su bdda08d1, dcf1996e e la sede tecnica; costi da righe fatture per competenza: bdda 6.941,22 (56 righe), dcf 4.062,93 (42), sede tecnica 836,91 (49, ripartite) — coerenti con i 7.359,68 / 4.481,38 di F1b che includono le quote di riparto. Scarto sul margine % del gruppo: 14,5 % (gen-ott) contro 16,1 % (gen-set), cifre di F1b non ri-calcolate da me. Effetto sul report: Riclassificare F1b-01: non «periodo non dichiarato» ma «mese in corso senza incasso dentro il margine % dell'anno, dichiarato come 'in corso' ma senza dire che porta solo costi». Gravita' bassa: decisione deliberata e dichiarata a video, con il segnale ricavi_mancanti come avviso. La proposta di F1b (flag mesi_senza_ricavi o esclusione dal ranking) resta come miglioria, non come bug.

- **Conversazione dell'assistente in sessionStorage dopo il logout: F3 «residuo accettato» contro F2b-7 «bug vero»** Chi ha ragione: Sui fatti sono d'accordo e il codice a HEAD li conferma: handleLogout (app-sidebar.tsx:141-149), logout /m (header-menu.tsx:94-101) e api/auth/logout/route.ts cancellano solo cookie e sessione server, nessun sessionStorage.clear/Clear-Site-Data. Nessuna decisione registrata che ACCETTI il residuo: l'unica traccia e' il commento home-chat.ts:364 che lo riconosce («sessionStorage sopravvive al logout nella stessa scheda») e la scelta della chiave per persona (commit 1b23ea17, CHAT_ASSISTENTE.md:246, AUDIT_COPERTURA.md:1554) che chiude il caso «la persona dopo lo vede a video», non «il dato resta nel browser». «Accettato» e' un giudizio di F3, non di Mattia. Verdetto: F2b-7 confermato come residuo noto, gravita' bassa; F3 va corretto da «accettato» a «noto, non deciso». Numero vero: Platea: ogni account con l'assistente (tutti i 7), ma solo nella stessa scheda, finche' resta aperta, e leggibile solo dagli strumenti del browser (la UI della persona successiva non la mostra: chiave per persona, presidio tests/test_sotto_utente_frontend.py::test_la_conversazione_e_della_persona_non_dell_account eseguito oggi: 1 passed). sessionStorage muore con la scheda: 0 persistenza su disco. Effetto sul report: Un solo punto, gravita' bassa, formulato «al logout la conversazione resta in sessionStorage della scheda (cifre e card), leggibile dagli strumenti del browser; la persona successiva non la vede». Non scriverlo come «accettato»: la decisione (pulire al logout, costo 3 righe, o accettare) va a Mattia.

- **Pagate senza data: F1d (d) «pagata=true con pagata_at NULL a DB: 0» contro F1d-02 «C: 30 documenti pagata=true e pagata_at NULL»** Chi ha ragione: Entrambi, come sospettato: le due frasi parlano di due livelli. A DB zero; i 30 nascono nel payload del worker, che per la regola RID forza pagata=True senza valorizzare pagata_at (documenti_service.py:818 e 845-848), e computeKpi non li conta in «Pagate (mese)» perche' parseLocalDate(null) -> null (lib/scadenziario.ts:345-350). Verdetto F1d-02: confermato_con_correzioni (titolo da riformulare, numeri giusti). Numero vero: A DB: pagata=true AND pagata_at IS NULL = 0 su TUTTI i 6 account con header (51015cc8 0/15, 2f3f93a1 0/457, 802967b0 0/12, 79920814 0/79, 080004f3 0/1, a8094f9a 0/0). A lettura, C (79920814): 30 documenti RID non pagati a DB, 6.163,40 EUR lordo (5.695,30 senza la NC), di cui 3 con data in ottobre 2026 per 205,89 EUR; selezionabili 0. A (51015cc8): 25 RID, nessuno in ottobre. Effetto sul report: Riformulare il titolo di F1d-02: «'Pagate (mese)' non conta le fatture pagate per regola RID: il worker le marca pagate a lettura senza una data di pagamento (a DB restano pagata=false), quindi la card del mese non potra' mai includerle mentre la sezione 'Pagate' le elenca». Togliere «pagata=true ma pagata_at NULL» dal titolo, che fa pensare a un dato sporco a DB. Resta «stessa etichetta per grandezze diverse», gravita' bassa (C: 3 doc / 205,89 EUR nel mese).

- **Gravita' divergente: calendario con oscurate (F1d-03 bassa / F1e-09 alta / F4-04 media) e archivio per mese con NC positive (F1e-07 alta / F1c-03, F1d-01, F4-08 media)** Chi ha ragione: Calendario oscurate: F1d-03 (bassa) — difetto vero nel codice (CalendarView salta solo pagata e is_nota_credito) ma platea quasi nulla: 1 solo documento oscurato in tutto il DB. F1e-09 «alta» e F4-04 «media» sono misurate su dataset sintetici, non sui clienti. Archivio NC positive: F1e-07 (alta) per la scala del brief — numero sbagliato a video oggi su 5 account su 5 che hanno NC, in ogni mese con una NC — con la precisazione che solo il SEGNO delle NC e' un errore; «pagate incluse» e' una definizione (archivio = tutti i documenti) da etichettare, come scrivono F1c-03 e F1e-07. I tre «media» sottostimano la platea (tutti gli account) e l'errore massimo (13,4 % di un mese). Numero vero: Oscurate: 1 documento in tutto il DB (account 080004f3, sede 09011cdd, 382,83 EUR header / 313,78 righe, non pagata, scadenza 02/06/2026): compare solo navigando il calendario a giugno 2026; 0 in ottobre o futuro. Archivio NC: 149 NC attive su 5 account, 44.897,89 EUR sommati col segno positivo (A 106 / 37.453,54; B 2f3f93a1 27 / 4.817,30; D 802967b0 12 / 2.105,60; C 2 / 474,10; E 080004f3 2 / 47,35), 100 % con totale_documento > 0 a video; errore massimo sull'intestazione del mese se le NC vanno sottratte: C giugno 2026 13,41 % (6.980,20 mostrato, NC 468,10), D maggio 10,72 % (25.889,67), B marzo 5,12 %, A maggio 1,55 % (886.132,71). Effetto sul report: Un'unica voce per difetto. Calendario oscurate: gravita' BASSA, «difetto vero, oggi 1 documento su 1 account, visibile solo a giugno 2026». Archivio NC positive: gravita' ALTA per la scala del brief (numero sbagliato a video su tutti i 5 account con NC, fino al 13,4 % del mese), con la correzione di perimetro: il bug e' il segno delle NC (44.897,89 EUR), «pagate ed escluse incluse» e' una definizione da scrivere nell'intestazione, non un numero sbagliato. Fondere F1c-03, F1d-01, F1e-07 e F4-08 in una voce.

## Cosa non è stato possibile verificare in sola lettura

- **La resa a video.** Nessun agente ha aperto l'app: i valori «mostrati» sono ricostruiti eseguendo la stessa formula del codice sui dati estratti, e le funzioni di `lib/` con node. Il rendering dei `.tsx` resta fuori, come in tutti gli audit precedenti.
- **Un sotto-utente vero.** In produzione ce ne sono zero e il brief vietava di crearne. I difetti del filone 2 sono provati su codice, su funzioni e permessi letti dal DB live e sui test esistenti eseguiti su Postgres locale. Restano da provare su un ambiente di test: il tempo di propagazione di 2 secondi su quattro processi del worker, e la rotta TTS con un cookie inventato.
- **La chat che risponde davvero.** Le chiamate a OpenAI erano vietate. I difetti del filone 3 si basano sul testo del prompt e sui dati consegnati al modello, non su risposte osservate. In particolare non è provato quanto spesso il modello divida davvero per il lordo, o sbagli le somme su una lista troncata.
- **Il consumo dei crediti su un guasto reale.** Misurato sul registro esistente: 2 domande fallite su 134 in 4 mesi. Provocarne una nuova richiederebbe una scrittura.
- **Le scadenze calcolate dalle regole dei fornitori.** Il calcolo vive nel worker e richiede un client del DB. Dove una sede non ha regole, il valore salvato equivale a quello calcolato. Su due sedi della catena A con regole attive il ricalcolo SQL non le applica.
- **Aree non guardate per scelta di perimetro:** la pagina Prezzi, le schede di catena «peso categoria», «spreco», «tag» e «prezzi», la card Salute della Home della catena A, `/m/diario` e `/m/turni` sul piano dei numeri. Il critico di completezza le ha segnalate.
- **L'origine di due anomalie nei dati:** i 19 documenti di dicembre 2025 senza righe su un punto vendita della catena A, e i 100 € di costi F&B inseriti a mano su un'altra sede. Capirne la causa richiede i log, non una query.


## Tabella riassuntiva per gravità

| # | ID | Difetto | Gravità | Classificazione | Filone |
|---|---|---|---|---|---|
| 1 | `K01` | Archivio «Per mese»: le note di credito sono sommate come fatture | alta | bug vero | 1+4 |
| 2 | `F1a-02` | Spesa per PV (catena): la fattura ripartita che vive su un PV e' contata intera E come quote → 456,30 € doppi | media | bug vero | 1 |
| 3 | `F1a-04` | 19 header fatture_documenti senza righe (dic 2025, 59.368 €) fanno comparire «Dicembre 2025 (19 fatture)» nel filtro periodo di Analisi Fatture su un mese che non ha righe | media | bug vero | 1 |
| 4 | `K03` | Home: pochi euro manuali in altri_costi_fb rendono «completo» un mese senza fatture | media | bug vero | 1 |
| 5 | `K10` | Card MOL di Margini verde sopra «Nessun giudizio» | media | bug vero | 1 |
| 6 | `K13` | Home della sede ferma mostra un mese a incasso zero | media | bug vero | 1 |
| 7 | `K15` | Catena: anteprima fattura letta dalla sede di sessione | media | bug vero | 4 |
| 8 | `K16` | Chat: 429 di OpenAI letto come limite raggiunto | media | bug vero | 3 |
| 9 | `K19` | query_margini: guasto presentato come nessun dato | media | bug vero | 3 |
| 10 | `K20` | confronto_prezzi fra unità di misura diverse | media | bug vero | 3 |
| 11 | `K21` | query_scadenze senza i totali che la descrizione promette | media | bug vero | 3 |
| 12 | `K23` | Doc GDPR e privacy: anonimizzazione della chat dichiarata ma assente | media | bug vero | 3 |
| 13 | `K26` | TTS: cookie non validato e dati verso Google | media | bug vero | 2 |
| 14 | `K05` | Prompt chat sede: percentuali sul fatturato lordo | media | stessa etichetta per grandezze diverse | 3 |
| 15 | `K06` | Chat query_margini: mesi a fatturato 0 e niente costi_mancanti | media | stessa etichetta per grandezze diverse | 1 |
| 16 | `K07` | «Fatturato» lordo e netto con la stessa parola | media | stessa etichetta per grandezze diverse | 1 |
| 17 | `K08` | Spesa per PV scarta le righe negative, Analisi Fatture le nettizza | media | stessa etichetta per grandezze diverse | 1 |
| 18 | `K11` | Soglie del MOL diverse fra Margini e catena | media | stessa etichetta per grandezze diverse | 1 |
| 19 | `F2a-2` | GET /api/home/config è rotta comune: un sotto-utente senza Home riceve contatori e tetti AI dell'account, soglia alert prezzi e nome referente | bassa | bug vero | 2 |
| 20 | `F2b-3` | Il sotto-utente vede «Configura assistente» (Home e Home di catena), ma il salvataggio è vietato dal worker e il messaggio dice «Riprova» | bassa | bug vero | 2 |
| 21 | `F2b-5` | Le guardie di pagina sono fail-open quando la sessione non è 'ok', e sulla navigazione client il layout (app) non gira: le tab spente dall'admin tornano visibili | bassa | bug vero | 2 |
| 22 | `F2b-6` | lib/fatture.ts mette in cache 60 s mesi-disponibili e categorie con chiave sul token: dopo il cambio sede si vedono quelli della sede precedente | bassa | bug vero | 2 |
| 23 | `F2b-7` | Logout e scadenza della sessione non svuotano sessionStorage: la conversazione con l'assistente (cifre e card) resta leggibile nella stessa scheda dopo l'uscita | bassa | bug vero | 2 |
| 24 | `F2b-8` | Home del sotto-utente: i link di KPI, Salute e «Da fare» portano a pagine che non ha (404) | bassa | bug vero | 2 |
| 25 | `F4-07` | Archivio fatture: il chip «Solo scadute» resta visibile e attivabile ma non cambia l'elenco; checkbox di riga inerti e barra di azioni di massa visibile | bassa | bug vero | 4 |
| 26 | `F4-10` | Esito parziale dell'azione di massa: il toast dice «Errore nel salvataggio» anche quando parte delle fatture è stata scritta | bassa | bug vero | 4 |
| 27 | `F4-11` | Vista gruppo: «Svuota questa sede» non dice quale sede, compare anche quando quella sede non ha nulla nel cestino e risponde «Cestino svuotato» | bassa | bug vero | 4 |
| 28 | `K02` | Calendario in browser conta le fatture escluse dai conti | bassa | bug vero | 1+4 |
| 29 | `K04` | Vista gruppo: selezione e aggiornamento a video per solo file_origine | bassa | bug vero | 4 |
| 30 | `K17` | Chat: crediti consumati su domande fallite | bassa | bug vero | 3 |
| 31 | `K24` | /m diario e turni aperte a chi ha solo Strumenti | bassa | bug vero | 2 |
| 32 | `K25` | Sotto-utente con Catena senza Home | bassa | bug vero | 2+3 |
| 33 | `K27` | Dismiss di una notifica non visibile al sotto-utente | bassa | bug vero | 2 |
| 34 | `F1a-06` | «Prodotti da controllare» (needs_review), «€ esclusi dai margini» (Da Classificare, netto) e chip «Solo da verificare» sono tre popolazioni con etichette vicine | bassa | stessa etichetta per grandezze diverse | 1 |
| 35 | `F1a-07` | Analisi e Tag: «Media periodo» (media semplice dei prezzi giornalieri) e «Prezzo medio / Rispetto alla media» (ponderata spesa/quantita') sono due formule | bassa | stessa etichetta per grandezze diverse | 1 |
| 36 | `K12` | Scadenziario: base IVA mista fra totale documento e somma righe | bassa | stessa etichetta per grandezze diverse | 1 |
| 37 | `K14` | Card «Pagate (mese)»: filtro non dichiarato e pagate RID senza data | bassa | stessa etichetta per grandezze diverse | 1+4 |
| 38 | `F4-06` | In vista Calendario le card e i chip di periodo restano visibili e filtrano, ma il calendario li ignora | bassa | periodo non dichiarato | 4 |
| 39 | `K09` | Spesa di Analisi Fatture contro costi di Margini sullo stesso periodo | bassa | periodo non dichiarato | 1 |
| 40 | `K18` | Prompt: appuntamenti di oggi sul giorno UTC | bassa | periodo non dichiarato | 3 |

Totale: **40 difetti confermati** (1 alta, 17 media, 22 bassa), 8 falsi allarmi, 2 incerti.

## Stato delle correzioni (16/10/2026, notte)

I verbali dei fix sono in `DOCUMENTAZIONE/AUDIT_COPERTURA.md` («Fix n. …»), ognuno con la sua prova per mutazione.

| # | Stato |
|---|---|
| 1 | fix n. 1 |
| 2 | fix n. 25 (migration da applicare al live prima del push) |
| 3 | fix n. 24 |
| 4 | fix n. 19-21 e le due revisioni (regola rivista: 20% e fine mese) |
| 5 | fix n. 22 |
| 6 | fix n. 23 |
| 7 | fix n. 2 + revisore |
| 8 | fix n. 9 |
| 9 | fix n. 10 |
| 10 | fix n. 11 |
| 11 | fix n. 12 |
| 12 | fix n. 18 (documenti allineati al codice, decisione di Mattia) |
| 13 | fix n. 13 (accesso) + n. 18 (privacy) |
| 14 | fix n. 14 |
| 15 | fix n. 15 |
| 16 | fix n. 25 |
| 17 | fix n. 25 |
| 18 | fix n. 25 |
| 19 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 20 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 21 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 22 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 23 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 24 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 25 | fix n. 4 |
| 26 | fix n. 5 |
| 27 | fix n. 6 |
| 28 | fix n. 3 |
| 29 | fix n. 7 |
| 30 | fix n. 16 (storno su guasto di OpenAI non fatto, dichiarato) |
| 31 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 32 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 33 | **aperto** (filone sotto-utenti, prossimo gruppo) |
| 34 | fix n. 25 |
| 35 | fix n. 25 |
| 36 | fix n. 8 |
| 37 | fix n. 4 |
| 38 | fix n. 4 |
| 39 | fix n. 25 |
| 40 | fix n. 17 |

Aperti: 9 su 40, tutti del filone sotto-utenti (#19-24, #31-33). Oggi in produzione non c'e' nessun sotto-utente.

## Conferma

**Durante le fasi Trova e Verifica: zero scritture sul DB, zero modifiche al codice, zero commit.** Ogni query è stata eseguita in una transazione `READ ONLY`. Lo stato del repo è stato confrontato con un'impronta presa prima di partire: identico alla fine di entrambe le fasi. I file di lavoro degli agenti stanno nello scratchpad della sessione, fuori dal repo.

Questo report, i suoi due allegati e l'eccezione in `.gitignore` che permette di versionarlo sono stati committati dopo, su richiesta di Mattia. I fix non fanno parte di questo audit: si fanno uno per volta, ciascuno col suo test provato per mutazione, a partire dal difetto n. 1.

**Allegati:**
- `allegati/FINDING_COMPLETI.md` — il testo integrale dei nove finder, con ciò che hanno verificato e trovato giusto.
- `allegati/QUERY_USATE.md` — le query SQL eseguite, col loro risultato.
