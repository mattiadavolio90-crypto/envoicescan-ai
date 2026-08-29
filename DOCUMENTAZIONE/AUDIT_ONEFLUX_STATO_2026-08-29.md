# Stato audit ONEFLUX — ciclo aperto il 29/08/2026

**Nessuna dimensione ancora aperta.** Questo file sostituisce il ciclo 2026-08,
chiuso e archiviato in `docs/storico/` insieme al suo storico
(`AUDIT_ONEFLUX_STATO_2026-08.md` e `..._STORICO.md`).

> Il ciclo precedente si è chiuso con **8 decisioni aperte risolte in una
> sessione dedicata** il 29/8/2026 (radar anomalie, `normalizza_piva`, prompt
> AI, tipo spesa, Argon2, `p_limit`, riparto, commento `ai_pending`). Deploy
> Railway + Vercel su `fb5785fd`.

---

## ⚪ Unico punto ereditato e ancora aperto

**F2-NOTEST — nessun test runner frontend.** `apps/web/` non ha alcun test che
esegua codice: l'unica rete è `npx tsc --noEmit`, che controlla i tipi e non
esegue niente. È una **decisione esplicita di Mattia**, non una svista: va
affrontata in una sessione dedicata, non segnalata come finding.

Materiale preparatorio già scritto: `DOCUMENTAZIONE/PUNTO_9_TEST_FRONTEND.md` e
`DOCUMENTAZIONE/PROMPT_PUNTO_9.md` (branch `docs/punto-9-test-frontend`).

Perché continua a costare: il 29/8 una guardia su una soglia è passata da `tsc`,
sembrava giusta a leggerla e **non scattava su nessuno dei 3 casi reali** perché
misurava dopo i filtri client. E nella stessa sessione un test scritto *apposta*
per catturare un difetto di firma — un `grep` riga per riga — non lo catturava,
perché il kwarg sbagliato stava su un'altra riga. Solo l'analisi AST l'ha visto.

---

## Come si apre una dimensione qui

Il protocollo è invariato rispetto ai due cicli precedenti — vale la pena
rileggerlo in `docs/storico/AUDIT_ONEFLUX_STATO_2026-08.md` §«COME SI USA QUESTO
FILE» prima di iniziare. In sintesi:

1. Una dimensione per sessione, autosufficiente (perimetro misurato, ipotesi,
   criterio di chiusura, comandi).
2. Audit **read-only** prima di ogni fix; remediation solo dopo conferma.
3. **Ogni severità e ogni cifra si ri-misurano sul DB live al momento di
   scriverle.** Nel ciclo 2026-07 è caduta 8 volte una severità ereditata; nel
   2026-08 il `code-reviewer` ha trovato un errore in **ogni** fase; nella
   sessione degli 8 punti ri-misurare ha corretto la roadmap **quattro volte**,
   e in tre casi ha cambiato il lavoro, non solo il racconto.
4. Ogni fix nuovo → **provato per mutazione, su copia in scratchpad**: si rimuove
   il fix e si controlla che i test tornino rossi. Un test che non fallisce
   quando il difetto torna non è una rete.
5. `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
6. Prima di dichiarare chiusa una fase: `gh pr view <n> --json headRefOid`
   contro `git log -1`, e CI verde **su GitHub**, non solo in locale (la CI gira
   su Python 3.12 con `requirements-lock.txt` e un gate
   `coverage --fail-under=45`: non è lo stesso segnale del verde locale).

---

## Lezioni trasversali da non ri-imparare

Le 36+ lezioni operative dei cicli precedenti stanno negli storici. Le tre che
hanno morso più di recente:

- **Un mock generoso è un test che mente.** I 6 test del radar anomalie sono
  stati verdi per mesi su una query che filtrava una colonna inesistente, perché
  il fake restituiva `self` da ogni builder ignorando gli argomenti. Un fake che
  valida i nomi di colonna contro lo schema reale l'avrebbe intercettato il primo
  giorno.
- **Leggere un `if` non dice quale suo lato è caldo.** Il `tipo` spesa sembrava
  protetto leggendo il codice; il 97,77% dell'importo reale passava dall'altro
  ramo.
- **Codice morto che resta chiamabile è un difetto latente.** Cambiare una firma
  senza aggiornare un call site irraggiungibile non rompe la produzione, ma
  l'`except` che lo avvolge silenzia l'errore — lo stesso meccanismo che aveva
  reso invisibile il difetto originale.
