# Prompt per la prossima sessione — chiusura degli 8 punti aperti

> Copia il blocco qui sotto come primo messaggio della nuova sessione.

---

Devi chiudere gli **8 punti aperti** lasciati dal ciclo audit 2026-08, che è
**chiuso** (7 fasi su 7). Il piano completo è già scritto e approvato:
`/home/vscode/.claude/plans/leggi-prompt-prossima-sessione-md-drifting-eclipse.md`
— **leggilo per primo**, contiene il perché di ogni punto e i riferimenti
`file:riga` misurati.

L'elenco degli 8 punti sta in cima a `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08.md`.
Il 9° (F2-NOTEST, introdurre un test runner frontend) è **fuori perimetro per mia
decisione esplicita**: sessione separata, non ri-segnalarlo come svista.

## Cosa è già fatto (non rifarlo)

- **PR #48 mergiata e deployata** — `7d2b581`. Deploy Vercel success, sito
  verificato (307), entrambi i fix presenti nel commit deployato.
- **`CLAUDE.md` rimisurato** — branch `docs/claude-md-cifre-rimisurate`, commit
  `2d895b3`, **pushato ma senza PR aperta**. Apri la PR e mergiala: dichiarava
  ancora «go-live 1 luglio» a due mesi dalla data, «~9500 test» invece di
  **11.424**, «2 clienti in test + 1 operativo» invece di **7 account attivi /
  11 PV**. Quest'ultimo cambia la valutazione del rischio: 4 clienti su 7 hanno
  migliaia di righe fattura e accesso nell'ultima settimana.

## Il punto 1 non è quello che dice la roadmap — leggi prima di agire

La roadmap dice «il radar anomalie non gira da giugno, ricollegarlo». **Misurato
in planning: la diagnosi era incompleta.**

`services/anomaly_radar_service.py:42` filtra `.eq('upload_id', upload_id)` su
`fatture_documenti`, ma **quella colonna non esiste** — verificato su
`information_schema` del DB live (27 colonne, nessuna è `upload_id`), zero
occorrenze in `migrations/` e `supabase/`, e `upsert_documento` non l'ha mai
scritta. Quindi la query non poteva restituire nulla **nemmeno quando Streamlit
era vivo**: il radar non è spento da giugno, è **nato rotto**.

I suoi 6 test passano perché mockano tutti il client: non hanno mai toccato la
colonna reale.

E il perimetro è più largo del radar: è morto **l'intero blocco di notifiche
`source_type='upload'`** (`services/upload_handler.py:2055-2090` — `td24_noddt`,
`td24_partial`, `quality_check_failed`). Il frontend le aspetta ancora
(`apps/web/src/app/(app)/notifiche/notifiche-shared.ts:14`).

**La mia decisione resta ricollegarlo**, ma va prima riparato: serve un
correlatore al posto di `upload_id` (`file_origine` è l'unica chiave persistita)
e i test vanno riscritti. Il piano ha le tre decisioni di design e il punto di
aggancio candidato (`services/invoice_service.py:1790`, unico collo di bottiglia
dei due canali vivi).

## Ordine

**Per superficie di deploy**, così ogni deploy è verificabile da solo:

1. **Merge della PR di `CLAUDE.md`** (solo doc).
2. **Gruppo Railway** — punti 1, 2, 3, 4, 5, **più 6 e 8** che sono formalmente
   Python (una RPC e un commento nel worker). Attenzione: l'auto-deploy Railway è
   configurato sul dashboard e **non ha filtro di path** — ogni merge su `main`
   lo redeploya, anche un diff di soli documenti.
3. **Gruppo Vercel** — il solo punto 7 (`ripartisci-dialog`, percentuali
   negative; fallisce già in sicurezza con 400 dal server).

Su ogni punto: **chiedimi la decisione** dove il piano ne prevede una (es. punto
3, allineare il prompt AI o documentare la divergenza; punto 4, obbligare la
categoria via API o accettare il disallineamento). Non scegliere al posto mio su
cose che cambiano il comportamento verso il cliente.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla.** Mai ereditata da roadmap,
  piano, o da una misura fatta prima nella stessa sessione. Nel ciclo appena
  chiuso il `code-reviewer` ha trovato un errore in **ogni** fase, quasi sempre
  di questo tipo.
- **Una condizione su una soglia va provata per mutazione sui valori reali**, su
  copia in scratchpad, mai sul file del branch. Un fix che passa `tsc` può non
  fare nulla: è successo il 29/8.
- **Leggere un `if` non dice quale suo lato è caldo.** Misura quale ramo
  percorrono i dati veri prima di dichiarare una cosa protetta.
- **`code-reviewer` a fine di ogni gruppo, sempre**, anche se il diff è di soli
  documenti.
- **Verifica sempre che lo sha della PR sia quello che intendevi pubblicare**
  (`gh pr view <n> --json headRefOid` contro `git log -1`): il 29/8 sono finito
  in detached HEAD e la CI ha certificato verde una versione senza i fix.
- Migration solo con mia conferma esplicita, applicata **prima** del deploy.
- Deploy fuori orario cliente, salvo mio via esplicito.

## Chiusura

Verbale di ogni punto in `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-08_STORICO.md`,
elenco in cima alla roadmap aggiornato man mano. Quando resta solo F2-NOTEST:
spostare i due doc in `docs/storico/` e aprire
`AUDIT_ONEFLUX_STATO_<nuova data>.md` — rinviato di proposito, perché archiviare
prima avrebbe reso invisibili queste 8 decisioni.
