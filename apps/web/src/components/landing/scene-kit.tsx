"use client";

// Primitivi dello scrollytelling: wrapper scena a tutto schermo, reveal-on-scroll
// e sfondo sfocato atmosferico. Reveal e snap rispettano prefers-reduced-motion.

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { cn } from "@/lib/utils";

// Reveal: il figlio entra (fade + leggero translate) quando la scena è in viewport.
// Con reduced-motion appare subito visibile, senza animazione.
// variant "up" = sale dal basso (testi); "zoom" = sale + scala leggera (immagini,
// dà profondità). L'entrata è ampia abbastanza da percepirsi, ma morbida.
type RevealVariant = "up" | "zoom";

const REVEAL_HIDDEN: Record<RevealVariant, string> = {
  up: "translate-y-10 opacity-0",
  // dissolvenza immagini piu' marcata: scala piu' bassa + risalita maggiore, cosi'
  // l'entrata si percepisce bene (richiesto su PC e mobile).
  zoom: "translate-y-14 scale-[0.88] opacity-0",
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
    // root = il contenitore che scrolla davvero (div h-dvh overflow-y-scroll), non
    // il viewport: su mobile lo scroll-snap vive dentro quel div, e osservare la
    // FINESTRA faceva partire l'animazione tardi/mai (sembrava "senza dissolvenza").
    // rootMargin negativo in basso: la scena si rivela quando entra davvero, non al
    // primo pixel. threshold 0 + rootMargin = scatto affidabile anche col dito.
    const scroller = el.closest<HTMLElement>("[data-scroll-root]") ?? null;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setVisibile(true);
          io.disconnect();
        }
      },
      { root: scroller, threshold: 0.01, rootMargin: "0px 0px -12% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Due velocità: i TESTI entrano svelti (850ms); le IMMAGINI più lente e con
  // dissolvenza più morbida (transform 1500ms, opacity 1900ms) -> il fade si
  // "stende" oltre il movimento, dando l'entrata graduale richiesta.
  const ease = "cubic-bezier(0.16, 1, 0.3, 1)";
  const style: CSSProperties =
    variant === "zoom"
      ? {
          transitionProperty: "transform, opacity",
          transitionDuration: "1500ms, 1900ms",
          transitionTimingFunction: `${ease}, ease-out`,
          transitionDelay: visibile ? `${delay}ms` : "0ms",
        }
      : {
          transitionProperty: "transform, opacity",
          transitionDuration: "850ms",
          transitionTimingFunction: ease,
          transitionDelay: visibile ? `${delay}ms` : "0ms",
        };

  return (
    <div
      ref={ref}
      className={cn(
        "will-change-transform motion-reduce:!transition-none",
        visibile ? "translate-y-0 scale-100 opacity-100" : REVEAL_HIDDEN[variant],
        className,
      )}
      style={style}
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
        // min-h-dvh + snap-start: la scena aggancia in cima al viewport (snap
        // preciso, niente spazio nero) ma puo' CRESCERE se il contenuto e' alto,
        // senza tagliarlo (overflow-y-auto invece di hidden). justify-center
        // centra quando c'e' spazio. py contenuto perche' tutto ci stia.
        "relative flex min-h-dvh w-full shrink-0 snap-start flex-col items-center justify-center overflow-y-auto px-5 py-14 text-center",
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
