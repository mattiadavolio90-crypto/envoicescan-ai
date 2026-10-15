"use client";

import { useEffect, useRef } from "react";
import { DisegnoFlusso, type Puntatore } from "@/components/home/disegno-flusso";
import { avvicina, livelloVoce, voceSimulata, type ModoAvatar } from "@/lib/avatar-flusso";
import { cn } from "@/lib/utils";

// L'avatar dell'assistente (fase L, 15/10/2026): il flusso che ruota su se stesso, accanto
// al briefing da computer («colonna») e in cima alla Home del telefono («fascia»). Il modo
// arriva da chi lo usa; il cursore e il tema li legge da solo. Quando il canvas non si vede
// o la scheda è in secondo piano il ciclo non disegna (resta solo il frame vuoto).

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export function AvatarFlusso({
  modo,
  variante,
  className,
}: {
  modo: ModoAvatar;
  variante: "colonna" | "fascia";
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const modoRef = useRef(modo);
  useEffect(() => {
    modoRef.current = modo;
  }, [modo]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let disegno: DisegnoFlusso;
    try {
      disegno = new DisegnoFlusso(canvas, variante);
    } catch {
      return; // niente canvas 2D: la colonna resta vuota, il briefing funziona lo stesso
    }
    const menoAnimazioni = window.matchMedia("(prefers-reduced-motion: reduce)");
    const puntatore: Puntatore = { x: 0, y: 0, dentro: false };
    const muovi = (e: PointerEvent) => {
      puntatore.x = e.clientX;
      puntatore.y = e.clientY;
      puntatore.dentro = true;
    };
    const esci = () => {
      puntatore.dentro = false;
    };
    window.addEventListener("pointermove", muovi, { passive: true });
    document.documentElement.addEventListener("pointerleave", esci);
    let visibile = true;
    const osservatore = new IntersectionObserver(([voce]) => {
      visibile = voce?.isIntersecting ?? true;
    });
    osservatore.observe(canvas);

    let voce = 0, mx = 0, my = 0, ultimo = performance.now(), ultimoFermo = 0, id = 0;
    const ciclo = (ora: number) => {
      id = requestAnimationFrame(ciclo);
      const dt = Math.min(0.05, (ora - ultimo) / 1000);
      ultimo = ora;
      if (!visibile || document.hidden) return;
      const fermo = menoAnimazioni.matches;
      // Fermo: un disegno ogni mezzo secondo basta a seguire tema e dimensioni.
      if (fermo && ora - ultimoFermo < 500) return;
      ultimoFermo = ora;
      const m = modoRef.current;
      voce = livelloVoce(voce, m === "parla" ? voceSimulata(ora / 1000) : 0, dt);
      // Dove guarda: la casella della chat mentre scrivi, altrimenti il cursore.
      const r = canvas.getBoundingClientRect();
      let tx = 0, ty = 0;
      const fuoco = document.activeElement;
      const bersaglio =
        m === "ascolta" && fuoco instanceof HTMLElement && fuoco.matches("textarea, input")
          ? fuoco.getBoundingClientRect()
          : null;
      const gx = bersaglio ? bersaglio.left + bersaglio.width * 0.3 : puntatore.dentro ? puntatore.x : null;
      const gy = bersaglio ? bersaglio.top + bersaglio.height / 2 : puntatore.dentro ? puntatore.y : null;
      if (gx !== null && gy !== null) {
        // Il cursore conta solo vicino al flusso: lontano (sul menu, in fondo al briefing)
        // il flusso resta dritto invece di girarsi e spegnersi da un lato.
        const fuori = Math.hypot(Math.max(r.left - gx, 0, gx - r.right), Math.max(r.top - gy, 0, gy - r.bottom));
        const peso = bersaglio ? 0.6 : Math.exp(-fuori / 220);
        tx = clamp((gx - (r.left + r.width / 2)) / (window.innerWidth * 0.4), -1, 1) * peso;
        ty = clamp((gy - (r.top + r.height / 2)) / (window.innerHeight * 0.4), -1, 1) * peso;
      }
      mx = avvicina(mx, tx, 6, dt);
      my = avvicina(my, ty, 6, dt);
      disegno.disegna({
        t: ora / 1000,
        dt,
        modo: m,
        voce,
        mx,
        my,
        puntatore,
        scuro: document.documentElement.classList.contains("dark"),
        fermo,
      });
    };
    id = requestAnimationFrame(ciclo);
    return () => {
      cancelAnimationFrame(id);
      osservatore.disconnect();
      window.removeEventListener("pointermove", muovi);
      document.documentElement.removeEventListener("pointerleave", esci);
    };
  }, [variante]);

  return (
    <canvas
      ref={canvasRef}
      data-avatar-arrivo={variante}
      aria-hidden="true"
      className={cn("block h-full w-full", className)}
    />
  );
}
