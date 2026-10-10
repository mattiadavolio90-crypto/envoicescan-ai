"use client";

import { useEffect, useState } from "react";
import { statoDomande, testoAttesa, vociDellaVista, type Conteggio, type Vista } from "@/lib/home-chat";
import { useAssistente } from "./assistente-provider";

// La conversazione di UNA vista, come la leggono la Home e `/m`: quali messaggi,
// quante domande restano, se si puo' scrivere. Una sola copia: la chat del
// telefono ne aveva una sua, e le due divergevano a ogni ritocco.
export function useConversazione({
  vista,
  limiteGiorno,
  domandeOggiIniziali,
  lettoAlle,
}: {
  vista: Vista;
  limiteGiorno: number;
  domandeOggiIniziali: number;
  /** Quando il server ha letto il numero: cambia a ogni render della pagina,
   *  anche se il numero e' uguale (il mattino dopo, 0 com'era ieri mattina). */
  lettoAlle: number;
}) {
  const { voci: tutte, inCorso, attesa, domande, invia, nuova, conferma, annulla } = useAssistente();
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

  function manda(testoDomanda: string) {
    if (bloccato || !testoDomanda.trim()) return;
    setValore("");
    void invia(testoDomanda, vista, { limiteGiorno, domandeOggi });
  }

  return {
    voci,
    valore,
    setValore,
    esaurite,
    bloccato,
    /** La riga del contatore: «Ti restano 12 domande oggi». */
    stato: testo,
    /** Testo d'attesa mentre risponde a questa vista; null = nessuna attesa. */
    attesa: inCorso === vista.chiave ? testoAttesa(attesa) : null,
    /** Aspetta la risposta di un'altra vista: qui la casella e' ferma. */
    inAltraVista: inCorso !== null && inCorso !== vista.chiave,
    manda,
    nuova: () => nuova(vista.chiave),
    conferma: (id: string) => void conferma(id),
    annulla,
  };
}
