import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";

export const metadata: Metadata = {
  title: "ONEFLUX — Tutto sotto controllo. Mentre pensi ad altro.",
  description:
    "Il cervello operativo della tua gestione. Ti dice com'è andata prima che tu lo chieda, e gli rispondi come a una persona. Le fatture entrano da sole. Provalo sul tuo locale, 7 giorni gratis.",
  openGraph: {
    title: "ONEFLUX — Tutto sotto controllo. Mentre pensi ad altro.",
    description:
      "Il braccio destro che tiene il tuo locale sotto controllo — e te lo dice prima che tu lo chieda. 7 giorni gratis.",
    type: "website",
    locale: "it_IT",
  },
};

export default function Home() {
  return <LandingPage />;
}
