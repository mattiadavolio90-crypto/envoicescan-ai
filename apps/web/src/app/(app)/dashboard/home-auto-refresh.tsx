"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

// La Home promette dati "aggiornati in tempo reale", ma dopo il primo render
// resta statica: se nel frattempo arriva un upload Invoicetronic o cambia una
// notifica, l'utente non lo vede finche' non ricarica a mano. Questo componente
// colma il gap SENZA polling continuo (che sprecherebbe risorse e batteria):
// quando l'utente torna sulla scheda dopo essere stato altrove, ri-renderizziamo
// i Server Component con router.refresh(). E' il momento in cui vuole vedere il
// dato fresco, ed e' anche quando e' piu' probabile che qualcosa sia cambiato.
//
// Throttle: ignoriamo i ritorni ravvicinati (< MIN_INTERVAL) per non rigenerare
// la Home se l'utente fa avanti-indietro tra le schede in pochi secondi.

const MIN_INTERVAL_MS = 30_000;

export function HomeAutoRefresh() {
  const router = useRouter();
  const lastRefresh = useRef<number>(Date.now());

  useEffect(() => {
    function maybeRefresh() {
      // Solo quando la scheda torna visibile (non quando la si lascia).
      if (document.visibilityState !== "visible") return;
      const now = Date.now();
      if (now - lastRefresh.current < MIN_INTERVAL_MS) return;
      lastRefresh.current = now;
      router.refresh();
    }

    document.addEventListener("visibilitychange", maybeRefresh);
    window.addEventListener("focus", maybeRefresh);
    return () => {
      document.removeEventListener("visibilitychange", maybeRefresh);
      window.removeEventListener("focus", maybeRefresh);
    };
  }, [router]);

  return null;
}
