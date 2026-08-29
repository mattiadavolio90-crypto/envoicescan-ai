# Punto 9 — F2-NOTEST: nessun test runner frontend

> **Stato: decisione aperta, di proposito.** Non è una svista d'audit: introdurre
> un runner è una scelta di progetto, e Mattia l'ha esplicitamente separata dagli
> altri 8 punti del ciclo 2026-08. Questo file prepara quella decisione; non la
> prende.

**Misure di questo documento: 29/08/2026.** Rimisurale prima di usarle — è la
regola del ciclo, ed è stata violata quattro volte proprio sui documenti.

---

## Il fatto, misurato

```bash
cd apps/web
find src -name '*.ts' -o -name '*.tsx' | wc -l          # 399 file
find src -name '*.ts' -o -name '*.tsx' | xargs wc -l    # 50.891 righe
find . -path ./node_modules -prune -o -name '*.test.ts*' -print   # (vuoto)
python3 -c "import json;print(json.load(open('package.json'))['scripts'])"
# {'dev','build','start','lint'} — nessun runner
```

**399 file, 50.891 righe, zero test, zero runner.** L'unica rete su `apps/web/`
è `npx tsc --noEmit`, che controlla i tipi e **non esegue niente**.

Il frontend è il layer più scoperto del progetto: il conto onesto del ciclo dava
il **66% mai letto** contro il 27% del Python.

## Perché non è teorico — è già costato due volte

1. **29/8, F7.** Un fix passava `tsc`, sembrava giusto a leggerlo, e **non
   scattava su nessuno dei 3 casi reali**: `poolSaturo: pool.length >= 500`
   misurava la soglia *dopo* i filtri client invece che prima. L'ha trovato il
   `code-reviewer`, non i tipi.
2. **F1.** Quattro liste di categorie di spesa divergenti fra loro: uno specchio
   che nessuno controllava. Stessa classe di difetto.

Entrambi sono difetti che **cambiano i numeri mostrati al cliente** senza
rompere niente in modo visibile.

## Quello che già esiste, e che cambia la domanda

Il progetto **non è a zero**. Otto file di test Python leggono `apps/web/`, e due
di essi **eseguono davvero il codice TypeScript** con `node -e`, spogliato delle
annotazioni di tipo:

| Test | Cosa protegge |
|---|---|
| `tests/test_password_policy_client_allineata.py` (11 test) | esegue `lib/password-policy.ts` e confronta il verdetto con `valida_password_compliance` su un campione ampio |
| `tests/test_login_next_open_redirect.py` (44 test) | esegue `nextSicuro` del login contro le classi di bypass |
| `tests/test_regole_dominio_guardia.py` (229 test) | rende esecutive le regole di dominio di `CLAUDE.md` |
| altri 5 file | invarianti client vari |

E **node è dichiarato in CI** (`.github/workflows/tests.yml:32-35`,
`node-version: '22'`) proprio perché quei test non dipendessero da cosa porta
l'immagine.

> Quindi la domanda del punto 9 **non è** «introdurre test frontend sì o no»:
> alcuni ci sono già e girano in CI. È: **serve un runner dedicato, o si estende
> il precedente che già funziona?**

## Le tre opzioni, con il costo vero

### A — Estendere il precedente Python+node (nessuna dipendenza nuova)
Test in `tests/*.py` che eseguono funzioni TS pure via `node -e`.
- **Pro**: zero dipendenze nuove, gira nella CI esistente, il precedente è già
  verde da giorni, un solo comando (`pytest`) per tutto il progetto.
- **Contro**: funziona solo su **logica pura**. Niente componenti, niente hook,
  niente rendering. Spogliare i tipi a mano è fragile su file complessi.
- **Superficie coperta**: `apps/web/src/lib/` — **3.339 righe**, dove sta la
  logica che calcola numeri (`margini.ts`, `foodcost.ts`, `format.ts`,
  `categorie-spesa.ts`).

### B — Vitest (runner vero, solo unit)
- **Pro**: esegue TS nativamente, niente spogliatura, copre anche hook e
  componenti con `@testing-library/react`. È lo standard per Next.js 16.
- **Contro**: dipendenze nuove, un secondo comando in CI, e — il costo reale —
  **la manutenzione**: un runner senza test è peggio di nessun runner, perché
  dà l'impressione di una rete che non c'è.
- **Costo d'ingresso**: `vitest` + config; i primi test si scrivono in un'ora.

### C — Playwright (end-to-end)
- **Pro**: è l'unico che prova ciò che il cliente vede davvero.
- **Contro**: il più caro da mantenere, lento in CI, e **punta al DB cloud
  reale** (trappola nota di `CLAUDE.md`: «Next.js in locale punta al DB cloud
  reale»). Servirebbe un ambiente separato che oggi non esiste.

## Raccomandazione

**A per la logica pura, subito; B quando serve toccare un componente.**

Non è un compromesso pigro: è ciò che i due difetti reali suggeriscono. Sia il
`poolSaturo` sia le quattro liste di categorie erano **logica pura** — entrambi
sarebbero stati presi da un test di tipo A, nessuno dei due richiedeva di
renderizzare un componente. `lib/` è anche la superficie dove sta il calcolo dei
numeri del cliente, cioè dove un difetto silenzioso costa di più.

C non prima di avere un ambiente di staging con un DB non di produzione.

## Criterio di accettazione, qualunque opzione

- Ogni test nuovo va **provato per mutazione**, su copia in scratchpad, mai sul
  file del branch. Nel ciclo la mutazione ha smascherato **tre** test che
  sembravano buoni.
- Un mock va reso **severo quanto la cosa vera**. I 6 test del radar anomalie
  passano da sempre su una query che interroga una colonna inesistente, perché
  il mock rispondeva comunque.
- Se si sceglie B: la CI deve **fallire** se il runner non trova test, altrimenti
  è uno skip verde. Il precedente esiste già — `16b1734` ha dichiarato node in CI
  proprio perché la sua assenza non fosse uno skip verde.

## Fuori perimetro

Gli **8 punti** del ciclo 2026-08: vanno chiusi prima, in sessioni loro.
Questo file si apre **quando restano solo loro chiusi e il punto 9**.
