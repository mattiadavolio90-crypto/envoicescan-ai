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
 * Wordmark "ONEFLUX": SVG unico dove la "O" e' il doppio anello del logo e la
 * "X" finale e' il flusso a tratti curvi; le lettere centrali NEFLU sono testo
 * nel font wordmark (Quicksand 700, var --font-wordmark da layout). currentColor
 * eredita da text-primary; altezza in em -> scala col font-size del contenitore.
 * Geometria definita nell'editor (wordmark_editor.html), allineamento ottico.
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
    <svg
      viewBox="0 0 398 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="ONEFLUX"
      className={cn("inline-block w-auto align-middle text-primary", className)}
      style={{
        height: "1em",
        ...(glow ? { filter: "drop-shadow(0 0 2px currentColor)" } : {}),
        ...style,
      }}
    >
      {/* O = doppio anello del logo, valori identici (r 42/31, stroke 6/2.5) */}
      <g transform="translate(8 7) scale(0.87)">
        <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" />
        <circle cx="50" cy="50" r="31" stroke="currentColor" strokeWidth="2.5" fill="none" />
      </g>
      <text
        x="100"
        y="74"
        fontFamily="var(--font-wordmark), 'Quicksand', sans-serif"
        fontWeight="700"
        fontSize="68"
        letterSpacing="3.5"
        fill="currentColor"
      >
        NEFLU
      </text>
      {/* X = path LETTERALI del logo (stessa curvatura), scalati: stroke 3.59*1.95 = 7 visivi */}
      <g transform="translate(265.19 -48.5) scale(1.95)">
        <path d="M36 36 C48 44 48 56 64 64" stroke="currentColor" strokeWidth="3.59" strokeLinecap="round" fill="none" />
        <path d="M64 36 C52 44 52 56 36 64" stroke="currentColor" strokeWidth="3.59" strokeLinecap="round" fill="none" />
      </g>
    </svg>
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
