# docs/storico — Know-how riusabile su problemi chiusi

Non è un archivio generico: un documento sta qui solo se il suo contenuto ha
ancora valore predittivo per un problema che si può ripresentare (pattern
d'errore, causa radice non ovvia, percorso diagnostico) — non solo perché
descrive un evento passato. Non descrivono lo stato attuale del sistema: per
quello vedi `README.md` (root), `CLAUDE.md` e `DOCUMENTAZIONE/DOC COMPLETA/`.
Se un documento chiuso non insegna nulla di riusabile, va eliminato, non
archiviato qui.

| File | Cos'è | Perché vale la pena tenerlo |
|---|---|---|
| `MIGRAZIONE_APP.md` | Piano di switch Streamlit → Next.js (Fasi 9–11), checklist DNS e spegnimento | Riferimento se un giorno serve rifare uno switch DNS/infrastruttura simile |
| `CHECKLIST_069_072.md` | Checklist di applicazione delle migration legacy 069–072 (cartella `migrations/` storica) | Traccia di cosa è stato applicato sullo schema legacy |
| `INVOICETRONIC_DIAGNOSI_2026-07-02.md` | Diagnosi blocco ricezione fatture OFFSIDE (2/7/2026): precedenza del Codice Destinatario sul cassetto fiscale, conflitto con provider terzi (Sistemi in Rete) | Pattern che si ripresenterà su altri clienti multi-provider: la regola SDI su cosa vince tra cassetto fiscale e XML fornitore non è ovvia e costa tempo riscoprirla |
| `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md` | Diagnosi blocco ricezione fatture OFFSIDE (14/7/2026): aziende create solo in sandbox invece che live, secrets Supabase disallineati, bug P7M (byte nulli) | 3 cause tecniche riusabili: sandbox-vs-live su Invoicetronic è un errore facile da ripetere su un nuovo cliente; il bug P7M è strutturale (qualunque fornitore che firma P7M può ritriggerarlo se il fix regredisce) |

> Il duplicato esatto `CHECKLIST_070_071.md` è stato rimosso (era identico a `CHECKLIST_069_072.md`).
> `PIANO_RIPARTIZIONE_COSTI_CATENA.md` e `PIANO_OPERATIVO_RIPARTIZIONE_COSTI_CATENA.md` (piani di
> decisione/disegno della ripartizione costi catena, 1/7 e 14/7/2026) sono stati **eliminati** il
> 17/7/2026 dopo verifica che la feature è deployata (commit a1e7c64+3baa013): il "come funziona"
> vive nel codice/migration, il "perché" (Proposta 2) non ha valore predittivo su problemi futuri.
> Nota: `INVOICETRONIC_DIAGNOSI_2026-07-02.md` e `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md` matchano
> il pattern `*DIAGNOSI*.md` in `.gitignore` (pensato per scratch temporanei) e sono stati aggiunti
> con `git add -f`: restano intenzionalmente tracciati qui, a differenza degli scratch non archiviati
> dello stesso pattern.
