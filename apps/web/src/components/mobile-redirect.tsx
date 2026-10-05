"use client";

import { useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useIsMobileDetect } from "@/hooks/use-mobile";
import { rimbalzoAlRender } from "@/lib/device";

// Su schermo mobile reindirizza la vista desktop (app) verso la PWA /m.
// Eccezioni: /admin (gestione, solo desktop) e /m (gia' mobile). Tutte le
// sezioni mobile vivono sotto /m (Impostazioni inclusa), quindi non serve
// alcuna whitelist di pagine (app).
//
// Un telefono vero rimbalza sempre (5/10/2026: da telefono solo /m). La finestra
// stretta di un computer solo all'ingresso: misurato il 23/09/2026, chi la
// affiancava mentre lavorava finiva su /m a meta' operazione, senza ritorno.
//
// `useIsMobileDetect` e non `useIsMobile`: quest'ultimo appiattisce a `false` il
// primo render, e segnare la decisione come presa su quel falso spegneva il
// rimbalzo anche per i telefoni veri (vedi `decisionePresa` in lib/device.ts).
export function MobileRedirect() {
  const isMobile = useIsMobileDetect();
  const router = useRouter();
  const pathname = usePathname();
  const decisoPer = useRef<string | null>(null);

  useEffect(() => {
    if (rimbalzoAlRender(decisoPer, isMobile, pathname)) router.replace("/m");
  }, [isMobile, pathname, router]);

  return null;
}
