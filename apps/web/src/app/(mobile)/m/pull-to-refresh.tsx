"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, ArrowDown } from "lucide-react";

// Pull-to-refresh nativo: trascini verso il basso dall'alto della pagina e
// rilasci per ricaricare i dati (router.refresh() rigenera i server component).
// Niente librerie: gestione touch manuale, attiva solo quando si e' gia' in cima.
const SOGLIA = 70; // px di trascinamento per far scattare il refresh
const MAX = 100; // px massimi di "elastico"

export function PullToRefresh() {
  const router = useRouter();
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef<number | null>(null);
  const attivo = useRef(false);

  useEffect(() => {
    function onTouchStart(e: TouchEvent) {
      // Solo se la pagina e' gia' scrollata in cima.
      if (window.scrollY > 0) {
        attivo.current = false;
        return;
      }
      attivo.current = true;
      startY.current = e.touches[0].clientY;
    }

    function onTouchMove(e: TouchEvent) {
      if (!attivo.current || startY.current === null || refreshing) return;
      const delta = e.touches[0].clientY - startY.current;
      if (delta <= 0) {
        setPull(0);
        return;
      }
      // Resistenza elastica: piu' tiri, meno cede.
      const eased = Math.min(MAX, delta * 0.5);
      setPull(eased);
    }

    async function onTouchEnd() {
      if (!attivo.current) return;
      attivo.current = false;
      startY.current = null;
      if (pull >= SOGLIA && !refreshing) {
        setRefreshing(true);
        setPull(SOGLIA);
        // Rinfresca i server component (Home, Avvisi)...
        router.refresh();
        // ...e segnala ai client component (Diario, Turni) di ricaricare i dati.
        window.dispatchEvent(new CustomEvent("oneflux:refresh"));
        // Diamo un attimo perche' il refresh server completi, poi rilasciamo.
        setTimeout(() => {
          setRefreshing(false);
          setPull(0);
        }, 900);
      } else {
        setPull(0);
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
  }, [pull, refreshing, router]);

  if (pull === 0 && !refreshing) return null;

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
