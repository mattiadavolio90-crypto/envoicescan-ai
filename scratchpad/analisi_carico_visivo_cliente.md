# ONEFLUX — cosa rende l'app faticosa da capire

**16/09/2026** · Analisi del carico visivo delle pagine cliente desktop.
Metro: un ristoratore poco avvezzo alla tecnologia.

**Come è stata fatta.** Due audit sull'app vera (account SUSHILAND, dati reali,
singolo locale e catena) più la lettura del codice, che dice *perché* succede e
quanto costa rimediare. Dove le fonti divergono lo scrivo.

**Il documento ha due parti:**

- **Parte 1 — cosa c'è a schermo e dove.** Quanto si scorre, cosa manca, cosa
  confonde nei contenuti.
- **Parte 2 — come appare.** Colore, spazio, cornici, tipografia: la parte che
  risponde a *"sembra complessa?"*. **Inizia [qui](#parte-2--come-appare-lapp).**
  Se hai poco tempo, comincia da lì: contiene i voti di complessità visiva.

**Cosa non copre.** L'account era pieno di dati: **il giorno 1 di un cliente
nuovo non è stato misurato.** Fuori anche Agenda/Personale e Strumenti (esclusi
su tua richiesta), l'area admin, il mobile e le pagine pubbliche. Non ci sono
screenshot: lo strumento di cattura non li salvava su file.

---

## In una pagina

L'app non è confusa a caso. Ha già in casa lo standard giusto — e in certi punti
è scritta con più cura della media. Il problema è un altro, e il test lo ha messo
a fuoco meglio di qualsiasi lettura del codice:

> **L'app mostra numeri enormi e rassicuranti costruiti su dati che le mancano.**

Un MOL di 2,2 milioni con scritto "eccellente" in verde, mentre in quattro mesi i
costi sono a zero. Un risparmio di 1.507 € che per 1.319 € viene da una sola riga
sbagliata. 641.555 € di scaduto che sono, con ogni probabilità, fatture pagate e
mai segnate. Per un utente poco tecnico questo è il danno peggiore possibile: non
si limita a non capire, **smette di fidarsi**. E quando smette di fidarsi di un
numero, smette di fidarsi di tutti.

Il secondo problema è che **le informazioni utili sono sempre in fondo.** In
catena, l'unica riga che fa risparmiare soldi ("Villa Guardia: pesce 9.635 € in
più del gruppo") sta a 1,8 schermate, sotto cinque righe che ripetono la stessa
cosa. In Analisi e Tag, il fornitore che ti costa il 77% in più è in terza riga
di una tabella a 1,5 schermate. In Gestione Fatture, per vedere le scadenze del
mese devi scorrere 38 schermate di scadute.

Il terzo è la **densità in alto**: da 11 a 29 elementi che chiedono attenzione,
di cui al primo accesso se ne usano 1 o 2.

**Le tre cose da fare per prime**, in mezza giornata scarsa:
1. Far comparire i nomi delle sedi in Catena (oggi sono invisibili — è un bug).
2. Chiudere la sezione "Scadute" all'apertura di Gestione Fatture.
3. Non mostrare il MOL gigante quando i dati del mese sono incompleti.

---

## Quello che è già buono, e non va toccato

Va detto prima, perché è lo standard a cui riportare il resto — ed è più facile
copiare una cosa di casa che inventarne una nuova.

- **Il testo dell'assistente in Catena** è la cosa meglio riuscita che ho visto:
  breve, dice subito il problema vero ("5 punti vendita hanno i dati di costo
  ancora da completare: lì il margine non è reale"), e non nasconde niente.
  Confrontato con la Home del singolo locale, che dice la stessa cosa quattro
  volte in quattro posti diversi, è un altro prodotto.
- **Il MOL di gruppo è arancione, non verde**, proprio perché i dati sono
  incompleti. La Home del singolo locale in identica situazione lo mostra verde e
  gigante. Qualcuno ci ha pensato: va esteso, non rifatto.
- **"Escludi dai conti"** ha conferma in due passi, dice la conseguenza esatta
  ("uscirà da margini, foodcost e analisi"), ed è reversibile. È messa
  deliberatamente prima del cestino per intercettare chi vuole solo togliere una
  fattura dai numeri. Fatta bene.
- **Il caricamento fatture** dà conto file per file (fornitore, righe, data,
  sede), distingue cinque esiti diversi e protegge la chiusura se qualcosa non è
  andato.
- **I numeri per sede sono coerenti**: filtrando Villa Guardia dalla vista gruppo
  escono le stesse cifre della vista locale. L'audit l'ha verificato.
- **Le sezioni vuote non compaiono** in Gestione Fatture. Giusto così.
- **L'app distingue "non ci sono dati" da "non sono riuscito a caricare"**, con
  testi rassicuranti. È una cura non comune.

---

## I rilievi, in ordine di importanza

L'ordine risponde a: *fa perdere fiducia?* poi *nasconde ciò che serve?* poi
*costa attenzione ogni giorno?* — e a parità, prima ciò che costa meno togliere.

---

### 1. L'app dà giudizi entusiasti su dati che non ha

**Cosa vede il cliente.** MOL 2.212.781 € su 3,26 milioni: il 68% di margine, per
un ristorante una cifra impossibile. Sotto, in verde: "MOL eccellente", "Food
cost eccellente". La tabella mostra costi a zero in gennaio, febbraio, agosto e
settembre, e personale a zero da luglio. **I giudizi nascono dai buchi.**

Lo stesso in Home: MOL di 416.798 € verde e gigante, e subito sotto la pagina
stessa scrive che *non è reale*. Due messaggi opposti nella stessa schermata.

E in Osservatorio: "Impatto stimato −1.507 €", di cui 1.319 € vengono da una
"Bevanda analcolica alle erbe" passata da 14,00 € a 0,40 €, cioè un errore di
lettura del prezzo. Un solo dato sbagliato detta il titolo della pagina.

**Perché.** I riquadri e i giudizi si calcolano su ciò che c'è, senza chiedersi se
sia completo. Il dato esiste già per saperlo: la Home lo segnala ("Mancano le
fatture di agosto"), Ricavi e Margini no.

**Leva:** ottimizzare · **Costo:** mezza giornata · **Chi ci perde:** chi guarda
il margine a colpo d'occhio e accetta che sia parziale — perde il numero grande e
vede un avviso. È un buon scambio: oggi quel numero è sbagliato.

**Da decidere:** nascondere il numero finché i dati mancano, o mostrarlo in grigio
con l'avviso accanto (come già fa la Catena). La seconda è più prudente e più
coerente con quello che l'app fa già altrove.

---

### 2. In Catena non si vedono i nomi delle sedi — è un bug

**Cosa vede il cliente.** Nel riquadro "Salute e margini per sede", cinque righe
cliccabili che dicono: `● dati incompleti 0 ›` · `● dati incompleti 25 ›` · `25 ›`
· `49 ›` · `50 ›`. **Di quale locale si parli non è dato sapere.** In una pagina
il cui unico scopo è confrontare i punti vendita.

**Perché.** Verificato: nella riga il nome è l'**unico** elemento senza protezione
dal restringimento — pallino, scritta "dati incompleti", indice e freccia sono
tutti protetti. Quando lo spazio manca, l'unico che può cedere è il nome, e
sparisce del tutto. Succede su portatile a 1140 px, cioè su uno schermo normale.

**Leva:** ottimizzare · **Costo:** <1h · **Chi ci perde:** nessuno. Su schermi
stretti si accorcerà "dati incompleti", non il nome.

> È il rilievo più urgente del documento. Non è una questione di gusto: una
> funzione centrale è inutilizzabile, e chi la apre su un portatile non può usarla.

---

### 3. Lo stesso numero, due valori diversi, stesso nome

**Cosa vede il cliente.** In Ricavi e Margini il riquadro viola **"Costi
gestione" dice 151.211 €**; la riga viola in tabella **"= Costi gestione totali"
dice 511.211 €**. Stesso nome, stesso colore, 360.000 € di differenza.

**Perché.** Verificato: il riquadro mostra le sole spese generali, il riepilogo
somma spese **più personale**. Due definizioni legittime con la stessa etichetta.

Non è isolato. L'audit ne ha trovati altri:

| Dove | Cosa non torna |
|---|---|
| Gestione Fatture | "Scadute 641.555 €" e "Da pagare (filtro) 430.340 €" sulle **stesse 414 fatture** |
| Gestione Fatture | contatore "426 su 581" con 414 scadute |
| Home | Fatturato 447.728 − 0 − 0 − 0 dovrebbe dare 447.728, il MOL dice 416.798 |
| Analisi Fatture | 6.626 righe / 6.728 acquisti / 1.798 prodotti / 1.766 prodotti diversi |
| Da verificare / Home | 101 prodotti e 19.050 € qui, 100 prodotti e 582 € là |
| Analisi e Tag | "Media periodo 7,66 €" e "Prezzo medio 7,83 €" a pochi centimetri |
| Vista gruppo | "2.582 fatture totali" e "Seleziona tutte (2.545)" sulla stessa riga |
| Villa Guardia | margine 39% in catena, 68% in Ricavi e Margini, 100% in Home |

Sul MOL della Home l'ipotesi dell'audit è probabilmente giusta: il fatturato
mostrato è lordo IVA, il MOL parte dal netto. Sull'ultima riga: tre periodi
diversi mai dichiarati.

**Leva:** rinominare (e dichiarare il periodo) · **Costo:** mezza giornata per
distinguere i nomi; le divergenze di Gestione Fatture vanno prima capite — **sono
le sole cose di questo documento che potrebbero essere bug veri.**

**Chi ci perde:** nessuno. Due grandezze diverse devono avere due nomi diversi.

---

### 4. Le informazioni che fanno risparmiare sono sempre le ultime

**Cosa vede il cliente.**

- **Catena:** cinque righe quasi identiche ("Mancano le fatture costo e il costo
  del personale") spingono in fondo gli unici avvisi che valgono soldi: *"Villa
  Guardia: pesce 59% della spesa contro 53% del gruppo, circa 9.635 € in più in 3
  mesi"* e *"margine al 39%, era 50%"*. A 1,8 schermate.
- **Analisi e Tag:** *"UNO S.R.L +77,4%"* — paghi il salmone 13,90 € invece di
  7,63 € — è in terza riga di una tabella che comincia a 1,5 schermate, sotto un
  grafico alto quasi una schermata.
- **Analisi Fatture:** la colonna **Totale** (dove spendo di più) è fuori
  schermo a destra: la tabella è larga 1341 px in uno spazio di 819.
- **Ricavi e Margini:** la tabella arriva ad aprile, **maggio-settembre sono
  nascosti** dietro la colonna Totale fissa, e non si capisce che ci sia altro.
- **Gestione Fatture:** per arrivare a "Questo mese" si scorrono le 414 scadute,
  ~38 schermate. In vista gruppo sono 1.685 righe: **~150 schermate**.

**Perché.** Le sezioni lunghe si aprono tutte, le ripetizioni non sono accorpate,
e le tabelle larghe non danno segnale di continuare.

**Leva:** riorganizzare · **Costo:** <1h per chiudere "Scadute" all'apertura;
mezza giornata per accorpare le righe ripetute in Catena; 1-2 giorni per le
colonne delle tabelle.

**Chi ci perde:** chi apriva Gestione Fatture per lavorare sulle scadute, che avrà
un clic in più. In vista gruppo la stessa modifica probabilmente **rende la pagina
usabile**: l'audit segnala 15 secondi di caricamento e screenshot che fallivano,
compatibile con 2.582 righe disegnate insieme.

> **Da verificare a parte:** quel caricamento e quei fallimenti non sono un
> problema di layout. Se la pagina disegna tutte le righe insieme, è un tema di
> tenuta, non di ordine visivo. Vale un controllo separato.

---

### 5. I riquadri coi numeri si comportano in modo diverso in ogni pagina

**Cosa vede il cliente.** In Gestione Fatture tre riquadri su quattro sono
filtri, ma **niente lo suggerisce** — nessuna freccia, nessun bordo. E cliccandoli
**si sommano**: chi clicca "Scadute" e poi "Questa settimana" ottiene zero
fatture e vede il riquadro rosso andare a "0 €", come se le scadute fossero
sparite. Nella stessa pagina, in vista gruppo, **le pillole delle sedi si
sostituiscono invece di sommarsi**: due comportamenti opposti a pochi centimetri.

Altrove i riquadri non sono cliccabili — giusto — ma alcuni hanno un bordo
luminoso che li fa sembrare selezionati senza motivo ("Da pagare",
"Fatturato netto").

E ci sono cose che sembrano pulsanti e non lo sono: l'etichetta rossa
"⚠ Verifica", "Dati incompleti", le pillole colorate della legenda in Ricavi e
Margini, le barre del grafico "Esposizione futura".

**Leva:** ottimizzare · **Costo:** <1h per rendere evidenti i riquadri-filtro;
mezza giornata per allineare somma/sostituzione.

**Chi ci perde:** chi ha imparato la scorciatoia dei riquadri-filtro — ma continua
a funzionare, diventa solo visibile.

**Da decidere:** i filtri si sommano o si sostituiscono? Oggi l'app fa entrambe
nella stessa pagina. Sostituire è più prevedibile per chi non è tecnologico;
sommare è più potente per chi sa cosa fa.

---

### 6. Sigle e parole che il cliente non può indovinare

L'audit ha provato a indovinarle guardando solo lo schermo. Queste non ci è
riuscito:

| Parola | Dove | Perché è un problema |
|---|---|---|
| **MOL** | ovunque | **49 volte in 12 pagine, spiegato in 2.** Mai in Ricavi e Margini, che è la pagina che lo calcola: né a schermo né dentro "Come funziona" |
| **TD01** | finestra fattura | codice del tracciato fiscale, non serve al cliente |
| **Scostamento medio** | Osservatorio | nessuna idea di cosa misuri |
| **PV** | Catena | **52 volte, mai spiegata.** E convivono tre parole: PV, sede, punto vendita |
| **N°** | Analisi Fatture | numero di cosa? Ruba spazio a Totale |
| **Esposizione futura** | Gestione Fatture | **si contraddice**: la prima barra è "Scadute", cioè il passato |
| **Regole fornitore** | Gestione Fatture | non si capisce cosa regoli |
| **k€** | grafico | "641.6k€" — solo qui; il resto della pagina scrive per esteso |
| **Righe / Solo ripartite** | Analisi Fatture, Home | "righe" di cosa? |
| **per metrica** | Catena | incomprensibile |
| **Tag** | Analisi e Tag | è il nome della pagina, ed è spiegato solo cliccando una "i" |
| **Salute della gestione** | Home | sembra un voto sul tuo lavoro, misura la completezza dei dati |

Più le incoerenze minori: prezzi col punto nelle righe e con la virgola nei
riquadri; "3177 €" senza separatore accanto a "2.915.165 €"; l'unità di misura
mai indicata (7,00 € di zucchine: al kg? a cassa?); il refuso "tueper" in Analisi
e Tag e "spesa cibo. contro" in Catena.

**Leva:** rinominare · **Costo:** <1h per MOL in Ricavi e Margini e per i refusi;
mezza giornata per le sigle ad alta frequenza; 1-2 giorni per il vocabolario
PV/sede/punto vendita.

**Chi ci perde:** nelle tabelle strette di Catena "PV" sta in una colonna e "punto
vendita" no. Soluzione: per esteso alla prima comparsa e nei titoli, sigla nelle
celle.

---

### 7. Rosso e verde dicono cose opposte nella stessa riga

**Cosa vede il cliente.** In Osservatorio un **ribasso** (Astici −29,8%, cioè una
buona notizia) ha pallino e bordo **rossi** con etichetta "critico", e la
percentuale verde. Allarme e via libera insieme.

In Analisi Fatture una riga da verificare ha **tre segnali per la stessa cosa**:
etichetta rossa "Verifica", etichetta verde "Conferma «SERVIZI E CONSULENZE»", e
in colonna "⚠ Scegli categoria" rosso. Il cliente non capisce che **quella verde
è la proposta del sistema, accettabile con un clic** — che è esattamente la cosa
da fare.

In Home il 416.798 € verde gigante convive con cinque triangoli arancioni e un
cerchio rosso al 49%.

**Perché.** Il colore segnala l'*entità* dello scostamento, non se sia buono o
cattivo.

**Leva:** ottimizzare · **Costo:** mezza giornata · **Chi ci perde:** chi usa il
rosso per trovare i casi grossi a prescindere dal segno. Si risolve distinguendo
intensità (grande/piccolo) da direzione (bene/male), senza perdere né l'una né
l'altra.

> **Vincolo:** "Da Classificare" e le righe da verificare **restano visibili** —
> è una regola di dominio. Qui non si propone di nasconderle: si propone di far
> capire cosa farne.

---

### 8. Troppo prima del primo dato

Misurato sull'app vera, finestra 1140 px:

| Pagina | Elementi in alto | Primo dato utile |
|---|---|---|
| Analisi Fatture | **29** (17 sopra la tabella) | ~0,9 schermate — ma i prezzi sono fuori a destra |
| Gestione Fatture | 20 (25 in gruppo) | 1,2 schermate (1,3 in gruppo) |
| Osservatorio | 19, su **9 fasce** | ~1 schermata |
| Analisi e Tag | 12 in alto, 55 in tutto | **subito** |
| Ricavi e Margini | 11 | ~1 schermata |
| Home | 3 visibili, 16 in tutto | subito, ma dopo l'animazione |

**Al primo accesso se ne usano 1 o 2.**

Cosa l'audit toglierebbe, con chi ci perde:

- **Grafico "Esposizione futura"** — ripete i riquadri e si contraddice nel nome.
  *Ci perde chi ha molte fatture a 60-90 giorni.* → mostrarlo solo quando c'è
  qualcosa oltre i 7 giorni.
- **Filtri rapidi** (Tutti/Solo scadute/…) — doppioni dei riquadri. *Ci perde chi
  usa "Questo mese", che non ha un riquadro.* → in un pannello filtri.
- **Esporta, Cestino, Aggiorna** — rari, stesso peso di "Lista". *Ci perde chi
  esporta per il commercialista: un clic in più.* → in un menu "⋯".
- **Riga soglia "Mostra variazioni da 5%"** — *ci perde chi compra grandi volumi,
  dove il 2% pesa.* → in filtri avanzati.
- **Tre dei sei riquadri** di Ricavi e Margini — tenere Fatturato, Costi F&B, MOL.
  *Ci perde chi vuole personale e spese in alto: sono in tabella.*
- **Minigrafici nei riquadri** — senza scala non si leggono. *Ci perde chi vuole
  l'andamento a colpo d'occhio: è già in tabella per mese.*
- **Riquadri "Righe" e "Prodotti diversi"** — *servono al supporto per controllare
  i caricamenti, non al ristoratore.*
- **Le cinque righe ripetute** in Catena → una sola ("5 PV con dati incompleti"),
  più la riga di Paderno che dice una cosa diversa.
- **"Configura assistente"** come prima cosa di Home e Catena — *ci perde il
  cliente appena arrivato.* → visibile solo finché non è configurato.

**Leva:** semplificare · **Costo:** 1-2 giorni per pagina. **È il rilievo più
caro e l'unico che può peggiorare l'app per chi la usa già.** Suggerisco un
pilota su **Osservatorio** (accorpare le 9 fasce in 3-4), la meno rischiosa,
prima di toccare le altre.

---

### 9. Cose piccole, a costo quasi nullo

- **L'animazione che scrive il testo lettera per lettera** in Home costa 5-10
  secondi prima di poter leggere, e spinge "Da fare oggi" sotto la piega. *Ci
  perde chi la trova piacevole — ma la si vede una volta al giorno, e ogni volta
  si aspetta.*
- **"Chiedi a ONEFLUX" copre il contenuto**: nasconde "Vedi coperti" e il valore
  di "Costo personale" in Home, "Tag di catena" e i "Vedi PV" in Catena. Va
  spostato o reso più piccolo.
- **Il periodo non viene ricordato** cambiando scheda in Osservatorio: scelto il
  2025, torni e sei sul 2026. E "Anno in corso" resta acceso mentre è selezionato
  un altro anno.
- **In Osservatorio con il 2025** compare "I prezzi dei tuoi fornitori sono
  stabili nel 2025" — ma per quel cliente il 2025 non ha fatture. **Rassicura su
  dati che non esistono.** <1h, nessuno ci perde.
- **Dieci pagine su dodici** tengono la frase che le spiega dentro un *tooltip*
  sul titolo, invisibile finché non ci passi il mouse. Le frasi sono già scritte e
  sono buone ("Cosa hai comprato, da chi e quanto incide"). <1h per renderle
  visibili. *Ci perde la compattezza:* su Ricavi e Margini, già affollata, una
  riga in più va valutata insieme al punto 8.
- **Il riquadro "I tuoi conti" è scritto al contrario**: il risultato (= MOL) sta
  in cima e gli addendi sotto, mentre un conto a mano si legge dall'alto in basso.
  E il Food cost è in percentuale mentre gli altri sono in euro: **da euro non si
  sottrae una percentuale.**
- **"Tutte le fatture sono al loro posto"** in Catena, detto subito dopo che in
  tutti e 5 i locali mancano fatture. Significa "nessuna fattura nella sede
  sbagliata", ma non si capisce.

---

## La mezza giornata da fare per prima

| Intervento | Costo | Chi ci perde |
|---|---|---|
| Nomi delle sedi visibili in Catena | <1h | nessuno |
| "Scadute" chiusa all'apertura | <1h | un clic a chi ci lavora |
| Niente MOL gigante con dati incompleti | <1h | il numero a colpo d'occhio |
| Spiegare MOL in Ricavi e Margini | <1h | nessuno |
| Riquadri-filtro riconoscibili | <1h | nessuno |
| Niente "prezzi stabili" su un anno senza dati | <1h | nessuno |
| Refusi ("tueper", "spesa cibo. contro") | <1h | nessuno |
| Spostare "Chiedi a ONEFLUX" | <1h | nessuno |

**In una mezza giornata l'app smette di nascondere i nomi delle sedi, smette di
dire "eccellente" sui buchi, e la pagina più pesante si apre in un secondo.**

---

## Quello che sembra facile e non lo è

- **Le divergenze numeriche di Gestione Fatture** (641k vs 430k, 426 vs 414) —
  vanno capite prima di toccarle: potrebbero essere definizioni diverse o bug
  veri. Non è una modifica di etichette.
- **Unificare PV / sede / punto vendita** — 52 occorrenze e parole che in certi
  punti hanno sfumature diverse. Prima si decide il vocabolario, poi si applica.
- **"Sposta in un'altra sede" assente in vista gruppo** — sembra una dimenticanza,
  **è deliberato**: quelle azioni agiscono sulla sede del locale in cui sei, non
  su quella del documento. Il difetto è che non lo dice: va spiegato, non
  "aggiunto".
- **Sistemare Gestione Fatture** — è il file più grande dell'app. Qualsiasi frase
  che comincia così è un progetto, non un ritocco.
- **Aggiungere i confronti ai riquadri di Ricavi e Margini** — i dati arrivano già
  dal server e vengono buttati, ma servono spazio e la gestione del caso "non
  c'è un periodo precedente".

---

## Le divergenze: misurate a database il 16/09/2026

Non sono più ipotesi. Ecco cosa è risultato, sede Villa Guardia.

### "426 su 581" contro 414 righe — **bug vero**

A database le fatture scadute non pagate sono **426**. Di queste **12 sono note
di credito** (1.324,39 €). La lista e i riquadri le escludono giustamente — 426 −
12 = **414**, le righe che vedi. Ma il contatore in alto conta *tutto ciò che
passa il filtro*, note di credito comprese.

**Stessa pagina, due popolazioni diverse, nessuna etichetta che lo dica.**
L'importo invece è corretto: 642.879,07 − 1.324,39 = 641.554,68 ≈ i 641.555 € a
schermo. **Costo: <1h.**

### 641.555 € di scaduto — **non è un bug**

Sono fatture reali mai segnate come pagate (confermato da te). Il numero è
giusto; è l'app che lo presenta come allarme. Non si tocca il calcolo: semmai si
decide come mostrarlo.

### Home: 447.728 − 0 − 0 − 0 = 416.798 — **non è un bug, ma è illeggibile**

Misurato su agosto: **lordo 447.728,44**, **netto 416.798,11**. Le due cifre
esatte viste a schermo. La card mostra in cima il fatturato **lordo IVA** e in
fondo un MOL calcolato sul **netto**, con in mezzo tre sottrazioni da zero.

Lo scarto di **30.930 € è l'IVA scorporata**, che non è scritta da nessuna parte.
Il conto non torna a chi prova a farlo a mente — ed è la cosa che il cliente
vede per prima ogni mattina. **Costo: <1h** (dichiarare la base).

### Margine Villa Guardia 39% / 68% / 100% — **tutti e tre corretti**

Tre periodi diversi, nessuno dichiarato:

| Dove | Valore | Periodo |
|---|---|---|
| Catena | 39% | ultimi mesi completi (mag 39,2%, giu 39,3%) |
| Ricavi e Margini | 68% | media gen-set, **mesi vuoti inclusi** |
| Home | 100% | agosto, dove costi e personale sono a zero |

Il margine ricostruito mese per mese:

| Mese | Netto | Costi F&B | Spese | Personale | MOL % |
|---|---|---|---|---|---|
| gen | 392.806 | **0** | **0** | 60.000 | 84,7% |
| feb | 358.677 | **0** | **0** | 60.000 | 83,3% |
| mar | 405.016 | 37.777 | 1.734 | 60.000 | 75,4% |
| **apr** | 361.181 | 133.473 | 41.800 | 60.000 | **34,9%** |
| **mag** | 393.422 | 153.429 | 25.932 | 60.000 | **39,2%** |
| **giu** | 375.963 | 128.889 | 39.179 | 60.000 | **39,3%** |
| lug | 373.626 | 86.404 | 42.452 | **0** | 65,5% |
| ago | 416.798 | **0** | **0** | **0** | 100,0% |
| set | 186.476 | **0** | **0** | **0** | 100,0% |

**Solo aprile, maggio e giugno hanno dati completi: il margine vero è ~35-39%.**
Il personale sparisce da luglio; costi merce assenti a gennaio, febbraio, agosto
e settembre.

> **La conseguenza che conta:** il 68% mostrato in Ricavi e Margini è una media
> che mescola mesi reali e mesi vuoti — **il numero più grande dell'app è il meno
> affidabile dei tre**. La Catena, che usa i mesi completi, dà l'unica cifra
> giusta. Non serve cambiare il calcolo: serve escludere i mesi incompleti dalla
> media, o dire su quali mesi è fatta.

### Note di credito sui margini — **nessun bug**

Sono salvate con importo positivo ma hanno `segno_compensazione = -1`: vengono
sottratte correttamente. Era il rischio peggiore, ed è escluso.

---

## Restano da verificare

1. **I 15 secondi e gli screenshot falliti** in vista gruppo: tenuta della pagina
   con 2.582 righe.
2. **Paderno Dugnano** ha 0 su tutto e sembra non ancora avviato: se è così entra
   nella "media 5 sedi" e nei confronti del gruppo, abbassandoli.
3. **La bevanda a −97,1%** e altri prezzi anomali: errore di lettura del dato?
4. **101 prodotti / 19.050 €** in Analisi Fatture contro **100 / 582 €** in Home.
5. **"2.582 fatture totali" vs "Seleziona tutte (2.545)"** in vista gruppo —
   probabilmente la stessa causa del contatore 426/414.
6. **Il giorno 1** non è stato misurato: l'account era pieno.

---

## Appendice — le misure

**Dal codice** (`apps/web/src/`, verificate il 16/09/2026):

- Nome sede in Catena: unico elemento della riga senza protezione dal
  restringimento — `sintesi-catena.tsx:413`.
- "Costi Gestione": `kpi-bar.tsx:128` mostra le sole spese generali;
  `calcolo-tab.tsx:914` somma spese + personale.
- "Esposizione futura": la prima fascia è "Scadute" (`lib/scadenziario.ts`,
  `buildCashFlow`) — il titolo dice futuro, la barra principale è passato.
- `k€`: formattazione presente solo in quel grafico.
- "Sposta sede"/"Ripartisci" nascoste in vista gruppo: scelta documentata nel
  codice (`scadenziario-client.tsx`, commento a `PeekDialogProps`).
- MOL: 49 occorrenze in 12 file cliente, spiegato in 2 (`kpi-block.tsx:196`,
  `finestra-margini-coperti.tsx:64`).
- Frase esplicativa nascosta nel tooltip: 10 pagine su 12.
- Ordine verticale: Analisi Fatture e Ricavi e Margini mettono i riquadri
  **sopra** le schede; Osservatorio no — ed è la struttura migliore delle tre.

**Dall'audit sull'app** (16/09/2026, finestra 1140×636/672, account SUSHILAND):
conteggi degli elementi, schermate di scorrimento, comportamento dei filtri e
tempi di caricamento come riportati nelle tabelle sopra. I conteggi includono
elementi che l'utente non percepisce come decisioni (intestazioni ordinabili,
"X" di rimozione): il numero percepito è più basso.

---
---

# PARTE 2 — Come appare l'app

*Secondo audit, 16/09/2026 pomeriggio, tema scuro, finestra 1140×672. Qui non si
guarda cosa c'è scritto ma **come appare**: colore, spazio, cornici, tipografia.*

## La prova, in una tabella

A ogni pagina è stato chiesto un voto: **quanto sembra complicata al primo
sguardo**, da 1 (semplicissima) a 10 (respingente).

| Pagina | Voto | In una frase |
|---|---|---|
| **Gestione Fatture** | **8** | Una bacheca di allarmi seguita da un muro rosso senza fine |
| **Ricavi e Margini** | **7** | Sei riquadri arcobaleno sopra un foglio di calcolo fitto |
| **Analisi Fatture** | **7** | Sopra un pannello da tecnico, sotto nomi senza numeri |
| **Osservatorio** | **7** | Un terminale di borsa: cifre rosse e verdi che gridano insieme |
| **Home** | **6** | Un tema da leggere, poi avvisi ovunque e un numero verde che li smentisce |
| **Catena** | **5** | La più leggera, ma il riquadro chiave non dice di quale sede parla |

**Media 6,7. Nessuna pagina sotto il 5.** Su tutte e sei la risposta alla domanda
*"sembra uno strumento semplice o complicato?"* è stata **complicato**.

> La sensazione che avevi è confermata. Non è un'impressione: è misurata su sei
> schermate, da chi guardava l'app per la prima volta.

---

## La causa numero uno: il colore decora invece di informare

È il filo che lega tutte e sei le pagine, ed è anche la cosa più economica da
correggere — si tolgono colori, non si riscrive nulla.

**Il sintomo più evidente.** I sei riquadri di Ricavi e Margini hanno sei colori
diversi: azzurro, arancione, verde, viola, rosa. Il giudizio è stato *"un
arcobaleno, non un sistema"*. Una regola in realtà c'è — il colore indica la
famiglia di voci, e la tabella la rispetta — ma non si capisce senza leggere la
legenda. E si rompe in tre punti: l'azzurro vuol dire sia "ricavi" sia
"cliccabile"; **Margine lordo e MOL hanno lo stesso identico verde**, quindi
sembrano la stessa cosa; e il verde non significa "va bene", perché il MOL è
verde anche quando mancano i costi.

**Lo stesso colore cambia senso da pagina a pagina:** il rosa è "scadute" in
Gestione Fatture e "personale" in Ricavi e Margini; l'arancione è "avviso" in
Home e "costi F&B" in Margini.

**E cambia senso dentro la stessa riga.** In Osservatorio il rosso a sinistra
(striscia, pallino) vuol dire *"variazione importante"*, mentre al centro
(percentuale) vuol dire *"prezzo aumentato"*. Risultato: una riga con striscia
rossa e numero verde. L'audit: *«il segnale rosso e quello verde si annullano»*.

**Cosa toglierebbe**, pagina per pagina — tutte modifiche di sola apparenza:

| Pagina | Colore da togliere | Cosa resta colorato |
|---|---|---|
| Ricavi e Margini | bordi e numeri dei sei riquadri | solo il MOL |
| Osservatorio | percentuali grandi e minigrafici | solo l'impatto in euro |
| Gestione Fatture | cornice rossa di ogni riga, etichetta azzurra "da fattura" | la data di scadenza |
| Analisi Fatture | riquadri Righe, Prodotti diversi, Media al mese | solo Spesa totale |
| Home e Catena | sfondi tinti rosso e verde delle card grandi | i numeri |

**Chi ci perde:** chi collegava il colore del riquadro a quello della riga in
tabella perde un aggancio visivo — ma i nomi sono identici, quindi il legame
resta. In Osservatorio chi scorreva cercando "i rossi" continua a trovarli
nell'impatto in euro, che dice la stessa cosa in modo più utile.

**Costo:** mezza giornata in tutto. **È l'intervento con più resa del documento.**

---

## I riquadri mostrano numeri falsi mentre caricano

**Cosa succede.** Su Ricavi e Margini, in tre aperture su tre, i sei riquadri
mostrano prima **"0 €" ovunque** — in un caso per **oltre 30 secondi**, mentre la
tabella sotto era già piena di cifre. Nelle altre due sono passati per valori
intermedi: *"Fatturato netto 396.025 €"*, poi *"257.307 €"*, poi il vero
3.263.965 €.

Lo stesso su Gestione Fatture ("Scadute 77.194 €" prima dei 641.555 € reali) e su
Analisi Fatture (9.091 € → 385.211 € → 691.766 €).

**Perché.** Verificato, ed è **metà causa deliberata**: i riquadri hanno
un'animazione che fa salire ogni numero da zero al valore vero in mezzo secondo.
Elegante su dati veloci; su dati lenti si somma all'attesa del server e il
cliente **legge cifre che non esistono**. L'animazione rispetta già le preferenze
di chi chiede meno movimento, quindi la struttura per spegnerla c'è.

Il tempo di attesa è l'altra metà, e non è grafica: ~25 secondi su Osservatorio
(con **due scheletri grigi diversi in sequenza**, e un salto di larghezza fra lo
scheletro e la pagina vera), ~15 secondi in vista gruppo.

**Chi ci perde:** nessuno. L'animazione è un vezzo, non un'informazione.

**Costo:** <1h non animare finché il dato non è arrivato. **I tempi di attesa
sono un tema tecnico separato**, non risolvibile con la grafica.

> È la **prima cosa che il cliente vede ogni giorno**. Prima di ogni ragionamento
> sui colori, l'app dovrebbe smettere di mostrare numeri sbagliati.

---

## La tabella di Analisi Fatture sembra rotta

**Cosa vede il cliente.** Le colonne finiscono **tagliate nette sul bordo destro**
("For…"), senza ombra, sfumatura o freccia che dica che c'è dell'altro. Il
giudizio: *«sembra che la tabella finisca lì, con un difetto di impaginazione»*.

Aggravante verificata nel codice: la barra di scorrimento orizzontale esiste, ma
**sta in fondo alla tabella, dopo 1798 righe**. Dalla parte alta è invisibile.

Nel frattempo, dentro la riga, ci sono **~350 px di vuoto** fra la descrizione e
la categoria — mentre le colonne che servono (€ medio, Totale) stanno fuori
schermo. Lo spazio c'è, è solo distribuito male.

**Chi ci perde:** chi legge descrizioni prodotto molto lunghe per intero — ma
oggi sono troncate comunque.

**Costo:** mezza giornata. **Con un solo effetto: i prezzi entrano nello schermo.**

---

## Le altre cose viste, in ordine di resa

**Il maiuscolo grida.** In Analisi Fatture le descrizioni prodotto sono **tutte
maiuscole, grassetto, bianche**: *«in tabella il dato grida più dei titoli»*.
Arrivano così dalle fatture elettroniche, ma si possono mostrare in minuscolo
senza toccare il dato. *Ci perde chi confronta parola per parola con la fattura
cartacea — poco.* **Mezza giornata.**

**Cornici dentro cornici.** Gestione Fatture ne ha **tre livelli**: la card della
sezione, dentro una cornice per ogni riga, dentro le etichette. Con centinaia di
righe scadute ognuna con la **sua cornice rossa**, l'effetto è *«un muro rosso
senza fine»*. Togliere la cornice alle righe — lasciando la data rossa e il
titolo della sezione — è **l'intervento singolo più efficace della pagina più
pesante dell'app**. *Chi ci perde: nessuno.* **<1h.**

**Cinque o sei stili di pulsante per pagina.** Pillola piena, pillola a contorno,
selettore a segmenti, rettangolo a contorno, link azzurro, menu nero. Su Analisi
Fatture sono sei. Non è grave da solo, ma è il motivo per cui le pagine sembrano
*«strati accumulati, aggiunti uno alla volta»*. **1-2 giorni**, da fare una volta
per tutte le pagine.

**Colonne che ondulano.** In Osservatorio le etichette dentro le righe si
spostano di 20-40 px da una riga all'altra a seconda della lunghezza delle cifre:
le colonne non stanno in fila. Inoltre **"MEDIA PERIODO / PENULTIMO / ULTIMO"
sono ripetute dentro ognuna delle 76 righe**, invece di stare una volta sola in
cima. Toglierle e allineare le colonne: *nessuno ci perde.* **Mezza giornata.**

**Sette-nove dimensioni di testo per pagina**, e testo troppo piccolo per un
cinquantenne: le percentuali sotto le cifre in Margini (~12 px grigie), le
etichette dei riquadri (~11 px maiuscole grigie), "414 fatture" sotto i numeri.
**Mezza giornata** per ridurle a quattro.

**Il riquadro dell'assistente occupa tutto il primo schermo** della Home, con un
testo che ripete le card sottostanti. *Ci perde chi legge solo il testo — ma le
stesse cose sono nelle card, e l'audio resta intero.* **<1h** ridurlo a 2-3 righe
con "leggi tutto".

**Diciotto segnali di allarme in Home.** Contati: 3 triangoli arancioni, 1 cerchio
rosso, 1 emoji ⚠️, campanella con badge, sfondo rosso, cerchio 49%, etichetta
"Dati incompleti", 3 pallini arancioni, riquadro ambra, 3 pallini gialli, frase
arancione. *«Danno la sensazione che sia tutto rotto»* — e accanto c'è un numero
verde gigante che dice il contrario.

**Il blocco "GRUPPO" in Catena è mezzo vuoto.** L'audit ha notato che rispetto al
mattino una delle due schede è sparita (probabilmente un tuo rilascio), lasciando
una scheda a metà larghezza e l'altra metà vuota: *«rompe il ritmo e fa sembrare
la pagina incompiuta»*. Soluzione: farne la quarta scheda della fila sotto.
**<1h.**

---

## Il tema chiaro si legge meglio di quello scuro

Verificato cambiando tema:

- **La tabella di Ricavi e Margini si legge meglio in chiaro**: righe più nette,
  numeri più riposanti. Nello scuro i numeri colorati *«sembrano al neon e
  stancano»*, e i grigi (percentuali, lucchetti, trattini) si confondono col fondo.
- **In chiaro i riquadri sono più leggeri** e sembrano meno un arcobaleno.
- **Difetto del chiaro:** lucchetti e percentuali colorate quasi invisibili.
- **In entrambi i temi** non si distingue quali celle sono modificabili — e
  **nel tema chiaro la frase "modifica le righe in bianco" non vuol dire niente,
  perché sono tutte bianche.**

Non propongo di cambiare il tema di default: propongo di **rendere visibili le
celle modificabili**, che è il difetto vero, presente in entrambi. **Mezza
giornata.**

> **Nota:** per rispondere a questa domanda l'audit ha cambiato il tema
> sull'account del cliente — è una preferenza salvata su tutti i dispositivi. È
> stato rimesso su scuro e verificato. Colpa del prompt, che non l'aveva escluso.

---

## La mezza giornata visiva

Tutti interventi di sola apparenza: **nessuna funzione tolta.**

| Intervento | Costo | Chi ci perde |
|---|---|---|
| Togliere la cornice rossa alle righe di Gestione Fatture | <1h | nessuno |
| Non animare i numeri finché il dato non è arrivato | <1h | nessuno |
| Riquadri di Margini grigi, colore solo sul MOL | <1h | un aggancio visivo con la tabella |
| Osservatorio: colore solo sull'impatto in euro | <1h | chi cercava "i rossi" |
| Togliere gli sfondi tinti alle card di Home e Catena | <1h | nessuno |
| Grigi i riquadri Righe / Prodotti diversi / Media al mese | <1h | nessuno |
| "Costi di gruppo" come quarta scheda in Catena | <1h | nessuno |

**Effetto atteso:** le due pagine più pesanti (voto 8 e 7) perdono il muro rosso e
l'arcobaleno, e l'app smette di mostrare numeri falsi in apertura. Nessuna
funzione sparisce.

Restano fuori, perché più cari: la tabella di Analisi Fatture (mezza giornata), il
maiuscolo delle descrizioni (mezza giornata), l'uniformità dei pulsanti (1-2
giorni).

---

## Da verificare — Parte 2

1. **I tempi di attesa**: 25 secondi su Osservatorio con due scheletri diversi, 15
   in vista gruppo, 30 con i riquadri a zero su Margini. Non è grafica.
2. **Il salto di larghezza** fra lo scheletro di caricamento e la pagina vera in
   Osservatorio.
3. **Una sede con 49 ha il pallino rosso e una con 50 ce l'ha arancione**: il
   colore arriva già deciso dal server, quindi la soglia sta lì. Da guardare
   perché un punto di differenza cambi colore.
4. **L'etichetta "da fattura"**: prima di toglierle colore, verificare quali altri
   valori può assumere.

## Appendice — Parte 2, verifiche nel codice

- **Numeri animati:** `useCountUp`, `margini/kpi-bar.tsx:88-113` — sale da 0 al
  valore in 500 ms; rispetta già `prefers-reduced-motion`.
- **Tabella tagliata:** `overflow-x-auto` su contenitore unico,
  `analisi-fatture/articoli-tab.tsx:422` — la barra nasce in fondo all'elemento,
  cioè sotto tutte le righe.
- **Palette salute:** `lib/salute-tint.ts` — una sola palette condivisa fra Home e
  catena, ben tenuta; le soglie di colore arrivano dal server.
- **Voti e descrizioni visive:** audit del 16/09/2026 pomeriggio, tema scuro,
  finestra 1140×672. Le dimensioni del testo sono stime a occhio.
