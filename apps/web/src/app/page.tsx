import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";

// SEO landing: il copy VISIBILE resta emozionale (brief: niente buzzword). Le
// parole-chiave reali che il ristoratore cerca su Google (food cost, fatture
// elettroniche, controllo costi, marginalità) vivono SOLO qui nei metadata e nel
// JSON-LD: invisibili in pagina, lette dai motori. Canonical su oneflux.it per
// separare nettamente la landing dall'app (app.oneflux.it).
// Titolo/descrizione anteprima social = stesso messaggio della scena 0 (coerenza
// con cio' che il visitatore vede aprendo il link). Le keyword SEO restano sotto,
// invisibili. og:image = /og-image.png statico 1200x630; metadataBase
// (https://www.oneflux.it nel layout) lo risolve in URL assoluto per gli scraper.
const OG_TITLE = "Prova ONEFLUX — il tuo assistente per i costi del ristorante";
const OG_DESC =
  "Gestisci il tuo locale senza diventare un contabile. Ai dati pensa OneFlux — si adatta a te.";

export const metadata: Metadata = {
  title: OG_TITLE,
  description: OG_DESC,
  keywords: [
    "software food cost ristorante",
    "controllo di gestione ristorante",
    "fatture elettroniche ristorante",
    "calcolo food cost",
    "marginalità ristorante",
    "gestione costi ristorante",
    "controllo costi ristorante",
    "assistente AI ristorazione",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    title: OG_TITLE,
    description: OG_DESC,
    url: "https://www.oneflux.it",
    siteName: "OneFlux",
    type: "website",
    locale: "it_IT",
    images: [
      {
        url: "/og-image.png",
        width: 1200,
        height: 630,
        alt: OG_TITLE,
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: OG_TITLE,
    description: OG_DESC,
    images: ["/og-image.png"],
  },
};

export default function Home() {
  return <LandingPage />;
}
