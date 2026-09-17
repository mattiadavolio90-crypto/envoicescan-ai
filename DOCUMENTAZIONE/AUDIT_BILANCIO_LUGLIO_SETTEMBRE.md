# Bilancio del lavoro di audit — 1 luglio → 17 settembre 2026

> **A cosa serve questo file.** Risponde a una sola domanda: **quanto lavoro e'
> stato fatto in questi due mesi e mezzo, e cosa ha prodotto.** E' il documento
> da leggere per primo: da qui si scende nel dettaglio, non viceversa.
>
> Le cifre sono state **ri-misurate il 17/09/2026**, non ereditate dai documenti
> precedenti. Dove una cifra circolava gia' scritta ed era diversa, lo dico.

---

## Da dove si entra — i quattro documenti che contano

| Se vuoi sapere… | Leggi |
|---|---|
| **Quanto lavoro e' stato fatto** (questo file) | `DOCUMENTAZIONE/AUDIT_BILANCIO_LUGLIO_SETTEMBRE.md` |
| **Cosa e' gia' stato guardato, con quale metro, e quando si riapre** | `DOCUMENTAZIONE/AUDIT_COPERTURA.md` |
| **Le nove lenti trasversali, una per una** | `docs/storico/audit-2026-09/INDICE_LENTI_L1_L9.md` |
| **Il racconto di ogni singola sessione** | `docs/storico/*_STORICO.md` (3 file, 8.858 righe) |

Tutto il resto e' materiale di lavoro: verbali di singola lente, prompt di fase
archiviati, CSV di misura. Si aprono quando servono, non si leggono di fila.

---

## La cifra sola

**In 78 giorni: 811 commit, 291 dei quali correzioni, 245 file di test nuovi, e
tre cicli di audit piu' nove lenti trasversali — tutti chiusi.**

La suite e' passata da poco piu' di 11.000 test a **14.800** (al commit
`ceb458e`, con cui si chiude L9). La copertura eseguita del backend e' al **65%**.

---

## Il lavoro, in numeri misurati oggi

> Ogni cifra porta il **commit su cui e' stata presa**. Il periodo si e' chiuso in
> due tempi: il bilancio fino a `05640af`, poi L9 fino a `ceb458e`. Misure prese
> in momenti diversi non si sommano a mente — l'ancora dice quale vale quando.

| Misura | Valore | Come e' stata presa |
|---|---|---|
| Commit dal 01/07/2026 | **811** a `ceb458e` | `git log --since=2026-07-01 --oneline` contato |
| — di cui `fix(...)` | **291** (36%) | stesso comando, subject che iniziano con `fix(` |
| Distribuzione | 136 a luglio · 302 ad agosto · **373 a settembre** | per mese |
| File di test creati | **245** (su 318 totali in `tests/`) | `--diff-filter=A` su `tests/test_*.py` |
| Righe di test nel repo | **74.454** | `wc -l` su `git ls-files 'tests/*.py'` |
| Test raccolti dalla suite | **14.800** a `ceb458e` (14.768 a `05640af`) | `pytest --collect-only` dalla root |
| Copertura backend eseguita | **65%** (24.958 stmts, 8.224 miss) | `coverage run -m pytest -m "not sql"`, 429 s |
| Documentazione d'audit | **16.988 righe** su 34 file | `wc -l` sui `.md` di audit **tracciati da git** |
| Strumenti d'audit riusabili | **9 script**, 1.817 righe | `scripts/audit_*.py` |

> **Il 36% di commit di correzione non e' un segnale di fragilita'.** E' la firma
> di un periodo in cui si e' andati a **cercare** i difetti invece di aspettarli:
> in un audit, trovare e correggere *e'* il prodotto.

---

## Cosa e' stato fatto, in quattro blocchi

### 1. Tre cicli di audit per strato — luglio, agosto, settembre

Guardavano l'app **uno strato per volta**: security, bug, performance,
architettura, qualita', AI, database, test, Edge Functions, DevOps.

- **Ciclo 2026-07** — chiuso il 28/08. Dieci dimensioni, tutte con seconda
  passata e `code-reviewer`. Il frontend, creduto a basso rischio, ha prodotto
  **39 findings, 7 HIGH attivi su clienti reali**, tutti corretti.
- **Ciclo 2026-08** — chiuso il 29/08. Sette fasi, **8 decisioni aperte chiuse**
  in una sessione dedicata. Fra queste: il radar anomalie era *nato* rotto
  (filtrava una colonna mai esistita) e la sua regola duplicati avrebbe prodotto
  **897 notifiche false**.
- **Ciclo 2026-09** — chiuso il 09/09, insieme all'audit di compliance legale.
  Ha chiuso l'ultima zona mai letta del backend.

### 2. Nove lenti trasversali — 14 → 17 settembre

Cambio di metodo: non piu' per strato, ma **per proprieta' che attraversa gli
strati**. Ognuna ha prodotto un artefatto che prima non esisteva.

**18 difetti corretti, ognuno provato per mutazione.** Il dettaglio sta in
`INDICE_LENTI_L1_L9.md`; i quattro piu' significativi:

- **L6** — il periodo di default di Margini e Analisi fatture lo decideva il
  giorno del *server*: alle 00:30 del 1° ottobre, «Mese in corso» avrebbe
  mostrato settembre intero, MOL compreso.
- **L7** — importi non finiti (`NaN`, `Infinity`) passavano **entrambe** le copie
  degli helper di conversione e arrivavano a Postgres, dove `SUM()` li propaga.
- **L2** — 152 chiamate cross-tenant eseguite su un Postgres vero: **0 leak**, e
  2 difetti d'isolamento corretti.
- **L9** — col worker giu', quattro pagine di `/m` dicevano «Nessun incasso
  inserito in questo mese.» su dati **mai arrivati**. Il fix del 3/9 che
  distingue «non c'e' niente» da «non sono riuscito a chiedere» era arrivato al
  desktop e non al mobile: l'helper lo usavano 11 file, **uno solo** dei quali
  su `/m`. E non e' un caso di bordo — lo stato iniziale e' `null`/`[]`, quindi
  la frase falsa compare **alla prima apertura della pagina**, mentre il toast
  d'errore sparisce dopo pochi secondi e lascia in pagina solo quella.

### 3. La rete di presidi

Non e' un sottoprodotto: e' **cio' che resta** quando l'audit finisce. Un audit
senza presidi si consuma; con i presidi, il difetto non torna.

- **539 test su un Postgres vero** (`-m sql`) — le funzioni SQL vengono
  **eseguite**, non lette. Fino al 07/09 le funzioni del DB coperte da test erano
  **zero**; oggi sono 25.
- **101 test Deno** sulle Edge Functions.
- **40 file** che eseguono TypeScript con node, per la logica pura del frontend.
- La documentazione viva e' protetta da `tests/test_documentazione_onesta.py`: un
  `.md` che cita un simbolo inesistente fa fallire la suite.

### 4. Nove strumenti riusabili

`scripts/audit_*.py` — 1.817 righe. Non sono script usa e getta: il piu' grande
(`audit_ciclo_vita_colonne.py`, 707 righe) rifa' in una lettura l'inventario di
667 colonne su 528 file, e si ri-lancia quando si aggiunge una colonna.

---

## Il contatore di copertura era indietro — di quanto

Fino al 17/09 `AUDIT_COPERTURA.md` certificava il commit **`a82213e` del
09/09/2026**. Tutto il ciclo delle otto lenti (14 → 17 settembre) stava nelle sue
righe di tabella, ma **non era mai rientrato nella "riga che conta"** in cima al
file. La riga e' stata portata a `05640af` insieme a questo bilancio.

Il delta misurato, da `a82213e` a `05640af`:

| | Certificato (09/09) | A `05640af` (17/09) | Delta |
|---|---|---|---|
| Suite, test verdi | 13.258 verdi | **14.184** verdi | **+926** |
| — raccolti in totale | — | **14.768** (14.184 + 45 skip + 539 `-m sql`) | — |
| Test su Postgres vero | 176 | **539** | **+363** |
| Copertura backend | 61% | **65%** | **+4 punti** |
| Commit | — | — | **+138** (39 fix, 8 test, 48 docs) |
| File di test nuovi | — | — | **+64** (12.132 righe) |
| Migration | 144 | 148 | **+4** |
| Diff complessivo | — | — | **220 file, +30.646 / −1.288 righe** |

**In pratica: dopo la certificazione e' stato fatto un altro audit intero.**

> **Perche' due righe e non una.** I 13.258 del 09/09 erano test **verdi**; i
> 14.768 di oggi sono **raccolti**, e comprendono i 539 `-m sql` e i 45 skip che
> nel primo termine non c'erano. Confrontarli direttamente darebbe **+1.510**
> invece di +926: e' il delta che questo documento riportava nella sua prima
> stesura. Due cifre vere non sono confrontabili se non misurano la stessa cosa.

**Poi e' arrivata L9**, nello stesso giorno ma dopo `05640af`. Il contatore
certifica ora **`ceb458e`**, ed e' li' che si ferma il periodo:

| | A `05640af` | A `ceb458e` (L9 chiusa) | Delta |
|---|---|---|---|
| Suite, test verdi | 14.184 | **14.216** | **+32** (i presidi di L9) |
| — raccolti in totale | 14.768 | **14.800** | **+32** |
| Test su Postgres vero | 539 | **539** | — |
| Commit | — | — | **+4** |
| Lenti chiuse | 8 su 9 | **9 su 9** | **+1** |
| Difetti corretti dalle lenti | 14 | **18** | **+4** |

> Le due tabelle non si sommano a mente: la prima confronta `a82213e` con
> `05640af`, la seconda `05640af` con `ceb458e`. Ogni riga dice su quale commit
> e' stata presa, ed e' l'unico modo perche' restino vere quando il repo si muove.

---

## Cosa manca — due cose, dette per nome

> **Il ciclo delle lenti e' chiuso: L9 il 17/09/2026.** Nessuna lente resta in
> coda. Da qui vale la regola ordinaria — *quando tocchi un file, lo copri*.

1. **Quattro lenti su nove non hanno un verbale proprio** — L2, L4, L6, L7. Il
   loro racconto vive **solo** dentro la riga di `AUDIT_COPERTURA.md`, che per
   quelle e' lunga quanto un documento. L6 ha corretto 4 difetti, L7 tre: e'
   parecchio lavoro affidato a una cella di tabella. (L9 sarebbe stata la quinta:
   per questo ha un `.md` suo.)
2. **I residui dichiarati di L1** — le classi di difetto non refutate restano
   aperte, elencate per `file:riga` in `CLASSI_DI_DIFETTO.md`. Si chiudono
   leggendo il chiamante, una per una.

E un limite dichiarato, che non e' una voce di coda ma va saputo: **l'harness dei
test esegue `lib/`, non i `.tsx`**. La logica di rendering del frontend e'
presidiata per *forma*, non per comportamento — chiuderlo richiederebbe un runner
frontend, che e' una decisione gia' presa in senso contrario (punto 9, ciclo
2026-08).

> Quel che **non** manca, ed e' bene dirlo: il backend non ha piu' righe mai
> guardate, il perimetro di sicurezza e' chiuso (216 endpoint su 216), e i tre
> cicli per strato sono chiusi tutti e tre.

---

## Le tre cose che questo periodo ha insegnato sul metodo

**Un test verde non prova niente; un mutante ucciso si'.** E' la lezione che
attraversa tutti e tre i cicli. Sono rimasti verdi sul bug: un mock generoso (i
test del radar passavano su una colonna mai esistita), un `tsc --noEmit`, un test
che legge il *sorgente* invece di eseguirlo. Per questo ogni difetto corretto in
queste nove lenti e' stato provato per mutazione — e in tre casi la mutazione ha
rivelato che il presidio era **finto**.

**Una cifra ereditata e' una cifra sbagliata.** E' successo abbastanza volte da
diventare una regola: il tetto delle righe misurato su una query troncata, quattro
numeri sbagliati in un verbale, il costo del personale dichiarato «0 righe,
procedi» e diventato 26.453 € il giorno dopo. Il caso limite e' del **16/09**: il
rilevatore di L5 camminava sul **filesystem** invece che sul repo, contava 4
script mai committati, ed era **verde in locale e rosso in CI sullo stesso
commit**. Tre passate di review locali non l'avevano visto: l'ha trovato il primo
push.

**Chi scrive il presidio non puo' essere l'unico a provarlo.** E' la lezione di
**L9**, ed e' costata quattro review, tutte rosse. 22 mutanti provati e uccisi,
ma **9 sono sopravvissuti al primo tentativo** del presidio che doveva ucciderli
— e **7 dei 9 li ha scritti il code-reviewer**, non chi aveva scritto i presidi.
Dal terzo giro in poi *tutti* i sopravvissuti sono suoi. La ragione e'
strutturale, non di bravura: una batteria di mutanti scritta da chi conosce il
presidio misura **cio' che il presidio gia' guarda**. I miei cancellavano il
token che il test cerca; i suoi lo lasciavano al suo posto e cambiavano il
significato intorno — un flag riazzerato nel `finally`, una variabile in
*shadowing*, i due messaggi **scambiati** fra il ramo del guasto e quello del
vuoto, un ramo duplicato per far quadrare un conteggio aggregato mentre la vista
di default restava scoperta.

Il corollario e' piu' scomodo: **una copertura non si sostituisce, si affianca.**
Sempre in L9, spostare la decisione in un helper eseguibile sembrava un
miglioramento netto — e ha **riaperto il difetto che la lente era nata per
chiudere**. L'helper copre la *decisione*; il booleano che gli arriva nasce nel
`catch` di un `.tsx`, che l'harness non esegue. Il mutante storico della lente e'
tornato a sopravvivere, con la suite verde. Le due coperture erano **ortogonali,
non alternative**: toglierne una per l'altra ha lasciato scoperto proprio il
punto d'ingresso del difetto.

---

## Nota su un duplicato — rimosso

`docs/storico/audit-2026-09/AUDIT_COPERTURA.md` era una **copia ferma al
07/09/2026**, divergente da quella viva in `DOCUMENTAZIONE/` (373 righe contro
555 di allora) e senza le righe delle lenti. Nessun documento la citava, e chi
l'avesse aperta per prima avrebbe letto uno stato vecchio di dieci giorni
credendolo corrente.

**E' stata cancellata il 17/09/2026 da `3307a36`**, lo stesso commit che ha
creato questo bilancio: oggi nel repo esiste una sola `AUDIT_COPERTURA.md`, in
`DOCUMENTAZIONE/`. La nota resta a verbale del perche' e' sparita.
