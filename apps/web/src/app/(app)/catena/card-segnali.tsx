"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, TrendingDown, Tag, CalendarX, ArrowRight, CheckCircle2, ClipboardList } from "lucide-react";
import { type Segnale, type SegnaliGruppo } from "@/lib/gruppo";
import { raggruppaSegnali } from "@/lib/catena-segnali";
import { haDestinazione, osservazioniDaMostrare } from "@/lib/catena-osservazioni";

const ICONA: Record<Segnale["tipo"], typeof AlertTriangle> = {
  dati_mancanti: ClipboardList,
  margine_calo: TrendingDown,
  prezzi_sopra: Tag,
  ricavi_mancanti: CalendarX,
};

// "Da vedere nella catena": card-segnale (icona + badge PV + messaggio macro +
// "Vedi PV →"). Si idrata dopo la Sintesi (i segnali sono in cache 1×/giorno,
// ma il primo calcolo del giorno può costare → fuori dal render bloccante).
export function CardSegnali({
  vaiAlPV,
  switching,
}: {
  vaiAlPV: (ristoranteId: string, page?: string) => void;
  switching: boolean;
}) {
  const [data, setData] = useState<SegnaliGruppo | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const reqRef = useRef(0);

  // Un errore qui NON può diventare "tutto sotto controllo": questa card esiste per
  // avvisare, e tacere su un errore darebbe una rassicurazione falsa.
  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    fetch("/api/gruppo/segnali", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) setLoadError(true);
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, []);

  useEffect(() => {
    carica();
  }, [carica]);

  const segnali = raggruppaSegnali(data?.segnali ?? []);
  const osservazioni = osservazioniDaMostrare(data);

  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <AlertTriangle className="size-4" />
        Da vedere nella catena
      </div>

      {/* Le osservazioni da consulente (fase 6) stanno SOPRA i segnali e fuori
          dal loro conteggio: sono fatti sull'andamento, non compiti, e non
          spengono il "tutto sotto controllo" qui sotto. */}
      {!loading && osservazioni.length > 0 ? (
        <div className="mt-3">
          <div className="text-xs font-medium text-muted-foreground">Da sapere</div>
          <ul className="mt-2 space-y-2">
            {osservazioni.map((o, i) => (
              <li
                key={`${o.tipo}-${o.ristorante_id}-${i}`}
                className="flex items-start gap-3 rounded-xl border bg-background/40 p-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-semibold text-muted-foreground" title={o.pv_nome}>
                    {o.pv_nome}
                  </div>
                  <div className="text-sm">{o.testo}</div>
                </div>
                {haDestinazione(o) ? (
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => vaiAlPV(o.ristorante_id, o.cta_page)}
                    className="inline-flex shrink-0 items-center gap-1 self-center rounded-md px-2 py-1 text-xs font-medium text-primary-text transition-colors hover:bg-accent disabled:opacity-50"
                  >
                    Vedi PV
                    <ArrowRight className="size-3.5" />
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {loading ? (
        <p className="mt-3 text-sm text-muted-foreground">Controllo i punti vendita…</p>
      ) : loadError && !data ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <AlertTriangle className="size-4 text-negativo" />
          Non è stato possibile controllare i punti vendita.
          <button
            type="button"
            onClick={carica}
            className="text-xs font-medium text-primary transition-colors hover:underline"
          >
            Riprova
          </button>
        </div>
      ) : segnali.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-positivo" />
          Tutto sotto controllo, nessuna segnalazione.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {segnali.map((s, i) => {
            const Icon = ICONA[s.tipo] ?? AlertTriangle;
            const nomi = s.pv.map((p) => p.pv_nome).join(" · ");
            return (
              <li
                key={`${s.tipo}-${s.pv[0].ristorante_id}-${i}`}
                className="flex items-start gap-3 rounded-xl border bg-background/40 p-3"
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-incerto" />
                <div className="min-w-0 flex-1">
                  {/* Il `title` porta i nomi per intero: raggruppando, questa
                      riga puo' elencare 5 PV e il troncamento renderebbe il
                      dato irrecuperabile dall'interfaccia. */}
                  <div className="truncate text-xs font-semibold text-muted-foreground" title={nomi}>
                    {s.pv.length > 1 ? `${s.pv.length} punti vendita · ${nomi}` : nomi}
                  </div>
                  <div className="text-sm">{s.testo}</div>
                </div>
                {/* Il bottone e' una DESTINAZIONE: lo si rende solo quando ce
                    n'e' una sola. Con piu' PV raggruppati manderebbe l'utente
                    su un PV arbitrario — lo stesso motivo per cui non si rende
                    sui segnali senza ristorante_id ("non e' stato possibile
                    controllare"), che non sono destinazioni. */}
                {s.pv.length === 1 && s.pv[0].ristorante_id ? (
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => vaiAlPV(s.pv[0].ristorante_id, s.pv[0].cta_page)}
                    className="inline-flex shrink-0 items-center gap-1 self-center rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent disabled:opacity-50"
                  >
                    Vedi PV
                    <ArrowRight className="size-3.5" />
                  </button>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
