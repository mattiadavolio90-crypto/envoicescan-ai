# Audit compliance legale — 09/09/2026

**Domanda di partenza (owner):** controllare termini, cookie, privacy e tutta la
documentazione per il cliente, e se l'app è in linea con GDPR e legislazione
italiana/europea.

**Verdetto:** l'impianto sostanziale era in ordine; **i documenti mentivano**.

---

## Il pattern riusabile — perché questo file esiste

> **Un documento legale non invecchia: diventa falso.** E la differenza conta,
> perché il Garante contesta la **dichiarazione non veritiera**, non la lacuna
> dichiarata.

Le pagine `/privacy` e `/termini` erano ferme al 19/06/2026. Nessuna era
sbagliata quando è stata scritta: il codice è andato avanti e le ha smentite una
alla volta, in silenzio, per quasi tre mesi. Una privacy policy è l'unico
artefatto del repo che **afferma fatti sul codice** senza che nulla verifichi che
siano ancora veri.

Il metodo che ha trovato i difetti, e che va rifatto uguale la prossima volta:
**non rileggere i documenti — confrontarli col codice, voce per voce.**

| Cosa dichiara il documento | Dove si verifica davvero |
|---|---|
| «Nessun cookie analytics» | `grep` dei pacchetti in `package.json` **e** di cosa monta il root layout |
| Elenco dei destinatari dei dati | ogni host esterno che il codice contatta (`api.telegram.org`, `api.brevo.com`, workflow di backup) |
| Retention dichiarate | i purge che esistono davvero nel worker, tabella per tabella |
| «Export di tutti i tuoi dati» | l'elenco delle tabelle con PII, confrontato con quelle esportate |
| Parametri di sicurezza | la costante nel codice, non il testo |

Rileggere la privacy non avrebbe trovato **nessuno** di questi: si legge bene,
è coerente con sé stessa. Mente solo rispetto al codice.

---

## Cosa è stato trovato (tutto verificato nel sorgente, non dedotto)

### Le tre falsità verso il cliente

1. **P.IVA inesistente nell'export art. 20.** `services/routers/account.py`
   dichiarava `Recoma System S.r.l. (P.IVA IT09599210961)` nel JSON scaricato
   dal cliente. La P.IVA era stata corretta **ovunque** il 10/07/2026
   (`PIANO_WEB_MARKETING.md:222`) tranne lì.

   **Perché è sopravvissuta due mesi:** un test la presidiava già
   (`test_documentazione_onesta.py::test_nessuna_piva_errata_nei_doc_vivi`), ma
   è parametrizzato su `DOC_VIVI`, cioè solo file `.md`. Il `.py` non era nel
   perimetro. *Un presidio che copre l'artefatto sbagliato è indistinguibile da
   nessun presidio.* Peggio: `tests/test_account_gdpr.py` asseriva
   `startswith("Recoma System")` — **sanciva il bug invece di prenderlo**.

2. **Vercel Analytics attivo mentre tre documenti dichiaravano di non averne.**
   `<Analytics />` da `@vercel/analytics` era montato nel root layout, contro
   quanto affermato da privacy, banner cookie e dossier compliance. Rimosso
   (decisione dell'owner): i documenti tornano veri senza riscriverli e senza
   dover introdurre un cookie-wall Accetta/Rifiuta.

3. **Cookie `oneflux_view` non dichiarato**, che rendeva falsa anche la frase
   «tutti i cookie sono HttpOnly» — quello è scritto da JavaScript.

### Dichiarazioni tecniche smentite dal codice

| Dichiarato | Reale |
|---|---|
| Argon2id `p=1` | `p=4` (`services/auth_service.py:53`) |
| Tentativi di accesso «conservati 15 minuti» | cleanup a **24h**; i 15 min sono il *lockout* (`_LOCKOUT_MINUTES`) |
| «Log applicativi senza PII in chiaro» | email in chiaro in decine di punti, nessuna rotazione nel repo |

*Trappola di lettura:* «15 minuti» compariva sia nel codice sia nel documento, e
sembrava confermato. Erano due grandezze diverse con lo stesso numero — la
durata del blocco e la durata della conservazione. **Un numero che coincide non
prova che si stia parlando della stessa cosa.**

### Destinatari dei dati non dichiarati

- **Telegram** (extra-UE) riceveva `Da: ${senderEmail}` negli alert ricavi —
  email di persone fisiche. **Risolto senza dichiararlo**: gli alert ora
  mascherano l'indirizzo (`maskEmail`), il valore esatto resta su
  `ricavi_email_queue.email_sender`, dove serve davvero. Un fornitore a cui non
  mandi dati personali non è un sub-responsabile: *togliere il dato è più
  economico che aggiungere una riga alla tabella e un DPA da firmare.*
- **GitHub** custodisce un `pg_dump` integrale del DB per 14 giorni. Era
  documentato internamente ma **assente dalla tabella pubblica**.
- **OpenAI**: la privacy diceva «categorizzazione». In realtà tre flussi, di cui
  due non anonimizzati — Vision manda **l'immagine integrale del documento**, la
  chat manda nomi fornitore e importi. Solo il briefing è anonimizzato.

### Dati e retention

Cinque tabelle conservavano dati personali **a tempo indeterminato**: `sessioni`
(ip, user_agent), `email_rate_log`, `category_change_log`, `ai_usage_events`,
`marketplace_leads`. Ora hanno una purge
(`supabase/migrations/20260909143000_retention_gdpr_log_e_sessioni.sql`).

L'export art. 20 ometteva `fatture_documenti`, `note_diario`, `custom_tags`, e
soprattutto esportava i `dipendenti` **della sola sede attiva**: un cliente
multi-sede riceveva un export parziale in silenzio (11 sedi su 12 in produzione).

La privacy non dichiarava affatto i **dati dei dipendenti** (nome, turni,
retribuzione lorda). Aggiunti, con la precisazione che su quei dati **il
titolare è il ristoratore** e ONEFLUX è responsabile: senza, non è chiaro a chi
tocchi informare il personale.

---

## Due errori miei, tenuti qui perché si ripeteranno

**1. La purge che non cancellava niente.** La prima stesura di
`purge_marketplace_leads` filtrava su `stato IN ('chiuso','annullato','rifiutato')`.
Il CHECK della tabella ammette solo `nuovo`/`gestito`/`archiviato`: la funzione
sarebbe stata un **no-op perenne**, e verde in qualunque test che si limitasse a
chiamarla senza seminare righe destinate a sparire. Un `DELETE` che non cancella
non fallisce mai.
→ *Per una purge, il test deve seminare almeno una riga che DEVE sparire e una
che DEVE restare. Il conteggio di ritorno da solo non distingue «filtro
corretto» da «filtro che non matcha nulla».*

**2. Il valore inventato al posto di quello letto.** Stesso errore due volte
nella stessa sessione: `operation_type='classificazione'` in un test, quando il
CHECK ammette `categorization`. Qui è saltato subito (violazione di constraint),
ma è la stessa radice del punto 1.
→ *Quando si scrive un valore che finisce in una colonna vincolata, si legge il
CHECK. Sempre.*

---

## Come sono provati i presidi

16 test nuovi in `tests/test_privacy_policy_veritiera.py` (documenti ↔ codice) e
12 in `tests/test_sql_retention_gdpr.py` (purge **eseguite** su Postgres vero).

**10 mutanti, uno alla volta, backup preso prima del primo:** P.IVA errata
rimessa nell'export, analytics reintrodotto come dipendenza, `<Analytics />`
rimontato nel layout, `parallelism` cambiato senza toccare i doc, «15 minuti»
rimesso nella privacy, email Telegram in chiaro, filtro temporale rimosso dalla
purge sessioni, stato inesistente sui lead, filtro di stato rimosso, `GRANT` ad
anon. **Tutti uccisi, ciascuno dal test giusto.**

Il mutante sulle sessioni merita una nota: senza filtro temporale la purge
cancella **tutte** le sessioni, cioè slogga ogni cliente. È il tipo di difetto
che in produzione si manifesta come «gli utenti devono rifare il login» senza
un solo errore nei log.

---

## Cosa resta aperto — richiede l'owner, non il codice

> **0. La migration non e' applicata al DB live.** Verificato su `pg_proc` il
> 09/09/2026: le 5 funzioni di purge esistono nel repo e nei test (che girano su
> un Postgres locale con le migration post-snapshot applicate), **non in
> produzione**. Finche' non viene applicata, `worker/run.py` chiama 5 RPC
> inesistenti ogni 24h — non un crash, ogni purge ha il suo `try`, ma la
> retention e' **dichiarata al cliente e non applicata**: esattamente la classe
> di difetto che questo audit esisteva per chiudere. Va applicata al live nella
> finestra oraria, prima o insieme al push.
>
> Lezione riusabile, gia' in memoria ma ricascataci qui: *scrivere una migration
> non e' applicarla, e un test verde su Postgres locale non dice niente sullo
> stato del live.* Lo stato reale si misura su `pg_proc`.


1. **DPA non firmati** con Supabase, OpenAI, Invoicetronic, Vercel, Railway
   (solo Brevo automatico). Checklist in `docs/COMPLIANCE_GDPR.md` §8. È la
   lacuna formale più concreta: la privacy li chiama già «sub-responsabili».
2. **Regione Supabase**: privacy e dossier dichiarano «UE — Frankfurt», ma **non
   è verificabile da alcun file del repo**. Se il progetto non fosse in UE, la
   dichiarazione al cliente sarebbe falsa. Da confermare dal dashboard.
3. **Email di contatto divergenti**: i legali usano `md@oneflux.it`, landing e
   structured data `mattia.davolio@recomasystem.it`. Il cliente vede due
   indirizzi per lo stesso titolare, e uno solo può essere quello per
   l'esercizio dei diritti.
4. **2FA assente anche per gli admin**, che possono impersonare qualsiasi
   cliente. Non obbligatoria, ma è la misura art. 32 più sproporzionata rispetto
   al livello di accesso.

---

## Riferimenti

- Commit: `a82213e`
- Suite: 13.258 verdi + 44 skip; **176 su Postgres vero** (erano 164); `tsc` pulito
- Documenti toccati: `apps/web/src/app/(legal)/{privacy,termini}/page.tsx`,
  `docs/COMPLIANCE_GDPR.md`
- Certificato di copertura aggiornato: `DOCUMENTAZIONE/AUDIT_COPERTURA.md`
