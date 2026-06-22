// Contenuti della landing pubblica (route "/"). Tutto il copy vive qui: per
// cambiare testi, prezzi o offerta si tocca SOLO questo file, non i componenti.
//
// Versione "Recoma-first": il tono e l'offerta parlano a un ristoratore che
// arriva caldo tramite Recoma. Quando passeremo al traffico freddo (ADS) basta
// rielaborare i testi qui sotto e l'offerta, senza ridisegnare la pagina.

export const LANDING = {
  // --- Barra in alto -------------------------------------------------------
  nav: {
    accediLabel: "Accedi",
    accediHref: "/login",
  },

  // --- Hero ----------------------------------------------------------------
  hero: {
    // Badge di fiducia: il ponte Recoma. È la prima cosa che rassicura il
    // cliente caldo. Da rimuovere/cambiare per il traffico freddo.
    eyebrow: "In collaborazione con Recoma System",
    title: "Sai ogni mattina se il tuo ristorante sta guadagnando.",
    subtitle:
      "ONEFLUX legge le tue fatture, le mette in ordine da solo e ti dice food cost, margini e dove stai pagando troppo. Senza Excel, senza smanettare: apri l'app e capisci come va.",
    ctaPrimary: "Parla con noi su WhatsApp",
    ctaSecondary: "Accedi alla tua area",
    note: "Pensato per ristoratori, non per ragionieri.",
  },

  // --- Sezione "il problema" ----------------------------------------------
  problema: {
    title: "La cassa gira, ma a fine mese cosa resta?",
    paragrafo:
      "Le fatture dei fornitori arrivano a decine, i prezzi cambiano di nascosto e capire il food cost reale richiede ore di Excel che non hai. Così si scopre troppo tardi che un margine si è mangiato il guadagno.",
    bullets: [
      "Non sai quali fornitori hanno alzato i prezzi questo mese.",
      "Il food cost lo stimi a sensazione, non sui numeri veri.",
      "Le fatture le accumuli e le guardi solo quando è tardi.",
    ],
  },

  // --- Funzionalità --------------------------------------------------------
  features: {
    title: "Tutto il controllo della gestione, in un colpo d'occhio",
    subtitle:
      "ONEFLUX fa il lavoro noioso al posto tuo e ti lascia solo le decisioni.",
    items: [
      {
        icon: "Sparkles",
        title: "Il buongiorno che ti dice la verità",
        text: "Ogni mattina un riassunto onesto della tua gestione: cosa va bene, cosa sistemare oggi. Niente report da decifrare.",
      },
      {
        icon: "Receipt",
        title: "Fatture in ordine, da sole",
        text: "Carichi (o ricevi via SDI) le fatture elettroniche: l'AI legge ogni riga e la categorizza automaticamente. Tu non tocchi nulla.",
      },
      {
        icon: "BarChart3",
        title: "Food cost e margini reali",
        text: "Margini, food cost e andamento dei conti calcolati sui tuoi numeri veri, mese per mese. Finalmente sai dove guadagni.",
      },
      {
        icon: "Bell",
        title: "Alert prezzi fornitori",
        text: "Ti avvisiamo solo quando un rincaro pesa davvero sulla tua spesa, non a ogni centesimo. Tratti col fornitore prima che faccia danni.",
      },
    ],
  },

  // --- Anteprima app (mockup) ---------------------------------------------
  preview: {
    title: "Così, ogni mattina",
    subtitle: "Apri l'app e in 10 secondi sai come sta andando.",
  },

  // --- Offerta lancio Recoma ----------------------------------------------
  // NB (Mattia): conferma/aggiusta i termini dell'offerta. Oggi è impostata
  // sul Check-up incluso, coerente con la "civetta" da 49€ di /assistenza.
  offerta: {
    badge: "Riservato ai clienti Recoma",
    title: "Parti con il Check-up Operativo incluso",
    text: "Configuriamo noi il tuo account e facciamo insieme una prima analisi dei tuoi numeri (valore 49€), così parti già sapendo dove intervenire. Nessun vincolo, disdici quando vuoi.",
    cta: "Attiva il tuo account",
  },

  // --- Prezzi (dal business plan, +IVA) -----------------------------------
  prezzi: {
    title: "Prezzi semplici, senza sorprese",
    subtitle: "Tutti i piani includono ogni funzione. Cambia solo il volume di fatture e l'uso dell'assistente. Prezzi +IVA.",
    piani: [
      {
        nome: "Base",
        prezzo: "39€",
        periodo: "/mese",
        descrizione: "Per il locale singolo che vuole ordine nei conti.",
        evidenza: false,
        features: [
          "Fino a 50 fatture/mese",
          "Categorizzazione AI delle fatture",
          "Food cost, margini e briefing giornaliero",
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
    nota: "Non sai quale piano fa per te? Scrivici: ti consigliamo quello giusto in due minuti.",
  },

  // --- FAQ -----------------------------------------------------------------
  faq: {
    title: "Domande frequenti",
    items: [
      {
        q: "Devo cambiare commercialista o gestionale?",
        a: "No. ONEFLUX si affianca a quello che già usi: serve a te per tenere sotto controllo costi e margini, non sostituisce il commercialista.",
      },
      {
        q: "Come arrivano le fatture nell'app?",
        a: "Puoi caricarle a mano (XML, P7M o PDF) oppure farle arrivare in automatico dal Sistema di Interscambio: in quel caso non devi fare più nulla.",
      },
      {
        q: "È complicato da usare?",
        a: "No, è pensato per chi sta in cucina e in sala, non al computer. Se vuoi, configuriamo tutto noi e ti mostriamo come funziona.",
      },
      {
        q: "I miei dati sono al sicuro?",
        a: "Sì. Password protette con crittografia forte, dati gestiti nel rispetto del GDPR e fatture trattate al volo senza archiviarle inutilmente.",
      },
      {
        q: "Posso disdire quando voglio?",
        a: "Sì, nessun vincolo di durata. Continui finché ti è utile.",
      },
    ],
  },

  // --- CTA finale ----------------------------------------------------------
  ctaFinale: {
    title: "Smetti di scoprire i problemi a fine mese",
    text: "Iniziamo dal tuo locale: ti facciamo vedere i tuoi numeri come non li hai mai visti.",
    cta: "Scrivici su WhatsApp",
  },

  // --- Footer --------------------------------------------------------------
  footer: {
    tagline: "Gestione costi e margini per la ristorazione.",
    // NB (Mattia): conferma l'email pubblica (dominio Aruba). Se non vuoi
    // mostrarla, togli la riga "email" dai contatti nel footer.
    email: "info@oneflux.it",
    privacyHref: "/privacy",
    terminiHref: "/termini",
  },
} as const;

// Messaggio precompilato per i CTA WhatsApp della landing (diverso da quello di
// /assistenza: qui chi scrive è un potenziale cliente, non un cliente attivo).
export const WHATSAPP_LANDING_MSG =
  "Ciao! Ho visto ONEFLUX e vorrei capire come funziona per il mio ristorante.";
