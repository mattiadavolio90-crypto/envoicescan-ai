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
  },

  // CTA prova gratuita reale (campi trial_active/trial_activated_at nel DB).
  cta: {
    label: "Inizia ora — 7 giorni gratis",
    nota: "Senza carta, senza obblighi",
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
    aggancio: {
      bg: "/landing/bg-marginalita.png",
      title: "Un unico flusso operativo.\nTutto sotto controllo",
      sotto: "Tu pensa alla sala e alla cucina. Ai numeri pensa OneFlux — e quando vuoi sapere come va, glielo chiedi",
      scrollHint: "scorri",
    },

    // SCENA 1 — Lui ti parla (briefing · PRIMO CUORE).
    // Testi generici di proposito: NON promettere numeri specifici (dipendono dai dati).
    briefing: {
      hero: "/landing/hero-briefing.png",
      kicker: "Il buongiorno",
      title: "Ogni giorno ti dice come sta andando. Prima che tu lo chieda",
      sotto: "Cosa è cambiato, cosa controllare, dove serve attenzione — confrontato con il tuo andamento",
    },

    // SCENA 2 — Tu gli parli (chat · SECONDO CUORE · la rivelazione)
    chat: {
      hero: "/landing/hero-chat.png",
      kicker: "Quando vuoi",
      title: "Glielo chiedi. E ti risponde",
      sotto: "Scrivi come a una persona, ti risponde come il tuo miglior collaboratore",
      // Sequenza reale dell'app. I messaggi compaiono UNO ALLA VOLTA, con ritardo
      // e indicatore "sta scrivendo": il wow è nel ritmo, non nella grafica.
      sequenza: [
        { da: "ai", testo: "Il salmone è costato € 7,29/kg, comprato il 27/05 da ADC." },
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
        "Le fatture arrivano in automatico e l'assistente le legge e le categorizza — migliaia di prodotti, in ordine da soli",
    },

    // SCENA 4 — Alert prezzi (automazioni, seconda metà).
    // È la promessa più "a guardia" del ristoratore: il rincaro che passa
    // inosservato è soldi persi. Tono più diretto, secondo riga che chiude il colpo.
    prezzi: {
      hero: "/landing/hero-prezzi.png",
      kicker: "E se qualcosa cambia",
      title: "Un fornitore alza i prezzi.\nLo sai prima di pagare",
      sotto: "OneFlux confronta ogni fattura con lo storico e ti avvisa quando un costo sale — con quanto ti pesa davvero, prima che diventi un problema",
    },

    // SCENA 5 — Il potere (mobile). LAYOUT 2 COLONNE: testo sx, telefono dx (verticale).
    // Chat su tema gestione (diversa dalla scena 2 sul salmone): niente ridondanza.
    potere: {
      heroMobile: "/landing/hero-mobile.jpeg",
      kicker: "Ovunque",
      title: "Da dove vuoi. Anche fuori dal locale",
      sotto: "In sala, dal fornitore, sul divano — il tuo locale ti risponde dove sei tu",
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
  // Numeri reali dal prodotto (verificati nel codice): fatture/mese 50/100/200,
  // domande AI/giorno 10/20/30, prezzi 39/59/79 +IVA.
  piani: {
    title: "Tutto incluso, in ogni piano",
    // Nessun piano "consigliato": tutti full optional, cambia solo il volume.
    // Niente "AI" nel copy (coerenza col resto della landing): "il tuo assistente".
    sottotitolo:
      "Ogni piano ha tutte le funzioni e il tuo assistente sempre attivo. Cambia solo il volume di fatture e domande: scegli in base alla dimensione del tuo locale.",
    lista: [
      { nome: "Base", prezzo: "39€", fatture: "50 fatture / mese", ai: "10 domande / giorno" },
      { nome: "Plus", prezzo: "59€", fatture: "100 fatture / mese", ai: "20 domande / giorno" },
      { nome: "Pro", prezzo: "79€", fatture: "200 fatture / mese", ai: "30 domande / giorno" },
    ],
    iva: "+IVA",
    catena: "Più locali? C'è la modalità catena, su ogni piano",
    // Rassicurazione umana sopra il prezzo: chi c'è dietro. Il target (ristoratore
    // poco tecnologico) prima di provare vuole sapere che non è solo un software.
    rassicurazione:
      "Non sei solo con un software: dall'altra parte c'è una persona vera che ti segue, non un call center",
  },

  // Footer completo (rettifica §F): logo leggibile, WhatsApp + email, legali,
  // collaborazione Recoma con P.IVA, copyright.
  footer: {
    tagline: "La tecnologia che la tua gestione aspettava",
    // Microcopy caldo (solo footer): rassicura che c'è una persona vera, non un
    // call center. Non cambia il senso, ammorbidisce il tono.
    umano: "Dall'altra parte c'è una persona vera, non un call center. Scrivici quando vuoi.",
    whatsappLabel: "Scrivici su WhatsApp",
    email: "mattia.davolio@recomasystem.it",
    privacyHref: "/privacy",
    terminiHref: "/termini",
    // "Recoma System" reso rosso e cliccabile (RecomaLink) sia qui sia in cima
    // alla scena 0; il prefisso resta testo normale.
    recomaPrefisso: "In collaborazione con",
    recomaNome: "Recoma System",
    recomaHref: "https://www.recomasystem.it",
    piva: "Recoma System S.r.l. · P.IVA IT09599210961",
  },
} as const;

export const WHATSAPP_LANDING_MSG =
  "Ciao! Vorrei provare ONEFLUX sul mio locale.";
