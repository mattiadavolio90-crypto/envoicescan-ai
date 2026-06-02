"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useIsMobile } from "@/hooks/use-mobile";

// Su schermo mobile reindirizza la vista desktop (app) verso la PWA /m.
// Eccezioni: /admin (gestione, solo desktop) e /m (gia' mobile). Tutte le
// sezioni mobile vivono sotto /m (Impostazioni inclusa), quindi non serve
// alcuna whitelist di pagine (app).
export function MobileRedirect() {
  const isMobile = useIsMobile();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isMobile) return;
    if (pathname.startsWith("/admin")) return;
    if (pathname.startsWith("/m")) return;
    router.replace("/m");
  }, [isMobile, pathname, router]);

  return null;
}
