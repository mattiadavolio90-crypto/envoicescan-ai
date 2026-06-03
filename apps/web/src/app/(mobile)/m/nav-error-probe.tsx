"use client";

import { useEffect } from "react";
import { toast } from "sonner";

// SONDA DIAGNOSTICA TEMPORANEA (rimuovere una volta confermata la causa).
// Cattura gli errori globali e i rejection non gestiti nel contesto PWA e li
// mostra a schermo (oltre che in console), cosi' possiamo finalmente LEGGERE il
// messaggio/URL reale che accompagna il "couldn't load" al primo tocco, invece
// di dedurlo. Non altera il comportamento dell'app.
export function NavErrorProbe() {
  useEffect(() => {
    function onError(e: ErrorEvent) {
      const msg = e?.message || String(e?.error || "errore");
      console.error("[probe] error:", msg, e?.filename, e?.lineno);
      toast.error(`DEBUG error: ${msg}`.slice(0, 160));
    }
    function onRejection(e: PromiseRejectionEvent) {
      const r = e?.reason;
      const msg = r?.message || String(r || "rejection");
      console.error("[probe] unhandledrejection:", msg);
      toast.error(`DEBUG rejection: ${msg}`.slice(0, 160));
    }
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  return null;
}
