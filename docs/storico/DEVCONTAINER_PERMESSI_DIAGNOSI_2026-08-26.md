# Diagnosi: devcontainer `.claude/` root-owned — login loop infinito — 26/08/2026

> ✅ **CHIUSO, risolto e verificato in sessione.** Il fix è dichiarativo
> (`postStartCommand` in `.devcontainer/devcontainer.json`) e testato nei
> casi limite, ma la conferma definitiva arriva solo da un vero
> **Rebuild Container** — finché non è stato fatto, considera il fix
> "verificato ma non ancora certificato su rebuild reale".

## Sintomo osservato

Il login OAuth (`claude` CLI → `/login`, ed equivalente nell'estensione
VSCode) sembrava riuscire a schermo, ma subito dopo l'ambiente tornava
sempre a "Not logged in" — un loop di login infinito. In sessione è stato
visto esplicitamente l'errore:

```
Transcript writes are failing (permission denied — EACCES)
```

## Causa radice

Il devcontainer monta un volume Docker nominato e persistente su
`/home/vscode/.claude` (dichiarato in `.devcontainer/devcontainer.json`,
chiave `mounts`):

```json
"mounts": [
  "source=oneflux-claude-config,target=/home/vscode/.claude,type=volume"
]
```

Un volume Docker nominato creato per la prima volta viene inizializzato da
Docker con owner **`root:root`** di default. L'utente con cui gira tutto nel
container è `vscode` (uid 1000), che quindi non aveva permessi di scrittura
sulla cartella. Il login "riusciva" solo nel senso che il flusso OAuth a
schermo si completava, ma il processo non poteva scrivere il token/le
sessioni per `EACCES` — quindi ad ogni riavvio l'app risultava di nuovo
sloggata.

## Verifica cronologia — nessun dato perso, solo mai scritto

Prima di applicare il fix, sono stati ispezionati `projects/`,
`history.jsonl`, `sessions/`, `backups/` sotto `/home/vscode/.claude`: tutti
i timestamp partivano dal giorno stesso del fix (24/08/2026, 10:56-10:59).
Questo conferma che il problema non ha **cancellato** nulla — semplicemente,
essendo la cartella non scrivibile da `vscode`, Claude Code non è mai
riuscito a scrivere lì prima d'ora. Non c'è quindi cronologia "persa" da
recuperare: è cronologia mai esistita.

## Fix applicato

Aggiunto un `postStartCommand` dichiarativo in
`.devcontainer/devcontainer.json`:

```json
"postStartCommand": "sudo mkdir -p /home/vscode/.claude && sudo chown -R vscode:vscode /home/vscode/.claude",
```

Due scelte deliberate:

- **`postStartCommand` e non `postCreateCommand`**: `postCreateCommand` gira
  solo alla *creazione* del container, mentre `postStartCommand` gira ad
  **ogni avvio** — incluso ogni rebuild e ogni semplice restart. Così, anche
  se in futuro Docker ricrea il volume `oneflux-claude-config` (che di
  default nasce `root:root`), il chown si riapplica sempre prima che sia
  possibile fare login.
- **`mkdir -p` di guardia prima del `chown`**: testato che `chown -R` su un
  path inesistente fallisce con exit code 1 (`chown: cannot access '...':
  No such file or directory`). Anche se in pratica il mount point esiste
  quasi sempre come directory vuota al primo avvio del volume, non era
  garantito da nessuna parte nel codice — il `mkdir -p` rende il comando
  resiliente in ogni caso, testato end-to-end su directory inesistente
  (exit 0).

Verificato inoltre, prima del rebuild:
- JSON del devcontainer sintatticamente valido (è JSONC — commenti `//`
  ammessi, formato standard supportato da VSCode/devcontainer CLI).
- Un solo blocco `mounts`, una sola entry, nessun doppione/conflitto.

## Conseguenza — CLI da rilinkare a cascata

La rottura dei permessi non ha danneggiato solo il login di Claude Code: ha
lasciato in uno stato incerto anche gli altri strumenti con cui Claude Code
opera nel container, perché il momento della rottura ha coinciso con un
riavvio/ricostruzione dell'ambiente. Stato verificato per ciascuno:

| Strumento | Stato a inizio sessione | Azione | Stato finale |
|---|---|---|---|
| Hook `.claude/settings.json` | Path relativi negli hook, causa di blocchi intermittenti su Bash | Fix path assoluti (`$CLAUDE_PROJECT_DIR`) applicato in questa sessione, **non ancora committato** — vive solo nel worktree | Nessun blocco su Bash durante tutta la sessione, ma il fix va committato per sopravvivere a un rebuild/checkout |
| GitHub CLI (`gh`) | Già autenticato da sessione precedente | Nessuna azione | OK, nessuna azione necessaria |
| Vercel CLI | Già linkato (`apps/web/.vercel/project.json`, progetto `oneflux-web`, `projectId prj_58N27B3gFDgvpUObP1KU1dHMB10O` — file locale, gitignored, non presente su un clone pulito) | Nessuna azione | OK, nessuna azione necessaria |
| Railway CLI | **Non linkato** (`railway status` → "No linked project found") | `railway link` (comando interattivo, eseguito dall'utente) sul progetto `ingenious-fascination`; rilinkato due volte (prima `worker`, poi `queue-worker`) per puntare al servizio giusto | Progetto `ingenious-fascination` (ID `ce933bf7-43cd-401f-9df6-0c8689758fe2`), environment `production`, servizio linkato `queue-worker` (Online). Entrambi i servizi confermati sani: `worker` (Online, `https://worker-production-a552.up.railway.app`) e `queue-worker` (Online) |

**Nota operativa**: per tornare a operare su `worker` con la CLI Railway
invece che su `queue-worker`, basta `railway link` di nuovo oppure
`railway service`.

## Checklist — se ricapita

Da seguire in ordine al prossimo episodio simile (update VSCode, rebuild
fallito, nuovo devcontainer, nuovo volume):

1. **Sintomo**: login che non persiste (loop, "Not logged in" ripetuto) →
   controllare **subito** l'owner di `/home/vscode/.claude` con
   `ls -la /home/vscode/.claude` — non assumere sia un problema di
   credenziali/token scaduto.
2. **Se root-owned**: il `postStartCommand` in `.devcontainer/devcontainer.json`
   dovrebbe averlo già risolto automaticamente al riavvio successivo. Se il
   problema persiste anche dopo un riavvio, verificare che
   `postStartCommand` sia ancora presente nel file (potrebbe essere stato
   rimosso o sovrascritto da una modifica successiva al devcontainer).
3. **Dopo che `.claude/` è a posto**, ricontrollare in ordine anche le altre
   CLI, perché la stessa causa (riavvio/ricostruzione ambiente) tende a
   scollegarle insieme:
   - hook `.claude/settings.json` (path assoluti, non relativi)
   - `gh auth status`
   - `vercel whoami` / presenza `apps/web/.vercel/project.json`
   - `railway status`
   Rilinkare solo ciò che risulta effettivamente scollegato — non toccare
   ciò che è già a posto.
4. **Railway in particolare**: il link è un comando **interattivo**
   (`railway link`) e va eseguito dall'utente, non è automatizzabile da
   Claude Code.

## Stato finale

Permessi `.claude/` sistemati e resi permanenti via `postStartCommand`
(da confermare su un vero Rebuild Container). Tutte e 4 le CLI operative:
Railway, Vercel, GitHub linkati e funzionanti; hook sistemati; Supabase
disponibile via MCP in lettura per query/log/advisors.
