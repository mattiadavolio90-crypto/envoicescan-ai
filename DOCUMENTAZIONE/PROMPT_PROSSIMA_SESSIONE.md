# Prompt per la prossima sessione

> **Mattia**: nella nuova sessione basta che scrivi
> `Leggi DOCUMENTAZIONE/PROMPT_PROSSIMA_SESSIONE.md e segui quello che dice.`
> Non serve incollare nulla: tutto quello che serve è qui sotto.

---

Il ciclo audit corrente è `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08-29.md`;
i verbali delle sessioni chiuse stanno in `..._STORICO.md`. Il ciclo 2026-08 è
**chiuso e archiviato** in `docs/storico/`: non riaprirlo.

**Il contatore della copertura è `DOCUMENTAZIONE/AUDIT_COPERTURA.md`**
(creato il 31/8/2026): è l'unico posto dove le somme tornano, e va aggiornato a
fine sessione insieme alla roadmap. Ri-misurato il 31/8: **34% letto
integralmente, 16% auditato per dimensione, 50% mai guardato** su 110.069 righe.
«Luglio + agosto coprono tutta l'app» **è falso** — leggilo prima di dichiarare
chiuso qualsiasi perimetro.

## ⚠️ Prima di scrivere una riga: c'è lavoro in coda, non spedito

Mattia accumula più sessioni e **deploya una volta sola, la sera**. Regola
aggiornata il 31/8/2026 (`CLAUDE.md` §«Dove si lavora», `WORKFLOW.md` §0):
**si lavora su `main` locale, niente branch, niente PR.** All'inizio della
sessione:

```bash
git branch --show-current           # deve essere main
git log --oneline origin/main..main # cosa e' gia' in coda, non spedito
```

Se quel secondo comando non è vuoto, **dillo a Mattia subito**: c'è lavoro
fatto e non ancora spedito, e va saputo prima di aggiungerne altro. Se ti
trovi su un branch, torna su `main` — non impilare una sessione sull'altra.

**Non spedire senza via esplicito di Mattia**, anche a test verdi: `git push`
(e a maggior ragione `gh pr merge`) È il deploy, e ha una finestra oraria
(sera/notte/mattina presto).

**Chiuso finora in questo ciclo:**
- **Dimensione «route API»** (30/8) — le 3 ipotesi di partenza erano tutte false;
  il rischio vero era strutturale ed è chiuso da
  `tests/test_route_api_auth_dichiarativa.py` (9 test, 238 endpoint enumerati
  dall'app vera, allowlist di 10 deroghe motivate).
- **Le 3 «voci aperte ereditate»** (31/8) — **2 su 3 erano false**, la terza
  aveva la domanda sbagliata. Tutte e tre chiuse, il fatto spostato dal
  documento al codice.
- **Primo pezzo di scadenziario** (31/8) — `buildCashFlow` estratta e coperta,
  4 mutanti uccisi.
- **Dimensione «scadenziario» CHIUSA** (31/8, 2ª sessione) — 7 funzioni estratte
  in `lib/scadenziario.ts`, **18 mutanti, 17 uccisi + 1 dichiarato**, client 2.210 → 2.118
  righe. Trovata e **lasciata invariata** (decisione di Mattia) la divergenza
  chip «Questo mese» (cumulativo) vs sezione «Questo mese» (fascia): ora è
  scritta in un test invece che in nessun posto.

## Cosa si fa, e cosa viene dopo

**Si apre `margini/`** (4.795 righe, **🟠 60% già letta**: il lavoro è sul 40%
restante, non da zero — **tocca il MOL**). Lo scadenziario è chiuso davvero: mutazione, commit, verbale, contatore ri-misurato,
`check_documentazione.py` pulito.

⚠️ **Prima di aprire `margini/`, leggi il verbale che l'ha già letta in parte.**
La coda sotto è stata corretta il 31/8 dopo il `code-reviewer`: la prima
stesura dava «mai guardata» ad aree che i cicli 07 e 08 avevano già coperto.
**Aprire un'area 🟠 non significa partire da zero**: il perimetro escluso è
stato misurato e motivato, e rileggerlo è lavoro fantasma.

| Area | Righe | Stato | Dove sta scritto cosa è già letto |
|---|---:|---|---|
| `(app)/margini/` | 4.795 | 🟠 60% letto | ciclo 07 §3c: calcolo-tab (1.248), analisi-tab (846), coperti-tab (809) |
| `(app)/catena/` | 3.127 | 🔴 **mai toccata** | nessun verbale — è l'unica area grande davvero vergine |
| `components/` | 7.298 | 🟠 30% letto | **F3 ciclo 08 CHIUSA** (`AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`) |
| `(app)/workspace/` | 5.012 | 🟠 37% letto | ciclo 07 §3c + **F6 ciclo 08 CHIUSA** |
| `(app)/prezzi/` | 2.361 | 🟠 41% letto | ciclo 07 §3c: variazioni-tab (973) |

**Deciso il 31/8: `margini/` è la prossima dimensione.** Regola di Mattia, in
`WORKFLOW.md` §5bis: *una cosa alla volta, chiusa davvero prima della
successiva — niente strascichi*. Lo scadenziario è chiuso, quindi si apre
`margini/` e **nient'altro** finché non è chiuso a sua volta.

**Chiuso davvero** = tutti e 5 i punti di §5bis, non tre su cinque: mutazione,
commit, verbale, contatore `AUDIT_COPERTURA.md` ri-misurato,
`check_documentazione.py` pulito.

## Cosa fare: aprire `margini/`

**È la priorità per esposizione, non per dimensione**: `catena/` è l'unica area
davvero vergine, ma `margini/` **tocca il MOL**, che è regola di dominio
critica (`CLAUDE.md` §1: le righe `Da Classificare` sono
escluse dai margini finché non vengono classificate, per non falsare il MOL).

**La strada è battuta tre volte** (`poolSaturo`/F7 il 29/8, `buildCashFlow` e
poi i filtri il 31/8): **estrarre la logica pura in `lib/`, coprirla in
`tests/*.py` con `esegui_ts`, provarla per mutazione**. Non serve un runner di
componenti — il punto 9 l'ha escluso per ragione strutturale
(`deploy-vercel.yml` scatta su `apps/web/**`: ogni merge di un test farebbe
partire un deploy di produzione).

**Prima cosa da fare, prima di estrarre qualsiasi cosa**: cercare nel perimetro
la logica che *decide numeri o inclusioni* — qui significa **come si calcola il
MOL e cosa entra o non entra nel calcolo**. È esattamente la classe che ha già
prodotto difetti veri, ed è quella dove un errore non si vede: il numero è
solo sbagliato.

Ipotesi da verificare, **non da assumere**:
- **l'esclusione delle righe `Da Classificare`** dai margini è nel backend, nel
  frontend, o in entrambi? Se è duplicata, le due copie sono allineate?
- **le soglie e i confini di periodo**: `margini/` confronta mesi e periodi.
  Ogni confine di data va guardato col fuso in mente, non solo con `tsc`.
- **le aggregazioni per categoria** rispettano il constraint
  `fatture_categoria_not_empty_chk` e la regola su `"📝 NOTE E DICITURE"`
  (consentita solo con `totale_riga == 0`)?

## Se `margini/` chiude presto: NON aprire altro

Regola di Mattia (§5bis): una cosa alla volta. Se `margini/` chiude e avanza
tempo, **si chiude bene** — verbale, contatore ri-misurato,
`check_documentazione.py` pulito, `code-reviewer` — e la sessione finisce lì,
lasciando il prompt pronto per la successiva. Aprire l'area dopo «già che ci
siamo» è esattamente lo strascico che questa regola vieta.

La coda per le sessioni successive, **per esposizione, non per dimensione**.
Gli stati sono quelli corretti dal `code-reviewer` il 31/8 — controlla sempre
`AUDIT_COPERTURA.md` prima di aprirne una:
1. **`catena/`** 🔴 3.127 righe — **mai toccata da nessuna passata**, multi-sede.
2. **`components/`** 🟠 30% — condivisa da tutte le pagine: un difetto qui si
   moltiplica. F3 del ciclo 08 ne ha lette 2.188 e motivato le esclusioni.
3. **`prezzi/`** 🟠 41% — 39.133 righe fattura a monte; letta `variazioni-tab`.
4. **`(mobile)/`** 🟠 32% — frontend separato; letta `mobile-turni`.
5. **`workspace/`** 🟠 37% — la più grande, ma esposizione live bassa (ciclo 07:
   turni 0, regole 0, ingredienti 0) e **F6 del ciclo 08 l'ha già chiusa**.

## Voce aperta, e non è una dimenticanza

**Alzare `dependencies=[...]` a livello di `APIRouter`.** È la correzione
strutturale piena sull'auth: sposterebbe il default da aperto a chiuso **nel
codice**, non solo nel test. Non fatta di iniziativa perché tocca **238
endpoint** e cambia comportamento su tutto il traffico di 7 account veri, e
perché `_resolve_user_from_token` *restituisce* l'utente agli handler: come
dipendenza di router il suo valore non arriva all'endpoint, quindi va disegnata,
non aggiunta meccanicamente. **Va aperta come dimensione a sé, con la sua
finestra di deploy — non come appendice di un'altra sessione.**

## Baseline radar — controllala a inizio sessione, è una riga di SQL

```sql
SELECT topic_key, source_type, count(*), max(created_at)::date
FROM notification_inbox GROUP BY 1,2 ORDER BY 3 DESC;
```

Al 31/8: **0 record `source_type='radar'`**. Il radar è stato ricollegato il
29/8 — dopo i primi upload reali dovrebbero comparirne **pochi e veri**. Se sono
molti, la ritaratura su `numero_documento` va rivista: prima del fix ne avrebbe
prodotti 897, tutti falsi.

Nota misurata il 31/8: `price_alert` ha 3 righe, tutte `source_type='upload'`,
l'ultima **1/6/2026** — è la dismissione di Streamlit, non un guasto. Non
indagarla di nuovo: il perché è nel docstring di `anomaly_radar_service.py` e in
2 test di `test_radar_aggancio_percorso_vivo.py`.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla**, mai ereditata da un
  documento — **nemmeno da questo, nemmeno dalla roadmap**. Il 31/8 le «voci
  aperte ereditate» erano marcate «verificate ancora vere» e **2 su 3 erano
  false**: riprenderle per buone ha prodotto lavoro fantasma finché la misura
  non le ha smontate. È la quarta sessione di fila in cui succede.
- **Ogni fix si prova per mutazione**, su copia in scratchpad: si rimuove il fix
  e si controlla che i test tornino rossi. **Verifica sempre che il mutante si
  applichi davvero** prima di leggerne l'esito: un mutante che non matcha il
  sorgente «sopravvive» senza misurare niente.
- **Serve anche la controprova**: un test che diventa rosso su tutto non
  discrimina. Il 31/8 la prima stesura di un test falliva sul docstring che
  documentava il difetto — un match testuale nudo misura il proprio pattern, non
  il codice.
- **Un mutante che non matcha va rifiutato, non interpretato**: il 31/8
  `?? Infinity` compariva **due volte** e la sostituzione singola sarebbe
  «sopravvissuta» senza misurare niente. Lo script di mutazione deve
  **asserire che le sostituzioni siano esattamente 1** e fermarsi altrimenti.
- **Una previsione sul mutante va verificata come il resto.** Il 31/8 era
  atteso che `new Date()` morisse *solo* a ovest di Greenwich: muore in
  **entrambi** i fusi, perché a Roma `new Date("YYYY-MM-DD")` vale le 02:00
  locali — stesso giorno, ma non mezzanotte. L'attesa era giusta per
  `pagata_at`, non per questi confini.
- **Un mock che non guarda cosa gli viene chiesto non è una rete.**
- **Leggere un `if` non dice quale suo lato è caldo.** Misura quale ramo
  percorrono i dati veri prima di dichiarare protetta una cosa.
- **`tsc` non esegue niente**: un fix può passare `tsc`, sembrare giusto a
  leggerlo e non fare nulla sui dati veri.
- Audit **read-only** prima di ogni fix; remediation solo dopo mia conferma.
- `code-reviewer` sul diff cumulativo a fine sessione, **sempre**.
- Dopo il push (serale, deciso da Mattia): **CI verde su GitHub**, non solo in
  locale — gira su Python 3.12 con `requirements-lock.txt` e un gate
  `coverage --fail-under=45`.
- Migration solo con mia conferma esplicita, applicata **prima** del deploy.
- **Deploy fuori orario cliente**, salvo mio via esplicito: è il **push** su
  `origin/main` a deployare. Railway riparte anche per un diff di soli
  documenti; se il push tocca `apps/web/**` parte **anche** Vercel.

## Chiusura — la lista completa, in ordine

Mattia non deve ricordartela: è qui. Fai **tutti** i punti, non i primi tre
(`WORKFLOW.md` §5bis).

1. **Prova per mutazione** ogni fix: rimuovi il fix su copia in scratchpad e
   controlla che i test tornino rossi. Verifica che il mutante si applichi
   davvero prima di leggerne l'esito.
2. **`/code-reviewer`** sul diff cumulativo (`origin/main..main`). **Sempre**,
   anche se sembra piccolo.
3. **Verbale** in `AUDIT_ONEFLUX_STATO_2026-08-29_STORICO.md`, in coda, con la data.
4. **Stato** aggiornato nella roadmap `AUDIT_ONEFLUX_STATO_2026-08-29.md`.
5. **Contatore** `AUDIT_COPERTURA.md`: sposta la riga (🔴 → 🔍 → 📖),
   **ri-misura** le righe coi comandi in cima al file, ricontrolla che le somme
   tornino. Saltare questo passo fa invecchiare il contatore e riporta il
   problema che è nato per risolvere.
6. **`python scripts/check_documentazione.py`** deve uscire pulito. Se segnala
   un piano orfano o l'indice fuori sync, sistemalo ora — non «poi».
7. **Committa tutto**, doc insieme al codice che documenta. `git add` non basta:
   il 30/8 il `code-reviewer` ha bloccato una chiusura perché i file erano
   staged e mai commitati. Controlla `git status --short` pulito.
8. **Riscrivi questo file** per la sessione successiva: cosa è stato chiuso, cosa
   resta, qual è la prossima dimensione. È l'unica cosa che passa alla sessione
   dopo — se non lo aggiorni, quella riparte da informazioni vecchie.
9. **Di' a Mattia quanti commit sono in attesa** (`git log --oneline
   origin/main..main`). **Non pushare**: il push è il deploy e lo decide lui,
   la sera.

Se la dimensione **non** è chiusa a fine sessione, i punti 1-2 saltano ma
**3-9 no**: il verbale dice a che punto sei, e il prompt dice da dove ripartire.
