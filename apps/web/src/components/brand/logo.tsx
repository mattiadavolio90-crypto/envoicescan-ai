"use client";

import { cn } from "@/lib/utils";

type LogoVariant = "full" | "icon" | "mono";

type LogoProps = {
  variant?: LogoVariant;
  size?: number;
  glow?: boolean;
  className?: string;
  title?: string;
};

/**
 * Mark ONEFLUX: box quadrato = la "O" di One, X interna = la "X" di fluX.
 * La X mantiene un margine dagli angoli del box (non li tocca).
 * Il colore eredita da currentColor: di default segue il testo / primary.
 */
function LogoMark({ glow, mono }: { glow?: boolean; mono?: boolean }) {
  const stroke = mono ? "currentColor" : "var(--logo-mark, currentColor)";

  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="size-full"
      style={glow ? { filter: "drop-shadow(0 0 3px var(--logo-glow, currentColor))" } : undefined}
    >
      {/* Cerchio = O (bordo più sottile della X per gerarchia) */}
      <circle cx="50" cy="50" r="42" stroke={stroke} strokeWidth="6" fill="none" />
      {/* X interna = X, vicina al cerchio senza toccarlo, terminali netti */}
      <path
        d="M31 31 L69 69 M69 31 L31 69"
        stroke={stroke}
        strokeWidth="7.5"
        strokeLinecap="square"
      />
    </svg>
  );
}

/**
 * Wordmark "ONEFLUX": testo in primary con tracking e glow opzionale.
 * Da usare ovunque appaia il nome del brand come titolo/marchio.
 */
export function Wordmark({
  glow = false,
  className,
  style,
}: {
  glow?: boolean;
  className?: string;
  style?: React.CSSProperties;
}) {
  return (
    <span
      className={cn("font-semibold tracking-[0.14em] text-primary", className)}
      style={{ ...(glow ? { filter: "drop-shadow(0 0 2px currentColor)" } : {}), ...style }}
    >
      ONEFLUX
    </span>
  );
}

export function Logo({
  variant = "full",
  size = 32,
  glow = false,
  className,
  title = "ONEFLUX",
}: LogoProps) {
  const mono = variant === "mono";

  if (variant === "full") {
    return (
      <span className={cn("inline-flex items-center gap-3", className)} role="img" aria-label={title}>
        <span className="shrink-0 text-primary" style={{ width: size, height: size }}>
          <LogoMark glow={glow} />
        </span>
        <span className="flex flex-col leading-none">
          <Wordmark glow={glow} className="tracking-[0.18em]" style={{ fontSize: size * 0.5 }} />
        </span>
      </span>
    );
  }

  return (
    <span
      className={cn("inline-flex shrink-0", mono ? "text-current" : "text-primary", className)}
      style={{ width: size, height: size }}
      role="img"
      aria-label={title}
    >
      <LogoMark glow={glow} mono={mono} />
    </span>
  );
}
