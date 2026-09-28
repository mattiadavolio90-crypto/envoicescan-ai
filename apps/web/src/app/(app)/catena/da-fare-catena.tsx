"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type SegnaliGruppo } from "@/lib/gruppo";
import { daFareCatena } from "@/lib/home-da-fare";
import { DaFareOggi } from "@/components/home/da-fare-oggi";

// «Da fare oggi» della Home di catena (28/9/2026): stesso componente del punto
// vendita, con i dati del gruppo — segnali, osservazioni e fatture da
// collocare. Prende il posto della card «Da vedere nella catena».
//
// I segnali si leggono dopo il render della Home (sono in cache 1×/giorno, ma
// il primo calcolo del giorno costa). Cosa mostrare, compreso «un errore non
// e' mai tutto in ordine», lo decide daFareCatena in lib/, dove e' provato.
export function DaFareCatena({
  nDaCollocare,
  vaiAlPV,
  switching,
}: {
  nDaCollocare: number | null | undefined;
  vaiAlPV: (ristoranteId: string, page?: string) => void;
  switching: boolean;
}) {
  const [data, setData] = useState<SegnaliGruppo | null>(null);
  const [loadError, setLoadError] = useState(false);
  const reqRef = useRef(0);

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoadError(false);
    fetch("/api/gruppo/segnali", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) setLoadError(true);
      });
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  const { voci, avviso, verde } = daFareCatena({ segnali: data, errore: loadError, nDaCollocare });

  return (
    <DaFareOggi
      voci={voci}
      verde={verde}
      avviso={avviso}
      onRiprova={carica}
      onVaiSede={(id, pagina) => vaiAlPV(id, pagina)}
      cambioSede={switching}
    />
  );
}
