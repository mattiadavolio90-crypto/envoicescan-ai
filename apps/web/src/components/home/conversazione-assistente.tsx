"use client";

import {
  domandeDalBriefing,
  mostraSuggerimenti,
  suggerimentiPer,
  type Vista,
} from "@/lib/home-chat";
import { PannelloConversazione } from "./pannello-conversazione";
import { useConversazione } from "./use-conversazione";

// La conversazione nel riquadro del briefing (28/9/2026): prende il posto del
// pulsante flottante «Chiedi a ONEFLUX». Lo stato e' in AssistenteProvider,
// qui la vista in cui si trova il cliente: si vede solo la sua conversazione
// (Mattia, 29/9), quella che l'assistente ricorda.
export function ConversazioneAssistente({
  vista,
  limiteGiorno,
  domandeOggiIniziali,
  lettoAlle,
  settore,
  temi,
}: {
  vista: Vista;
  /** Di cosa ha parlato il briefing della sede: ne nascono le domande
   *  proposte. Assente (catena, worker vecchio) = domande fisse. */
  temi?: readonly string[];
  /** Settore dell'account: i negozi hanno domande proposte loro. */
  settore?: string | null;
  limiteGiorno: number;
  domandeOggiIniziali: number;
  /** Quando il server ha letto il numero: cambia a ogni render della pagina,
   *  anche se il numero e' uguale (il mattino dopo, 0 com'era ieri mattina). */
  lettoAlle: number;
}) {
  const c = useConversazione({ vista, limiteGiorno, domandeOggiIniziali, lettoAlle });

  return (
    <PannelloConversazione
      voci={c.voci}
      attesa={c.attesa}
      suggerimenti={
        !c.esaurite && mostraSuggerimenti(c.voci, vista)
          ? vista.contesto === "sede" && temi?.length
            ? domandeDalBriefing(temi, settore, { registra: true })
            : suggerimentiPer(vista.contesto, settore)
          : null
      }
      onSuggerimento={c.manda}
      valore={c.valore}
      onCambia={c.setValore}
      onInvia={() => c.manda(c.valore)}
      placeholder={
        c.esaurite
          ? "Limite di oggi raggiunto"
          : c.inAltraVista
            // Una domanda alla volta per account: se aspetta la risposta in
            // un'altra vista, qui la casella e' ferma e deve dire perche'.
            ? "Sto rispondendo alla domanda che hai fatto in un'altra vista…"
            : vista.contesto === "catena"
            ? "Chiedimi dei tuoi punti vendita…"
            : "Chiedimi dei tuoi costi, fornitori, margini…"
      }
      bloccato={c.bloccato}
      stato={c.stato}
      statoAvviso={c.esaurite}
      onNuova={c.nuova}
      onConferma={c.conferma}
      onAnnulla={c.annulla}
    />
  );
}
