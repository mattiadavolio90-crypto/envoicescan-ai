"use client";

import { cn } from "@/lib/utils";

type LogoSpinnerProps = {
  size?: number;
  label?: string;
  className?: string;
  fullscreen?: boolean;
  glow?: boolean;
};

/**
 * Spinner di brand (F3): l'anello pulsa col glow e la X curva ruota, loop infinito.
 * Sostituisce gli spinner generici.
 */
export function LogoSpinner({ size = 40, label, className, fullscreen = false, glow = false }: LogoSpinnerProps) {
  const spinner = (
    <span className={cn("inline-flex flex-col items-center gap-3", className)} role="status" aria-label={label ?? "Caricamento"}>
      <span
        className={cn("oneflux-spinner text-primary", glow && "oneflux-spinner-glow")}
        style={{ width: size, height: size }}
      >
        <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="size-full">
          <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" />
          <circle cx="50" cy="50" r="31" stroke="currentColor" strokeWidth="2.5" fill="none" />
          <g className="oneflux-spinner-x">
            <path d="M36 36 C48 44 48 56 64 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
            <path d="M64 36 C52 44 52 56 36 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
          </g>
        </svg>
      </span>
      {label ? <span className="text-sm text-muted-foreground">{label}</span> : null}
    </span>
  );

  if (fullscreen) {
    return (
      <div className="flex min-h-[40vh] w-full items-center justify-center">{spinner}</div>
    );
  }

  return spinner;
}
