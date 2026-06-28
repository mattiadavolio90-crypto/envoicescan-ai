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
  scene: {
    // Regola tipografica (rettifica): NIENTE punto a fine frase. Il punto si usa
    // solo come stacco interno tra le due frasi di un titolo doppio.

    // SCENA 0 — Aggancio (mistero)
    aggancio: {
      bg: "/landing/bg-marginalita.png",
      title: "Un unico flusso operativo.\nTutto sotto controllo",
      firma: "Lavora per te mentre ti occupi di altro",
      scrollHint: "scorri",
    },

    // SCENA 1 — Lo specchio (riconoscimento)
    specchio: {
      bg: "/landing/bg-personale.png",
      kicker: "Tu",
      title: "Il tuo lavoro è gestire. Non fare data entry",
      sotto: "Il tuo posto è nelle decisioni, non a compilare un foglio Excel a notte fonda",
    },

    // SCENA 2 — Lui ti parla (briefing · PRIMO CUORE)
    // Testi generici di proposito: il briefing accenna, sotto ci sono notifiche+card.
    // NON promettere numeri specifici (incassi/coperti): dipendono da come il cliente
    // carica i dati. Si parla del MODO in cui l'assistente lavora, non dei numeri.
    briefing: {
      hero: "/landing/hero-briefing.png",
      kicker: "Ogni mattina",
      title: "Ogni giorno ti dice come sta andando. Prima che tu lo chieda",
      sotto:
        "Cosa è cambiato, cosa controllare, dove serve attenzione — confrontato con il tuo andamento.",
    },

    // SCENA 3 — Tu gli parli (chat · SECONDO CUORE · la rivelazione)
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

    // SCENA 4 — La prova (automazioni). Rettifica: jolly mail RIMOSSO, solo hero-prezzi.
    prova: {
      hero: "/landing/hero-prezzi.png",
      kicker: "Nel frattempo",
      title: "I dati entrano da soli",
      sotto:
        "Le fatture dei fornitori arrivano in automatico, l'assistente le legge, le categorizza e ti segnala se un prezzo cambia.",
      chiusura: "Tu non tocchi niente",
    },

    // SCENA 5 — Il potere (LA frase che deve restare)
    potere: {
      bg: "/landing/bg-coperti.png",
      kicker: "Ovunque",
      title: "Da dove vuoi. Anche fuori dal locale",
      sotto: "In sala, dal fornitore, sul divano — il tuo locale ti risponde dove sei tu.",
    },

    // SCENA 6 — L'invito + rivelazione (hero-conti NUOVA: tutto verde, salute 100%)
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
    title: "Un prezzo, zero lavoro in cambio",
    lista: [
      { nome: "Base", prezzo: "39€", fatture: "50 fatture / mese", ai: "10 domande AI / giorno", evidenza: false },
      { nome: "Plus", prezzo: "59€", fatture: "100 fatture / mese", ai: "20 domande AI / giorno", evidenza: true },
      { nome: "Pro", prezzo: "79€", fatture: "200 fatture / mese", ai: "30 domande AI / giorno", evidenza: false },
    ],
    iva: "Prezzi IVA esclusa.",
    catena: "Più locali? C'è la modalità catena, su ogni piano",
  },

  footer: {
    tagline: "La tecnologia che la tua gestione aspettava.",
    email: "info@oneflux.it",
    privacyHref: "/privacy",
    terminiHref: "/termini",
  },
} as const;

export const WHATSAPP_LANDING_MSG =
  "Ciao! Vorrei provare ONEFLUX sul mio locale.";
