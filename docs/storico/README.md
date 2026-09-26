# docs/storico — Know-how riusabile su problemi chiusi

Non è un archivio generico: un documento sta qui solo se il suo contenuto ha
ancora valore predittivo per un problema che si può ripresentare (pattern
d'errore, causa radice non ovvia, percorso diagnostico) — non solo perché
descrive un evento passato. Non descrivono lo stato attuale del sistema: per
quello vedi `README.md` (root), `CLAUDE.md` e `DOCUMENTAZIONE/tecnica/`.
Se un documento chiuso non insegna nulla di riusabile, va eliminato, non
archiviato qui.

| File | Cos'è | Perché vale la pena tenerlo |
|---|---|---|
| `MIGRAZIONE_APP.md` | Piano di switch Streamlit → Next.js (Fasi 9–11), checklist DNS e spegnimento | Riferimento se un giorno serve rifare uno switch DNS/infrastruttura simile |
| `CHECKLIST_069_072.md` | Checklist di applicazione delle migration legacy 069–072 (cartella `migrations/` storica) | Traccia di cosa è stato applicato sullo schema legacy |
| `INVOICETRONIC_DIAGNOSI_2026-07-02.md` | Diagnosi blocco ricezione fatture OFFSIDE (2/7/2026): precedenza del Codice Destinatario sul cassetto fiscale, conflitto con provider terzi (Sistemi in Rete) | Pattern che si ripresenterà su altri clienti multi-provider: la regola SDI su cosa vince tra cassetto fiscale e XML fornitore non è ovvia e costa tempo riscoprirla |
| `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md` | Diagnosi blocco ricezione fatture OFFSIDE (14/7/2026): aziende create solo in sandbox invece che live, secrets Supabase disallineati, bug P7M (byte nulli) | 3 cause tecniche riusabili: sandbox-vs-live su Invoicetronic è un errore facile da ripetere su un nuovo cliente; il bug P7M è strutturale (qualunque fornitore che firma P7M può ritriggerarlo se il fix regredisce) |
| `DEVCONTAINER_PERMESSI_DIAGNOSI_2026-08-26.md` | Volume `.claude/` root-owned → login loop infinito, hook/CLI (Railway) da rilinkare a cascata | Pattern che si ripresenterà a ogni ricreazione del volume Docker (update VSCode, rebuild falliti, nuovo devcontainer): senza il fix in `postStartCommand`, il login smette silenziosamente di persistere |
| `AUDIT_ULTIMO_PERIMETRO_2026-09.md` | Verbale del ciclo di audit di settembre 2026: la logica dentro il DB (78 corpi di funzione letti dal live), il registro delle correzioni, gli script che scrivono in produzione | Contiene le misure e le query di ogni punto chiuso. La sintesi leggibile a distanza di tempo sta invece in `DOCUMENTAZIONE/AUDIT_COPERTURA.md`, che e' il certificato dei tre cicli |
| `COMPLIANCE_DOC_VS_CODICE_2026-09-09.md` | Audit compliance legale (privacy, cookie, termini, GDPR) del 9/9/2026: 3 dichiarazioni false verso il cliente, 2 destinatari dei dati non dichiarati, 5 tabelle senza retention | Il metodo, non l'esito: un documento legale **non invecchia, diventa falso**, e si controlla confrontandolo col codice voce per voce (host contattati, purge esistenti, tabelle con PII) — rileggerlo non trova nulla. Contiene anche i due modi in cui una purge sbagliata resta verde |
| `audit_prompt_ai_report_2026-09-03.md` | Audit del prompt AI e di `config/` (3/9/2026): 12 chiavi del dizionario in mojibake (doppia codifica UTF-8 nei byte del file), e la contraddizione interna del prompt neutralizzata dal gate a valle | Due cose riusabili: il mojibake in un dizionario **non si vede a occhio** e si trova solo validando i byte, non rileggendo il file; e la ragione per cui la tensione «DEVI classificare sempre» ↔ «se non riconosci → Da Classificare» **non** è un buco (il gate accetta solo `alta` non-dubbia o categoria confermata) — senza questa nota un audit futuro la riapre come difetto |
| `audit_worker_report_2026-09-03.md` | Audit di `worker/` (3/9/2026): `_schedule_retry` della coda email passava a PostgREST la stringa `"now() + interval '...'"` come valore timestamptz | Il pattern vale oltre il caso: un'espressione SQL passata **come valore** a PostgREST viene rifiutata (`'now()'` casta, `'now() + interval …'` no), e l'UPDATE intero fallisce in silenzio — niente `failed`, niente backoff, lock non rilasciato. Era **latente** (88/88 righe done al primo colpo): il difetto si vede solo al primo errore transitorio, quindi non lo trova l'uso normale |
| `audit_briefing_report_2026-09-03.md` | Audit di `daily_briefing_service.py` (3/9/2026): importi in formato inglese nei bullet scadenze, e il validatore esteso all'entusiasmo vietato | Contiene la prova che **due rilievi in memoria erano invecchiati** («le regole di tono sono violate in produzione», «6 soglie su 11 sbagliate»): ri-misurati su 42 snapshot, 0 violazioni e 11 leve allineate. È il promemoria che un rilievo va ri-misurato prima di ereditarlo — e il metodo per farlo (`daily_briefing_state`, non il doc) |
| `audit_router_scadenziario_report_2026-09-03.md` | 1ª passata sui router (3/9/2026): `POST /api/scadenziario/notifica` muto da giugno per un `on_conflict` su un vincolo unico **inesistente** | Classe di difetto che si ripresenta: un `on_conflict` che nomina un vincolo non esistente fa cadere ogni chiamata nell'`except`, e se il frontend la fa best-effort il risultato è **silenzio totale** — 300 fatture scadute per 4,4 M€ e zero avvisi al cliente, senza un solo errore visibile. Si misura su `pg_indexes`, non si deduce dal codice |
| `coerenza_numeri_report_2026-09-03.md` | Verifica di quadratura dei numeri fra le pagine (3/9/2026), read-only: catena OFFSIDE per intero, SUSHILAND, LAND DEI SAPORI, TIME CAFE | È il **metodo** per confrontare gli stessi numeri fra pagine diverse (confronti A–E, mesi 2026-01→08, catena con sede tecnica dei costi comuni) con il perimetro fuori copertura dichiarato in fondo. Rifare la quadratura da zero costa una sessione; questo dice quali confronti valgono e dove i numeri divergono per disegno |

> Il duplicato esatto `CHECKLIST_070_071.md` è stato rimosso (era identico a `CHECKLIST_069_072.md`).
> `PIANO_RIPARTIZIONE_COSTI_CATENA.md` e `PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md` (piani di
> decisione/disegno della ripartizione costi catena, 1/7 e 14/7/2026) sono stati **eliminati** il
> 17/7/2026 dopo verifica che la feature è deployata (commit a1e7c64+3baa013): il "come funziona"
> vive nel codice/migration, il "perché" (Proposta 2) non ha valore predittivo su problemi futuri.
> Nota: `INVOICETRONIC_DIAGNOSI_2026-07-02.md` e `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md` matchano
> il pattern `*DIAGNOSI*.md` in `.gitignore` (pensato per scratch temporanei) e sono stati aggiunti
> con `git add -f`: restano intenzionalmente tracciati qui, a differenza degli scratch non archiviati
> dello stesso pattern.
>
> **Convenzione piani di lavoro** (formalizzata in `WORKFLOW.md`): i piani per-feature vivono in
> `docs/piani/PIANO_<feature>.md`, sono git-ignorati e **si eliminano a feature deployata** — l'esito
> passa nella memoria persistente, non qui. Un piano finisce archiviato in `docs/storico/` solo se il
> suo contenuto ha valore predittivo su problemi futuri (la regola in cima a questo file); altrimenti
> si elimina, come già fatto sopra per i due piani della ripartizione costi catena.
