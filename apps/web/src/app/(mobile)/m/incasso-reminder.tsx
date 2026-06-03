"use client";

import { useEffect } from "react";

// Innesca la (ri)generazione dell'avviso "manca l'incasso di ieri" lato server,
// che alimenta il badge della campanella. Stesso principio del desktop, dove la
// notifica scadenze si rigenera all'apertura del tab Scadenziario: qui parte
// all'avvio della sezione mobile.
//
// Fire-and-forget: niente UI, niente navigazione (lontano dal bug PWA "couldn't
// load"). Guard giornaliero in sessionStorage: una sola chiamata per sessione+
// giorno, cosi' non parte a ogni cambio tab. L'endpoint e' comunque idempotente.
export function IncassoReminder() {
  useEffect(() => {
    try {
      const oggi = new Date().toISOString().slice(0, 10);
      const key = `oneflux:incasso-reminder:${oggi}`;
      if (sessionStorage.getItem(key)) return;
      sessionStorage.setItem(key, "1");
    } catch {
      // sessionStorage non disponibile: procedi comunque (idempotente lato server).
    }
    fetch("/api/ricavi/notifica-mancante", { method: "POST" }).catch(() => {});
  }, []);

  return null;
}
