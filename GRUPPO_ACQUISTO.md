# 🤝 ONEFLUX — Gruppo d'Acquisto Automatico
*Concept — sessione pianificazione 8 luglio 2026, Mattia D'Avolio, Recoma System srl*

## L'idea in una frase
OneFlux conosce già, dalle fatture SDI, quanto comprano i suoi clienti, cosa,
a che prezzo e con che frequenza. Questa domanda aggregata — mai dichiarata
da nessun cliente, solo dedotta dai dati — diventa leva negoziale verso i
fornitori: "i miei N ristoranti comprano insieme X quantità al mese di
[prodotto], oggi a prezzo medio Y — che offerta fai al gruppo?"

## Perché non è un altro Soplaya
OneFlux non tocca ordini, logistica, consegne, fatturazione dell'acquisto.
Aggrega la domanda e porta l'accordo; l'ordine corre poi direttamente tra
ristorante e fornitore come sempre avviene oggi. Il ruolo resta quello di
segnalatore/negoziatore, mai quello di centrale d'acquisto o rivenditore.
**Questo confine non va spostato senza discuterne esplicitamente** — è la
differenza tra restare un software e diventare un'altra azienda.

## Perché è potenzialmente il differenziante forte
- L'asset (i dati aggregati di acquisto reali) non è replicabile da un
  competitor che nasce oggi: richiede una base clienti già in produzione
- Effetto rete a due lati: più ristoranti → più potere contrattuale → offerte
  migliori → più ristoranti attratti. Il fornitore partecipa perché vede
  volume vero, non una vetrina vuota da popolare
- Il servizio "si ripaga da solo" nel discorso commerciale: se il gruppo fa
  risparmiare più dell'abbonamento, il prezzo dell'app diventa un dettaglio

## Componenti tecniche (ex punti D, E, F della roadmap precedente)

### Componente 1 — Normalizzazione prodotti cross-cliente (ex punto D)
Motore della domanda: riconoscere che descrizioni diverse tra fornitori/
clienti sono lo stesso prodotto, per poterne sommare i volumi.

**Approccio a rischio contenuto:** non serve normalizzare tutto. Priorità a
due segnali affidabili:
1. Stesso `CodiceArticolo` XML + stesso fornitore tra clienti diversi → match
   certo al 100%, zero interpretazione
2. Commodity ad alto volume e bassa ambiguità descrittiva (da individuare
   nella fase di validazione, vedi sotto) — non prodotti freschi o articoli
   con nomi molto variabili tra fornitori

Coerente con la regola "poche ma buone": meglio un benchmark affidabile su
30-40 prodotti commodity che uno su 500 con metà dei match sbagliati.

### Componente 2 — Bacheca/canale offerte (ex punto E)
Non un marketplace da popolare a freddo. È il punto di atterraggio, dentro
l'app, delle offerte negoziate nella Fase 2/3 sotto: una card contestuale
(riuso del meccanismo trigger già esistente in `/assistenza`) che compare
quando c'è un'offerta reale per quel cliente specifico, personalizzata sul
suo consumo — "sul fior di latte il gruppo ha un prezzo a -11%, in base ai
tuoi consumi risparmi circa €X/mese".

### Componente 3 — Clausola ToS uso aggregato/anonimizzato (ex punto F)
Prerequisito legale condiviso con il benchmark KPI (vedi IMPLEMENTAZIONI.md
punto 3). Necessaria prima di iniziare ad accumulare la fondazione, così i
dati raccolti sono coperti fin dall'inizio. Punti chiave (verifica legale
prima del lancio, non sono un avvocato):
- Clausola nei Termini di Servizio che autorizza l'uso dei dati in forma
  aggregata e anonimizzata per statistiche/benchmark e per negoziazioni di
  gruppo
- Soglia minima di aggregazione (proposta: almeno 5 clienti dietro ogni dato
  mostrato), per impedire che si risalga al prezzo di un singolo cliente/
  fornitore
- Mai esporre nomi di fornitori o clienti nel dato aggregato, solo medie/
  volumi anonimi

## Percorso in 4 fasi — in ordine di rischio crescente

### Fase 1 — Validazione manuale, zero codice (PRIMA DI TUTTO)
**Obiettivo: scoprire se il mercato risponde, prima di costruire qualunque
cosa.** Al momento non è stata ancora individuata la commodity né i
fornitori per il test — è la primissima cosa da fare, non un dettaglio da
rimandare.

Passi concreti:
1. Scegliere 1 commodity candidata (ipotesi di partenza da verificare: un
   prodotto secco, alto volume, bassa differenziazione — es. olio, farina,
   scatolame, oppure non-food come detergenti/monouso; da confermare o
   smentire con i dati reali dei clienti attuali)
2. Estrarre a mano il volume aggregato mensile di quella commodity tra i
   clienti attuali (query diretta su Supabase, nessuna feature da costruire)
3. Contattare 2-3 fornitori con quel volume in mano: chiedere se e quanto si
   muove il prezzo
4. **Gate esplicito:** se nessun fornitore muove il prezzo in modo
   significativo, l'idea si ridimensiona o si abbandona per quella
   commodity — si prova un'altra categoria, non si passa alla Fase 2 a
   prescindere

### Fase 2 — Pilota manuale con i clienti
Solo se la Fase 1 dà un segnale positivo. Si porta l'offerta negoziata ai
clienti coinvolti a voce o via messaggio (non ancora in-app), si misura
quanti aderiscono davvero. Verifica che anche il lato domanda risponda, non
solo quello dell'offerta.

### Fase 3 — Prima automazione (solo dopo 1-2 pilota riusciti)
- Componente 1 (normalizzazione) applicata alla commodity validata
- Componente 2 (card offerta contestuale) per mostrarla in app
- Ancora nessun pannello self-service per i fornitori: le offerte le porta
  Matt/il team, il software le distribuisce e misura l'adesione

### Fase 4 — Pannello fornitore self-service (molto più avanti)
Da costruire solo se il volume di offerte gestite manualmente lo giustifica.
Prematuro oggi.

## Ruolo di OneFlux verso i fornitori — decisione presa
Tre modelli possibili, rischio crescente: segnalatore (commissione su
segnalato, zero responsabilità operativa) → negoziatore di gruppo (contratti
quadro, più lavoro) → broker/centrale (si entra nella transazione, diventa
un'altra azienda — **da evitare**).

Decisione attuale: **si parte come segnalatore, senza modello di guadagno
definito nell'immediato.** Priorità ora è costruire un buon servizio
automatizzato; la monetizzazione (commissione, quota fissa, o nessuna nel
breve termine) si valuta in un secondo momento, quando il servizio avrà
dimostrato di funzionare. Da tenere presente: "automatizzato" è l'obiettivo a
regime della Fase 3-4, non il punto di partenza — la Fase 1 è
intenzionalmente manuale, perché è il modo più economico di scoprire se il
mercato risponde prima di investire in sviluppo.

## Rischi aperti, da monitorare
- **Conflitto con fornitori esistenti dei clienti:** se un fornitore storico
  percepisce che OneFlux dirotta volume verso un concorrente, può
  irrigidirsi — anche sulla qualità/puntualità dell'invio fatture. Va gestito
  con trasparenza: il gruppo d'acquisto è opt-in, un'opportunità aggiuntiva,
  mai una sostituzione imposta
- **Massa critica geografica:** serve una base clienti sufficiente per area
  perché il volume aggregato sia interessante per un fornitore — soglia da
  verificare nella Fase 1 stessa, non solo a priori
- **Lavoro operativo non software:** le Fasi 1-3 richiedono tempo di
  negoziazione umana (telefonate, trattative) — non è un costo di sviluppo,
  è un costo di tempo di Matt/del team, da mettere in conto separatamente
  dalle stime tecniche

## Prossima azione concreta
Nessun brief tecnico da questo documento è pronto per Claude Code oggi: il
passo successivo è **fuori dall'app** — individuare la commodity candidata e
fare le prime 2-3 telefonate di validazione (Fase 1). Il documento va
aggiornato con l'esito prima di procedere alla Fase 3.
