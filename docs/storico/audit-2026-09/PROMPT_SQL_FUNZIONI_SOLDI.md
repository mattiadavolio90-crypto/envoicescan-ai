# Prompt sessione — Punto 1 dell'audit: le funzioni SQL che calcolano i soldi

> **Modello**: **Opus**. Non serve `ultrathink`: l'impianto è deciso e provato,
> questa è esecuzione. Serve invece per la voce 3, che è una decisione di dominio.
> **Sforzo**: medio. Tre voci, la seconda vale l'80% del valore.
> **Documento vivo**: `DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` (ignorato da
> git, sta su disco), sezione «Da dove riparte la prossima sessione».
> **Stato repo alla stesura**: `98f2ec9`, coda push **0**, suite **13.078 verdi**,
> 38 test SQL verdi (07/09/2026, ore 16:00).

---

## ⚠️ Prima di tutto: ri-misura, non ereditare

Ogni cifra qui è del **07/09/2026**. In questo progetto le premesse dei prompt
sono state smentite dalla misura in 5 casi su 10, e nella sessione che ha
scritto questo file **una migration scritta con cura non faceva quello che
diceva**: revocava permessi che non erano dove pensavo. È stata smascherata
eseguendola, non rileggendola.

La regola che ne esce, e che vale per tutta questa sessione: **provare
eseguendo**. Ora si può: c'è un Postgres vero nei test.

```bash
python -m pytest -q -m sql           # 38 test, devono essere verdi
git log --oneline origin/main..main  # atteso: vuoto
python scripts/check_documentazione.py
```

Se i 38 non sono verdi **non è un problema dei test**: o lo snapshot dello
schema è in drift rispetto al DB live, o una migration nuova non si applica
sopra. Il messaggio d'errore della fixture lo dice esplicitamente.

---

## Cosa c'è già, e come si usa

Nella sessione del 07/09 è stato costruito l'impianto per **eseguire** la logica
SQL nei test. Prima non esisteva: 78 funzioni e 26 trigger giravano in
produzione senza che un solo test ne eseguisse una riga.

| Pezzo | A cosa serve |
|---|---|
| `supabase/schema_snapshot.sql` | fotografia dello schema del DB live (3.934 righe). Le migration del repo **non** ricostruiscono il database: applicate a un Postgres vuoto danno 18 tabelle su 59 |
| `scripts/genera_schema_snapshot.py` | rigenera lo snapshot dai cataloghi. Richiede `SUPABASE_DB_URL`, che il progetto **non ha**: oggi si produce via MCP Supabase |
| `tests/conftest_sql.py` | avvia un Postgres locale effimero (`pgserver`), carica lo snapshot, applica sopra le migration più recenti. Fixture: `sql`, `scalare`, `db_sql` |
| `tests/test_sql_categorie_fb.py` | **il modello da imitare**: semina righe vere, chiama la funzione, asserisce sul risultato |
| `tests/test_sql_funzioni_permessi.py` | nessuna funzione raggiungibile dalla chiave pubblica |

**Il modo di scrivere un test SQL**, dal file esistente: `_semina_una_riga_per_categoria`
inserisce un utente, una sede e una riga di fattura; poi si chiama la funzione e
si guarda cosa torna. Ogni test gira in una transazione annullata, quindi
l'ordine non conta e non serve pulire.

> **Mai asserire sul testo del corpo** con `pg_get_functiondef`. Nella sessione
> del 07/09 due test lo facevano: il code-reviewer ha mostrato un mutante che
> cambiava il comportamento lasciando il testo intatto, e sopravviveva. Sono
> stati riscritti chiamando le funzioni.

---

## Le tre voci, in ordine

### 1. Le cinque funzioni morte — mezz'ora

Nessun chiamante nel codice (misurato il 07/09): `gruppo_prezzi_categoria` (22
righe), `swap_ricette_order` (42), `create_ristorante_for_user` (24),
`conta_ristoranti_utente` (17), `get_distinct_files(p_user_id text)` (11).

Una migration che le elimina chiude anche un difetto vero: `get_distinct_files`
esiste in **tre** varianti e PostgREST non sa quale scegliere quando la si
chiama col solo `p_user_id` — errore `PGRST203`. Oggi ci passa
`elimina_tutte_fatture` senza sede, che logga e prosegue con un conteggio
parziale.

⚠️ **Prima di cancellare, ri-misura i chiamanti.** Il codice cambia: una funzione
senza chiamanti a settembre può averne uno a ottobre. Cerca in `services/`,
`worker/`, `utils/`, `scripts/`, `tools/` **e** `supabase/functions/`.

### 2. I test sulle sei funzioni che muovono soldi o fatture — è la voce che vale

Sono le funzioni che calcolano i numeri che il cliente legge. Nessuna è coperta.

| Funzione | Righe | Cosa fa, e cosa può rompersi in silenzio |
|---|---:|---|
| `riparto_quote_mensili` | 80 | riscrive `mol`, `primo_margine`, `costi_fb_totali`, `fatturato_netto` in `margini_mensili`. Separa costi F&B da spese generali: se sbaglia, il MOL totale resta giusto e le componenti no |
| `sposta_fattura_a_sede` | 74 | sposta le righe di una fattura fra sedi, con una guardia sulle collisioni. Sbagliarla significa fatture nella sede sbagliata |
| `sync_margini_mensili_from_ricavi` | 60 | trigger su ogni scrittura di ricavo giornaliero: aggrega il mese e ricalcola il fatturato netto |
| `scadenziario_fatture_aggregate` | 49 | aggrega i documenti dello scadenziario. Nel 2026 un difetto qui ha reso invisibili 4,4 M€ di scadenze |
| `costi_automatici_mensili` | 26 | i costi che entrano nel MOL. Contiene le esclusioni della regola di dominio #1 e #2 (`Da Classificare`, `NOTE E DICITURE`) e l'anti-doppio-conteggio del riparto |
| `claim_batch_for_processing` | 30 | il worker prende in carico le fatture da elaborare, con `FOR UPDATE SKIP LOCKED`. Un difetto qui significa fatture elaborate due volte o mai |

Per ognuna: seminare righe, chiamare, asserire sul risultato, poi **provare per
mutazione** — un mutante per volta, backup dello snapshot preso **prima** del
primo, `git status` dopo l'ultimo ripristino. Se un mutante sopravvive, scrivere
**perché**: può essere codice ridondante, non per forza un test debole.

Suggerimento su cosa asserire, imparato il 07/09: **asserisci le componenti, non
l'aggregato**. Due errori opposti che si compensano lasciano la somma giusta.

### 3. Le due divergenze — sono una domanda per Mattia, non un fix

Non correggerle di iniziativa: sono decisioni di prodotto.

- **`data_competenza` vs `data_documento`**: dashboard, chat e spreco aggregano
  per data documento; margini e gruppo per competenza. Divergono su 229 righe,
  3.794 €, 1 sede. Ri-misurare: la cifra è del 07/09.
- **Il limite giornaliero della chat** (`chat_usage_check_and_log`) azzera a
  mezzanotte **UTC**, cioè alle 01:00 o 02:00 italiane.

---

## Vincoli da rispettare

- **Il buco di sicurezza del 07/09 è chiuso**, non riaprirlo. Ogni migration che
  crea o ricrea una funzione deve revocare **nominando i ruoli**:
  `REVOKE ALL ON FUNCTION ... FROM PUBLIC, anon, authenticated;` più il `GRANT`
  esplicito a `service_role`. Il solo `FROM PUBLIC` **non basta**: le default
  privileges del progetto danno grant nominali. Il presidio è
  `tests/test_sql_funzioni_permessi.py`, che diventa rosso da solo.
- **Se applichi una migration al DB live, riallinea lo snapshot nello stesso
  commit**, altrimenti il DB di test resta indietro e i test diventano verdi per
  omissione.
- **Mai `git add -A`**: nel working tree ci sono file di altre sessioni.
- **Push e deploy**: chiedi a Mattia. La finestra è sera/notte/mattina presto,
  salvo sua indicazione contraria.
- Regole di dominio #1 e #2 di `CLAUDE.md`: `costi_automatici_mensili` le tocca
  entrambe.

## Chiusura (WORKFLOW.md §5)

Presidio provato per mutazione, commit su `main` locale, contatore
`DOCUMENTAZIONE/AUDIT_ULTIMO_PERIMETRO.md` aggiornato, `check_documentazione.py`
pulito, `/code-reviewer` verde. Quando le tre voci sono chiuse, il Punto 1 è
chiuso e si passa al **Punto 2** (il registro delle correzioni che non sa chi ha
scritto), descritto nello stesso documento.
