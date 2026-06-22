import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";

export const metadata: Metadata = {
  title: "ONEFLUX — Costi e margini del ristorante sotto controllo",
  description:
    "ONEFLUX legge le tue fatture elettroniche, le categorizza con l'AI e ti mostra food cost, margini e alert prezzi fornitori. Pensato per ristoratori, non per ragionieri.",
  openGraph: {
    title: "ONEFLUX — Costi e margini del ristorante sotto controllo",
    description:
      "Sai ogni mattina se il tuo ristorante sta guadagnando. Fatture in ordine da sole, food cost e margini reali, alert sui rincari dei fornitori.",
    type: "website",
    locale: "it_IT",
  },
};

export default function Home() {
  return <LandingPage />;
}
