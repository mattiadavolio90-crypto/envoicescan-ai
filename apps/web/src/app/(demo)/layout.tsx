import type { Metadata } from "next";

// Route-group PUBBLICO per il Demo Tour: nessun getCurrentSession, nessun
// redirect al login (a differenza di (app)/layout.tsx). Chiunque abbia il link
// vede la demo. Precedente: (legal)/layout.tsx, anch'esso pubblico.
//
// Niente manifest PWA qui: la demo non deve far comparire il prompt "Installa
// ONEFLUX" di Chrome (quello vive solo dentro l'app vera).

export const metadata: Metadata = {
  title: "Prova ONEFLUX — il tuo assistente per i costi del ristorante",
  description:
    "Guarda in un minuto come ONEFLUX legge le tue fatture, ti avvisa dei rincari e ti mostra il margine reale. Dati di esempio, nessuna registrazione.",
  robots: { index: false, follow: false },
};

export default function DemoLayout({ children }: { children: React.ReactNode }) {
  return children;
}
