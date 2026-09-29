"use client";

import { useEffect, useState } from "react";
import {
  mostraSuggerimenti,
  suggerimentiPer,
  statoDomande,
  testoAttesa,
  vociDellaVista,
  type Conteggio,
  type Vista,
} from "@/lib/home-chat";
import { useAssistente } from "./assistente-provider";
import { PannelloConversazione } from "./pannello-conversazione";

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
}: {
  vista: Vista;
  /** Settore dell'account: i negozi hanno domande proposte loro. */
  settore?: string | null;
  limiteGiorno: number;
  domandeOggiIniziali: number;
  /** Quando il server ha letto il numero: cambia a ogni render della pagina,
   *  anche se il numero e' uguale (il mattino dopo, 0 com'era ieri mattina). */
  lettoAlle: number;
}) {
  const { voci: tutte, inCorso, attesa, domande, invia, nuova } = useAssistente();
  const [valore, setValore] = useState("");
  const voci = vociDellaVista(tutte, vista.chiave);

  // Il numero della pagina, con il momento in cui e' arrivato: un router.refresh
  // o una Home riaperta lo rinnovano e vince su una risposta piu' vecchia.
  const [server, setServer] = useState<Conteggio>(() => ({ valore: domandeOggiIniziali, alle: Date.now() }));
  // `alle` e' l'ora del browser, non `lettoAlle`: gli orologi di server e
  // browser non si confrontano. `lettoAlle` serve solo a sapere che c'e' una
  // lettura nuova.
  useEffect(() => {
    setServer({ valore: domandeOggiIniziali, alle: Date.now() });
  }, [domandeOggiIniziali, lettoAlle]);
  const { usate: domandeOggi, esaurite, testo } = statoDomande(limiteGiorno, server, domande);
  const bloccato = inCorso !== null || esaurite;

  function manda(testo: string) {
    if (bloccato || !testo.trim()) return;
    setValore("");
    void invia(testo, vista, { limiteGiorno, domandeOggi });
  }

  return (
    <PannelloConversazione
      voci={voci}
      attesa={inCorso === vista.chiave ? testoAttesa(attesa) : null}
      suggerimenti={
        !esaurite && mostraSuggerimenti(voci, vista)
          ? suggerimentiPer(vista.contesto, settore)
          : null
      }
      onSuggerimento={manda}
      valore={valore}
      onCambia={setValore}
      onInvia={() => manda(valore)}
      placeholder={
        esaurite
          ? "Limite di oggi raggiunto"
          : vista.contesto === "catena"
            ? "Chiedimi dei tuoi punti vendita…"
            : "Chiedimi dei tuoi costi, fornitori, margini…"
      }
      bloccato={bloccato}
      stato={testo}
      statoAvviso={esaurite}
      onNuova={() => nuova(vista.chiave)}
    />
  );
}
