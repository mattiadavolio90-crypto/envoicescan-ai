# Prompt per la prossima sessione

> Copia il blocco qui sotto come primo messaggio della nuova sessione.

---

Il ciclo audit 2026-08 è **chiuso e archiviato** in `docs/storico/`: 7 fasi, le
**8 decisioni** risolte e deployate (`fb5785fd`), e il **punto 9 (F2-NOTEST)
chiuso** il 29/8 con i primi test che eseguono davvero il TypeScript.
**Non c'è nulla di aperto da quel ciclo: non riaprirlo.**

Il ciclo corrente è `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md`. Ha già
il **perimetro scoperto misurato** (§«Il perimetro ancora scoperto», 30/8/2026)
ma **nessuna dimensione aperta**: la apri tu, in questa sessione.

## Cosa fare: aprire la dimensione «route API»

**169 route API, 4.776 righe, mai auditate come layer proprio.**

Non è una scelta di comodo — è la lezione più cara del ciclo scorso. In F2 il
perimetro dichiarato conteneva «le pagine, non il percorso»: **2 dei 4 difetti
della fase stavano nelle route API, incluso l'unico HIGH** (open redirect su
`/login?next=`, che ha richiesto 3 stesure). Un layer che ha già prodotto un
HIGH e non è mai stato letto per intero è il posto giusto da cui ripartire.

Distribuzione misurata: `admin` 41 route, `workspace` 30, `tag` 11, `margini` 10,
`gruppo` 10, `scadenziario` 9, `riparto` 8, `account` 8.

**Prima cosa da fare, prima di leggere qualsiasi file**: decidere l'ordine
**sull'esposizione live**, non sul numero di route. Il ciclo 2026-07 ha
dimostrato due volte che coverage ed esposizione divergono — `workspace.py` era
priorità 1 per coverage e governa ~29 righe di dati veri.

Ipotesi da verificare, non da assumere:
- **auth e autorizzazione**: ogni route verifica la sessione? E che il
  `ristorante_id` richiesto appartenga a chi chiama? (`auth.uid()` è sempre NULL
  — l'auth è custom, RLS non protegge niente.)
- route che **scrivono** senza validare l'input al server, fidandosi della UI:
  è esattamente il difetto del punto 4 del ciclo scorso (il `tipo` spesa era
  protetto solo dal client).
- soft-delete: `filter_active()` / `deleted_at IS NULL` applicato ovunque.

## Poi, se resta tempo: lo scadenziario

Seconda per priorità, e la più esposta fra le pagine: **2.001 documenti non
pagati, 1.853 già scaduti**, in **un solo file da 2.244 righe**
(`scadenziario-client.tsx`). Ha già avuto un difetto di fuso su `pagata_at`,
corretto lato scrittura; **la UI che lo legge non è mai stata auditata**. I test
del punto 9 coprono `computeKpi` e `bucketizeDocumenti` — la logica pura, non il
resto del file.

## Voci aperte ereditate — verificate ancora vere il 30/8

Sono in fondo alla roadmap con le misure. In sintesi: il blocco notifiche
`source_type='upload'` è morto (ultima emessa **1/6/2026**), `check_weekly` ha
**zero chiamanti**, `normalizza_descrizione` copre 5 pattern su 7.

**Baseline radar**: `notification_inbox` ha **0 record `source_type='radar'`**
su 65 (30/8). Il radar è stato ricollegato il 29/8 — dopo i primi upload reali
dovrebbero comparirne **pochi e veri**. Se sono molti, la ritaratura va rivista:
prima del fix ne avrebbe prodotti 897, tutti falsi. **Controllalo a inizio
sessione**, è una riga di SQL.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla**, mai ereditata da un
  documento — nemmeno da questo. Il 29/8 ri-misurare ha corretto la roadmap
  **quattro volte**, e in tre casi ha cambiato il lavoro, non solo il racconto.
- **Ogni fix si prova per mutazione**, su copia in scratchpad: si rimuove il fix
  e si controlla che i test tornino rossi. Vale anche per un test scritto per
  correggere un test che non misurava.
- **Un mock che non guarda cosa gli viene chiesto non è una rete.** I 6 test del
  radar sono stati verdi per mesi su una colonna inesistente.
- **Leggere un `if` non dice quale suo lato è caldo.** Misura quale ramo
  percorrono i dati veri prima di dichiarare protetta una cosa.
- Audit **read-only** prima di ogni fix; remediation solo dopo mia conferma.
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
- **Verifica che lo sha della PR sia quello inteso**
  (`gh pr view <n> --json headRefOid` contro `git log -1`) e la CI verde **su
  GitHub**, non solo in locale: gira su Python 3.12 con `requirements-lock.txt`
  e un gate `coverage --fail-under=45`.
- Migration solo con mia conferma esplicita, applicata **prima** del deploy.
- **Deploy fuori orario cliente**, salvo mio via esplicito: l'auto-deploy Railway
  parte a ogni merge su `main`, anche per un diff di soli documenti.

## Chiusura

Verbale in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md` (crealo alla prima fase
chiusa — il nome matcha l'eccezione `.gitignore` `!AUDIT_ONEFLUX_STATO*.md`),
e aggiorna lo stato della dimensione nella roadmap. **Committa il doc insieme al
codice che documenta.**
