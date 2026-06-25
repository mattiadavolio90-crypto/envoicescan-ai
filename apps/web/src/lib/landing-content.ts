// Contenuti della landing pubblica (route "/"). Tutto il copy vive qui: per
// cambiare testi, prezzi, conversazione AI o offerta si tocca SOLO questo file.
//
// Posizionamento (v2): il wedge non e' "sai se guadagni" (lo dicono tutti), ma
// "NON devi compilare niente — niente magazzino, niente inventario, niente
// Excel — e per sapere come va PARLI con un assistente AI". Data-entry free +
// agente conversazionale = il vero effetto wow. Tono: ristoratore, non corporate.

export const LANDING = {
  nav: {
    accediLabel: "Accedi",
    accediHref: "/login",
  },

  // --- Hero ----------------------------------------------------------------
  // L'hero ospita la demo VIVA: la barra del chiedi si digita da sola e l'AI
  // risponde (componente client ChatDemo). Gli "scambi" qui sotto sono lo
  // script di quella demo e fanno da prova del differenziatore.
  hero: {
    eyebrow: "In collaborazione con Recoma System",
    title: "Il gestionale che non devi compilare.",
    subtitle:
      "Niente magazzino, niente inventario, niente Excel. Le fatture entrano da sole, l'AI le legge e tu — per sapere come va il locale — fai una domanda.",
    note: "Pensato per chi sta ai fornelli, non al computer.",
    ctaPrimary: "Provalo sul tuo locale",
    ctaSecondary: "Accedi",
    // Script della demo dell'hero: domande che si digitano e ricevono risposta a rotazione.
    scambi: [
      {
        q: "Quanto ho speso di carne a maggio?",
        a: "A maggio € 4.180 di carne, +12% su aprile. Il rincaro arriva quasi tutto dal tuo macellaio abituale.",
      },
      {
        q: "Quale fornitore ha alzato i prezzi?",
        a: "Negli ultimi 90 giorni l'olio EVO è salito del 9% (≈ €120/mese in più) e la farina del 6%. Gli altri stabili.",
      },
      {
        q: "Com'è andato il mese?",
        a: "Maggio chiuso con € 12.480 di margine, +14% su aprile. Food cost al 28%, in linea. Bel mese 👏",
      },
    ],
  },

  // --- Contrasto: gli altri vs ONEFLUX (assorbe "cosa tieni sotto controllo") -
  contrasto: {
    title: "Tutti i gestionali ti chiedono di lavorare. Questo no.",
    subtitle:
      "Il motivo per cui non hai mai usato un software di food cost è sempre lo stesso: troppo lavoro manuale. ONEFLUX toglie proprio quello — e ciò che gli altri ti fanno calcolare, qui lo chiedi e basta.",
    righe: [
      {
        tema: "Magazzino e inventario",
        altri: "Conti tutto a mano, scaffale per scaffale, ogni settimana.",
        oneflux: "Non lo fai. Mai.",
      },
      {
        tema: "Food cost, margini, calcoli",
        altri: "Fogli Excel, formule, ore perse a fine servizio.",
        oneflux: "Calcolati da soli sui tuoi numeri veri.",
      },
      {
        tema: "Sapere come va il locale",
        altri: "Studi tabelle e grafici che non hai tempo di leggere.",
        oneflux: "Fai una domanda all'assistente. Ti risponde. Fine.",
      },
    ],
    nota: "Non sei tecnologico? Meglio. Qui non c'è niente da imparare.",
  },

  // --- Come funziona (3 step) ---------------------------------------------
  comeFunziona: {
    title: "Tu non fai niente. Ecco come.",
    step: [
      {
        n: "1",
        titolo: "Le fatture arrivano da sole",
        testo: "Colleghiamo il tuo codice SDI: ogni fattura elettronica entra in automatico. Oppure la trascini al volo, una e via.",
      },
      {
        n: "2",
        titolo: "L'AI legge ogni riga",
        testo: "Riconosce prodotti, categorie e prezzi da sola, fattura dopo fattura. Niente da sistemare, niente da inserire.",
      },
      {
        n: "3",
        titolo: "Tu chiedi, lui risponde",
        testo: "Apri l'app e fai la domanda. Food cost, margini, rincari dei fornitori: la risposta è già pronta.",
      },
    ],
  },

  // --- Cosa ottieni (strip compatta sotto "come funziona", non sezione a sé) -
  controllo: {
    title: "E intanto hai sotto controllo:",
    chips: [
      "Food cost reale, mese per mese",
      "Margini e andamento dei conti",
      "Rincari dei fornitori, segnalati in tempo",
      "Il buongiorno che ti dice com'è andata",
    ],
  },

  // --- Offerta lancio Recoma ----------------------------------------------
  // NB (Mattia): conferma/aggiusta i termini.
  offerta: {
    badge: "Riservato ai clienti Recoma",
    title: "Parti con il Check-up Operativo incluso",
    text: "Configuriamo noi il tuo account e facciamo insieme una prima analisi dei tuoi numeri (valore 49€). Tu non devi preparare niente. Nessun vincolo, disdici quando vuoi.",
    cta: "Attiva il tuo account",
  },

  // --- Prezzi (dal business plan, +IVA) -----------------------------------
  prezzi: {
    title: "Un prezzo, zero lavoro in cambio",
    subtitle: "Tutti i piani includono ogni funzione e l'assistente AI. Cambia solo il volume di fatture. Prezzi +IVA.",
    piani: [
      {
        nome: "Base",
        prezzo: "39€",
        periodo: "/mese",
        descrizione: "Per il locale singolo che vuole ordine nei conti.",
        evidenza: false,
        features: [
          "Fino a 50 fatture/mese",
          "Lettura e categorizzazione AI",
          "Food cost, margini e briefing",
          "Assistente AI: 10 domande/giorno",
        ],
      },
      {
        nome: "Plus",
        prezzo: "59€",
        periodo: "/mese",
        descrizione: "Il più scelto: per chi ordina spesso e vuole gli alert.",
        evidenza: true,
        features: [
          "Fino a 100 fatture/mese",
          "Tutto del piano Base",
          "Alert prezzi fornitori e scadenziario",
          "Assistente AI: 20 domande/giorno",
        ],
      },
      {
        nome: "Pro",
        prezzo: "79€",
        periodo: "/mese",
        descrizione: "Per i volumi alti e chi vuole il massimo dall'analisi.",
        evidenza: false,
        features: [
          "Fino a 200 fatture/mese",
          "Tutto del piano Plus",
          "Analisi e tag avanzati",
          "Assistente AI: 30 domande/giorno",
        ],
      },
    ],
    nota: "Non sai quale piano fa per te? Scrivici: te lo diciamo in due minuti.",
  },

  // --- FAQ -----------------------------------------------------------------
  faq: {
    title: "Domande frequenti",
    items: [
      {
        q: "Devo fare il magazzino o l'inventario?",
        a: "No, mai. È la differenza con tutti gli altri gestionali: ONEFLUX lavora sulle fatture, non ti chiede di contare o inserire niente a mano.",
      },
      {
        q: "Come arrivano le fatture nell'app?",
        a: "In automatico dal Sistema di Interscambio (colleghiamo il tuo codice SDI), oppure le trascini tu quando vuoi: XML, P7M o PDF. In entrambi i casi le legge l'AI.",
      },
      {
        q: "Devo cambiare commercialista o gestionale?",
        a: "No. ONEFLUX si affianca a quello che già usi: serve a te per tenere sotto controllo costi e margini, non sostituisce nessuno.",
      },
      {
        q: "Non sono pratico di tecnologia, è un problema?",
        a: "Al contrario. Non c'è niente da imparare: apri e fai una domanda a parole tue. Se vuoi, configuriamo e ti mostriamo tutto noi.",
      },
      {
        q: "Posso disdire quando voglio?",
        a: "Sì, nessun vincolo di durata. Continui finché ti è utile.",
      },
    ],
  },

  // --- CTA finale ----------------------------------------------------------
  ctaFinale: {
    title: "Smetti di lavorare per il software. Fallo lavorare per te.",
    text: "Iniziamo dal tuo locale: configuriamo noi e ti facciamo vedere i tuoi numeri come non li hai mai visti. Senza che tu inserisca niente.",
    cta: "Scrivici su WhatsApp",
  },

  // --- Footer --------------------------------------------------------------
  footer: {
    tagline: "Il gestionale data-entry free per la ristorazione.",
    // NB (Mattia): conferma l'email pubblica (dominio Aruba) o togli la riga.
    email: "info@oneflux.it",
    privacyHref: "/privacy",
    terminiHref: "/termini",
  },
} as const;

export const WHATSAPP_LANDING_MSG =
  "Ciao! Ho visto ONEFLUX e vorrei capire come funziona per il mio ristorante.";
