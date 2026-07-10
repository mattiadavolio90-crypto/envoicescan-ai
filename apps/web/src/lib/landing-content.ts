// Contenuti della landing pubblica scrollytelling (route "/"). Tutto il copy vive
// qui: per cambiare testi, immagini, sequenza chat o piani si tocca SOLO questo file.
//
// Impianto (brief giugno 2026, validato): landing a SCENE a tutto schermo, una alla
// volta, reveal-on-scroll. Tono misterioso ma sicuro. Ogni scena fa UNA promessa,
// non spiega una funzione. La parola "AI" quasi mai: la sensazione di AI ovunque.
// Doppio cuore: LUI ti parla (briefing) + TU gli parli (chat). Le automazioni sono
// la PROVA, non l'eroe. Le immagini sono screenshot reali in /public/landing/.

export const LANDING = {
  nav: {
    accediLabel: "Accedi",
    accediHref: "/login",
    // Demo interattiva pubblica (route-group (demo)): CTA PRIMARIA dell'hero
    // (audit CRO 10/07). È il passo a frizione più bassa del funnel e fa il
    // selling pesante (il bottino 220€): bottone vero centrato, non più pill
    // nell'angolo. "(1 minuto)" dichiara il costo in tempo: abbassa la soglia
    // d'ingresso più di qualsiasi copy persuasivo.
    demoLabel: "Guarda la demo (1 minuto)",
    demoHref: "/demo",
    // Via secondaria sotto il bottone demo, per chi vuole subito il contatto.
    demoAltWhatsapp: "oppure scrivici su WhatsApp",
  },

  // CTA prova gratuita reale (campi trial_active/trial_activated_at nel DB).
  // nota/nota2: risk reversal + canale nella lingua del target (il ristoratore
  // ordina dai fornitori su WhatsApp: il canale è comfort zone, non ripiego).
  // "si disdice con un messaggio" confermato da Mattia (10/07): dev'essere vero.
  cta: {
    label: "Inizia ora, 7 giorni gratis",
    nota: "Senza carta, senza obblighi · si disdice con un messaggio",
    nota2: "Ci scrivi come scrivi a un fornitore — risponde una persona vera",
    // Attivazione via WhatsApp: l'account lo configura Mattia.
  },

  // --- SCENE -----------------------------------------------------------------
  // Ogni scena: kicker (occhiello), titolo (1 frase), sotto (1 frase). `bg` =
  // sfondo sfocato atmosferico (mostra una pagina che il testo NON nomina);
  // `hero` = screenshot nitido protagonista su nero pulito.
  // Struttura a 8 scene (rettifica 2): 0=aggancio+specchio FUSE; automazioni
  // SDOPPIATE in 3=categorizzazione + 4=alert prezzi; 5=potere mobile (2 colonne).
  // Regola tipografica: NIENTE punto a fine frase (solo come stacco nei titoli doppi).
  // Kicker blu su tutte le scene 1–6; la scena 0 sta NUDA (nessun kicker).
  scene: {
    // SCENA 0 — Aggancio + Specchio (FUSE). Niente kicker: è l'apertura.
    // Gerarchia invertita (audit CRO 10/07): il BENEFICIO sta nell'h1 (controllo
    // + rimozione del dolore "contabile"), la frase aspirazionale scende a
    // sottotitolo. L'h1 precedente ("Un nuovo modo di pensare...") era una
    // frase-template: nessuna categoria, nessun beneficio.
    aggancio: {
      bg: "/landing/bg-marginalita.png",
      title: "Il tuo locale sotto controllo.\nSenza diventare un contabile",
      sotto: "Un nuovo modo di pensare alla gestione",
      sotto2: "Ai dati pensa OneFlux\nsi adatta a te, non il contrario",
      scrollHint: "scorri",
    },

    // SCENA 1 — Lui ti parla (briefing · PRIMO CUORE).
    // Testi generici di proposito: NON promettere numeri specifici (dipendono dai dati).
    briefing: {
      hero: "/landing/hero-briefing.png",
      kicker: "Il buongiorno",
      title: "Ogni giorno ti dice come sta andando. Prima che tu lo chieda",
      sotto: "Cosa è cambiato, cosa controllare, dove serve attenzione, confrontato con il tuo andamento",
    },

    // SCENA 2 — Tu gli parli (chat · SECONDO CUORE · la rivelazione)
    chat: {
      hero: "/landing/hero-chat.png",
      kicker: "Quando vuoi",
      title: "Glielo chiedi. E ti risponde",
      sotto: "Quando vuoi sapere come va, glielo chiedi e lui risponde: è il tuo assistente",
      // Sequenza reale dell'app. I messaggi compaiono UNO ALLA VOLTA, con ritardo
      // e indicatore "sta scrivendo": il wow è nel ritmo, non nella grafica.
      // `censura`: porzione del testo da oscurare (dato sensibile = nome fornitore),
      // stesso trattamento dei nomi nella slide prezzi. Il componente la rende come
      // barretta sfocata/oscurata al posto del testo.
      // Branzino (non salmone): il salmone è il filo narrativo della DEMO con
      // prezzi diversi (18,90→21,90 €/kg) — chi fa landing→demo non deve trovare
      // lo stesso pesce a due prezzi.
      sequenza: [
        { da: "ai", testo: "Il branzino è costato € 14,90/kg, comprato il 27/05 da ", censura: "ADC", coda: "." },
        { da: "user", testo: "Pensi che vada bene come prezzo di acquisto?" },
        {
          da: "ai",
          testo:
            "Posso confrontarlo con i prezzi degli ultimi 6 mesi dai fornitori. Vuoi che faccia il confronto?",
        },
      ],
    },

    // SCENA 3 — Categorizzazione (automazioni, prima metà). Immagine pulita: solo
    // descrizione + categoria, niente prezzi/fornitori.
    categorie: {
      hero: "/landing/hero-categorie.png",
      kicker: "Nel frattempo",
      title: "I dati entrano da soli",
      sotto:
        "Le tue fatture di acquisto arrivano in automatico e l'assistente le legge e le categorizza: migliaia di prodotti, in ordine da soli",
      // chiusura sotto l'immagine: il ribaltamento concreto (niente data entry).
      // "automatizzato" parola-chiave azzurra (gestita nel componente).
      chiusura: "Niente magazzino, niente anagrafiche, niente ore al computer: tutto automatizzato",
    },

    // SCENA 4 — Alert prezzi (automazioni, seconda metà).
    // È la promessa più "a guardia" del ristoratore: il rincaro che passa
    // inosservato è soldi persi. Tono più diretto, secondo riga che chiude il colpo.
    prezzi: {
      hero: "/landing/hero-prezzi.png",
      kicker: "E se qualcosa cambia",
      title: "Un fornitore alza i prezzi.\nLo sai prima di pagare",
      sotto: "OneFlux confronta ogni fattura con lo storico e ti avvisa quando un costo sale, e quanto impatta sulla gestione",
    },

    // SCENA 5 — Il potere (mobile). LAYOUT 2 COLONNE: testo sx, telefono dx (verticale).
    // Chat su tema gestione (diversa dalla scena 2 sul salmone): niente ridondanza.
    potere: {
      heroMobile: "/landing/hero-mobile.jpeg",
      kicker: "Ovunque",
      title: "Da dove vuoi. Anche fuori dal locale",
      sotto: "In sala, dal fornitore, sul divano: ti risponde dove sei tu, come un consulente, sempre a portata di mano",
    },

    // SCENA 6 — L'invito + rivelazione (hero-conti: tutto verde, salute 100%)
    invito: {
      hero: "/landing/hero-conti.png",
      kicker: "Provalo",
      title: "E questo è solo l'inizio",
      sotto: "Provalo sul tuo locale, adesso",
      firma: "La tecnologia che la tua gestione aspettava",
    },
  },

  // --- SCENA 7 — Piani (fondo pagina, minimal) -------------------------------
  // Numeri reali dal prodotto: fatture/mese 50/100/200 (confermati da Mattia),
  // prezzi 39/59/79 +IVA. Crediti AI/mese: cifra grande che comunica potenza, con
  // riferimento concreto piccolo sotto (~10/20/30 richieste/giorno). Termine
  // "crediti AI" (NON "token"). Cifre tonde mappate da 10/20/30 domande/giorno.
  piani: {
    title: "Tutto incluso, in ogni piano",
    // Nessun piano "consigliato": tutti full optional, cambia solo il volume.
    sottotitolo:
      "Ogni piano ha tutte le funzioni e il tuo assistente sempre attivo. Cambia solo il volume di fatture e crediti: scegli in base alla dimensione del tuo locale.",
    // Voci con spunta blu (uguali per tutti, mostrate in ogni card): fatture,
    // crediti, SDI, check-up. `creditiNota` NON è una spunta: è la spiegazione
    // piccola sotto la riga crediti (quanti crediti ≈ quante richieste/giorno).
    lista: [
      { nome: "Base", prezzo: "39€", fatture: "Fino a 50 fatture / mese", crediti: "1.000 crediti AI / mese", creditiNota: "~10 richieste al giorno" },
      { nome: "Plus", prezzo: "59€", fatture: "Fino a 100 fatture / mese", crediti: "2.000 crediti AI / mese", creditiNota: "~20 richieste al giorno" },
      { nome: "Pro", prezzo: "79€", fatture: "Fino a 200 fatture / mese", crediti: "3.000 crediti AI / mese", creditiNota: "~30 richieste al giorno" },
    ],
    // Voci uguali in ogni piano (oltre a fatture/crediti).
    sdi: "Ricezione fatture via SDI inclusa",
    checkup: "1 check-up gratuito dopo il primo mese",
    checkupDettaglio: "maggiori dettagli in Servizi",
    iva: "+IVA",
    // Riga catena sul dolore vero del multi-sede: non essere più in ogni locale.
    catena: "Più locali? Tutte le sedi confrontate in un colpo d'occhio, anche da casa — modalità catena, su ogni piano",
    // chiarimento sotto la riga catena: i prezzi sono per singola sede.
    perPuntoVendita: "I prezzi esposti sono per punto vendita",
    // Attivazione in 3 passi sopra la CTA finale: ammazza l'obiezione "sarà
    // complicato / non sono capace" nel momento esatto in cui riaffiora.
    attivazione: [
      "Ci scrivi su WhatsApp",
      "Colleghiamo noi le tue fatture, tu non configuri niente",
      "Domani mattina hai il primo briefing",
    ],
    // Trust signal GDPR (lavoro compliance già fatto, qui solo esposto).
    trust: "I tuoi dati restano tuoi · GDPR · server in UE",
    // Invito alla demo prima delle card: gradino a bassa frizione. Tono POSITIVO
    // (mai "non sei sicuro?", che pianta un dubbio dove vuoi la scelta): invita a
    // vederlo dal vivo. Ripete il "1 minuto" dell'hero — dichiara il costo in
    // tempo e abbassa la soglia più di qualsiasi copy persuasivo.
    demoNota: "Guardalo in azione, ti basta 1 minuto",
  },

  // --- Sezione SERVIZI (pubblica) -------------------------------------------
  // Fonte unica = catalogo `SERVIZI` in lib/assistenza.ts (stesso dell'app):
  // modificando un servizio lì, cambia sia nell'app sia qui. Qui solo titolo/intro
  // della sezione; le card leggono label/descrizione/icona dal catalogo.
  servizi: {
    kicker: "Non solo software",
    title: "C'è una persona dietro, che ti segue davvero",
    sottotitolo:
      "Oltre all'app, ti affianchiamo con servizi su misura per il tuo locale: dall'analisi dei numeri all'assistenza continuativa.",
  },

  // Footer completo (rettifica §F): logo leggibile, WhatsApp + email, legali,
  // collaborazione Recoma con P.IVA, copyright.
  footer: {
    tagline: "La tecnologia che la tua gestione aspettava",
    // Microcopy caldo (solo footer): persona vera, nessun ticket. "servizi" in
    // giallo (coerente con la card servizi) e linkato alla sezione Servizi pubblica
    // (#servizi nella landing, stessa fonte del catalogo dell'app). Rimosso "non un
    // call center" (suonava polemico).
    umanoPre: "Dall'altra parte c'è una persona vera. Scrivici quando vuoi, niente ticket, niente attese. ",
    umanoServizi: "Guarda i nostri servizi",
    whatsappLabel: "Scrivici su WhatsApp",
    email: "mattia.davolio@recomasystem.it",
    privacyHref: "/privacy",
    terminiHref: "/termini",
    // "Recoma System" reso rosso e cliccabile (RecomaLink) sia qui sia in cima
    // alla scena 0; il prefisso resta testo normale.
    recomaPrefisso: "In collaborazione con",
    recomaNome: "Recoma System",
    recomaHref: "https://www.recomasystem.it",
    // Dati legali Recoma sotto la collaborazione (lato sinistro footer).
    recomaRagione: "RECOMASYSTEM Srl",
    recomaIndirizzo: "Via Leonardo da Vinci 249 · 20090 Trezzano sul Naviglio (MI)",
    recomaPiva: "P.IVA 12993240154",
    // Copyright OneFlux (lato destro). Per ora solo ©: il marchio e' in corso di
    // deposito (non ancora depositato). NON scrivere "marchio depositato/registrato"
    // ne' ® finche' Mattia non conferma il deposito col relativo numero.
    copyrightOneflux: "© 2026 OneFlux · Mattia D'Avolio",
  },
} as const;

export const WHATSAPP_LANDING_MSG =
  "Ciao! Vorrei provare ONEFLUX sul mio locale.";
