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
> si mettono in ordine di importanza → si scelgono i più importanti (max 4) →
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

✅ **Dopo un aggiornamento del programma il briefing si rigenera da solo.** Ogni
snapshot salvato porta dentro il numero di versione della logica che l'ha prodotto:
se cambio le regole e alzo quel numero, gli snapshot vecchi vengono scartati alla
prima apertura. Non c'è nessuna cache da svuotare a mano.

Oltre a questo, un briefing più vecchio di **30 minuti** viene comunque rifatto:
copre i dati che cambiano durante il giorno (righe classificate, fatture elaborate
in sottofondo) senza aspettare il giorno dopo.

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
| **Righe da classificare** | ci sono prodotti da controllare **caricati negli ultimi 7 giorni**; l'arretrato più vecchio non fa card ma viene citato nel testo se supera 20 voci |
| **Fatture costo mancanti** | mese con ricavi ma **zero costi food+spese**, oppure nessuna fattura caricata da **7 giorni** |
| **Ricavi automatici assenti** | cliente collegato ai ricavi automatici ma nessun ricavo da più giorni dei suoi giorni di chiusura + 1 |
| **Alert prezzi** | un prodotto/categoria è rincarato oltre la soglia automatica |
| **Anomalia coperti** | i coperti di ieri si scostano ≥20% dal solito (servono almeno 4 giorni con coperti nel periodo di riferimento) |

---

## 4. Le tre "aperture" (il contesto iniziale, non to-do)

In testa al briefing, nell'ordine: prima il benvenuto o il rientro, poi la buona
notizia ("prima il bene, poi la rogna"). Non sono card: non si ignorano e non
contano per il "tutto a posto".

- **Benvenuto** — per un locale nuovo, che non ha ancora nessun dato. Sostituisce
  le altre due: senza dati non c'è né un rientro né una buona notizia da dare.
- **Rientro** — "Bentornato" se non apri il briefing da **≥7 giorni**. Propone
  l'assistenza solo se la Salute è rossa. Mai un rimprovero.
- **Buona notizia** — sceglie la prima disponibile tra:
  1. **MOL del mese chiuso**, festeggiato **solo se** è positivo, **maggiore del
     mese prima**, la Salute non è rossa **e** i costi del mese non mancano
     (altrimenti sarebbe un "+X%" falso);
  2. altrimenti **perdita in calo** (in rosso ma meno del mese prima);
  3. altrimenti **incasso di ieri** (solo di ieri; più vecchio = silenzio),
     con lo scontrino medio se si scosta ≥10% dalla media, e il confronto con la
     media dello stesso giorno della settimana quando c'è abbastanza storico;
  4. altrimenti **fatture arrivate ieri** — per i locali che ricevono le fatture
     in automatico e non inseriscono l'incasso, è il loro dato fresco. Dice
     **quante e quanto, e basta**: fino al 9/9/2026 aggiungeva anche le righe da
     controllare, ripetendo parola per parola la voce che sta due righe sotto e
     rimanda alla stessa card (vedi §5.1);
  5. altrimenti **nessuna apertura**: il briefing è solo lista di cose da fare.

---

## 5. Come sceglie e ordina le voci

1. **Una voce per argomento** — niente doppioni dello stesso tema.

   > ### 5.1 Chi possiede un'informazione la dice una volta sola
   >
   > La regola vale anche **fra apertura e corpo**, non solo dentro l'elenco:
   > sono due blocchi che vengono concatenati senza controllo di sovrapposizione,
   > ed è lì che il 9/9/2026 il cliente leggeva *"una riga è da controllare, la
   > trovi qui sotto"* seguito, due righe dopo, da *"Ci sono alcune righe da
   > controllare: trovi il dettaglio qui sotto"*.
   >
   > Il posto che possiede un'informazione è **quello che ha la CTA**: l'apertura
   > accenna alla novità, la voce to-do rimanda alla card.
   >
   > *Limite noto*: se quella voce è **spenta dal configuratore**, l'informazione
   > non la dà più nessuno — prima l'accenno in apertura passava comunque, perché
   > il filtro dei topic spenti guarda un'altra voce. È coerente con la richiesta
   > del cliente (ha spento proprio quell'avviso), ma va saputo.
   >
   > Vale anche in catena,
   > dove per lo stesso motivo la narrativa **non parla più** delle fatture di
   > gruppo da collocare: quel tema vive nel campo strutturato, e il rimando lo
   > scrive il client — che è l'unico a sapere se la coda esiste (sul mobile non
   > c'è, quindi "qui sotto" sarebbe falso).
2. **Solo ciò su cui puoi agire** — i conteggi compaiono solo se > 0; un upload
   fallito compare solo se era automatico (quello manuale lo vedi mentre carichi).
3. **Rispetta gli interruttori del configuratore** — le voci che hai spento
   spariscono. Eccezione: **gli upload falliti non si possono spegnere**.
4. **Ordina per importanza dell'argomento**, e a parità di argomento per gravità
   (errore prima, poi attenzione, poi informazione). Regola: prima il tema, poi la
   gravità dentro lo stesso tema.
5. **Tiene le prime 4** — il resto resta nella campanella. (Tua decisione del
   19/06: l'andamento sta nel testo del briefing, le card sono SOLO cose da fare.)

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
mostra le card del briefing più le voci minori che non sono entrate nelle prime 4.
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

### La cascata dei dati del gruppo (RISOLTO, verificato 17/7)

La card "I conti del gruppo" **mette il MOL al centro come il PV** (dal 9/9/2026)
e, quando i costi sono incompleti, **lo dice accanto invece di nasconderlo**.
Funziona a quattro livelli, decisi dalla presenza dei dati (non dalla percentuale
di salute), scelti da `metricaPrincipaleConti` in `lib/catena-confronti.ts` —
una funzione sola per desktop e `/m`, così le due superfici non divergono:

| Livello | Quando | Cosa mostra |
|---|---|---|
| **non_determinabile** | la completezza dei PV non è stata letta (RPC in errore) | Nessun numero: "Conti del gruppo non disponibili" + Riprova. Mai il verde |
| **nessuno** | il gruppo non ha né fatturato né spese food | Nessun numero: "Dati ancora incompleti, completa i punti vendita" |
| **food** | ci sono le spese food, ma a qualche sede manca il **personale** | **MOL grande** in ambra + avviso "N PV con dati di costo incompleti: questo margine non è reale" (porta alla finestra Margini, che marca quali). Food cost nella riga sotto, una volta. Badge "margine %" **nascosto**: è Σmol/Σnetto, cioè lo stesso numero gonfiato. Card gialla, mai verde/rosso |
| **completo** | tutte le sedi hanno fatturato + food + personale | MOL e margine, colore verde/rosso |

**Perché:** senza il costo del personale di una sede il MOL aggregato è gonfiato
verso l'alto. Fino al 9/9 la catena lo **nascondeva** e al suo posto metteva il
food cost: due viste dello stesso prodotto con due metriche diverse in primo
piano (screenshot del 9/9: "FOOD COST DEL GRUPPO 39,1%" in catena, "MOL −14.590 €"
nel PV). Ora la catena fa come il PV: il numero si vede sempre, e quando non è
reale lo dice l'avviso — non il silenzio.

**Una divergenza deliberata dal PV, da sapere:** con i costi incompleti il PV
mostra il MOL **e** tutto il breakdown (Personale e Spese inclusi); la catena
mostra il MOL ma **nasconde** Personale e Spese. Lì i costi mancano a una sede e
le righe restano i suoi numeri; qui una somma di gruppo a cui manca il personale
di 2 PV su 4, etichettata "Costo personale", sarebbe un secondo numero falso
sotto il primo, senza un avviso suo. Scelta di prodotto, non un bug: se si vuole
il breakdown parziale va aggiunto con il suo caveat.

> Storico. Verificato il 17/7 su SUSHILAND: 3 sedi su 4 non avevano il costo
> personale, quindi il gruppo stava al livello "food" e il MOL era **nascosto** —
> era la regola di allora. Dal 9/9/2026 nello stesso caso il MOL si vede, in ambra
> e con l'avviso. Il livello di SUSHILAND oggi non è stato ri-misurato.

---

## 9. Le leve su cui puoi chiedermi di intervenire

| Cosa vuoi cambiare | Valore attuale |
|---|---|
| Quante card mostra al massimo | 4 |
| L'ordine di importanza degli argomenti | vedi §5 |
| Quali avvisi si possono spegnere | tutti tranne gli upload falliti |
| Dopo quanti giorni dice "bentornato" | 7 giorni |
| Quando festeggiare il MOL | positivo, in crescita, salute ok, costi presenti |
| Soglia scontrino medio "notevole" | 10% |
| Soglia anomalia coperti | 20% |
| Da quanti giorni senza fatture scatta l'avviso | 7 giorni |
| Finestra "novita" da controllare | 7 giorni |
| Quante voci arretrate prima di dirlo | 20 |
| Finestra "ricavi automatici assenti" | giorni di chiusura + 1 |
| Ogni quanto si ricalcola in giornata | 30 minuti |
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
