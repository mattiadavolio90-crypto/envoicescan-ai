# Audit di correttezza ottobre 2026 — i finding completi della fase Trova

Testo integrale restituito dai nove finder il 15/10/2026, prima della verifica. I nomi dei clienti sono sostituiti da «[cliente]». Le classificazioni e le gravità qui sono quelle **del finder**: quelle valide sono nel report, dopo la verifica.

## F1c quadrature sedi singole C+D

### F1c-01 — Home di D mostra «Luglio» (0 € di incasso, 89 € di sole spese) come ultima fotografia: MOL −89 € rosso, «vs giugno», freccia verde −97,9% sulle spese, sparkline MOL −100% — senza alcun avviso

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Home desktop (card «I tuoi conti», kpi-block.tsx) e /m/briefing (stesso fetchKpi+KpiBlock) dell'account D = user 802967b0 / sede 86300227. C non e' toccato (settembre ha incasso).

**prova.** Oggi 15/10/2026: home_kpi parte da settembre (nessuna riga margini_mensili, costi 0 → has_data False), agosto idem, luglio: margini_mensili assente, RPC costi 2026-07 = fb 0,00 / spese 89,08 (13 righe, query ricalcolo) → has_data = (lordo>0 or fb>0 or spese>0 or personale>0) = True → mese mostrato «Luglio». _kpi_periodo(7): fatturato 0, netto 0, food_cost None, personale 0, spese 89,08, mol −89,08, costi_mancanti = (0>0 and ...) = False. Confronto: giugno has_data (override 80.655 → netto 73.322,73; fb 13.058,88; spese 4.180,61; pers 20.080; MOL 36.003,24) → confronto_label «vs giugno»; spese_delta = (89,08−4.180,61)/4.180,61 = −97,9% → kpi-block Trend buonoSeSu=false, delta giu' → tinta VERDE (sopprimi solo se spese===0); mol_delta = −100,2% (grigio perche' MOL<0); fatturato/personale soppressi (==0). incasso_fuori_norma(luglio): netto 0 → None → nessun avviso; confronto_escluso: giugno 73.322,73 vs mediana 73.896,91 → non fuori norma → il confronto resta. tintContiPV: costi_mancanti False, fuori_norma non true, mol<0 → ROSSO. Sparkline mol_mensile gen→lug: 31.296,09 / 16.505,43 / 28.438,79 / 37.347,38 / 38.947,67 / 36.003,24 / −89,08 → calcolaSparkline ytdPct = (−89,08−31.296,09)/31.296,09 = −100,3%, linea rossa: esattamente il «falso crollo» che il commento a worker:10024 dice di voler evitare. Il briefing si protegge da questo caso (_mesi_confrontabili, worker:6777: fatturato<=0 → False), la Home e la chat no.

**numeri attesi vs mostrati.** Mostrato: «Luglio» MOL −89 €, Spese generali 89 € con ↓97,9% verde, sparkline −100,3%. Atteso: «Giugno» MOL 36.003 € (o luglio dichiarato senza incasso, senza frecce).

**fix proposto.** In home_kpi (e in _chat_query_margini, stesso loop) la scelta del mese da mostrare deve richiedere un mese con incasso o con merce (fatturato>0 or fb>0), non «qualsiasi componente >0»; in alternativa esporre `incasso_mancante` quando fatturato==0 e, come per costi_mancanti, azzerare i delta, escludere il punto dalla sparkline e mostrare l'avviso «manca l'incasso di luglio».

**presidio proposto.** Test pytest su home_kpi (stile test_home_kpi_sparkline) con oggi=15/10, giugno pieno e luglio con sole spese 89 €: atteso periodo_label «Giugno» (o costi/incasso mancanti dichiarati), spese_delta_pct None e mol_mensile senza il punto di luglio; mutante: rimettere `or spese > 0` in has_data deve far fallire il test.

**gia presidiato da.** Nessuno sulla Home. tests/test_briefing_onesta_fatturato_zero.py copre solo il briefing (_mesi_confrontabili); tests/test_home_kpi_sparkline.py usa mesi con fatturato>0 e non prova il mese di sole spese.

**file e righe.** `services/fastapi_worker.py:9866-9867 (has_data include un mese di sole spese)`; `services/fastapi_worker.py:9929-9940 (loop che sceglie il mese)`; `services/fastapi_worker.py:9990-10021 (confronto e fuori norma: netto 0 → None)`; `services/fastapi_worker.py:10024-10033 (sparkline)`; `apps/web/src/app/(app)/dashboard/kpi-block.tsx:138-157 (Trend spese: sopprimi solo se ===0)`; `apps/web/src/lib/catena-confronti.ts:319-336 (ytdPct)`

### F1c-02 — Chat query_margini per D include «luglio 2026: fatturato 0, mol −89,08» senza flag; costi_mancanti mai esposto

Filone 1 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Chat (tool query_margini) dell'account D (user 802967b0). Per C nessun effetto oggi (nessun mese con costi_mancanti, nessun mese a incasso 0 fra gli ultimi 6).

**prova.** Lettura worker:5324-5341 + dati: il loop fa 6 iterazioni da ottobre 2026 all'indietro (ott, set, ago: has_data False; lug: has_data True per 89,08 € di spese; giu, mag) → risultati = [luglio {fatturato 0, food_cost_pct None, mol −89,08, parziale False}, giugno {80.655 / 17,8 / 36.003,24}, maggio {88.606 / 19,3 / 38.947,67}]. Il dict non porta ne' costi_mancanti ne' un flag «senza incasso»: solo «parziale» (vero solo per il mese corrente). Per C costi_mancanti e' False su tutti i mesi (fb>0 ovunque), quindi l'omissione del flag non cambia nulla oggi su questi due account.

**numeri attesi vs mostrati.** Chat riceve «luglio 2026: fatturato 0 €, MOL −89 €» come mese chiuso normale.

**fix proposto.** Stesso criterio di F1c-01 (saltare o marcare i mesi con fatturato 0) e aggiungere `costi_mancanti: k["costi_mancanti"]` al dict del mese, cosi' chat, Home e briefing leggono lo stesso segnale.

**presidio proposto.** Test su _chat_query_margini con margini mockati (come tests/test_fase_e_incasso_fuori_norma.py::test_query_margini_*): un mese a fatturato 0 e sole spese non entra in `mesi` o porta `senza_incasso: True`; un mese con ricavi e fb 0 porta `costi_mancanti: True`.

**gia presidiato da.** tests/test_audit_bug_passata2.py:157 verifica solo che la stringa "parziale" stia nel sorgente (getsource, non un presidio sul comportamento). Niente sul mese a incasso 0 o su costi_mancanti.

**file e righe.** `services/fastapi_worker.py:5324-5341`

### F1c-03 — Intestazione «Per mese» dell'archivio scadenziario somma le note di credito col segno positivo e include le pagate: D maggio 25.889,67 € contro 23.114,45 € di acquisti netti

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Gestione Fatture → vista «Per mese» (lista_mensile), intestazione di ogni mese (AgendaSection). C = user 79920814 / sede f16aebe5 e D = user 802967b0 / sede 86300227.

**prova.** raggruppaPerMeseFattura eseguita con node (--experimental-strip-types, TZ Europe/Rome) sui 453 documenti reali (110 C + 343 D, tutti con header fatture_documenti, 0 oscurate) nella forma di get_documenti_scadenziario: totali identici alla ricostruzione SQL (COALESCE(header.totale_documento, SUM(totale_riga))). D: gen 19.778,29 € (39 doc, 1 NC 62,68 sommata positiva; debito aperto 19.715,61; netto NC 19.652,93), feb 42.436,38 (65, 0 NC), mar 28.017,98 (64, 2 NC 46,91 → netto 27.924,16), apr 24.388,39 (64, 4 NC 454,99, 1 pagata 6.270,88 → debito aperto 17.662,52, netto NC 23.478,41), mag 25.889,67 (56, 3 NC 1.387,61, 12 pagate 4.021,68 → debito aperto 20.480,38; acquisti netti NC 23.114,45: scarto +2.775,22 = 2×NC), giu 19.943,38 (54, 2 NC 153,41, 1 pagata 2.133 → debito aperto 17.656,97), lug 108,68 (1). C: mar 10.023,46 (17 doc, tutte pagate via RID), apr 7.127,44 (16), mag 8.017,42 (20), giu 6.980,20 (12, 1 NC 468,10 → netto 6.044,00, scarto +936,20), lug 4.639,00 (13), ago 5.932,14 (12, 1 NC 6,00), set 8.102,34 (16), ott 2.890,23 (4): per C il debito aperto e' 0,00 in OGNI mese (79 header pagata + 43 documenti sotto regola RID senza pagata_manuale_at) mentre l'intestazione mostra la somma piena. totale_documento della NC in fatture_documenti e' positivo (468,10) mentre le righe sono negative (−383,69 netto IVA): sommato come acquisto.

**numeri attesi vs mostrati.** D maggio: mostrato 25.889,67 €; acquisti netti NC 23.114,45 €; debito aperto 20.480,38 €. C giugno: mostrato 6.980,20 €; netto NC 6.044,00 €; debito aperto 0,00 €.

**fix proposto.** In raggruppaPerMeseFattura (e nell'header di AgendaSection) sottrarre i documenti con is_nota_credito invece di sommarli, e dichiarare cosa somma l'intestazione («N documenti · acquisti X € · da pagare Y €») oppure escludere pagate/oscurate come fa computeKpi. La parte «pagate incluse» e' una scelta di etichetta (archivio = tutti i documenti), la NC a segno positivo e' un numero sbagliato.

**presidio proposto.** Estendere tests/test_scadenziario_vista_mensile_frontend.py con un TD04 (is_nota_credito True, totale 100) accanto a un TD01 da 300: atteso totale 200 (oggi 400); mutante: tornare a `s + d.totale_documento` deve farlo fallire.

**gia presidiato da.** tests/test_scadenziario_vista_mensile_frontend.py (solo TD01 positivi: test_nessuna_fattura_si_perde_per_strada fissa 185 = somma piena).

**file e righe.** `apps/web/src/lib/scadenziario.ts:875-876 (totale = somma di tutti i totale_documento)`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:284-285 (AgendaSection: totale = docs.reduce)`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2046-2049 (gruppiMensili da documentiCalendario: nessuna esclusione)`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2515-2535 (ramo lista_mensile)`; `services/documenti_service.py:808-814 (totale = header, lordo IVA)`

### F1c-04 — «Spesa» di Analisi Fatture e costi di Margini divergono per mese (C aprile +2.246,12 € in Margini, maggio −3.020,13 €) perche' una usa data_documento e l'altra data_competenza; sull'anno coincidono

Filone 1 · periodo non dichiarato · gravità bassa · confidenza alta

**chi lo vede.** Analisi Fatture (KPI «Spesa totale», mese specifico) contro Ricavi e Margini (tabella Calcolo, stesso mese) di C = user 79920814. D non ha righe con competenza diversa dal mese documento (0,00 € in ogni mese).

**prova.** SQL per mese: C aprile Analisi (data_documento, NOTE escluse, righe ≠0) 6.064,93 € vs Margini auto (COALESCE(data_competenza,data_documento), fb 5.114,66 + spese 3.196,39) 8.311,05 €; righe datate aprile con competenza in altro mese 774,01 €, righe datate maggio con competenza in altro mese 3.020,13 € → 6.064,93 − 774,01 + 3.020,13 = 8.311,05 ✓; maggio Analisi 6.847,60 vs Margini 3.827,47 (= 6.847,60 − 3.020,13) ✓. Su tutto il 2026 (Analisi 1/1→15/10 su data_documento; Margini gen→ott su competenza) la parte automatica e' identica: C 45.498,98 € = 45.498,98 €; D 136.766,11 € = 136.766,11 € (competenza_altro_anno = 0 per entrambi). Margini aggiunge gli «altri costi» manuali: C 1.600 € (300 €/mese mar-lug + 100 ago) → F&B+Spese = 27.783,43 + 19.315,55 = 47.098,98; D 3.764,95 € → 102.454,12 + 38.076,94 = 140.531,06. Da Classificare: 0,00 € per entrambi in ogni mese (nessun effetto oggi). NC: nettizzate in entrambe (somma di totale_riga negativi).

**numeri attesi vs mostrati.** C aprile: Analisi 6.064,93 € / Margini F&B+Spese 8.611,05 € (8.311,05 auto + 300 manuali); C maggio: 6.847,60 € / 4.127,47 €.

**fix proposto.** Dichiarare il periodo nell'etichetta del KPI di Analisi Fatture («per data fattura») o usare la stessa chiave di mese dei margini; nessun numero da correggere.

**presidio proposto.** Test che, con una riga datata 30/04 e competenza 05, /api/fatture/kpi di aprile la conta e _calcola_costi_auto_per_periodo la mette a maggio, e che l'etichetta del KPI dichiara «data fattura».

**gia presidiato da.** Nessuno fissa i totali di /api/fatture/kpi contro i costi di Margini (confermato: grep su tests/ per get_fatture_kpi / _fetch_fatture_rows con assert sui totali).

**file e righe.** `services/fastapi_worker.py:10583-10587 (_fetch_fatture_rows: filtro su data_documento)`; `services/fastapi_worker.py:10417-10430 (_build_fatture_base_query: nessun filtro Da Classificare)`; `services/routers/fatture.py:393-399 (_calc: somma righe ≠0)`; `services/fastapi_worker.py:10925-10937 (_calcola_costi_auto_per_periodo: competenza con fallback documento, Da Classificare esclusa)`

### Verificato e trovato giusto

- Ricalcolo da DB per mese (regola SQL: deleted_at IS NULL, NOT oscurata, categoria<>'Da Classificare', NOT ripartita_su_gruppo, mese=COALESCE(data_competenza,data_documento), spese = 5 CATEGORIE_SPESE_GENERALI) — C 2026: mar fb 7.812,20/sp 1.972,05; apr 5.114,66/3.196,39; mag 2.064,33/1.763,14; giu 3.869,88/1.241,47; lug 2.145,09/1.705,28; ago 2.914,91/1.993,51; set 2.143,53/5.182,47; ott 1.618,83/761,24. D 2026: gen 12.432,23/4.924,23; feb 26.297,58/10.661,35; mar 20.090,75/4.823,37; apr 13.224,21/6.992,07; mag 14.253,64/5.738,11; giu 13.058,88/4.180,61; lug 0,00/89,08. Nessuna riga con categoria vuota, nessuna 'NOTE E DICITURE' senza emoji, nessuna NOTE con importo, 0 righe da_verificare: la query Python di _calcola_costi_auto_per_* e la RPC costi_automatici_mensili (corpo letto con pg_get_functiondef: sola SELECT) danno lo stesso risultato su questi dati.
- KPI per mese ricalcolati con la formula di _kpi_periodo/get_margini_analisi (override mensile fuso): C mar netto 6.818,18 MOL −9.091,07 fc 114,6%; apr 8.909,09 / −5.004,96 / 57,4%; mag (override 9.328) 8.480,00 / −1.488,47 / 24,3%; giu 6.932,05 / −9.516,30 / 55,8%; lug 8.029,45 / −1.195,40 / 26,7%; ago 4.539,64 / −6.816,70 / 66,4%; set 7.821,36 / −3.975,64 / 27,4%; ott 4.499,27 / +2.119,20 / 36,0% (personale 0). D gen 69.295,76 / 31.296,09 / 18,9%; feb 73.464,36 / 16.505,43 / 35,8%; mar 73.896,91 / 28.438,79 / 27,8%; apr 78.529,91 / 37.347,38 / 17,8%; mag (override 88.606) 80.550,91 / 38.947,67 / 19,3%; giu (override 80.655) 73.322,73 / 36.003,24 / 17,8%; lug 0 / −89,08 / —.
- Totali salvati in margini_mensili NON letti da nessuna superficie: costi_fb_auto/costi_spese_auto/mol/food_cost_perc sono stantii (C mar salvato fb 7.853,10 vs vivo 7.812,20, mol −11.291,07 vs −9.091,07; C mag-ott e D mag-giu salvati a 0 con costi vivi) ma Home (_kpi_periodo), Margini (/analisi e /kpi), chat e briefing ricalcolano MOL e costi dal vivo; carica_margini_anno legge `mol` ma _kpi_periodo non lo usa; margini.py:216 (GET /api/margini, senza chiamanti) usa i costi vivi; mol_perc_medio di margine_service.py:1039 viene dal kpi calcolato, non dalla tabella.
- Home di C oggi: «Settembre» (ultimo mese completo con dati): fatturato 8.603,50 €, food cost 27,4%, personale 4.471 €, spese 5.182,47 €, MOL −3.975,64 € rosso; costi_mancanti False (fb 2.143,53 > 0). Agosto e' fuori norma (netto 4.539,64 < 0,75 × mediana 7.925,40 = 5.944,05 sui 6 mesi vicini) → confronto_escluso = «agosto», nessuna freccia, testo «nessun confronto con agosto: incasso fuori dal solito» (testoConfronto). Presidiato da tests/test_fase_e_incasso_fuori_norma.py (home_kpi_settembre_non_si_confronta_con_agosto_di_ferie).
- Margini anno corrente (1/1→15/10/2026, percentuali = totali/totali netto) — C: lordo 61.631,95, netto 56.029,04, F&B 27.783,43 (49,59%), spese 19.315,55 (34,47%), personale 43.899,40 (78,35%), MOL −34.969,34 (−62,41%); 8 mesi attivi, 0 senza costi → giudizio presente (rosso), card KPI MOL rossa: coerenti. D: lordo 493.966,64, netto 449.060,58, F&B 102.454,12 (22,82%), spese 38.076,94 (8,48%), personale 120.080 (26,74%), MOL 188.449,52 (41,97%); 6 mesi attivi, 0 senza costi → giudizio presente (verde), card KPI MOL verde: coerenti. Il rischio «card verde sopra gauge Nessun giudizio» (kpi-bar.tsx:208 molTone senza controllo costi mancanti) NON si materializza su C e D: nessun mese con ricavi e F&B=0.
- Nessun «MOL al 100%» mostrato per C o D: tutti i mesi con ricavi hanno F&B>0; D ago-ott hanno ricavi 0 (nessuna riga margini_mensili, nessun override, nessun ricavo giornaliero) → nella tabella escono a 0 con pctIncidenza null (netto 0 → «—»); D luglio esce MOL −89,08 colorato per segno (meseSenzaCosti false perche' netto<=0) — coerente con la definizione, e' il caso di F1c-01.
- Ricavi senza IVA e override mensili: C mag override 9.328 € (margini_mensili 0) → Home, Margini (/analisi, /kpi via _load_mensile_overrides) e chat (_merge_override_mensile) usano tutti 9.328 lordo / 8.480,00 netto. D mag override 88.606 vs ricavi_giornalieri 88.606,27 (1 giorno) → vince l'override ovunque (netto 80.550,91; lo 0,24 € di scarto col giornaliero non e' visibile). D giu override 80.655 vs margini_mensili 3.000 iva10 + 500 altri_ricavi_noiva → l'override sostituisce tutte e tre le voci (altri=0) in Home, Margini, chat e fetchNettoMese (/api/ricavi/modalita ritorna la riga mensile → scorporoNetto = 73.322,73): stesso netto su tutte le superfici; i 500 € di altri ricavi del giornaliero non li legge nessuno, per costruzione dell'override.
- Note di credito nei totali di Analisi Fatture e Margini: nettizzate in entrambe (C giu NC −383,69 netto IVA, ago −5,45; D gen −51,38, mar −45,91, apr −404,28, mag −1.156,91, giu −140,36 entrano col segno negativo in Spesa e nei costi auto).
- Briefing per D oggi (15/10): _briefing_mese_chiuso (giorno 15 ≤ 15) guarda settembre: food_cost None → tace; _mesi_confrontabili (fatturato<=0 → False) tace sulla «buona notizia»; _briefing_food_cost_alto non scatta (fb del mese dopo = 0). Per C: settembre fc 27,4% ≤ 33 → _briefing_mese_chiuso dice il mese senza allarme; consolidato (fb ottobre 1.618,83 > 0).
- raggruppaPerMeseFattura eseguita con node sui documenti reali di C e D: conteggi (C 110 = 17+16+20+12+13+12+16+4; D 343 = 39+65+64+64+56+54+1) e totali identici alla ricostruzione SQL per ogni mese; nessun documento senza header e nessuna oscurata su C e D (i rami «fallback somma righe» e «oscurate» non sono esercitati da questi account).
- Analisi Fatture: righe «Da Classificare» = 0,00 € in ogni mese per C e D (il catch-all F&B non sposta nulla oggi); nessuna riga ripartita_su_gruppo (sedi singole).

### Non verificabile in sola lettura

- Rendering effettivo delle pagine (cache KPI Home 2', cache _fetch_fatture_rows 90'): non ho chiamato il worker ne' Next; i valori «mostrati» sono ricostruiti eseguendo la stessa formula sui dati estratti via SQL e le funzioni lib con node.
- Risposta della chat/briefing in produzione: non chiamati; la lettura e' codice + dati (loop di _chat_query_margini riprodotto a mano).
- Card «Salute» della Home per C e D: non quantificata (fuori dal perimetro F1c; le voci fatturato/personale di settembre per D risultano mancanti per costruzione).
- Il ramo «oscurate» e «documento senza header» dello scadenziario non e' provabile su C e D (0 oscurate, 0 senza header): verificato solo che la funzione non le esclude (scadenziario.ts:846-876).

## F4 gestione fatture azioni e contatori

### F4-01 — In catena una spunta su un file_origine agisce su tutte le sedi che lo hanno, anche quelle nascoste o già pagate (con Seleziona tutte + Segna non pagate si toglie il pagamento a una fattura mai selezionata)

Filone 4 · bug vero · gravità alta · confidenza alta

**chi lo vede.** Gestione Fatture vista di gruppo /catena/fatture, scheda Scadenzario. Non succede in vista sede (/scadenziario mono-sede: lì un file_origine compare una volta sola). Mobile: nessuna pagina scadenziario sotto (mobile)/m. Quali account siano toccati non è misurato: il compito escludeva il DB.

**prova.** Eseguito con node lib/scadenziario.ts su un dataset sintetico in cui DUP2.xml è aperta su rA e su rB e DUP.xml è aperta su rA e pagata su rB. (a) Una spunta sulla riga di rA, cioè selezione {DUP2.xml}: pianoAzioneDiMassa → gruppi [{rA:[DUP2.xml]},{rB:[DUP2.xml]}], cambiano 2. La barra dice «1 selezionata», la conferma «2 fatture per 100 €». Con il filtro punto vendita = rA la riga di rB non è visibile (visibiliConFiltroA=[rA]) ma viene scritta lo stesso, perché il piano gira su `documenti` e non sui filtrati (client :1731-1738, voluto dal test :314). (b) Con Seleziona tutte su [X1@rA aperta, DUP@rA aperta, DUP@rB pagata], motivoAzioneSpenta(pianoNonPagate) restituisce null, quindi «Segna non pagate» è ACCESO. Invia {rB:[DUP.xml]} e la conferma dice «1 fattura per 120 € tornerà fra quelle da pagare, e la data di pagamento verrà rimossa». Sullo stesso dataset in mono-sede il pulsante è spento e i gruppi sono []. Lato server segna_fattura_pagata scrive pagata=false, pagata_at=null e pagata_manuale_at (documenti_service.py:557-570), e pagata_manuale_at spegne l'automatismo RID su quella fattura. (c) statoSelezioneSezione(Scadute, ['DUP2.xml']) dà selezionati=2: un clic spunta due righe.

**fix proposto.** La chiave di selezione diventa `${ristorante_id ?? ''}|${file_origine}`, la stessa di applicaPagataAVideo: in selectedFileOrigini, chiaviSelezionaTutte, statoSelezioneSezione, toggleSelect/toggleAll e nel `set.has` di pianoAzioneDiMassa (che poi invia solo file_origine per gruppo).

**presidio proposto.** Test node in test_scadenziario_azione_di_massa_frontend.py. (1) Stesso file_origine su due sedi entrambe aperte: selezionare la riga di r1 produce gruppi solo per r1. (2) Seleziona tutte con un omonimo pagato su r2: motivoAzioneSpenta(pianoNonPagate) non è null e i gruppi sono []. Da provare per mutazione riportando la chiave al solo file_origine.

**gia presidiato da.** Nessuno. test_a_video_in_catena_la_chiave_include_la_sede (:200) copre solo l'aggiornamento a video; test_in_catena_raggruppa_per_sede (:145) usa file_origine tutti distinti.

**file e righe.** `apps/web/src/lib/scadenziario.ts:158-160`; `apps/web/src/lib/scadenziario.ts:189-201`; `apps/web/src/lib/scadenziario.ts:225-250`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1642`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1731-1738`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1798-1823`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:319-324`; `services/documenti_service.py:557-570`

### F4-02 — «Seleziona tutte (N)», la barra «N selezionate» e la conferma danno tre numeri diversi per la stessa selezione in catena

Filone 4 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** /catena/fatture, scheda Scadenzario, quando lo stesso file_origine è su più sedi. In vista sede i tre numeri coincidono (sedeA: N=6, Set=6).

**prova.** Eseguito su un dataset di gruppo di 16 documenti con DUP2.xml aperta su due sedi e DUP.xml aperta su rA e pagata su rB. Il bottone vale chiaviSelezionaTutte(D).length = 9, perché `.map(d => d.file_origine)` non deduplica. Dopo il clic la barra mostra new Set(chiavi).size = 8 («8 selezionate»). La conferma dice «9 fatture per 3320 €… 1 selezionata è già pagata: resta com'è», anche se Seleziona tutte prende solo fatture da pagare: la «già pagata» è DUP.xml@rB, catturata dalla chiave.

**fix proposto.** Si risolve insieme a F4-01: con la chiave sede|file_origine bottone, barra e conferma contano la stessa popolazione.

**presidio proposto.** Test node: su un dataset con un omonimo su due sedi, chiaviSelezionaTutte(D).length == new Set(chiavi).size == pianoAzioneDiMassa(D, set, true).cambiano.length e giaCosi == 0.

**gia presidiato da.** Nessuno: test_scadenziario_contatore_frontend.py e test_scadenziario_azione_di_massa_frontend.py non usano file_origine duplicati.

**file e righe.** `apps/web/src/lib/scadenziario.ts:158-160`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2042`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2461-2464`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2566-2569`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2615-2620`

### F4-03 — In catena «Elimina fattura» e «Modifica data» aggiornano a video tutte le sedi con quel file_origine, mentre il server ne tocca una sola

Filone 4 · bug vero · gravità media · confidenza alta

**chi lo vede.** /catena/fatture (Scadenzario, Calendario, Archivio) fino al primo «Aggiorna» o ricaricamento. In vista sede l'effetto non c'è.

**prova.** Ho replicato le due righe del client sul dataset di gruppo. handleElimina su DUP2.xml@rA (:1907 `prev.filter(d => d.file_origine !== doc.file_origine)`) lascia a video 0 righe DUP2 invece di 1: sparisce anche quella di rB, che a DB resta attiva, perché il server cestina solo rA (cestino.py elimina_fattura_soft filtra user_id+file_origine+ristorante_id). handleSetScadenza a 2026-12-31 su DUP2@rA (:1882-1891) cambia la scadenza su rA e su rB. La card Scadute passa da 1600 a 1500 €, mentre il valore coerente col DB (solo rA spostata) è 1550 €. Il codice ammette il difetto nel commento di handleOscura (:1927-1931). handleSpostata (:1939-1941) ha la stessa chiave ma in catena non si raggiunge: PeekDialog non carica le sedi se modalitaCatena (:713-714), quindi «Sposta» non compare.

**fix proposto.** Usare lo stesso match di handleOscura in handleElimina e handleSetScadenza: d.file_origine === doc.file_origine && d.ristorante_id === doc.ristorante_id. In handleSpostata per coerenza.

**presidio proposto.** Estrarre in lib una funzione «togliAVideo(documenti, doc)» / «applicaScadenzaAVideo» con chiave sede|file_origine, con test node su due sedi omonime, e una guardia che il .tsx la usi.

**gia presidiato da.** Nessuno: test_scadenziario_oscurate_frontend.py copre la sola chiave di handleOscura in modo indiretto; nessun test su handleElimina e handleSetScadenza.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1882-1891`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1907`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1927-1936`; `services/routers/cestino.py:229-238`

### F4-04 — Il Calendario mostra come da pagare le fatture «Escluse da te» (oscurate)

Filone 4 · bug vero · gravità media · confidenza alta

**chi lo vede.** /scadenziario e /catena/fatture, scheda Calendario: celle dei giorni e lista del giorno.

**prova.** Ho replicato la regola di CalendarView (:497-506: salta solo pagata e is_nota_credito). Gruppo, ottobre 2026: il giorno 20 vale 350 € «1 fatt.» ed è OSCFUT@rB, oscurata. Settembre 2026: il giorno 1 vale 250 € ed è OSCSCAD@rA, oscurata. Nello stesso momento computeKpi, bucketizeDocumenti (sezione «Escluse da te») e scaduteFuoriDalMese (fuoriSet=3/600, senza OSCSCAD) le escludono. Anche l'endpoint server /api/scadenziario/calendario le esclude (routers/scadenziario.py:149-153, «Esclusa dai conti = esclusa anche dalle scadenze»). Stesso difetto in dayDocs (:530-535).

**fix proposto.** Aggiungere `if (doc.oscurata) continue;` in agg e in dayDocs. Meglio ancora: estrarre in lib una funzione «documentiDelCalendario» che riusa statoDocumento ed escluda ciò che non è Scaduta o Da pagare.

**presidio proposto.** Estrarre l'aggregazione del calendario in lib/scadenziario.ts con test node: un'oscurata con scadenza nel mese non entra in nessuna cella. Va provato per mutazione togliendo la riga.

**gia presidiato da.** Nessuno: test_scadenziario_calendario_fuori_mese_frontend.py:102 copre l'esclusione solo per scaduteFuoriDalMese, non per le celle.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:495-509`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:528-536`; `services/routers/scadenziario.py:144-153`

### F4-05 — La card «Pagate (mese)» si azzera con qualsiasi filtro di periodo ma non dice «(filtro)», a differenza delle altre tre

Filone 4 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** /scadenziario e /catena/fatture, viste Scadenzario e Calendario (le card sono nascoste solo in Archivio).

**prova.** Gruppo senza filtri: computeKpi dà pagate_mese 2 / 720 €. Con un clic su Scadute (periodo='scadute') computeKpi(filtraDocumenti) dà pagate_mese 0 / 0 €, perché matchDocumento scarta ogni pagata quando periodo≠'tutti' (lib :692-693). Le altre tre card cambiano etichetta in «Scadute (filtro)», «Settimana (filtro)», «Da pagare (filtro)» (:2070, :2076, :2087). Pagate resta «Pagate (mese)» (:2095) e il cliente legge «0 € pagati questo mese». Con un filtro fornitore (Forn SCAD1) vale 0 anche lì, sempre senza etichetta.

**fix proposto.** Due opzioni. (1) Etichetta «Pagate (mese, filtro)» quando filtriAttivi. (2) Calcolare Pagate (mese) sui documenti filtrati senza il periodo, che per definizione esclude le pagate, così il consuntivo non dipende dal chip di scadenza.

**presidio proposto.** Test node: computeKpi(filtraDocumenti(D,{periodo:'scadute'})).pagate_mese_count == 0, e una guardia sul .tsx che l'etichetta di Pagate dipenda da filtriAttivi (oppure il test sulla funzione scelta).

**gia presidiato da.** Nessuno: i test KPI (test_scadenziario_kpi_frontend.py) lavorano su liste non filtrate.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2068-2095`; `apps/web/src/lib/scadenziario.ts:339-351`; `apps/web/src/lib/scadenziario.ts:692-694`

### F4-06 — In vista Calendario le card e i chip di periodo restano visibili e filtrano, ma il calendario li ignora

Filone 4 · periodo non dichiarato · gravità bassa · confidenza alta

**chi lo vede.** /scadenziario e /catena/fatture, scheda Calendario.

**prova.** documentiCalendario (:1775-1783) passa periodo:'tutti' e non applica dataDa/dataA. I chip Settimana, Mese e date personalizzate sono nascosti solo in lista_mensile (:2349), e le card solo in lista_mensile (:2068). Esecuzione: dopo il clic su Scadute le card mostrano 4 / 1600 € (documentiFiltrati=6), mentre il calendario resta costruito su 16 documenti e mostra ancora il 18/10 (300 €, settimana) e il 25/10 (120 €). Il commento :1773-1774 dichiara che «i chip periodo sono specifici dell'agenda», ma a video restano accesi nel Calendario.

**fix proposto.** Nascondere i chip di periodo (Tutti/Solo scadute compresi) e rendere non cliccabili le card in vista calendario, oppure applicare il periodo anche al calendario.

**presidio proposto.** Guardia sul .tsx: i chip di periodo sono condizionati a view === 'agenda'.

**gia presidiato da.** Nessuno.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1773-1783`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2068`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2335-2368`

### F4-07 — Archivio fatture: il chip «Solo scadute» resta visibile e attivabile ma non cambia l'elenco; checkbox di riga inerti e barra di azioni di massa visibile

Filone 4 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** /scadenziario e /catena/fatture, scheda Archivio fatture, che è la vista di apertura dal 09/10.

**prova.** gruppiMensili nasce da documentiCalendario, che ignora il periodo (:2046-2049). Esecuzione: con periodo='scadute' raggruppaPerMeseFattura(documentiCalendario) dà sempre 3/10/3 documenti, cioè tutti e 16. Il blocco Tutti/Solo scadute (:2335-2344) non è nascosto in lista_mensile, a differenza di Settimana e Mese (:2349, il cui commento dice proprio «un chip che si accende e non cambia l'elenco è peggio di un chip assente»). Il chip attivo fa anche comparire «Pulisci filtri». DocumentoRow disegna sempre la checkbox (:187-193), ma in Archivio onToggleSelect è `() => {}` (:2530), quindi il clic non fa niente. La barra «N selezionate / Segna pagate» (:2566) non ha guardia di vista e resta a video con una selezione fatta nello Scadenzario.

**fix proposto.** Nascondere il gruppo Tutti/Solo scadute in lista_mensile, oppure azzerare il periodo entrando in Archivio. Non disegnare la checkbox quando mostraScadenze=false. Mostrare la barra di massa solo con view==='agenda'.

**presidio proposto.** Guardia sul sorgente del ramo lista_mensile, da provare per mutazione.

**gia presidiato da.** Parziale: test_scadenziario_vista_mensile_frontend.py:138-167 presidia solo il messaggio di elenco vuoto con «Solo scadute» attivo, non l'inerzia del chip.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2335-2349`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2046-2049`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2529-2531`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:187-193`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2566`

### F4-08 — Archivio fatture: il totale del mese somma le note di credito come importi positivi (e include le escluse dai conti), e la riga NC non ha badge

Filone 4 · bug vero · gravità media · confidenza media

**chi lo vede.** /scadenziario e /catena/fatture, scheda Archivio fatture (intestazione di ogni mese e righe).

**prova.** AgendaSection somma docs.reduce(totale_documento) senza guardare il tipo (:285). Esecuzione con una NC da 150 € (sede A, settembre): il mese 2026-09 vale 1220 €, cioè 300+600+150(NC)+120+50, con la NC aggiunta e non sottratta. Agosto vale 1250 €, cioè 1000 + 250 di fattura oscurata. Per il segno reale: get_documenti_scadenziario preferisce fatture_documenti.totale_documento (:788-791), che arriva da ImportoTotaleDocumento dell'XML senza inversione (invoice_service.py:872-878), mentre il segno sta in una colonna separata, segno_compensazione=-1 per TD04 (documenti_service.py:159). La sezione Note di credito dello Scadenzario infatti usa Math.abs. In Archivio DocumentoRow non mostra il badge «nota di credito»: c'è solo quello «esclusa da te» (:201-205).

**fix proposto.** Nel totale del mese sottrarre le NC (o sommarle a parte) ed escludere oppure dichiarare le oscurate. In DocumentoRow mostrare il badge NC e l'importo col segno.

**presidio proposto.** Test node su raggruppaPerMeseFattura: con una NC da 150 € il totale del mese scende di 150, non sale.

**gia presidiato da.** Nessuno: test_scadenziario_vista_mensile_frontend.py:91 verifica che nessuna fattura si perda, non il segno.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:284-285`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:201-205`; `apps/web/src/lib/scadenziario.ts:875`; `services/documenti_service.py:788-791`; `services/documenti_service.py:159`

### F4-09 — In catena l'«Anteprima fattura» del dettaglio legge la sede di sessione: per le fatture delle altre sedi esce vuota o con le righe sbagliate

Filone 4 · bug vero · gravità media · confidenza alta

**chi lo vede.** /catena/fatture: dettaglio di qualsiasi fattura con ristorante_id diverso dalla sede attiva del login, sede tecnica compresa.

**prova.** PeekDialog chiama `/api/scadenziario/anteprima?file_origine=…` senza ristorante_id (:784). Il proxy route.ts inoltra il solo file_origine e il worker get_anteprima_fattura usa _resolve_ristorante_id(user) (routers/scadenziario.py:243-246), poi filtra .eq('ristorante_id', sede di sessione). Una fattura di un'altra sede dà quindi 0 righe, e il dialog scrive «Nessuna riga trovata.» (:904-905). Con un omonimo sulla sede attiva mostra le righe e il totale di quell'altro documento. Esiste già l'endpoint giusto, /api/gruppo/prezzi/fattura?ristorante_id=&file_origine=, usato da components/fatture/anteprima-fattura-dialog.tsx:61-64.

**fix proposto.** In PeekDialog, quando doc.ristorante_id è presente, usare /api/gruppo/prezzi/fattura con ristorante_id, come anteprima-fattura-dialog.tsx; oppure riusare quel componente.

**presidio proposto.** Guardia sul .tsx: la fetch dell'anteprima porta ristorante_id quando il documento ce l'ha, sul modello di test_anteprima_fattura_frontend.py.

**gia presidiato da.** Nessuno per lo scadenziario: test_anteprima_fattura_frontend.py copre Analisi Fatture → Articoli.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:777-788`; `apps/web/src/app/api/scadenziario/anteprima/route.ts:7-12`; `services/routers/scadenziario.py:239-260`

### F4-10 — Esito parziale dell'azione di massa: il toast dice «Errore nel salvataggio» anche quando parte delle fatture è stata scritta

Filone 4 · bug vero · gravità bassa · confidenza media

**chi lo vede.** /scadenziario e /catena/fatture, barra «Segna pagate» / «Segna non pagate».

**prova.** Codice. handleBulkPaga continua sui gruppi successivi dopo un ok:false (:1858 `continue`), scarta `aggiornate` e mostra solo toast.error + loadData (:1862). Il server scrive ogni file_origine singolarmente e restituisce ok=false se anche uno solo fallisce (routers/scadenziario.py:186-203). Dopo il reload il cliente si ritrova pagate le fatture riuscite sotto un messaggio di errore generico. Un fallimento deterministico c'è: un documento senza riga in fatture_documenti compare in lista (get_documenti_scadenziario parte da `fatture`, :640-641) ma segna_fattura_pagata dà «Fattura non trovata» (:609-613). Se un Seleziona tutte lo include, ogni Segna pagate termina in errore pur scrivendo le altre. Quanti siano oggi questi documenti non è misurato.

**fix proposto.** Sommare aggiornate anche sui gruppi falliti, leggere `dettaglio` e mostrare «N segnate, M non riuscite» con i nomi dei falliti. Valutare se rendere selezionabili i documenti senza header.

**presidio proposto.** Estrarre in lib una funzione che compone l'esito dai responsi per gruppo, con test node sul caso misto ok/ko.

**gia presidiato da.** Nessuno: test_il_toast_dopo_l_azione_di_massa (:397) copre solo il caso tutto-ok.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1843-1872`; `services/routers/scadenziario.py:179-203`; `services/documenti_service.py:609-613`

### F4-11 — Vista gruppo: «Svuota questa sede» non dice quale sede, compare anche quando quella sede non ha nulla nel cestino e risponde «Cestino svuotato»

Filone 4 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** /catena/fatture, pannello Cestino.

**prova.** Codice. Il cestino di gruppo elenca le fatture di tutte le sedi (gruppo.py:1950-1953). Il bottone appare se cestinoItems.length>0 (:2186), con le scritte «Svuota questa sede» / «Elimini il cestino di questa sede?» (:2190, :2212) e nessun nome di sede. Il server svuota la sola sede di sessione (cestino.py:184-198 → _resolve_ristorante_id). Se gli elementi sono tutti di altre sedi, svuota_cestino ritorna success con righe_eliminate 0 (db_service.py:1968-1969) e il client mostra «Cestino svuotato» (:2007) con la lista invariata dopo loadCestino. Il riferimento a «questa sede» in una pagina di gruppo non individua la sede: l'utente non sa quali fatture stia cancellando definitivamente.

**fix proposto.** Mettere il nome della sede attiva nell'etichetta e nella conferma, mostrare il bottone solo se fra gli elementi c'è quella sede, e usare righe_eliminate nel toast.

**presidio proposto.** Guardia sul .tsx e test endpoint con mock esplicito sul conteggio 0.

**gia presidiato da.** Nessuno: test_cestino_invalidazione_cache.py copre solo l'invalidazione.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2001-2011`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2186-2212`; `services/routers/cestino.py:184-198`; `services/db_service.py:1968-1969`

### F4-12 — Manca la guardia TD04 sul server /pagata: nessun numero cambia (falso allarme)

Filone 4 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuna pagina mostra un numero diverso. Solo il dettaglio della NC scriverebbe «Pagata il …» (:844-845) dopo una POST diretta.

**prova.** Ho cercato tutti i lettori di pagata. Escludono le NC prima o indipendentemente da pagata: computeKpi (lib :336 prima di :339), bucketizeDocumenti (:407 prima di :411), statoDocumento (:561 prima di :562), contaDaPagare (:122), aggregaPerSede (:785), CalendarView (client :499), endpoint calendario (routers/scadenziario.py:145-147), notifica (:461-463), chat scadenze (fastapi_worker.py:4866). Nell'esecuzione NCPAGATA@rB non entra in Pagate (mese): pagate_mese_count=2 = PAGMESE + DUP@rB. Non ci sono altri lettori Python o SQL di fatture_documenti.pagata (grep su services, worker, migrations).

**fix proposto.** Facoltativo: rifiutare TD04 lato server per difesa in profondità.

**presidio proposto.** Nessuno necessario per i numeri.

**gia presidiato da.** test_scadenziario_kpi_frontend.py::test_le_note_di_credito_non_sono_debiti, test_scadenziario_contatore_frontend.py::test_le_note_di_credito_non_gonfiano_il_contatore

**file e righe.** `services/routers/scadenziario.py:179-203`; `apps/web/src/lib/scadenziario.ts:335-351`

### Verificato e trovato giusto

- Filtri server sulle scritture. segna_fattura_pagata: filter_active + user_id + ristorante_id + file_origine (documenti_service.py:573-581); il fallback per id parte da un lookup già filtrato per user, sede e deleted_at (:584-605). elimina_fattura_soft: user + file_origine + sede + deleted_at IS NULL (cestino.py:229-238). oscura: user + file_origine + sede + deleted_at IS NULL (cestino.py:358-361). ripristina: user + file_origine + sede + deleted_at NOT NULL (db_service.py:1927-1932).
- Sede scrivibile (routers/scadenziario.py:67-94 e cestino.py:84-106): ownership su ristoranti.user_id più verifica_sede_consentita per i sotto-utenti; sede tecnica ammessa. È corretto: la vista di gruppo la include (gruppo.py _resolve_gruppo_con_tecnica) e i documenti di gruppo vivono lì. Una sede altrui dà 404 (test_pagata_con_ristorante_id_non_del_cliente_404).
- «aggiornate» conta i file_origine riusciti per sede, ciascuno un documento (fatture_documenti chiave user, sede, file_origine). Il toast «N fatture segnate come pagate» parla quindi di fatture: in catena DUP2 su due sedi vale 2 documenti, conteggio giusto.
- Singola handlePaga in catena: applicaPagataAVideo usa la chiave sede|file_origine. Esecuzione su DUP2@rA: a video cambia solo rA (rB resta pagata=false).
- Vista sede (dataset sede A): card Scadute 2/1050 = sezione Scadute 2/1050; Settimana 1/300 = sezione 1/300; Da pagare 6/2070 = somma sezioni scadute+settimana+mese+oltre+senza (1050+300+320+0+400); contatore contaDaPagare 6 = Da pagare count; «Seleziona tutte (6)» = Set 6; senza scadenza 1/400 sotto Da pagare.
- Vista gruppo: card Scadute 4/1600 = sezione 4/1600; Settimana 1/300 = sezione; Da pagare 9/3320 = 1600+300+320+700+400; tendina per sede aggregaPerSede rA 2070 + rB 1250 = 3320 = Da pagare. Dopo «Scadute»: tendina rA 1050 + rB 550 = 1600 = card; «X su Y» = contaDaPagare(filtrati)=4 su 9, uguale a Da pagare (filtro) 4.
- Sezione «Pagate» (3 / 1520 €, di sempre) e card «Pagate (mese)» (2 / 720 €): etichette diverse per popolazioni diverse, quindi non è un conflitto. Note di credito e Escluse da te sommano con Math.abs e stanno fuori da card e contatore.
- statoDocumento su tutti i 16 documenti usa la stessa precedenza dei bucket: oscurata, poi NC, poi pagata, poi senza scadenza/scaduta. Esempi: OSCSCAD → «Escluse da te», NCPAGATA → «Nota di credito», DUP2 → «Scaduta».
- Macchina a stati dei filtri, oggi. Le CARD si SOSTITUISCONO: Scadute poi Settimana porta filtroPeriodo a 'settimana', non a zero risultati. computeKpi dopo i due clic: scadute 0, settimana 1/300, con etichetta «(filtro)». Le SEDI si SOMMANO: alternaPuntoVendita su rA poi rB dà {rA,rB}, e spuntarle tutte torna a vuoto. È il contrario di quanto scriveva COERENZA_VISIVA_ANALISI_CARICO.md:214-216 (card che si sommano, pillole sedi che si sostituiscono). Il popover «Le card in alto non si sommano» (:2145-2146) descrive correttamente il comportamento di oggi.
- «Da pagare» chiama resetFiltri, che azzera periodo, fornitori, date, nuove, sede e ricerca (:1675-1683, :2093), ed è attiva solo senza filtri (:2092). In catena con la sede rA scelta la card mostra Da pagare (filtro) 2070 €, e dopo il clic 3320 € con la tendina su «Tutti i punti vendita». Comportamento coerente col suo stato attivo, non un numero sbagliato.
- I chip «Tutti»/«Solo scadute» impostano il periodo senza toggle (:2339), mentre Settimana, Mese e date personalizzate fanno toggle (:2354, :2361). Nessuna cifra incoerente: l'etichetta (filtro) segue filtriAttivi.
- La selezione sopravvive ai filtri per scelta presidiata (test :314: il piano usa `documenti`). Esecuzione: con SCAD1 e SETT1 selezionate e filtro fornitore SETT1, la barra dice 2, la conferma «2 fatture per 1300 €» (anche quella nascosta). La conferma dichiara numero ed euro: niente scrittura silenziosa, solo nessuna indicazione che una delle due non è a video.
- «Sposta in un'altra sede» e «Ripartisci sul gruppo» non compaiono in catena (PeekDialog :713-714 non carica le sedi se modalitaCatena). Non è dichiarato a video ma non produce numeri sbagliati, e così handleSpostata non si raggiunge in catena.
- Mobile: nessuna pagina scadenziario sotto apps/web/src/app/(mobile)/m (grep scadenz/pagata trova solo mobile-chat.tsx).
- git status --porcelain identico prima e dopo; i file di lavoro in scratchpad/audit/F4 sono stati cancellati.

### Non verificabile in sola lettura

- Quali account e sedi abbiano oggi lo stesso file_origine su due sedi (popolazione di F4-01, F4-02, F4-03): il compito vietava il DB, quindi clienti_ids sono vuoti. È una query read-only su fatture_documenti GROUP BY user_id, file_origine HAVING count(distinct ristorante_id)>1.
- Quanti documenti in lista non hanno header in fatture_documenti (il fallimento deterministico di F4-10): il codice cita «6 su 3.530» all'11/9, cifra presa da un commento e non misurata.
- Segno reale di fatture_documenti.totale_documento sulle TD04 (F4-08): dedotto dal codice (ImportoTotaleDocumento non invertito, segno_compensazione separato), non misurato a DB.
- elimina_fattura_soft e oscura_fattura controllano con .limit(1) senza filtro deleted_at (cestino.py:221-233, :306-313): un documento con alcune righe già cancellate singolarmente potrebbe rispondere «already_in_trash» pur essendo a video. Serve il DB per sapere se esistono documenti parzialmente cancellati.
- Esito parziale reale dell'azione di massa e comportamento del server su una NC: verificabili solo con una POST in produzione o con un client Supabase. Esclusi dai vincoli 2 e 3; ho usato la sola lettura del codice.
- Righe React con chiave duplicata (key={doc.file_origine} in AgendaSection :321, NoteCreditoSection :445, dayDocs :634) con omonimi su due sedi: l'effetto a rendering (righe perse o duplicate) non si esegue senza browser.

## F1b quadrature catena B

### F1b-01 — Mese in corso con 11.841 € di costi e 0 € di ricavi dentro i totali di Margini (anno corrente) e Catena (overview, ranking, margini-coperti)

Filone 1 · periodo non dichiarato · gravità bassa · confidenza alta

**chi lo vede.** Margini KPI bar + tab Calcolo con preset «Anno corrente» (1 gen → 15 ott, entrambe le sedi); Catena → I conti del gruppo, ranking per margine %, scheda Margini e coperti (vista anno); /m briefing catena. Account 2f3f93a1 (sedi bdda08d1, dcf1996e).

**prova.** Ricalcolo SQL (definizione costi_automatici_mensili + override modalità mensile): ottobre 2026 ha ricavi 0 su entrambe le sedi (nessun override, margini_mensili fatturato 0) ma costi auto+quote: bdda F&B 6.822,57 + spese 537,11 = MOL −7.359,68; dcf 3.772,33 + 709,05 = −4.481,38; gruppo −11.841,06. Totali gen–ott vs gen–set: gruppo MOL 109.788,58 (14,5 %) vs 121.629,64 (16,1 %); bdda 80.671,55 (17,2 %) vs 88.031,23 (18,7 %); dcf 29.117,03 (10,2 %) vs 33.598,41 (11,7 %). Margini: _aggrega_mensili_margini itera tutti i mesi del range (worker 11006-11060) e la pagina parte da anno_corrente = 1 gen→oggi (margini/page.tsx:47-55); Catena: gruppo_overview mesi_periodo = 1..mese_corr (gruppo.py:1152-1160), ranking margine_perc = mol/netto gen–ott (gruppo.py:1260) con `incompleti` giudicato sul mese PRECEDENTE (_costi_mese_per_sede su settembre, gruppo.py:1180-1184) → le due sedi risultano complete anche se ottobre pesa solo di costi. Il periodo È dichiarato a video (catena «Anno 2026 · gen–ott, ottobre in corso», _label_anno_parziale gruppo.py:1067-1083; Margini «1 gen → 15 ott», filtri-periodo.tsx:38) ma nessuna superficie dice che ottobre porta costi senza incasso; la Home invece isola il mese (worker 9926-9949) e non lo mostra. Esiste il segnale catena «ricavi mancanti nel mese in corso» (gruppo.py:2510-2545) come unico avviso.

**numeri attesi vs mostrati.** Gruppo gen–set MOL 121.629,64 (16,1 %) → mostrato gen–ott 109.788,58 (14,5 %); bdda 88.031,23 (18,7 %) → 80.671,55 (17,2 %); dcf 33.598,41 (11,7 %) → 29.117,03 (10,2 %).

**fix proposto.** Nel mese in corso con netto = 0 e costi > 0 (modalità mensile, incasso inserito a fine mese) escludere il mese dal margine % di ranking/KPI o mostrare accanto al totale «ottobre: costi N € senza incasso» (stessa logica di `costi_mancanti` ma rovesciata), senza cambiare l'arco dichiarato.

**presidio proposto.** Test su _aggrega_sedi_mensili/_aggrega_mensili_margini: mese corrente con netto 0 e fb > 0 → il margine % del periodo deve o escluderlo o esporre un flag `mesi_senza_ricavi` che il frontend mostri; mutante: togliere il flag → rosso.

**gia presidiato da.** tests/test_catena_periodo_e_soglie.py (etichetta e mese in corso), tests/test_gruppo_aggrega_sedi.py (formula) — nessun test sul caso ricavi 0 / costi > 0 nel mese corrente

**file e righe.** `services/fastapi_worker.py:11006-11060`; `services/routers/gruppo.py:1152-1184`; `services/routers/gruppo.py:1260`; `services/routers/gruppo.py:1067-1083`; `apps/web/src/app/(app)/margini/page.tsx:47-55`; `apps/web/src/app/(app)/margini/filtri-periodo.tsx:38`

### F1b-02 — «Spesa» di Analisi Fatture ≠ costi di Margini sullo stesso mese: differenza = costi manuali (altri_costi_*) e quote Da Classificare, non la data di competenza

Filone 1 · stessa etichetta per grandezze diverse · gravità bassa · confidenza alta

**chi lo vede.** Analisi Fatture KPI «Spesa totale» (routers/fatture.py get_fatture_kpi) vs Margini tab Calcolo/KPI bar, stessa sede e stesso mese. Sede bdda08d1 (9 mesi su 10 divergono), sede dcf1996e (solo ago/set per 3,83 e 8,18 €).

**prova.** data_competenza è NULL su tutte le 4.849 righe attive dell'account (0 righe, 0 € con mese di competenza ≠ mese documento; su tutto il DB 229/40.737) → COALESCE e data_documento coincidono. Replica SQL di get_fatture_kpi (data_documento, deleted_at NULL, oscurata=false, no NOTE, include Da Classificare, + righe quote proiettate = Σ quota_importo del riparto, worker _fetch_fatture_rows 10577-10665) contro costi Margini (fb_auto+spese_auto+altri_costi_fb+altri_costi_spese+quote_riparto_fb+quote_riparto_spese): bdda gen −483,00; feb −372,00; mar −342,00; apr −291,00; mag −235,00; giu −535,00; lug −381,00; ago −68,17 (= −72 altri + 3,83 quota DC); set −378,81 (= −387 + 8,19); ott 0. dcf: ago +3,83, set +8,18 (quote Da Classificare proiettate), altri mesi 0. Totale bdda gen–set: Analisi Fatture 3.098 € in meno dei costi di Margini (costi inseriti a mano, non da fattura) e 12,02 € in più per PV dalle quote Da Classificare che la proiezione non filtra (worker 10640-10660) mentre riparto_quote_mensili le esclude dal MOL (SQL live, filtro `q.categoria <> 'Da Classificare'`).

**numeri attesi vs mostrati.** bdda settembre 2026: Analisi Fatture 32.860,86 € vs Margini costi 33.239,67 € (diff −378,81 = −387 manuali + 8,19 quota DC); gennaio 54.048,97 vs 54.531,97 (−483).

**fix proposto.** Nessun fix numerico: sono due grandezze (acquisti da fattura vs costi del conto economico). Se serve coerenza a video, aggiungere alla KpiBar di Analisi Fatture la nota «esclude i costi inseriti a mano in Margini» oppure filtrare le righe proiettate Da Classificare come fa _righe_quote_gruppo (worker 10760-10775).

**presidio proposto.** Test che, su un dataset con altri_costi_fb > 0 e una quota Da Classificare, documenti la differenza attesa fra get_fatture_kpi.totale e get_margini_kpi.costi_fb+spese (o la azzeri se si sceglie di filtrare le proiettate DC).

**gia presidiato da.** Nessun test fissa i totali di /api/fatture/kpi contro Margini (MAPPA_NUMERI §D); test_sql_funzioni_soldi::test_costi_la_competenza_ha_precedenza_sulla_data_documento copre la competenza lato RPC

**file e righe.** `services/routers/fatture.py:367-489`; `services/fastapi_worker.py:10577-10665`; `services/fastapi_worker.py:10872-10931`; `services/riparto_service.py:443-540`

### F1b-03 — Chat query_margini espone per ottobre un «MOL» di −7.359,68 / −4.481,38 € su fatturato 0: è la somma dei costi, segnalato solo come «parziale»

Filone 1 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** Chat della sede (tool query_margini, worker 5292-5360) e vista catena con sede esplicita; entrambe le sedi di 2f3f93a1. La Home non lo mostra mai (settembre ha dati).

**prova.** Riesecuzione pura della regola (6 mesi da oggi indietro, has_data = fatturato>0 or fb>0 …, worker 5322-5338) sui ricalcoli SQL: ottobre 2026 ha fatturato 0,00, food_cost_pct None, mol −7.359,68 (bdda) e −4.481,38 (dcf), has_data True (fb 6.822,57 / 3.772,33) → entra nel risultato con parziale=True; incasso_fuori_norma non si applica al mese in corso (worker 7262-7270). Il risultato non porta `costi_mancanti` né un flag «ricavi mancanti» (MAPPA §A.8 confermata); il prompt (worker 4103-4108) spiega «parziale» come «mancano giorni» e invita a dividere per i giorni trascorsi, mentre qui mancano del tutto i ricavi (modalità mensile, inserita a fine mese). Gli altri 5 mesi sono corretti: set 56.032,50/42,7 %/6.163,68 e 34.234,80/30,1 %/6.167,21; ago marcato incasso_fuori_norma (16.265,09 < 0,75×52.812,05; 5.935,87 < 0,75×31.285,44).

**numeri attesi vs mostrati.** Atteso: ottobre senza MOL (o con nota «solo costi: 7.359,68 €»); mostrato all'AI: mol −7.359,68 (bdda) / −4.481,38 (dcf) con fatturato 0.

**fix proposto.** In _chat_query_margini aggiungere al mese `ricavi_mancanti: netto == 0 and fb > 0` (e `costi_mancanti` come la Home) e una `nota` che dica che il MOL del mese è la sola somma dei costi; nel prompt, trattare «parziale senza incasso» come dato da non commentare.

**presidio proposto.** Test: mese corrente con override assente e fb > 0 → la voce porta ricavi_mancanti True e nota non vuota; mutante: rimuovere il flag → rosso.

**gia presidiato da.** tests/test_fase_e_incasso_fuori_norma.py::test_query_margini_non_segna_il_mese_in_corso (solo il flag parziale)

**file e righe.** `services/fastapi_worker.py:5322-5338`; `services/fastapi_worker.py:4103-4108`; `services/fastapi_worker.py:9843-9855`

### Verificato e trovato giusto

- costi_automatici_mensili sul DB live (pg_get_functiondef, STABLE, nessuna scrittura) = definizione richiesta: deleted_at IS NULL, NOT oscurata, categoria <> 'Da Classificare', NOT COALESCE(ripartita_su_gruppo,false), mese = COALESCE(data_competenza,data_documento), spese = p_cat_spese (CATEGORIE_SPESE_GENERALI = 4 operative + MATERIALE DI CONSUMO, config/constants.py:212-218), F&B = tutto il resto meno '📝 NOTE E DICITURE'; la replica SQL dà es. bdda set F&B 21.590,56 / spese 8.126,29, dcf set 9.379,13 / 1.363,31.
- Home oggi 15/10 (regola worker 9926-9949 applicata ai dati): ultimo mese completo = settembre, has_data su entrambe le sedi → nessun fallback né «in corso». bdda: Fatturato (lordo) 56.032,50, food cost 42,7 %, personale 12.174,00, spese 11.212,27, MOL 6.163,68; dcf: 34.234,80, 30,1 %, 11.240,00, 4.449,28, 6.167,21. Confronto soppresso perché agosto è fuori norma (bdda 16.265,09 < 0,75×mediana 52.812,05; dcf 5.935,87 < 0,75×31.285,44) e settembre è nella norma (51.577,35 > 38.609,25; 31.285,44 > 21.165,16) — riesecuzione pura di _incasso_fuori_norma (worker 7256-7290). Etichetta a video «Settembre» (kpi-block.tsx:77 meta={periodo_label}). /m briefing usa lo stesso fetchKpi+KpiBlock (m/briefing/page.tsx:29-31): identico.
- Catena overview (gruppo.py:1108-1290, mesi 1..10): Fatturato (IVA incl.) 825.296,66; netto 756.400,18; F&B 289.274,21 → food cost 38,2 %; spese 179.704,11; personale 177.633,28; MOL 109.788,58; margine medio 14,5 %; ranking bdda 17,2 % / dcf 10,2 %; etichetta «Anno 2026 · gen–ott, ottobre in corso» mostrata in sintesi-catena.tsx (meta={overview.periodo_label}) e in mobile-catena.tsx:159 («MOL del gruppo · {periodo_label}»). Sparkline esclude ottobre (netto 0, gruppo.py:1237-1241).
- Catena «Margini e coperti» vista anno (gruppo.py:1538-1660): fatturato NETTO per PV con tooltip «al netto dell'IVA» (scheda-margini-coperti.tsx:66-67): bdda 470.010,65, dcf 286.389,53, gruppo 756.400,18; margine % 17,2 / 10,2 / 14,5. Etichetta periodo = _label_anno_parziale (presidio tests/test_catena_periodo_e_soglie.py).
- Margini preset «Anno corrente» (1 gen → 15 ott, dichiarato in filtri-periodo.tsx:38): bdda Fatturato Netto 470.010,65 (sub «lordo 511.586,99»), Costi F&B 189.374,40, Margine Lordo 280.636,25, Spese 102.196,16, Personale 97.768,54, MOL 80.671,55 (17,2 %); dcf 286.389,53 (313.709,67), 99.899,81, 186.489,72, 77.507,95, 79.864,74, 29.117,03 (10,2 %). Per sede coincidono al centesimo con la catena: _aggrega_mensili_margini (worker 11006-11060) e _aggrega_sedi_mensili (gruppo.py:217-325) hanno la stessa formula (override iva10/1,10+iva22/1,22+altri; fb = auto+altri_costi_fb+quote_riparto_fb; spese idem; personale 3 campi).
- Le quattro «Fatturato» diverse sono tutte giuste e il periodo/grandezza è dichiarato a video: Home «Fatturato» lordo del mese (Settembre); Margini «Fatturato Netto» con lordo sotto (1 gen → 15 ott); Catena «Fatturato (IVA incl.)» gen–ott; Margini e coperti «Fatturato» netto con tooltip; chat «fatturato» lordo per mese.
- Ricavi senza IVA esclusi (commit 42910123/99bee8b4/002248c1): la regola vive nel DB — flag ristoranti.escludi_ricavi_noiva + trigger BEFORE ricavi_noiva_esclusi_guardia che azzera altri_ricavi_noiva (e ricalcola netto/primo_margine/mol su margini_mensili); RPC elimina_ricavi_noiva ripulisce lo storico. Sul live: colonna presente, 3 trigger attivi (tgenabled O) su ricavi_giornalieri, ricavi_modalita_mensile, margini_mensili; funzione con ramo RETURN NULL e ramo margini_mensili. Nessuna sede su tutto il DB ha escludi_ricavi_noiva=true (0 righe) e le 3 sedi di B sono false. Tutti i lettori leggono altri_ricavi_noiva da tabelle coperte dal trigger, quindi l'esclusione vale per costruzione: _kpi_periodo (worker 9781-9795, usato da Home, chat, briefing _netti_mensili/_buona_notizia/_briefing_mese_chiuso), _aggrega_sedi_mensili (gruppo.py:271-281), _aggrega_mensili_margini (worker 11036-11040), get_margini_analisi (margini.py:1306), home_salute (worker 9538-9566), gruppo_salute_componenti + _applica_override_netto (gruppo.py:735-775), /m nettoDaMostrare via fetchNettoMese (periodi.ts:138-160 su /api/ricavi/modalita e /api/ricavi/giornalieri), email settimanale (ricavi_giornalieri). GET /api/account/ricavi-noiva applica l'override mensile come Margini. Presidio: tests/test_sql_ricavi_noiva.py (23 test).
- margini_mensili totali salvati sono stantii su 20/20 mesi ma nessuna superficie li legge: costi_fb_auto e costi_spese_auto = 0,00 ovunque (ricalcolo es. bdda gen 18.744,93 / 25.031,72); mol_perc = 0,00 ovunque; mol diverge su 20/20 (dcf gen salvato 14.158,93 vs ricalcolo 81,79; bdda feb −21.034,29 vs 22.342,63; ott −418,46 vs −7.359,68); fatturato_netto = 0 su bdda 9 mesi (modalità mensile) e su dcf gen–giu differisce di 60–314 € (altri_ricavi_noiva salvato 626,49 vs override 479,00 a gennaio). Lettori verificati: _kpi_periodo ricalcola (worker 9800-9830) e carica_margini_anno seleziona `mol` senza che nessuno lo usi (margine_service.py:366); gruppo_overview seleziona fatturato_netto (gruppo.py:1130) ma _aggrega_sedi_mensili non lo legge; analisi-centri e analisi-avanzata usano fatturato_netto solo senza override (margini.py:545, :706) → per B solo ottobre, dove salvato 0 = ricalcolo 0; segnale ricavi_mancanti lo usa solo come presenza > 0 sul mese corrente (gruppo.py:2529); segnale margine_calo ricalcola (gruppo.py:2417-2425). Presidi: test_kpi_periodo_quote_riparto::test_mol_home_coincide_con_formula_barra_kpi_margini, test_gruppo_aggrega_sedi::test_override_vince_sullo_snapshot, test_analisi_margini_quote_riparto::test_analisi_centri_override_ha_la_precedenza_sullo_snapshot.
- Quote riparto: Σ quota_importo per PV/mese (escluse Da Classificare) = margini_mensili.quote_riparto_fb + quote_riparto_spese su 20/20 mesi (scarto 0,00); gennaio ha quote con tipo 'fb' ma categoria SPESE (20,77 / 6,92) e tipo 'generale' con categoria FB (0,91): riparto_quote_mensili (SQL live) decide per categoria quando non è NULL → 6.309,30 = 6.308,39 + 0,91 e 3.963,02 = 3.942,25 + 20,77, coerente con la proiezione per categoria di _proietta_riparto (riparto_service.py:381-441). Il mese del riparto coincide col mese di data_documento delle righe reali su 10/10 mesi (0 righe difformi).
- Da Classificare: 4 righe attive (3 sulla sede tecnica f7bba05f, ripartite, 7,67 + 7,67 + 8,71 = 24,05 €, needs_review; 1 su bdda del 13/10 a 0,00 €): fuori dai costi auto (RPC esclude per categoria e per ripartita) e fuori dalle quote del MOL (riparto_quote_mensili esclude 'Da Classificare' da q_spese: le quote DC 3,83 ago + 8,19/8,18 set per PV non sono in quote_riparto_*, verificato dallo scarto 0,00 sopra). Visibili: la riga bdda nel filtro Da classificare di Analisi Fatture, nella voce Salute «da controllare» (1 prodotto, worker 9606-9625) e nel briefing (_briefing_righe_da_classificare, worker 7864+); le 3 della sede tecnica in Catena → Fatture → Costi di gruppo (/api/gruppo/costi-comuni, riparto.py:1424-1448 da_classificare_importo/costi; correzione dal dropdown via PATCH /api/riparto/riga-categoria, scheda-costi-gruppo.tsx:527-540) e come righe proiettate con categoria Da Classificare/needs_review nel tab Articoli di ciascun PV (12,02 € per PV). Regola di dominio 1/6 rispettata.
- data_competenza vs data_documento: 0 righe e 0 € con mese diverso sull'account (data_competenza NULL su 4.849/4.849 righe attive; 229/40.737 su tutto il DB, altri account) → per B la «Spesa» di Analisi Fatture e i costi di Margini non divergono per il mese di competenza (vedi F1b-02 per le cause reali).
- ripartita_su_gruppo e oscurata: 0 NULL su 40.737 righe attive di tutto il DB → `.neq('ripartita_su_gruppo', True)` di _calcola_costi_auto_per_mese (worker 10897, PostgREST scarta i NULL) e `NOT COALESCE(...)` della RPC danno oggi lo stesso insieme; il flag da_verificare è spento (ESCLUDI_DA_VERIFICARE_DAI_MARGINI False, db_service.py:220-237) quindi RPC e query Python coincidono.
- Home Salute su settembre per entrambe le sedi: «fatture» ok (F&B di settembre > 0 via _costi_automatici_mese, worker 8458-8500), «fatturato» ok per bdda solo grazie al fallback override (snapshot margini_mensili a 0, worker 9560-9566; presidio tests/test_salute_modalita_mensile.py), «personale» ok (12.174 / 11.240). Catena completezza: _applica_override_netto (gruppo.py:735-775) evita il falso «senza fatturato» di bdda (presidio tests/test_gruppo_completezza_override.py).
- Volumi account B ri-misurati: fatture_documenti 569 attivi (802 con cestino), documenti dal 1/1 al 13/10/2026, ultimo caricamento 14/10; 4.849 righe attive (bdda 2.439 = 247.443,29 €; dcf 1.431 = 143.687,56 €; sede tecnica 979 = 74.773,50 € tutte ripartite); margini_mensili 20 righe (2 PV × gen–ott 2026); override modalità mensile gen–set su entrambe le sedi, ottobre assente.

### Non verificabile in sola lettura

- Resa effettiva a video delle card (cache Home 2', HTML renderizzato): il worker non è stato chiamato; i numeri sono il ricalcolo con la stessa formula del codice (worker _kpi_periodo, gruppo.py _aggrega_sedi_mensili, margini.py get_margini_kpi).
- livello_dati e pv_da_completare della catena oggi: dipendono da _completezza_dati_pv + _personale_non_ancora_dovuto eseguiti nel worker; non riprodotti.
- Comportamento dei lettori DOPO un'esclusione reale dei ricavi senza IVA: nessuna sede del DB ha il flag acceso e attivarlo richiede una scrittura in produzione; verificato solo per costruzione (trigger attivi + lettori sulle tabelle coperte) e tramite tests/test_sql_ricavi_noiva.py.

## F3 chat di catena

### F3-01 — Il prompt della sede fa calcolare MOL %, personale % e spese % sul fatturato LORDO, mentre la pagina Margini divide per il NETTO

Filone 3 · bug vero · gravità alta · confidenza media

**chi lo vede.** Chat della Home sede, desktop e /m, e query_margini anche dalla chat di catena. Riguarda tutti gli account che hanno la pagina margini e chiedono «il personale/MOL va bene?». Gli ID non si possono separare senza DB, quindi va considerato strutturale per tutti.

**prova.** Il blocco KPI del prompt passa 'Fatturato: €{kpi.fatturato}' (fw:3693). Quel valore è il LORDO, iva10+iva22+altri (_kpi_periodo fw:9812); il MOL invece è calcolato sul netto. Le soglie del prompt dicono 'MOL % (margine operativo lordo ÷ fatturato)' e 'Costo personale % (costo personale ÷ fatturato)' (fw:4048, 4051). La pagina Margini fa personale_perc=pers/netto e mol_perc=mol/netto (services/routers/margini.py:1526-1527). Ho eseguito _kpi_periodo, estratto via AST, con iva10=50.000, iva22=5.000, personale 15.000, F&B 14.000, spese 9.000: fatturato 55.000, netto 49.552,91, MOL 11.552,91. Sulla pagina: personale 30,27% (fascia 'elevato'), MOL 23,31%, spese 18,16%. Con la formula che il prompt dà al modello: personale 27,27% (fascia 'norma'), MOL 21,01%, spese 16,36%. Lo scarto è sistematico (lordo/netto ≈ 1,10) e fa cambiare fascia di benchmark. query_margini restituisce lo stesso fatturato lordo senza il netto (fw:5332).

**fix proposto.** Mettere nel prompt (e in query_margini) le percentuali già calcolate con la formula della pagina (personale_pct, spese_pct, mol_pct sul netto), oppure almeno il netto, e cambiare le righe delle soglie in '÷ fatturato netto (IVA esclusa)'. Il modello non deve dividere.

**presidio proposto.** Un test che costruisce il prompt con margini sintetici (iva10/iva22 diversi da zero) e verifica che la riga del personale % riporti lo stesso numero di margini.py:1526 sugli stessi dati. Va provato per mutazione sostituendo netto con lordo.

**gia presidiato da.** Nessuno. test_chat_gate_permessi_pagina.py controlla solo che il MOL compaia o no; nessun test confronta le percentuali che il modello deve calcolare con quelle della pagina.

**file e righe.** `services/fastapi_worker.py:3693-3697`; `services/fastapi_worker.py:4045-4055`; `services/fastapi_worker.py:4131`; `services/fastapi_worker.py:9812-9846`; `services/fastapi_worker.py:5329-5336`; `services/routers/margini.py:1526-1527`

### F3-02 — Un 429 di OpenAI (sovraccarico) blocca la casella della chat con «Limite di oggi raggiunto» anche se restano crediti

Filone 3 · bug vero · gravità media · confidenza alta

**chi lo vede.** Home (desktop) e /m/chat, sia vista sede sia catena: tutti gli account, quando OpenAI risponde RateLimitError.

**prova.** _chat_loop_openai trasforma RateLimitError in HTTPException 429 'Servizio temporaneamente sovraccarico...' (fw:4591). Il client chiama quotaEsaurita(status, data) (assistente-provider.tsx:152), che su qualsiasi 429 senza 'questo mese' restituisce 'giorno' (home-chat.ts:138-143). Eseguito con node: quotaEsaurita(429,{error:'Servizio temporaneamente sovraccarico...'}) dà 'giorno'. statoCrediti({90,900}, server alle=1000, risposta alle=2000 finita='giorno') dà esaurite=true, testo 'Limite di oggi raggiunto — si azzera a mezzanotte', rimasti=894. La casella resta bloccata (use-conversazione.ts bloccato = inCorso || esaurite) finché un ricaricamento della pagina non porta una lettura server più recente.

**fix proposto.** Nel worker usare 503 (non 429) per il sovraccarico di OpenAI, oppure far riconoscere a quotaEsaurita i soli due testi della quota (giorno e mese) invece di «ogni 429».

**presidio proposto.** Caso in test_home_chat_frontend.py: quotaEsaurita(429, {error: testo del sovraccarico}) deve essere null. Più un test sul worker che fissi lo status del sovraccarico OpenAI diverso da quello della quota.

**gia presidiato da.** tests/test_home_chat_frontend.py:298-313 esegue quotaEsaurita con node, ma solo sui messaggi della quota. A :308 fissa proprio 429 senza testo = 'giorno', cioè il comportamento che produce il blocco.

**file e righe.** `services/fastapi_worker.py:4590-4591`; `apps/web/src/lib/home-chat.ts:138-143`; `apps/web/src/lib/home-chat.ts:420-435`; `apps/web/src/components/home/assistente-provider.tsx:149-153`; `apps/web/src/components/home/use-conversazione.ts:36-37`

### F3-03 — Una domanda fallita dopo la RPC dei crediti (502 guasto di uno strumento, 504 timeout, 429 OpenAI) consuma 3 crediti, anche di ricarica, e il contatore a video non lo mostra

Filone 3 · bug vero · gravità media · confidenza alta

**chi lo vede.** Chat sede e catena, desktop e /m: tutti gli account. Con crediti del mese finiti si consuma la ricarica pagata.

**prova.** La RPC chat_crediti_check_and_log fa INSERT in chat_usage_log prima della chiamata OpenAI (migration 20261010135911_chat_crediti_ricariche.sql:189; chiamata a fw:6220). I rifiuti prima della RPC non consumano: 403 sotto-utente (fw:6148-6151), 400 catena con una sola sede (fw:6159-6171), 403 piano free, catena spenta, chat spenta (fw:6188-6214); 429 della quota esce prima dell'INSERT (migration :161,181,185). Dopo la RPC non esiste compensazione: grep 'rimbors|storn|refund' in fastapi_worker.py dà 0 risultati. Gli 8 strumenti di sede non fase F non hanno try (AST: query_costi, scadenze, appuntamenti, ultimi_acquisti, trend, confronto con 0 try). Un'eccezione risale a esegui_tool (fw:4618) e diventa 502 (fw:4635); solo la fase F è protetta (fw:5960-5974). Eseguito con node: dopo 502 o 504 contatoreAggiornato(data senza crediti_oggi) restituisce i crediti di prima e statoCrediti mostra 'Ti restano 894 crediti', mentre il server ne ha scalati 3 (CHAT_CREDITI_PER_DOMANDA=3, fw:3048).

**fix proposto.** Avvolgere ogni strumento di sede in un try che restituisca al modello {errore:'dato non leggibile...'}, come per la fase F. Per 502/504/429 OpenAI dopo la RPC: un'RPC di storno idempotente (DELETE della riga appena inserita, per id) oppure una decisione dichiarata e documentata che il tentativo si paga. Nella risposta d'errore includere i crediti aggiornati, così il contatore a video resta vero.

**presidio proposto.** Test su chat_ai (sb mock) con _chat_query_costi che solleva: oggi la risposta è 502. Dopo il fix va asserito o lo storno o il 200 con errore allo strumento. Un test SQL che verifichi che dopo lo storno chat_crediti_stato torna al valore precedente.

**gia presidiato da.** tests/test_chat_catena_quota_non_consumata.py esegue chat_ai vero (sb mock) e prova solo il rifiuto prima della quota per la catena a sede singola. tests/test_chat_strumenti_pagine.py:285 prova il try della sola fase F (query_tag). Nessun test sui guasti dopo la RPC.

**file e righe.** `services/fastapi_worker.py:6218-6226`; `services/fastapi_worker.py:4580-4636`; `services/fastapi_worker.py:5913-5978`; `supabase/migrations/20261010135911_chat_crediti_ricariche.sql:139-195`; `apps/web/src/lib/home-chat.ts:149-159`

### F3-04 — «Appuntamenti di oggi» nel prompt della sede usa date.today() del server (UTC): fra mezzanotte e le 01/02 di Roma inietta quelli di ieri

Filone 3 · periodo non dichiarato · gravità media · confidenza alta

**chi lo vede.** Chat della Home sede, desktop e /m, per chi ha la pagina agenda e scrive fra 00:00 e 01:00 (CET) o 02:00 (CEST). Tutti gli account con eventi in diario_eventi.

**prova.** Il prompt mette 'Oggi e' {oggi_str}' da _oggi_rome() (fw:3998-4001, relativo :475-478) e, nello stesso prompt, '## Appuntamenti di oggi' filtrati con data_evento = _date_ag.today() (fw:3742). Il server gira in UTC, lo dice la docstring di _oggi_rome (fw:46-47). Eseguito: alle 2026-10-15T22:30Z date.today() UTC = 2026-10-15 e _oggi_rome() = 2026-10-16, quindi il modello riceve 'Oggi è 16 ottobre' con gli appuntamenti del 15. CHAT_ASSISTENTE.md §6 punto 4 dice che a 'cosa ho oggi' risponde dal prompt senza chiamare lo strumento. Gemello minore: query_costi usa _date_q.today() per decidere 'mese_non_ancora_caricato' (fw:4808). Che i clienti scrivano di notte è documentato: 1 riga su 95 di chat_usage_log fra 00 e 02 di Roma (tests/test_chat_quota_giorno_di_roma.py docstring).

**fix proposto.** Sostituire _date_ag.today() e _date_q.today() con _oggi_rome().

**presidio proposto.** Test sul prompt con _oggi_rome e date.today patchati a giorni diversi (caso scelto dove UTC e Roma divergono). La query a diario_eventi deve ricevere la data di Roma. Va provato per mutazione.

**gia presidiato da.** Nessuno. query_appuntamenti (fw:4941) usa già _oggi_rome; nessun test copre il blocco agenda del prompt.

**file e righe.** `services/fastapi_worker.py:3735-3762`; `services/fastapi_worker.py:4806-4810`; `services/fastapi_worker.py:43-52`

### F3-05 — query_margini restituisce {mesi: []} quando la lettura fallisce: il guasto si presenta al modello come «nessun dato»

Filone 3 · bug vero · gravità media · confidenza alta

**chi lo vede.** Chat sede (desktop e /m) e catena (query_margini con sede) durante un errore Supabase o RPC: tutti gli account con la pagina margini.

**prova.** Dentro _anno() un'eccezione su carica_margini_anno o calcola_costi_automatici_per_anno_sql diventa ({}, {}, {}) (fw:5346-5354). _kpi_periodo dà quindi has_data False e il mese sparisce. Eseguito _chat_query_margini estratto via AST, con margine_service finto che solleva RuntimeError('timeout supabase'): risultato {'mesi': []}, identico a un cliente senza margini, senza campo errore. Il prompt di sede dice 'se uno strumento torna vuoto, dillo' e §6 di CHAT_ASSISTENTE.md ('Onestà sui guasti') vieta proprio di far passare un guasto per assenza di dati.

**fix proposto.** Se una lettura fallisce restituire {'errore': 'dato non leggibile in questo momento: non dire che non c'e'...'}, come la fase F (fw:5972-5974), invece di {mesi: []}.

**presidio proposto.** Test su _chat_query_margini con carica_margini_anno che solleva: deve uscire 'errore' e non 'mesi': []. Va provato per mutazione rimettendo l'except che restituisce dizionari vuoti.

**gia presidiato da.** tests/test_fase_e_incasso_fuori_norma.py:201 copre il guasto solo per _incasso_fuori_norma_sede, non per _chat_query_margini.

**file e righe.** `services/fastapi_worker.py:5305-5359`

### F3-06 — confronto_prezzi ordina e premia il «prezzo migliore» fra unità di misura diverse e non passa l'unità al modello

Filone 3 · bug vero · gravità media · confidenza media

**chi lo vede.** Chat sede e catena (confronto_prezzi con sede), desktop e /m, quando la ricerca tollerante trova lo stesso prodotto in formati diversi da fornitori diversi.

**prova.** Ho eseguito _chat_confronto_prezzi estratto via AST, con utils/voci_prezzo.py vero e sb finto, su 3 righe: A 'MOZZARELLA FIOR DI LATTE KG' 8,00 €/KG, B 'MOZZARELLA 125G' 1,20 €/PZ, C 'MOZZARELLA BUFALA CT 3KG' 36,00 €/CT. Output in ordine B (1,2), A (8,0), C (36,0) con i soli campi fornitore, prezzo, data, descrizione: unita_misura è letta (fw:5418) ma non restituita (fw:5458-5468). La descrizione dello strumento dice 'per trovare il migliore' (fw:5546). Il modello direbbe B più conveniente, mentre al kg costa 9,60 contro 8,00. Differenza e % di risparmio restano al modello. La frequenza sui dati reali non è misurata (filone senza DB).

**fix proposto.** Restituire unita_misura per voce, raggruppare o confrontare solo fra voci con la stessa unità (o normalizzare per kg/l quando possibile) e calcolare nel tool differenza e % rispetto al migliore, per gruppo di unità.

**presidio proposto.** Test con righe di unità diverse: l'ordinamento non deve mescolare PZ e KG e ogni voce porta l'unità. Va provato per mutazione.

**gia presidiato da.** tests/test_chat_confronto_prezzi_per_fattura.py (commit 149b3538) copre la scelta dell'ultima fattura per fornitore, non le unità.

**file e righe.** `services/fastapi_worker.py:5407-5468`; `services/fastapi_worker.py:5544-5557`

### F3-07 — query_scadenze promette «quanto devo a X» e «scadenze questa settimana» ma dà solo il totale generale e un elenco troncato a 30, senza totali per fornitore, settimana o scadute

Filone 3 · bug vero · gravità media · confidenza media

**chi lo vede.** Chat sede (pagina scadenziario) e catena (query_scadenze con sede), desktop e /m. Riguarda gli account con più di 30 documenti aperti.

**prova.** La descrizione promette 'quanto devo a X', 'scadenze questa settimana' (fw:5504-5506). Ho eseguito _chat_query_scadenze estratto via AST su 55 documenti aperti: 25 di Y ottobre, 4 di X il 20/10, 8 di X a dicembre, 10 di Z senza data, 5 di X senza data, 3 di X scaduti a settembre. Mostrate 30 voci su 55, totale_da_pagare 19.600, nota di troncamento presente, nessun campo per fornitore o per periodo. Debito vero verso X 16.600 contro 2.100 sommando le voci mostrate. 'Questa settimana' (15-21/10): vero 6.500 contro 1.700 calcolabile dalle voci mostrate. Le scadute non hanno un flag e la differenza di date resta al modello. La nota dice di non presentare l'elenco come esaustivo: questo mitiga ma lascia la domanda senza risposta.

**fix proposto.** Aggiungere argomenti opzionali fornitore e intervallo (da/a, preset 'settimana') con filtro prima del troncamento, e restituire totale_filtrato, n_documenti_filtrati e scaduto_totale calcolati su tutte le voci.

**presidio proposto.** Test con più di 30 voci: con fornitore=X il totale dello strumento deve essere uguale alla somma di tutti i documenti di X, anche quelli fuori dalle 30.

**gia presidiato da.** tests/test_chat_query_scadenze.py (:56-233) presidia il troncamento onesto e il totale complessivo, non i totali per fornitore o settimana.

**file e righe.** `services/fastapi_worker.py:4843-4926`; `services/fastapi_worker.py:5500-5514`

### F3-08 — Il prompt chiede al modello di calcolare medie giornaliere, impatti in € e confronti fra periodi, anche sui costi da fatture, che arrivano a fine mese

Filone 3 · periodo non dichiarato · gravità media · confidenza media

**chi lo vede.** Chat sede e catena, desktop e /m, su ogni confronto mese su mese o domanda «conviene?». Tutti gli account.

**prova.** Righe del prompt di sede che fanno calcolare il modello: fw:4105-4106 'calcola i giorni trascorsi... (totale mese ÷ giorni trascorsi)', applicato a ogni confronto mese su mese, quindi anche alla spesa da fatture, che lo stesso prompt dice caricate 'a fine mese o in ritardo' (fw:4083); fw:4130-4133 'Calcola subito l'impatto concreto... rientrare al 30% varrebbe €25.800' con la base lorda di F3-01; fw:4147 'chiama query_costi DUE VOLTE... e confronta tu i totali'; fw:4045-4054 percentuali '÷ fatturato'; fw:3673 date relative 'calcolale da oggi' (solo con i proponi_*). Prompt di catena: fw:4290 media giornaliera e fw:4287 'Confronta SEMPRE per percentuali/incidenze', ma gruppo_spesa dà solo € per sede (vedi F3-09). Nessuno strumento restituisce giorni trascorsi, medie o differenze: query_costi solo totale; query_margini senza delta e senza MOL % (fw:5329-5336). Questa è una rilevazione sul testo del prompt: il modello non è stato chiamato (vincolo del filone).

**fix proposto.** Calcolare nel dato le metriche che il prompt chiede: giorni trascorsi e media giornaliera nel risultato di query_costi e query_margini quando il mese è il corrente, delta e % fra mesi in query_margini. Limitare la regola della media giornaliera al fatturato e dire esplicitamente che sui costi da fatture il mese in corso non si confronta.

**presidio proposto.** Test sul dato restituito (non sul testo del prompt): query_costi del mese corrente porta giorni_trascorsi e la media; query_margini porta delta_pct fra mesi consecutivi.

**gia presidiato da.** tests/test_audit_bug_passata2.py:157 verifica solo con getsource che 'parziale' compaia nel sorgente (non è un presidio di comportamento).

**file e righe.** `services/fastapi_worker.py:4083`; `services/fastapi_worker.py:4105-4107`; `services/fastapi_worker.py:4130-4134`; `services/fastapi_worker.py:4147`; `services/fastapi_worker.py:4287-4291`; `services/fastapi_worker.py:3673-3674`

### F3-09 — gruppo_spesa consegna al modello la pivot con chiavi UUID per sede, senza incidenza per sede, e il prompt chiede di confrontare per incidenze

Filone 3 · bug vero · gravità bassa · confidenza bassa

**chi lo vede.** Chat della catena (desktop e /m vista catena), account multi-sede con la scheda spesa accesa.

**prova.** SpesaPivotResponse: per_pv Dict[ristorante_id → €], totali_pv con chiave ristorante_id, pv [{id, nome}] come unica mappa (services/routers/gruppo.py:1384-1399, 1480-1494). incidenza_pct è la quota della riga sul totale generale, non l'incidenza per sede. Il dispatcher passa model_dump() così com'è (fw:4535-4537). Ho eseguito una stima della forma con dati sintetici: con 5 sedi e 200 fornitori, 69.951 caratteri, gli UUID ripetuti 1.010 volte; con i nomi al posto degli UUID 36.621. Il modello deve rimappare gli UUID e calcolare da solo le incidenze per sede che il prompt di catena esige (fw:4287).

**fix proposto.** Nel dispatcher di catena trasformare per_pv e totali_pv con chiave nome sede e aggiungere l'incidenza per sede (riga/totale della sede); eventualmente limitare alle prime N righe con 'altro'.

**presidio proposto.** Test sul dispatcher: il risultato di gruppo_spesa non contiene UUID come chiavi e porta incidenza per sede.

**gia presidiato da.** Nessuno sul formato consegnato al modello.

**file e righe.** `services/fastapi_worker.py:4535-4537`; `services/routers/gruppo.py:1384-1399`; `services/routers/gruppo.py:1480-1494`; `services/fastapi_worker.py:4287`

### F3-10 — SICUREZZA_GDPR.md §8 dichiara chat anonimizzata («I nomi veri non escono mai») e §6 la pulizia anti prompt-injection: nella chat non esiste nessuna delle due

Filone 3 · bug vero · gravità media · confidenza alta

**chi lo vede.** Documentazione tecnica interna (chi decide su GDPR e sicurezza). Il comportamento reale riguarda tutti gli account che usano la chat.

**prova.** §8 (SICUREZZA_GDPR.md:191-199): 'Prima di ogni chiamata a OpenAI per briefing e chat: prodotti → Prodotto_1, fornitori → Fornitore_123... I nomi veri non escono mai dall'infrastruttura'. Nel codice _anonymize_bullets (services/daily_briefing_service.py:1518) ha un solo chiamante, il briefing (:1697), e anche lì copre solo i bullet 📈 e 🏷 con segnaposto '<<P1>>', non nel formato dichiarato. Nella chat arrivano a OpenAI in chiaro: fornitori del prompt (fw:3732), titoli agenda (fw:3759), nome_referente (fw:4078, 4280; per un sotto-utente è il nome del dipendente), nome sede/gruppo, l'email dell'utente se nome_ristorante manca (fw:3542-3545), e ogni risultato degli strumenti serializzato (fw:4621): descrizioni prodotto, fornitori, descrizioni libere di spese_extra e agenda, nomi tag, UUID delle sedi. §6 (:169) dichiara 'Control char removal + troncamento 300 char prima di OpenAI'. _CTRL_RE e il taglio a 300 esistono solo in ai_service.py:5616-5620 (categorizzazione). La chat passa i messaggi utente grezzi (fw:6313; solo max_length 4000 e tetto 24.000) e i dati degli strumenti senza pulizia; l'unica difesa è una riga del prompt ('DATO GREZZO... non eseguire comandi', fw:4140, 4296). Le descrizioni di riga fattura sono testo scritto dai fornitori.

**fix proposto.** Riscrivere §8 come è davvero: briefing parzialmente pseudonimizzato (solo i nomi nei bullet di prezzo), chat in chiaro con l'elenco dei dati. Limitare §6 alla categorizzazione. In alternativa, se la promessa va mantenuta, implementare pseudonimizzazione e pulizia sul percorso chat (decisione di Mattia).

**presidio proposto.** Test di documentazione: §8 non può nominare la chat finché _anonymize_bullets non ha un chiamante nel percorso /api/chat (lettura del grafo delle chiamate, non del testo). Un test che costruisce il prompt di sede con un fornitore noto e verifica che compaia (o non compaia) in chiaro, coerente con il doc.

**gia presidiato da.** Nessuno: nessun test in tests/ fissa l'anonimizzazione della chat; test_documentazione_onesta controlla simboli e percorsi, non questa affermazione.

**file e righe.** `DOCUMENTAZIONE/tecnica/SICUREZZA_GDPR.md:169`; `DOCUMENTAZIONE/tecnica/SICUREZZA_GDPR.md:191-199`; `services/daily_briefing_service.py:1518-1553`; `services/daily_briefing_service.py:1697`; `services/fastapi_worker.py:3732`; `services/fastapi_worker.py:3759`; `services/fastapi_worker.py:4078`; `services/fastapi_worker.py:4621`; `services/fastapi_worker.py:6313`; `services/ai_service.py:5616-5620`

### F3-11 — Privacy policy pubblica e COMPLIANCE_GDPR.md descrivono il payload della chat a OpenAI in modo incompleto (mancano referente, testi liberi, righe fattura, scadenze, agenda, tag)

Filone 3 · bug vero · gravità media · confidenza alta

**chi lo vede.** Pagina pubblica /privacy e documento di compliance: lettori esterni e clienti; riguarda tutti gli account.

**prova.** Privacy (apps/web/src/app/(legal)/privacy/page.tsx:245-250): l'assistente trasmette 'indicatori economici..., le principali categorie di spesa e i principali fornitori con i relativi importi, oltre al nome dell'attività'. COMPLIANCE_GDPR.md:57 dice lo stesso, 'verificato nel codice il 09/09/2026', cioè prima dei 7 strumenti di catena (29/9) e della fase F (8/10). Nel codice arrivano a OpenAI anche: nome_referente, dato personale e per un sotto-utente nome del dipendente (fw:4078, 4280); titoli degli appuntamenti di oggi (fw:3759); con gli strumenti descrizioni e prezzi di righe fattura (query_costi, ultimi_acquisti, trend, confronto), fornitori e importi delle scadenze (fw:4874-4879), titolo e descrizione libera degli appuntamenti (fw:4958-4963), descrizioni libere delle spese extra (fw:5058), nomi dei tag (fw:5149), Score Fornitori, rincari; in catena nomi sedi e gruppo e UUID. Nessuna anonimizzazione nel percorso chat (vedi F3-10). La riga sul briefing ('nomi di prodotti e fornitori sono sostituiti', :253-254) è vera solo per i bullet di prezzo.

**fix proposto.** Aggiornare informativa e tabella di compliance con le categorie reali: domanda dell'utente, nome di chi scrive, righe fattura e fornitori interrogati, scadenze, appuntamenti, spese annotate, tag, nomi dei punti vendita. Correggere la frase sul briefing ('i nomi nei segnali di prezzo').

**presidio proposto.** Estendere tests/test_privacy_policy_veritiera.py: per ogni strumento in _CHAT_TOOLS_SEDE e _CHAT_TOOLS_GRUPPO una categoria di dato dichiarata nella privacy (mappa nel test), così uno strumento nuovo senza dichiarazione fa fallire.

**gia presidiato da.** tests/test_privacy_policy_veritiera.py:220-233 verifica solo che OpenAI sia nominato come fornitore contattato, non cosa gli viene trasmesso.

**file e righe.** `apps/web/src/app/(legal)/privacy/page.tsx:229-255`; `docs/COMPLIANCE_GDPR.md:51-58`; `services/fastapi_worker.py:4078`; `services/fastapi_worker.py:4621`

### Verificato e trovato giusto

- _chat_risolvi_sede, estratta via AST ed eseguita, rifiuta (None) tutti questi input: '', '   ', None, 123, 0, True, lista, dict, UUID di una sede non in elenco ('9999…'), '[cliente]' (sottostringa di due sedi), 'su', 'i', '%', '*', '.', prefissi di UUID ('11111111', '1111'), nome+suffisso ('[cliente] NAVIGLI 2', '… Milano'), 'caffe centrale' senza accento, accento NFD, caratteri fullwidth, due sedi con lo stesso nome normalizzato. Accetta solo sedi dell'elenco: nome esatto con maiuscole e spazi o tab o NBSP diversi, id esatto con spazi attorno, sottostringa unica di 3 caratteri ('nav'). Con 'navigli' contro ['[cliente] NAVIGLI','Navigli'] vince l'esatta. Nessuna accettazione indebita.
- Dispatcher di catena _chat_esegui_tool_catena, estratto ed eseguito con gli strumenti stubbati: proponi_incasso, proponi_spesa, query_coperti (con e senza sede), query_personale, query_tag danno 'strumento sconosciuto' e non eseguono niente; sede 'rid-99' o assente dà errore con l'elenco dei nomi e non esegue niente; un argomento 'ristorante_id':'rid-99' passato dal modello arriva negli args ma lo strumento riceve ristorante_id='rid-1' dalla riga letta (e _chat_esegui_tool_sede non legge mai args['ristorante_id']).
- Percorsi della sede verso strumenti e query: vista sede = _resolve_ristorante_id dal token (fw:6135) per tutti gli strumenti di sede, fase F, prompt (home_kpi(authorization), _chat_top_cat_forn con p_user_id + p_ristorante_id, agenda per ristorante_id del token), _chat_nome_sede e _chat_noiva_escluso. query_coperti rilegge dal token (fw:5366) e get_coperti_analisi(authorization). proponi_* = sede del token, poi assistente.proponi, poi sede_scrivibile (UUID valido, user_id, attivo, non tecnica, verifica_sede_consentita: routers/assistente.py:276-297, 681). La Conferma /api/assistente/registra ricontrolla con sede_scrivibile l'id che arriva dal client (assistente.py:597). Catena: strumenti di sede solo tramite _chat_risolvi_sede su _chat_sedi_catena (user_id, attivo, non tecnica, sedi_operative del sotto-utente: fw:6006-6024). Strumenti di gruppo e prompt di catena: authorization, poi _resolve_gruppo (verifica_catena + user_id + almeno 2 sedi: gruppo.py:972-1019). Il client non manda mai un id sede (ChatRequest fw:3323-3336).
- Strumenti di sede eseguibili in catena: tutti filtrano il tenant. Per AST: query_costi, ultimi_acquisti, trend_prezzo, confronto_prezzi e appuntamenti hanno .eq('user_id') e .eq('ristorante_id'); scadenze usa get_documenti_scadenziario(user_id, rid); margini usa carica_margini_anno(user_id, rid).
- Gate all'esecuzione in vista sede: _esegui_tool rifiuta ogni nome non in _offerti (fw:6374), cioè la lista dopo gate di pagina, scheda fase F, settore e rimozione dei proponi_* senza card_conferma. In più _chat_esegui_tool_sede ricontrolla settore (fw:5916), permesso fase F (fw:5961) e rifiuta i proponi_* (fw:5975-5978). È provato da tests/test_chat_catena_sede.py:320-345, che esegue la closure vera di chat_ai (sb mock), e da tests/test_sql_chat_proposte.py:342-358 (Postgres vero: proponi da dispatcher condiviso o senza card, niente scritto).
- Gate all'esecuzione in catena: nomi_di_sede = strumenti offerti dopo i gate di pagina e settore; un nome fuori va al dispatcher di gruppo, che lo dichiara 'sconosciuto'. gruppo_margini_coperti e gruppo_spesa sono ricontrollati sulla scheda (fw:4104-4106 via _SCHEDA_DELLO_STRUMENTO_GRUPPO) e le colonne dei coperti tolte se spente. Prove: tests/test_chat_catena_sede.py:149-174 (dispatcher vero), :244-281 (closure vera di chat_ai: sede di un altro account rifiutata, query_coperti non offerto), tests/test_chat_catena_sede_sql.py (Postgres vero, due clienti).
- query_coperti in catena non può leggere la sede dal token: non è in _CHAT_TOOLS_SEDE_IN_CATENA (fw:6000-6003) e l'esecuzione dà 'strumento sconosciuto' (verificato eseguendo il dispatcher).
- Quota: catena con una sola sede rifiutata con 400 prima della RPC (fw:6159-6171), provato eseguendo chat_ai in tests/test_chat_catena_quota_non_consumata.py. I 403 (sotto-utente senza home o catena, piano free, catena spenta, chat della sede spenta) e il 400 vengono tutti prima della RPC (fw:6146-6214). I 429 della quota non inseriscono: la RPC fa RETURN prima dell'INSERT (migration 20261010135911:161,181,185 contro :189). Fail-closed: 503 se la RPC fallisce.
- Storico per vista (eseguito con node su lib/home-chat.ts vero): con una conversazione mista sede:X, sede:Y, catena e 'sede:', corpoRichiestaChat manda solo i messaggi della vista corrente (X: qX1,aX1,qX2,…; Y: qY1,aY1; catena: qC1,aC1; 'sede:' solo l'ultimo, qV2). parseConversazione scarta role 'system', content non stringa, vista assente o vuota, card malformate, e restituisce [] su '{', '{}', 'null', '[null,1,"a"]'. Coda tagliata a 16. conRisposta mette la risposta nella vista della domanda anche dopo un cambio sede. idPersona: titolare 'T', sotto-utente 'T:email'.
- Vista 'sede:' vuota: mandare solo l'ultimo messaggio è voluto e commentato (home-chat.ts:330-338) e provato (tests/test_home_chat_frontend.py:544-546). Effetto collaterale innocuo: a schermo vociDellaVista mostra tutte le voci 'sede:' insieme, quindi lo schermo ha più di ciò che il modello ricorda, solo nel caso raro di sede non risolta.
- Cambio sede a conversazione aperta: il client passa alla chiave sede:Y e manda solo lo storico di Y, ma il server risponde sulla sede del token. Per qualche secondo dopo il cambio può rispondere sulla sede precedente. È un compromesso dichiarato (fw:6173-6178) e fissato da tests/test_chat_vista_sede.py:192 (legge solo che ChatRequest non abbia sede_id). Il prompt nomina la sede; una card proposta in quella finestra porta ristorante_id e sede_nome della sede su cui scriverà, e la Conferma ricontrolla.
- Desktop e /m condividono la chiave sessionStorage per persona nello stesso tab (layout (app):91 e (mobile)/m/layout.tsx:89, stessa idPersona): stessa persona, stesse viste, card visibili in entrambi. Nessun problema. Logout: la conversazione resta in sessionStorage (il logout non la pulisce, app-sidebar.tsx:143), ma la chiave è per persona (home-chat.ts:364-369): un altro utente nello stesso tab non la legge. Residuo accettato: leggibile dagli strumenti del browser finché il tab è aperto.
- _anonymize_bullets ha un solo chiamante, il briefing (daily_briefing_service.py:1697); nessuna chiamata dal percorso chat. Lo dichiaro come verificato; la conseguenza sui documenti sta in F3-10 e F3-11.
- In catena con la scheda Scadenze o Prezzi di catena spenta (tab_off_catena_*), query_scadenze e confronto_prezzi di sede restano offerti se la pagina del PV è accesa. Non è un buco: sono gli stessi dati che l'account vede aprendo il PV, e CHAT_ASSISTENTE.md §5.3 dichiara i gate della vista PV.
- Due sedi con lo stesso nome normalizzato: l'enum le deduplica (fw:6057) e _chat_risolvi_sede restituisce None, quindi nessuna delle due è interrogabile per nome dalla catena. Scelta conservativa provata da tests/test_chat_catena_sede.py:53; è un limite di usabilità, non di isolamento.

### Non verificabile in sola lettura

- Quanto sono frequenti nei dati reali i casi di F3-06 (stesso prodotto in unità diverse da fornitori diversi negli ultimi 180 giorni) e di F3-07 (account con più di 30 documenti aperti): servirebbe il DB, escluso per il filone 3.
- Se il modello davvero divide per il fatturato lordo (F3-01) o sbaglia le somme (F3-07, F3-08): verificarlo richiede chiamate a OpenAI, vietate. I finding si basano sul testo del prompt e sul dato consegnato.
- Fuso orario effettivo del container Railway (F3-04): non letto da produzione. Si assume UTC come dichiarato nel codice (fw:46-47) e misurato dal test della quota (righe notturne su chat_usage_log).
- Lo storno dei crediti su un 502/504 reale e il contenuto di chat_usage_log dopo un guasto: richiederebbe una chiamata al worker o scritture.
- Quanto sono grandi i risultati reali di gruppo_spesa per gli account catena (numero di fornitori × sedi): stimato solo su dati sintetici.

## F1a quadrature catena A

### F1a-01 — Home: 100 € manuali in altri_costi_fb bastano a dichiarare «completo» settembre e il MOL esce verde al 100%

Filone 1 · bug vero · gravità alta · confidenza alta

**chi lo vede.** Home «I tuoi conti» (desktop e /m/briefing, stesso KpiBlock) della sede 0dca4d1f, mese mostrato oggi = Settembre 2026 (ultimo mese completo, worker:9926-9935). Anche la tabella Margini della stessa sede: la colonna Set non e' «senza costi» (meseSenzaCosti) e _mesi_senza_costi conta 4 mesi su 10 invece di 5.

**prova.** margini_mensili 2026/9 sede 0dca4d1f: fatturato_iva10 309.017,38 + altri 105.374,85 (lordo 414.392,23, netto 386.299,74), costi_fb_auto live (RPC costi_automatici_mensili) = nessuna riga per settembre (ultima fattura 30/06), altri_costi_fb = 100,00 (updated_at 06/10), spese 0, personale 0. _kpi_periodo (worker:9798-9868): fb = 0 + 100 + 0 = 100 → costi_mancanti = (414.392 > 0 and 100 <= 0) = False; has_data True; food_cost_pct = round(100/386.299,74*100,1) = 0,0; mol = 386.199,74 (100,0%). tintContiPV (lib/catena-confronti.ts:371-381): costi_mancanti false, incasso_fuori_norma assente → «verde». Il banner «Mancano le fatture costo» (kpi-block.tsx:101-114) e' condizionato a kpi.costi_mancanti → non appare. Le altre 3 sedi, stesso mese, stessa assenza di fatture ma altri_costi_fb = 0 → costi_mancanti true, giallo + banner. La voce Salute «Fatture caricate» (_costi_automatici_mese, worker:8458) guarda i soli costi AUTO → per la stessa sede e lo stesso mese dice che manca la merce: la stessa pagina si contraddice.

**numeri attesi vs mostrati.** Atteso: MOL giallo con banner «Mancano le fatture costo di settembre» (come le altre 3 sedi). Mostrato (dedotto dal codice): MOL 386.200 € in verde, Food cost 0%, nessun banner.

**fix proposto.** Non basta «fb > 0»: la soglia va resa relativa (es. fb < 5% del netto = costi mancanti) oppure il predicato deve guardare le sole fatture merce (costi auto + quote riparto F&B) escludendo altri_costi_fb, ma attenzione ai clienti che inseriscono tutta la merce a mano. Decisione di dominio per Mattia; in ogni caso le quattro gemelle (_kpi_periodo, _mesi_senza_costi, meseSenzaCosti, _costi_mese_per_sede) vanno mosse insieme e allineate a _costi_automatici_mese.

**presidio proposto.** Test su _kpi_periodo con riga {fatturato_iva10: 309.017, altri_costi_fb: 100} e costi auto vuoti: atteso costi_mancanti True (oggi False) e lo stesso caso su _mesi_senza_costi e meseSenzaCosti (esegui_ts); mutante: rimettere `fb <= 0` → rosso.

**gia presidiato da.** tests/test_margini_giudizio_dati_incompleti.py (test_una_quota_di_riparto_spese_non_basta_a_completare_il_mese: copre la quota SPESE, non un importo F&B minuscolo), tests/test_catena_confronti_frontend.py:687-696 (tintContiPV su costi_mancanti gia' deciso), tests/test_kpi_periodo_quote_riparto.py (somma, non soglia). Nessun test prova che 100 € su 386.000 € non completano il mese.

**file e righe.** `services/fastapi_worker.py:9798-9868 (_kpi_periodo, costi_mancanti = fatturato > 0 and fb <= 0 con fb che include altri_costi_fb)`; `apps/web/src/lib/catena-confronti.ts:371-381 (tintContiPV)`; `apps/web/src/app/(app)/dashboard/kpi-block.tsx:72-114`; `services/routers/margini.py:921-934 (_mesi_senza_costi su costi_fb_totali)`; `apps/web/src/lib/margini-aggregati.ts:256-259 (meseSenzaCosti)`; `services/fastapi_worker.py:8458-8500 (_costi_automatici_mese, solo auto)`

### F1a-02 — Spesa per PV (catena): la fattura ripartita che vive su un PV e' contata intera E come quote → 456,30 € doppi

Filone 1 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Catena → finestra «Spesa per PV» (gruppo_spesa_pivot + _righe_quote_gruppo), colonna del PV fd7ac484 e grand total, periodo che include gennaio 2026; Analisi Fatture del PV fd7ac484 (righe reali 456,30 + riga proiettata quota 114,08).

**prova.** L'account non ha una sede tecnica (ristoranti.sede_tecnica = false su tutte e 5). L'unico riparto (riparto_costi_catena gen 2026, importo 456,30, origine fattura IT08172050968_0ofr3.xml.p7m) ha le 2 righe (5,00 SERVIZI + 451,30 UTENZE) su fatture con ristorante_id = fd7ac484 e ripartita_su_gruppo = true; quote: 4 PV × (1,25 + 112,83) = 456,30. RPC gruppo_spesa_pivot (corpo live letto con pg_get_functiondef: nessun filtro su ripartita_su_gruppo) chiamata per gen 2026 sui 4 PV: fd7ac484 SERVIZI 5.975,70 e UTENZE 34.249,99; stessa somma senza righe ripartite: 5.970,70 e 33.798,69 (delta 5,00 + 451,30). gruppo.py:1448-1461 aggiunge poi le quote (114,08 per PV) → il grand total porta 456,30 due volte. costi_automatici_mensili (margini/Home) invece esclude le ripartite: li' e' corretto.

**numeri attesi vs mostrati.** Gen 2026, PV fd7ac484: atteso SERVIZI 5.970,70 + quota 1,25 e UTENZE 33.798,69 + quota 112,83; mostrato 5.975,70 + 1,25 e 34.249,99 + 112,83 (grand total +456,30).

**fix proposto.** Aggiungere `AND NOT COALESCE(f.ripartita_su_gruppo, FALSE)` in gruppo_spesa_pivot (e verificare gruppo_peso_categoria / gruppo_spreco_fb_categorie, stessa famiglia `totale_riga > 0`, non controllate qui); in Analisi Fatture del PV che ospita la fattura ripartita, escludere le righe reali quando esistono le proiettate (o marcare la riga come «ripartita, conteggiata via quota»).

**presidio proposto.** Test -m sql: fattura con ripartita_su_gruppo = true su un PV + quote sui PV → gruppo_spesa_pivot non la ritorna; mutante: togliere il filtro → rosso.

**gia presidiato da.** tests/test_gruppo_spesa_pivot_quote.py (quote dentro la colonna del PV, assume la fattura sulla sede tecnica). Nessun test col riparto su un PV.

**file e righe.** `supabase/migrations/20260912075621_oscura_fattura.sql:360-380 (gruppo_spesa_pivot senza NOT ripartita_su_gruppo)`; `services/routers/gruppo.py:1444-1461 (_righe_quote_gruppo aggiunte dopo la RPC)`; `services/fastapi_worker.py:10437-10448 (_build_fatture_base_query: nessun filtro ripartita) e :10608-10625 (proiettate aggiunte)`

### F1a-03 — «Spesa per PV» (catena) e «Spesa totale» (Analisi Fatture) sullo stesso periodo e sedi differiscono di 111.335,94 €: una scarta le righe negative, l'altra le nettizza

Filone 1 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** Catena → «Spesa per PV» (per categoria/fornitore) vs Analisi Fatture KPI «Spesa totale» di ogni PV; tutte e 4 le sedi con fatture dell'account.

**prova.** Periodo 01/01/2026→15/10/2026 (default di entrambe: Analisi anno_corrente gen→oggi; catena _periodo_da_query anno intero, ma non esistono righe oltre il 31/07). Replica SQL delle due definizioni. Catena (gruppo_spesa_pivot: totale_riga > 0, categoria <> 'Da Classificare', COALESCE(data_competenza,data_documento)) vs Analisi (/api/fatture/kpi: totale_riga <> 0, Da Classificare incluse, NOTE escluse, data_documento): 0dca4d1f 572.236,89 vs 553.914,91 (+18.321,98); 5444e918 569.856,03 vs 560.045,22 (+9.810,81); cc016821 705.730,79 vs 691.651,51 (+14.079,28); fd7ac484 1.695.570,45 vs 1.626.446,58 (+69.123,87). Totale +111.335,94 = righe negative scartate 122.398,82 (di cui in documenti TD04: 46.863,11 = 11.517,68 + 6.262,78 + 7.038,85 + 22.043,80; in fatture normali — sconti/abbuoni: 75.535,71 = 7.279,22 + 7.513,93 + 13.320,43 + 47.422,13) − Da Classificare positive escluse dalla catena 11.062,88 (474,92 + 3.965,90 + 6.280,00 + 342,06). Quadratura al centesimo per ogni sede. data_competenza mai diversa da data_documento (0 righe) e nessuna NOTE con importo > 0: le due basi di data non pesano. Note di credito: 106 documenti TD04 (20/17/18/51), totale_documento header 37.453,54 € (7.265,59 + 4.570,22 + 5.113,26 + 20.504,47), somma righe −35.237,13 (hanno anche 10 righe positive), segno_compensazione = −1 su 106/106.

**numeri attesi vs mostrati.** Stesse sedi, stesso periodo: catena 3.543.394,16 vs Analisi (somma 4 PV) 3.432.058,22.

**fix proposto.** Decidere una definizione sola di «spesa»: o la pivot nettizza (filtro `totale_riga <> 0` e somma con segno, come Analisi) oppure la catena dichiara «al lordo di note di credito e sconti (X €)». Da Classificare: o anche Analisi le tiene fuori dal KPI «Spesa» (mostrandole a parte) o la catena dichiara l'esclusione.

**presidio proposto.** Test -m sql su gruppo_spesa_pivot con una riga −50 e una +100 dello stesso PV: atteso 50 (se si nettizza) — mutante: rimettere `> 0` → 100 → rosso. In parallelo un test su get_fatture_kpi e sulla pivot con lo stesso dataset che asserisce l'uguaglianza delle due «spese».

**gia presidiato da.** Nessuno: MAPPA_NUMERI §D conferma che nessun test fissa i totali di /api/fatture/kpi ne' le NC in Spesa per PV; tests/test_gruppo_spesa_pivot_quote.py copre solo le quote.

**file e righe.** `supabase/migrations/20260912075621_oscura_fattura.sql:374 (AND f.totale_riga > 0)`; `services/routers/fatture.py:386-396 (_calc: rows_nonzero, somma netta)`; `services/fastapi_worker.py:10558-10600 (_fetch_fatture_rows su data_documento, Da Classificare incluse)`; `services/routers/gruppo.py:1084-1105 (_periodo_da_query default anno intero)`

### F1a-04 — 19 header fatture_documenti senza righe (dic 2025, 59.368 €) fanno comparire «Dicembre 2025 (19 fatture)» nel filtro periodo di Analisi Fatture su un mese che non ha righe

Filone 1 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Analisi Fatture → filtro periodo «mese specifico» (filtri-periodo.tsx:131 «{label} ({count} fatture)») del PV fd7ac484; lo scadenziario non li mostra (RPC su fatture).

**prova.** fatture_documenti attivi dell'account: 2.601; documenti distinti in fatture attive: 2.582. I 19 in piu' sono tutti di fd7ac484, data_documento 09–31/12/2025, totale_documento 59.368,37 €, e NON hanno nessuna riga in fatture (nemmeno soft-deleted: con_righe_cancellate = 0); min(data_documento) delle righe di fd7ac484 = 01/01/2026. /api/fatture/mesi-disponibili (routers/fatture.py:326-360) conta fatture_documenti → lista «Dicembre 2025, 19»; selezionandolo /api/fatture/kpi e articoli (su fatture) tornano vuoti.

**numeri attesi vs mostrati.** Atteso: nessun «Dicembre 2025» nel filtro (0 righe). Mostrato: «Dicembre 2025 (19 fatture)».

**fix proposto.** Costruire i mesi disponibili dalle righe (fatture, deleted_at IS NULL) o da una JOIN con fatture; e capire perche' 19 header di dicembre sono rimasti senza righe (upload interrotto dopo l'insert dell'header?) — eventuale pulizia e' una scrittura, fuori da questo audit.

**presidio proposto.** Test su get_mesi_disponibili con un header senza righe: il mese non compare (o compare con count 0); mutante: tornare a contare fatture_documenti → rosso.

**gia presidiato da.** Nessuno trovato su /api/fatture/mesi-disponibili.

**file e righe.** `services/routers/fatture.py:326-360 (get_mesi_disponibili su fatture_documenti)`; `apps/web/src/app/(app)/analisi-fatture/filtri-periodo.tsx:131`

### F1a-05 — Home: «Fatturato» lordo IVA e MOL su netto nella stessa card, base ancora non dichiarata (447.728 − 0 − 0 − 0 = 416.798 e' ancora cosi')

Filone 1 · stessa etichetta per grandezze diverse · gravità bassa · confidenza alta

**chi lo vede.** Home «I tuoi conti» (desktop e /m), tutte le sedi; oggi evidente su 3 sedi su 4 che hanno settembre a costi 0.

**prova.** cc016821 settembre 2026 (mese mostrato oggi): fatturato = 284.781,06 + 99.057,77 = 383.838,83 (lordo, _kpi_periodo worker:9810); netto = 284.781,06/1,10 + 99.057,77 = 357.949,64; F&B 0, spese 0, personale 0 → MOL 357.949,64. Scarto 25.889,19 = IVA scorporata. kpi-block.tsx: etichette «Fatturato» (:124) e «MOL (margine)» (:83); grep di «lordo|netto|IVA» nel file: 0 occorrenze. Dal 17/09 il MOL e' pero' giallo con banner «Mancano le fatture costo di settembre» (costi_mancanti true su questa sede).

**numeri attesi vs mostrati.** Mostrato: Fatturato 383.839 €, −0%, −0 €, −0 €, MOL 357.950 €. Manca: IVA 25.889 €.

**fix proposto.** Sottotitolo sulla tessera Fatturato («IVA inclusa · netto 357.950 €») o MOL dichiarato «su netto». Margini lo fa gia' (kpi-bar.tsx:219: «Fatturato Netto» con «lordo …» sotto).

**presidio proposto.** Test sul testo della tessera (via helper in lib) che richiede la dichiarazione della base quando fatturato ≠ netto.

**gia presidiato da.** Nessuno sulle etichette della card (test_home_card_compatte_frontend copre i blocchi, non la base).

**file e righe.** `apps/web/src/app/(app)/dashboard/kpi-block.tsx:83-85,122-127`; `services/fastapi_worker.py:9806-9812`

### F1a-06 — «Prodotti da controllare» (needs_review), «€ esclusi dai margini» (Da Classificare, netto) e chip «Solo da verificare» sono tre popolazioni con etichette vicine

Filone 1 · stessa etichetta per grandezze diverse · gravità bassa · confidenza media

**chi lo vede.** Home → Salute voce «Righe classificate» e briefing (esclusi_importo); Analisi Fatture → chip «Solo da verificare» + KPI; sede cc016821 (e le altre 3).

**prova.** cc016821 oggi: righe needs_review = 156, somma 14.286,41 €, descrizioni distinte 89 (worker:9596-9611 conta le descrizioni distinte needs_review → «89 prodotti da controllare»); righe categoria = 'Da Classificare' = 56, somma NETTA 582,02 € (= +6.280,00 − 5.697,98; _card_da_classificare worker:8533 somma con segno), 37 descrizioni distinte; il chip «Solo da verificare» di Analisi Fatture (routers/fatture.py:419: needs_review) mostra 156 righe / 14.286,41 €. Il «101 prodotti / 19.050 €» vs «100 / 582 €» del 16/09 e' la stessa coppia (needs_review vs Da Classificare) con dati di allora. Le 56 righe Da Classificare sono tutte needs_review (54 su 56 con importo ≠ 0 + 2 a zero), quindi la seconda e' un sottoinsieme della prima.

**numeri attesi vs mostrati.** Home: 89 prodotti / 582 € ; Analisi «Solo da verificare»: 156 righe / 14.286 € / 89 prodotti.

**fix proposto.** Dichiarare le due grandezze: «N prodotti da controllare, di cui M senza categoria: X € netti (Y € di acquisti, Z € di storni) fuori dai margini». L'importo netto 582 € nasconde 6.280 € di acquisti esclusi.

**presidio proposto.** Test sul testo della voce Salute/briefing che, con righe needs_review classificate e righe Da Classificare, nomina entrambe le cifre.

**gia presidiato da.** tests/test_home_card_da_classificare.py (predicato della card, non l'accostamento), nessun test fissa i KPI del chip da verificare.

**file e righe.** `services/fastapi_worker.py:9596-9618 (da_controllare = descrizioni distinte needs_review)`; `services/fastapi_worker.py:8533-8575 (_card_da_classificare: categoria = Da Classificare, somma con segno)`; `services/routers/fatture.py:418-420 (solo_da_verificare = needs_review)`; `apps/web/src/app/(app)/analisi-fatture/articoli-tab.tsx:410 («Solo da verificare»)`

### F1a-07 — Analisi e Tag: «Media periodo» (media semplice dei prezzi giornalieri) e «Prezzo medio / Rispetto alla media» (ponderata spesa/quantita') sono due formule

Filone 1 · stessa etichetta per grandezze diverse · gravità bassa · confidenza alta

**chi lo vede.** Analisi e Tag → grafico «Trend prezzi nel periodo» (Media periodo = trend.prezzo_medio_periodo) vs tabella Fornitori (colonna «Prezzo medio», intestazione «Rispetto alla media» = aggregati.prezzo_medio_tag) e KPI «Prezzo medio ponderato»; l'account ha 13 tag custom e 3 di gruppo.

**prova.** Esecuzione delle funzioni pure (services.tag_analytics_service, streamlit mockato, nessun client) su 2 righe KG: 01/03 10 kg a 9 € (90 €), 02/03 1 kg a 11 € (11 €): _compute_trend → prezzo_medio_periodo = 10,0 (media dei prezzi per giorno, tag_analytics_service.py:255); _compute_fornitori → prezzo_medio_tag = 9,1818 (101/11, :347); _compute_kpi → prezzo_medio_ponderato = 9,1818. Entrambe giuste, nomi vicini. Il «7,66 vs 7,83» del 16/09 e' questa differenza.

**numeri attesi vs mostrati.** Stesso tag, stessa risposta: Media periodo 10,00 €, Rispetto alla media 9,18 €.

**fix proposto.** Rinominare «Media periodo» in «Media dei prezzi giornalieri» (o usare la ponderata anche nel trend: nota che prezzo_medio_periodo alimenta price_impact_service, quindi cambiarla sposta gli alert prezzi della Home).

**presidio proposto.** Test con due giorni a quantita' diverse (10 kg / 1 kg) che documenti la differenza voluta (o, se si unifica, l'uguaglianza); il mutante «media semplice → ponderata» oggi sopravvive al test esistente.

**gia presidiato da.** tests/test_tag_audit_fix.py::test_kpi_trend_e_fornitori_concordano_su_unita_miste asserisce kpi == trend == forn ma su un dataset con un solo acquisto per giorno (dove le due formule coincidono per costruzione); tests/test_tag_analytics_service.py:92.

**file e righe.** `services/tag_analytics_service.py:243-273 (_compute_trend: mean dei PrezzoTag giornalieri)`; `services/tag_analytics_service.py:340-356 (_compute_fornitori: spesa_tot/qta_tot)`; `apps/web/src/app/(app)/analisi-e-tag/analisi-e-tag-client.tsx:206,1032-1043`

### F1a-08 — margini_mensili: i totali salvati (costi_fb_auto, costi_spese_auto, mol, mol_perc) sono stantii o a zero, ma nessuna pagina li legge

Filone 1 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuna superficie: Home, Margini, catena, chat e briefing ricalcolano dai componenti. Resta un rischio latente per chi aprira' GET /api/margini (margini.py:170-216, fetchMarginiAnno senza chiamanti).

**prova.** margini_mensili 2026: costi_fb_auto/costi_spese_auto = 0 su tutte le righe di 0dca4d1f, 5444e918, cc016821 (che hanno costi live mar→lug: es. cc016821 mag F&B 153.261,31) e su fd7ac484 da maggio (live mag 193.744,76, giu 163.420,49, lug 129.003,02). mol salvato fd7ac484 mag e giu = 280.923,99 con mol_perc 100,00; ricalcolo live: mag 186.878,67 (39,1%), giu 212.635,37 (42,9%). fatturato_netto salvato invece coincide col ricalcolo su tutte le righe controllate. Lettori: grep su services — chat (worker:3812-3891) legge solo fatturato/personale/altri_costi_spese; home_kpi, margini analisi/kpi, gruppo ricalcolano; riparto_quote_mensili (corpo live) riscrive `mol` partendo dai costi_*_auto stantii quando gira.

**numeri attesi vs mostrati.** n/a (non mostrati).

**fix proposto.** Nessuno urgente. Se si vuole chiudere il rischio: rimuovere GET /api/margini e fetchMarginiAnno, oppure far ricalcolare i costi_*_auto nello snapshot al salvataggio.

**presidio proposto.** Presidio statico: nessun .ts/.tsx chiama fetchMarginiAnno (o rimozione).

**gia presidiato da.** tests/test_costi_auto_fatture_mol.py e test_margini_endpoint_rpc (ricalcolo live), nessuno sul fatto che lo snapshot non sia letto.

**file e righe.** `services/routers/margini.py:170-216`; `apps/web/src/lib/margini.ts:76-77 (fetchMarginiAnno, nessun chiamante)`; `services/fastapi_worker.py:9833-9842 (MOL ricalcolato, mai letto)`

### Verificato e trovato giusto

- (a) «Costi gestione» non esiste piu' a video: kpi-bar.tsx:219-224 «Spese Generali», gauge calcolo-tab.tsx:1063 «Spese Generali», waterfall :1100 «− Spese Generali + Personale» (cifra combinata, etichetta che lo dice); grep «Costi gestione|Costi Gestione» su apps/web/src = solo commenti e demo.
- (b) Scadenziario sede cc016821 oggi (regole computeKpi replicate in SQL, oggi 15/10/2026): 581 documenti, 0 oscurate, 18 NC (12 scadute, 5.113,26 €), 0 pagate; Da pagare 563 / 784.224,60 €; Scadute 438 / 665.885,04 €; Senza scadenza 125 / 118.339,56 €; future 0. Scadute + senza scadenza = Da pagare al centesimo: «Scadute > Da pagare» non e' piu' possibile, le senza-scadenza sono dentro Da pagare e contate anche a parte (lib/scadenziario.ts:313-379). Nessuna regola fornitore su questa sede (fornitori_pagamenti_config: 0 su cc016821) → scadenza_effettiva salvata = live.
- (c) Contatore «426 su 581» chiuso: contaDaPagare (lib/scadenziario.ts:118) e chiaviSelezionaTutte (:158) usano gli stessi tre predicati; oggi entrambi = 563 (581 − 18 NC − 0 pagate − 0 oscurate). Presidio: tests/test_scadenziario_contatore_frontend.py (test_le_note_di_credito_non_gonfiano_il_contatore, TestSelezionaTutte).
- (f) Vista gruppo: 2.582 documenti attivi = 2.582 file_origine distinti (0 file_origine su piu' sedi: la selezione per solo file_origine non ha collisioni); 106 NC, 0 oscurate, 15 pagate → selezionabili 2.461 = contaDaPagare = Seleziona tutte; la striscia per sede (aggregaPerSede :775-792) esclude NC/pagate/oscurate: stessa popolazione.
- (e) I tre periodi sono dichiarati: Home meta = periodo_label (kpi-block.tsx:77; oggi «Settembre 2026»), catena = periodo_label di _label_anno_parziale (sintesi-catena.tsx:155-179), Margini = preset anno_corrente a video + per cc016821 «Nessun giudizio: 5 mesi su 10 … non ha costi» (gen, feb, ago, set, ott senza F&B; margini.py:1398-1420) con MOL% 70,9 che resta a video per decisione di Mattia; catena: ranking margine_perc None per i PV incompleti (gruppo.py:1247-1262) e livello_dati «food» (settembre senza costi su tutti i PV) → MOL in ambra, non verdetto.
- costi_automatici_mensili (SQL, STABLE, letta con pg_get_functiondef: nessuna scrittura) = replica indipendente su fatture (deleted_at, NOT oscurata, categoria <> Da Classificare, NOT ripartita, COALESCE data, 5 CATEGORIE_SPESE_GENERALI, NOTE escluse): 10 celle mag/giu/lug × 4 sedi identiche al centesimo (es. cc016821 mag F&B 153.261,31 / spese 26.099,84; fd7ac484 lug 129.003,02 / 122.482,94). _calcola_costi_auto_per_mese (worker:10853-10905) ha gli stessi filtri (.neq Da Classificare, .neq ripartita, oscurata False, COALESCE via or_).
- Ricalcolo mag/giu/lug 2026 per sede (lordo / netto / F&B / spese / personale / MOL / MOL%): 0dca4d1f 1.337.353,71 / 1.247.232,93 / 257.748,01 / 64.054,71 / 120.000 / 805.430,21 / 64,6% (lug senza fatture e senza personale); 5444e918 1.333.047,10 / 1.238.106,27 / 273.865,92 / 44.304,71 / 120.000 / 799.935,64 / 64,6% (idem lug); cc016821 1.225.833,86 / 1.143.010,80 / 367.664,61 / 108.620,70 / 120.000 / 546.725,49 / 47,8% (lug personale 0); fd7ac484 1.537.798,46 / 1.426.255,76 / 488.918,27 / 216.492,79 / 180.000 / 540.844,70 / 37,9%. Gruppo: 5.434.033,13 / 5.054.605,76 / 1.388.196,81 / 433.472,91 / 540.000 / 2.692.936,04 / 53,3%. Mese per mese (MOL%): 0dca mag 39,7 giu 52,8 lug 100; 5444 42,4 / 52,8 / 100; cc01 39,2 / 39,3 / 65,5; fd7 39,1 / 42,9 / 31,2. Apr-giu (unici mesi completi): 42,0 / 41,9 / 37,8 / 39,8.
- Gen→ott 2026 (catena overview e Margini anno corrente, nessun override ricavi_modalita_mensile: 0 righe per le sedi): netto 3.871.221,28 / 3.726.768,86 / 3.607.072,22 / 4.477.159,18; MOL% 76,4 / 75,3 / 70,9 / 54,2; gruppo netto 15.682.221,54, MOL 10.746.012,79 → 68,5% (ambra: livello «food»). Home oggi = Settembre 2026 su tutte e 4 le sedi (fatturato > 0 → has_data), costi_mancanti true su 3 (netto 357.949,64 / 382.438,62 / 466.450,51, MOL = netto), sede 0c23548c senza margini ne' fatture → card vuota.
- Da Classificare: 133 righe (13 / 46 / 56 / 18), importi netti 474,92 / 944,89 / 582,02 / −1.302,36 €, 0 oscurate, 0 ripartite; fuori da F&B e spese in RPC (f.categoria <> 'Da Classificare') e nel worker (.neq). Riparto: le sole quote dell'account sono gen 2026 (SERVIZI 1,25 + UTENZE 112,83 per PV = 456,30), nessuna quota Da Classificare; corpo live di riparto_quote_mensili contiene `q.categoria <> 'Da Classificare'` nel FILTER di q_spese (commit d9a33fce applicato sul DB).
- Note di credito nei margini: 106 TD04, fatture_documenti.segno_compensazione = −1 su tutti; le righe NC sono negative in fatture (somma −35.237,13) e entrano sottratte nei costi auto; lo scadenziario le esclude (is_nota_credito, documenti_service.py:851) e la vista mensile ne mostra la spiegazione (:957).
- margini_mensili.fatturato_netto salvato coincide col ricalcolo iva10/1,10 + iva22/1,22 + altri su tutte le righe mag/giu/lug/set delle 4 sedi (es. cc016821 set 357.949,64).
- Chat (worker:3812-3891) legge da margini_mensili solo fatturato_*, costo_* e altri_costi_spese: non eredita il mol salvato stantio.
- Scadenziario, totale del documento: 1 documento su 581 di cc016821 senza header (fallback a somma righe, documenti_service.py:812-815); pivot/Analisi non ne risentono.

### Non verificabile in sola lettura

- scadenza_effettiva live (_applica_regole_fornitore con regole fornitore) non eseguibile senza client: per cc016821 non ci sono regole (equivalenza con il valore salvato garantita), ma per fd7ac484 (4 regole attive: 2 rid, 30gg, 60gg su 234 documenti) e 0dca4d1f (1 regola 60gg, 4 documenti) i KPI scadenze non sono stati ricalcolati.
- Resa a video non osservata (niente browser/screenshot): i valori «mostrati» sono dedotti da dati + codice; in particolare dove la Home del 16/09 mostrava «582 €» (il campo esclusi_importo non e' reso da nessun .tsx: grep 0 in apps/web/src; probabilmente testo del briefing).
- Analisi e Tag su un tag reale dei 13 dell'account: la normalizzazione descrizione_key (_normalize_custom_tag_key) e le conversioni di unita' non sono replicabili in SQL; provata la divergenza delle due medie per costruzione con le funzioni pure.
- Il «430.340 Da pagare (filtro)» del 16/09 non e' ricostruibile: i dati sono cambiati (pagate/nuovi documenti) e il filtro usato allora non e' documentato.
- Origine dei 19 header orfani di dicembre 2025 (upload interrotto? import manuale?) e dei 100 € di altri_costi_fb di settembre su 0dca4d1f: dati di produzione, nessuna scrittura o indagine sui log.
- gruppo_peso_categoria e gruppo_spreco_fb_categorie (stessa famiglia `totale_riga > 0`, senza filtro ripartita): non chiamate, solo segnalate come da controllare.

## F2b sotto-utenti frontend

### F2b-1 — /m/diario e /m/turni aperte al sotto-utente con la sola pagina Strumenti: tutte le chiamate dati rispondono 403

Filone 2 · bug vero · gravità media · confidenza alta

**chi lo vede.** PWA /m (bottom-nav «Agenda» e «Movimenti»): qualunque sotto-utente con 'workspace' acceso e 'agenda' spenta. Un sotto-utente con la sola pagina Strumenti atterra proprio lì (primaTabMobile → /m/diario). Account toccati non misurati: il filone è solo codice, senza DB.

**prova.** Eseguito con node lib/sotto-utente.ts su {sotto_utente:true, pagine:['workspace']}: vedeTabMobile('/m/diario') = true, vedeTabMobile('/m/turni') = true, tabMobileNascoste = ['/m/briefing','/m/chat'], primaTabMobile = '/m/diario'. Le 20 rotte che chiamano mobile-diario.tsx (:101,:285,:320), mobile-spese.tsx (:113,:230,:262), mobile-incassi.tsx (:118,:231,:270) e mobile-turni.tsx (:210,:358,:368,:424,:704,:712,:876-879,:922) le ho estratte da services/permessi_rotte.py con ast e passate alla stessa regola di rotta_consentita (:339-348). Esito: 0 su 20 consentite con {workspace}; 20 su 20 con {agenda}; 3 su 20 con {workspace,margini} (solo /api/ricavi/giornalieri). PAGINE_PER_ROTTA dà _p(A) a workspace/diario, spese, personale e dipendenti (:154-184) fin dal primo commit 46ab02a6. Il commento di sotto-utente.ts:63-64 («che il worker apre con Agenda oppure Strumenti») è quindi falso. ha_pagina(user,'agenda') vuole pagine['agenda'] is True (sotto_utenti_service.py:241-251): non c'è nessun alias workspace→agenda.

**fix proposto.** In vedeTabMobile, TAB_MOBILE_AGENDA va con pagine.includes('agenda') soltanto, allineato a PAGINE_PER_ROTTA. Si corregge anche il commento di :63-64. In alternativa si aggiunge W alle rotte workspace/diario|spese|personale, ma vorrebbe dire dare in più al sotto-utente: da scartare.

**presidio proposto.** Correggere tests/test_sotto_utente_frontend.py:95: oggi asserisce il comportamento sbagliato (_nascoste(['workspace']) == ['/m/briefing','/m/chat']); deve diventare tutte e quattro le tab nascoste. Aggiungere poi un test di coerenza TS↔Python: per ogni tab mobile visibile con un insieme di pagine, le rotte che il suo .tsx chiama devono essere consentite da PAGINE_PER_ROTTA con quelle pagine.

**gia presidiato da.** Nessun presidio. tests/test_sotto_utente_frontend.py:95 fissa il comportamento errato; test_nessun_redirect_porta_alla_pagina_negata controlla solo i cicli di redirect, non i 403.

**file e righe.** `apps/web/src/lib/sotto-utente.ts:62-76`; `apps/web/src/lib/sotto-utente.ts:83-88`; `services/permessi_rotte.py:99-102`; `services/permessi_rotte.py:153-184`; `apps/web/src/app/(mobile)/m/bottom-nav.tsx:18-19`; `apps/web/src/app/(mobile)/m/diario/page.tsx:9`; `apps/web/src/app/(mobile)/m/turni/page.tsx:10`; `tests/test_sotto_utente_frontend.py:95`

### F2b-2 — Sotto-utente con Catena ma senza Home: «apri il punto vendita» lo riporta in /catena, e su /m «Vista catena» porta a una pagina di sede con l'intestazione «Tutti i punti vendita»

Filone 2 · bug vero · gravità media · confidenza alta

**chi lo vede.** Desktop, sidebar in vista catena (scelta di una sede) e /catena (pulsante «Apri PV» della sintesi). Mobile, menu ⋮ → «Vista catena». Tocca i sotto-utenti con pagine {catena, …} senza 'home': combinazione consentita da valida_permessi e dal pannello admin. Account non misurati: filone solo codice.

**prova.** Eseguito con node su {sotto_utente:true, num_sedi:2, pagine:['catena','analisi_fatture']}: haHome=false, haCatena=true, primaPaginaAbilitata()= '/catena'. app-sidebar.tsx:236, quando inChain, fa router.push('/dashboard') dopo cambiaSedeEAttendi; sintesi-catena.tsx:358/:411 fa vaiAlPV(id) con page='/dashboard'. /dashboard chiama requireHome (page-guard.ts:39-43) → redirect(primaPaginaAbilitata) = '/catena', e la sidebar riscrive il cookie 'chain' (:202-206). In vista catena la sidebar mostra solo le voci di catena (:282-321), non visibleNav: dalla UI il sotto-utente non arriva alle pagine di sede, salvo un avviso con action_page o un URL scritto a mano. Su mobile header-menu.tsx:68-73 scrive 'chain' e va a /m/briefing; requireTabMobile reindirizza a primaTabMobile ('/m/diario' con agenda, altrimenti '/m/impostazioni'). Il layout (m/layout.tsx:73,:102) calcola inChain = haCatena && cookie!='pv' e scrive «Tutti i punti vendita» sopra dati della sola sede attiva. valida_permessi (sotto_utenti_service.py:304-356) non vieta catena senza home.

**fix proposto.** Il drill-down catena→PV deve atterrare su una pagina di sede che la persona ha: haHome ? '/dashboard' : prima pagina di PAGINE_IN_ORDINE accesa. Serve una variante di primaPaginaAbilitata che salti il ramo catena, usata da handleCambiaSede e vaiAlPV. Su /m: «Vista catena» nascosta quando !haHome (la Home di catena mobile sta in /m/briefing), oppure inChain del layout legato anche a haHome. In alternativa il pannello admin rifiuta catena senza home.

**presidio proposto.** Test node su lib/sotto-utente: per ogni combinazione con haCatena && !haHome, la destinazione del drill-down a un PV non è '/catena' né '/dashboard'. Va provato per mutazione rimettendo '/dashboard'.

**gia presidiato da.** Nessun presidio. test_nessun_redirect_porta_alla_pagina_negata (tests/test_sotto_utente_frontend.py:111-130) esclude solo i cicli verso la pagina negata, e qui il rimbalzo è verso una pagina permessa.

**file e righe.** `apps/web/src/components/nav/app-sidebar.tsx:233-237`; `apps/web/src/app/(app)/catena/sintesi-catena.tsx:358-372`; `apps/web/src/app/(app)/catena/sintesi-catena.tsx:411`; `apps/web/src/lib/page-guard.ts:39-43`; `apps/web/src/lib/sotto-utente.ts:51-54`; `apps/web/src/app/(mobile)/m/header-menu.tsx:68-73`; `apps/web/src/app/(mobile)/m/layout.tsx:73`; `apps/web/src/app/(mobile)/m/layout.tsx:102`

### F2b-3 — Il sotto-utente vede «Configura assistente» (Home e Home di catena), ma il salvataggio è vietato dal worker e il messaggio dice «Riprova»

Filone 2 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** /dashboard (sotto-utente con Home) e /catena (sotto-utente con Catena). Account non misurati.

**prova.** dashboard/page.tsx:45 rende <ConfigAssistente> a chiunque abbia config. config-assistente.tsx:64 fa POST /api/home/config, che sta in ROTTE_VIETATE (permessi_rotte.py:290) → 403; su !res.ok il toast (:78) dice «Non sono riuscito a salvare le impostazioni. Riprova.». Stessa cosa in sintesi-catena.tsx:383 → config-assistente-catena.tsx:77 POST /api/gruppo/assistant-config, vietata (permessi_rotte.py:292), toast :92 «Riprova». Né i due componenti né le pagine controllano sotto_utente (grep 'sotto_utente' in apps/web/src: nessun uso in dashboard/catena/config-*). Il dialog mostra anche le preferenze del titolare: nome referente, soglia alert, giorni di chiusura, interruttore chat.

**fix proposto.** Non rendere ConfigAssistente/ConfigAssistenteCatena quando session.user.sotto_utente; in alternativa, su 403 un messaggio «Impostazione dell'account: la cambia il titolare» come già fa articoli-tab per il riparto.

**presidio proposto.** Funzione pura in lib (es. mostraConfigAssistente(user)) testata con node: false per sotto_utente, true per il titolare.

**gia presidiato da.** Nessun presidio. tests/test_catena_config_guardia_salva.py riguarda il blocco del Salva dopo un caricamento fallito, non i sotto-utenti.

**file e righe.** `apps/web/src/app/(app)/dashboard/page.tsx:45`; `apps/web/src/app/(app)/dashboard/config-assistente.tsx:64-78`; `apps/web/src/app/(app)/catena/sintesi-catena.tsx:383`; `apps/web/src/app/(app)/catena/config-assistente-catena.tsx:77-92`; `services/permessi_rotte.py:290-292`

### F2b-4 — TTS: il saluto (col nome della persona) e la narrativa del briefing con le cifre vanno a translate.google.com, che non è fra i sub-responsabili, e la route accetta qualunque cookie non vuoto

Filone 2 · bug vero · gravità media · confidenza media

**chi lo vede.** Chi preme «Ascolta» nel riquadro assistente: Home desktop (riquadro-assistente.tsx:81), /m/briefing (mobile-briefing.tsx:113) e la Home di catena mobile (mobile-catena.tsx:87). Tutti gli account con briefing, titolari e sotto-utenti.

**prova.** api/tts/route.ts:54-56 controlla solo che il cookie oneflux_session esista: nessuna verifySession, il valore è libero. :58-71 prende q (fino a 600 caratteri) e lo manda in GET a https://translate.google.com/translate_tts, endpoint non ufficiale. ascolta-button.tsx:68 passa testo = `${briefing.saluto}. ${briefing.narrativa}`. Il saluto è _saluto_per_ora(nome) (fastapi_worker.py:6434), con nome = user['nome_referente'] (:9326), che per un sotto-utente è il suo nome (sotto_utenti_service.sovrapponi). La lista dei sub-responsabili della privacy ((legal)/privacy/page.tsx:172-210: Supabase, OpenAI, Brevo, Vercel, Railway) non nomina Google: grep -i 'google' su app/(legal) → 0 risultati. Inoltre, con un cookie qualsiasi, la route resta un proxy TTS aperto verso Google.

**fix proposto.** Validare la sessione (verifySession, status 'ok'). Decidere se tenere il TTS di Google: se resta, va dichiarato nella privacy, e senza nome nel testo inviato; in alternativa solo speechSynthesis del dispositivo, già presente come ripiego in ascolta-button.tsx:45-51.

**presidio proposto.** Estendere tests/test_regole_dominio_guardia.py (ROUTE_NON_PROXY_DICHIARATE già elenca tts) con un test che esegua la logica di auth della route: cookie inventato → 401. Più un controllo che ogni host esterno chiamato da app/api compaia nella privacy.

**gia presidiato da.** tests/test_regole_dominio_guardia.py:522-534 dichiara la route come non-proxy, ma non ne verifica né l'autenticazione né i destinatari.

**file e righe.** `apps/web/src/app/api/tts/route.ts:53-71`; `apps/web/src/components/ascolta-button.tsx:68`; `apps/web/src/app/(legal)/privacy/page.tsx:172-210`; `services/fastapi_worker.py:6434`; `services/fastapi_worker.py:9326`

### F2b-5 — Le guardie di pagina sono fail-open quando la sessione non è 'ok', e sulla navigazione client il layout (app) non gira: le tab spente dall'admin tornano visibili

Filone 2 · bug vero · gravità bassa · confidenza media

**chi lo vede.** Tutte le pagine con requirePagina, requirePaginaConTab, requireHome, requireCatena e requireTabMobile, in navigazione SPA, quando /api/auth/me va in timeout o dà 5xx due volte ('unavailable') oppure il token è appena stato revocato ('invalid'). Titolari e sotto-utenti.

**prova.** page-guard.ts:24, :41, :47 e :56 fanno return se session.status !== 'ok'. Il commento :16-20 assume che il layout giri prima, ma la documentazione di Next 16.2.6 inclusa nel repo (apps/web/node_modules/next/dist/docs/01-app/02-guides/authentication.md:1350) dice che i layout «don't re-render on navigation». Con Link (sidebar) l'(app)/layout.tsx:47-76 non rifà quindi il controllo. Eseguito con node lib/tab-flags: con sessione ok e pagine ['prezzi','tab_off_prezzi_score'], risolviTab(…,'score') = 'variazioni' e tabAttive = [variazioni,sconti,nc]; con sessione non ok (pagine=null, page-guard.ts:96), risolviTab(null,'prezzi','score') = 'score' e tabAttive = [variazioni,sconti,nc,score]. Le tab spente esistono solo nel frontend (il worker non le controlla), quindi /api/prezzi/score-fornitori risponde ai dati. Con 'invalid' la pagina si rende con blocchi vuoti (il worker dà 401) invece di andare al login: in apps/web/src non c'è una gestione globale del 401. I dati delle pagine non consentite restano protetti dal 403 del worker.

**fix proposto.** Nelle guardie: 'invalid' → redirect('/login'); 'unavailable' → la pagina non si rende (throw o un componente di riprova), invece di proseguire con pagine=null.

**presidio proposto.** Estrarre in lib la decisione delle guardie (status, user, flag) → {passa|404|redirect:x} e testarla con node: status 'unavailable' e 'invalid' non devono dare 'passa'. Provare per mutazione rimettendo il return.

**gia presidiato da.** Nessun presidio. tests/test_page_guard_tab_frontend.py prova solo risolviTab con sessione valida.

**file e righe.** `apps/web/src/lib/page-guard.ts:16-28`; `apps/web/src/lib/page-guard.ts:39-58`; `apps/web/src/lib/page-guard.ts:94-100`; `apps/web/src/app/(app)/layout.tsx:47-76`; `apps/web/src/lib/auth.ts:96-120`

### F2b-6 — lib/fatture.ts mette in cache 60 s mesi-disponibili e categorie con chiave sul token: dopo il cambio sede si vedono quelli della sede precedente

Filone 2 · bug vero · gravità bassa · confidenza media

**chi lo vede.** /analisi-fatture (selettore mesi, elenco categorie e «usate»), negli account multi-sede, titolari e sotto-utenti con più sedi, fino a 60 s dopo cambia-sede. Con sedi di settore diverso (retail/ristorazione) cambia anche l'elenco categorie ammesse. Account non misurati.

**prova.** lib/fatture.ts:137-140: con revalidateSec si usa next:{revalidate}. fetchMesiDisponibili (:174-181) e fetchCategorie (:204-209) passano 60. In Next 16.2.6 la chiave della Data Cache (node_modules/next/dist/server/lib/incremental-cache/index.js:239-256) è [url, method, headers, …]: gli header contengono Authorization: Bearer <token> (lib/worker-config.ts:18-23) ma nessun riferimento alla sede, e l'URL non ha parametri di sede. Il worker invece risolve la sede dalla sessione: fatture.py:327-345 (.eq('ristorante_id', ristorante_id)) e :1046-1070. cambia-sede non cambia il token e non c'è revalidateTag/revalidatePath (grep 'revalidate' in apps/web/src: solo lib/fatture.ts). La sessione resta per persona (token diversi), quindi niente fuga fra persone.

**fix proposto.** Usare cache:'no-store' come tutte le altre letture; in alternativa includere la sede attiva nella chiave (es. ?sede=<sede_attiva_id> ignorato dal worker), oppure revalidateTag al cambio sede.

**presidio proposto.** Presidio statico: in apps/web/src nessun fetch verso WORKER_URL con next.revalidate o force-cache senza la sede nella chiave; provarlo per mutazione su lib/fatture.ts.

**gia presidiato da.** Nessun presidio: grep 'revalidate' in tests → 0 risultati.

**file e righe.** `apps/web/src/lib/fatture.ts:128-150`; `apps/web/src/lib/fatture.ts:174-181`; `apps/web/src/lib/fatture.ts:204-210`; `services/routers/fatture.py:327-345`; `services/routers/fatture.py:1046-1070`

### F2b-7 — Logout e scadenza della sessione non svuotano sessionStorage: la conversazione con l'assistente (cifre e card) resta leggibile nella stessa scheda dopo l'uscita

Filone 2 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Dispositivo condiviso (tablet di sala): titolare e dipendente nella stessa scheda, uno dopo l'altro. Desktop e /m.

**prova.** assistente-provider.tsx:105 salva la conversazione in sessionStorage sotto chiaveConversazione(idPersona) (home-chat.ts:364-369). handleLogout (app-sidebar.tsx:141-145), logout mobile (header-menu.tsx:94-98) e api/auth/logout/route.ts:8-30 cancellano solo i cookie: nessun sessionStorage.clear e nessun Clear-Site-Data (grep 'sessionStorage' nei tre file → 0). Il commento home-chat.ts:364 ammette che sessionStorage sopravvive al logout. La chiave per persona impedisce alla UI della persona successiva di mostrarla (test_la_conversazione_e_della_persona_non_dell_account), ma il dato resta in chiaro nel browser fino alla chiusura della scheda.

**fix proposto.** Al logout rimuovere le chiavi 'oneflux:assistente:*' (o tutto sessionStorage) prima di router.push('/login'); in alternativa header Clear-Site-Data: "storage" sulla risposta di /api/auth/logout.

**presidio proposto.** Funzione pura di pulizia in lib (lista delle chiavi da rimuovere) testata con node su uno Storage finto, chiamata da entrambi i logout.

**gia presidiato da.** tests/test_sotto_utente_frontend.py:133-144 presidia solo le chiavi distinte per persona.

**file e righe.** `apps/web/src/components/home/assistente-provider.tsx:88-110`; `apps/web/src/lib/home-chat.ts:364-369`; `apps/web/src/components/nav/app-sidebar.tsx:141-145`; `apps/web/src/app/(mobile)/m/header-menu.tsx:94-98`; `apps/web/src/app/api/auth/logout/route.ts:8-30`

### F2b-8 — Home del sotto-utente: i link di KPI, Salute e «Da fare» portano a pagine che non ha (404)

Filone 2 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** /dashboard di un sotto-utente con Home ma senza margini, analisi_fatture o prezzi. Account non misurati.

**prova.** kpi-block.tsx:82, :103, :127, :144, :151, :158 hanno link fissi a /margini, /analisi-fatture e /prezzi. salute-card.tsx:38-40 usa v.cta_page arrivato dal worker (fastapi_worker.py:9673, :9681). home-da-fare.ts:59 usa a.cta_page delle azioni del briefing. Nessuno filtra per pagine_abilitate (grep pagine_abilitate in dashboard/ e components/home: solo page.tsx:169 per i trigger). Le pagine mancanti fanno notFound() via requirePagina (page-guard.ts:27). Mostrare i dati è una scelta («Home intera»); il link a un 404 no.

**fix proposto.** Passare pagine_abilitate a KpiBlock, SaluteCard e DaFareOggi e togliere il link (lasciando il testo) quando la pagina di destinazione è spenta, con lo stesso mapping percorso→flag di _PAGINA_DI_PERCORSO (permessi_rotte.py:359).

**presidio proposto.** Funzione pura in lib hrefSeConsentito(href, pagine) testata con node, sullo stesso mapping usato da notifica_visibile lato worker.

**gia presidiato da.** Nessun presidio.

**file e righe.** `apps/web/src/app/(app)/dashboard/kpi-block.tsx:82-158`; `apps/web/src/app/(app)/dashboard/salute-card.tsx:38-46`; `apps/web/src/lib/home-da-fare.ts:52-62`; `apps/web/src/lib/page-guard.ts:27`

### Verificato e trovato giusto

- INVENTARIO pagina → guardia → flag → rotte → esito (desktop). /dashboard: requireHome (page.tsx:177, prima di ogni blocco) → H; chiama /api/home/briefing, kpi e salute (H), più GET /api/home/config e /api/notifiche (comuni). OK, tranne POST /api/home/config (F2b-3).
- /analisi-fatture: requirePaginaConTab('analisi_fatture') → F; rotte /api/fatture/* e upload (F), /api/scadenziario/anteprima (S,C,P,F). PATCH /api/riparto/riga-categoria (C) dà 403 a chi non ha la Catena, ma articoli-tab.tsx:653-660 lo intercetta col messaggio «lo può correggere solo chi gestisce la catena»: scelta voluta e gestita.
- /margini: requirePaginaConTab('margini') → M; /api/margini/* e /api/ricavi/* (M; giornalieri e modalità M,A). Nessuna rotta fuori pagina (verifica automatica su tutti i .tsx della cartella e dei componenti importati).
- /analisi-e-tag: requirePagina('analisi_e_tag') → T; solo /api/tag/* (sorgenteSede). OK.
- /prezzi: requirePaginaConTab('prezzi') → P; /api/prezzi/* (P), GET soglia-alert (P), anteprima fattura con /api/scadenziario/anteprima (P ammesso). /api/gruppo/prezzi/fattura parte solo se viene passato ristoranteId (anteprima-fattura-dialog.tsx:62), cosa che variazioni-tab non fa.
- /scadenziario: requirePagina('scadenziario') → S; rotte S e S,C, /api/account/preferenze (comune). Le varianti /api/gruppo/* solo con modalitaCatena, che la pagina non passa. «Ripartisci» e «Sposta sede» spariscono con catena:false da /api/account/sedi (scadenziario-client.tsx:714-726, :1003; account.py:843-846).
- /agenda: requirePaginaConTab('agenda') → A; solo /api/workspace/diario, spese, personale e dipendenti (A). OK.
- /workspace: ?tab=agenda|spese|personale reindirizza a /agenda prima della guardia (page.tsx:29-31); requirePaginaConTab('workspace') → W; rende solo FoodcostTab e InventarioTab con rotte /api/workspace/foodcost/* e inventario/* (W). I .tsx A che stanno nella cartella workspace li usa /agenda.
- /catena, /catena/fatture, /catena/analisi: requireCatena in catena/layout.tsx:6, più il controllo delle schede; rotte /api/gruppo/*, /api/riparto/* (C) e /api/scadenziario/* (S,C). La scheda «Scadenze» richiede anche 'scadenziario' (catena-schede.ts:139): vede in meno, va bene. Eccezione: POST assistant-config (F2b-3).
- /notifiche, /assistenza, /impostazioni, /style-guide senza guardia: usano solo rotte comuni (/api/notifiche, /api/assistenza/lead, /api/account/me, /api/account/sedi) o nessun dato.
- Mobile: /m → redirect /m/briefing. /m/briefing e /m/chat: requireTabMobile → haHome; rotte home (H) e /api/chat (H,C); /api/gruppo/* solo con haCatena. /m/notifiche e /m/impostazioni senza guardia, solo rotte comuni. Il layout /m chiama /api/notifiche e GET /api/home/config (comuni) e /api/gruppo/chat-config solo se inChain (richiede haCatena).
- Deep link /catena senza C con più sedi: requireCatena → redirect('/dashboard' se Home, altrimenti prima pagina). primaPaginaAbilitata non restituisce mai /catena senza haCatena (node: 'home false, catena false' → mai /catena), quindi niente ciclo. I dati di gruppo restano protetti da verify_catena nel worker.
- Deep link /dashboard senza Home: requireHome redirige prima che parta qualunque blocco (page.tsx:177, prima del return). Destinazione: prima pagina accesa (node: ['workspace'] → '/workspace', [] → '/impostazioni').
- Deep link /admin: admin/layout.tsx:6-8 e ogni page admin reindirizzano se !is_admin. Il worker forza is_admin=False per il sotto-utente (account.py:198) e vieta /api/admin/*.
- Deep link /impostazioni per un sotto-utente: Piano, Ricavi senza IVA, Privacy/GDPR (export ed elimina) e «Email settimanale» non compaiono (account-client.tsx:897, :943, :1012, :1015; account.py:183-201 forza email_settimanale_abilitata=False). Il worker vieta elimina, esporta-dati, svuota-dati e ricavi-noiva (permessi_rotte.py:283-296). Tema e password scrivono su sotto_utenti (account.py:369-374, cambia-password :10-11). Mobile /m/impostazioni riusa lo stesso AccountClient.
- Deep link /m/chat senza Home e /m/diario senza agenda: requireTabMobile reindirizza a primaTabMobile, mai sulla tab negata (node, tutte le combinazioni del test). Eccezione: il caso workspace (F2b-1).
- /assistenza: il sotto-utente può solo mandare una richiesta di informazioni (POST /api/assistenza/lead, comune, fastapi_worker.py:2952-2985: insert di un lead con contatto_email della persona). Nessun acquisto o pagamento nel flusso; il Boost è segnalato come titolare=false (dashboard/page.tsx:170).
- Proxy che inoltrano la query (fatture/righe-articolo, trend, righe-export, gruppo/tag/[...path]): il worker prende la sede dalla sessione (fatture.py:706-716, :945-958) e ignora ristorante_id in query. L'unico ristorante_id esplicito (gruppo/prezzi/fattura) passa per _resolve_gruppo + rid_to_nome (gruppo.py:3683-3685) e richiede C.
- Cookie oneflux_view manipolato da un sotto-utente senza C: desktop inChain = isCatenaPage || (catenaRaggiungibile && …), con catenaRaggiungibile = hasMultiSede && mostraCatena (false) (app-sidebar.tsx:177, :213); /catena reindirizza lato server; /m layout, /m/briefing, /m/chat e /impostazioni calcolano inChain con haCatena(user) dal server (false); header-menu nasconde «Vista catena» con catena:false. Le sedi mostrate vengono da /api/account/sedi già filtrata con filtra_sedi.
- Nessun Cache-Control pubblico: l'unico header di cache è 'private, max-age=86400' su api/tts. Nessun unstable_cache, 'use cache', revalidate di route o force-cache. L'unico uso di Data Cache è lib/fatture.ts (F2b-6), con chiave per token: niente fuga fra persone (incremental-cache/index.js:239-256 include gli header).
- idPersona: email con maiuscole o spazi darebbe chiavi diverse (node: 'u1:[email] ' contro 'u1:[email]'), ma sotto_utenti.email ha CHECK email = lower(btrim(email)) AND email <> '' (migration 20260928215000:41-42), quindi il caso non si presenta. Email assente → 'u1:' condivisa fra persone: impossibile, colonna NOT NULL. FALSO ALLARME.
- Email in chiaro nella chiave sessionStorage: storage per origine e per scheda, mai inviato al server; la stessa email compare già nella sidebar (app-sidebar.tsx:446). Non espone niente di nuovo: FALSO ALLARME. Il problema vero è il contenuto rimasto dopo il logout (F2b-7).
- Casi limite eseguiti con node su lib/sotto-utente: pagine [] / null / solo tab_off_* → niente Home, niente Catena, atterraggio /impostazioni e /m/impostazioni, tab mobile tutte nascoste. Catena true con 1 sede → haCatena false (vede in meno). Titolare con pagine ristrette → Home sempre. sotto_utente con is_admin true → '/admin', ma il worker forza is_admin False per i sotto-utenti, quindi caso irraggiungibile. Su telefono un sotto-utente senza Home riceve un URL desktop (es. '/analisi-fatture') da primaPaginaAbilitata(u,true): MobileRedirect lo rimanda a /m e lì requireTabMobile lo sistema. Un salto in più, nessun 403.
- ImpersonaBanner nel layout chiama /api/admin/impersona/status, che è una route Next locale (legge solo il cookie oneflux_impersonate, status/route.ts) e non arriva al worker /api/admin: nessun 403 per i sotto-utenti.
- requirePagina fail-open sul caricamento completo (hard navigation): getCurrentSession è cache() per richiesta, layout e pagina vedono lo stesso esito; 'invalid' → il layout reindirizza a /login, 'unavailable' → il layout rende il ripiego senza children. Lì il fail-open non mostra niente; il caso residuo è la navigazione client (F2b-5).

### Non verificabile in sola lettura

- Quanti sotto-utenti reali hanno le combinazioni dei finding (solo workspace senza agenda; catena senza home): il filone è dichiarato senza DB, quindi clienti_ids vuoti. Si misura con una query su sotto_utenti.pagine filtrata per titolare.
- Comportamento a runtime di Next 16 su soft navigation (layout non rieseguito) e della Data Cache su Vercel: ricavato dai sorgenti e dalla documentazione inclusi in node_modules, senza avviare Next (vietato dal compito).
- Contenuto effettivo del briefing inviato a Google (presenza del nome nel saluto per gli account reali): si prova con una lettura dei briefing salvati, esclusa dal filone senza DB.
- Se un dismiss del sotto-utente spegne la notifica anche al titolare (POST /api/notifiche/{id}/dismiss, ignorabile anche dalla Home del sotto-utente) e cosa espone GET /api/home/config a chi non ha la Home: sono punti backend del filone F2a, non verificati qui.
- /m/diario e /m/turni non applicano i tab_off_agenda_* che il desktop rispetta, per il titolare come per il sotto-utente: non è specifico dei sotto-utenti (il titolare vede lo stesso), quindi non è un caso «vede più del titolare». Segnalato senza approfondire.

## F1e definizioni e periodi

### F1e-01 — «Fatturato»: la stessa parola per lordo IVA (Home, catena Sintesi, chat) e netto (Margini, catena Margini e coperti), con basi dichiarate solo in tre superfici su cinque

Filone 1 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** Home card «I tuoi conti» (sede e /m/briefing, stesso KpiBlock): tessera «Fatturato» senza indicazione IVA, periodo in meta = `kpi.periodo_label` («Settembre» o «Ottobre · in corso»); Ricavi e Margini KpiBar: «Fatturato Netto» con sotto «lordo X», chip «Anno in corso»; Catena → Sintesi: «Fatturato (IVA incl.)» con meta `overview.periodo_label`; Catena → Analisi → Margini e coperti: colonna «Fatturato» (netto, dichiarato solo nel tooltip); chat tool query_margini: chiave `fatturato` lorda, descrizione dice solo «fatturato». Tutti gli account; nessun ID misurabile in questo filone (solo codice).

**prova.** Home: kpi-block.tsx:122-124 `label="Fatturato"` senza suffisso, valore `kpi.fatturato`; worker _kpi_periodo (fastapi_worker.py:9800-9813) `fatturato = iva10 + iva22 + altri` (lordo) e `netto = iva10/1.10 + iva22/1.22 + altri`; periodo_label a :10043-10045. Margini: kpi-bar.tsx:219 `label: "Fatturato Netto", numeric: kpi.fatturato_netto, sub: lordo …`. Catena Sintesi: sintesi-catena.tsx:238 `label="Fatturato (IVA incl.)"` su `kpi.fatturato` = gruppo.py:1227 `fatturato=round(tot_lordo, 2)`. Catena Margini e coperti: scheda-margini-coperti.tsx:65-67 `label: "Fatturato"` tooltip «al netto dell'IVA» su gruppo.py:1621 `fatturato=round(netto, 2)`. Chat: fastapi_worker.py:5332 `"fatturato": k["fatturato"]` (lordo da _kpi_periodo), descrizione tool :5519-5524 «Andamento di fatturato, food cost % e MOL». Due superfici con la sola parola «Fatturato» (Home lordo, catena Margini e coperti netto) e la chat che riceve il lordo mentre la pagina Margini titola il netto.

**numeri attesi vs mostrati.** Stesso mese: Home mostra lordo (iva10+iva22+altri), Margini mostra netto (iva10/1.10+iva22/1.22+altri) con il lordo in sottotitolo; a parità di dati il numero Home è il «lordo» della card Margini, ma il cliente legge due «Fatturato» diversi.

**fix proposto.** Etichetta Home «Fatturato (IVA incl.)» come la catena (o «Incasso lordo»), colonna catena Margini e coperti «Fatturato netto» nell'intestazione e non solo nel tooltip; nel tool chat rinominare la chiave in `fatturato_lordo` (o aggiungere `fatturato_netto`) e scriverlo nella descrizione, così l'AI non confronta il lordo con il «Fatturato Netto» che il cliente legge su Margini.

**presidio proposto.** Test frontend su un file di sorgente (tests/test_*_frontend.py con helpers_ts) che legge le etichette dei KPI «Fatturato» in kpi-block.tsx, sintesi-catena.tsx e scheda-margini-coperti.tsx e pretende il suffisso (IVA incl./netto) accanto alla parola; test worker che asserisce che il payload di _chat_query_margini contenga una chiave con la base IVA nel nome.

**gia presidiato da.** Nessun test lega etichetta e base IVA: test_fase_e_incasso_fuori_norma.py:476 prova solo che food cost coincide fra catena, pagina e chat; test_food_cost_sempre_su_netto copre il denominatore del food cost, non l'etichetta del fatturato.

**file e righe.** `apps/web/src/app/(app)/dashboard/kpi-block.tsx:78`; `apps/web/src/app/(app)/dashboard/kpi-block.tsx:122-124`; `services/fastapi_worker.py:9800-9813`; `services/fastapi_worker.py:10043-10045`; `apps/web/src/app/(app)/margini/kpi-bar.tsx:219`; `apps/web/src/app/(app)/catena/sintesi-catena.tsx:238`; `services/routers/gruppo.py:1227`; `apps/web/src/app/(app)/catena/analisi/scheda-margini-coperti.tsx:65-67`; `services/routers/gruppo.py:1621`; `services/fastapi_worker.py:5332`; `services/fastapi_worker.py:5519-5524`

### F1e-02 — Lo stesso MOL % riceve giudizi diversi: gauge Margini (5/12/20) contro pallino catena «Margini e coperti» (8/15)

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Ricavi e Margini → tab Analisi (gauge MOL con emoji e commento da _valuta_soglia_margine) e Catena → Analisi → Margini e coperti (pallino margineDot per PV). Il `colore` del ranking (gruppo.py _colore_margine) non è reso da nessun .tsx. Tutti gli account con catena.

**prova.** Eseguito con python -I (funzioni pure estratte via ast da routers/margini.py e routers/gruppo.py) e con node (lib/catena-confronti.ts): MOL 7% → Margini 🟠 «MOL basso» / catena margineDot bg-negativo (rosso); 10% → 🟠 / bg-incerto (giallo); 13% → 🟡 «MOL nella norma» / bg-incerto; 18% → 🟡 «MOL nella norma» / bg-positivo (verde); 25% → 🟢 / verde. Soglie: margini.py:860-865 (5,12,20,200); catena-confronti.ts:24-25 SOGLIA_MARGINE_VERDE=15, GIALLO=8 e margineDot :54-59; gruppo.py:328-340 _colore_margine (15/8) la cui docstring dice «stesse soglie di lettura dei conti PV», falso. _colore_margine finisce in RankingPV.colore (gruppo.py:1266) che nessun .tsx legge (grep `r.colore|ranking.*colore` vuoto): sintesi-catena.tsx:284 usa `pv.colore` della salute.

**numeri attesi vs mostrati.** MOL 18%: Margini dice 🟡 «MOL nella norma», la catena mette il pallino verde; MOL 7%: Margini 🟠 «MOL basso», catena rosso.

**fix proposto.** Una sola scala: portare SOGLIA_MARGINE_VERDE/GIALLO a 20/12 (le soglie di Margini, che hanno anche il testo) oppure, se la catena deve restare a tre colori, derivarle dalle stesse costanti (esporle dal worker nell'overview o generarle da config/constants.py come già si fa per altre costanti condivise) e cancellare _colore_margine, che non ha consumatori.

**presidio proposto.** Test che esegue margineDot con node e _valuta_soglia_margine in Python sugli stessi valori (7, 13, 18) e pretende la stessa classe di colore (rosso/giallo/verde ↔ 🔴🟠/🟡/🟢); un test sul sorgente che vieta un secondo set di soglie MOL fuori da constants.py.

**gia presidiato da.** tests/test_catena_confronti_frontend.py:71 fissa 15/8 e tests/test_margini_soglie_settore.py:185-205 fissa 5/12/20: ciascuna copia è protetta nel suo valore, nessun test le confronta.

**file e righe.** `services/routers/margini.py:860-865`; `services/routers/margini.py:965-977`; `apps/web/src/lib/catena-confronti.ts:24-25`; `apps/web/src/lib/catena-confronti.ts:54-59`; `services/routers/gruppo.py:328-340`; `services/routers/gruppo.py:1266`; `apps/web/src/app/(app)/catena/analisi/scheda-margini-coperti.tsx:238`

### F1e-03 — Card MOL di Ricavi e Margini verde col MOL positivo anche quando l'analisi sotto dice «Nessun giudizio: mancano costi»

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Ricavi e Margini, KpiBar in cima alla pagina (sede). La Home, sullo stesso mese, mette il MOL in giallo via tintContiPV. Tutti gli account con un mese a ricavi senza fatture merce.

**prova.** kpi-bar.tsx:208 `const molTone: Tone = kpi.mol >= 0 ? "positivo" : "negativo"`; il tipo KpiData (kpi-bar.tsx:9-28) e MarginiKpiResponse (margini.py:1463-1480) non hanno nessun campo costi_mancanti/mesi_senza_costi: il client non può saperlo. _mesi_senza_costi ha un solo chiamante, get_margini_analisi (margini.py:1403), che sostituisce il giudizio con «Nessun giudizio» (:941,:954). Per confronto tintContiPV eseguita con node: {mol:1300,costi_mancanti:true} → giallo; la KpiBar non ha quel ramo.

**numeri attesi vs mostrati.** Mese con ricavi 50.000 e costi F&B 0: card MOL verde; gauge sotto «Nessun giudizio: mancano costi»; Home sullo stesso mese MOL giallo.

**fix proposto.** get_margini_kpi espone `mesi_senza_costi` (riusando _mesi_senza_costi sugli stessi mesi attivi) e la KpiBar decide il tono con una funzione di lib (es. toneMol in lib/kpi-margini-tab.ts) che torna «incerto» quando >0, come tintContiPV; il test la esegue con node.

**presidio proposto.** Test worker: get_margini_kpi su un mese con ricavi e costi F&B a zero torna mesi_senza_costi=1; test frontend su toneMol({mol:1300, mesi_senza_costi:1}) = incerto, provato per mutazione togliendo il ramo.

**gia presidiato da.** tests/test_margini_giudizio_dati_incompleti copre solo get_margini_analisi; tests/test_kpi_margini_tab_frontend.py non ha assert sul tono (grep «molTone|tone» vuoto).

**file e righe.** `apps/web/src/app/(app)/margini/kpi-bar.tsx:208`; `apps/web/src/app/(app)/margini/kpi-bar.tsx:9-28`; `services/routers/margini.py:1463-1480`; `services/routers/margini.py:921`; `services/routers/margini.py:1403`; `apps/web/src/lib/catena-confronti.ts:369-379`

### F1e-04 — KPI_SOGLIE (constants) e _KPI_SOGLIE_MARGINI (routers/margini) differiscono solo nel tetto 100 vs 200 di mol/primo_margine: esito identico su ogni valore

Filone 1 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuno: eseguiti i due valutatori, l'emoji è la stessa per ogni percentuale (il ramo finale torna l'ultima soglia sia con 100 sia con 200). In più il consumatore di KPI_SOGLIE['mol'] (margine_service.genera_commenti_kpi) non ha chiamanti a runtime, solo tests/test_margine_service.py; il briefing usa solo KPI_SOGLIE['food_cost'] (worker:7334-7358), identica.

**prova.** python -I su funzioni pure estratte: food_cost/spese_generali/personale uguali; primo_margine e mol diversi solo nell'ultima tupla (100 vs 200). _valuta_soglia_margine (margini.py:973-977) e _valuta_soglia (margine_service.py:985-997) ricadono entrambe su `soglie[-1]` oltre l'ultima soglia → stesso emoji/testo. grep `genera_commenti_kpi(` in services: nessun chiamante.

**numeri attesi vs mostrati.** Nessuna differenza a video.

**fix proposto.** Far importare _KPI_SOGLIE_MARGINI da config.constants (una copia sola) e allineare il tetto; nessuna urgenza.

**presidio proposto.** Assert `_KPI_SOGLIE_MARGINI is KPI_SOGLIE` (o uguaglianza) in tests/test_margini_soglie_settore.py.

**gia presidiato da.** tests/test_margini_soglie_settore.py:185-205 fissa la copia di margini.py; nessun test confronta le due.

**file e righe.** `config/constants.py:1914-1945`; `services/routers/margini.py:834-865`; `services/margine_service.py:969-997`; `services/fastapi_worker.py:7334-7358`

### F1e-05 — «Spesa totale» di Analisi Fatture e i costi di Ricavi e Margini sono su basi diverse (data fattura vs competenza, Da Classificare dentro vs fuori) e la card non lo dice

Filone 1 · periodo non dichiarato · gravità media · confidenza alta

**chi lo vede.** Analisi Fatture (sede), KpiBar: «Spesa totale» e «Media al mese», chip periodo «Anno in corso», nessuna nota su base IVA, data o righe non classificate; a confronto con Costi F&B/Spese Generali della pagina Margini per lo stesso periodo. Tutti gli account con fatture.

**prova.** Le quattro differenze confermate nel codice: (1) data: _fetch_fatture_rows filtra `data_documento` (fastapi_worker.py:10602-10605) mentre i costi di Margini usano COALESCE(data_competenza,data_documento) (SQL costi_automatici_mensili 20260912075621_oscura_fattura.sql:120, Python _calcola_costi_auto_per_mese :10893-10896); (2) _build_fatture_base_query (:10436-10448) non ha `.neq("categoria", CATEGORIA_NON_CLASSIFICATA)` che i costi di Margini hanno (:10889, SQL :124); (3) _apply_tipo_prodotti_filter (:10452-10455) food_beverage = «non in CATEGORIE_SPESE_GENERALI_WORKER», quindi le Da Classificare cadono in F&B; (4) righe quote proiettate aggiunte (:10622-10641) mentre Margini le somma da quote_riparto_* (_kpi_periodo :9819-9828). Etichette: analisi-fatture/kpi-bar.tsx:71-72; chip analisi-fatture/filtri-periodo.tsx:93 «Anno in corso». NC nettizzate in entrambe (fatture.py:393-400). La stessa etichetta «Spesa totale» compare in catena scheda-tag-catena.tsx:453 su gruppo_tag_analisi che usa COALESCE(data_competenza,data_documento) (oscura_fattura.sql, def gruppo_tag_analisi righe 19-21 del corpo): stessa parola, altra data.

**numeri attesi vs mostrati.** Per un mese con N righe Da Classificare e M righe con data_competenza diversa dalla data fattura, «Spesa totale» ≠ Costi F&B + Spese Generali di Margini della somma di quelle righe; quantità non misurabile senza DB.

**fix proposto.** Dichiararlo accanto al numero («per data fattura, IVA esclusa, comprese le righe da classificare») oppure allineare: filtro su COALESCE(data_competenza,data_documento) in _fetch_fatture_rows e una terza voce esplicita «Da classificare» nel KPI invece di farle cadere in F&B. Sono numeri diversi entrambi giusti: serve il nome, non un ricalcolo.

**presidio proposto.** Test worker con righe sintetiche (una con data_competenza nel mese successivo, una Da Classificare): get_fatture_kpi e _calcola_costi_auto_per_mese sullo stesso mese devono tornare totali che differiscono esattamente delle righe dichiarate; oggi non esiste nessun test sui totali di /api/fatture/kpi.

**gia presidiato da.** Nessuno sui totali: tests/test_s3c_medium_low.py prova solo che i filtri solo_da_verificare/solo_ripartite restringono e che tipo_prodotti arriva al fetch.

**file e righe.** `services/fastapi_worker.py:10436-10448`; `services/fastapi_worker.py:10452-10455`; `services/fastapi_worker.py:10602-10605`; `services/fastapi_worker.py:10622-10641`; `services/routers/fatture.py:393-405`; `apps/web/src/app/(app)/analisi-fatture/kpi-bar.tsx:71-72`; `apps/web/src/app/(app)/analisi-fatture/filtri-periodo.tsx:93`; `supabase/migrations/20260912075621_oscura_fattura.sql:120-124`; `apps/web/src/app/(app)/catena/analisi/scheda-tag-catena.tsx:453`

### F1e-06 — Catena «Spesa per punto vendita» scarta le righe negative (note di credito) che Analisi Fatture e i tag nettizzano

Filone 1 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** Catena → Analisi → scheda «Spesa per punto vendita» (pivot per categoria/fornitore ed export Excel) contro Analisi Fatture del singolo PV e scheda tag catena. Account con catena e note di credito nel periodo.

**prova.** gruppo_spesa_pivot (20260912075621_oscura_fattura.sql:355-378) ha `AND f.totale_riga > 0`; il loop delle quote (gruppo.py:1449-1451) `if totale_riga <= 0: continue`. Analisi Fatture: fatture.py:393-400 somma anche le righe negative («le note di credito … DEVONO ridurre la spesa»); gruppo_tag_analisi `sum(f.totale_riga)` senza filtro di segno; costi_automatici_mensili SQL idem. Nessuna nota a video (scheda-spesa-pv.tsx: grep «credito|negativ» vuoto).

**numeri attesi vs mostrati.** PV con 10.000 di acquisti e una NC da 300: Analisi Fatture «Spesa totale» 9.700, catena «Spesa per punto vendita» 10.000.

**fix proposto.** Togliere `totale_riga > 0` dalla RPC e il `<= 0: continue` dalle quote (migration + gruppo.py) così la spesa per PV è netta come nel PV; se si vuole tenere il lordo, scriverlo nel sottotitolo della scheda («al lordo delle note di credito»).

**presidio proposto.** Test -m sql su gruppo_spesa_pivot con una riga −100 di TD04: il totale del PV deve scendere di 100; mutante: rimettere `> 0`.

**gia presidiato da.** Nessuno: tests/test_gruppo_spesa_pivot_quote.py e tests/test_sql_funzioni_soldi.py non hanno righe negative/TD04 (grep vuoto).

**file e righe.** `supabase/migrations/20260912075621_oscura_fattura.sql:374`; `services/routers/gruppo.py:1449-1451`; `services/routers/fatture.py:393-400`; `apps/web/src/app/(app)/catena/analisi/scheda-spesa-pv.tsx:95`

### F1e-07 — Gestione Fatture, vista «Per mese»: l'intestazione del mese somma le note di credito col segno positivo e include escluse e pagate, contando tutto

Filone 1 · bug vero · gravità alta · confidenza alta

**chi lo vede.** Gestione Fatture (sede) e Catena → Fatture (riusa ScadenziarioClient), vista `lista_mensile`: intestazione di ogni mese con «N» documenti e «X €». Tutti gli account con NC o fatture escluse.

**prova.** Eseguito con node lib/scadenziario.ts su 4 documenti (NC 300 €, esclusa 500 €, pagata 700 €, aperta 1.100 €): documentiCalendario = filtraDocumenti(periodo «tutti») include l'esclusa (scadenziario-client.tsx:1775-1783; matchDocumento :692 salta i filtri di stato con «tutti»); raggruppaPerMeseFattura (lib :840-876) non esclude nulla → intestazione «4 / 2.600 €» (client :285 `docs.reduce(totale_documento)`, :308 `{docs.length}`, :313 formatEuro(totale)). Il segno: totale_documento viene da fatture_documenti.totale_documento = ImportoTotaleDocumento dell'XML (documenti_service.py:810-813; invoice_service.py:872-875), positivo anche per TD04: l'inversione di segno (invoice_service.py:1015+) tocca solo le righe. Con solo le aperte sarebbe 1 / 1.100; nettizzando la NC 800.

**numeri attesi vs mostrati.** Dataset sintetico: mostrato «4 documenti · 2.600 €»; atteso 1 / 1.100 € (solo aperte) o 800 € (nettizzando la NC) a seconda della definizione, mai 2.600.

**fix proposto.** In raggruppaPerMeseFattura (già calcola `totale` e `count` a :875-876, che l'intestazione non usa) sottrarre le NC e lasciare fuori le oscurate dal totale; l'intestazione legge g.totale/g.count invece di rifare la somma nel .tsx. Se l'archivio deve contare anche le pagate, scriverlo («compreso pagato»).

**presidio proposto.** Estendere tests/test_scadenziario_vista_mensile_frontend.py con una NC, un'oscurata e una pagata nello stesso mese e fissare totale e conteggio attesi; test sul sorgente che vieta `docs.reduce` in AgendaSection (la somma vive nella lib).

**gia presidiato da.** tests/test_scadenziario_vista_mensile_frontend.py usa solo documenti positivi, non NC, non oscurati (righe 32-48): verde sul bug.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:285`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:308`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:313`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1775-1783`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2047`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2516-2520`; `apps/web/src/lib/scadenziario.ts:840-876`; `services/documenti_service.py:810-813`; `services/invoice_service.py:872-875`

### F1e-08 — Gestione Fatture: totale documento IVA inclusa quando c'è fatture_documenti, netto righe quando manca — base mista nella stessa lista

Filone 1 · stessa etichetta per grandezze diverse · gravità media · confidenza alta

**chi lo vede.** Gestione Fatture (sede e catena): colonna importo, KPI Scadute/Da pagare, calendario, chat query_scadenze. Quanti documenti cadono nel fallback non è misurabile senza DB.

**prova.** documenti_service.py:810-813: `totale_doc = extra.get("totale_documento")` (fatture_documenti, = ImportoTotaleDocumento XML, IVA inclusa: invoice_service.py:872-875), altrimenti `totale_righe` = somma totale_riga (netto IVA, NC negative). Il campo non porta traccia di quale base è stata usata (solo `totale_incoerente` per la divergenza). Margini e Analisi Fatture usano sempre le righe nette.

**numeri attesi vs mostrati.** Fattura 1.000 + IVA 10%: con fatture_documenti mostra 1.100, senza mostra 1.000 nella stessa colonna.

**fix proposto.** Esporre `totale_base: "documento" | "righe"` nel payload e marcare a video i totali da righe («netto, stimato»), oppure nel fallback ricostruire il lordo dalle righe + IVA dei DatiRiepilogo quando disponibili.

**presidio proposto.** Test su get_documenti_scadenziario con un documento senza riga in fatture_documenti che asserisce il flag della base; conteggio a DB dei documenti attivi senza fatture_documenti (query di un altro filone).

**gia presidiato da.** tests/test_documenti_service_scadenziario.py:208-306 prova la preferenza e il fallback (valore), non che il cliente veda che la base cambia.

**file e righe.** `services/documenti_service.py:810-815`; `services/invoice_service.py:872-875`; `services/documenti_service.py:851-860`

### F1e-09 — Calendario scadenze in browser conta le fatture «Escluse dai conti» che KPI, sezioni, scadute-fuori-mese e worker escludono

Filone 1 · bug vero · gravità alta · confidenza alta

**chi lo vede.** Gestione Fatture → vista Calendario (sede e catena): totale del giorno, intensità della casella, totale mese; sulla stessa pagina i KPI e «scaduteFuoriDalMese» la escludono. Account con fatture oscurate non pagate con scadenza.

**prova.** CalendarView (scadenziario-client.tsx:489-506) salta solo `doc.pagata` e `doc.is_nota_credito`; riceve documentiCalendario (:2562, :1775-1783) che include le oscurate (eseguito: filtraDocumenti con periodo «tutti» → oscurata inclusa = true). Replica della logica inline con node sul dataset: ottobre 2026 → {21: 500 (esclusa), 23: 1100}, totale 1.600; il worker /api/scadenziario/calendario (routers/scadenziario.py:143-151) salta anche `oscurata` → {23: 1100}; statoDocumento(osc) = «Escluse da te» (lib :560); computeKpi da_pagare_totale = 1100; scaduteFuoriDalMese esclude via statoDocumento (:600). La route Next api/scadenziario/calendario/route.ts esiste ma nessun .tsx la chiama (grep «api/scadenziario/calendario» fuori da route.ts vuoto).

**numeri attesi vs mostrati.** Dataset sintetico ottobre 2026: calendario mostra 1.600 € (500 il 21 + 1.100 il 23); atteso 1.100 € (solo il 23), come dà il worker.

**fix proposto.** Spostare l'aggregazione del calendario in lib/scadenziario.ts (es. aggregaCalendario(documenti, anno, mese, today) basata su statoDocumento, così esclude oscurate/NC/pagate con la stessa regola delle altre viste) e farla usare da CalendarView; in alternativa consumare l'endpoint worker già esistente. Un `if (doc.oscurata) continue;` nel .tsx chiude il buco ma resta non testabile.

**presidio proposto.** Test frontend con node su aggregaCalendario con il dataset a 4 documenti: il giorno 21 non deve esistere; mutante: togliere il controllo oscurata.

**gia presidiato da.** tests/test_scadenziario_calendario_fuori_mese_frontend.py:102 copre scaduteFuoriDalMese (lib), non la griglia; tests/test_scadenziario_oscurate_frontend.py copre KPI, per sede ed elenco, non il calendario.

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:489-506`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:1775-1783`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2562`; `apps/web/src/lib/scadenziario.ts:559-568`; `apps/web/src/lib/scadenziario.ts:591-608`; `services/routers/scadenziario.py:143-151`; `apps/web/src/app/api/scadenziario/calendario/route.ts`

### F1e-10 — Due copie di calcolaPeriodo (Margini e Analisi Fatture): identiche sui preset che le pagine offrono, divergono solo su preset non raggiungibili dall'interfaccia

Filone 1 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuno dall'interfaccia: entrambi i filtri offrono solo «Anno in corso», mese specifico e personalizzato (margini/filtri-periodo.tsx:70-86, analisi-fatture/filtri-periodo.tsx:90-106). Solo un URL scritto a mano con ?preset=q1 vede la differenza (Margini lo onora, Analisi Fatture lo riporta ad anno_corrente per whitelist page.tsx:54-60).

**prova.** Eseguite con node le due copie (TZ Europe/Rome e UTC) il 15/10/2026 12:00 e il 1/10/2026 00:30: mese_corrente, trimestre_corrente, semestre_corrente, anno_corrente → UGUALI (es. 2026-10-01..2026-10-01 «Mese in corso» alle 00:30 del 1°); anno_precedente, q1-q4, h1, h2 → la copia di Analisi Fatture ricade su «Anno in corso» (default dello switch). grep «anno_precedente|"q1"|"h1"» nei .tsx: nessun chip. Il server usa oggiARoma() in entrambe le page (margini/page.tsx:52, analisi-fatture/page.tsx:61).

**numeri attesi vs mostrati.** Nessuna differenza sui preset raggiungibili.

**fix proposto.** analisi-fatture/periodi.ts ri-esporta calcolaPeriodo/calcolaMese da margini/periodi.ts (o entrambi da lib/periodo.ts), così la seconda copia non può più divergere; il whitelist di analisi-fatture/page.tsx resta.

**presidio proposto.** Test con node che esegue entrambe le esportazioni sugli stessi preset e date e pretende uguaglianza (muore se la copia torna).

**gia presidiato da.** tests/test_margini_periodi_frontend.py (13 preset della copia Margini); tests/test_periodo_giorno_di_roma_frontend.py (oggiARoma in entrambe le page); tests/test_periodo_fonte_unica_frontend.py copre lib/periodo, non queste due copie.

**file e righe.** `apps/web/src/app/(app)/margini/periodi.ts:30-68`; `apps/web/src/app/(app)/analisi-fatture/periodi.ts:22-47`; `apps/web/src/app/(app)/margini/page.tsx:47-55`; `apps/web/src/app/(app)/analisi-fatture/page.tsx:48-63`; `apps/web/src/app/(app)/margini/filtri-periodo.tsx:70-86`; `apps/web/src/app/(app)/analisi-fatture/filtri-periodo.tsx:90-106`

### F1e-11 — Chat query_margini manda MOL e food cost senza il flag costi_mancanti che Home e briefing usano per non giudicare

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Chat (sede e catena via ristorante_id): risposta dell'AI su «com'è andato il MOL». Account con un mese a ricavi inseriti e fatture merce non ancora caricate.

**prova.** fastapi_worker.py:5330-5337: chiavi `mese, fatturato, food_cost_pct, mol, parziale`; :5355-5358 aggiunge solo `incasso_fuori_norma`/`nota`. _kpi_periodo calcola `costi_mancanti` (:9868) e la Home lo usa per colorare in giallo e sopprimere i delta (:9991-9995, tintContiPV); il briefing tace (_briefing_mese_chiuso). La descrizione del tool (:5519-5524) non avverte. Un mese con costi_mancanti arriva all'AI come MOL positivo e food cost 0% senza spiegazione.

**numeri attesi vs mostrati.** Mese con ricavi 40.000 netti e costi 0: la chat riceve mol ≈ 40.000 − personale, food_cost_pct 0.0, nessun avviso; la Home lo mostra giallo con banner.

**fix proposto.** Aggiungere `"costi_mancanti": k["costi_mancanti"]` e, quando vero, una `nota` («mese senza fatture merce: MOL e food cost non sono reali») come già fatto per incasso_fuori_norma; nel prompt dire di non festeggiare quel MOL.

**presidio proposto.** Test worker su _chat_query_margini con margini mockati (ricavi > 0, costi F&B 0): la voce del mese porta costi_mancanti=True e la nota; mutante: togliere la chiave.

**gia presidiato da.** Nessuno: tests/test_fase_e_incasso_fuori_norma.py:232-255 asserisce solo incasso_fuori_norma/nota/parziale; grep costi_mancanti nei test_chat_*.py vuoto.

**file e righe.** `services/fastapi_worker.py:5330-5337`; `services/fastapi_worker.py:5355-5358`; `services/fastapi_worker.py:9868`; `services/fastapi_worker.py:9991-9995`

### F1e-12 — gruppo_salute_componenti chiama `netto` una somma lorda: oggi usata solo come presenza (> 0), ma il nome invita a dividerci sopra

Filone 1 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuno oggi: tutti i consumatori la confrontano con zero.

**prova.** SQL 20261004083133_personale_chiamata.sql:147-149 `sum(fatturato_iva10 + fatturato_iva22 + altri_ricavi_noiva) AS netto` senza /1.10 e /1.22 (ultima definizione: nessuna migration successiva la ridefinisce). Consumatori: gruppo.py:912 `netto = float(r.get("netto") or 0)` → :924 `100 if netto > 0 else 0`; :2175 `<= 0` nella completezza; :772 _applica_override_netto scrive il lordo di proposito (docstring :742-746 lo riconosce). Nessun `/ netto` su quella colonna.

**numeri attesi vs mostrati.** Nessuna differenza a video.

**fix proposto.** Rinominare la colonna in `ricavi_lordi` (migration + gruppo.py + test) oppure scorporare davvero; finché resta «netto» un futuro MOL/netto calcolato da lì sarebbe sottostimato di 10-22%.

**presidio proposto.** Test -m sql: su un mese con iva10=1100, iva22=1220 la colonna rinominata vale 2320 (lordo) e un grep nel sorgente di gruppo.py vieta `/ r["netto"]` sulle righe della RPC.

**gia presidiato da.** tests/test_gruppo_completezza_override.py:38-51 (override sostituisce il netto a zero: prova il valore, non il significato); tests/test_salute_gruppo_formula_condivisa.

**file e righe.** `supabase/migrations/20261004083133_personale_chiamata.sql:147-149`; `services/routers/gruppo.py:742-746`; `services/routers/gruppo.py:772`; `services/routers/gruppo.py:912-924`; `services/routers/gruppo.py:2175`

### F1e-13 — Esclusione NOTE: SQL e pandas escludono solo '📝 NOTE E DICITURE', il Python di Margini anche 'NOTE E DICITURE' senza emoji e categoria vuota — la vuota non può esistere, la senza-emoji sì

Filone 1 · falso allarme · gravità bassa · confidenza media

**chi lo vede.** In teoria Home/catena (SQL) vs Ricavi e Margini (Python) sullo stesso mese, solo se esiste una riga con categoria 'NOTE E DICITURE' senza emoji e totale_riga ≠ 0; con la regola #2 (NOTE solo a importo 0) il contributo sarebbe comunque 0.

**prova.** SQL costi_automatici_mensili (20260912075621_oscura_fattura.sql:136-137) `categoria <> '📝 NOTE E DICITURE'`; pandas (margine_service.py:138-142) idem; Python _calcola_costi_auto_per_mese (fastapi_worker.py:10915-10920) ed _…_per_periodo (:10992-10997) `elif cat and cat not in CATEGORIE_NOTE_WORKER` con CATEGORIE_NOTE_WORKER = {'📝 NOTE E DICITURE', 'NOTE E DICITURE'} (:10314). Constraint fatture_categoria_not_empty_chk (20260901160000_annulla_enforce_no_unclassified.sql:29-31) `categoria is not null and btrim(categoria) <> ''` → la categoria vuota è impossibile a DB (il ramo `cat and` è morto); 'NOTE E DICITURE' senza emoji passa il constraint: se esiste, SQL la conta come F&B e Python no. Esistenza a DB non verificabile in questo filone.

**numeri attesi vs mostrati.** Nessuna differenza salvo righe con categoria 'NOTE E DICITURE' senza emoji e importo ≠ 0, la cui esistenza non è stata misurata.

**fix proposto.** Allineare la RPC alla lista Python (`categoria <> ALL(ARRAY['📝 NOTE E DICITURE','NOTE E DICITURE'])`) o, meglio, misurare a DB se la grafia senza emoji esiste e normalizzarla; togliere il ramo `cat and` ridondante.

**presidio proposto.** Query (altro filone): SELECT count(*) FROM fatture WHERE categoria = 'NOTE E DICITURE' AND deleted_at IS NULL; test -m sql che inserisce una riga 'NOTE E DICITURE' con importo e verifica che la RPC la tratti come il Python.

**gia presidiato da.** tests/test_costi_automatici_rpc_catchall.py:90 (equivalenza Python/pandas solo con l'emoji); tests/test_da_classificare_sql_allineato.py (allinea la stringa 'Da Classificare', non le NOTE).

**file e righe.** `supabase/migrations/20260912075621_oscura_fattura.sql:136-137`; `services/margine_service.py:138-142`; `services/fastapi_worker.py:10314`; `services/fastapi_worker.py:10915-10920`; `services/fastapi_worker.py:10992-10997`; `supabase/migrations/20260901160000_annulla_enforce_no_unclassified.sql:29-31`

### F1e-14 — Percorsi senza chiamanti confermati: GET /api/margini (anno UTC, senza override), /api/dashboard/stats, GruppoKpi.spesa_fornitori e RankingPV.colore

Filone 1 · falso allarme · gravità bassa · confidenza alta

**chi lo vede.** Nessuno: nessun .tsx li chiama o li rende. Rischio futuro: un nuovo chiamante di GET /api/margini leggerebbe l'anno in UTC e senza ricavi in modalità mensile.

**prova.** margini.py:169-176 `anno = _dt.now().year` (UTC su Railway) e nessun _merge_override_mensile; lib/margini.ts:76 fetchMarginiAnno definita, grep in apps/web/src senza altri match. fastapi_worker.py:1467 dashboard_stats via RPC dashboard_stats_aggregata; lib/dashboard.ts:24 fetchDashboardStats definita, dashboard/page.tsx:102 commenta che non è più chiamata, nessun altro match. gruppo.py:1229 spesa_fornitori=tot_fb, lib/gruppo.ts:9 solo nel tipo. gruppo.py:1266 colore=_colore_margine(...), grep `r.colore|ranking.*colore` nei .tsx vuoto (sintesi-catena.tsx:284 usa pv.colore della salute).

**numeri attesi vs mostrati.** Nessuna differenza a video.

**fix proposto.** Rimuovere GET /api/margini, fetchMarginiAnno, fetchDashboardStats (e la RPC se non ha altri usi), spesa_fornitori e colore dal payload, o dichiararli deprecati nel presidio delle rotte; se GET /api/margini deve restare, usare _oggi_rome() e _merge_override_mensile.

**presidio proposto.** Test sul sorgente che elenca le funzioni esportate da lib/*.ts senza import in apps/web/src (strumento costruito e mai collegato), come già fatto per altri presidi statici.

**gia presidiato da.** Nessuno.

**file e righe.** `services/routers/margini.py:169-176`; `apps/web/src/lib/margini.ts:76`; `services/fastapi_worker.py:1467-1500`; `apps/web/src/lib/dashboard.ts:24`; `apps/web/src/app/(app)/dashboard/page.tsx:102`; `services/routers/gruppo.py:1229`; `services/routers/gruppo.py:1266`; `apps/web/src/lib/gruppo.ts:9`

### Verificato e trovato giusto

- /m mobile-catena.tsx colore inline (:61, :68-70, :160 `affidabile ? (molPos ? verde : rosso) : giallo` con affidabile da metricaPrincipaleConti) = tintConti di lib/catena-confronti.ts:347 su 7 casi eseguiti con node (completo ±, food, nessuno, campo assente, incasso_fuori_norma): tutti UGUALI.
- tintContiPV (catena-confronti.ts:369-379) eseguita: {mol:1300}=verde, {mol:-500}=rosso, costi_mancanti=true → giallo in entrambi i segni, incasso_fuori_norma=true → giallo; la Home usa SALUTE_TINT[tintContiPV(kpi)] (kpi-block.tsx:66) coerente col banner.
- Periodi dichiarati a video: Home `periodo_label` = mese («Settembre») o «Ottobre · in corso» (worker :10043-10045, fallback 6 mesi :9940-9966); catena `_label_anno_parziale` (gruppo.py:1067-1079) dice l'arco e il mese parziale; Margini/Analisi Fatture chip «Anno in corso» (filtri-periodo :73/:93) con calcolaPeriodo(oggiARoma()); chat query_margini marca `parziale` sul mese corrente (:5337) e `incasso_fuori_norma` (:5355-5358).
- Le due calcolaPeriodo coincidono sui 4 preset raggiungibili anche alle 00:30 del 1° ottobre (Europe/Rome e UTC con la stessa Date): mese_corrente 2026-10-01..2026-10-01, anno_corrente 2026-01-01..2026-10-01.
- KPI_SOGLIE (constants.py:1914) e _KPI_SOGLIE_MARGINI (margini.py:834) danno lo stesso emoji per ogni valore eseguito (4, 7, 10, 13, 18, 25) su tutte le chiavi: il tetto 100 vs 200 non cambia l'esito (fallthrough su soglie[-1]).
- Analisi Fatture nettizza le note di credito (fatture.py:393-400, righe negative sommate) come gruppo_tag_analisi (sum(totale_riga)) e costi_automatici_mensili (nessun filtro di segno).
- Worker /api/scadenziario/calendario (routers/scadenziario.py:143-151) esclude pagate, NC e oscurate — coerente con statoDocumento (lib :559-568), scaduteFuoriDalMese (:591-608, eseguita: 0 sul dataset) e computeKpi (eseguita: da_pagare_totale 1100 = solo la fattura aperta).
- costi_automatici_mensili SQL (oscura_fattura.sql:111-140, ultima definizione) e fallback pandas (margine_service.py:138-142) hanno gli stessi filtri: deleted_at, NOT oscurata, <> 'Da Classificare', NOT ripartita_su_gruppo, COALESCE(data_competenza,data_documento), F&B = tutto tranne spese e '📝 NOTE E DICITURE'.
- Il ramo `cat and` del Python di Margini (worker :10919, :10996) è reso irraggiungibile dal constraint fatture_categoria_not_empty_chk (20260901160000:29-31): nessuna divergenza possibile sulla categoria vuota.
- Tutti i consumatori della colonna `netto` di gruppo_salute_componenti sono di sola presenza (gruppo.py:912/924, :2175) e l'override (:772) scrive il lordo coerentemente.
- Etichette con base dichiarata: Margini «Fatturato Netto» + sub «lordo …» (kpi-bar.tsx:219); catena Sintesi «Fatturato (IVA incl.)» (sintesi-catena.tsx:238); catena Margini e coperti tooltip «al netto dell'IVA» (scheda-margini-coperti.tsx:65-67).
- Catena «Margini e coperti» (gruppo.py:1610-1631) è tutta su base netta (fatturato, margine %, scontrino medio = netto/coperti) e il lordo resta nei «conti del gruppo» (:1227): coerente al suo interno.
- git status --porcelain identico a inizio e fine lavoro; nessun file toccato nel repo; scratch sotto scratchpad/audit/f1e cancellato.

### Non verificabile in sola lettura

- Quanti documenti dello scadenziario cadono nel fallback «somma righe» (nessuna riga in fatture_documenti): servirebbe una query su fatture_documenti vs fatture per user_id/ristorante_id (filone senza DB).
- Se a DB esistono righe con categoria 'NOTE E DICITURE' senza emoji (o 'Da Clasificare') con totale_riga ≠ 0: la divergenza SQL/Python del punto 10 è concreta solo in quel caso.
- Gli ID dei clienti toccati da ciascun finding: filone solo codice, nessuna misura per account; tutti i finding valgono per ogni account che ha i dati descritti (NC, oscurate, mese senza costi, catena).
- La differenza numerica reale fra «Spesa totale» di Analisi Fatture e i costi di Margini per un mese dato (righe Da Classificare e data_competenza ≠ data_documento): va misurata a DB.
- Il comportamento del gauge MOL su un mese reale con costi mancanti (F1e-03): confermato nel codice, non riprodotto su un account.

## F1d scadenziario a DB

### F1d-01 — Archivio «Per mese»: l'intestazione del mese somma le note di credito come costi positivi (A: +37.453,54 EUR su 7 mesi)

Filone 1 · bug vero · gravità media · confidenza alta

**chi lo vede.** Gestione Fatture, vista Archivio/«Per mese» (AgendaSection intestazione: count = docs.length, totale = somma totale_documento di tutti i docs). Vista singola sede e vista gruppo (catena/fatture riusa ScadenziarioClient). Toccati: A 51015cc8 (tutte le 4 sedi con fatture: fd7ac484, cc016821, 5444e918, 0dca4d1f) e C 79920814/f16aebe5.

**prova.** SQL (CTE che ricostruisce get_documenti_scadenziario) per A, gruppo per mese di data_documento: 2026-05 n=574 tot_header=886.132,71 con 22 NC per +6.888,83 (le righe nette delle stesse NC valgono −6.168,88); 2026-06 765.726,03 con 18 NC +9.371,60; 2026-07 446.383,49 con 13 NC +4.920,76; 2026-04 +6.262,05; 2026-03 +5.400,43; 2026-02 +3.253,85; 2026-01 +1.356,02. Totale NC sommate in positivo su A: 37.453,54 EUR (= bucket noteCredito di bucketizeDocumenti eseguito con node: 106 doc, 37.453,54). C: 2026-06 header 6.980,20 include la NC AXPO +468,10 (righe nette −383,69); 2026-08 header 5.932,14 include NC +6,00. Esecuzione node di raggruppaPerMeseFattura sui 2582 documenti reali di A restituisce esattamente gli stessi header (2026-05: count 574, totale 886.132,71), quindi la funzione non esclude ne' nettizza le NC. Il totale_documento delle NC arriva da fatture_documenti.totale_documento (ImportoTotaleDocumento XML, positivo) mentre in Analisi Fatture le NC sono nettizzate (routers/fatture.py).

**numeri attesi vs mostrati.** A, maggio 2026: mostrato 886.132,71 EUR; sottraendo le 22 NC (lordo) sarebbe 872.355,05 EUR (oppure 879.243,88 se le NC fossero semplicemente escluse). Su tutto l'archivio di A lo scarto e' 2x37.453,54 = 74.907,08 EUR se le NC vanno sottratte. C, giugno 2026: mostrato 6.980,20, atteso 6.044,00 (o 6.512,10 escludendole).

**fix proposto.** In raggruppaPerMeseFattura (o nell'intestazione dell'Archivio) trattare le NC con segno negativo (totale -= totale_documento quando is_nota_credito) oppure escluderle dal totale e mostrarle a parte come fa bucketizeDocumenti; decidere la stessa convenzione di Analisi Fatture (nettizza).

**presidio proposto.** test in test_scadenziario_vista_mensile_frontend.py: un mese con una fattura da 100 e una NC da 30 deve dare totale 70 (o 100 se si sceglie di escluderla), mutante: rimuovere il ramo is_nota_credito -> 130.

**gia presidiato da.** tests/test_scadenziario_vista_mensile_frontend.py copre raggruppaPerMeseFattura solo con is_nota_credito=False (riga 38): nessun test con una NC nel mese. MAPPA_NUMERI A.4 lo segnalava come sospetto, ora misurato.

**file e righe.** `apps/web/src/lib/scadenziario.ts:840-887 (raggruppaPerMeseFattura: nessuna esclusione, totale = somma di tutti i docs)`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:285-308 (AgendaSection: totale = docs.reduce, badge docs.length)`; `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:2516-2535 (vista lista_mensile usa gruppiMensili senza filtro)`; `services/documenti_service.py:810-816 (totale_documento preferisce fatture_documenti, positivo anche per TD04)`

### F1d-02 — «Pagate (mese)» ignora le fatture pagate per regola RID: pagata=true ma pagata_at NULL (C: 30 doc / 5.695,30 EUR, di cui 3 di ottobre per 205,89)

Filone 1 · stessa etichetta per grandezze diverse · gravità bassa · confidenza alta

**chi lo vede.** Card «Pagate (mese)» di Gestione Fatture (computeKpi), vista singola sede e gruppo. Toccati: C 79920814/f16aebe5 (30 doc RID su 108 pagate) e A 51015cc8 sede fd7ac484 (25 doc RID su 36 pagate, 99.535,74 EUR, nessuno con data in ottobre).

**prova.** SQL: fatture_documenti con regola attiva modalita='rid', pagata_manuale_at NULL e pagata=false a DB: C 30 doc (6.163,40 lordo, 5.695,30 senza la NC AXPO), di cui 3 con data_documento in ottobre 2026 (205,89 EUR); A 25 doc (99.565,64 lordo). get_documenti_scadenziario (documenti_service.py:845-847) li marca pagata=True ma pagata_at resta None (:819). Esecuzione node di computeKpi sui 110 documenti reali di C: pagate_mese_count=19, pagate_mese_totale=11.648,49 — le 3 RID di ottobre (fo 2026-10-01 85,13; 2026-10-02 14,64; 2026-10-07 106,12) non entrano perche' parseLocalDate(null) -> null (:333-337). bucketizeDocumenti le mette invece nella sezione «Pagate» (108 doc / 53.238,13). Lo stesso SQL conferma: pagata_eff_senza_at C=30, A=25.

**numeri attesi vs mostrati.** C, ottobre 2026: mostrato 19 doc / 11.648,49 EUR; se le RID valessero 'pagate alla data documento' sarebbero 22 doc / 11.854,38 EUR. La sezione «Pagate» della stessa pagina conta 108 doc, la card del mese non potra' mai includere le RID.

**fix proposto.** Decidere la semantica: o la card dichiara «Pagate (mese) — solo pagamenti registrati» oppure il worker valorizza pagata_at con la data documento (o la scadenza RID) per le fatture RID, cosi' la card e la sezione «Pagate» parlano della stessa popolazione.

**presidio proposto.** test_scadenziario_kpi_frontend.py: documento pagata=True, pagata_at=None, data_documento nel mese -> dichiarare esplicitamente se entra o no in pagate_mese (oggi: no), cosi' la scelta e' scritta e non implicita.

**gia presidiato da.** tests/test_documenti_service_rid_e_regole.py:232-300 fissa pagata=True per RID ma non pagata_at; tests/test_scadenziario_kpi_frontend.py non ha un documento pagata=True con pagata_at=None.

**file e righe.** `apps/web/src/lib/scadenziario.ts:333-341 (computeKpi: pagate_mese solo se pagata_at >= primoMese)`; `services/documenti_service.py:819 (pagata_at = _to_date_iso(extra.pagata_at) -> None per le RID)`; `services/documenti_service.py:843-847 (RID forza pagata=True senza data)`

### F1d-03 — Calendario in pagina (CalendarView) non esclude le oscurate, a differenza di KPI, bucket, scaduteFuoriDalMese ed endpoint worker — oggi senza impatto (0 documenti oscurati con scadenza)

Filone 4 · bug vero · gravità bassa · confidenza media

**chi lo vede.** Gestione Fatture, vista Calendario (griglia mensile) — singola sede e gruppo. Nessun account toccato oggi: A e C hanno 0 documenti oscurati; in tutto il DB c'e' 1 documento oscurato (user 080004f3) senza scadenza in ottobre o futura.

**prova.** Codice: scadenziario-client.tsx:497-506 salta solo doc.pagata e doc.is_nota_credito; lib statoDocumento (:559) e scaduteFuoriDalMese (:584) e routers/scadenziario.py:148-156 saltano anche oscurata. SQL: osc=0 per tutte le 5 sedi di A e per C (CTE, count FILTER oscurata); query globale su fatture.oscurata=true: 1 documento, osc_scad_ottobre_non_pagate=0, osc_scad_futura_non_pagate=0.

**numeri attesi vs mostrati.** Oggi nessuno scarto misurabile (0 oscurate con scadenza). Con un'oscurata di X EUR scadente nel mese, la casella del giorno mostrerebbe X in piu' rispetto a KPI e sezioni.

**fix proposto.** Aggiungere `if (doc.oscurata) continue;` in CalendarView (o calcolare la griglia con statoDocumento !== 'Escluse da te'), oppure far consumare al client l'endpoint worker gia' corretto.

**presidio proposto.** Estrarre l'aggregazione per giorno del calendario in lib/scadenziario.ts (es. aggregaPerGiorno) e testarla con un'oscurata nel mese.

**gia presidiato da.** tests/test_scadenziario_calendario_fuori_mese_frontend.py:102 copre scaduteFuoriDalMese (lib), non CalendarView (componente .tsx, fuori dalla rete).

**file e righe.** `apps/web/src/app/(app)/scadenziario/scadenziario-client.tsx:497-506 (CalendarView agg: manca `if (doc.oscurata) continue`)`; `apps/web/src/lib/scadenziario.ts:559-567 (statoDocumento esclude oscurata)`; `services/routers/scadenziario.py:148-156 (endpoint calendario esclude oscurata)`

### F1d-04 — totale_incoerente confronta lordo IVA (fatture_documenti) con netto righe: vero per 2557/2582 documenti di A e 105/110 di C; il flag non e' reso da nessun componente

Filone 1 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Nessuno a video: il campo viaggia nel payload di /api/scadenziario e /api/gruppo/scadenziario ed e' dichiarato nel tipo Documento, ma nessun .tsx lo legge (grep su apps/web/src: solo lib/scadenziario.ts:11). Account misurati: A 51015cc8 e C 79920814.

**prova.** SQL (CTE): count FILTER (hdr AND tdoc<>0 AND abs(tdoc-totale_righe)>0.01) = 2557 su 2582 (A: 1064/1082, 578/581, 466/467, 449/452) e 105/110 (C). documenti_service.py:814-815 calcola totale_incoerente = abs(totale_doc - totale_righe) > 0.01 dove totale_doc e' ImportoTotaleDocumento (IVA inclusa) e totale_righe la somma dei totale_riga (netti).

**numeri attesi vs mostrati.** Flag pensato per segnalare righe soft-deleted/ripartizioni: dovrebbe essere raro; e' vero nel 99% dei casi perche' misura l'IVA.

**fix proposto.** Confrontare totale_documento con totale_imponibile (o con la somma righe + IVA) oppure rimuovere il campo dal payload finche' non ha un consumatore.

**presidio proposto.** Se si tiene: test in test_documenti_service_scadenziario.py con totale_documento = imponibile+IVA e righe = imponibile -> totale_incoerente False.

**gia presidiato da.** nessun test cerca totale_incoerente (grep tests/: nessuna occorrenza).

**file e righe.** `services/documenti_service.py:810-815`; `apps/web/src/lib/scadenziario.ts:11`

### Verificato e trovato giusto

- Popolazione dello scadenziario ricostruita a DB = output della lib eseguita con node sui documenti reali (A gruppo 2582 doc, A sede fd7ac484 1082, C 110): nessuno scarto su nessun numero.
- A vista gruppo (5 PV attivi, nessuna sede tecnica a DB: sede_tecnica=false per tutte le righe di ristoranti di 51015cc8): Scadute 1714 / 2.945.907,96; Questa settimana 0 / 0; Da pagare 2437 / 3.756.242,76 (di cui senza scadenza 723 / 810.334,80); Pagate (mese) 0 / 0; «2437 fatture da pagare»; «Seleziona tutte (2437)»; archivio 7 mesi (gen-lug 2026, nessun doc senza data). SQL e computeKpi/contaDaPagare/chiaviSelezionaTutte/bucketizeDocumenti coincidono.
- A vista singola sede fd7ac484 (la sede con piu' documenti, 1082): Scadute 629 / 1.230.735,00; settimana 0; Da pagare 995 / 1.712.814,52 (senza scadenza 366 / 482.079,52); Pagate (mese) 0; NC 51; pagate 36 (25 RID); «Seleziona tutte (995)». SQL = node.
- C (f16aebe5, 110 doc): Da pagare 0 (tutto pagato: 78 manuali + 30 RID), Scadute 0, settimana 0, Pagate (mese) 19 / 11.648,49, NC 2, «Seleziona tutte» non compare (0 selezionabili). SQL = node.
- Vista gruppo, tendina per sede (aggregaPerSede con periodo 'tutti'): 995+563+450+429 = 2437 e 1.712.814,52+784.224,60+632.837,75+626.365,89 = 3.756.242,76 = card Da pagare; con periodo 'scadute': 629+438+332+315 = 1714 e somma 2.945.907,96 = card Scadute. Il PV senza fatture (0c23548c) manca dalla Map e il client lo mostra a 0 (`?? 0`).
- (a) file_origine presenti su piu' sedi dello stesso account A: 0 (SQL GROUP BY file_origine HAVING count>1 sulla popolazione gruppo). chiaviSelezionaTutte(...).length = 2437 = chiavi distinte 2437: oggi un click seleziona esattamente 2437 righe. La selezione per solo file_origine resta strutturalmente fragile (lib:158, client:1817), ma senza dati che la colpiscano.
- (b) base IVA mista: A 0 documenti senza header, 2 con totale_documento=0 che cadono sulla somma righe (0,02 EUR e 0,00 EUR, entrambi in Da pagare); C 0 e 0. Peso sui riquadri: 0,02 EUR su 3.756.242,76.
- (d) pagata=true con pagata_at NULL a DB: 0 (A e C); pagata_at valorizzato con pagata=false: 0; pagata_at nel futuro: 0. L'unica popolazione 'pagata senza data' e' quella RID (finding F1d-02).
- (e) scadenza_effettiva NULL con scadenza_xml o giorni_termini_xml presenti: 0 (A e C). Dove la pagina calcola una scadenza diversa da quella salvata (A 236, C 41) e' sempre per regola fornitore/RID applicata a lettura (scad_diversa_non_regola = 0): il percorso xml della lib coincide con la colonna salvata.
- Nessun consumatore legge fatture_documenti.scadenza_effettiva/pagata direttamente: chat (_chat_query_scadenze, fastapi_worker.py:4875), endpoint calendario (routers/scadenziario.py:148) e pagina passano tutti da get_documenti_scadenziario, quindi le 236+41 scadenze ricalcolate da regola non divergono fra superfici.
- Filtri periodo: computeKpi su filtraDocumenti(periodo='scadute') per A gruppo da «1714 su 2437 fatture da pagare» e card Scadute=Da pagare=1714 (coerente con la nota della mappa: le card si ricalcolano sulla lista filtrata); periodo 'settimana' e 'mese' danno 0 perche' A non ha scadenze fra il 15/10 e il 14/11/2026.
- scaduteFuoriDalMese(ottobre 2026) per A = 1714 / 2.945.907,96 (= tutte le scadute: nessuna cade in ottobre), per la sede fd7ac484 629, per C 0: il calendario spiega correttamente la griglia vuota.
- RPC scadenziario_fatture_aggregate: corpo letto con pg_get_functiondef, solo SELECT (SECURITY DEFINER con guardia auth.role): la chiamata diretta via MCP e' rifiutata ('Accesso negato', auth.role() non e' service_role) e il corpo e' stato replicato verbatim nella CTE; fatture_documenti attive senza duplicati (fo, ristorante_id) per tutte le sedi misurate (n_dup=0).
- Regole fornitore applicate dalla CTE come _applica_regole_fornitore: A fd7ac484 4 regole (2 rid, 30gg, 60gg) + 0dca4d1f 1 regola 60gg; C 6 regole rid; tutte con modalita valorizzata (nessun ramo legacy giorni_pagamento).

### Non verificabile in sola lettura

- Calendario con documenti oscurati: nessun account ha un'oscurata con scadenza (A e C 0, intero DB 1 senza scadenza futura), quindi lo scarto a video di CalendarView non e' misurabile sui dati; il finding F1d-03 si basa sul confronto fra codice e sul conteggio 0.
- Selezione per solo file_origine con duplicati fra sedi (A: 0 file_origine su piu' sedi): l'effetto 'un click seleziona due righe' non e' riproducibile sui dati di produzione senza creare un documento di prova.
- Chiamata reale della RPC scadenziario_fatture_aggregate via MCP: rifiutata dalla guardia auth.role() (non service_role); verificata replicandone il corpo SELECT.
- Rendering React (badge, testo «X su Y», intestazioni): non eseguibile senza avviare Next; verificato per lettura del .tsx e per esecuzione delle funzioni di lib che alimentano quei testi.

## F2a sotto-utenti backend+SQL

### F2a-1 — POST /api/notifiche/{id}/dismiss: un sotto-utente senza la pagina archivia una notifica che non vede, e il titolare la perde

Filone 2 · bug vero · gravità media · confidenza alta

**chi lo vede.** Titolare dell'account (campanella /notifiche, /m/notifiche, Home di catena /api/gruppo/notifiche): la notifica sparisce dalla sua inbox (include_dismissed=False). Nessun account toccato oggi: 0 sotto-utenti in produzione (SELECT count(*) FROM sotto_utenti = 0). Vale per qualunque account a cui l'admin crei un sotto-utente senza Home.

**prova.** Sonda su Postgres locale (scratchpad/audit/F2a/test_sonda.py::test_sonda_dismiss_senza_la_pagina_archivia_anche_per_il_titolare): sotto-utente con {analisi_fatture: True} su sede1, notifica con action_page='/margini' sulla stessa sede. GET /api/notifiche del sotto-utente NON la contiene (notifica_visibile la filtra), il titolare sì; POST /api/notifiche/{id}/dismiss dal sotto-utente -> 200; dismissed_at=2026-10-15 08:37:52 UTC; dopo, il titolare non la vede più (titolare_la_vede_dopo=False). Codice: fastapi_worker.py:2924-2929 filtra solo .eq(user_id).in_(ristorante_id, sedi_consentite), mai notifica_visibile; la lista (fw:2791-2793) e la catena (gruppo.py:2677-2678) la applicano. L'id è uuid (information_schema.columns notification_inbox.id = uuid), quindi serve conoscere l'id: lo sfruttamento pratico è basso ma l'inbox dell'account è condivisa e l'azione va oltre ciò che la lista concede.

**numeri attesi vs mostrati.** atteso dismissed_at NULL (notifica non visibile al chiamante); ottenuto dismissed_at valorizzato e notifica sparita per il titolare

**fix proposto.** In dismiss_notifica, per un sotto-utente leggere prima la riga (id, user_id, ristorante_id, action_page) con gli stessi filtri e applicare notifica_visibile(user, action_page): se False rispondere 200 senza scrivere (come per la sede altrui) o 404. Così lista e azione usano lo stesso predicato.

**presidio proposto.** Test -m sql in tests/test_sql_sotto_utenti.py accanto a test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto: sotto-utente senza Home e senza Margini, notifica /margini sulla sua sede, dismiss -> dismissed_at resta NULL e il titolare la vede ancora (la sonda scritta è già questo test, oggi rosso).

**gia presidiato da.** tests/test_sql_sotto_utenti.py::test_archiviare_una_notifica_di_un_altra_sede_non_ha_effetto copre solo la sede, non la pagina; tests/test_permessi_rotte.py:252-285 prova notifica_visibile da sola. Nessun test sul dismiss per pagina.

**file e righe.** `services/fastapi_worker.py:2908-2931`; `services/permessi_rotte.py:365-376`; `services/fastapi_worker.py:2791-2793`

### F2a-2 — GET /api/home/config è rotta comune: un sotto-utente senza Home riceve contatori e tetti AI dell'account, soglia alert prezzi e nome referente

Filone 2 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Sotto-utente senza Home (desktop e /m: il layout di /m la chiama su ogni pagina). Espone dati dell'account che le Impostazioni gli nascondono (regola «solo in meno», memoria 3/10). 0 sotto-utenti in produzione oggi.

**prova.** Sonda test_sonda_home_config_senza_home: sotto-utente con la sola analisi_fatture: GET /api/home/briefing -> 403 (coerente), GET /api/home/config -> 200 con chat_ai_enabled, chat_limite_giorno=150, chat_limite_mese=1500, chat_crediti_oggi/mese/ricarica, price_alert_threshold=5.0, alert_prezzi_solo_preferiti, giorni_chiusura_settimanali, nome_referente, 15 topics con enabled. Codice: permessi_rotte.py:277 la dichiara in ROTTE_COMUNI; fastapi_worker.py:10083-10155 non distingue il sotto-utente e chiama _chat_quota_pool, _chat_budget_mensile_pool, _chat_crediti_stato (sempre col titolare) e get_price_alert_threshold. Nessun dato di fattura o di margine; i tetti rivelano il piano dell'account.

**numeri attesi vs mostrati.** atteso: niente tetti/crediti AI né soglia alert a chi non ha la Home; mostrato: chat_limite_giorno=150, chat_limite_mese=1500, price_alert_threshold=5.0

**fix proposto.** Per un sotto-utente senza Home rispondere con un ConfigResponse ridotto (chat_ai_enabled=False, tetti e crediti a 0, topics=[], price_alert_threshold di default) oppure lasciare la rotta comune ma calcolare la parte AI/soglia solo se _su.ha_pagina(user, PAGINA_HOME); il layout di /m ha bisogno solo di chat_ai_enabled/chat_limite_giorno, che a chi non ha Home devono già dire «chat spenta».

**presidio proposto.** Test -m sql: sotto-utente senza Home -> /api/home/config non contiene chat_limite_giorno>0, chat_limite_mese, crediti né price_alert_threshold dell'account; con Home -> uguale al titolare. Mutante: togliere il ramo ridotto.

**gia presidiato da.** Nessuno: tests/test_home_config_chat_quota.py e test_isolamento_per_risorsa.py non hanno un caso sotto-utente su home/config (grep 'sotto' = 0 righe).

**file e righe.** `services/permessi_rotte.py:276-277`; `services/fastapi_worker.py:10077-10155`; `apps/web/src/app/(mobile)/m/layout.tsx:76-83`

### F2a-3 — Chat di catena con la sola Catena (senza Home): il worker e /catena desktop la accettano, /m la nasconde

Filone 3 · stessa etichetta per grandezze diverse · gravità bassa · confidenza alta

**chi lo vede.** Sotto-utente con catena=True e home=False: su desktop /catena ha il widget chat (page.tsx:62-65 solo chatCatenaAttiva, nessun haHome), su /m la tab /m/chat è nascosta anche in vista catena (sotto-utente.ts:63-71 TAB_MOBILE_HOME richiede haHome). Stessa persona, due risposte. 0 sotto-utenti in produzione.

**prova.** Sonda test_sonda_chat_catena_con_sola_catena_senza_home: sotto-utente {catena: True} su tutte le sedi: POST /api/chat contesto=sede -> 403 «Assistente non consentito»; contesto=catena -> supera il gate (418 iniettato su _chat_quota_pool, prima di OpenAI). Regola voluta: CHAT_ASSISTENTE.md:239-241 «La chat di sede richiede la pagina home, quella di catena la Catena effettiva»; permessi_rotte.py:213-214 _p(H, C); commit 46ab02a chiude il residuo «chat di catena senza Catena» (AUDIT_COPERTURA:1550). La doc dice anche «Home = accesso all'AI» (sotto_utenti_service.py:37), che contraddice la chat di catena con la sola C: le due frasi convivono nel repo.

**numeri attesi vs mostrati.** worker: catena con sola C passa il gate; /m: tab chat nascosta senza Home

**fix proposto.** Decisione di Mattia: o «Home = accesso all'AI» (allora /api/chat in catena richiede anche H e /catena desktop nasconde il widget senza Home) oppure «la Catena include la chat di catena» (allora vedeTabMobile mostra /m/chat in vista catena a chi ha la Catena). Poi allineare la frase di sotto_utenti_service.py:37 e §5bis.

**presidio proposto.** Test TS in tests/test_sotto_utente_frontend.py: utente {catena, no home} in vista catena -> vedeTabMobile('/m/chat') coerente con la regola scelta; test -m sql già esistente (test_chat_rifiutata_per_contesto_prima_della_quota) da estendere col caso catena-senza-home atteso (403 o pass).

**gia presidiato da.** tests/test_sql_sotto_utenti.py:655-671 (solo i tre casi rifiutati); tests/test_sotto_utente_frontend.py (tab mobile) — nessuno confronta i due fronti.

**file e righe.** `services/fastapi_worker.py:6149-6152`; `services/permessi_rotte.py:213-214`; `apps/web/src/lib/sotto-utente.ts:63-71`; `apps/web/src/app/(app)/catena/page.tsx:62-65`; `DOCUMENTAZIONE/tecnica/CHAT_ASSISTENTE.md:239-241`

### F2a-4 — apps/web/src/app/api/tts/route.ts accetta qualunque cookie non vuoto: proxy TTS verso Google senza validare la sessione

Filone 2 · bug vero · gravità bassa · confidenza alta

**chi lo vede.** Nessun cliente: la route non serve dati (il testo lo manda il client, max 600 caratteri) e non costa (servizio translate_tts non ufficiale e gratuito). Rischio: relay aperto a chiunque imposti un cookie oneflux_session fittizio -> abuso dall'IP di Vercel e possibile blocco di Google, che spegnerebbe «Ascolta» per i clienti veri. Non è un tema sotto-utenti.

**prova.** Codice letto: tts/route.ts:55-58 `const token = cookieStore.get(SESSION_COOKIE)?.value; if (!token) return 401` e poi fetch a translate.google.com; nessuna chiamata al worker (test_regole_dominio_guardia.py:523-533 la dichiara «unica con logica non-auth»). Chiamante: components/ascolta-button.tsx:68 con il testo del briefing già a video. Nessun test valida il token.

**numeri attesi vs mostrati.** atteso 401 con cookie non valido; ottenuto (per lettura del codice) 200 con audio per qualunque cookie non vuoto

**fix proposto.** Validare la sessione prima del fetch (una GET /api/auth/me al worker con il token, o il helper di lib/auth usato da auth/me) e rispondere 401 se non valida; in alternativa spostare il proxy nel worker dietro _resolve_user_from_token e un rate limit per account.

**presidio proposto.** Test via node (tests/test_*_frontend.py) che la route chiami il verificatore di sessione, provato per mutazione togliendo la chiamata; o test -m sql sul worker se la route migra lì.

**gia presidiato da.** tests/test_regole_dominio_guardia.py (solo perimetro delle route non-proxy, non il comportamento).

**file e righe.** `apps/web/src/app/api/tts/route.ts:55-58`; `apps/web/src/components/ascolta-button.tsx:68`; `tests/test_regole_dominio_guardia.py:523-533`

### Verificato e trovato giusto

- DB live: sotto_utenti, sotto_utenti_sedi, sessioni hanno RLS attiva (relrowsecurity=true; sessioni anche forced) e ZERO policy (pg_policies vuoto) -> nessun accesso per anon/authenticated; grant (role_table_grants) solo a postgres e service_role su sotto_utenti, sotto_utenti_sedi, sessioni, chat_usage_log: nessun grant nominale residuo ad anon/authenticated, come dichiara la migration 20260928215000:181-186.
- DB live: i 5 trigger della migration sono presenti e attivi (tgenabled='O'): sotto_utenti_sedi_guardia, sotto_utenti_titolare_immutabile, sotto_utenti_email_unica, users_email_non_di_un_sotto_utente, sessioni_sotto_utente_del_titolare, con le funzioni omonime.
- DB live: nessuna funzione fra gruppo_*, chat_crediti_*, sotto_utenti_*, sessioni_* e le 20 con p_user_id/p_ristorante_ids è eseguibile da anon/authenticated/PUBLIC (routine_privileges vuoto; proacl = {postgres=X, service_role=X} per tutte le 31).
- DB live: le 10 gruppo_* (peso_categoria, prezzi_catena, prezzi_coppie, salute_componenti, spesa_pivot, spreco_fb_categorie, tag_analisi, tag_descrizioni, tag_fornitori, tag_trend) sono SECURITY DEFINER, filtrano con ANY(p_ristorante_ids) e deleted_at, non ricevono user_id: il filtro di tenant/sottoinsieme sta in _resolve_gruppo (gruppo.py:972-1019, verifica_catena + sedi del titolare), coerente con la mappa.
- DB live: chat_crediti_check_and_log (SECURITY DEFINER) prende advisory lock su p_user_id, delega a chat_crediti_stato (pool -> user_id = p_user_id; non pool -> ristorante_id = p_ristorante_id della sessione) e inserisce in chat_usage_log(user_id, ristorante_id, crediti, da_ricarica): p_user_id è sempre user['id'] = titolare (fw:3275-3283, 3222-3226). chat_usage_log ha colonne id,user_id,ristorante_id,created_at,crediti,da_ricarica: nessuna dimensione persona. È una scelta dichiarata (CHAT_ASSISTENTE.md:242-243 «La quota è una per account»; migration:9-11 sotto_utente_id «aggancio per un futuro audit trail»; memoria «sotto-utente solo in meno» 3/10), non un difetto: il 429 mensile dice al sotto-utente «il titolare può chiedere una ricarica» (fw:6248-6251).
- Le 20 funzioni con p_user_id: 15 filtrano user_id = p_user_id (regex sul corpo); le 5 senza filtro sono scritture che usano p_user_id come valore di INSERT (accoda_upload_ambiguo, crea_riparto_con_quote, track_ai_usage_event con guardia auth.role) o admin_* (p_user_ids/p_ristorante_ids da un endpoint admin): lette per intero, nessuna legge dati di un altro tenant.
- POST /api/fatture/assegna-sede (fatture.py:1513-1560): solo ownership (fatture_queue.user_id, ristoranti.user_id+attivo). Per un sotto-utente richiede C (permessi_rotte:247); la Catena effettiva implica TUTTE le sedi operative e la tecnica (sovrapponi:120-123); una sede creata dopo spegne catena_consentita a ogni risoluzione (TTL 2 s) e quindi la rotta risponde 403 (test_sede_nuova_spegne_la_catena_finche_non_e_assegnata). Falso allarme.
- DELETE /api/riparto/{id} (riparto.py:835-866) non chiama _require_catena per scelta documentata, ma la rotta è _p(C) (permessi_rotte:259) e ha_pagina(catena) legge pagine_abilitate['catena'] = effettive[PAGINA_CATENA] = lo stesso valore di ctx['catena'] usato da verifica_catena (sotto_utenti_service:89,149,251,256): controllo equivalente. Falso allarme.
- Cambio pagine/sedi da admin senza revoca: cache per token con TTL 2 s per i sotto-utenti (auth_service.py:1349-1352, 1512-1525), 4 processi uvicorn in produzione (railway.toml WORKER_WEB_CONCURRENCY=4, DEPLOY_RUNBOOK.md:31): ogni processo rilegge sotto_utenti+sedi+ristoranti entro 2 s dal proprio ultimo refresh, quindi la finestra è ≤2 s per processo; disattivare ed eliminare revocano subito (sotto_utenti_admin.py:294-297, 315-316). Presidio: test_la_sessione_di_un_sotto_utente_resta_in_cache_al_massimo_2_secondi. Falso allarme.
- Rotte con id di risorsa: fatture/{riga_id}/categoria filtra .eq(ristorante_id) della sede attiva (fatture.py:1308-1314); workspace ricette/ingredienti/inventario/diario filtrano user_id+ristorante_id attivo o _solo_sede_del_sotto_utente (workspace.py:52-59, 383, 394, 456, 466, 724-735); tag con _assert_tag_ownership(user_id, ristorante_id) (tag.py:119-126); gruppo/prezzi/preferiti contro rid_to_nome dopo verifica_catena (gruppo.py:3605-3640); sposta-sede e assistente/registra con sede_consentita (fatture.py:1611-1622, assistente.py:276-297). Presidio: test_sotto_utente_non_raggiunge_le_risorse_di_un_altra_sede (≥40 ricette con gli id della sede 1 da un sotto-utente della sede 2).
- AI senza Home per altre vie: /api/home/briefing, kpi, salute, alert-prezzi, /api/dashboard/stats sono _p(H) (permessi_rotte:208-212) e la sonda conferma 403 su briefing; le chiamate interne (home_kpi da chat fw:3687, gruppo_segnali fw:4542) ereditano la rotta d'ingresso /api/chat già gated; il briefing di catena in /api/gruppo/overview è deterministico (_build_briefing, nessun riferimento a OpenAI in gruppo.py); l'email settimanale legge solo users (email_settimanale_service.py:177-190) -> i sotto-utenti non la ricevono; le notifiche con testo del briefing hanno action_page 'dashboard' -> mappate su H in notifica_visibile; TTS riceve il testo dal client; /api/assistente/registra è gated per tipo (M o A, assistente.py:594) e non chiama l'AI; proponi_* esistono solo come strumenti della chat (fw:5808-5825, gate _CHAT_TOOL_FLAG). Unica via è la chat di catena con la sola C (F2a-3).
- Test eseguiti: python -m pytest tests/test_permessi_rotte.py tests/test_sotto_utenti_pagine.py -q -p no:randomly -> 80 passed, 9 warnings (34 s); python -m pytest tests/test_sql_sotto_utenti.py -q -p no:randomly -> 56 passed, 9 warnings (166 s), /dev/shm 0% prima e dopo, nessun pytest/Postgres orfano.
- Produzione: 0 righe in sotto_utenti, 0 in sotto_utenti_sedi, 0 sessioni con sotto_utente_id (misurato oggi): nessun cliente è toccato oggi dai finding; nessun sotto-utente creato.

### Non verificabile in sola lettura

- Efficacia del TTL di 2 s su più processi in produzione (4 uvicorn su Railway): richiederebbe un sotto-utente di prova sul live; verificato solo per lettura del codice e con il test su un processo.
- Comportamento reale di api/tts con un cookie fittizio: non ho chiamato Vercel (vincolo 2); prova solo per lettura del codice.
- Quota AI per persona: non esiste la colonna, quindi non si può misurare chi ha consumato cosa; classificata come scelta dichiarata, non verificabile oltre i documenti citati.
