// Catalogo servizi (Assistenza). Statico in codice: pochi servizi che cambiano
// di rado, niente tabella DB da gestire. Per modificarne uno basta una voce qui.
//
// La struttura e' tipizzata in modo forte per essere pronta alla fase 2 (prezzi
// visibili, report asincroni, automazione check-up) senza renderizzare ora nulla
// di non richiesto: i campi prezzo/report esistono nei dati ma NON vanno in UI.

// Nomi icona ammessi (lucide-react). Union type: un refuso qui e' errore a
// compile-time, non un fallback silenzioso a runtime.
export type ServizioIconName =
  | "Stethoscope"
  | "LineChart"
  | "Headset"
  | "FileSearch"
  | "PiggyBank"
  | "Globe";

// Resa grafica: servizio OneFlux standard, entry-point in risalto, area partner.
export type ServizioVariant = "default" | "featured" | "partner";

// Modalita' prezzo per la fase 2 (prezzo fisso vs "a partire da" vs custom).
export type PriceMode = "fixed" | "starting_from" | "custom";

export type Servizio = {
  // Chiave stabile: mappata 1:1 a `servizio_key` nel payload lead e letta dalla
  // coda admin. NON rinominare in id/slug senza toccare worker + tabella.
  key: string;
  label: string;
  descrizione: string;
  icon: ServizioIconName;
  variant?: ServizioVariant;

  // --- Area partner ---
  partnerLabel?: string; // micro-label sopra il titolo (es. collaborazione Recoma)
  partnerUrl?: string; // link informativo, secondario

  // --- Fase 2: presenti nei dati, NON renderizzati ora ---
  priceMode?: PriceMode;
  priceValue?: string; // testo umano gia' pronto: "49€ una tantum", "da 199€/mese"
  isFutureAutomated?: boolean; // servizio che diventera' automatizzabile in-app
  asyncReportTopics?: string[]; // temi dei report scritti asincroni (card Analisi)
  notesInternal?: string; // promemoria interno, mai mostrato all'utente
};

export const SERVIZI: Servizio[] = [
  {
    key: "checkup_operativo",
    label: "Check-up Operativo",
    descrizione:
      "Una prima analisi sui tuoi dati in app per capire cosa manca, cosa non torna e su quali priorità conviene intervenire subito nella gestione.",
    icon: "Stethoscope",
    variant: "featured",
    priceMode: "fixed",
    priceValue: "49€ una tantum",
    isFutureAutomated: true,
    notesInternal:
      "Videocall inclusa. Fase 2: generazione automatica del check-up in-app e invio al cliente; usabile come leva commerciale (regalo/sconto).",
  },
  {
    key: "consulenza_gestionale",
    label: "Consulenza Gestionale",
    descrizione:
      "Analizziamo i tuoi numeri reali: food cost, fornitori e spese. Ti diciamo dove stai perdendo, cosa puoi recuperare e come impostare una strategia concreta per migliorare.",
    icon: "LineChart",
    variant: "default",
    priceMode: "starting_from",
    priceValue: "da 199€/mese",
    notesInternal: "Servizio continuativo.",
  },
  {
    key: "assistenza_continuativa",
    label: "Assistenza Continuativa",
    descrizione:
      "Gestiamo noi l'app al posto tuo: carichiamo i dati che ci comunichi, controlliamo i numeri e teniamo tutto sotto monitoraggio. Tu devi solo entrare e guardare l'andamento della tua gestione.",
    icon: "Headset",
    variant: "default",
    priceMode: "fixed",
    priceValue: "99€/mese",
    notesInternal: "Servizio continuativo.",
  },
  {
    key: "analisi_su_richiesta",
    label: "Analisi su Richiesta",
    descrizione:
      "Hai una domanda specifica o bisogno di un'analisi sulla tua gestione? Ricevi un'analisi scritta entro 48h sui tuoi numeri o su analisi di mercato, senza appuntamenti, su costi, margini, prezzi o altre criticità operative.",
    icon: "FileSearch",
    variant: "default",
    priceMode: "starting_from",
    priceValue: "da 49€ una tantum",
    // TODO (fase 2): contenitore dei report asincroni. Questi topic guideranno
    // la scelta del tipo di report e, in futuro, la generazione/consegna in-app.
    asyncReportTopics: [
      "food_cost",
      "margini",
      "fornitori",
      "prezzi",
      "criticita_operative",
      "analisi_mercato",
    ],
    notesInternal:
      "Fase 2: includere food cost, margini, fornitori, prezzi, criticità operative e analisi di mercato come report scritti consegnabili in-app.",
  },
  {
    key: "ottimizzazione_costi",
    label: "Ottimizzazione Costi",
    descrizione:
      "Analizziamo le tue spese fisse: confrontiamo i listini dei fornitori, le offerte su luce e gas e le commissioni del tuo POS. Ti diciamo dove stai pagando troppo e ti prepariamo una proposta concreta per ridurre i costi che hai già con i nostri partner.",
    icon: "PiggyBank",
    variant: "partner",
    priceMode: "custom",
    // Prezzo su preventivo: nessun badge in UI. priceValue resta vuoto apposta.
    partnerLabel: "Offerta partner",
    notesInternal: "Area partner OneFlux. Prezzo su preventivo, da definire in fase 2.",
  },
  {
    key: "sito_presenza_online",
    label: "Sito e Presenza Online",
    descrizione:
      "Sito moderno e performante, social curati, contenuti, foto e video professionali del locale e dei piatti. Tecnologie aggiornate per farti trovare online e fare una buona impressione al primo sguardo.",
    icon: "Globe",
    variant: "partner",
    priceMode: "custom",
    // Prezzo su preventivo: nessun badge in UI. priceValue resta vuoto apposta.
    partnerLabel: "In collaborazione con Recoma System",
    partnerUrl: "https://recomasystem.it",
    notesInternal:
      "Il servizio NON si chiama Recoma: Recoma e' citata solo come collaborazione. Link esterno informativo e secondario. Prezzo da definire in fase 2.",
  },
];

// Numero WhatsApp per il contatto diretto. Override possibile via env pubblica;
// fallback al numero noto ai clienti. Formato internazionale senza '+'.
export const WHATSAPP_NUMERO =
  process.env.NEXT_PUBLIC_WHATSAPP_NUMERO ?? "393488014534";

export function whatsappLink(servizioLabel?: string): string {
  const base = `https://wa.me/${WHATSAPP_NUMERO}`;
  if (!servizioLabel) return base;
  const testo = `Ciao! Vorrei informazioni sul servizio "${servizioLabel}".`;
  return `${base}?text=${encodeURIComponent(testo)}`;
}

// --- Lato admin: coda lead --------------------------------------------------
export type MarketplaceLead = {
  id: string;
  servizio_key: string;
  servizio_label: string;
  messaggio: string;
  contatto_email: string | null;
  contatto_nome: string | null;
  ristorante_nome: string | null;
  stato: "nuovo" | "gestito" | "archiviato";
  created_at: string | null;
};

export type MarketplaceLeadList = {
  leads: MarketplaceLead[];
  nuovi: number;
};
