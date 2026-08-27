# Prompt per la prossima sessione — resta solo §2

Contesto: leggi `DOCUMENTAZIONE/AUDIT_ONEFLUX_STATO_2026-07.md` (indice, 1
minuto) e `..._STORICO.md §32` (l'ultima sessione, 27/8/2026) prima di
iniziare.

**Il ciclo audit 2026-07 è aperto su UNA SOLA voce: §2.** Tutto il resto —
§1, §3b, §3c, i 4 punti §27, il MEDIUM delle note di credito — è chiuso.

## L'unica voce aperta

### §2 — Il mock globale di `tests/conftest.py`

**Non aprirla senza tempo dedicato e senza che Mattia l'abbia deciso per quella
sessione specifica.** È una decisione già presa due volte: è lavoro lungo, non
un residuo da smaltire in coda a qualcos'altro.

Il problema: `openai`, `requests`, `argon2`, `xmltodict`, `supabase`, `tenacity`
sono **tutti installati davvero** nel venv, ma `tests/conftest.py` li sostituisce
con `MagicMock()`. Conseguenza: i test sui rami `except` sono **vacui** — un
attributo di un MagicMock non eredita da `BaseException`, quindi
`except openai.RateLimitError` solleva `TypeError` invece di catturare.

Cosa aspettarsi rimuovendolo:
- rilanciare ~11.200 test e sistemare le ricadute;
- `tests/test_eccezioni_moduli_mockati.py` diventa **rosso**: è il segnale
  atteso, quel file documenta il problema e va cancellato col workaround;
- attenzione a `importlib.reload`: ricaricare `ai_service` ricrea le classi di
  eccezione, mentre `upload_handler.py` le cattura all'import — un `except` che
  non matcha più. Il tentativo del 25/8 è stato scartato per questo (STORICO
  §23), la soluzione finale recupera la funzione non decorata dal mock stesso.

## Metodo (non derogabile)

- Audit **read-only** prima di qualunque fix; remediation solo dopo conferma
  esplicita di Mattia.
- Ogni severità dell'agente **si riverifica** sul DB live (Supabase MCP) o
  eseguendo il codice. In questo ciclo è successo **cinque volte** che un numero
  ereditato non reggesse alla riverifica — l'ultima il 27/8: 236,23 € su 3 righe
  erano diventati 285,50 € su 7, perché il verbale era vecchio, non sbagliato.
- `code-reviewer` sul diff cumulativo **a fine sessione, sempre** — anche sui
  fix che sembrano piccoli.
- Ogni fix nuovo richiede test verificati **per mutazione, su copia in
  scratchpad**, mai sul file del branch di lavoro. E attenzione a *cosa* misura
  il test: il 27/8 un mutante è sopravvissuto perché il test contava le righe
  aggiornate invece delle query emesse — verde per il motivo sbagliato.
- Migration solo con conferma esplicita, applicata **prima** del deploy.
- CI parte solo su `pull_request` o push a `main`/`progetto` — un branch pushato
  da solo non attiva nulla. `gh` è autenticato in questo ambiente: push,
  `gh pr create` e `gh pr merge` sono utilizzabili direttamente.
- Deploy solo fuori orario clienti (sera/notte/mattina presto), salvo conferma
  esplicita e specifica di Mattia per un'eccezione — non basta un "sì" generico
  dato prima di sapere l'orario.
- Aggiorna indice e STORICO a fine sessione, in una sezione nuova numerata in
  sequenza (prossima: §33).

## Quando §2 sarà chiusa

Il ciclo si dichiara chiuso: aggiungere "**Ciclo chiuso il gg/mm/aaaa**" in cima
all'indice, spostare indice e STORICO in `docs/storico/`, e creare
`AUDIT_ONEFLUX_STATO_<AAAA-MM>.md` per il ciclo nuovo (non riusare questo file).

## Annotazioni utili lasciate dal 27/8

- `worker/email_queue_processor.py` scrive i ricavi giornalieri **fuori dal
  router**, quindi non spegne l'override mensile come fanno i 3 percorsi del
  router. Misurato: 0 righe `email`/`xls` sulle sedi con override, quindi oggi
  non è esposto. Se un cliente iniziasse a caricare i ricavi via email, va
  agganciato anche lì (`services/routers/ricavi.py::_spegni_override_mensile`).
- Il canale SDI **non** applica la policy date, ed è una decisione a verbale
  (STORICO §27 e §32) difesa da `tests/test_upload_policy_canale_sdi.py`.
- Il flush PROP-1 prima del blocco policy è **documenta-e-chiudi**, non
  dimenticato: nessun dato sbagliato, refactor sproporzionato al rischio.
