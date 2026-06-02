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
 * Mark ONEFLUX (F3): doppio anello = la "O" di One (esterno spesso, interno fine),
 * X a tratti curvi = la "X" di fluX che evoca il flusso.
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
      {/* O = doppio anello: esterno spesso, interno fine */}
      <circle cx="50" cy="50" r="42" stroke={stroke} strokeWidth="6" fill="none" />
      <circle cx="50" cy="50" r="31" stroke={stroke} strokeWidth="2.5" fill="none" />
      {/* X = due tratti curvi a flusso */}
      <path d="M36 36 C48 44 48 56 64 64" stroke={stroke} strokeWidth="7" strokeLinecap="round" />
      <path d="M64 36 C52 44 52 56 36 64" stroke={stroke} strokeWidth="7" strokeLinecap="round" />
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
