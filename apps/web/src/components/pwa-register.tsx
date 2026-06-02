"use client";

import { useEffect } from "react";

// Registra il service worker (public/sw.js) una volta montata l'app.
// In dev lo saltiamo: niente cache che confonde durante lo sviluppo.
export function PwaRegister() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      /* registrazione SW fallita: l'app funziona comunque, solo niente PWA */
    });
  }, []);

  return null;
}
