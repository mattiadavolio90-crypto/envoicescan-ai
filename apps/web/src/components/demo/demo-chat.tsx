"use client";

import { useEffect, useState } from "react";
import { PannelloConversazione } from "@/components/home/pannello-conversazione";
import { fmtCrediti, type VoceChat } from "@/lib/home-chat";
import { demoChatScambio, demoChatSuggerimenti } from "@/lib/demo-data";

// La conversazione del Demo Tour, dentro il riquadro del briefing come nella
// Home vera (28/9/2026: niente piu' pulsante flottante). Stesso pannello del
// prodotto (PannelloConversazione), ma NIENTE fetch a /api/chat, niente
// sessionStorage, niente quota vera. Quando lo step chat e' attivo «recita» due
// scambi: domanda → l'assistente pensa → risposta, poi il follow-up (dove
// trovare il messaggio di trattativa per il fornitore). Il campo resta inerte.

// Fase = quanti "eventi" della sceneggiatura sono avvenuti:
//   0 vuota · 1 domanda1 · 2 pensa1 · 3 risposta1 · 4 domanda2 · 5 pensa2 · 6 risposta2
type Fase = 0 | 1 | 2 | 3 | 4 | 5 | 6;

const TEMPI: { fase: Fase; ms: number }[] = [
  { fase: 1, ms: 500 },
  { fase: 2, ms: 1300 },
  { fase: 3, ms: 2900 },
  { fase: 4, ms: 5200 },
  { fase: 5, ms: 6000 },
  { fase: 6, ms: 7600 },
];

const VISTA = "demo";

export function DemoConversazione({ attiva }: { attiva: boolean }) {
  const [fase, setFase] = useState<Fase>(0);

  useEffect(() => {
    if (!attiva) {
      setFase(0);
      return;
    }
    const timers = TEMPI.map((t) => setTimeout(() => setFase(t.fase), t.ms));
    return () => timers.forEach(clearTimeout);
  }, [attiva]);

  const [domanda1, risposta1, domanda2, risposta2] = demoChatScambio;
  const voci: VoceChat[] = [
    ...(fase >= 1 ? [{ ...domanda1, vista: VISTA }] : []),
    ...(fase >= 3 ? [{ ...risposta1, vista: VISTA }] : []),
    ...(fase >= 4 ? [{ ...domanda2, vista: VISTA }] : []),
    ...(fase >= 6 ? [{ ...risposta2, vista: VISTA }] : []),
  ];
  // Base: 1.000 crediti al mese, 3 a domanda (fase J).
  const rimanenti = 1000 - 3 * (fase >= 6 ? 2 : fase >= 3 ? 1 : 0);

  return (
    <PannelloConversazione
      ancoraDemo="chat"
      voci={voci}
      attesa={fase === 2 ? "Sto leggendo le tue fatture..." : fase === 5 ? "Guardo i tuoi fornitori..." : null}
      suggerimenti={fase === 0 ? demoChatSuggerimenti : null}
      valore=""
      placeholder="Chiedimi dei tuoi costi, fornitori, margini…"
      bloccato
      stato={`Ti restano ${fmtCrediti(rimanenti)} crediti`}
    />
  );
}
