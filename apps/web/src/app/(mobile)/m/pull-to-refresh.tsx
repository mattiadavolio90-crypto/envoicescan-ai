"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Loader2, ArrowDown } from "lucide-react";

// Pull-to-refresh nativo: trascini verso il basso dall'alto della pagina e
// rilasci per ricaricare i dati. router.refresh() rigenera i server component
// (Home, Avvisi); l'evento "oneflux:refresh" fa ricaricare i client component
// (Diario, Turni). Gestione touch manuale, attiva solo quando si e' in cima.
const SOGLIA = 70; // px di trascinamento per far scattare il refresh
const MAX = 100; // px massimi di "elastico"

export function PullToRefresh() {
  const router = useRouter();
  const pathname = usePathname();
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  // Stato letto dentro i listener tenuto in ref: cosi' l'effetto si monta UNA
  // sola volta e i listener non vengono riattaccati a ogni pixel di trascinamento.
  const startY = useRef<number | null>(null);
  const attivo = useRef(false);
  const pullRef = useRef(0);
  const refreshingRef = useRef(false);

  // Sulla Chat il pull-to-refresh non serve (azzererebbe la conversazione) e
  // interferisce con lo scroll dei messaggi: disattivato lì.
  const disabilitato = pathname.startsWith("/m/chat");

  useEffect(() => {
    if (disabilitato) return;

    function setPullBoth(v: number) {
      pullRef.current = v;
      setPull(v);
    }

    function onTouchStart(e: TouchEvent) {
      if (window.scrollY > 0 || refreshingRef.current) {
        attivo.current = false;
        return;
      }
      attivo.current = true;
      startY.current = e.touches[0].clientY;
    }

    function onTouchMove(e: TouchEvent) {
      if (!attivo.current || startY.current === null || refreshingRef.current) return;
      const delta = e.touches[0].clientY - startY.current;
      if (delta <= 0) {
        setPullBoth(0);
        return;
      }
      setPullBoth(Math.min(MAX, delta * 0.5)); // resistenza elastica
    }

    function onTouchEnd() {
      if (!attivo.current) return;
      attivo.current = false;
      startY.current = null;
      if (pullRef.current >= SOGLIA && !refreshingRef.current) {
        refreshingRef.current = true;
        setRefreshing(true);
        setPullBoth(SOGLIA);
        router.refresh();
        window.dispatchEvent(new CustomEvent("oneflux:refresh"));
        setTimeout(() => {
          refreshingRef.current = false;
          setRefreshing(false);
          setPullBoth(0);
        }, 900);
      } else {
        setPullBoth(0);
      }
    }

    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    window.addEventListener("touchend", onTouchEnd);
    return () => {
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.removeEventListener("touchend", onTouchEnd);
    };
  }, [disabilitato, router]);

  if (disabilitato || (pull === 0 && !refreshing)) return null;

  const pronto = pull >= SOGLIA;

  return (
    <div
      className="pointer-events-none fixed inset-x-0 z-30 flex justify-center"
      style={{
        top: "calc(56px + env(safe-area-inset-top))",
        transform: `translateY(${pull - 20}px)`,
        opacity: Math.min(1, pull / SOGLIA),
        transition: refreshing ? "transform 0.2s" : "none",
      }}
    >
      <div className="flex size-9 items-center justify-center rounded-full border border-border bg-background shadow-md">
        {refreshing ? (
          <Loader2 className="size-4 animate-spin text-primary" />
        ) : (
          <ArrowDown
            className={`size-4 text-muted-foreground transition-transform ${pronto ? "rotate-180 text-primary" : ""}`}
          />
        )}
      </div>
    </div>
  );
}
