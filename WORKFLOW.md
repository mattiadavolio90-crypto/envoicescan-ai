# WORKFLOW — Come si lavora a una feature su ONEFLUX

Disciplina di **processo**: il come. I vincoli di dominio — il cosa-non-rompere —
stanno in `CLAUDE.md`.

Regola guida: **semplicità prioritaria**. Se un passo costa più di quanto fa
risparmiare, salta il passo.

> ## Due regole su questo documento
>
> **1. Una regola nuova entra solo se ne esce una.** Chi aggiunge una sezione
> dichiara quale toglie o accorpa. Se non ne trova nessuna da togliere, la regola
> nuova probabilmente appartiene a un hook, a una skill o alla memoria — non qui.
>
> **2. Una regola sta qui solo se è azionabile e non automatizzabile.** Se un
> hook o una skill possono eseguirla, ci vanno. Se è un fatto storico, va in
> memoria. Il *racconto* di perché una regola esiste sta in fondo (§11), non
> accanto alla regola.
>
> Perché: al 2/9/2026 questo file dichiarava «una pagina» e ne aveva **569**, con
> la numerazione rotta per accrescimento (`1bis`, `1ter`, `5bis`). Ogni incidente
> aveva aggiunto un paragrafo, nessuno ne aveva mai tolto uno — e le regole che
> contano stavano in fondo, dove non arrivava più nessuno.

---

## 1. Si accumula, si spedisce una volta sola

Tutte le sessioni committano su **`main` locale**. Niente branch, niente PR.
La sera, quando Mattia lo dice: **un push, un deploy**.

1. **Durante il giorno**: commit atomici su `main` locale, uno per intervento
   concluso. **Nessun push, nessuna PR.** Una sessione nuova parte da `main`.
2. **Un branch si apre SOLO se** quel lavoro **potrebbe non essere spedito**
   (esperimento, refactor incerto). **Non** in base alla dimensione. Se un branch
   esiste e il lavoro va spedito, riportalo su `main` e chiudilo senza mergiarlo.
3. **Prima di spedire**: `touch .claude/.pre_merge` (fa girare la suite completa
   allo Stop), `/code-reviewer` sul cumulativo `origin/main..main`, poi il push.

**Il deploy è legato al push, non alla sessione.** Un commit locale non spedisce
niente: 4 sessioni → 4+ commit → **un push, un deploy**. Succede da solo, se non
si pusha.

**Divieto operativo**: mai `git push`, `gh pr create`, `gh pr merge` di
iniziativa. Prima di spedire, guarda cosa parte:

```bash
git log --oneline origin/main..main    # cosa partirebbe adesso
git diff --stat origin/main..main      # quanto, e su quali file
```

### Il parallelo è il regime normale

Più sessioni lavorano insieme sulla stessa directory. **Commit e file non tuoi
sono lo stato atteso**, non un allarme. A fine sessione, una riga:

> In coda: 7 commit (3 miei, 4 di altre sessioni), pronti per stasera.

Niente ⚠️, niente domanda. **Vietato**: committare lavoro non tuo (`git add -A`
è il modo tipico di farlo per sbaglio — elenca i tuoi file); toccare senza dirlo
un file già modificato in `git status`; pushare di iniziativa.

**Se un rosso non è tuo**: i test possono fallire per lavoro non committato di
un'altra sessione. Verifica che il rosso esista anche senza le modifiche altrui
prima di concludere che l'hai rotto tu.

**Segnalare un rischio che nasce da lavoro altrui** richiede tre pezzi: **di chi
è**, **cosa rischia**, **chi deve agire** (quasi sempre: la sessione che l'ha
scritto). Senza il primo, Mattia legge una tua dimenticanza.

> Non è mio: una sessione sta lavorando al tab Admin e ha una migration ancora
> non committata. Se stasera parte il codice senza lo schema, quel tab si rompe.
> La chiude quella sessione — se non la chiude, dimmelo e la committo io.

**Igiene branch**: con la regola sopra non dovrebbero nascere. Se ne resta uno, va
chiuso appena il suo lavoro è su `main` o è stato buttato. `/pulisci-branch`
elenca senza eliminare.

---

## 2. Pianificare ed eseguire

Il **plan mode** è il default per qualsiasi lavoro non banale: si progetta in sola
lettura, Mattia approva, poi si esegue.

Chiudere e riaprire una sessione per fase è un'ottimizzazione, **non la regola**:

- **1-2 fasi finibili in un pomeriggio** → una sessione sola. Aprirne una seconda
  fa spendere più token, non meno (ogni sessione riparte da zero).
- **3+ fasi, o più giorni** → ciclo a più sessioni, con
  `docs/piani/PIANO_<feature>.md` (§3) a portare lo stato.

### Il file di piano

Solo per lavori oltre la singola sessione. **Uno per feature**, git-ignorato
(`docs/piani/*.md`), effimero:

```markdown
# PIANO — <feature>
Sessione di apertura: <data>. Obiettivo in una frase.

## Decisioni concordate (non ridiscutere senza motivo)
## Fasi
- [ ] Fase 1 — <cosa> · modello: <vedi §4>
## Stato / note aperte
```

I `memory/project_*.md` restano la fonte di verità sullo stato **tra** sessioni;
il piano è la mappa operativa del lavoro **in corso**. A feature deployata:
aggiorna la memoria, **elimina** il piano. Mai due fonti sullo stesso stato.

⚠️ **Si aggiorna una sessione alla volta**: due sessioni sullo stesso file si
sovrascrivono senza avviso.

---

## 3. "A che punto siamo?" si risponde in cinque righe

1. **Una riga secca**: finito / manca X / bloccato su Y.
2. **Al massimo 3 punti**, uno per cosa aperta, una riga ciascuno.
3. **Una sola domanda**, se serve una sua decisione.
4. **«Vuoi il dettaglio?»** — e fermati lì.

**Massimo ~10 righe. Niente tabelle, blocchi di codice, nomi di file o funzioni**,
salvo che il nome *sia* la risposta.

Il criterio non è «quanto so», è **cosa gli serve per decidere il prossimo passo**.
Se una frase non cambia cosa farà nei prossimi cinque minuti, si taglia — anche se
è vera, anche se l'hai appena misurata.

**Non fare**: ricostruire il ragionamento; citare percorsi con numero di riga;
spiegare *perché* una cosa non è un problema invece di dire che non lo è; elencare
cosa non hai fatto; premettere l'autocritica. Un tuo errore si corregge in **mezza
riga**, non in un paragrafo. Vale **in ogni sessione**, anche quando non lo ricorda.

---

## 4. Fine planning: riepilogo non tecnico + modello per fase

**Sempre**, a ogni `ExitPlanMode`: un riepilogo breve in linguaggio **non tecnico**,
comprensibile senza aver letto il piano. **E subito sotto questa tabella**, una
riga per fase anche quando la fase è una sola:

| Fase | Cosa fa | Modello | Sforzo |
|---|---|---|---|
| 1 | *(una riga, in italiano corrente)* | Opus | `ultrathink` |

Se una fase è `ultrathink`, scrivi accanto **in mezza riga perché** («tocca il
MOL», «apre una dimensione nuova»): è l'unico modo per accorgersi se lo si sta
mettendo ovunque per abitudine. Con più fasi, indica quali stanno nella stessa
sessione: cambiare modello a metà sessione non si può.

### Quale modello, quanto sforzo

**Il default è Opus. Sonnet è l'eccezione.** Si decide fase per fase.

| Tipo di fase | Modello | Sforzo |
|---|---|---|
| Pianificazione, design, decisioni architetturali | Opus | `ultrathink` |
| Audit di una dimensione, debug non ovvio | Opus | `ultrathink` |
| Fix su regola di dominio (MOL, categorizzazione, auth) | Opus | `ultrathink` |
| UI nuova, modifiche al worker, scelte di interazione | Opus | normale |
| Implementazione di un piano già deciso | Opus | normale |
| Trascrizione: il piano dice file, riga e cosa sostituire | Sonnet | normale |
| Ricerca/scan ampia read-only | sub-agente `Explore` | — |

**Due test secchi.** *Quale modello*: la fase richiede **decisioni**? → Opus, anche
se il piano è dettagliato. Solo **trascrizione**? → Sonnet. Nel dubbio, Opus.
*Quanto sforzo*: se sbagliare **si vede sui dati dei clienti** o costa una sessione
di ripianificazione → `ultrathink`. Se sbagliare significa un test rosso che te lo
dice subito → normale.

`ultrathink` si attiva scrivendo la parola nel messaggio che apre la fase. Metterlo
ovunque è come non metterlo da nessuna parte: smetti di guardare la colonna.

---

## 5. Una cosa alla volta, chiusa davvero

Una dimensione/fase si apre solo quando la precedente è **completamente chiusa**.
Niente strascichi, niente «lo finiamo dopo».

**Chiusa davvero** significa tutte e cinque, non tre su cinque:

1. Il codice fa quello che deve, **provato per mutazione** (§6).
2. Il lavoro è **committato** — non `git add`-ato.
3. **Verbale** nello STORICO del ciclo, con la data. **Tetto 40 righe.**
4. **Stato del ciclo aggiornato**: la dimensione si sposta in «cosa è chiuso», e
   **ogni voce del tuo "non fatto" entra nei residui aperti**.
5. **Contatore `AUDIT_COPERTURA.md` ri-misurato** (non copiato) e
   `python scripts/check_documentazione.py` pulito.

**Eseguili con `/chiusura-feature`**, che li fa tutti e cinque in ordine. Un lavoro
che non sta in una sessione non è un'eccezione: si divide in fasi, e **ogni fase**
rispetta i cinque punti.

**Fine fase ≠ deploy.** Una checklist tutta `[x]` significa «pronto e committato su
`main` locale». Col ciclo ad accumulo la domanda si pone **una volta per ciclo**.

**Il prompt della prossima sessione non è un passo della chiusura**: si scrive solo
se Mattia lo chiede (`/salva-stato`).

**Fine implementazione**: confronto esplicito col piano approvato. Deviazioni →
elencate col motivo. Nessuna deviazione → dichiararlo, non darlo per scontato.

---

## 6. Come si conduce un ciclo di audit

Il **metodo** vive qui; lo **stato di un ciclo** vive nel suo documento (oggi
`DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`). Non duplicare: una regola scritta
solo nel documento di stato sparisce quando il ciclo viene archiviato.

Il documento di stato è in **due file**: quello principale dice *cosa manca* e
resta leggibile in un minuto; il `_STORICO.md` raccoglie i verbali. Il dettaglio va
**sempre** nello storico.

- **Apri con `/apertura-sessione`**: controlli di sessione, stato, residui, e la
  misura a DB dell'area **prima** di sceglierla.
- **Profondità minima**: una passata read-only + una di remediation. Se la
  remediation scrive codice, **`code-reviewer` prima di dichiarare chiusa** — non
  opzionale.
- **Riverifica i numeri con un metodo diverso** da quello che li ha prodotti:
  perimetro, conteggio dei finding, gravità. Un numero preso per buono dall'agente
  che l'ha prodotto non è verificato, è solo scritto.
- **Una dimensione su perimetro parziale è `parziale`, non `chiusa`.**
- **Un ciclo si chiude a copertura completa**, non alla prima passata verde.
- **I buchi di copertura test trovati durante un audit non si chiudono in coda alla
  stessa sessione**: sono scrittura, non audit. Si pianificano a parte.

### Prova per mutazione

Si rimuove il fix su **copia in scratchpad** (mai sul file del branch) e si
controlla che i test tornino rossi. Un test che non fallisce quando il difetto
torna non è una rete. Riporta il bilancio e **perché** i sopravvissuti
sopravvivono.

⚠️ Se il pattern non esiste nel sorgente non hai mutato niente: «sopravvissuto» non
misura nulla.

---

## 7. Manutenzione della documentazione

Quando una fase/feature/piano si chiude:

```bash
python scripts/check_documentazione.py
```

Poi agisci **subito, senza chiedere conferma**, sui casi ovvi del lavoro appena
chiuso: documento chiuso il cui contenuto è già in memoria o in un commit →
**elimina**; documento chiuso con valore predittivo → **`docs/storico/`**; link
rotto dal tuo lavoro → **ripara**; documento nuovo → **aggiungi all'indice** di
`MAPPA_TECNICA.md` §6 ora, non "poi".

**Segnala invece di decidere** quando è dubbio — es. un piano che non hai scritto tu.

Non è un hook perché nessun evento tecnico distingue «una feature si è chiusa» da
«ho risposto a una domanda»: quel giudizio richiede il contesto della conversazione.

---

## 8. Gli hook, e come sono tarati

| Hook | Quando agisce |
|---|---|
| `claude_hook_test_gate.py` | solo `.md` → niente; lavoro in corso → i test dei file toccati; `.pre_merge`/`main`/file globale → suite completa |
| `claude_hook_reviewer_gate.py` | > 8 file non-test, > 400 righe nette, o path sensibile — misurati sul merge-base con `main`. Avvisa anche se molto codice cambia senza che stato/contatore siano toccati |
| `claude_hook_promemoria.py` | su Edit/Write: ricorda le trappole di dominio nell'istante in cui tocchi un file critico |
| `claude_hook_db_guard.py`, `branch_guard.py`, `registra_sessione.py`, `precompact_snapshot.py` | protezioni su DB, branch e continuità di sessione |

I **path sensibili non hanno soglia**: un fix di tre righe su `auth_service.py` o
`ai_service.py` merita la review quanto un refactor da 400. Se un gate **non riesce
a misurare**, blocca dicendolo: «non lo so» e «niente da rivedere» non sono la
stessa cosa.

L'hook parla nel momento dell'azione; il piano e la memoria conservano l'intento
tra sessioni. Sono leve complementari.

---

## 9. Problema segnalato da un cliente: prima cerca, poi analizzi

Prima di un'analisi da zero, cerca se è già stato riscontrato: `memory/project_*.md`
e `DOCUMENTAZIONE/` (inclusi i `docs/storico/*.md`). Un problema già diagnosticato —
anche su un cliente diverso — spesso ha la stessa causa radice.

---

## 10. Perché queste regole — il racconto

Non sono istruzioni: sono gli incidenti che le hanno generate. Si leggono se una
regola sembra arbitraria, non prima di lavorare.

**§1, l'accumulo.** Nessuna regola aveva mai imposto branch-e-PR: era una
consuetudine auto-alimentata. Al 30/8/2026 il repo aveva **19 branch remoti** (15
già dentro `main`) e ~35 locali risalenti a maggio. E, dato che spedire = deploy,
una richiesta di autorizzazione per ogni intervento: 5 merge il 28/8 fra le 12:44 e
le 16:49, in piena fascia di servizio. La versione col branch condiviso non bastava
perché ogni sessione che non ne sapeva ne apriva uno suo: il 31/8 il lavoro era in
due posti, e la sera sarebbero stati due merge in ordine obbligato.

**§1, il parallelo.** Le sessioni chiedevano a Mattia cosa fare dei commit altrui —
cioè conferma della normalità — abbastanza spesso da rendere necessaria la regola
(1/9/2026). E una segnalazione vera («c'è una migration non committata») ha prodotto
la mossa sbagliata perché non diceva **di chi era**: Mattia ha letto una
dimenticanza della sessione che parlava.

**§3, le cinque righe.** Il 31/8, su una domanda da tre righe di risposta, sono
arrivati: il ragionamento completo, i percorsi con numero di riga, la spiegazione
del perché una cosa non era un problema, e l'autocritica in cima. Tutto corretto,
tutto fuori posto.

**§4, il modello.** La versione precedente dava «esecuzione meccanica → Sonnet» come
regola binaria. Applicata alla lettera su «Ristrutturazione Personale» ha prodotto
fasi ciascuna corretta e incoerenti fra loro: una ha reintrodotto un toggle che un
commento dichiarava ridondante, un'altra ha consegnato 5 endpoint senza la UI per
raggiungerli. «Tutte le funzioni ci sono ma la pagina è incasinata» è costato una
sessione di ripianificazione. Il `code-reviewer` non intercetta questa classe:
verifica la correttezza *dentro* la fase, mai la coerenza *fra* le fasi.

**§5, una cosa alla volta.** Il 31/8 c'erano due piani in `docs/piani/`: uno con
tutte le fasi spuntate e il codice in produzione da giorni, l'altro che ripeteva
regole superate («un solo branch di lavoro», «merge = deploy») e le avrebbe rimesse
in circolo alla prima sessione che lo apriva. Il danno non è il file: è che una
sessione nuova non sa **quali** documenti sono ancora veri.

**§5, i cinque punti.** Al 2/9/2026 la skill di chiusura ne eseguiva **due**: chi la
invocava credeva di aver chiuso e aveva saltato verbale, residui e contatore. Sei
sessioni di fila hanno chiuso una dimensione senza aggiornare la roadmap; il file di
stato è rimasto indietro di tre giorni e nessun controllo lo vedeva.

**§6, la riverifica.** Nel ciclo 2026-07 è caduta 8 volte una severità ereditata;
nel 2026-08 il `code-reviewer` ha trovato un errore in **ogni** fase; nel 2026-09
le ipotesi del prompt di sessione erano false in **5 casi su 10**, e un'area
indicata da un prompt aveva 0 righe a DB.

**§8, le soglie.** Le precedenti (3 file / 150 righe, misurate sull'ultimo commit)
scattavano su quasi ogni sessione. **Un gate che scatta sempre viene saltato per
riflesso invece che letto** — ed è il motivo per cui ogni soglia qui è tarata
sull'evitare il falso positivo, non sul massimizzare la copertura.
