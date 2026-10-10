"use client";

import { useEffect, useState } from "react";
import { statoCrediti, testoAttesa, vociDellaVista, type Conteggio, type QuotaCrediti, type Vista } from "@/lib/home-chat";
import { useAssistente } from "./assistente-provider";

// La conversazione di UNA vista, come la leggono la Home e `/m`: quali messaggi,
// quanti crediti restano, se si puo' scrivere. Una sola copia: la chat del
// telefono ne aveva una sua, e le due divergevano a ogni ritocco.
export function useConversazione({
  vista,
  quota,
  lettoAlle,
}: {
  vista: Vista;
  /** Tetti e crediti spesi come li ha letti la pagina (quotaDaConfig / quotaDaGruppo). */
  quota: QuotaCrediti;
  /** Quando il server ha letto il numero: cambia a ogni render della pagina,
   *  anche se il numero e' uguale (il mattino dopo, 0 com'era ieri mattina). */
  lettoAlle: number;
}) {
  const { voci: tutte, inCorso, attesa, crediti: risposta, invia, nuova, conferma, annulla } = useAssistente();
  const [valore, setValore] = useState("");
  const voci = vociDellaVista(tutte, vista.chiave);

  // Il numero della pagina, con il momento in cui e' arrivato: un router.refresh
  // o una Home riaperta lo rinnovano e vince su una risposta piu' vecchia.
  const { limiteGiorno, limiteMese, oggi, mese, ricarica } = quota;
  const [server, setServer] = useState<Conteggio>(() => ({ oggi, mese, ricarica, alle: Date.now() }));
  // `alle` e' l'ora del browser, non `lettoAlle`: gli orologi di server e
  // browser non si confrontano. `lettoAlle` serve solo a sapere che c'e' una
  // lettura nuova.
  useEffect(() => {
    setServer({ oggi, mese, ricarica, alle: Date.now() });
  }, [oggi, mese, ricarica, lettoAlle]);
  const { crediti, esaurite, testo, breve } = statoCrediti({ limiteGiorno, limiteMese }, server, risposta);
  const bloccato = inCorso !== null || esaurite;

  function manda(testoDomanda: string) {
    if (bloccato || !testoDomanda.trim()) return;
    setValore("");
    void invia(testoDomanda, vista, crediti);
  }

  return {
    voci,
    valore,
    setValore,
    esaurite,
    bloccato,
    /** La riga del contatore: «Ti restano 640 crediti». */
    stato: testo,
    /** Il segnaposto della casella ferma: «Limite di oggi raggiunto». */
    statoBreve: breve,
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
