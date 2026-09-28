"use client";

import { useState } from "react";
import { toast } from "sonner";
import { type Briefing } from "@/lib/home";
import { puoIgnorare } from "@/lib/briefing-shared";
import { statoAzioni } from "@/lib/briefing-azioni";
import { vociDaAzioniPV } from "@/lib/home-da-fare";
import { RiquadroAssistente } from "@/components/home/riquadro-assistente";
import { DaFareOggi } from "@/components/home/da-fare-oggi";

type Props = {
  briefing: Briefing;
  /** La conversazione con l'assistente, dentro il riquadro. Assente = chat non
   *  disponibile nel piano (o config non letta): il riquadro resta il briefing. */
  conversazione?: React.ReactNode;
};

// Home del punto vendita: riquadro dell'assistente + «Da fare oggi», con gli
// stessi componenti della Home di catena (28/9/2026).
export function HomeBriefing({ briefing, conversazione }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());

  async function dismiss(id: string) {
    setLoading((prev) => new Set(prev).add(id));
    try {
      const res = await fetch("/api/notifiche/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      if (!res.ok) throw new Error();
      // Nascondiamo la card solo se il dismiss e' andato a buon fine: altrimenti
      // sparirebbe dalla UI ma ricomparirebbe al refresh (stato incoerente).
      // Stesso comportamento della Home mobile.
      setDismissed((prev) => new Set(prev).add(id));
    } catch {
      toast.error("Non sono riuscito a ignorare l'avviso. Riprova.");
    } finally {
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  const visibili = briefing.azioni.filter((a) => !dismissed.has(a.id));
  const datiMancanti = briefing.dati_mancanti ?? [];
  // Il verde "tutto a posto" lo decide SOLO il backend (gateato su dati mancanti e
  // Salute): l'archiviazione locale non deve poterlo forzare. Se non ci sono card
  // visibili ma il backend non dice tutto_ok, mai il verde: la nota neutra se
  // mancano dati, altrimenti niente (la narrativa sopra dice gia' perche').
  const stato = statoAzioni(briefing.tutto_ok, visibili.length, datiMancanti.length);

  return (
    <section className="space-y-5">
      <RiquadroAssistente
        etichetta="Il tuo assistente"
        saluto={briefing.saluto}
        narrativa={briefing.narrativa}
        testoAscolta={`${briefing.saluto}. ${briefing.narrativa}`}
        chiaveGiorno={briefing.data}
      >
        {conversazione}
      </RiquadroAssistente>
      <DaFareOggi
        voci={stato === "lista" ? vociDaAzioniPV(visibili, puoIgnorare) : []}
        verde={stato === "verde"}
        datiMancanti={stato === "dati_mancanti" ? datiMancanti : undefined}
        onIgnora={dismiss}
        inCorso={loading}
      />
    </section>
  );
}
