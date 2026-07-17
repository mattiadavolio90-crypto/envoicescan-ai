# Invoicetronic — Diagnosi ricevimento fatture ferma (2/7/2026)

> ✅ **SUPERATO DAI FATTI.** Verificato in DB il 17/7/2026: `fatture_queue` per
> OFFSIDE (P.IVA 07863990961) riceve regolarmente (26 righe, ultima il
> 15/7/2026) — il blocco strutturale qui diagnosticato (Codice Destinatario non
> registrato / conflitto con Sistemi in Rete) non è più presente. Causa radice
> definitiva del blocco successivo: vedi `DIAGNOSI_OFFSIDE_INVOICETRONIC_2026-07-14.md`
> e `RIEPILOGO_OFFSIDE_STATO_15-07.md` (stato corrente). Questo documento resta
> come traccia del ragionamento sulla precedenza del Codice Destinatario nel
> cassetto fiscale — utile se un altro cliente con provider fatturazione
> multiplo avrà lo stesso sintomo.

## Problema iniziale
La coda `fatture_queue` risultava a zero da mesi: il ricevimento automatico fatture via SDI → Invoicetronic → webhook → ONEFLUX sembrava fermo.

## Cause trovate (in ordine di scoperta)

### 1. Profilo Desk su chiave Test invece che Live — RISOLTO
Il profilo Desk di Mattia aveva la API key **Test** (`ik_test_...`) al posto della **Live** (`ik_live_...`). Su Invoicetronic l'ambiente (Test/Sandbox vs Live) è determinato solo dal prefisso della chiave usata, non da un flag separato. Con la chiave Test, tutto quello che si vedeva/configurava nel Desk (fatture, webhook) era isolato in sandbox, scollegato dal flusso reale.

**Fix applicato:**
- Aggiornato il secret `INVOICETRONIC_API_KEY` su Supabase Edge Functions Secrets con la chiave Live. Non serve redeploy (i secret sono letti a runtime dalla Edge Function).
- Non è stata pagata/attivata la postazione Desk Live (5€/mese+IVA): non serve, il Desk è solo un'interfaccia di visualizzazione manuale, il flusso automatico webhook → worker passa dall'API diretta, non dal Desk. Il banner rosso "questa API key live è valida ma non ha una postazione Desk attiva" nel profilo Desk è quindi atteso e va ignorato.

### 2. Webhook in ambiente Live limitato a una sola azienda — RISOLTO
Nella Dashboard (ambiente Live, non Desk) esisteva già un webhook configurato correttamente (URL, evento `receive.add`, Signing Secret), ma con il campo **Azienda** valorizzato su "MATTIA D'AVOLIO" — quindi attivo solo per quell'azienda, non per le aziende clienti reali (OFFSIDE, SUSHILAND x3, LAND DEI SAPORI), già censite in ambiente Live nella sezione Aziende della Dashboard (create l'11/06/2026).

**Fix applicato:** rimosso il valore dal campo Azienda del webhook e salvato. Campo vuoto = webhook attivo per tutte le aziende dell'account, come da documentazione ufficiale Invoicetronic.

**Verifica post-fix:** controllati i log edge-function di Supabase (progetto `vthikmfpywilukizputn`) — ancora zero chiamate su `invoicetronic-webhook`. Atteso: il webhook non fa replay retroattivo, scatta solo su eventi nuovi da questo momento in poi.

### 3. Codice Destinatario non registrato sul cassetto fiscale di OFFSIDE — CAUSA RADICE ATTUALE, NON RISOLTA
OFFSIDE ha comunicato verbalmente ai propri fornitori di inviare le fatture al Codice Destinatario Invoicetronic `7HD37X0`, ma **non ha registrato questo codice sul proprio cassetto fiscale** (Fatture e Corrispettivi → Registrazione dell'indirizzo telematico). Il cassetto fiscale di OFFSIDE ha invece registrato il Codice Destinatario di **Sistemi in Rete** (altro provider, usato per pagamento fornitori).

**Regola SDI verificata:** il Codice Destinatario registrato sul cassetto fiscale del destinatario ha sempre precedenza sul Codice Destinatario scritto dal fornitore nell'XML fattura. Quindi, anche per i fornitori che hanno correttamente scritto `7HD37X0` in fattura, SDI recapita comunque a Sistemi in Rete, perché è quello registrato sul cassetto.

Conferma empirica: fatture arrivate tra 1/7 e 2/7 risultano ricevute su Sistemi in Rete, non su Invoicetronic.

**Vincolo esplicito di Mattia:** OFFSIDE non può disattivare/sostituire Sistemi in Rete sul cassetto fiscale (dipendenze su pagamenti/conservazione). Registrare `7HD37X0` al posto del codice di Sistemi in Rete è quindi escluso come soluzione, anche se tecnicamente risolverebbe il problema.

## Prossimi passi

1. **Verificare se Sistemi in Rete offre un reinoltro/duplicazione** delle fatture ricevute (es. "inoltra a altro Codice Destinatario", export automatico via email/API, "Codice Destinatario secondario"). Molti gestionali fatture lo supportano per casi come commercialista + software gestionale che devono ricevere entrambi. — **Azione:** OFFSIDE controlla il pannello di Sistemi in Rete.
2. **Se Sistemi in Rete non ha questa funzione:** fallback manuale — OFFSIDE scarica periodicamente gli XML da Sistemi in Rete e li carica su ONEFLUX via upload manuale (già supportato), senza toccare la configurazione esistente.
3. **Da tenere a mente per altri clienti** (SUSHILAND, LAND DEI SAPORI): verificare se hanno lo stesso problema strutturale — Codice Destinatario `7HD37X0` comunicato ai fornitori ma non registrato sul cassetto fiscale, con un altro provider ancora attivo come destinatario primario.

## Nota secondaria non urgente
`INVOICETRONIC_API_KEY` non è mai stata impostata su Railway (worker/queue-worker). È un fallback opzionale nel codice (default stringa vuota, non blocca l'avvio) usato solo per il fallback `xml_url`. Da sistemare se questo fallback viene effettivamente usato in produzione — non prioritario ora.
