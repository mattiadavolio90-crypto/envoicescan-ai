"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Sparkles,
  AlertTriangle,
  TrendingDown,
  Tag,
  CalendarX,
  CheckCircle2,
  ChevronRight,
  ArrowRight,
  ClipboardList,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { AscoltaButton } from "@/components/ascolta-button";
import type { GruppoOverview, Segnale, SegnaliGruppo } from "@/lib/gruppo";

const ICONA: Record<Segnale["tipo"], typeof AlertTriangle> = {
  dati_mancanti: ClipboardList,
  margine_calo: TrendingDown,
  prezzi_sopra: Tag,
  ricavi_mancanti: CalendarX,
};
const DOT: Record<string, string> = {
  verde: "bg-emerald-500",
  giallo: "bg-amber-500",
  rosso: "bg-rose-500",
  grigio: "bg-muted-foreground/40",
};
const TXT: Record<string, string> = {
  verde: "text-emerald-600 dark:text-emerald-500",
  giallo: "text-amber-600 dark:text-amber-500",
  rosso: "text-rose-600 dark:text-rose-500",
  grigio: "text-muted-foreground",
};

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
}
function pct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// Vista catena su mobile (monitoraggio): briefing di gruppo + conti + salute +
// segnali + ranking, tutto impilato. Toccare un PV ci SCENDE: cambia sede, passa
// in modalità PV (cookie) e torna alla home mobile, che mostrerà quel locale.
export function MobileCatena({ overview }: { overview: GruppoOverview }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);
  const [segnali, setSegnali] = useState<Segnale[] | null>(null);

  useEffect(() => {
    let alive = true;
    fetch("/api/gruppo/segnali", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j: SegnaliGruppo | null) => {
        if (alive) setSegnali(j?.segnali ?? []);
      })
      .catch(() => {
        if (alive) setSegnali([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  async function drill(id: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: id }),
      });
      if (!res.ok) throw new Error();
      document.cookie = `oneflux_view=pv; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax`;
      router.push("/m/briefing");
      router.refresh();
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  const { kpi } = overview;
  const molPos = kpi.mol >= 0;
  // Cascata come il desktop: il MOL si mostra solo se i dati sono completi,
  // altrimenti sarebbe gonfiato → si mostra il food cost e si avvisa.
  const completo = kpi.livello_dati === "completo";

  return (
    <div className="space-y-4">
      {/* Briefing di gruppo */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/10 via-violet-500/[0.05] to-background p-5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-primary/80">
            <Sparkles className="size-3.5" />
            Il tuo assistente · catena
          </div>
          <AscoltaButton testo={`${overview.briefing.saluto}, ${overview.nome_gruppo}. ${overview.briefing.narrativa}`} />
        </div>
        <h1 className="mt-2 text-xl font-bold tracking-tight">
          {overview.briefing.saluto}, {overview.nome_gruppo}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-foreground/90">{overview.briefing.narrativa}</p>
      </div>

      {/* Conti del gruppo (compatto) — MOL se completo, altrimenti food cost */}
      <div
        className={cn(
          "rounded-2xl border p-5 text-center",
          !completo
            ? "bg-gradient-to-br from-amber-500/10 to-background"
            : molPos
              ? "bg-gradient-to-br from-emerald-500/10 to-background"
              : "bg-gradient-to-br from-rose-500/10 to-background",
        )}
      >
        {completo ? (
          <>
            <div className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">
              MOL del gruppo · {overview.periodo_label}
            </div>
            <div className={cn("mt-1 text-4xl font-black tabular-nums", molPos ? TXT.verde : TXT.rosso)}>
              {euro(kpi.mol)}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              margine {pct(kpi.margine_medio_perc)} · fatturato {euro(kpi.fatturato)}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 border-t pt-3 text-center">
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Food cost</div>
                <div className="text-sm font-semibold tabular-nums">{pct(kpi.food_cost_pct)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Personale</div>
                <div className="text-sm font-semibold tabular-nums">{euro(kpi.costo_personale)}</div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Spese gen.</div>
                <div className="text-sm font-semibold tabular-nums">{euro(kpi.spese_generali)}</div>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">
              Food cost del gruppo · {overview.periodo_label}
            </div>
            <div className="mt-1 text-4xl font-black tabular-nums">
              {kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              fatturato {euro(kpi.fatturato)} · {kpi.pv_da_completare} PV da completare: MOL non ancora calcolabile
            </div>
          </>
        )}
      </div>

      {/* Salute del gruppo */}
      <div className="rounded-2xl border bg-card p-4">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-sm font-semibold">Salute del gruppo</span>
          <span className={cn("text-sm font-bold tabular-nums", TXT[overview.salute_colore])}>
            {overview.salute_indice}/100
          </span>
        </div>
        <ul className="space-y-1">
          {overview.salute_pv.map((pv) => (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => drill(pv.ristorante_id)}
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left active:bg-accent disabled:opacity-50"
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", DOT[pv.colore])} />
                <span className="flex-1 truncate text-sm">{pv.nome}</span>
                <span className={cn("text-sm font-semibold tabular-nums", TXT[pv.colore])}>{pv.indice}</span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/40" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Da vedere nella catena */}
      <div className="rounded-2xl border bg-card p-4">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <AlertTriangle className="size-4" />
          Da vedere nella catena
        </div>
        {segnali === null ? (
          <p className="mt-3 text-sm text-muted-foreground">Controllo i punti vendita…</p>
        ) : segnali.length === 0 ? (
          <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
            <CheckCircle2 className="size-4 text-emerald-500" />
            Tutto sotto controllo.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {segnali.map((s, i) => {
              const Icon = ICONA[s.tipo] ?? AlertTriangle;
              return (
                <li key={`${s.tipo}-${s.ristorante_id}-${i}`}>
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => drill(s.ristorante_id)}
                    className="flex w-full items-start gap-3 rounded-xl border bg-background/40 p-3 text-left active:bg-accent disabled:opacity-50"
                  >
                    <Icon className="mt-0.5 size-4 shrink-0 text-amber-500" />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-semibold text-muted-foreground">{s.pv_nome}</span>
                      <span className="block text-sm">{s.testo}</span>
                    </span>
                    <ArrowRight className="mt-0.5 size-4 shrink-0 text-primary" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Ranking punti vendita */}
      <div className="rounded-2xl border bg-card">
        <div className="border-b px-4 py-3 text-sm font-semibold">
          Ranking punti vendita
          <span className="ml-2 text-xs font-normal text-muted-foreground">per margine %</span>
        </div>
        <ul className="divide-y">
          {overview.ranking.map((pv) => (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => drill(pv.ristorante_id)}
                className="flex w-full items-center gap-2.5 px-4 py-3 text-left active:bg-accent disabled:opacity-50"
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", DOT[(pv.colore as string) ?? "grigio"])} />
                <span className="flex-1 truncate text-sm font-medium">{pv.nome}</span>
                {pv.dati_incompleti ? (
                  <span className="text-xs text-muted-foreground">dati incompleti</span>
                ) : (
                  <span className={cn("text-sm font-semibold tabular-nums", TXT[(pv.colore as string) ?? "grigio"])}>
                    {pct(pv.margine_perc)}
                  </span>
                )}
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/40" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
