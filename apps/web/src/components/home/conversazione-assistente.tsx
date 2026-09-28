"use client";

import { useEffect, useState } from "react";
import {
  SUGGERIMENTI_CATENA,
  SUGGERIMENTI_SEDE,
  domandeRimanenti,
  mostraSuggerimenti,
  testoAttesa,
  testoContatore,
  type Vista,
} from "@/lib/home-chat";
import { useAssistente } from "./assistente-provider";
import { PannelloConversazione } from "./pannello-conversazione";

// La conversazione nel riquadro del briefing (28/9/2026): prende il posto del
// pulsante flottante «Chiedi a ONEFLUX». Lo stato e' in AssistenteProvider,
// qui la vista in cui si trova il cliente e la quota della sua vista.
export function ConversazioneAssistente({
  vista,
  limiteGiorno,
  domandeOggiIniziali,
}: {
  vista: Vista;
  limiteGiorno: number;
  domandeOggiIniziali: number;
}) {
  const { pronta, voci, inCorso, attesa, domande, entraIn, invia, nuova } = useAssistente();
  const [valore, setValore] = useState("");

  // La riga «Ora sei in…» si aggiunge solo dopo aver letto la conversazione
  // salvata: prima sarebbe aggiunta a una conversazione vuota, e persa.
  useEffect(() => {
    if (pronta) entraIn(vista);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pronta, vista.chiave, entraIn]);

  const domandeOggi = domande[vista.chiave] ?? domandeOggiIniziali;
  const rimanenti = domandeRimanenti(limiteGiorno, domandeOggi);
  const esaurite = rimanenti <= 0;
  const bloccato = inCorso !== null || esaurite;

  function manda(testo: string) {
    if (bloccato || !testo.trim()) return;
    setValore("");
    void invia(testo, vista, { limiteGiorno, domandeOggi });
  }

  return (
    <PannelloConversazione
      voci={voci}
      attesa={inCorso ? testoAttesa(attesa) : null}
      suggerimenti={
        !esaurite && mostraSuggerimenti(voci, vista)
          ? vista.contesto === "catena" ? SUGGERIMENTI_CATENA : SUGGERIMENTI_SEDE
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
      stato={testoContatore(rimanenti)}
      statoAvviso={esaurite}
      onNuova={nuova}
    />
  );
}
