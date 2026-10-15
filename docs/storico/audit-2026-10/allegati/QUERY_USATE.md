# Audit di correttezza ottobre 2026 — le query usate

Tutte eseguite il 15/10/2026 sul DB di produzione dentro `BEGIN READ ONLY; …; COMMIT;`. Nomi dei clienti sostituiti da «[cliente]».

## F1c quadrature sedi singole C+D

### Colonne di margini_mensili (il primo tentativo con ricavi_iva10 e' fallito: i campi sono fatturato_iva10/22)

```sql
BEGIN READ ONLY; SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='margini_mensili' ORDER BY ordinal_position; COMMIT;
```

**Risultato.** 34 colonne, fra cui fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, costi_fb_auto, costi_spese_auto, mol, quote_riparto_*, costo_personale_chiamata

### Sedi dei due account

```sql
BEGIN READ ONLY; SELECT id, user_id, tipo_attivita, nuovi_da FROM ristoranti WHERE user_id IN ('79920814-...','802967b0-...'); COMMIT;
```

**Risultato.** C → f16aebe5-735b-4d1b-a168-81af1547db03 (ristorazione, nuovi_da 14/10); D → 86300227-53c3-4193-9b45-761b3654e889 (ristorazione, nuovi_da 15/7)

### Corpo delle funzioni SQL prima di ragionarci (nessuna chiamata diretta: sola SELECT in entrambe)

```sql
BEGIN READ ONLY; SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('costi_automatici_mensili','scadenziario_fatture_aggregate'); COMMIT;
```

**Risultato.** costi_automatici_mensili: SQL STABLE, filtri deleted_at/oscurata/Da Classificare/ripartita, mese=COALESCE(competenza,documento), food = tutto tranne spese e NOTE; scadenziario_fatture_aggregate: somma totale_riga per file_origine, solo deleted_at

### Totali salvati in margini_mensili per C e D

```sql
BEGIN READ ONLY; SELECT user_id, ristorante_id, anno, mese, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, fatturato_netto, costo_dipendenti, costo_personale_extra, costo_personale_chiamata, altri_costi_fb, altri_costi_spese, quote_riparto_fb, quote_riparto_spese, costi_fb_auto, costi_spese_auto, costi_fb_totali, primo_margine, mol, food_cost_perc, mol_perc, updated_at FROM margini_mensili WHERE user_id IN (...) ORDER BY user_id, anno, mese; COMMIT;
```

**Risultato.** C: 10 righe 2026 (gen-feb vuote, mar-ott con fatturato; mag a 0; altri_costi_spese 300 mar-lug, altri_costi_fb 100 ago; costi_fb_auto/mol salvati a 0 da giugno). D: 6 righe gen-giu (personale 20.000/mese, giu 3.000+500 altri; mag-giu costi salvati a 0)

### Override modalita' mensile

```sql
BEGIN READ ONLY; SELECT r.user_id, m.ristorante_id, m.anno, m.mese, m.modalita, m.fatturato_iva10, m.fatturato_iva22, m.altri_ricavi_noiva, m.coperti FROM ricavi_modalita_mensile m JOIN ristoranti r ON r.id=m.ristorante_id WHERE r.user_id IN (...) ORDER BY 1,3,4; COMMIT;
```

**Risultato.** C 2026-05 mensile 9.328; D 2026-05 mensile 88.606; D 2026-06 mensile 80.655 (altri 0 in tutti)

### Ricalcolo costi auto per mese con la regola SQL dei margini

```sql
BEGIN READ ONLY; SELECT user_id, ristorante_id, EXTRACT(YEAR FROM COALESCE(data_competenza,data_documento))::int anno, EXTRACT(MONTH FROM ...)::int mese, SUM(totale_riga) FILTER (WHERE categoria <> ALL(spese5) AND categoria <> '📝 NOTE E DICITURE') fb_auto, SUM(totale_riga) FILTER (WHERE categoria = ANY(spese5)) spese_auto, COUNT(*), COUNT/SUM FILTER (categoria_fiducia='da_verificare') FROM fatture WHERE user_id IN (...) AND deleted_at IS NULL AND NOT oscurata AND categoria <> 'Da Classificare' AND NOT COALESCE(ripartita_su_gruppo,FALSE) AND COALESCE(data_competenza,data_documento) IS NOT NULL AND EXTRACT(YEAR ...)=2026 GROUP BY 1,2,3,4; COMMIT;
```

**Risultato.** C mar-ott e D gen-lug: valori riportati in verificato_ok; 0 righe da_verificare

### Spesa di Analisi Fatture per mese (data_documento) con scomposizione Da Classificare / competenza altro mese / ripartite / NC

```sql
BEGIN READ ONLY; SELECT user_id, EXTRACT(YEAR FROM data_documento), EXTRACT(MONTH FROM data_documento), SUM(totale_riga) FILTER (WHERE totale_riga<>0) spesa_analisi, COUNT(*) FILTER (WHERE totale_riga<>0), SUM FILTER (categoria='Da Classificare'), SUM FILTER (data_competenza IS NOT NULL AND date_trunc('month',data_competenza)<>date_trunc('month',data_documento)) competenza_altro_mese, SUM FILTER (ripartita_su_gruppo), SUM FILTER (tipo_documento='TD04') FROM fatture WHERE user_id IN (...) AND deleted_at IS NULL AND NOT oscurata AND categoria <> '📝 NOTE E DICITURE' AND data_documento >= '2026-01-01' GROUP BY 1,2,3; COMMIT;
```

**Risultato.** C: mar 9.010,24; apr 6.064,93 (competenza altrove 774,01); mag 6.847,60 (3.020,13); giu 5.111,35 (NC −383,69); lug 3.850,37; ago 4.908,42 (NC −5,45); set 7.326,00; ott 2.380,07. D: gen 17.356,46; feb 36.958,93; mar 24.914,12; apr 20.216,28; mag 19.991,75 (NC −1.156,91); giu 17.239,49; lug 89,08. Da Classificare 0 ovunque

### Volumi e stato righe dei due account

```sql
BEGIN READ ONLY; SELECT user_id, COUNT(*), COUNT(*) FILTER (WHERE oscurata), COUNT(*) FILTER (WHERE deleted_at IS NOT NULL), MIN(data_documento), MAX(data_documento), COUNT(DISTINCT file_origine), COUNT(DISTINCT ristorante_id) FROM fatture WHERE user_id IN (...) GROUP BY user_id; COMMIT;
```

**Risultato.** C: 1.635 righe, 0 oscurate, 0 cancellate, 05/03→07/10/2026, 110 documenti, 1 sede. D: 3.888 righe, 0/0, 05/01→01/07/2026, 343 documenti, 1 sede

### Controlli di uguaglianza fra la query Python dei margini e la RPC, e totali annui Analisi vs Margini

```sql
BEGIN READ ONLY; SELECT user_id, COUNT(*) FILTER (WHERE categoria IS NULL OR btrim(categoria)=''), COUNT(*) FILTER (WHERE categoria='NOTE E DICITURE'), COUNT(*) FILTER (WHERE categoria='📝 NOTE E DICITURE' AND totale_riga<>0), SUM FILTER (NOTE), COUNT(*) FILTER (WHERE competenza in altro anno), SUM(totale_riga) FILTER (WHERE data_documento BETWEEN '2026-01-01' AND '2026-10-15' AND categoria<>NOTE AND totale_riga<>0) analisi_anno_corrente, SUM(totale_riga) FILTER (WHERE COALESCE(competenza,documento) BETWEEN '2026-01-01' AND '2026-10-31' AND categoria<>'Da Classificare' AND categoria<>NOTE AND NOT ripartita) margini_auto_anno FROM fatture WHERE user_id IN (...) AND deleted_at IS NULL AND NOT oscurata GROUP BY 1; COMMIT;
```

**Risultato.** C: 0/0/0/0,00/0, 45.498,98 = 45.498,98. D: 0/0/0/0,00/0, 136.766,11 = 136.766,11

### Documenti nella forma di get_documenti_scadenziario (per eseguire raggruppaPerMeseFattura con node)

```sql
BEGIN READ ONLY; SELECT f.user_id, btrim(f.file_origine), MIN(ristorante_id), MIN(COALESCE(tipo_documento,'TD01')), MIN(data_documento), SUM(totale_riga), BOOL_OR(oscurata), MAX(d.totale_documento), BOOL_OR(d.pagata), MAX(d.scadenza_effettiva), MAX(d.scadenza_override), MAX(d.scadenza_source), MAX(d.pagata_manuale_at), MAX(d.scadenza_xml), MAX(d.giorni_termini_xml), MAX(d.piva_fornitore), MIN(f.fornitore), MIN(f.created_at) FROM fatture f LEFT JOIN fatture_documenti d ON d.file_origine=f.file_origine AND d.ristorante_id=f.ristorante_id AND d.user_id=f.user_id AND d.deleted_at IS NULL WHERE f.user_id IN (...) AND f.deleted_at IS NULL AND f.file_origine IS NOT NULL AND btrim(f.file_origine)<>'' GROUP BY 1,2; COMMIT;
```

**Risultato.** 453 documenti (110 C: 85 TD01, 22 TD24, 2 TD04, 1 TD06; 343 D: 241 TD01, 83 TD24, 12 TD04, 6 TD06, 1 TD02); 0 senza header, 0 oscurate, 0 override scadenza; pagata header: C 79, D 12; pagata_manuale_at: C 20. Salvati in scratchpad, usati con node, poi cancellati

### Regole fornitore (RID) che forzano pagata=True nello scadenziario

```sql
BEGIN READ ONLY; SELECT c.ristorante_id, c.modalita, c.giorni_pagamento, c.data_riferimento, c.attiva, (SELECT COUNT(DISTINCT d.file_origine) FROM fatture_documenti d WHERE d.ristorante_id=c.ristorante_id AND d.piva_fornitore=c.piva_fornitore AND d.deleted_at IS NULL) FROM fornitori_pagamenti_config c WHERE c.ristorante_id IN (...) ORDER BY 1; COMMIT;
```

**Risultato.** D: 1 regola rid (2 documenti). C: 6 regole rid (15+5+6+5+3+9 = 43 documenti)

### Intestazione «Per mese» ricostruita in SQL contro debito reale, NC, pagate (incluso effetto RID)

```sql
BEGIN READ ONLY; WITH docs AS (SELECT user_id, ristorante_id, btrim(file_origine) fo, MIN(COALESCE(tipo_documento,'TD01')) tipo, MIN(data_documento) data_doc, SUM(totale_riga) tot_righe FROM fatture WHERE user_id IN (...) AND deleted_at IS NULL AND file_origine IS NOT NULL GROUP BY 1,2,3), arr AS (SELECT d.*, COALESCE(h.totale_documento, d.tot_righe) totale, COALESCE(h.pagata,false) OR (c.piva_fornitore IS NOT NULL AND h.pagata_manuale_at IS NULL) pagata_eff FROM docs d LEFT JOIN fatture_documenti h ON ... AND h.deleted_at IS NULL LEFT JOIN fornitori_pagamenti_config c ON c.ristorante_id=d.ristorante_id AND c.piva_fornitore=h.piva_fornitore AND COALESCE(c.attiva,true) AND c.modalita='rid') SELECT user_id, to_char(data_doc,'YYYY-MM'), COUNT(*), SUM(totale) tot_per_mese_pagina, COUNT/SUM FILTER (tipo='TD04'), COUNT FILTER (pagata_eff), SUM FILTER (pagata_eff AND tipo<>'TD04'), SUM FILTER (NOT pagata_eff AND tipo<>'TD04') debito_aperto, SUM(non NC) − SUM(NC) acquisti_netti_nc, SUM(tot_righe) FROM arr GROUP BY 1,2 ORDER BY 1,2; COMMIT;
```

**Risultato.** Valori riportati nel finding F1c-03; i tot_per_mese_pagina coincidono con l'output node di raggruppaPerMeseFattura per tutti i 15 mesi

### Ricavi giornalieri (per capire da dove vengono i fatturati di margini_mensili e l'altri_ricavi 500 di D giugno)

```sql
BEGIN READ ONLY; SELECT r.user_id, g.ristorante_id, to_char(g.data,'YYYY-MM'), COUNT(*), SUM(fatturato_iva10), SUM(fatturato_iva22), SUM(altri_ricavi_noiva) FROM ricavi_giornalieri g JOIN ristoranti r ON r.id=g.ristorante_id WHERE r.user_id IN (...) GROUP BY 1,2,3 ORDER BY 1,3; COMMIT;
```

**Risultato.** C: giu 26 gg 7.625,25; lug 26 gg 8.832,40; ago 16 gg 4.993,60; set 27 gg 8.603,50; ott 14 gg 4.949,20. D: mag 1 riga 88.606,27; giu 1 riga 3.000 + 500 altri. Nessun giornaliero per D lug-ott

## F4 gestione fatture azioni e contatori

### Nessuna query SQL: il compito F4 era solo codice ed esecuzione. Tutte le cifre vengono da node --experimental-strip-types su apps/web/src/lib/scadenziario.ts (hook di risoluzione @/ come tests/helpers_ts.py) con un dataset sintetico di 16 documenti (sedi rA, rB; scadute, settimana, mese, oltre, senza scadenza, pagate mese e mese prima, NC aperta e pagata, oscurata scaduta e futura, DUP.xml aperta/pagata, DUP2.xml aperta/aperta), data di sistema 15/10/2026 UTC

```sql
N/A (esecuzione node: computeKpi, bucketizeDocumenti, contaDaPagare, chiaviSelezionaTutte, statoSelezioneSezione, pianoAzioneDiMassa, messaggioConfermaAzioneDiMassa, motivoAzioneSpenta, aggregaPerSede, filtraDocumenti, alternaPuntoVendita, raggruppaPerMeseFattura, statoDocumento, scaduteFuoriDalMese, applicaPagataAVideo più la replica della regola CalendarView :497-506 e delle righe client :1882-1891 e :1907)
```

**Risultato.** Gruppo: KPI scadute 4/1600, settimana 1/300, da pagare 9/3320, pagate mese 2/720. Seleziona tutte 9 contro Set 8. Piano DUP2 con 2 gruppi e 2 cambiano su una sola spunta. Dopo Seleziona tutte «Segna non pagate» è acceso e invia rB:[DUP.xml] (in mono-sede è spento). Calendario ottobre giorno 20 = 350 € oscurata. Pagate (mese) dopo Scadute = 0. Archivio settembre (sede A) 1220 con la NC +150. handleSetScadenza porta scadute a 1500 invece di 1550. handleElimina lascia 0 righe DUP2 invece di 1.

## F1b quadrature catena B

### Sedi dell'account, settore, flag no IVA, sede tecnica

```sql
BEGIN READ ONLY; SELECT id, tipo_attivita, escludi_ricavi_noiva, sede_tecnica, created_at::date FROM ristoranti WHERE user_id = '2f3f93a1-c1f4-4804-858e-a161e6f36f3f' ORDER BY created_at; COMMIT;
```

**Risultato.** 3 sedi: dcf1996e e bdda08d1 (ristorazione, escludi false, sede_tecnica false), f7bba05f (sede_tecnica true, escludi false)

### Snapshot margini_mensili 2026 dell'account (tutte le colonne usate dai lettori)

```sql
BEGIN READ ONLY; SELECT ristorante_id, anno, mese, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, fatturato_netto, costi_fb_auto, costi_spese_auto, altri_costi_fb, altri_costi_spese, quote_riparto_fb, quote_riparto_spese, costo_dipendenti, costo_personale_extra, costo_personale_chiamata, mol, mol_perc, updated_at FROM margini_mensili WHERE user_id = '2f3f93a1-…' ORDER BY ristorante_id, anno, mese; COMMIT;
```

**Risultato.** 20 righe (2 PV × gen–ott): costi_*_auto = 0 e mol_perc = 0 ovunque; bdda fatturato 0 su tutti i mesi; dcf fatturato gen–giu; quote riparto e personale valorizzati; ottobre personale 0

### Corpo della funzione SQL costi_automatici_mensili prima di replicarla (verifica sola lettura)

```sql
BEGIN READ ONLY; SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='costi_automatici_mensili'; COMMIT;
```

**Risultato.** LANGUAGE sql STABLE, solo SELECT: filtri deleted_at IS NULL, NOT oscurata, categoria <> 'Da Classificare', NOT COALESCE(ripartita_su_gruppo,FALSE), mese=COALESCE(data_competenza,data_documento); food = non spese e non NOTE

### Override modalità mensile dell'account

```sql
BEGIN READ ONLY; SELECT ristorante_id, anno, mese, modalita, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, coperti, updated_at FROM ricavi_modalita_mensile WHERE ristorante_id IN ('dcf1996e-…','bdda08d1-…','f7bba05f-…') ORDER BY 1,2,3; COMMIT;
```

**Risultato.** 18 righe modalita='mensile' gen–set 2026 per bdda e dcf (es. bdda set 49.006,70 + 7.025,80 noIVA; dcf set 32.442,95 + 1.791,85); ottobre assente

### Ricavi giornalieri dell'account

```sql
BEGIN READ ONLY; SELECT ristorante_id, EXTRACT(YEAR FROM data), EXTRACT(MONTH FROM data), count(*), SUM(fatturato_iva10), SUM(fatturato_iva22), SUM(altri_ricavi_noiva), SUM(coperti) FROM ricavi_giornalieri WHERE ristorante_id IN (…3 sedi…) GROUP BY 1,2,3; COMMIT;
```

**Risultato.** 0 righe: l'account non usa i giornalieri

### Trigger e funzione del blocco no IVA sul live

```sql
BEGIN READ ONLY; SELECT tgname, tgrelid::regclass, tgenabled FROM pg_trigger WHERE tgname LIKE '%noiva%'; COMMIT;  /  SELECT md5(pg_get_functiondef(p.oid)), position('RETURN NULL' in …)>0, position('TG_TABLE_NAME = ''margini_mensili''' in …)>0 FROM pg_proc … proname='ricavi_noiva_esclusi_guardia'
```

**Risultato.** 3 trigger attivi (O) su ricavi_giornalieri, ricavi_modalita_mensile, margini_mensili; funzione presente con entrambi i rami

### Sedi di TUTTI gli account con esclusione no IVA attiva e residui no IVA

```sql
BEGIN READ ONLY; SELECT r.user_id, r.id, r.escludi_ricavi_noiva, (SELECT COALESCE(SUM(altri_ricavi_noiva),0) FROM margini_mensili mm WHERE mm.ristorante_id=r.id), (SELECT COALESCE(SUM(altri_ricavi_noiva),0) FROM ricavi_modalita_mensile m WHERE m.ristorante_id=r.id), (SELECT COALESCE(SUM(altri_ricavi_noiva),0) FROM ricavi_giornalieri g WHERE g.ristorante_id=r.id) FROM ristoranti r WHERE r.escludi_ricavi_noiva = true; COMMIT;
```

**Risultato.** 0 righe: nessuna sede esclusa su tutto il DB

### Righe Da Classificare, ripartite e oscurate dell'account

```sql
BEGIN READ ONLY; SELECT ristorante_id, categoria, ripartita_su_gruppo, oscurata, count(*), SUM(totale_riga), MIN(COALESCE(data_competenza,data_documento)), MAX(…) FROM fatture WHERE user_id='2f3f93a1-…' AND deleted_at IS NULL AND (categoria='Da Classificare' OR ripartita_su_gruppo OR oscurata) GROUP BY 1,2,3,4; COMMIT;  /  SELECT id, ristorante_id, data_documento, categoria, totale_riga, needs_review, ripartita_su_gruppo … WHERE categoria='Da Classificare'
```

**Risultato.** Nessuna oscurata; sede tecnica 979 righe tutte ripartite (74.773,50 €) di cui 3 Da Classificare (24,05 €, needs_review); 1 Da Classificare su bdda (0,00 €, 13/10, needs_review)

### Ricalcolo costi auto per sede/mese 2026 con la definizione SQL

```sql
BEGIN READ ONLY; SELECT ristorante_id, EXTRACT(YEAR …), EXTRACT(MONTH FROM COALESCE(data_competenza,data_documento)), SUM(CASE WHEN categoria IN ('SERVIZI E CONSULENZE','UTENZE E LOCALI','MANUTENZIONE E ATTREZZATURE','RAPPRESENTANZA','MATERIALE DI CONSUMO') THEN totale_riga ELSE 0 END) AS spese, SUM(CASE WHEN categoria NOT IN (…) AND categoria <> '📝 NOTE E DICITURE' THEN totale_riga ELSE 0 END) AS food, count(*) FROM fatture WHERE user_id='2f3f93a1-…' AND deleted_at IS NULL AND oscurata=false AND categoria <> 'Da Classificare' AND ripartita_su_gruppo=false AND COALESCE(data_competenza,data_documento) >= '2026-01-01' GROUP BY 1,2,3; COMMIT;
```

**Risultato.** 20 righe; es. bdda set food 21.590,56 spese 8.126,29, ott 6.696,31/244,91; dcf set 9.379,13/1.363,31, ott 3.646,06/416,87

### Conto economico ricalcolato per sede e mese (override + costi auto + manuali + quote + personale)

```sql
BEGIN READ ONLY; WITH c AS (…costi auto come sopra…), m AS (SELECT mm.*, COALESCE(o.fatturato_iva10, mm.fatturato_iva10) …, COALESCE(o.altri_ricavi_noiva, mm.altri_ricavi_noiva) … FROM margini_mensili mm LEFT JOIN ricavi_modalita_mensile o ON … AND o.modalita='mensile' WHERE mm.user_id='2f3f93a1-…' AND mm.anno=2026) SELECT rid, mese, override, lordo, netto=iva10/1.10+iva22/1.22+altri, fb_auto, spese_auto, altri_costi_*, quote_riparto_*, personale, fb_tot, spese_tot, mol, mol_pct, fc_pct FROM m LEFT JOIN c …; COMMIT;
```

**Risultato.** 20 righe: es. bdda set lordo 56.032,50 netto 51.577,35 fb_tot 22.027,40 spese_tot 11.212,27 pers 12.174,00 MOL 6.163,68 (12,0 %, fc 42,7 %); dcf set 34.234,80 / 31.285,44 / 9.428,95 / 4.449,28 / 11.240,00 / 6.167,21 (19,7 %, 30,1 %); ottobre netto 0 con MOL −7.359,68 e −4.481,38; agosto netto 16.265,09 e 5.935,87

### Aggregati per periodo (set, ott, gen–set, gen–ott, mag–ott) per sede e gruppo

```sql
BEGIN READ ONLY; WITH … r AS (…conto economico per mese…), p AS (SELECT 'set',9,9 UNION ALL SELECT 'ott',10,10 UNION ALL SELECT 'gen-set',1,9 UNION ALL SELECT 'gen-ott',1,10 UNION ALL SELECT 'mag-ott',5,10) SELECT p.periodo, COALESCE(r.rid,'GRUPPO'), SUM(lordo), SUM(netto), SUM(fb_auto), SUM(spese_auto), SUM(altri_costi_fb), SUM(altri_costi_spese), SUM(quote_riparto_fb), SUM(quote_riparto_spese), SUM(personale), SUM(fb_tot), SUM(spese_tot), SUM(netto-fb_tot-spese_tot-personale) AS mol, mol/netto*100, fb_tot/netto*100 FROM p JOIN r ON r.mese BETWEEN p.m0 AND p.m1 GROUP BY GROUPING SETS ((p.periodo, r.rid),(p.periodo)); COMMIT;
```

**Risultato.** gen–ott gruppo: lordo 825.296,66 netto 756.400,18 fb 289.274,21 spese 179.704,11 pers 177.633,28 MOL 109.788,58 (14,5 %, fc 38,2 %); bdda 511.586,99/470.010,65/189.374,40/102.196,16/97.768,54/80.671,55 (17,2 %); dcf 313.709,67/286.389,53/99.899,81/77.507,95/79.864,74/29.117,03 (10,2 %); gen–set gruppo MOL 121.629,64 (16,1 %), bdda 88.031,23 (18,7 %), dcf 33.598,41 (11,7 %); set gruppo lordo 90.267,30 MOL 12.330,89 (14,9 %); ott gruppo MOL −11.841,06 con netto 0

### data_competenza vs data_documento sull'account

```sql
BEGIN READ ONLY; SELECT ristorante_id, ripartita_su_gruppo, count(*), round(SUM(totale_riga),2), count(*) FILTER (WHERE data_competenza IS NOT NULL), count(*) FILTER (WHERE data_competenza IS NOT NULL AND date_trunc('month',data_competenza) <> date_trunc('month',data_documento)), SUM(totale_riga) FILTER (…stesso filtro…) FROM fatture WHERE user_id='2f3f93a1-…' AND deleted_at IS NULL GROUP BY 1,2; COMMIT;
```

**Risultato.** 4.849 righe attive, data_competenza NULL su tutte: 0 righe / 0 € con mese diverso

### Spesa di Analisi Fatture (data_documento, include Da Classificare, no NOTE, + quote proiettate) vs costi di Margini per sede/mese

```sql
BEGIN READ ONLY; WITH af AS (SELECT ristorante_id, EXTRACT(MONTH FROM data_documento), SUM(totale_riga) FILTER (WHERE categoria <> '📝 NOTE E DICITURE'), SUM(totale_riga) FILTER (WHERE categoria='Da Classificare') FROM fatture WHERE user_id='2f3f93a1-…' AND deleted_at IS NULL AND oscurata=false AND ripartita_su_gruppo=false AND EXTRACT(YEAR FROM data_documento)=2026 GROUP BY 1,2), qt AS (SELECT q.ristorante_id, rc.mese, SUM(q.quota_importo), SUM(q.quota_importo) FILTER (WHERE q.categoria='Da Classificare') FROM riparto_costi_catena_quote q JOIN riparto_costi_catena rc ON rc.id=q.riparto_id WHERE rc.user_id='2f3f93a1-…' AND rc.anno=2026 GROUP BY 1,2), c AS (…costi auto…) SELECT rid, mese, af_own+quote_tot AS spesa_analisi_fatture, fb_auto+spese_auto+altri_costi_fb+altri_costi_spese+quote_riparto_fb+quote_riparto_spese AS costi_margini, diff, dc_own, dc_quote, altri_costi_manuali, quote_tot-quote_dc-quote_riparto_fb-quote_riparto_spese AS quote_vs_snapshot FROM margini_mensili mm LEFT JOIN af … LEFT JOIN qt … LEFT JOIN c …; COMMIT;
```

**Risultato.** bdda diff gen −483, feb −372, mar −342, apr −291, mag −235, giu −535, lug −381, ago −68,17 (−72 + 3,83 DC), set −378,81 (−387 + 8,19 DC), ott 0; dcf diff 0 tranne ago +3,83 e set +8,18; quote_vs_snapshot 0,00 su 20/20 mesi

### Quote riparto per PV/mese per tipo e classe di categoria (FB/SPESE/DC/NULL)

```sql
BEGIN READ ONLY; SELECT q.ristorante_id, rc.anno, rc.mese, rc.tipo, CASE WHEN q.categoria IS NULL THEN 'NULL' WHEN q.categoria='Da Classificare' THEN 'DC' WHEN q.categoria IN (…spese…) THEN 'SPESE' WHEN q.categoria='📝 NOTE E DICITURE' THEN 'NOTE' ELSE 'FB' END, count(*), round(SUM(q.quota_importo),2) FROM riparto_costi_catena_quote q JOIN riparto_costi_catena rc ON rc.id=q.riparto_id WHERE rc.user_id='2f3f93a1-…' AND rc.anno=2026 GROUP BY 1,2,3,4,5; COMMIT;
```

**Risultato.** Gennaio: tipo fb/FB 6.308,39 (bdda) e 2.102,80 (dcf), tipo generale/FB 0,91, tipo fb/SPESE 20,77 e 6,92, generale/SPESE 3.942,25; quote DC: ago 3,83 e set 8,19/8,18 per PV; nessuna categoria NULL

### Coincidenza mese del riparto / mese di data_documento delle righe reali

```sql
BEGIN READ ONLY; SELECT rc.anno, rc.mese, count(DISTINCT rc.id), count(DISTINCT rc.file_origine), count(*) FILTER (WHERE rc.file_origine IS NULL), SUM(rc.importo_totale), (SELECT count(*) FROM fatture f WHERE f.user_id=rc.user_id AND f.file_origine = ANY(array_agg(rc.file_origine)) AND f.deleted_at IS NULL AND (EXTRACT(YEAR FROM f.data_documento)<>rc.anno OR EXTRACT(MONTH FROM f.data_documento)<>rc.mese)) FROM riparto_costi_catena rc WHERE rc.user_id='2f3f93a1-…' AND rc.anno=2026 GROUP BY rc.user_id, rc.anno, rc.mese; COMMIT;
```

**Risultato.** 10 mesi, 200 riparti da file (0 manuali), 0 righe con mese documento diverso dal mese del riparto

### Totali salvati vs ricalcolati per ogni mese 2026

```sql
BEGIN READ ONLY; WITH c AS (…costi auto…) SELECT mm.ristorante_id, mm.mese, mm.fatturato_netto, netto_ricalc, mm.costi_fb_auto, fb_auto_ricalc, mm.costi_spese_auto, spese_auto_ricalc, mm.mol, mol_ricalc, mm.mol_perc, mm.primo_margine, mm.costi_fb_totali, mm.food_cost_perc, mm.coperti FROM margini_mensili mm LEFT JOIN ricavi_modalita_mensile o … LEFT JOIN c … WHERE mm.user_id='2f3f93a1-…' AND mm.anno=2026 ORDER BY 1,2; COMMIT;
```

**Risultato.** 20/20 mesi divergono: costi auto salvati 0, mol_perc 0; es. dcf gen netto 28.222,63 vs 28.075,14, mol 14.158,93 vs 81,79; bdda feb mol −21.034,29 vs 22.342,63; ott −418,46 vs −7.359,68

### Funzioni SQL che leggono le colonne salvate e corpo di riparto_quote_mensili / gruppo_spesa_pivot / gruppo_salute_componenti / sync_margini_mensili_from_ricavi

```sql
BEGIN READ ONLY; SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND (p.prosrc ILIKE '%fatturato_netto%' OR p.prosrc ILIKE '%mol_perc%' OR p.prosrc ILIKE '%costi_fb_auto%' OR p.prosrc ILIKE '%.mol%'); COMMIT;  /  SELECT proname, prosrc … WHERE proname ILIKE '%riparto%' OR '%spesa_pivot%' OR '%salute_componenti%' OR '%sync_margini%'
```

**Risultato.** Solo scrittori: elimina_ricavi_noiva, ricavi_noiva_esclusi_guardia, riparto_quote_mensili, sync_margini_mensili_from_ricavi; riparto_quote_mensili esclude 'Da Classificare' da q_spese e decide FB/spese per categoria; gruppo_spesa_pivot esclude Da Classificare e totale_riga <= 0

### NULL su ripartita_su_gruppo/oscurata e righe con competenza su tutto il DB

```sql
BEGIN READ ONLY; SELECT count(*) FILTER (WHERE ripartita_su_gruppo IS NULL), count(*) FILTER (WHERE oscurata IS NULL), count(*) FILTER (WHERE data_competenza IS NOT NULL), count(*) FROM fatture WHERE deleted_at IS NULL; COMMIT;
```

**Risultato.** 0 NULL, 0 NULL, 229 con competenza, 40.737 righe attive

### Documenti dell'account

```sql
BEGIN READ ONLY; SELECT count(*), count(*) FILTER (WHERE deleted_at IS NULL), min(data_documento), max(data_documento), max(created_at)::date FROM fatture_documenti WHERE user_id='2f3f93a1-…'; COMMIT;
```

**Risultato.** 802 totali, 569 attivi, 1/1→13/10/2026, ultimo caricamento 14/10

## F3 chat di catena

### Nessuna query SQL: il filone 3 è dichiarato solo codice ed esecuzione di funzioni pure.

```sql
(nessuna)
```

**Risultato.** Ho eseguito script Python (-I) nello scratchpad (ora cancellato) con funzioni estratte via AST da services/fastapi_worker.py: _chat_risolvi_sede, _chat_esegui_tool_catena, _chat_esegui_tool_gruppo, _chat_query_margini, _kpi_periodo, _chat_confronto_prezzi, _chat_query_scadenze. Ho caricato utils/voci_prezzo.py dal file, senza importare i pacchetti services o utils. Ho eseguito con node --experimental-strip-types (stesso prologo di tests/helpers_ts.py) lib/home-chat.ts e lib/sotto-utente.ts veri: parseConversazione, vociDellaVista, codaPerVista, corpoRichiestaChat, conRisposta, quotaEsaurita, contatoreAggiornato, statoCrediti, messaggioRisposta, idPersona, chiaveConversazione. git status --porcelain è identico alla baseline.

## F1a quadrature catena A

### Sedi dell'account e numero header

```sql
SELECT id, sede_tecnica, tipo_attivita, attivo, escludi_ricavi_noiva, created_at::date, (SELECT count(*) FROM fatture_documenti fd WHERE fd.ristorante_id=r.id AND fd.deleted_at IS NULL) FROM ristoranti r WHERE user_id='51015cc8-…'
```

**Risultato.** 5 sedi, nessuna sede tecnica; header 1101 / 467 / 452 / 581 / 0 (0c23548c creata 14/09 senza dati)

### Corpo delle funzioni SQL prima di chiamarle

```sql
SELECT pg_get_functiondef(…) per costi_automatici_mensili, gruppo_spesa_pivot, scadenziario_fatture_aggregate, riparto_quote_mensili
```

**Risultato.** le prime tre STABLE/sola lettura (chiamate); riparto_quote_mensili scrive (NON chiamata, letto solo il corpo: filtro Da Classificare presente)

### margini_mensili 2026 delle 4 sedi (ricavi, costi manuali, quote, personale, totali salvati)

```sql
SELECT ristorante_id, mese, fatturato_iva10, fatturato_iva22, altri_ricavi_noiva, fatturato_netto, costi_fb_auto, costi_spese_auto, altri_costi_fb, altri_costi_spese, quote_riparto_fb, quote_riparto_spese, costo_dipendenti, costo_personale_extra, costo_personale_chiamata, mol, mol_perc FROM margini_mensili WHERE user_id='51015cc8-…' AND anno=2026
```

**Risultato.** 40 righe; costi_*_auto = 0 ovunque tranne fd7ac484 gen-apr; 0dca4d1f set altri_costi_fb = 100; personale 60.000 gen-giu (fd7ac484 fino a lug), poi 0

### Costi automatici live via RPC per sede/mese

```sql
SELECT r.id, m.* FROM ristoranti r CROSS JOIN LATERAL costi_automatici_mensili(user, r.id, 2026, ARRAY[]::text[], ARRAY[5 categorie spese], false) m
```

**Risultato.** es. cc016821: mar 37.691,08/1.819,60; apr 133.473,14/41.800,36; mag 153.261,31/26.099,84; giu 128.888,81/39.179,14; lug 85.514,49/43.341,72; nessuna sede oltre luglio

### Replica indipendente dei costi auto mag/giu/lug

```sql
SELECT ristorante_id, EXTRACT(MONTH FROM COALESCE(data_competenza,data_documento)), SUM(totale_riga) FILTER (categoria NOT IN spese+NOTE), SUM FILTER (categoria IN spese) FROM fatture WHERE user_id=… AND deleted_at IS NULL AND NOT oscurata AND categoria<>'Da Classificare' AND NOT COALESCE(ripartita_su_gruppo,false) AND anno=2026 AND mese IN (5,6,7) GROUP BY 1,2
```

**Risultato.** 10 celle identiche alla RPC al centesimo

### Override ricavi modalita' mensile

```sql
SELECT * FROM ricavi_modalita_mensile WHERE ristorante_id IN (sedi) AND anno=2026
```

**Risultato.** 0 righe

### Ricalcolo per sede e mese (netto, F&B, spese, personale, MOL, MOL%) con confronto ai salvati

```sql
WITH c AS (RPC costi), mm AS (margini_mensili scorporo IVA) SELECT … netto-fb-spese-pers, (…)/netto*100, fb_salvato, mol_salvato, molp_salvato … WHERE mese IN (5,6,7,9)
```

**Risultato.** vedi verificato_ok; fd7ac484 mag/giu mol salvato 280.923,99 (100%) vs live 186.878,67 (39,1%) / 212.635,37 (42,9%)

### Aggregati per periodo (gen-ott, mag-lug, set, apr-giu) per sede e totale

```sql
… GROUP BY ROLLUP((periodo, rid)) con conteggio mesi senza F&B
```

**Risultato.** gen-ott MOL% 76,4 / 75,3 / 70,9 / 54,2 con 5 / 6 / 5 / 3 mesi senza F&B; mag-lug 64,6 / 64,6 / 47,8 / 37,9

### Scadenziario cc016821: replica computeKpi

```sql
WITH docs AS (fatture attive GROUP BY file_origine, ristorante_id), j AS (LEFT JOIN fatture_documenti attive) SELECT conteggi/importi per oscurata, TD04, pagata, scadenza_effettiva < '2026-10-15', IS NULL
```

**Risultato.** 581 doc, 0 oscurate, 18 NC (12 scadute, 5.113,26), 0 pagate, da pagare 563 / 784.224,60, scadute 438 / 665.885,04, senza scadenza 125 / 118.339,56, 1 senza header

### Gruppo: documenti, NC, oscurate, pagate, selezionabili, file su piu' sedi, header

```sql
… SELECT COUNT(*), COUNT(DISTINCT file_origine), SUM(nc), SUM(oscurata), SUM(pagata), SUM(selezionabile), (file_origine con >1 ristorante_id), (COUNT fatture_documenti attivi)
```

**Risultato.** 2.582 / 2.582 / 106 / 0 / 15 / 2.461 / 0 / 2.601

### Header senza righe

```sql
SELECT ristorante_id, COUNT(*), SUM(esiste riga anche cancellata), MIN/MAX data, SUM(totale_documento) FROM fatture_documenti fd WHERE user=… AND deleted_at IS NULL AND NOT EXISTS (fatture attive stesso file_origine/sede)
```

**Risultato.** fd7ac484: 19 header, 0 con righe, dic 2025, 59.368,37 €

### Fonte scadenza e regole fornitore

```sql
SELECT scadenza_source, COUNT(*), … FROM fatture_documenti WHERE ristorante_id='cc016821-…'; SELECT ristorante_id, modalita, giorni, (COUNT doc del fornitore) FROM fornitori_pagamenti_config WHERE user=… AND attiva
```

**Risultato.** cc016821: 450 xml, 131 none (=125 non pagate senza scadenza + 6 NC); regole: 1 su 0dca4d1f (4 doc), 4 su fd7ac484 (12+13+115+94 doc), 0 su cc016821

### Da Classificare per sede

```sql
SELECT ristorante_id, COUNT(*), SUM(totale_riga), COUNT(DISTINCT file_origine), SUM(oscurata), SUM(ripartita) FROM fatture WHERE user=… AND deleted_at IS NULL AND categoria='Da Classificare' GROUP BY 1; + split positivo/negativo/zero/needs_review
```

**Risultato.** 13 / 46 / 56 / 18 righe; 474,92 / 944,89 / 582,02 / −1.302,36 €; cc016821 = +6.280,00 −5.697,98, 2 a zero, 54 needs_review

### needs_review e max date per sede

```sql
SELECT ristorante_id, MAX(data_documento), MAX(created_at), COUNT(*), COUNT(DISTINCT file_origine), SUM(needs_review), SUM(totale_riga) FILTER (needs_review), COUNT(DISTINCT lower(trim(descrizione))) FILTER (needs_review AND totale_riga<>0) FROM fatture … NOT oscurata GROUP BY 1
```

**Risultato.** ultime fatture 30/06 (0dca, 5444) e 31/07 (cc01, fd7); cc016821 needs_review 156 righe / 14.286,41 € / 89 prodotti

### Note di credito per sede

```sql
WITH nc AS (fatture TD04 per documento) SELECT COUNT(*), SUM(tot_righe), righe neg/pos, SUM(fd.totale_documento), MIN/MAX(segno_compensazione) … JOIN fatture_documenti
```

**Risultato.** 20 / 17 / 18 / 51 doc; header 7.265,59 / 4.570,22 / 5.113,26 / 20.504,47; righe −6.642,16 / −4.275,76 / −4.911,95 / −19.407,26; segno −1 su tutti

### Spesa catena (pivot) vs Analisi Fatture, gen→15/10

```sql
SELECT ristorante_id, SUM FILTER (totale_riga>0 AND categoria<>'Da Classificare' AND COALESCE(data_competenza,data_documento) BETWEEN …), SUM FILTER (totale_riga<>0 AND categoria<>NOTE AND data_documento BETWEEN …), SUM FILTER (totale_riga<0), SUM FILTER (Da Classificare), righe con data_competenza diversa FROM fatture … NOT oscurata GROUP BY 1; + split righe negative per TD04/non TD04
```

**Risultato.** 572.236,89 vs 553.914,91; 569.856,03 vs 560.045,22; 705.730,79 vs 691.651,51; 1.695.570,45 vs 1.626.446,58; negative 122.398,82 (NC 46.863,11, altre 75.535,71); 0 righe con competenza diversa

### Riparto dell'account e fattura ripartita

```sql
SELECT rc.anno, rc.mese, rc.tipo, rc.importo_totale, q.ristorante_id, q.categoria, q.quota_importo FROM riparto_costi_catena rc JOIN riparto_costi_catena_quote q …; SELECT … FROM fatture WHERE file_origine='IT08172050968_0ofr3.xml.p7m'
```

**Risultato.** gen 2026, 456,30 generale, quote 1,25 + 112,83 (4 PV); 2 righe su fd7ac484 con ripartita_su_gruppo = true (5,00 + 451,30)

### Doppio conteggio nella pivot catena

```sql
SELECT * FROM gruppo_spesa_pivot(4 PV, 'categoria', '2026-01-01', '2026-01-31', false) WHERE dim_val IN (SERVIZI, UTENZE); SELECT categoria, SUM(totale_riga), SUM FILTER (NOT ripartita) FROM fatture fd7ac484 gen, totale_riga>0
```

**Risultato.** RPC: 5.975,70 / 34.249,99; senza ripartite: 5.970,70 / 33.798,69

### Tag esistenti

```sql
SELECT COUNT(*) FROM custom_tags WHERE user_id=…; gruppo_tags; fornitori_pagamenti_config attive
```

**Risultato.** 13 tag custom, 3 di gruppo, 5 regole

### Esecuzione pura (no DB): medie del tag

```sql
python: _compute_trend / _compute_fornitori / _compute_kpi su 2 righe KG (10 kg @9, 1 kg @11), streamlit mockato
```

**Risultato.** prezzo_medio_periodo 10,0; prezzo_medio_tag 9,1818; prezzo_medio_ponderato 9,1818

## F1e definizioni e periodi

### Nessuna query SQL: il filone F1e è solo codice. Esecuzione node delle due copie di calcolaPeriodo (margini/periodi.ts e analisi-fatture/periodi.ts) su 11 preset, 2 date (15/10/2026 12:00 e 1/10/2026 00:30), TZ Europe/Rome e UTC

```sql
node --experimental-strip-types periodi.mjs (scratchpad/audit/f1e, cancellato): import delle due periodi.ts via module.registerHooks su @/, confronto data_da/data_a/label
```

**Risultato.** 4 preset condivisi UGUALI su entrambe le date e TZ; anno_precedente, q1-q4, h1, h2 divergono (la copia Analisi Fatture ricade su «Anno in corso»); nessun chip UI li offre

### Soglie MOL: esecuzione pura di _valuta_soglia_margine (routers/margini.py) e _colore_margine (routers/gruppo.py) estratte con ast (utf-8-sig per il BOM) e confronto KPI_SOGLIE vs _KPI_SOGLIE_MARGINI

```sql
python -I soglie.py: exec dei soli nodi ast _KPI_SOGLIE_MARGINI, _valuta_soglia_margine, _colore_margine, KPI_SOGLIE; valori 4,7,10,13,18,25
```

**Risultato.** 7% → 🟠 vs rosso; 10% → 🟠 vs giallo; 13% → 🟡 vs giallo; 18% → 🟡 vs verde; 25% → 🟢 vs verde. KPI_SOGLIE ≠ _KPI_SOGLIE_MARGINI solo nel tetto 100/200 di mol e primo_margine, esito identico

### Colori catena: margineDot, tintConti, tintContiPV di lib/catena-confronti.ts e replica della logica inline di /m mobile-catena.tsx

```sql
node --experimental-strip-types tint.mjs: margineDot(4..25), tintConti su mol ±, livello completo/food/nessuno/assente, tintContiPV con costi_mancanti/incasso_fuori_norma, inline mobile vs tintConti su 7 casi
```

**Risultato.** SOGLIA_MARGINE_VERDE=15, GIALLO=8; margineDot 7→negativo, 13→incerto, 18→positivo; tintConti giallo per ogni livello ≠ completo; tintContiPV giallo con costi_mancanti o incasso_fuori_norma; mobile inline = tintConti su 7/7 casi

### Scadenziario: filtraDocumenti(periodo «tutti»), raggruppaPerMeseFattura, statoDocumento, scaduteFuoriDalMese, bucketizeDocumenti, computeKpi di lib/scadenziario.ts su 4 documenti sintetici (NC 300, oscurata 500, pagata 700, aperta 1100, scadenze 20-23/10/2026, oggi 15/10/2026) + replica della logica inline di CalendarView e del worker

```sql
TZ=Europe/Rome node --experimental-strip-types scad.mjs
```

**Risultato.** documentiCalendario include l'oscurata; «Per mese» settembre 2026: conteggio 4, totale 2.600 (NC sommata positiva); CalendarView ottobre {21:500, 23:1100} = 1.600 vs worker {23:1100}; statoDocumento osc=«Escluse da te», nc=«Nota di credito»; computeKpi da_pagare 1 / 1.100; bucketize oscurate 1, noteCredito 1, pagate 1

### Verifica di non-modifica del repo

```sql
git status --porcelain a inizio e fine; diff
```

**Risultato.** IDENTICO (M .claude/settings.json, M tests/test_brevo_mittente_default.py, ?? AVATAR/, ?? avvia-locale.sh, ?? ferma-locale.sh)

## F1d scadenziario a DB

### Corpo della RPC usata dallo Step 1 di get_documenti_scadenziario

```sql
BEGIN READ ONLY; SELECT pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.proname='scadenziario_fatture_aggregate'; COMMIT;
```

**Risultato.** plpgsql SECURITY DEFINER, solo SELECT su fatture (user_id, ristorante_id = ANY, deleted_at IS NULL, file_origine non vuoto), DISTINCT ON prima riga + SUM(totale_riga)

### Tentativo di chiamata diretta della RPC per C

```sql
BEGIN READ ONLY; SELECT count(*), sum(totale_documento) FROM public.scadenziario_fatture_aggregate('79920814-...'::uuid, ARRAY['f16aebe5-...']::uuid[]); COMMIT;
```

**Risultato.** ERROR P0001 Accesso negato (auth.role() via MCP non e' service_role) -> corpo replicato nella CTE

### Sedi dei due account, flag attivo/sede_tecnica, documenti per sede

```sql
BEGIN READ ONLY; SELECT r.id, r.user_id, r.attivo, r.sede_tecnica, r.nuovi_da, (SELECT count(*) FROM fatture f WHERE f.ristorante_id=r.id AND f.deleted_at IS NULL) AS righe_fatture, (SELECT count(DISTINCT btrim(f.file_origine)) FROM fatture f WHERE f.ristorante_id=r.id AND f.deleted_at IS NULL AND f.file_origine IS NOT NULL AND btrim(f.file_origine)<>'') AS documenti FROM ristoranti r WHERE r.user_id IN ('51015cc8-...','79920814-...') ORDER BY r.user_id, documenti DESC; COMMIT;
```

**Risultato.** A: 5 PV attivi, nessuna sede_tecnica: fd7ac484 1082 doc, cc016821 581, 5444e918 467, 0dca4d1f 452, 0c23548c 0. C: f16aebe5 110 doc

### Colonne di fatture_documenti e fornitori_pagamenti_config

```sql
BEGIN READ ONLY; SELECT table_name, column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('fatture_documenti','fornitori_pagamenti_config') ORDER BY table_name, ordinal_position; COMMIT;
```

**Risultato.** fatture_documenti: pagata_at timestamptz, scadenza_* date, totale_documento numeric, pagata_manuale_at; fornitori_pagamenti_config senza deleted_at

### Regole fornitore attive dei due account

```sql
BEGIN READ ONLY; SELECT user_id, ristorante_id, piva_fornitore, modalita, giorni_pagamento, data_riferimento, attiva, created_at FROM fornitori_pagamenti_config WHERE user_id IN ('51015cc8-...','79920814-...') ORDER BY user_id, ristorante_id, attiva DESC, created_at DESC; COMMIT;
```

**Risultato.** A: fd7ac484 4 regole (2 rid, 30gg, 60gg), 0dca4d1f 1 regola 60gg; C: 6 regole rid; tutte attive con modalita

### Duplicati (file_origine, ristorante_id) e cancellate in fatture_documenti

```sql
BEGIN READ ONLY; SELECT ristorante_id, count(*) AS n_doc, count(*) FILTER (WHERE dup>1) AS n_dup, count(*) FILTER (WHERE deleted_at IS NOT NULL) AS n_del FROM (SELECT ristorante_id, btrim(file_origine) fo, deleted_at, count(*) OVER (PARTITION BY ristorante_id, btrim(file_origine)) AS dup FROM fatture_documenti WHERE user_id IN (...) AND deleted_at IS NULL) t GROUP BY ristorante_id; COMMIT;
```

**Risultato.** n_dup=0 ovunque; header attivi: 452, 467, 581, 110, 1101 (fd7ac484 ha 19 header piu' dei documenti con righe)

### CTE che ricostruisce get_documenti_scadenziario (RPC + fatture_documenti filter_active + oscurate + regole fornitore + gerarchia scadenza + RID + totale) — usata come prefisso di tutte le query seguenti

```sql
WITH params AS (SELECT :UID::uuid AS uid, :RIDS::uuid[] AS rids, DATE '2026-10-15' AS today), base AS (... corpo RPC ...), prima_riga AS (...), agg AS (...), fd AS (SELECT btrim(file_origine) fo, ristorante_id frid, piva_fornitore, numero_documento, totale_documento tdoc, scadenza_xml, giorni_termini_xml, scadenza_effettiva se_db, scadenza_source ss_db, scadenza_override, pagata pag_db, pagata_at pat_db, pagata_manuale_at FROM fatture_documenti, params p WHERE user_id=p.uid AND ristorante_id=ANY(p.rids) AND deleted_at IS NULL), osc AS (SELECT DISTINCT btrim(file_origine) fo, ristorante_id FROM fatture, params p WHERE user_id=p.uid AND ristorante_id=ANY(p.rids) AND oscurata=true AND deleted_at IS NULL), reg AS (SELECT DISTINCT ON (ristorante_id, btrim(piva_fornitore)) ... FROM fornitori_pagamenti_config ... attiva ... ORDER BY ristorante_id, btrim(piva_fornitore), created_at ASC), d0 AS (SELECT a.*, (fd.fo IS NOT NULL) hdr, ..., CASE override->'override' | no hdr->'none' | rid->'fornitore_rid' | 30/60/90gg(_fm)->'fornitore' | scadenza_xml->'xml' | data+giorni_termini->'xml' | se_db->coalesce(ss_db,'stored') | 'none' END src, CASE ... END scad FROM agg a LEFT JOIN fd ... LEFT JOIN osc ... LEFT JOIN reg ON reg.rrid=a.ristorante_id AND reg.rpiva=btrim(coalesce(fd.piva_fornitore,''))), docs AS (SELECT d0.*, (CASE WHEN src='fornitore_rid' AND pagata_manuale_at IS NULL THEN true ELSE coalesce(pag_db,false) END) pagata, (pat_db AT TIME ZONE 'UTC')::date pagata_at, ROUND(CASE WHEN tdoc IS NOT NULL AND tdoc<>0 THEN tdoc ELSE totale_righe END,2) totale, (upper(btrim(tipo_documento))='TD04') is_nc, p.today FROM d0, params p)
```

**Risultato.** A gruppo 2582 documenti, C 110: stessa popolazione del worker (hdr mancanti 0)

### KPI per vista (gruppo A con ROLLUP per sede; C)

```sql
BEGIN READ ONLY; <CTE> SELECT coalesce(ristorante_id::text,'TUTTE') vista, count(*) n_doc, count(*) FILTER (WHERE oscurata) osc, count(*) FILTER (WHERE NOT oscurata AND is_nc) nc, count(*) FILTER (WHERE NOT oscurata AND NOT is_nc AND pagata) pagate_n, count(*)/sum(totale) FILTER (WHERE ... pagata AND pagata_at>=DATE '2026-10-01') pm, count/sum FILTER (WHERE ... NOT pagata) dp, ... AND scad IS NULL ss, ... AND scad < today sc, ... AND scad BETWEEN today AND today+7 sett, count(DISTINCT file_origine) FILTER (selezionabili) sel_fo_distinct, count(*) FILTER (WHERE src='fornitore_rid') rid_n, count(*) FILTER (WHERE NOT hdr) no_hdr FROM docs GROUP BY ROLLUP(ristorante_id) ORDER BY 1; COMMIT;
```

**Risultato.** A TUTTE: 2582 doc, osc 0, nc 106, pagate 39, pm 0, dp 2437/3.756.242,76, ss 723/810.334,80, sc 1714/2.945.907,96, sett 0, sel_fo_distinct 2437, rid 25. fd7ac484: 1082, nc 51, pagate 36, dp 995/1.712.814,52, ss 366/482.079,52, sc 629/1.230.735,00. cc016821: dp 563/784.224,60. 5444e918: dp 450/632.837,75. 0dca4d1f: dp 429/626.365,89. C: 110, nc 2, pagate 108, pm 19/11.648,49, dp 0, rid 43

### (a) file_origine su piu' sedi di A

```sql
BEGIN READ ONLY; <CTE A> SELECT count(*) fo_multi_sede, sum(n) righe_coinvolte, ... FROM (SELECT file_origine, count(*) n, count(*) FILTER (WHERE NOT oscurata AND NOT is_nc AND NOT pagata) n_sel, ... FROM docs GROUP BY file_origine HAVING count(*)>1) t; COMMIT;
```

**Risultato.** fo_multi_sede 0

### (b)(d)(e) base IVA mista, coerenza pagata/pagata_at, scadenza salvata vs calcolata — A e C

```sql
BEGIN READ ONLY; <CTE> SELECT vista, count FILTER (NOT hdr) no_hdr, count/sum FILTER (hdr AND (tdoc IS NULL OR tdoc=0)) hdr_tdoc_null, count/sum FILTER (fallback AND selezionabile) fallback_in_dapagare, count FILTER (hdr AND tdoc<>0 AND abs(tdoc-totale_righe)>0.01) incoerenti, count FILTER (pag_db AND pat_db IS NULL) pag_senza_at, count FILTER (NOT pag_db AND pat_db IS NOT NULL) at_senza_pag, count/sum FILTER (pagata AND pagata_at IS NULL) pagata_eff_senza_at, count FILTER (src='fornitore_rid' AND NOT pag_db) rid_forzate_pagate, count FILTER (hdr AND se_db IS NULL AND (scadenza_xml IS NOT NULL OR giorni_termini_xml IS NOT NULL)) se_null_con_xml, count FILTER (hdr AND scad IS DISTINCT FROM se_db) scad_diversa_da_db, count FILTER (... AND src NOT IN ('fornitore','fornitore_rid','override')) scad_diversa_non_regola FROM docs GROUP BY ROLLUP(ristorante_id); COMMIT;
```

**Risultato.** A: no_hdr 0, hdr_tdoc_null 2 (0,02 e 0,00 EUR, entrambi in Da pagare), incoerenti 2557/2582, pag_senza_at 0, at_senza_pag 0, pagata_eff_senza_at 25 (99.535,74), rid_forzate 25, se_null_con_xml 0, scad_diversa_da_db 236, scad_diversa_non_regola 0. C: no_hdr 0, tdoc_null 0, incoerenti 105/110, pagata_eff_senza_at 30 (5.695,30), rid_forzate 30, se_null_con_xml 0, scad_diversa 41, non_regola 0

### (c) Archivio «Per mese»: intestazioni con NC e pagate — A e C

```sql
BEGIN READ ONLY; <CTE> SELECT to_char(data_documento,'YYYY-MM') mese, count(*) n, sum(totale) tot_header, count(*) FILTER (WHERE is_nc) nc_n, sum(totale) FILTER (WHERE is_nc) nc_tot_sommato, sum(totale_righe) FILTER (WHERE is_nc) nc_righe_netto, count/sum FILTER (WHERE pagata) pag, count(*) FILTER (WHERE data_documento IS NULL) senza_data FROM docs GROUP BY 1 ORDER BY 1 DESC; COMMIT;
```

**Risultato.** A: 2026-07 316/446.383,49 (13 NC +4.920,76); 06 579/765.726,03 (18 NC +9.371,60); 05 574/886.132,71 (22 NC +6.888,83, righe nette −6.168,88); 04 597/898.281,72 (21 NC +6.262,05); 03 263/405.632,61 (17 NC +5.400,43); 02 129/266.403,73 (10 NC +3.253,85); 01 124/276.153,00 (5 NC +1.356,02); senza_data 0. C: 2026-06 12/6.980,20 (1 NC +468,10, netto −383,69); 2026-08 12/5.932,14 (1 NC +6,00); 2026-10 4/2.890,23

### (c) Oscurate con scadenza nel mese corrente o futura — intero DB (solo user_id)

```sql
BEGIN READ ONLY; SELECT o.user_id, count(*) doc_oscurati, count(*) FILTER (WHERE fd.scadenza_effettiva >= DATE '2026-10-01' AND fd.scadenza_effettiva < DATE '2026-11-01' AND NOT coalesce(fd.pagata,false) AND upper(coalesce(fd.tipo_documento,'TD01'))<>'TD04') osc_scad_ottobre_non_pagate, count(*) FILTER (WHERE fd.scadenza_effettiva >= DATE '2026-11-01' AND ...) osc_scad_futura_non_pagate, sum(fd.totale_documento) FILTER (...) FROM (SELECT DISTINCT user_id, ristorante_id, btrim(file_origine) fo FROM fatture WHERE oscurata=true AND deleted_at IS NULL AND file_origine IS NOT NULL) o LEFT JOIN fatture_documenti fd ON ... AND fd.deleted_at IS NULL GROUP BY o.user_id; COMMIT;
```

**Risultato.** 1 solo documento oscurato in tutto il DB (user 080004f3), 0 con scadenza in ottobre o futura

### Export compatto dei documenti ricostruiti (foi,sede,is_nc,totale,scad,pagata,pagata_at,data_documento) per eseguire la lib con node — A per sede (3 chiamate) e C

```sql
BEGIN READ ONLY; <CTE>, idx AS (SELECT docs.*, dense_rank() OVER (ORDER BY file_origine) foi, array_position((SELECT rids FROM params), ristorante_id) ri FROM docs) SELECT count(*) n, string_agg(foi||','||ri||','||is_nc::int||','||totale||','||coalesce(scad::text,'')||','||pagata::int||','||coalesce(pagata_at::text,'')||','||coalesce(data_documento::text,''), ';' ORDER BY foi) csv FROM idx WHERE ri=1 | ri=2 | ri IN (3,4,5) | (C: tutte); COMMIT;
```

**Risultato.** 1082 + 581 + 919 = 2582 righe per A, 110 per C; salvate in scratchpad/audit/F1d/*.csv e cancellate a fine lavoro

### RID non pagate a DB, di cui con data documento in ottobre; pagata_at future

```sql
BEGIN READ ONLY; SELECT fd.user_id, count(*) FILTER (WHERE r.modalita='rid' AND fd.pagata_manuale_at IS NULL AND NOT coalesce(fd.pagata,false)) rid_non_pagate_a_db, sum(fd.totale_documento) FILTER (...) rid_non_pagate_tot, count/sum FILTER (... AND fd.data_documento >= DATE '2026-10-01') rid_ottobre, count(*) FILTER (WHERE fd.pagata_at > now()) pagata_at_futura, count(*) FILTER (... AND fd.scadenza_effettiva < DATE '2026-10-15') rid_scadute_a_db FROM fatture_documenti fd LEFT JOIN fornitori_pagamenti_config r ON r.user_id=fd.user_id AND r.ristorante_id=fd.ristorante_id AND r.attiva AND btrim(r.piva_fornitore)=btrim(coalesce(fd.piva_fornitore,'')) WHERE fd.user_id IN (...) AND fd.deleted_at IS NULL GROUP BY fd.user_id; COMMIT;
```

**Risultato.** C: 30 RID non pagate a DB (6.163,40 lordo incl. NC), 3 con data in ottobre (205,89), pagata_at future 0, 10 con scadenza salvata gia' passata. A: 25 (99.565,64), 0 in ottobre, future 0, 12 scadute a DB

### Esecuzione node (non SQL) di lib/scadenziario.ts sui documenti reali: computeKpi, contaDaPagare, chiaviSelezionaTutte, bucketizeDocumenti, raggruppaPerMeseFattura, scaduteFuoriDalMese, aggregaPerSede (periodo tutti e scadute), filtraDocumenti+computeKpi (scadute/settimana/mese) — TZ Europe/Rome, oggi 2026-10-15

```sql
node --experimental-strip-types runner.mjs in_<vista>.json (registerHooks per l'alias @/, fetch stubbato; input letto da file perche' 2582 documenti in argv superano ARG_MAX e esegui_ts fallisce con 'Argument list too long')
```

**Risultato.** A gruppo: kpi {scadute 1714/2.945.907,96; settimana 0; da_pagare 2437/3.756.242,76; pagate_mese 0; senza_scadenza 723/810.334,80}, contaDaPagare 2437, chiavi 2437 (distinte 2437), bucket pagate 39/151.016,99, noteCredito 106/37.453,54, mesi identici al SQL, scaduteFuoriDalMese(ott) 1714, perSede 995/563/450/429 e scadute 629/438/332/315. A sede fd7ac484: 629/1.230.735,00, 995/1.712.814,52, 366/482.079,52, pagate 36/147.160,42, NC 51/20.504,47. C: da_pagare 0, pagate_mese 19/11.648,49, pagate 108/53.238,13, NC 2/474,10

## F2a sotto-utenti backend+SQL

### Funzioni public con p_user_id/p_ristorante_ids, gruppo_*, chat_crediti_*: nome, SECURITY, firma

```sql
BEGIN READ ONLY; SELECT p.proname, p.prosecdef, pg_get_function_identity_arguments(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND (pg_get_function_identity_arguments(p.oid) ILIKE '%p_user_id%' OR pg_get_function_identity_arguments(p.oid) ILIKE '%p_ristorante_ids%' OR p.proname LIKE 'gruppo_%' OR p.proname LIKE 'chat_crediti%') ORDER BY p.proname; COMMIT;
```

**Risultato.** 31 funzioni; 27 SECURITY DEFINER, 4 invoker (articoli_da_fatture, chat_top_categoria_fornitore, costi_automatici_mensili, costi_automatici_mensili_gruppo)

### Corpo di chat_crediti_check_and_log e chat_crediti_stato

```sql
BEGIN READ ONLY; SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('chat_crediti_check_and_log','chat_crediti_stato') ORDER BY p.proname; COMMIT;
```

**Risultato.** check_and_log: lock su p_user_id, stato via chat_crediti_stato, INSERT chat_usage_log(user_id, ristorante_id, crediti, da_ricarica); stato: pool -> user_id = p_user_id, non pool -> ristorante_id = p_ristorante_id

### Per ogni funzione: SECURITY, ACL, filtra p_user_id / ANY(p_ristorante_ids) / deleted_at, scrive

```sql
BEGIN READ ONLY; SELECT p.proname, p.prosecdef, p.proacl::text, (pg_get_functiondef(p.oid) ~* 'user_id\s*=\s*p_user_id'), (pg_get_functiondef(p.oid) ~* 'ANY\s*\(\s*p_ristorante_ids\s*\)'), (pg_get_functiondef(p.oid) ~* 'ristorante_id\s*=\s*p_ristorante_id\b'), (pg_get_functiondef(p.oid) ~* 'deleted_at'), (pg_get_functiondef(p.oid) ~* '\m(insert|update|delete)\M\s+(into|public\.|[a-z_]+\s+set|from)'), length(pg_get_functiondef(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND (...stesso filtro...) ORDER BY p.proname; COMMIT;
```

**Risultato.** ACL = {postgres=X,service_role=X} per tutte le 31; 10 gruppo_* filtrano ANY(p_ristorante_ids) e deleted_at senza user_id; 15 filtrano user_id = p_user_id; 5 senza filtro sono scritture/admin

### Corpo delle 5 funzioni senza filtro user_id

```sql
BEGIN READ ONLY; SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname IN ('crea_riparto_con_quote','admin_conteggio_fatture','admin_ultimo_caricamento','track_ai_usage_event','accoda_upload_ambiguo') ORDER BY p.proname; COMMIT;
```

**Risultato.** accoda_upload_ambiguo e crea_riparto_con_quote inseriscono con p_user_id; admin_* filtrano = any(p_user_ids)/unnest(p_ristorante_ids); track_ai_usage_event ha guardia auth.role() <> service_role

### Policy su sotto_utenti, sotto_utenti_sedi, sessioni, chat_usage_log, chat_crediti_ricariche

```sql
BEGIN READ ONLY; SELECT tablename, policyname, roles, cmd, qual, with_check FROM pg_policies WHERE schemaname='public' AND tablename IN ('sotto_utenti','sotto_utenti_sedi','sessioni','chat_usage_log','chat_crediti_ricariche') ORDER BY tablename, policyname; COMMIT;
```

**Risultato.** 0 righe: nessuna policy (RLS attiva senza policy = negato a tutti tranne service_role)

### Grant di tabella ad anon/authenticated/service_role

```sql
BEGIN READ ONLY; SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name IN ('sotto_utenti','sotto_utenti_sedi','sessioni','users','chat_usage_log') GROUP BY table_name, grantee ORDER BY table_name, grantee; COMMIT;
```

**Risultato.** sotto_utenti, sotto_utenti_sedi, sessioni, chat_usage_log: solo postgres e service_role; users: anche authenticated (con policy id = auth.uid(), sempre NULL)

### Trigger non interni e stato RLS su sotto_utenti, sotto_utenti_sedi, sessioni, users

```sql
BEGIN READ ONLY; SELECT c.relname, t.tgname, t.tgenabled, p.proname, c.relrowsecurity, c.relforcerowsecurity FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_proc p ON p.oid=t.tgfoid WHERE NOT t.tgisinternal AND c.relname IN ('sotto_utenti','sotto_utenti_sedi','sessioni','users') ORDER BY c.relname, t.tgname; COMMIT;
```

**Risultato.** 5 trigger, tutti 'O' (attivi): sessioni_sotto_utente_del_titolare, sotto_utenti_email_unica, sotto_utenti_titolare_immutabile, sotto_utenti_sedi_guardia, users_email_non_di_un_sotto_utente; RLS true su tutte (forced su sessioni e users)

### Conteggio sotto-utenti in produzione e colonne di chat_usage_log

```sql
BEGIN READ ONLY; SELECT (SELECT count(*) FROM sotto_utenti), (SELECT count(*) FROM sotto_utenti_sedi), (SELECT count(*) FROM sessioni WHERE sotto_utente_id IS NOT NULL), (SELECT string_agg(column_name, ',' ORDER BY ordinal_position) FROM information_schema.columns WHERE table_schema='public' AND table_name='chat_usage_log'); COMMIT;
```

**Risultato.** 0, 0, 0; colonne: id,user_id,ristorante_id,created_at,crediti,da_ricarica

### Grant di esecuzione ad anon/authenticated/PUBLIC sulle funzioni interessate

```sql
BEGIN READ ONLY; SELECT routine_name, grantee, privilege_type FROM information_schema.routine_privileges WHERE routine_schema='public' AND grantee IN ('anon','authenticated','PUBLIC') AND (routine_name LIKE 'gruppo_%' OR routine_name LIKE 'chat_crediti%' OR routine_name LIKE 'sotto_utenti%' OR routine_name LIKE 'sessioni_%' OR routine_name LIKE 'users_email%' OR routine_name IN (...20 nomi...)) ORDER BY routine_name, grantee; COMMIT;
```

**Risultato.** 0 righe

### Policy su users, ristoranti, notifiche, chat_crediti_ricariche

```sql
BEGIN READ ONLY; SELECT tablename, policyname, roles::text, cmd, qual FROM pg_policies WHERE schemaname='public' AND tablename IN ('users','ristoranti','notifiche','chat_crediti_ricariche') ORDER BY tablename, policyname; COMMIT;
```

**Risultato.** users: 4 policy authenticated con id = auth.uid(); ristoranti: service_role ALL true + authenticated user_id = auth.uid()

### Tipo delle colonne di notification_inbox (id uuid?)

```sql
BEGIN READ ONLY; SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='notification_inbox' ORDER BY ordinal_position; COMMIT;
```

**Risultato.** id uuid; user_id, ristorante_id uuid; action_page text; dismissed_at timestamptz
