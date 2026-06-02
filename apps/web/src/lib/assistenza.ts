// Catalogo servizi del Marketplace (Assistenza). Statico in codice: pochi
// servizi che cambiano di rado, niente tabella DB da gestire. Per aggiungerne
// uno basta una voce qui (key univoca + testi). L'icona e' un nome lucide-react
// risolto lato pagina.

export type Servizio = {
  key: string;
  label: string;
  descrizione: string;
  icon: string; // nome icona lucide-react
  badge?: string; // etichetta opzionale (es. "Novità")
};

export const SERVIZI: Servizio[] = [
  {
    key: "consulenza_fb",
    label: "Consulenza F&B",
    descrizione:
      "Analisi del food cost, ottimizzazione dei margini e revisione dei fornitori. Un confronto sui tuoi numeri per capire dove recuperare redditività.",
    icon: "ChefHat",
  },
  {
    key: "studio_menu",
    label: "Studio del menù",
    descrizione:
      "Ricerca di mercato nella tua zona: equilibrio del menù, analisi dei competitor e posizionamento dei prezzi. Per capire come ti collochi davvero.",
    icon: "BookOpen",
  },
  {
    key: "comparatori",
    label: "Comparatori utenze e POS",
    descrizione:
      "Confronto delle offerte di luce, gas, POS e commissioni sui pagamenti. Ti diciamo se stai pagando troppo e dove puoi risparmiare.",
    icon: "Plug",
  },
  {
    key: "sito_web",
    label: "Rifacimento sito web",
    descrizione:
      "Un sito moderno, veloce e fatto per farti trovare. Dalla vetrina alle prenotazioni online, curato nei dettagli.",
    icon: "Globe",
  },
  {
    key: "social_foto",
    label: "Gestione social e foto",
    descrizione:
      "Presenza sui social e food photography professionale. Contenuti che fanno venire fame e attirano clienti nuovi.",
    icon: "Camera",
  },
  {
    key: "analisi_listini",
    label: "Analisi listini fornitori",
    descrizione:
      "Dimmi su quali prodotti vorresti spuntare prezzi migliori: analizziamo i tuoi listini e ti prepariamo una proposta di acquisto più conveniente.",
    icon: "TrendingDown",
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
