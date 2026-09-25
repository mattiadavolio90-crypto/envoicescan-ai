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
  l'analisi prezzi e le **osservazioni** (§4-bis), le parti lente. In sottofondo
  prepara la versione completa per l'apertura successiva.
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
| **Costo personale mancante** | un mese chiuso non ha costi del personale. Il mese **appena chiuso** si chiede solo **dal 15** (la busta paga arriva a metà mese: prima, 5 sedi su 5 risultavano "in ritardo"); i mesi più vecchi subito |
| **Incasso di ieri mancante** | ieri non risulta nessun incasso. Si dice **solo il giovedì** (guarda il mercoledì), cioè una volta a settimana, e solo se la sede ha già inserito incassi in passato; saltato in "modalità mensile". Se nelle impostazioni del locale ci sono N giorni di chiusura a settimana, basta un incasso negli ultimi N+1 giorni (come per i ricavi automatici): chi è chiuso il mercoledì non riceve l'avviso il giovedì. La card non ha il bottone «Ignora», quindi l'unico modo per non ripeterlo è non dirlo: quando usciva tutti i giorni veniva ignorato 25 volte su 35 |
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
     mese prima**, la Salute non è rossa **e** i due mesi sono confrontabili:
     **entrambi** con fatturato e con i costi presenti (altrimenti sarebbe un
     "+X%" falso);
  2. altrimenti **perdita in calo** (in rosso ma meno del mese prima), con la
     stessa condizione sui due mesi. Fino al 23/9/2026 diceva «la perdita è
     scesa a € 9.380» su due mesi **senza incassi**: la "perdita" era la somma
     dei costi, e il "miglioramento" era che ne erano stati inseriti meno;
  3. altrimenti **incasso di ieri** (solo di ieri; più vecchio = silenzio),
     con lo scontrino medio se si scosta ≥10% dalla media, e il confronto con la
     media dello stesso giorno della settimana quando c'è abbastanza storico;
  4. altrimenti **fatture arrivate ieri** — per i locali che ricevono le fatture
     in automatico e non inseriscono l'incasso, è il loro dato fresco. Dice
     **quante e quanto, e basta**: fino al 9/9/2026 aggiungeva anche le righe da
     controllare, ripetendo parola per parola la voce che sta due righe sotto e
     rimanda alla stessa card (vedi §5.1);
  5. altrimenti **nessuna apertura**: il briefing è solo lista di cose da fare.

### 4-bis. Le osservazioni: cosa direbbe un consulente (dal 24/9/2026)

Dopo le aperture e prima di "Da sistemare oggi", il briefing può dire un fatto
sull'**andamento** del locale, non sulla completezza dell'archivio. Come le
aperture, non sono card e non contano per il "tutto a posto"; a differenza
delle aperture, **si possono spegnere** dal configuratore. Si calcolano solo
nella versione completa (§2), non in quella rapida.

- **Andamento dell'incasso**: **solo il martedì**. Confronta l'incasso delle
  ultime 4 settimane (lunedì-domenica) con le 4 prima e parla solo se si è
  mosso di **almeno il 10%** in su o in giù. Servono almeno 20 giorni con
  incasso in ciascuna delle due finestre, o tace. Se i coperti sono inseriti
  (almeno 20 giorni per finestra) dice anche come si sono mossi coperti e
  scontrino medio; sotto il 3% li dice "stabili".
  *Come suona* (cifre di esempio): «📊 Nelle ultime 4 settimane sono entrati € 48.210 di incasso, il
  16% in più delle 4 settimane prima (€ 41.668).»
- **Food cost alto**: **solo a cavallo fra un mese e l'altro** (l'ultimo giorno
  del mese e i primi 7 del successivo), e sul mese di **due mesi prima**:
  l'ultimo mese caricato è quasi sempre parziale (fatture ancora in arrivo) e
  darebbe un food cost falsamente basso. Serve che il mese dopo abbia già
  fatture di food & beverage, o tace. Parla se il food cost supera il **33%**
  (norma del settore 28-33%), dice "soglia critica" oltre il **38%**, e
  aggiunge quanti euro di acquisti in più rappresenta rispetto al 33%. Mai per
  i negozi.
  *Come suona* (cifre di esempio): «🍽️ A luglio il food cost è stato del 45,8%, oltre la soglia
  critica del 38%: rispetto al 33% sono circa € 581 di acquisti in più.»
  ⚠️ **Parlerà spesso**: sopra il 33% è la condizione normale di molte sedi
  (misurato: 22 mesi consolidati su 32, su 7 sedi su 8). Quando le fatture sono
  al passo, a ogni cambio di mese si accenderà su quasi tutte; oggi tace perché
  le fatture di molte sedi sono ferme (simulato: 5 sedi il 3/8, nessuna il 2/9).
  Se ti sembra troppo, la leva è la soglia (§9).

**Perché solo queste due** (misurato sul DB il 24/9): delle altre candidate
del piano nessuna diceva qualcosa di utile. Il fornitore che pesa più dell'80% di una
categoria c'era su 7 sedi su 8 (quasi tutto bevande: rumore); nessun prodotto o
categoria saliva da 3 mesi; le scadenze "accumulate" erano false perché metà
delle sedi non segna mai le fatture pagate; il MOL mese su mese è un'altalena.

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

> rientro → buona notizia → andamento incasso → food cost alto → upload fallito → upload ricavi fallito → alert prezzi →
> righe da classificare → fatture mancanti → fatturato mancante → incasso mancante →
> costo personale mancante → scadenze → anomalia coperti → appuntamenti

Se **nessuna voce viene selezionata**, e solo allora, il briefing dice che è tutto a posto.

**I dati mancanti sono una riga, non la notizia del giorno** (dal 24/9/2026).
Fatturato, costo del personale, incasso e fatture di un mese senza costi restano
card (col loro bottone), ma nel testo non hanno più una frase ciascuno: si
raccolgono **in una riga sola, in fondo** — «Per completare il quadro mancano il
fatturato di agosto 2026 e il costo del personale di luglio 2026: finché non ci
sono, margini e food cost non sono completi.» Fatturato e personale dello stesso
periodo si dicono insieme. Prima «il fatturato non è stato inserito» era l'apertura di 31
briefing su 43.

---

## 6. Il tono

- **Versione scritta a mano**: apertura + osservazioni + "Da sistemare oggi:" +
  una frase per voce + in fondo la riga dei dati mancanti (§5). Se mancano solo
  dati, niente "Da sistemare oggi:": dopo l'eventuale apertura c'è solo quella
  riga.
- **Versione riscritta dall'AI** (solo nella rigenerazione completa): tono
  **sobrio**, max 3 frasi, niente entusiasmo da coach, niente aggettivi enfatici,
  al massimo 1 emoji, vietato inventare numeri. Le osservazioni si dicono
  **sempre** e non contano nelle 3 frasi: se l'AI ne perde la cifra, o il testo
  esce troncato, si torna alla versione a mano. I nomi di prodotti e fornitori
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

È un **testo fisso scritto dal codice**, senza AI: decisione di Mattia del 24/9, che
l'AI eventualmente la si aggiunge dopo. Viene calcolato dal vivo a ogni apertura e non
è giornaliero come quello del singolo PV. Sotto c'è la card «Da vedere nella catena»,
che invece si calcola una volta al giorno.

Regole della frase:

- **Una sede è completa** se nel mese chiuso ha tre cose: il fatturato, le fatture di
  costo (euro di merce del mese) e il costo del personale. È un controllo sulla
  **presenza dei dati**, non sulla percentuale di Salute. Se ne manca una, il margine
  di quella sede non è reale:
  - la sede resta fuori dal confronto «va meglio / è più indietro»;
  - la frase dice «N punti vendita hanno i dati di costo ancora da completare».
- **Il personale, fino al 14 del mese**, segue la regola del PV (§3): quello del mese
  appena chiuso non si chiede ancora. Se a una sede manca solo quello:
  - la sede non viene detta «da completare», e al suo posto: «In un punto vendita il
    costo del personale di settembre non è ancora inserito: fino ad allora il margine
    è più alto del reale.»
  - resta comunque fuori dal confronto, perché il margine è davvero gonfiato;
  - la stessa regola vale per l'indice di Salute di ogni sede e per l'avviso «Mancano
    il costo del personale» della card.
- **«Tutto in ordine»** compare solo se non ci sono avvisi aperti, la Salute non è
  rossa, nessuna sede è da completare e non ci sono fatture di gruppo da smistare.
  Mai dire che va tutto bene mentre la salute del gruppo è bassa. Le sedi che
  aspettano solo il personale non lo spengono, come nel PV. La card «I conti del
  gruppo», però, resta in ambra con «N PV con dati di costo incompleti»: parla del
  numero, che senza personale è davvero gonfiato, e non di un compito.

**Le osservazioni da consulente** stanno nella card, nel riquadro «Da sapere», sopra
gli avvisi. Sono quelle del PV (§4-bis): stesso calcolo, stessa frase, stessi giorni.
- **Andamento dell'incasso**: il martedì.
- **Food cost alto**: fra l'ultimo giorno del mese e i primi 7; mai per i negozi.

C'è una riga per sede, col nome della sede davanti. Non sono avvisi, quindi non
spengono il «Tutto in ordine» e non si contano fra gli avvisi aperti. Si spengono in
tre modi:
- dal configuratore della catena;
- escludendo la sede dall'assistente della catena;
- spegnendole nel configuratore **di quella sede**: se l'hai spento sul PV, la catena
  non te lo ripete. Vale dal giorno dopo, perché la card della catena si calcola una
  volta al giorno e cambiare il configuratore del PV non la ricalcola.

Se il calcolo di un'osservazione fallisce, quell'osservazione manca e basta, come nel
PV: non spegne gli avvisi né il «Tutto in ordine». Nei giorni in cui nessuna delle
due può uscire, la card non fa nessuna lettura in più.

> ⚠️ **Parleranno poco finché i dati restano fermi**: misurato il 24/9 sulle 3
> catene. Negli ultimi martedì un'osservazione è comparsa solo il 1° settembre, per
> una sede su 5. Il food cost di inizio ottobre non esce da nessuna parte, perché le
> fatture di settembre non ci sono ancora. È lo stesso limite della fase 4: fatture e
> incassi fermi da settimane.

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

## 8-bis. L'email settimanale del lunedì

Una volta a settimana, il lunedì fra le 7 e le 10, l'assistente scrive al
cliente, anche se non apre l'app (fase 7, deciso il 24-25/9). **La ricevono solo i
clienti che abiliti tu**, uno per uno, dalla scheda cliente nel pannello admin
(«Email settimanale»): di default è spenta per tutti. Il cliente abilitato la
può sempre spegnere dal link nell'email o dalle Impostazioni, e la sua scelta
vince: se l'ha spenta, riabilitarlo non la riaccende. Dalla stessa scheda,
«Mandami una prova» ti spedisce l'email che quel cliente riceverebbe, anche
prima di abilitarlo. In più c'è un interruttore generale sul server
(`EMAIL_SETTIMANALE_ATTIVA`): finché è spento non parte niente per nessuno.

La regola è la tua: **mai informazioni inutili o incomplete**. Ogni argomento
compare solo se per quel cliente il dato è affidabile:

| Argomento | Quando compare | Esempio |
|---|---|---|
| Incasso della settimana | Sia la settimana chiusa sia quella prima hanno almeno 6 giorni registrati (uno in meno per ogni giorno di chiusura dichiarato nelle impostazioni del locale) | «La settimana scorsa hai incassato € 2.012, in linea con la settimana prima.» Sotto il 3% è «in linea» |
| Fatture arrivate | Solo dove le fatture arrivano **in automatico dallo SDI** (almeno una negli ultimi 30 giorni). Chi carica a mano lo fa a blocchi, e «0 fatture questa settimana» sarebbe falso. Le note di credito non si contano. In una catena c'è anche la riga dei **costi comuni di gruppo** (le fatture intestate alla società), l'unico argomento in cui compare | «La settimana scorsa sono arrivate dallo SDI 7 fatture per € 5.081.» |
| Osservazioni (§4-bis) | Quando scattano, con le stesse regole del briefing. L'andamento dell'incasso parla il martedì, quindi di lunedì tace: c'è già l'incasso della settimana | — |
| Invito a riprendere | Solo a chi **non manda dati da 4 settimane** (né fatture né incassi, su nessuna sede) | «Non riceviamo dati dal 15 luglio: bastano le fatture per ricominciare.» |

Non entrano i compiti (righe da classificare, dati mancanti): non sono notizie.
Una catena riceve un'email sola, con una riga per sede. **Se nessun argomento ha
qualcosa da dire, quella settimana l'email non parte.**

Se un argomento non si riesce a calcolare (un guasto), non si finge che non ci sia
niente da dire: scatta un avviso a noi, e senza altri argomenti quella email non
parte. Se le impostazioni del locale non si leggono, le osservazioni non partono:
un'email spedita non si ritira.

> Misurato sui dati del 21/9: su 6 clienti, 3 avrebbero ricevuto numeri (incasso
> per SUSHILAND e CASATI 14, fatture dallo SDI per OFFSIDE) e 3 l'invito a
> riprendere (FISH HOUSE, TIME CAFE, ASI). Il 7/9 CASATI 14 non l'avrebbe
> ricevuta: la settimana prima aveva solo 4 giorni di incasso.

## 9. Le leve su cui puoi chiedermi di intervenire

| Cosa vuoi cambiare | Valore attuale |
|---|---|
| Quante card mostra al massimo | 4 |
| L'ordine di importanza degli argomenti | vedi §5 |
| Quali avvisi si possono spegnere | tutti tranne gli upload falliti |
| Dopo quanti giorni dice "bentornato" | 7 giorni |
| Quando festeggiare il MOL | positivo, in crescita, salute ok, fatturato e costi presenti in entrambi i mesi |
| Soglia scontrino medio "notevole" | 10% |
| Soglia anomalia coperti | 20% |
| Da che giorno si chiede il personale del mese chiuso | dal 15 |
| Giorno dell'avviso "incasso mancante" | giovedì |
| Andamento incasso: giorno e soglia | martedì, ±10% su 4 settimane |
| Andamento incasso: giorni minimi con incasso per finestra | 20 |
| Coperti e scontrino "stabili" sotto | 3% |
| Food cost: norma / critico | fino al 33% / oltre il 38% |
| Food cost: quando se ne parla | ultimo giorno del mese e primi 7 |
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
