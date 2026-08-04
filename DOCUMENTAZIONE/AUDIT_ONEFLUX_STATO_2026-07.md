# Stato audit ONEFLUX — ciclo 2026-07

**Tutte e 10 le dimensioni sono 🟢, tutte con seconda passata e `code-reviewer`.**
Quello che resta non sono findings aperti: è **perimetro mai letto** (§1) e
**copertura test da scrivere** (§2). Sono due cose diverse e vanno tenute distinte.

> **Dov'è il dettaglio.** Questo file dice *cosa manca*, in un minuto.
> Il dettaglio verificato di ogni passata — perimetro, findings, numeri
> misurati, errori corretti in corsa, le 36 lezioni operative — sta in
> **`AUDIT_ONEFLUX_STATO_2026-07_STORICO.md`**, stessa cartella.
> Aprilo quando riapri una dimensione e vuoi sapere cosa è già stato guardato.

Legenda: 🟢 chiusa · 🟡 residui aperti · ⚪ mai fatta.

| # | Dimensione | Stato | Ultima passata | In una riga |
|---|---|---|---|---|
| 1 | Security | 🟢 | 29/7 | 3 passate + follow-up; 1 CRITICAL (scrittura cross-tenant) + 2 HIGH fixati e deployati |
| 2 | Edge Functions | 🟢 | 4/8 (2ª) | 13/13 file riletti; HIGH nuovo (race rete-sicurezza ↔ claim worker) fixato — PR #5 |
| 3 | Bug | 🟢 | 3/8 (2 passate) | ~16.800 righe (non 5.000 come dichiarato); 2 HIGH + bonifica `prodotti_master` sul DB live |
| 4 | AI | 🟢 | 4/8 (2ª) | HIGH guardrail NOTE + bug preesistente: l'UPDATE su `fatture` falliva **sempre**, in silenzio — PR #6 |
| 5 | Performance | 🟢 | 3/8 + 4/8 | Il cap PostgREST 1000 righe era un difetto di **correttezza** già attivo sui clienti, non di performance |
| 6 | Qualità/UI | 🟢 | 4/8 (2ª) | Rischio più basso confermato; 1 MEDIUM reale (select morto in Admin) fixato — PR #11 |
| 7 | Database | 🟢 | 30/7 (deploy 2/8) | Migration live ma codice Python mai committato per 3 giorni — da lì la lezione 1 |
| 8 | Architettura | 🟢 | 2/8 | 2 fasi, deployato; `code-reviewer` introdotto qui per la prima volta |
| 9 | Test | 🟢 | 3/8 | La suite **non difendeva il MOL**: rotta la regola, 10.195 test restavano verdi |
| 10 | DevOps/Config | 🟢 | 30/7 | `openapi-drift.yml` corretto ma con trigger che non includeva `services/routers/**` |

---

## §1 — Perimetro mai letto (priorità alta)

Codice che **nessun audit ha mai attraversato**. Non è "controllato e giudicato
a basso rischio": è rischio ignoto per definizione.

| File | Stato | Perché conta |
|---|---|---|
| `services/routers/gruppo.py` | letto in parte | In catena il cap PostgREST scatta **prima** sulle query `.in_()` multi-sede |
| `services/routers/riparto.py` | **mai letto** | Nominato nel perimetro di 2 passate diverse (Bug, Database), mai aperto in nessuna |
| `services/routers/fatture.py` | **mai letto** | Idem — e il giro B della passata Bug l'ha riindicato come collegato al riparto |
| `services/routers/ricavi.py` | **mai letto** | Mai nominato come letto in nessuna riga della tabella |
| `worker/email_queue_processor.py` | **mai letto** | Idem |
| `services/ai_service.py:3392,3453` e `:3579-3990` | **mai letto** | Ultimo sito plausibile della classe troncamenti; se troncata → più chiamate GPT a pagamento |
| `services/routers/admin.py` | letto ~15% | 3010 righe (ricontate il 4/8: il doc diceva 2959), coperte solo da Security passata 3 + Bug |

## §2 — Copertura test (lavoro di scrittura, non di audit)

Nessun audit può farlo in coda a sé stesso: va pianificato come sessione propria.

- **`services/upload_handler.py`** — 909 statement scoperti (parsing XML/P7M,
  dedup, orchestrazione AI a chunk). Il buco più grande del progetto in assoluto.
- **`worker/run.py`** — 0%, mai importato dalla suite.
- **`services/routers/riparto.py`** — 7 endpoint su 11 senza alcun test.
- **`verify_and_migrate_password`** (`services/auth_service.py`) — il ramo SHA256
  legacy + migrazione automatica (riscrive `password_hash` sul DB) resta scoperto.
- **Il mock globale di `tests/conftest.py` va ripensato** — `openai`, `requests`,
  `argon2`, `xmltodict`, `supabase`, `tenacity` sono **tutti installati davvero**:
  il conftest sta oscurando librerie funzionanti e rende vacui i test sui rami
  `except`. Toglierlo significa rilanciare 10.000 test e sistemare le ricadute.
  `tests/test_eccezioni_moduli_mockati.py` documenta il problema: **quando
  qualcuno lo rimuoverà quel file diventerà rosso, ed è il segnale atteso.**
- **`.coveragerc` non è un gate** — baseline 45% documentata e riproducibile, ma
  nessun workflow fallisce se scende.

## §3 — Aperti per scelta, con la loro ragione

Non dimenticanze: decisioni. Riaprirle solo con la ragione che le ha chiuse.

- **Cache per-processo vs `WORKER_WEB_CONCURRENCY=4`** — `clear_fatture_cache()`
  invalida il processo che ha servito la richiesta, non gli altri 3. Il TTL 15s
  accorcia la finestra, non la elimina. Risolverlo davvero = invalidazione
  condivisa o cache esterna, cioè **infrastruttura nuova**.
  ⚠️ Non abbassare ancora i TTL: è la scorciatoia che sembra un fix e non lo è.
- **`normalizza_descrizione` (`utils/text_utils.py`) copre 5 pattern su 7** — `CUORI FIL.MERL` vs
  `CUORI FIL MERL`, e l'asterisco di `BRODO...TTL *`, sopravvivono. I 5 conflitti
  esistenti sono stati bonificati il 3/8. Se ne ricompaiono di nuovi **per questi
  due pattern**, è il segnale di estendere la funzione invece di bonificare a mano.
- **L'agent notturno è spento** (`enabled=false` dal 30/5, mai eseguito). Il codice
  ora è corretto ma la feature non è mai stata collaudata: accenderla **è un
  collaudo**, non un'ovvietà. 669 righe `needs_review` da smaltire.
- **3 MEDIUM AI** (prompt anti-"Da Classificare", superficie di prompt injection
  via descrizione fattura, rate-limit fail-open) — lasciati aperti il 4/8 per
  istruzione esplicita ("fix solo l'HIGH").
- **3 MEDIUM/LOW Qualità/UI** — quota chat non mostrata su mobile
  (`mobile-chat.tsx`); `userScalable: false` in `apps/web/src/app/layout.tsx`
  (WCAG 1.4.4, tocca il root layout); 5 LOW di accessibilità sparsi su 20+ file.

## §4 — Buchi di sorveglianza (trovati fuori dimensione)

- **Nessun test di regressione su `X-Reprocess-Key`** — il canale (CRITICAL Edge
  Functions del 30/7) è stato rimosso, ma **nulla impedisce di reintrodurlo**.
- **2 monitor CI che falliscono verdi** — `riparto_coerenza_check.yml` e
  `invoicetronic_eventi_sconosciuti_check.yml` fanno `exit 0` anche su HTTP ≠ 200:
  annotazione rossa nei log, job verde. L'unico segnale reale è l'alert Telegram.
- **`services/routers/fatture.py:850`** passa ancora `volte_visto: 1` — `insert()`
  puro, innocuo oggi, **dannoso se convertito in `upsert`**.
- **Cleanup righe orfane** su re-upload di fatture >2000 righe
  (`services/invoice_service.py:1938-1958`): la lista `numero_riga` è quella già
  troncata. Caso raro, richiede una versione precedente pre-cap.
- ~~**`_CATEGORIE_SPESE_M`** è dead code~~ — **falso, corretto il 4/8/2026**: ha un
  consumatore vivo in `services/routers/margini.py:76` (più un test che lo asserisce).
  Era scritto come "dead code verificato" e non lo era: se qualcuno l'avesse rimosso
  fidandosi, avrebbe rotto i margini.

---

## Come si lavora a questo documento

1. **Una sessione per volta.** Due sessioni che scrivono in parallelo si
   sovrascrivono senza avviso.
2. **Chi chiude una voce la barra e lascia la data** — mai cancellarla in
   silenzio: `~~voce~~ — CHIUSA il gg/mm`.
3. **Il dettaglio va nello STORICO, non qui.** Questo file deve restare
   leggibile in un minuto: è la sua unica funzione.
4. **"Deployato" scritto qui non è una prova**: verifica con
   `git log -- <file>` e con `/health` (il worker espone il commit).
   Il caso Database del 30/7 nasce esattamente da qui.
5. **Questo file è tracciato da git** grazie all'eccezione
   `!AUDIT_ONEFLUX_STATO*.md` in `.gitignore` (che copre anche lo STORICO,
   il cui nome è costruito apposta per matcharla). Committalo col lavoro
   che documenta.

**Modello**: audit read-only con `oneflux-audit` (Sonnet regge); remediation
con Opus e **solo dopo conferma esplicita di Mattia**; `code-reviewer` sul diff
cumulativo a fine sessione, sempre — anche sui fix piccoli, che è dove è
saltato in passato.

## Chiusura del ciclo

Il ciclo si dichiara chiuso quando §1 e §2 sono vuote — non quando la tabella
è tutta 🟢 (lo è già dal 4/8). Allora:

1. Aggiungere in cima "**Ciclo chiuso il gg/mm/aaaa**"
2. Spostare questo file **e il suo STORICO** in `docs/storico/`
3. Per un nuovo ciclo, creare `AUDIT_ONEFLUX_STATO_2026-10.md` (data corrente
   nel nome) — non riusare questo file
