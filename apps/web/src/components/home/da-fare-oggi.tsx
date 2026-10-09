"use client";

import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  Check,
  CheckCircle,
  Info,
  XCircle,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { SeveritaVoce, VoceDaFare } from "@/lib/home-da-fare";

// «Da fare oggi», con le stesse righe nelle due Home (Mattia, 28/9); la catena
// le raggruppa per punto vendita (fase G). Le voci arrivano gia' decise
// (lib/home-da-fare): qui si rende e basta.

export function IconaSeverita({ severity }: { severity: SeveritaVoce }) {
  if (severity === "error") return <XCircle className="size-5 text-destructive shrink-0" />;
  if (severity === "warning") return <AlertTriangle className="size-5 text-incerto shrink-0" />;
  if (severity === "success") return <CheckCircle className="size-5 text-positivo shrink-0" />;
  return <Info className="size-5 text-primary shrink-0" />;
}

/** «Controllo i punti vendita…» o «Non è stato possibile controllare…». */
export function NotaControllo({
  avviso,
  onRiprova,
}: {
  avviso: "caricamento" | "errore";
  onRiprova?: () => void;
}) {
  if (avviso === "caricamento") {
    return <p className="text-sm text-muted-foreground">Controllo i punti vendita…</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      <AlertTriangle className="size-4 text-negativo" />
      Non è stato possibile controllare i punti vendita.
      {onRiprova && (
        <button
          type="button"
          onClick={onRiprova}
          className="text-xs font-medium text-primary transition-colors hover:underline"
        >
          Riprova
        </button>
      )}
    </div>
  );
}

/** Una voce del «Da fare»: icona, testo, Ignora e il pulsante della sua azione. */
export function RigaVoce({
  voce: v,
  occupata = false,
  onIgnora,
  onVaiSede,
  cambioSede = false,
}: {
  voce: VoceDaFare;
  occupata?: boolean;
  onIgnora?: (voce: VoceDaFare) => void;
  onVaiSede?: (ristoranteId: string, pagina: string) => void;
  cambioSede?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border bg-card p-4 transition-all sm:flex-row sm:items-center sm:gap-4",
        occupata && "pointer-events-none opacity-50",
      )}
    >
      <IconaSeverita severity={v.severity} />
      <div className="min-w-0 flex-1">
        {v.sede && (
          <p
            className="truncate text-xs font-semibold text-muted-foreground"
            title={v.sedeCompleta ?? v.sede}
          >
            {v.sede}
          </p>
        )}
        <p className="text-sm leading-snug">{v.testo}</p>
        {v.dettaglio && <p className="mt-0.5 text-xs text-muted-foreground">{v.dettaglio}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {v.ignorabile && onIgnora && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            disabled={occupata}
            onClick={() => onIgnora(v)}
          >
            Ignora
          </Button>
        )}
        {v.azione?.tipo === "pagina" && (
          <Link href={v.azione.href} className={cn(buttonVariants({ size: "sm" }))}>
            {v.azione.etichetta}
            <ArrowRight className="size-4" />
          </Link>
        )}
        {v.azione?.tipo === "sede" && onVaiSede && (
          <Button
            size="sm"
            variant="outline"
            disabled={cambioSede}
            onClick={() => {
              const a = v.azione;
              if (a?.tipo === "sede") onVaiSede(a.ristoranteId, a.pagina);
            }}
          >
            {v.azione.etichetta}
            <ArrowRight className="size-4" />
          </Button>
        )}
      </div>
    </div>
  );
}

/** Il verde: lo decide chi chiama, mai questo componente. */
export function TuttoInOrdine() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-positivo/20 bg-gradient-to-br from-positivo/[0.07] via-transparent to-transparent py-10 text-center">
      <div className="rounded-full bg-positivo/10 p-3 ring-1 ring-positivo/20">
        <Check className="size-7 text-positivo" />
      </div>
      <p className="text-base font-semibold text-positivo">Tutto in ordine per oggi</p>
      <p className="text-sm text-muted-foreground">Nessuna azione da fare. Buon lavoro!</p>
    </div>
  );
}

/** Il «Da fare» del punto vendita. Quello della catena, per sede, e' in
 * `app/(app)/catena/da-fare-catena.tsx`. */
export function DaFareOggi({
  voci,
  verde,
  datiMancanti,
  onIgnora,
  inCorso,
}: {
  voci: VoceDaFare[];
  /** Tutto in ordine: lo decide chi chiama, mai questo componente. */
  verde: boolean;
  /** Nessuna voce ma mancano dati: nota neutra, niente verde. */
  datiMancanti?: string[];
  onIgnora?: (id: string) => void;
  inCorso?: Set<string>;
}) {
  if (voci.length === 0) {
    if (verde) return <TuttoInOrdine />;
    if (datiMancanti && datiMancanti.length > 0) {
      // Nessuna card urgente, ma mancano dati: senza quelli i numeri sono falsi.
      return (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-incerto/20 bg-gradient-to-br from-incerto/[0.07] via-transparent to-transparent py-8 text-center">
          <div className="rounded-full bg-incerto/10 p-3 ring-1 ring-incerto/20">
            <Info className="size-6 text-incerto" />
          </div>
          <p className="text-base font-semibold text-incerto">Nessuna azione urgente</p>
          <p className="max-w-md text-sm text-muted-foreground">
            Per avere il quadro completo, però, mancano ancora:{" "}
            <span className="font-medium text-foreground">{datiMancanti.join(", ")}</span>.
          </p>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-muted-foreground">
        Da fare oggi
        <span className="ml-1.5 text-muted-foreground/60">({voci.length})</span>
      </h2>
      {voci.map((v) => (
        <RigaVoce
          key={v.id}
          voce={v}
          occupata={inCorso?.has(v.id) ?? false}
          onIgnora={onIgnora && ((voce) => onIgnora(voce.id))}
        />
      ))}
    </div>
  );
}
