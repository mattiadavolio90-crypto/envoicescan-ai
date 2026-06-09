"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

// Rete di sicurezza per i cold-start del worker (Railway scale-to-zero).
//
// Quando un blocco Server Component (briefing / kpi / salute) torna vuoto perche'
// il worker era addormentato e ha sforato il timeout di 8s, prima si vedeva un
// fallback muto e il contenuto compariva SOLO ricaricando a mano. Qui invece:
// montiamo questo componente nel fallback, ripinghiamo l'endpoint proxy con un
// piccolo backoff e, appena il worker risponde, facciamo router.refresh() — i
// Server Component si ri-renderizzano e il blocco appare DA SOLO.
//
// Il keep-alive (.github/workflows/keepalive_worker.yml) tiene il worker caldo
// nelle ore di uso: questo retry copre i casi residui (deploy, riavvii).

// Backoff progressivo: copre la rigenerazione in background del briefing, che su
// clienti con molte fatture (full-load righe + alert prezzi) puo' richiedere
// qualche decina di secondi. Prima si fermava a ~20s e mostrava il fallback
// "piu' lento del solito" mentre il background stava ancora lavorando.
const BACKOFF_MS = [1500, 3000, 6000, 10000, 12000, 15000];

type Props = {
  /** Endpoint proxy Next da ripingare, es. "/api/home/briefing". */
  endpoint: string;
  /** Skeleton mostrato mentre si attende il worker. */
  children: React.ReactNode;
};

export function BlockRetry({ endpoint, children }: Props) {
  const router = useRouter();
  const attempt = useRef(0);
  const [exhausted, setExhausted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      if (cancelled) return;
      try {
        const res = await fetch(endpoint, { cache: "no-store" });
        if (cancelled) return;
        if (res.ok) {
          // Il worker e' tornato disponibile: ri-renderizza i Server Component
          // cosi' il blocco appare con i dati reali. router.refresh() non perde
          // lo stato client del resto della pagina.
          router.refresh();
          return;
        }
      } catch {
        /* worker ancora giu'/cold: continuiamo col backoff */
      }
      const next = BACKOFF_MS[attempt.current];
      attempt.current += 1;
      if (next === undefined) {
        setExhausted(true);
        return;
      }
      timer = setTimeout(tick, next);
    }

    timer = setTimeout(tick, BACKOFF_MS[0]);
    attempt.current = 1;
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [endpoint, router]);

  if (exhausted) {
    // Dopo qualche tentativo a vuoto smettiamo di pingare e offriamo il refresh
    // manuale, senza loop infinito.
    return (
      <button
        type="button"
        onClick={() => router.refresh()}
        className="w-full rounded-2xl border border-dashed bg-muted/30 py-6 text-center text-sm text-muted-foreground transition-colors hover:bg-muted/50"
      >
        Caricamento più lento del solito. Tocca per riprovare.
      </button>
    );
  }

  return <>{children}</>;
}
