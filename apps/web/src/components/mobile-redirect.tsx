"use client";

import { useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { useIsMobile } from "@/hooks/use-mobile";
import { deveRimbalzareSuMobile, preferisceDesktop } from "@/lib/device";

// Su schermo mobile reindirizza la vista desktop (app) verso la PWA /m.
// Eccezioni: /admin (gestione, solo desktop) e /m (gia' mobile). Tutte le
// sezioni mobile vivono sotto /m (Impostazioni inclusa), quindi non serve
// alcuna whitelist di pagine (app).
//
// Il rimbalzo vale SOLO all'ingresso. Misurato il 23/09/2026: `isPhoneViewport()`
// guarda solo la larghezza, quindi chi affiancava la finestra di un desktop
// mentre lavorava finiva su /m a meta' operazione, senza alcun modo di tornare
// indietro (riallargare non bastava: /m e' escluso dal redirect stesso).
// La decisione si prende una volta sola, sul primo passaggio.
export function MobileRedirect() {
  const isMobile = useIsMobile();
  const router = useRouter();
  const pathname = usePathname();
  const decisoPer = useRef<string | null>(null);

  useEffect(() => {
    // `giaDentro` distingue l'ingresso dal ridimensionamento: per lo stesso
    // pathname la decisione si prende una volta sola. Un cambio di larghezza
    // ri-esegue l'effetto (useIsMobile e' agganciato a matchMedia) ma non
    // ri-decide, quindi non strappa via l'utente dalla pagina che sta usando.
    const giaDentro = decisoPer.current === pathname;
    decisoPer.current = pathname;

    if (
      deveRimbalzareSuMobile({
        isPhone: isMobile,
        pathname,
        giaDentro,
        preferisceDesktop: preferisceDesktop(),
      })
    ) {
      router.replace("/m");
    }
  }, [isMobile, pathname, router]);

  return null;
}
