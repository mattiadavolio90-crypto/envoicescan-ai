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
| **Le otto lenti trasversali, una per una** | `docs/storico/audit-2026-09/INDICE_LENTI_L1_L8.md` |
| **Il racconto di ogni singola sessione** | `docs/storico/*_STORICO.md` (3 file, 8.858 righe) |

Tutto il resto e' materiale di lavoro: verbali di singola lente, prompt di fase
archiviati, CSV di misura. Si aprono quando servono, non si leggono di fila.

---

## La cifra sola

**In 78 giorni: 803 commit, 310 dei quali correzioni, 245 file di test nuovi, e
tre cicli di audit piu' otto lenti trasversali — tutti chiusi.**

La suite e' passata da poco piu' di 11.000 test a **14.768**. La copertura
eseguita del backend e' al **65%**.

---

## Il lavoro, in numeri misurati oggi

| Misura | Valore | Come e' stata presa |
|---|---|---|
| Commit dal 01/07/2026 | **803** | `git log --since=2026-07-01` |
| — di cui `fix(...)` | **310** (39%) | stesso comando, filtrato sul prefisso |
| Distribuzione | 136 a luglio · 302 ad agosto · **365 a settembre** | per mese |
| File di test creati | **245** (su 318 totali in `tests/`) | `--diff-filter=A` su `tests/test_*.py` |
| Righe di test nel repo | **74.130** | `wc -l` su `git ls-files 'tests/*.py'` |
| Test raccolti dalla suite | **14.768** | `pytest --collect-only` dalla root |
| Copertura backend eseguita | **65%** (24.958 stmts, 8.224 miss) | `coverage run -m pytest -m "not sql"`, 429 s |
| Documentazione d'audit | **17.173 righe** su 36 file | `wc -l` sui `.md` di audit tracciati |
| Strumenti d'audit riusabili | **9 script**, 1.817 righe | `scripts/audit_*.py` |

> **Il 39% di commit di correzione non e' un segnale di fragilita'.** E' la firma
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

### 2. Otto lenti trasversali — 14 → 17 settembre

Cambio di metodo: non piu' per strato, ma **per proprieta' che attraversa gli
strati**. Ognuna ha prodotto un artefatto che prima non esisteva.

**14 difetti corretti, ognuno provato per mutazione.** Il dettaglio sta in
`INDICE_LENTI_L1_L8.md`; i tre piu' significativi:

- **L6** — il periodo di default di Margini e Analisi fatture lo decideva il
  giorno del *server*: alle 00:30 del 1° ottobre, «Mese in corso» avrebbe
  mostrato settembre intero, MOL compreso.
- **L7** — importi non finiti (`NaN`, `Infinity`) passavano **entrambe** le copie
  degli helper di conversione e arrivavano a Postgres, dove `SUM()` li propaga.
- **L2** — 152 chiamate cross-tenant eseguite su un Postgres vero: **0 leak**, e
  2 difetti d'isolamento corretti.

### 3. La rete di presidi

Non e' un sottoprodotto: e' **cio' che resta** quando l'audit finisce. Un audit
senza presidi si consuma; con i presidi, il difetto non torna.

- **539 test su un Postgres vero** (`-m sql`) — le funzioni SQL vengono
  **eseguite**, non lette. Fino al 07/09 le funzioni del DB coperte da test erano
  **zero**; oggi sono 25.
- **101 test Deno** sulle Edge Functions.
- **34 file** che eseguono TypeScript con node, per la logica pura del frontend.
- La documentazione viva e' protetta da `tests/test_documentazione_onesta.py`: un
  `.md` che cita un simbolo inesistente fa fallire la suite.

### 4. Nove strumenti riusabili

`scripts/audit_*.py` — 1.817 righe. Non sono script usa e getta: il piu' grande
(`audit_ciclo_vita_colonne.py`, 707 righe) rifa' in una lettura l'inventario di
667 colonne su 528 file, e si ri-lancia quando si aggiunge una colonna.

---

## Il contatore di copertura era indietro — di quanto

`AUDIT_COPERTURA.md` certifica il commit **`a82213e` del 09/09/2026**. Tutto il
ciclo delle otto lenti (14 → 17 settembre) sta nelle sue righe di tabella, ma
**non e' mai rientrato nella "riga che conta"** in cima al file.

Il delta misurato oggi, da `a82213e` a `05640af`:

| | Certificato (09/09) | Oggi (17/09) | Delta |
|---|---|---|---|
| Suite | 13.258 verdi | **14.768** raccolti | **+1.510** |
| Test su Postgres vero | 176 | **539** | **+363** |
| Copertura backend | 61% | **65%** | **+4 punti** |
| Commit | — | — | **+138** (39 fix, 8 test, 48 docs) |
| File di test nuovi | — | — | **+64** (12.132 righe) |
| Migration | 144 | 148 | **+4** |
| Diff complessivo | — | — | **220 file, +30.646 / −1.288 righe** |

**In pratica: dopo la certificazione e' stato fatto un altro audit intero.** La
riga in cima al contatore va aggiornata, ed e' l'unica correzione di sostanza che
questo bilancio impone.

---

## Cosa manca — tre cose, dette per nome

1. **L9 — «Giornata del cliente e parita' `/m`»**, la nona e ultima lente. Non
   iniziata, e **senza piano scritto** (L5–L8 ne avevano uno ciascuna). E' l'unica
   voce in coda.
2. **Quattro lenti su otto non hanno un verbale proprio** — L2, L4, L6, L7. Il
   loro racconto vive **solo** dentro la riga di `AUDIT_COPERTURA.md`, che per
   quelle e' lunga quanto un documento. L6 ha corretto 4 difetti, L7 tre: e'
   parecchio lavoro affidato a una cella di tabella.
3. **I residui dichiarati di L1** — le classi di difetto non refutate restano
   aperte, elencate per `file:riga` in `CLASSI_DI_DIFETTO.md`. Si chiudono
   leggendo il chiamante, una per una.

> Quel che **non** manca, ed e' bene dirlo: il backend non ha piu' righe mai
> guardate, il perimetro di sicurezza e' chiuso (216 endpoint su 216), e i tre
> cicli per strato sono chiusi tutti e tre.

---

## Le due cose che questo periodo ha insegnato sul metodo

**Un test verde non prova niente; un mutante ucciso si'.** E' la lezione che
attraversa tutti e tre i cicli. Sono rimasti verdi sul bug: un mock generoso (i
test del radar passavano su una colonna mai esistita), un `tsc --noEmit`, un test
che legge il *sorgente* invece di eseguirlo. Per questo ogni difetto corretto in
queste otto lenti e' stato provato per mutazione — e in tre casi la mutazione ha
rivelato che il presidio era **finto**.

**Una cifra ereditata e' una cifra sbagliata.** E' successo abbastanza volte da
diventare una regola: il tetto delle righe misurato su una query troncata, quattro
numeri sbagliati in un verbale, il costo del personale dichiarato «0 righe,
procedi» e diventato 26.453 € il giorno dopo. Il caso limite e' del **16/09**: il
rilevatore di L5 camminava sul **filesystem** invece che sul repo, contava 4
script mai committati, ed era **verde in locale e rosso in CI sullo stesso
commit**. Tre passate di review locali non l'avevano visto: l'ha trovato il primo
push.

---

## Nota su un duplicato

`docs/storico/audit-2026-09/AUDIT_COPERTURA.md` e' una **copia ferma al
07/09/2026**, divergente da quella viva in `DOCUMENTAZIONE/` (373 righe contro
555, e senza le righe delle lenti). Nessun documento la cita. E' un fossile:
chi lo aprisse per primo leggerebbe uno stato vecchio di dieci giorni credendolo
corrente.
