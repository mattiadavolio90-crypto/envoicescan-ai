import Link from "next/link";
import { ArrowDown, ArrowUp } from "lucide-react";
import { calcolaSparkline, offsetAnello, type PuntoMol } from "@/lib/catena-confronti";
import { SALUTE_TINT, type ColoreSalute } from "@/lib/salute-tint";
import { cn } from "@/lib/utils";

// I pezzi comuni alle due card della Home, PV e catena (step 3, 28/9/2026).
// Fino a qui erano quattro card grandi con gradiente e aloni colorati, alte
// mezza pagina (Mattia: «enormi, occupano tutta la pagina»). Ora parlano come le
// tessere di Margini (`margini/kpi-bar.tsx`): fondo della card, bordo neutro,
// etichette piccole in maiuscolo, colore solo sul numero che giudica.

export function CardHome({
  titolo,
  meta,
  children,
}: {
  titolo: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">{titolo}</h2>
        {meta && <span className="shrink-0 text-xs text-muted-foreground">{meta}</span>}
      </div>
      {children}
    </div>
  );
}

export function EtichettaKpi({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] font-medium uppercase leading-none tracking-wider text-muted-foreground">
      {children}
    </span>
  );
}

const TESSERA =
  "flex min-w-0 flex-col gap-1 rounded-lg border border-border px-3 py-2 text-left transition-colors hover:border-muted-foreground/40";

// Una voce dei conti (Fatturato, Food cost, …): tessera piccola, cliccabile
// verso la pagina dove si controlla. `href` nel PV, `onClick` in catena.
export function TesseraVoce({
  label,
  valore,
  segno,
  extra,
  href,
  onClick,
}: {
  label: string;
  valore: string;
  segno?: string;
  extra?: React.ReactNode;
  href?: string;
  onClick?: () => void;
}) {
  const contenuto = (
    <>
      <EtichettaKpi>
        {segno && <span className="mr-1">{segno}</span>}
        {label}
      </EtichettaKpi>
      <span className="flex flex-wrap items-baseline justify-between gap-x-2">
        <span className="text-base font-semibold tabular-nums">{valore}</span>
        {extra}
      </span>
    </>
  );
  if (href) return <Link href={href} className={TESSERA}>{contenuto}</Link>;
  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={TESSERA}>
        {contenuto}
      </button>
    );
  }
  return <div className={TESSERA}>{contenuto}</div>;
}

// Andamento del margine nell'anno: una linea bassa accanto al MOL, con la
// variazione dal primo all'ultimo mese. La geometria e la % le calcola
// `calcolaSparkline` in lib/, coperta da test; qui resta il disegno. Prima era
// scritto due volte (MolAndamento nel PV, MolSparkline in catena).
//
// Con i costi mancanti la curva e' quella del MOL gonfiato: ambra, e la
// variazione senza verde/rosso ne' freccia — un «in meglio» potrebbe essere solo
// un costo che manca.
export function AndamentoMargine({
  punti,
  anno,
  affidabile,
}: {
  punti: PuntoMol[];
  anno: number | null;
  affidabile: boolean;
}) {
  const spark = calcolaSparkline(punti);
  if (!spark) return null;
  const { d, ytdPct, su, stroke, meseDa, meseA, cx, cy } = spark;
  const colore = affidabile ? stroke : "text-incerto";
  const coloreDelta = affidabile ? (su ? "text-positivo" : "text-negativo") : "text-muted-foreground";
  return (
    <div className="flex w-32 shrink-0 flex-col gap-1 sm:w-40">
      <svg
        viewBox="0 0 240 40"
        className="h-8 w-full overflow-visible"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Andamento del margine ${anno ?? ""}${affidabile ? "" : ", dati incompleti"}`.trim()}
      >
        <path d={d} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("stroke-current", colore)} />
        <circle cx={cx} cy={cy} r="3" className={cn("fill-current", colore)} />
      </svg>
      <span className="flex items-center justify-end gap-1 text-[11px] leading-none text-muted-foreground">
        {meseDa} → {meseA}{anno ? ` ${anno}` : ""}
        {ytdPct != null && (
          <span className={cn("inline-flex items-center gap-0.5 font-semibold tabular-nums", coloreDelta)}>
            {affidabile && (su ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
            {Math.abs(ytdPct).toLocaleString("it-IT", { maximumFractionDigits: 1 })}%
          </span>
        )}
      </span>
    </div>
  );
}

// Anello della completezza, piccolo. `indice` null = non determinabile: anello
// vuoto e «—». Uno zero disegnerebbe «sede messa malissimo», che e'
// un'affermazione — e non sappiamo niente.
export function AnelloCompletezza({ indice, colore }: { indice: number | null; colore: ColoreSalute }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = indice != null ? offsetAnello(indice, r) : c;
  const tint = SALUTE_TINT[colore];
  return (
    <div className="relative size-14 shrink-0">
      <svg viewBox="0 0 120 120" className="size-14 -rotate-90">
        <circle cx="60" cy="60" r={r} className="stroke-muted" strokeWidth="12" fill="none" />
        <circle
          cx="60" cy="60" r={r}
          className={cn("transition-all", tint.ring)}
          stroke="currentColor" strokeWidth="12" fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset}
        />
      </svg>
      <span className={cn("absolute inset-0 flex items-center justify-center text-xs font-bold tabular-nums", tint.text)}>
        {indice != null ? `${indice}%` : "—"}
      </span>
    </div>
  );
}

// La riga in testa alla card della completezza: anello, giudizio, e una frase
// che dice cosa conta (nel PV «2 voci su 5 da sistemare», in catena la media).
export function RiepilogoCompletezza({
  indice,
  colore,
  nota,
}: {
  indice: number | null;
  colore: ColoreSalute;
  nota?: React.ReactNode;
}) {
  const tint = SALUTE_TINT[colore];
  return (
    <div className="flex items-center gap-3">
      <AnelloCompletezza indice={indice} colore={colore} />
      <div className="flex min-w-0 flex-col items-start gap-1">
        <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", tint.badge)}>{tint.label}</span>
        {nota && <span className="text-xs text-muted-foreground">{nota}</span>}
      </div>
    </div>
  );
}
