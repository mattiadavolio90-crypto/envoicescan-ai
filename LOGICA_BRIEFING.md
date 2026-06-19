# LOGICA BRIEFING

Come ragiona il briefing della Home (singolo punto vendita e catena): cosa decide
di dirti, in che ordine, e con quale tono. Scritto per capire la **logica**, non il
codice: quando vuoi cambiare qualcosa, mi indichi il punto qui sotto e io traduco
nel codice.

---

## 1. L'idea di fondo: prima i numeri, poi il tono

Il briefing **non** è un testo inventato dall'AI. Funziona come una catena di
montaggio:

> dati veri → problemi/notizie con numeri esatti → si tengono solo quelli utili →
> si mettono in ordine di importanza → si scelgono i più importanti (max 5) →
> l'AI riscrive **solo il tono** → frase finale

L'AI interviene **all'ultimo passo** e ha il divieto assoluto di toccare numeri,
date, nomi o di aggiungere/togliere argomenti. Se l'AI non risponde, c'è sempre un
testo scritto a mano come rete di sicurezza.

Conseguenza pratica:
- vuoi cambiare **COSA dice** (quali avvisi, quando, in che ordine) → si tocca una
  **regola** (una soglia, una priorità);
- vuoi cambiare **COME lo dice** (tono, lunghezza) → si tocca il **prompt dell'AI**.

---

## 2. Quando si ricalcola (e perché a volte vedi cose vecchie)

Il briefing è un **dato giornaliero**: si calcola una volta al giorno e poi si
riusa tutto il giorno. Tre casi:

- **Già calcolato oggi** → te lo mostra subito, senza rifare i conti (~0,5s).
- **Non ancora calcolato oggi** (prima apertura della giornata, o subito dopo che
  hai inserito dati) → ne costruisce uno **fresco e coerente all'istante**, saltando
  solo l'analisi prezzi (l'unica parte lenta). In sottofondo prepara la versione
  completa per l'apertura successiva.
- **Nessun ristorante collegato** → briefing vuoto.

**Si ricalcola da solo** quando cambiano i dati che racconta: carico fatture,
inserimento fatturato/personale/costi, inserimento ricavi/incassi.

⚠️ **Un aggiornamento del programma (deploy) NON ricalcola il briefing già salvato.**
Per questo, dopo che cambio la logica, devo svuotare la cache a mano: altrimenti
continui a vedere il testo vecchio anche se il codice è nuovo.

---

## 3. Da dove nascono gli avvisi

Due famiglie di segnali, fuse insieme:

### a) Notifiche già salvate
- un upload automatico di fattura è fallito;
- scadenze fornitori (superate o in arrivo);
- appuntamenti di oggi.

### b) Segnali "dal vivo" (ricalcolati ogni volta dai dati veri)
Sono **gli stessi che alimentano la card Salute**, così le due cose non si
contraddicono mai. Scattano a queste condizioni:

| Avviso | Quando compare |
|---|---|
| **Fatturato mancante** | il mese precedente non ha fatturato (né normale né in "modalità mensile") |
| **Costo personale mancante** | il mese precedente non ha costi del personale |
| **Incasso di ieri mancante** | ieri non risulta nessun incasso (saltato se la sede lavora in "modalità mensile") |
| **Righe da classificare** | ci sono righe fattura non categorizzate (ultimi 30 giorni) |
| **Fatture costo mancanti** | mese con ricavi ma **zero costi food+spese**, oppure nessuna fattura caricata da 30 giorni |
| **Ricavi automatici assenti** | cliente collegato ai ricavi automatici ma nessun ricavo da ≥3 giorni |
| **Alert prezzi** | un prodotto/categoria è rincarato oltre la soglia automatica |
| **Anomalia coperti** | i coperti di ieri si scostano ≥30% dal solito |

---

## 4. Le due "aperture" (il contesto iniziale, non to-do)

In testa al briefing, nell'ordine: prima il rientro, poi la buona notizia
("prima il bene, poi la rogna").

- **Rientro** — "Bentornato" se non apri il briefing da **≥7 giorni**. Propone
  l'assistenza solo se la Salute è rossa. Mai un rimprovero.
- **Buona notizia** — sceglie la prima disponibile tra:
  1. **MOL del mese chiuso**, festeggiato **solo se** è positivo, **maggiore del
     mese prima**, la Salute non è rossa **e** i costi del mese non mancano
     (altrimenti sarebbe un "+X%" falso);
  2. altrimenti **perdita in calo** (in rosso ma meno del mese prima);
  3. altrimenti **incasso di ieri** (solo di ieri; più vecchio = silenzio),
     con lo scontrino medio se si scosta ≥15% dalla media;
  4. altrimenti **nessuna apertura**: il briefing è solo lista di cose da fare.

---

## 5. Come sceglie e ordina le voci

1. **Una voce per argomento** — niente doppioni dello stesso tema.
2. **Solo ciò su cui puoi agire** — i conteggi compaiono solo se > 0; un upload
   fallito compare solo se era automatico (quello manuale lo vedi mentre carichi).
3. **Rispetta gli interruttori del configuratore** — le voci che hai spento
   spariscono. Eccezione: **gli upload falliti non si possono spegnere**.
4. **Ordina per importanza dell'argomento**, e a parità di argomento per gravità
   (errore prima, poi attenzione, poi informazione). Regola: prima il tema, poi la
   gravità dentro lo stesso tema.
5. **Tiene le prime 5** — il resto resta nella campanella.

Ordine di importanza degli argomenti (dal più al meno urgente):

> rientro → buona notizia → upload fallito → upload ricavi fallito → alert prezzi →
> righe da classificare → fatture mancanti → fatturato mancante → incasso mancante →
> costo personale mancante → scadenze → anomalia coperti → appuntamenti

Se **nessuna voce viene selezionata**, e solo allora, il briefing dice che è tutto a posto.

---

## 6. Il tono

- **Versione scritta a mano**: apertura + "Da sistemare oggi:" + una frase per
  voce. Fonde fatturato e personale dello stesso mese in un'unica frase.
- **Versione riscritta dall'AI** (solo nella rigenerazione completa): tono
  **sobrio**, max 3 frasi, niente entusiasmo da coach, niente aggettivi enfatici,
  al massimo 1 emoji, vietato inventare numeri. I nomi di prodotti e fornitori
  vengono **nascosti** prima di inviare il testo all'AI e ripristinati dopo (i nomi
  veri non escono mai). Se l'AI sbaglia o non risponde → torna alla versione a mano.

**Saluto:** "Buongiorno" fino alle 12, "Buon pomeriggio" fino alle 18, poi
"Buonasera", seguito dal nome del referente (mai la ragione sociale).

---

## 7. Coerenza tra briefing, campanella e Salute

Briefing, campanella e card Salute leggono **le stesse fonti**. La campanella
mostra le card del briefing più le voci minori che non sono entrate nelle prime 5.
Per costruzione, le tre cose non possono contraddirsi.

---

## 8. Il briefing della CATENA (gruppo)

Calcolato dal vivo a ogni apertura (non è giornaliero come quello del singolo PV).
Regole:

- La **completezza di una sede** si misura sulla sua **Salute** (che vede i costi
  mancanti), non solo sul fatturato. Una sede entra nel confronto dei margini solo
  se è affidabile (Salute ≥ 50); sotto quella soglia il suo margine non è reale e la
  sede viene contata come "da completare".
- Solo le sedi affidabili entrano nel confronto "va meglio / è più indietro".
- "Tutto sotto controllo" appare **solo se**: nessun avviso aperto, Salute non
  rossa e nessuna sede incompleta. Mai dire che va tutto bene mentre la salute del
  gruppo è bassa.

> **Da fare:** la card "I conti del gruppo" può ancora mostrare numeri gonfiati
> (food cost basso, MOL irreale) quando più sedi non hanno i costi inseriti — stesso
> problema dei costi mancanti ma a livello di gruppo, non ancora affrontato.

---

## 9. Le leve su cui puoi chiedermi di intervenire

| Cosa vuoi cambiare | Valore attuale |
|---|---|
| Quante card mostra al massimo | 5 |
| L'ordine di importanza degli argomenti | vedi §5 |
| Quali avvisi si possono spegnere | tutti tranne gli upload falliti |
| Dopo quanti giorni dice "bentornato" | 7 giorni |
| Quando festeggiare il MOL | positivo, in crescita, salute ok, costi presenti |
| Soglia scontrino medio "notevole" | 15% |
| Soglia anomalia coperti | 30% |
| Finestra "righe/fatture recenti" | 30 giorni |
| Finestra "ricavi automatici assenti" | 3 giorni |
| Tono, lunghezza, numero di emoji | sobrio, 3 frasi, 1 emoji |
| Soglie colore Salute | ≥80 verde / ≥50 giallo / <50 rosso |
| Soglia di affidabilità sede nella catena | Salute ≥ 50 |

Per ognuna basta che mi dici il nuovo valore o la nuova regola e la applico.

---

## 10. Esempio reale (LAND DEI SAPORI)

> *"Buon pomeriggio, MARCO e GABRI"* → saluto per ora + nome referente
> *(nessuna apertura festante)* → il MOL non si festeggia perché mancano i costi
> *"Da sistemare oggi: mancano le fatture costo di maggio… 2 righe da classificare"*
> → i due avvisi più importanti, riscritti in tono sobrio
