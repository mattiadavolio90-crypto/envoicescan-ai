"use client";

import { useCallback, useState } from "react";
import { useAssistente } from "@/components/home/assistente-provider";
import type { StatoAscolta } from "@/components/ascolta-button";
import { modoAvatar, type ModoAvatar } from "@/lib/avatar-flusso";

/** Il modo dell'avatar sulla Home del telefono (fase L): parla con «Ascolta», pensa mentre
 *  l'assistente risponde. «Ti ascolto» lì non c'è: la chat del telefono è in un'altra pagina. */
export function useModoAvatar(): { modo: ModoAvatar; suStato: (stato: StatoAscolta) => void } {
  const { inCorso } = useAssistente();
  const [parla, setParla] = useState(false);
  const suStato = useCallback((stato: StatoAscolta) => {
    if (stato === "playing") setParla(true);
    else if (stato === "idle") setParla(false);
  }, []);
  return { modo: modoAvatar({ parla, pensa: inCorso !== null, ascolta: false }), suStato };
}
