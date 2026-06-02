"use client";

import { useEffect, useState } from "react";

// Overlay di avvio della PWA: copre lo splash statico del sistema operativo con
// l'animazione di brand (anelli che si espandono attorno al logo). Appare una
// sola volta per avvio dell'app (flag di sessione), poi svanisce sulla Home.
const SESSION_FLAG = "oneflux:splash-shown";
const DURATA = 1200; // ms visibile prima del fade-out
const FADE = 320; // ms del fade-out

export function SplashOverlay() {
  const [stato, setStato] = useState<"hidden" | "visible" | "closing">("hidden");

  useEffect(() => {
    try {
      if (sessionStorage.getItem(SESSION_FLAG) === "1") return;
      sessionStorage.setItem(SESSION_FLAG, "1");
    } catch {
      // sessionStorage non disponibile: mostriamo comunque una volta
    }
    setStato("visible");
    const t1 = setTimeout(() => setStato("closing"), DURATA);
    const t2 = setTimeout(() => setStato("hidden"), DURATA + FADE);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, []);

  if (stato === "hidden") return null;

  return (
    <div
      className={`oneflux-login-overlay${stato === "closing" ? " oneflux-login-overlay-out" : ""}`}
      style={{ zIndex: 100 }}
      aria-hidden
    >
      <div className="oneflux-login-stage" style={{ width: 160, height: 160 }}>
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-mark text-primary" style={{ width: 104, height: 104 }}>
          <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="size-full">
            <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" />
            <circle cx="50" cy="50" r="31" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <g className="oneflux-spinner-x" style={{ transformOrigin: "50% 50%" }}>
              <path d="M36 36 C48 44 48 56 64 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
              <path d="M64 36 C52 44 52 56 36 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
            </g>
          </svg>
        </span>
      </div>
    </div>
  );
}
