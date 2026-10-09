"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { type SegnaliGruppo } from "@/lib/gruppo";
import type { Notifica } from "@/lib/notifiche-shared";
import { daFareCatena, MAX_SEDI_VISIBILI, type SedeDaFare, type VoceDaFare } from "@/lib/home-da-fare";
import { IconaSeverita, NotaControllo, RigaVoce, TuttoInOrdine } from "@/components/home/da-fare-oggi";

type Avvisi = { notifiche?: Notifica[]; sedi_non_lette?: string[] };

// «Da fare oggi» della Home di catena: segnali, osservazioni e avvisi di ogni
// punto vendita in un elenco solo, una riga chiusa per sede (fase G, 9/10/2026).
// Prende il posto anche del pulsante «Vedi tutti gli avvisi».
//
// Segnali e avvisi si leggono dopo il render della Home (i segnali sono in
// cache 1×/giorno, ma il primo calcolo del giorno costa). Cosa mostrare,
// compreso «un errore non e' mai tutto in ordine», lo decide daFareCatena in
// lib/, dove e' provato.
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
  const [avvisi, setAvvisi] = useState<Avvisi | null>(null);
  const [erroreAvvisi, setErroreAvvisi] = useState(false);
  const [archiviati, setArchiviati] = useState<Set<string>>(new Set());
  const [inCorso, setInCorso] = useState<Set<string>>(new Set());
  const reqRef = useRef(0);

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoadError(false);
    setErroreAvvisi(false);
    fetch("/api/gruppo/segnali", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) setLoadError(true);
      });
    fetch("/api/gruppo/notifiche", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setAvvisi(j);
      })
      .catch(() => {
        if (my === reqRef.current) setErroreAvvisi(true);
      });
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  async function archivia(v: VoceDaFare) {
    if (!v.rif) return;
    setInCorso((prev) => new Set(prev).add(v.id));
    try {
      const res = await fetch("/api/notifiche/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: v.rif }),
      });
      if (!res.ok) throw new Error();
      // Sparisce SOLO se il worker l'ha archiviato: altrimenti tornerebbe al
      // prossimo caricamento.
      setArchiviati((prev) => new Set(prev).add(v.id));
    } catch {
      toast.error("Non sono riuscito ad archiviare l'avviso. Riprova.");
    } finally {
      setInCorso((prev) => {
        const next = new Set(prev);
        next.delete(v.id);
        return next;
      });
    }
  }

  const { generali, sedi, totale, avviso, notaAvvisi, verde } = daFareCatena({
    segnali: data,
    errore: loadError,
    avvisi,
    erroreAvvisi,
    nDaCollocare,
    archiviati,
  });

  const nota = avviso ? <NotaControllo avviso={avviso} onRiprova={carica} /> : null;
  const notaLettura = notaAvvisi ? (
    <p className="flex items-start gap-2 rounded-md border border-incerto/30 bg-incerto/10 px-3 py-2 text-xs text-incerto">
      <AlertTriangle className="mt-px size-3.5 shrink-0" />
      {notaAvvisi}
    </p>
  ) : null;

  const riga = (v: VoceDaFare) => (
    <RigaVoce
      key={v.id}
      voce={v}
      occupata={inCorso.has(v.id)}
      onIgnora={archivia}
      onVaiSede={(id, pagina) => vaiAlPV(id, pagina)}
      cambioSede={switching}
    />
  );

  const sede = (s: SedeDaFare) => (
    <details key={s.ristoranteId} className="group rounded-xl border bg-card">
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4 [&::-webkit-details-marker]:hidden">
        <IconaSeverita severity={s.severity} />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold" title={s.nome}>
          {s.nome}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">{s.conteggio}</span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-2 border-t p-3">{s.voci.map(riga)}</div>
    </details>
  );

  if (totale === 0) {
    if (nota || notaLettura) {
      return (
        <div className="space-y-2">
          {nota}
          {notaLettura}
        </div>
      );
    }
    if (verde) return <TuttoInOrdine />;
    return null;
  }

  const altre = sedi.slice(MAX_SEDI_VISIBILI);
  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-muted-foreground">
        Da fare oggi
        <span className="ml-1.5 text-muted-foreground/60">({totale})</span>
      </h2>
      {generali.map(riga)}
      {sedi.slice(0, MAX_SEDI_VISIBILI).map(sede)}
      {altre.length > 0 && (
        <details className="group/altre">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 text-sm font-medium text-primary-text [&::-webkit-details-marker]:hidden">
            {altre.length === 1 ? "Un altro punto vendita" : `Altri ${altre.length} punti vendita`}
            <ChevronDown className="size-4 transition-transform group-open/altre:rotate-180" />
          </summary>
          <div className="mt-3 space-y-3">{altre.map(sede)}</div>
        </details>
      )}
      {nota}
      {notaLettura}
    </div>
  );
}
