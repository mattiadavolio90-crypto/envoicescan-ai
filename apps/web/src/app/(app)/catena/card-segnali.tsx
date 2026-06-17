"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, TrendingDown, Tag, CalendarX, ArrowRight, CheckCircle2 } from "lucide-react";
import { type Segnale, type SegnaliGruppo } from "@/lib/gruppo";

const ICONA: Record<Segnale["tipo"], typeof AlertTriangle> = {
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

  useEffect(() => {
    let alive = true;
    fetch("/api/gruppo/segnali", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (alive) setData(j);
      })
      .catch(() => {})
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const segnali = data?.segnali ?? [];

  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <AlertTriangle className="size-4" />
        Da vedere nella catena
      </div>

      {loading ? (
        <p className="mt-3 text-sm text-muted-foreground">Controllo i punti vendita…</p>
      ) : segnali.length === 0 ? (
        <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-emerald-500" />
          Tutto sotto controllo, nessuna segnalazione.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {segnali.map((s, i) => {
            const Icon = ICONA[s.tipo] ?? AlertTriangle;
            return (
              <li
                key={`${s.tipo}-${s.ristorante_id}-${i}`}
                className="flex items-start gap-3 rounded-xl border bg-background/40 p-3"
              >
                <Icon className="mt-0.5 size-4 shrink-0 text-amber-500" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-semibold text-muted-foreground">{s.pv_nome}</div>
                  <div className="text-sm">{s.testo}</div>
                </div>
                <button
                  type="button"
                  disabled={switching}
                  onClick={() => vaiAlPV(s.ristorante_id, s.cta_page)}
                  className="inline-flex shrink-0 items-center gap-1 self-center rounded-md px-2 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent disabled:opacity-50"
                >
                  Vedi PV
                  <ArrowRight className="size-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
