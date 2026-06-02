"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useIsMobile } from "@/hooks/use-mobile";

// Su schermo mobile reindirizza la vista desktop (app) verso la PWA /m.
// Eccezione: /admin resta solo desktop (gestione, non si fa da telefono).
// Il redirect scatta una volta lato client; chi vuole la vista piena puo'
// tornarci via link diretto (il redirect non si ripete se gia' su /m).
export function MobileRedirect() {
  const isMobile = useIsMobile();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isMobile) return;
    if (pathname.startsWith("/admin")) return;
    if (pathname.startsWith("/m")) return;
    // L'utente puo' scegliere "Vista completa" dal menu mobile: in quel caso
    // un flag di sessione disattiva il redirect finche' non chiude la scheda.
    try {
      if (sessionStorage.getItem("oneflux:force-desktop") === "1") return;
    } catch {
      /* sessionStorage non disponibile: prosegui col redirect */
    }
    router.replace("/m");
  }, [isMobile, pathname, router]);

  return null;
}
