"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  ChevronsUpDown,
  TrendingUp,
  Wallet,
  Receipt,
  ChevronRight,
} from "lucide-react";
import { type GruppoOverview, type RankingPV } from "@/lib/gruppo";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { FinestraSpesaPV } from "./finestra-spesa-pv";
import { FinestraMarginiCoperti } from "./finestra-margini-coperti";

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

function pct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// Token semantici a contrasto AA su dark E light (regola di design catena).
const DOT: Record<RankingPV["colore"], string> = {
  verde: "bg-emerald-500",
  giallo: "bg-amber-500",
  rosso: "bg-rose-500",
  grigio: "bg-muted-foreground/40",
};

const SALUTE_RING: Record<GruppoOverview["salute_colore"], string> = {
  verde: "text-emerald-500",
  giallo: "text-amber-500",
  rosso: "text-rose-500",
};

function KpiCard({
  icon: Icon,
  label,
  value,
  onClick,
  hint,
}: {
  icon: typeof TrendingUp;
  label: string;
  value: string;
  onClick?: () => void;
  hint?: string;
}) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        <Icon className="size-4" />
        {label}
      </div>
      <div className="text-3xl font-black tabular-nums">{value}</div>
      {hint && <div className="text-xs text-muted-foreground/70">{hint}</div>}
    </>
  );
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className="flex flex-col gap-2 rounded-2xl border bg-card p-5 text-left transition-colors hover:bg-accent"
      >
        {body}
      </button>
    );
  }
  return <div className="flex flex-col gap-2 rounded-2xl border bg-card p-5">{body}</div>;
}

function SaluteGauge({
  indice,
  colore,
  numPv,
}: {
  indice: number;
  colore: GruppoOverview["salute_colore"];
  numPv: number;
}) {
  const R = 34;
  const C = 2 * Math.PI * R;
  const dash = (indice / 100) * C;
  return (
    <div className="flex items-center gap-4 rounded-2xl border bg-card p-5">
      <svg viewBox="0 0 80 80" className="size-20 shrink-0 -rotate-90">
        <circle cx="40" cy="40" r={R} className="fill-none stroke-muted" strokeWidth="7" />
        <circle
          cx="40"
          cy="40"
          r={R}
          className={cn("fill-none stroke-current", SALUTE_RING[colore])}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${C}`}
        />
      </svg>
      <div>
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Salute del gruppo
        </div>
        <div className="mt-0.5 flex items-baseline gap-2">
          <span className={cn("text-3xl font-black tabular-nums", SALUTE_RING[colore])}>
            {indice}
          </span>
          <span className="text-sm text-muted-foreground">
            media {numPv} {numPv === 1 ? "sede" : "sedi"}
          </span>
        </div>
      </div>
    </div>
  );
}

function DaVedere() {
  // Fase 2 (motore segnali) popolerà questa card. Per ora placeholder coerente
  // con il widget notifiche: nessun segnale = stato sereno, niente rumore.
  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Da vedere nella catena
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        Nessuna segnalazione al momento. Qui compariranno gli avvisi sui punti
        vendita da tenere d&apos;occhio.
      </p>
    </div>
  );
}

export function SintesiCatena({ overview }: { overview: GruppoOverview }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);
  const [spesaOpen, setSpesaOpen] = useState(false);
  const [marginiOpen, setMarginiOpen] = useState(false);

  async function vaiAlPV(ristoranteId: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: ristoranteId }),
      });
      if (!res.ok) throw new Error();
      router.push("/dashboard");
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  const { kpi, ranking } = overview;

  return (
    <div className="space-y-8">
      {/* Header gruppo + selettore "Vai a un PV" */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Building2 className="size-6 text-primary" />
          Gruppo {overview.nome_gruppo}
          <span className="text-base font-normal text-muted-foreground">
            · {overview.num_pv} punti vendita
          </span>
        </h1>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                type="button"
                disabled={switching}
                className="inline-flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-sm font-medium transition-colors hover:bg-accent disabled:opacity-50"
              >
                Vai a un punto vendita
                <ChevronsUpDown className="size-4" />
              </button>
            }
          />
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="text-xs text-muted-foreground">
              Apri un punto vendita
            </DropdownMenuLabel>
            {ranking.map((pv) => (
              <DropdownMenuItem
                key={pv.ristorante_id}
                disabled={switching}
                onClick={() => vaiAlPV(pv.ristorante_id)}
              >
                {pv.nome}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* 3 KPI del gruppo — Margine e Spesa aprono le finestre di confronto */}
      <div className="grid gap-4 sm:grid-cols-3">
        <KpiCard icon={Wallet} label="Fatturato gruppo" value={euro(kpi.fatturato)} />
        <KpiCard
          icon={TrendingUp}
          label="Margine medio"
          value={pct(kpi.margine_medio_perc)}
          hint="Confronta margini e coperti →"
          onClick={() => setMarginiOpen(true)}
        />
        <KpiCard
          icon={Receipt}
          label="Spesa fornitori"
          value={euro(kpi.spesa_fornitori)}
          hint="Confronta spesa per PV →"
          onClick={() => setSpesaOpen(true)}
        />
      </div>

      {/* Salute gruppo + Da vedere */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SaluteGauge
          indice={overview.salute_indice}
          colore={overview.salute_colore}
          numPv={overview.num_pv}
        />
        <DaVedere />
      </div>

      {/* Ranking punti vendita per margine % */}
      <div className="rounded-2xl border bg-card">
        <div className="flex items-baseline justify-between gap-2 border-b px-5 py-4">
          <h2 className="text-sm font-semibold">Ranking punti vendita</h2>
          <span className="flex items-baseline gap-3 text-xs text-muted-foreground">
            <span>{overview.periodo_label} · per margine %</span>
            <button
              type="button"
              onClick={() => setMarginiOpen(true)}
              className="font-medium text-primary hover:underline"
            >
              Confronta →
            </button>
          </span>
        </div>
        <ul className="divide-y">
          {ranking.map((pv) => (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => vaiAlPV(pv.ristorante_id)}
                className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-accent disabled:opacity-50"
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", DOT[pv.colore])} />
                <span className="flex-1 truncate text-sm font-medium">{pv.nome}</span>
                {pv.dati_incompleti ? (
                  <span className="text-xs text-muted-foreground">dati incompleti</span>
                ) : (
                  <span className="flex items-baseline gap-3">
                    <span className="text-sm font-semibold tabular-nums">{pct(pv.margine_perc)}</span>
                    <span className="w-24 text-right text-xs text-muted-foreground tabular-nums">
                      {euro(pv.fatturato)}
                    </span>
                  </span>
                )}
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/50" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Finestre di confronto: caricano i dati solo all'apertura (lazy). */}
      <FinestraSpesaPV open={spesaOpen} onOpenChange={setSpesaOpen} />
      <FinestraMarginiCoperti open={marginiOpen} onOpenChange={setMarginiOpen} />
    </div>
  );
}
