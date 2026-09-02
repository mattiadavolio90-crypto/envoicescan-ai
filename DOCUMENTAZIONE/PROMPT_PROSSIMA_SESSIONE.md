# Prompt prossima sessione — dopo `notifiche/`, e un errore che la review ha preso

> Scritto il 2/9/2026 sera. La sessione ha fatto la 1ª passata su
> `(app)/notifiche/` (14 test nuovi, 20 → 34) e corretto **un difetto che il
> cliente vedeva davvero**: la notifica «Manca l'incasso di ieri» arrivava senza
> il pulsante per andare a inserirlo.
>
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha violato **otto** volte in cinque giorni —
> l'ottava è di questa sessione, §1.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git branch --show-current                # NON basta git log
git status --short
git log --oneline origin/main..main      # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, col numero che leggi tu adesso.
Il push manda tutti i commit accumulati — e **il push È il deploy**.

A fine di questa sessione la coda era **2 commit, entrambi miei**
(`3533817`, `06ee637`). Se ne trovi di più, sono di altre sessioni: si contano e
si dice **di chi sono**, non si committano e non si pushano.

---

## 1. La lezione della sessione: la misura giusta, la conclusione sbagliata

Ho misurato bene e concluso male, e **il `code-reviewer` mi ha bloccato**.

Il dato era esatto: 33 notifiche a DB con `action_page='Agenda'` che non
producevano nessun pulsante. La correzione no: ho mappato `Agenda → /agenda`
**deducendo la destinazione dal nome del campo**, senza guardare dove sta oggi la
funzione. Gli incassi sono stati spostati fuori dall'Agenda: si inseriscono da
Margini → Calcolo (desktop) e da «Movimenti» (mobile). `(app)/agenda/` non
contiene nemmeno la stringa `incass`.

Avrei prodotto un pulsante che **non fa fare la cosa chiesta**, e per di più una
divergenza: per lo stesso topic il briefing e la notifica live usano `/margini`
da sempre.

> **Prima di mappare una CTA, cerca la funzione, non il nome.** Un
> `grep -ril "incass" sulla cartella` costava dieci secondi e avrebbe evitato
> tre errori (destinazione, "gemello" sbagliato, censimento incompleto).

Corollario che è già costato due volte: **una frase scritta in una docstring
diventa verità per chi legge dopo.** Avevo scritto «gli unici due `action_page`
letterali del codice»; sono nove (sette in `upload_handler.py:2051-2145`).

**Non riaprire:**
- **`agenda: "/margini"` nella mappa non è un refuso.** È voluto: la chiave è il
  vecchio nome di pagina, la destinazione è dove si inserisce l'incasso oggi. Un
  mutante che rimette `/agenda` **viene ucciso da un test**.
- **`"Vai ai Documenti"`, `"Carica Fatture"`, `"Gestione e Pagamenti"` restano
  senza pulsante**, di proposito: nessuna destinazione univoca, e `/documenti`
  non esiste. Meglio nessun pulsante di un 404 — congelato da un test.
- **Il merge `info`+`success`** nei filtri è una scelta di prodotto (una sola
  voce «Informazioni»). `success` **non esiste nei dati veri**: nessun dato lo
  proteggerebbe, per questo c'è un test.

---

## 2. Debito lasciato aperto, con motivo

**La CTA su mobile resta nascosta.** `incasso_mancante` nasce *sul* mobile
(`m/incasso-reminder.tsx`) ma punta a `/margini`, che è desktop: `hideCta` la
nasconde. È **scritto nel codice** accanto a `hideCta`. Il lavoro vero è un
deep-link mobile verso «Movimenti» (`m/turni`), che è una scelta di prodotto:
**chiedila a Mattia**, non deciderla. Non aggirare `hideCta`.

**I 7 `action_page` di `upload_handler.py:2051-2145`** sono nomi di pagina sul
percorso Streamlit (che gli audit danno per morto, ma **verificalo** se ci lavori:
darlo per morto senza misura è come ereditare una cifra).

**`scripts/regen_notifiche_utente.py:83` importa `services/notification_service.py`,
che non esiste più**: lo script è rotto. Preesistente, non introdotto qui, non
toccato — non era la dimensione aperta.

**`AUDIT_COPERTURA.md` ha ancora tre cifre di riepilogo che non tornano**, e non
da oggi. Ho aggiornato **solo il mio delta** (+58 righe, verificato con
l'aritmetica esplicita) e lasciato lo scarto annotato: ritoccare a mano una somma
di cui non conosci l'origine è l'errore che quel file documenta.

---

## 3. La prossima dimensione — misurala prima di sceglierla

Aree ancora a **zero** logica estratta, con le righe ri-misurate il 2/9 sera:
`agenda/` (693), `assistenza/` (292), `style-guide/` (256).

**Non ereditare questa lista come una priorità.** Il criterio che ha funzionato
due sere di fila è: **conta le righe a DB delle tabelle che l'area serve**, poi
scegli. È così che l'agenda è stata scartata (0 turni) e `notifiche/` scelta
(67 righe, 5 utenti, 5 negli ultimi 7 giorni).

Lavoro già individuato, **per quando l'agenda avrà dati**:
- il costo turno **diverge** fra desktop (`personale-tab.tsx`, con `Math.max(0, …)`)
  e mobile (`mobile-turni.tsx`, senza clamp). Irraggiungibile con 0 turni, ma è
  euro quando ne arriveranno.
- `calcolaOreTotali` è duplicata nei due file: **oggi identiche**, nessun bug attivo.
- Gli helper date locali sono duplicati in 19 occorrenze su 12 file.
- Le funzioni pure di `personale-tab.tsx` (1842 righe) vanno spostate in `lib/`
  **prima** di poter testare il pannello: importarle da lì trascina il componente
  React nel grafo e rompe l'harness.

In `notifiche/` resta scoperto il rendering (`SeverityIcon`, i filtri come UI, il
`dismiss` con `fetch`); in `impostazioni/` tutti i form (`CambioPasswordForm`,
`ZonaPericolosa`, `PrivacyGdprCard`, `AspettoCard`, `SediGruppoCard`).

---

## 4. Regole di lavoro confermate anche stavolta

**L'oracolo, non il diff.** Le tre funzioni estratte sono state confrontate con
l'originale ricostruito da `git show HEAD:<file>` come `.mjs` in scratchpad:
**2.340 casi**, 0 divergenze. **Validato sui due lati**: rompendo l'oracolo →
740 e 185 divergenze. Senza il secondo lato non sai se l'oracolo misura qualcosa.

**Mutazione su copia, mai sul file del branch.** 18 mutanti, 17 uccisi; il
sopravvissuto è il **commento di controllo** e doveva sopravvivere.

**Un test che usa input inventati misura il codice, non la realtà.** I test di
`ctaDi` esistevano, passavano, e usavano `pages/99_inesistente.py`: nessuno aveva
mai provato un valore letto dal DB. È così che il difetto è vissuto per mesi.

**`tsc` non esegue niente.** È uscito 0 anche sulla versione con la destinazione
sbagliata: un pulsante che punta alla pagina sbagliata non è un errore di tipo.

**Chiusura §5bis**: mutazione col bilancio *e i sopravvissuti motivati*, suite
verde, `tsc`, `next build`, `/code-reviewer` sul cumulativo (**riproduci ogni
rilievo prima di accettarlo** — qui ne ha prodotti 4, tutti fondati), verbale,
`AUDIT_COPERTURA.md` **ri-misurato**, `check_documentazione.py`, prompt nuovo,
**dire la coda a Mattia senza pushare**.

---

## 5. Come si parla a Mattia

Non legge codice: decide **cosa** si fa. Alle domande di stato — **una riga di
verdetto, max 3 punti, una domanda, «Vuoi il dettaglio?»**. Tetto ~10 righe,
niente tabelle né percorsi con numero di riga. Un tuo errore si corregge in
**mezza riga**, non in un paragrafo. A fine planning (`ExitPlanMode`): riepilogo
non tecnico **+ tabella fase / modello / sforzo**.
