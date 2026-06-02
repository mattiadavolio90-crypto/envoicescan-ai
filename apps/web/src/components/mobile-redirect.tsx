"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useIsMobile } from "@/hooks/use-mobile";

// Pagine (app) raggiungibili anche da mobile senza essere rimbalzate su /m:
// sono pagine "di servizio" semplici e gia' responsive, linkate dal menu mobile
// (Impostazioni) o dal flusso di onboarding. Tutto il resto e' redirezionato.
const MOBILE_ALLOWED = ["/impostazioni"];

// Su schermo mobile reindirizza la vista desktop (app) verso la PWA /m.
// Eccezioni: /admin (gestione, solo desktop), /m (gia' mobile) e le pagine in
// MOBILE_ALLOWED. Chi vuole l'intera vista desktop usa "Vista completa" dal
// menu (flag di sessione force-desktop).
export function MobileRedirect() {
  const isMobile = useIsMobile();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isMobile) return;
    if (pathname.startsWith("/admin")) return;
    if (pathname.startsWith("/m")) return;
    if (MOBILE_ALLOWED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return;
    // "Vista completa" dal menu mobile disattiva il redirect per la sessione.
    try {
      if (sessionStorage.getItem("oneflux:force-desktop") === "1") return;
    } catch {
      /* sessionStorage non disponibile: prosegui col redirect */
    }
    router.replace("/m");
  }, [isMobile, pathname, router]);

  return null;
}
