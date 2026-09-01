# Prompt prossima sessione — cosa resta di `(app)/dashboard/`, e due lezioni

> Scritto l'1/9/2026 a fine serata. La sessione ha fatto la 1ª passata su
> `dashboard/` (92 test dove non ce n'era nessuno) e **due fix che il cliente
> vede**, decisi da Mattia in fase di piano.
>
> **Le cifre qui dentro sono misurate a quel HEAD. Ri-misurale, non ereditarle.**
> È la regola che questo progetto ha violato **sei** volte in tre giorni — e la
> settima l'ho evitata per un soffio stasera: avevo scritto `lib/` = 5.195 righe
> e notifiche = 219 stimando invece di contare. Sono 5.186 e 242. Il documento
> chiede la somma quadrata: `wc -l`, non l'aritmetica a mente.

---

## 0. Prima di qualunque cosa — controlli di sessione

```bash
git status --short
git log --oneline origin/main..main     # quanti commit sono in coda?
```

**Se la coda non è vuota, dillo a Mattia subito**, col numero che leggi tu
adesso. A fine 1/9 erano **5**, di cui **4 miei** (l'altro è della sessione
categorizzazione). Il push manda tutti i commit accumulati — e **il push È il
deploy**. La finestra è sera/notte e la decide Mattia.

### ⚠️ Due fix in coda cambiano quello che il cliente vede

Non sono refactor: se Mattia pusha, **cambiano schermate**.

1. **`f3490e4`** — la linea del margine di **OFFSIDE SPORTS PUB** passa da
   rossa a verde. Era rossa mentre il MOL risaliva da −21.305,32 a −684,23.
2. **`d9e2003`** — le mini-linee di margini/prezzi/analisi-fatture/demo non
   spariscono più su un valore non finito.

Vanno **guardate a schermo** dopo il deploy (`npm run dev`, dashboard di
OFFSIDE). ⚠️ Il locale punta al **DB cloud reale**: si guarda, non si tocca.

### La suite è VERDE — e la storia dei 7 rossi vale la pena leggerla

`12.447 passed, 44 skipped`, misurati a fine serata sia nel repo che in copia
pulita. Ma a metà sessione erano **7 rossi** (`test_gate_fiducia`,
`test_radar_aggancio_percorso_vivo`, `test_nucleo_decisione_deterministica`).

Non erano miei, e la prova non è stata "passano isolati" — quella è debole, il
prompt precedente avvertiva proprio di non fermarsi lì. È stata: **worktree su
un commit precedente + suite intera**. Lì erano verdi; sul mio HEAD in copia
pulita anche. Venivano dai file **non committati** della sessione
categorizzazione, che nel frattempo ha committato.

> **Un rosso si attribuisce con un worktree, non con un'intuizione.** Costa 2
> minuti: `git worktree add /tmp/vr <commit>`, copiaci `.env`, lancia la suite.

---

## 1. Cosa è stato fatto, e cosa NON riaprire

`MolAndamento` in `kpi-block.tsx` era la **copia integrale** di
`calcolaSparkline`: eliminata, non ri-estratta. Stessa sorte per `euro()`
(→ `lib/format.ts`), `MESI_ABBR`, `offsetAnello` in `salute-card.tsx`.

Cinque moduli in `lib/`, **92 test** = home-kpi 18 + home-config 13 +
home-chat 22 + notifiche-shared 20 + sparkline-punti 19.
Mutazione: **39 mutanti, 38 uccisi**, 1 equivalente.

**Se torni sulla dashboard, il lavoro è il rendering, non la logica.**

---

## 2. La prossima dimensione: cosa resta scoperto

L'harness esegue **solo moduli senza React**: rendering, hook, stato ed effetti
restano fuori per costruzione. Nella dashboard restano dentro i `.tsx`:

| Dove | Cosa | Perché non è uscito |
|---|---|---|
| `chat-widget.tsx` | rotazione messaggi d'attesa, scroll, `Set` dei dismissed | stato React |
| `home-briefing.tsx` | `useTypewriter` | effetto + timer |
| `block-retry.tsx` | backoff `[1500…15000]` | è una macchina a stati con `useRef` |
| `home-auto-refresh.tsx` | throttle su `visibilitychange` | idem |

Le due aree grandi ancora a **zero logica estratta**: `impostazioni/` (806) e
`agenda/` (693). `MolAndamento` era l'aggancio pronto della dashboard; lì
l'aggancio va **cercato con un grep, non a memoria** — e poi vanno **aperti i
file**, perché «il file importa da `lib/`» non è «la logica del file è in
`lib/`» (§2 del prompt precedente, la lezione che è costata una passata intera).

---

## 3. Due trappole dell'harness scoperte stasera — costano ore se non le sai

**1. Un import di SOLO TIPO basta a rendere un modulo non eseguibile.**
`home-kpi.ts` importava `type HomeKpi` da `lib/home.ts`, che importa `./worker`
con path relativo: l'harness riscrive solo l'alias `@/`, e node muore con
`ERR_MODULE_NOT_FOUND` — un errore che sembra "il modulo è rotto" e invece è la
catena di import. **Un modulo di logica pura non deve importare da un modulo
che fa fetch**, nemmeno un tipo. Se serve una forma, la si dichiara strutturale.

Corollario: spostare un file in `lib/` **non basta** a renderlo testabile.
`notifiche-shared.ts` importava il tipo da `lib/notifiche.ts` → `./worker-config`.
La dipendenza è stata **invertita** (il tipo vive nel modulo puro, quello con le
fetch lo ri-esporta) e nessun call-site è cambiato.

**2. NaN e Infinity non attraversano il confine Python→node.**
`json.dumps(float("nan"))` scrive `NaN`, che **non è JSON valido**: `JSON.parse`
dentro l'harness muore con `SyntaxError` prima di eseguire il modulo. I valori
non finiti vanno **costruiti in JavaScript** — vedi `_punti_js` in
`tests/test_sparkline_punti_frontend.py`.

---

## 4. Regole di lavoro che non cambiano

**Il gate del diff non basta.** `git diff | grep '^+'` prova che la logica è
*uscita* dal `.tsx`, non che sia *arrivata intatta*. La prova è l'oracolo:
l'originale da `git show HEAD:<file>`, ricostruito come `.mjs` in scratchpad,
confrontato col modulo nuovo su input avversari. Stasera: 21 casi sulla
sparkline MOL e 60 confronti sulle 4 polyline, 0 divergenze. Fra gli input
avversari ci sono i **valori veri presi dal DB**, non solo numeri inventati.

**Un oracolo va validato sui due lati**, sempre: un mutante palese deve morire,
un commento cambiato deve sopravvivere. Stasera la validazione ha **fatto il suo
lavoro**: il primo mutante che avevo scelto (`delta > 0` → `>= 0`) è
sopravvissuto perché era *equivalente*, non perché i test fossero deboli. Se
non l'avessi validato avrei concluso il contrario.

**Un mutante sopravvissuto si spiega, non si archivia.** Due dei tre di stasera
erano lacune vere nei test (regex greedy del grassetto; `Math.max(...vals, 1)`
su serie sotto l'unità) e sono state chiuse. Solo uno era equivalente.

**`tsc` prende alcuni errori e non altri.** Stasera ne ha preso uno vero
(`toggleTopic` non generico scartava campi) e **mancato** un altro:
`alertPrezziAttivo` diventata funzione usata in un `&&`, quindi sempre truthy —
trovato rileggendo il file, non dai tipi.

⚠️ **Un'altra sessione può cancellare il tuo commit.** Stasera la sessione
categorizzazione ha fatto `reset --hard HEAD~1` per correggere il proprio
commit e ha portato via `f5fe072`, che nel frattempo ci stava sopra. Il lavoro
era salvo solo nel working tree. **Controlla `git log` dopo ogni pausa lunga**;
se un commit sparisce sta nel reflog (`git reflog show main`) e si recupera con
`git cherry-pick`.

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
**mezza riga**, non in un paragrafo.
