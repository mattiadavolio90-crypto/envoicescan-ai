# Prompt per la sessione del punto 9 (F2-NOTEST)

> ⚠️ **ARCHIVIATO — il punto 9 e' stato chiuso il 29/8/2026** (opzione A: test
> in `tests/*.py` che eseguono il TypeScript vero con node). Questo prompt e'
> storia: non eseguirlo. L'esito sta in
> `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md`.

> **Apri questa sessione solo quando gli 8 punti sono chiusi.** Copia il blocco
> qui sotto come primo messaggio.

---

Devi affrontare il **punto 9** del ciclo audit 2026-08: **F2-NOTEST — non esiste
alcun test runner frontend**. È l'ultimo punto rimasto; gli altri 8 sono chiusi.

Leggi per primo `docs/storico/AUDIT_ONEFLUX_STATO_2026-08_PUNTO_9.md`: contiene la misura,
le tre opzioni con il costo vero, la raccomandazione e il criterio di
accettazione. **Rimisura le sue cifre** prima di usarle — sono del 29/8/2026, e
in questo progetto una cifra ereditata da un documento è stata sbagliata quattro
volte.

## Tre cose che non puoi dedurre da solo

1. **Questa non è una svista d'audit, è una decisione di progetto** che ho
   separato di proposito dagli altri 8 punti. Non trattarla come un difetto da
   fixare in fretta.

2. **Il progetto non è a zero test frontend.** Otto file Python leggono
   `apps/web/`, e due **eseguono davvero il TypeScript** via `node -e`
   (`test_password_policy_client_allineata.py`, `test_login_next_open_redirect.py`).
   Node è già dichiarato in CI. Quindi la domanda non è «test frontend sì o no»,
   è **«runner dedicato, o estendo il precedente che già funziona?»**

3. **Non partire dal runner, parti dai due difetti reali.** Il `poolSaturo` di
   F7 e le quattro liste di categorie di F1 erano **entrambi logica pura**:
   nessuno dei due richiedeva di renderizzare un componente. Se la tua proposta
   non avrebbe preso quei due, è la proposta sbagliata.

## Cosa mi aspetto

Una raccomandazione **con il costo di manutenzione dichiarato**, non un elenco di
framework. Il rischio vero qui non è scegliere male: è installare un runner,
scrivere quattro test dimostrativi e ritrovarsi fra sei mesi con una rete che
sembra esserci e non c'è. Dimmi anche cosa **non** copriremmo.

Poi, se decidiamo di procedere: i primi test veri su `apps/web/src/lib/`
(3.339 righe, dove sta il calcolo dei numeri del cliente), non test dimostrativi.

## Metodo, non derogabile

- **Ogni cifra si ri-misura al momento di scriverla.** Mai ereditata da un
  documento, da questo prompt, o da una misura fatta prima nella stessa sessione.
- **Ogni test nuovo va provato per mutazione**, su copia in scratchpad, mai sul
  file del branch. Nel ciclo la mutazione ha smascherato **tre** test che
  sembravano buoni.
- **Un mock va reso severo quanto la cosa vera.** I 6 test del radar anomalie
  passano da sempre su una query che interroga una colonna inesistente.
- Se aggiungiamo un runner: **la CI deve fallire se non trova test**, altrimenti
  è uno skip verde. Precedente: `16b1734`.
- `code-reviewer` a fine sessione, sempre.
- **Verifica che lo sha della PR sia quello che intendevi pubblicare**
  (`gh pr view <n> --json headRefOid` contro `git log -1`).
- Deploy fuori orario cliente, salvo mio via esplicito. Ma attenzione: un lavoro
  di soli test **non dovrebbe** toccare `apps/web/**` in modo da far partire il
  deploy Vercel — se lo fa, fermati e dimmelo.

## Chiusura

> **Aggiornato il 29/8/2026.** Gli altri 8 punti sono chiusi e deployati
> (`fb5785fd`), e il ciclo 2026-08 è già stato archiviato in `docs/storico/`.
> Questo è l'**unico punto ancora aperto**.

Verbale in `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-09.md` (il ciclo
corrente); gli storici dei cicli chiusi stanno in `docs/storico/` e non vanno
più modificati.
