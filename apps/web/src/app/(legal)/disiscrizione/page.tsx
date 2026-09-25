import type { Metadata } from "next";
import { Suspense } from "react";
import { DisiscrizioneClient } from "./disiscrizione-client";

export const metadata: Metadata = {
  title: "Email settimanale",
  description: "Smetti di ricevere l'email settimanale di ONEFLUX.",
  robots: { index: false },
};

export default function DisiscrizionePage() {
  return (
    <Suspense fallback={null}>
      <DisiscrizioneClient />
    </Suspense>
  );
}
