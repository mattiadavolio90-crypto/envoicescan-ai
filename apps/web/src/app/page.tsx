import type { Metadata } from "next";
import { LandingPage } from "@/components/landing/landing-page";

export const metadata: Metadata = {
  title: "ONEFLUX — Il gestionale del ristorante che non devi compilare",
  description:
    "Niente magazzino, niente inventario, niente Excel. Le fatture entrano da sole, l'AI le legge e tu, per sapere come va il locale, fai una domanda all'assistente.",
  openGraph: {
    title: "ONEFLUX — Il gestionale del ristorante che non devi compilare",
    description:
      "Data-entry free: niente magazzino né Excel. Le fatture le legge l'AI e per sapere food cost, margini e rincari basta chiedere all'assistente.",
    type: "website",
    locale: "it_IT",
  },
};

export default function Home() {
  return <LandingPage />;
}
