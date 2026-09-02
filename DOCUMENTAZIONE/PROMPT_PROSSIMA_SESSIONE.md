# Prompt prossima sessione — dopo `impostazioni/`, e una priorità ribaltata dalla misura

> Scritto il 2/9/2026 mattina. La sessione ha fatto la 1ª passata su
> `(app)/impostazioni/` (22 test dove non ce n'era nessuno), corretto **un
> difetto che il cliente avrebbe visto**, e migrato il test della password
> all'harness condiviso.
>
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha violato **sette** volte in quattro giorni.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git branch --show-current                # NON basta git log: vedi sotto
git status --short
git log --oneline origin/main..main      # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, col numero che leggi tu adesso.
Il push manda tutti i commit accumulati — e **il push È il deploy**.

### ⚠️ Un'altra sessione può lasciarti su un branch che non è `main`

Il 2/9 la sessione categorizzazione ha creato **`push-doc-tmp`**, ci ha
cherry-piccato i **propri** 3 commit e ha lasciato il repo con HEAD **lì sopra**.
I miei 2 commit erano su `main`: se quel branch fosse stato pushato, il mio
lavoro non sarebbe partito. `git log` non lo segnala — mostra commit plausibili.

> **Controlla `git branch --show-current`, non solo il log.** E verifica dove
> stanno i tuoi commit con `git branch --contains <sha>`. Il branch altrui non si
> tocca: si dice **di chi è** e **chi deve agire**.

Stessa famiglia: un `git add -A` di un'altra sessione può **inglobare le tue
modifiche non committate** in un commit altrui. Il 2/9 è successo con
`AUDIT_COPERTURA.md` (contenuto salvo, ma finito nel commit `fc68e49`).

---

## 1. Cosa è stato fatto, e cosa NON riaprire

**Il difetto corretto — il piano `free`.** Le mappe dei piani erano **due e
divergenti**: `account-client.tsx` (base/plus/pro, Title Case) e `lib/admin.ts`
(free/base/plus/pro, MAIUSCOLO). Il backend conosce `free`
(`config/constants.py::PIANO_LIMITI_FATTURE_MESE`) e **il menu admin lo offre**
(`PIANO_OPTIONS`): assegnarlo a una sede faceva mostrare al cliente la stringa
grezza minuscola `free`, senza prezzo.

> **Era latente, non un incidente** — e va detto così. Misurato a DB: i due
> utenti con `users.piano='free'` vedevano entrambi "Base", perché la sede
> risolta ha `piano='base'` e la sede a piano NULL di OFFSIDE è `sede_tecnica`,
> esclusa da `_resolve_ristorante_id`. La mia prima lettura diceva «il cliente lo
> vede adesso»: **sbagliata**, corretta dalla misura prima di scrivere il piano.

Ora: `lib/piani.ts` (40 righe) è la fonte unica per cliente e admin — un solo
record per piano con **entrambe** le rese, così non possono divergere. Deciso da
Mattia: label `"Free"`, dicitura `"Piano di prova"` al posto del prezzo.
`lib/impostazioni-account.ts` (62 righe) ha barra di utilizzo, i tre stati
dell'assistente AI, le due conferme distruttive.

**Non riaprire:**
- **Le conferme SVUOTA/ELIMINA non vanno uniformate.** `SVUOTA` è
  case-sensitive, `ELIMINA` no. È **deliberato**: il worker rivalida con la
  stessa asimmetria (`services/routers/account.py:284` e `:405`). I test la
  congelano apposta perché nessuno la "corregga" credendola una svista.
- **`fmtDate` non si tocca.** Il bug del parsing UTC non è raggiungibile qui
  (l'input è sempre un timestamp completo, mai una data nuda) e sostituirla con
  `formatData` **cambierebbe la data a schermo**. Il perché è scritto in un
  commento sopra la funzione.
- **`limite = 0` dà barra vuota e verde**, non "illimitato": preesistente,
  congelato in un test invece che cambiato.

---

## 2. La prossima dimensione — e perché NON è l'agenda

Il prompt di ieri indicava `agenda/` (693 righe). **Misurata a DB il 2/9:
`turni_personale` 0 righe, `diario_eventi` 2, `dipendenti` 1, `spese_extra` 16.**
L'area è sostanzialmente vuota in produzione: testarla ora congelerebbe scelte di
dominio che nessun cliente ha mai validato.

> **La priorità ereditata da un documento va ri-misurata come le cifre.** Non è
> la dimensione del codice a dire quanto è vivo.

C'è comunque lavoro pronto, **per quando l'agenda avrà dati**:
- `calcolaOreTotali` è duplicata (`personale-tab.tsx:134` / `mobile-turni.tsx:152`).
  Le ho confrontate riga per riga: **oggi identiche, nessun bug attivo.**
- Il costo turno invece **diverge**: desktop `personale-tab.tsx:149` ha
  `Math.max(0, oreT - ext)`, mobile `mobile-turni.tsx:964` fa `std * (ore - oreExt)`
  senza clamp. Irraggiungibile con 0 turni, ma è euro quando ne arriveranno.
- Gli helper date locali sono duplicati in **19 occorrenze su 12 file**.
- `personale-tab.tsx` è 1842 righe con ~20 `fetch`: le sue funzioni pure
  (`calcolaSlotOre`, `calcolaOreTotali`, `orarioTurno`) vanno spostate in `lib/`
  **prima** di poter testare il pannello personale — importarle da lì trascina
  l'intero componente React nel grafo e rompe l'harness.

**Aree ancora a zero logica estratta**, da misurare prima di sceglierne una:
`assistenza/` (292), `style-guide/` (256), `notifiche/` (242), agenda (693).
E in `impostazioni/` resta scoperto tutto il rendering: `CambioPasswordForm`,
`ZonaPericolosa`, `PrivacyGdprCard`, `AspettoCard`, `SediGruppoCard` sono handler
`async` con `fetch` + `useState`.

---

## 3. Debito lasciato aperto, con motivo

**`AUDIT_COPERTURA.md` ha tre cifre di riepilogo che non tornano — e non da
oggi.** Sommando la tabella vengono lette 26.966 / area 51.232; a HEAD `0234da8`,
cioè **prima** del lavoro del 2/9, venivano 26.864 / 51.128 contro un testo che
già diceva 24.733 / 52.780.

Ho aggiornato **solo il mio delta** (+102 righe, verificato) e **annotato lo
scarto invece di correggerlo**: ritoccare a mano una somma di cui non conosci
l'origine è esattamente l'errore che quel file documenta a proposito del 31/8.
Va riconciliato da chi conosce la provenienza dello scarto.

**`etichettaPianoAdmin` è esportata ma non ha ancora call-site**: i 3 punti admin
passano da `PIANO_LABEL`. Coperta da test, non è un difetto.

**`PIANO_COLOR` e `PIANO_OPTIONS` restano letterali** in `admin.ts` (scelta
dichiarata: le label di `PIANO_OPTIONS` incorporano i limiti). Oggi le chiavi
coincidono con `PIANI`, ma **nessun test le lega**: un piano nuovo domani darebbe
badge senza colore e voce di menu mancante. Una riga di test alla prossima
passata sull'area admin.

---

## 4. Regole di lavoro confermate anche stavolta

**L'oracolo, non il diff.** `statoUsageBar` è stata confrontata con l'originale
ricostruito da `git show HEAD:<file>` come `.mjs` in scratchpad: **225
combinazioni** (`usate`×`limite`, NaN e ±Infinity inclusi), **0 divergenze**.
**Validato sui due lati**: soglia 90→91 nell'oracolo → 3 divergenze; commento
cambiato → 0. Senza il secondo lato non sapresti se l'oracolo misura qualcosa.

**Mutazione su copia, mai sul file del branch.** 12 mutanti, 12 uccisi. Il
mutante-commento deve **sopravvivere**: se muore, i test misurano il testo.

**Un rosso si attribuisce con un worktree.** A metà sessione 3 rossi
(`test_audit_bug_passata2`, `test_route_api_auth_dichiarativa`). "Passano
isolati" è prova debole. La prova è stata: `git worktree add /tmp/vr 0234da8` +
i miei file + suite → 34 verdi. Venivano dai file **non committati** della
sessione parallela.

**`tsc` non esegue niente.** È uscito 0 su tutto; le zone toccate vanno comunque
rilette a occhio — una label che diventa vuota non è un errore di tipo.

**Chiusura §5bis**: bilancio mutanti coi sopravvissuti *elencati col motivo*,
suite verde, `npx tsc --noEmit`, `next build`, `/code-reviewer` sul cumulativo
(riproduci ogni rilievo prima di accettarlo), verbale, `AUDIT_COPERTURA.md`
**ri-misurato**, `check_documentazione.py`, prompt nuovo, **dire la coda a
Mattia senza pushare**.

---

## 5. Come si parla a Mattia

Non legge codice: decide **cosa** si fa. Alle domande di stato — **una riga di
verdetto, max 3 punti, una domanda, «Vuoi il dettaglio?»**. Tetto ~10 righe,
niente tabelle né percorsi con numero di riga. Un tuo errore si corregge in
**mezza riga**, non in un paragrafo. A fine planning (`ExitPlanMode`): riepilogo
non tecnico **+ tabella fase / modello / sforzo**.
