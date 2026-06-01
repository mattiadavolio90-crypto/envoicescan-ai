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
 * Spinner di brand: il box ONEFLUX pulsa col glow neon e la X interna ruota
 * (X -> rombo -> X), loop infinito. Sostituisce gli spinner generici.
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
          <path
            className="oneflux-spinner-x"
            d="M31 31 L69 69 M69 31 L31 69"
            stroke="currentColor"
            strokeWidth="7.5"
            strokeLinecap="square"
          />
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
