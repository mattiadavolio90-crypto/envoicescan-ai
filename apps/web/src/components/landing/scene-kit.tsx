"use client";

// Primitivi dello scrollytelling: wrapper scena a tutto schermo, reveal-on-scroll
// e sfondo sfocato atmosferico. Reveal e snap rispettano prefers-reduced-motion.

import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

// Reveal: il figlio entra (fade + leggero translate) quando la scena è in viewport.
// Con reduced-motion appare subito visibile, senza animazione.
// variant "up" = sale dal basso (testi); "zoom" = sale + scala leggera (immagini,
// dà profondità). L'entrata è ampia abbastanza da percepirsi, ma morbida.
type RevealVariant = "up" | "zoom";

const REVEAL_HIDDEN: Record<RevealVariant, string> = {
  up: "translate-y-8 opacity-0",
  zoom: "translate-y-10 scale-[0.94] opacity-0",
};

export function Reveal({
  children,
  className,
  delay = 0,
  variant = "up",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  variant?: RevealVariant;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visibile, setVisibile] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ridotto = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (ridotto) {
      setVisibile(true);
      return;
    }
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setVisibile(true);
          io.disconnect();
        }
      },
      { threshold: 0.2 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={cn(
        "transition-all duration-[850ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] will-change-transform motion-reduce:transition-none",
        visibile ? "translate-y-0 scale-100 opacity-100" : REVEAL_HIDDEN[variant],
        className,
      )}
      style={{ transitionDelay: visibile ? `${delay}ms` : "0ms" }}
    >
      {children}
    </div>
  );
}

// Scena a tutto schermo. `center` centra il contenuto; il padding lascia respiro.
export function Scene({
  children,
  className,
  id,
}: {
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={cn(
        "relative flex min-h-dvh w-full snap-center flex-col items-center justify-center overflow-hidden px-5 py-24 text-center",
        className,
      )}
    >
      {children}
    </section>
  );
}

// Sfondo sfocato atmosferico: una pagina dell'app, illeggibile, come texture.
// Scurito ai bordi perché il testo resti leggibile sopra.
export function BlurBg({ src, alt = "" }: { src: string; alt?: string }) {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        className="size-full scale-110 object-cover opacity-[0.18] blur-2xl"
      />
      <div className="absolute inset-0 bg-gradient-to-b from-background via-background/60 to-background" />
      <div className="absolute inset-0 bg-background/40" />
    </div>
  );
}

// Occhiello (kicker) sopra il titolo di scena.
export function Kicker({ children }: { children: ReactNode }) {
  return (
    <p className="mb-5 text-sm font-semibold uppercase tracking-[0.2em] text-primary">{children}</p>
  );
}
