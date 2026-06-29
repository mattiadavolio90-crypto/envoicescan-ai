import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";

// SEO landing: il copy VISIBILE resta emozionale (brief: niente buzzword). Le
// parole-chiave reali che il ristoratore cerca su Google (food cost, fatture
// elettroniche, controllo costi, marginalità) vivono SOLO qui nei metadata e nel
// JSON-LD: invisibili in pagina, lette dai motori. Canonical su oneflux.it per
// separare nettamente la landing dall'app (app.oneflux.it).
export const metadata: Metadata = {
  title: "ONEFLUX — Controllo costi e food cost per il tuo ristorante",
  description:
    "Il braccio destro del tuo ristorante: le fatture elettroniche entrano da sole, l'assistente le categorizza, calcola food cost e marginalità e ti dice ogni mattina come va. Avvisi sui rincari dei fornitori. Provalo sul tuo locale, 7 giorni gratis.",
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
    title: "ONEFLUX — Il braccio destro del tuo ristorante",
    description:
      "Le fatture entrano da sole, l'assistente le legge e ti dice ogni mattina come va il locale. Food cost, marginalità e avvisi sui rincari, sotto controllo. 7 giorni gratis.",
    url: "/",
    siteName: "ONEFLUX",
    type: "website",
    locale: "it_IT",
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "ONEFLUX — Il braccio destro del tuo ristorante",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "ONEFLUX — Il braccio destro del tuo ristorante",
    description:
      "Le fatture entrano da sole, l'assistente le legge e ti dice ogni mattina come va. Food cost, marginalità e avvisi rincari. 7 giorni gratis.",
    images: ["/opengraph-image"],
  },
};

export default function Home() {
  return <LandingPage />;
}
