"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  ChevronsUpDown,
  TrendingUp,
  Receipt,
  ChevronRight,
  Sparkles,
  Tags,
  ArrowUp,
  ArrowDown,
  ArrowRight,
} from "lucide-react";
import {
  type GruppoOverview,
  type GruppoBriefing,
  type SalutePV,
  type MolMensile,
} from "@/lib/gruppo";
import { cn } from "@/lib/utils";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { AscoltaButton } from "@/components/ascolta-button";
import { FinestraSpesaPV } from "./finestra-spesa-pv";
import { FinestraMarginiCoperti } from "./finestra-margini-coperti";
import { CardSegnali } from "./card-segnali";
import { TagCatenaDialog } from "./gruppo-tag-section";
import { ConfigAssistenteCatena } from "./config-assistente-catena";

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

// Palette per stato salute/colore — stessa famiglia visiva della Home PV
// (gradiente + orb + ring), token a tema → dark/light-safe.
const TINT = {
  verde: {
    ring: "text-emerald-500",
    text: "text-emerald-600 dark:text-emerald-500",
    badge: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
    card: "bg-gradient-to-br from-emerald-500/10 via-emerald-500/[0.03] to-background",
    orb1: "bg-emerald-400/15",
    orb2: "bg-emerald-400/8",
    dot: "bg-emerald-500",
    label: "In salute",
  },
  giallo: {
    ring: "text-amber-500",
    text: "text-amber-600 dark:text-amber-500",
    badge: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
    card: "bg-gradient-to-br from-amber-500/10 via-amber-500/[0.03] to-background",
    orb1: "bg-amber-400/15",
    orb2: "bg-amber-400/8",
    dot: "bg-amber-500",
    label: "Da completare",
  },
  rosso: {
    ring: "text-rose-500",
    text: "text-rose-600 dark:text-rose-500",
    badge: "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400",
    card: "bg-gradient-to-br from-rose-500/10 via-rose-500/[0.03] to-background",
    orb1: "bg-rose-400/15",
    orb2: "bg-rose-400/8",
    dot: "bg-rose-500",
    label: "Dati incompleti",
  },
  grigio: {
    ring: "text-muted-foreground/40",
    text: "text-muted-foreground",
    badge: "bg-muted text-muted-foreground",
    card: "bg-card",
    orb1: "bg-transparent",
    orb2: "bg-transparent",
    dot: "bg-muted-foreground/40",
    label: "Dati incompleti",
  },
} as const;

type ColoreTint = keyof typeof TINT;

// ─── Briefing di gruppo (hero) ─────────────────────────────────────────────
function BriefingGruppo({ briefing, nomeGruppo }: { briefing: GruppoBriefing; nomeGruppo: string }) {
  return (
    <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/10 via-violet-500/[0.04] to-background p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-sky-400/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full bg-violet-400/10 blur-3xl" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-primary/80">
          <Sparkles className="size-4" />
          <span>Il tuo assistente · catena</span>
        </div>
        <AscoltaButton testo={`${briefing.saluto}, ${nomeGruppo}. ${briefing.narrativa}`} />
      </div>
      <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
        {briefing.saluto}, {nomeGruppo}
      </h1>
      <p className="mt-4 max-w-none text-base leading-relaxed text-foreground/90 sm:text-lg">
        {briefing.narrativa}
      </p>
    </div>
  );
}

// ─── Sparkline andamento MOL del gruppo (come MolAndamento della Home) ──────
const MESI_ABBR = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

function MolSparkline({ punti, anno }: { punti: MolMensile[]; anno: number }) {
  if (punti.length < 2) return null;
  const W = 240;
  const H = 40;
  const PAD = 4;
  const vals = punti.map((p) => p.mol);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const n = punti.length;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (n - 1);
  const y = (v: number) => H - PAD - ((v - min) / range) * (H - 2 * PAD);
  const d = punti.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.mol).toFixed(1)}`).join(" ");
  const primo = punti[0].mol;
  const ultimo = punti[n - 1].mol;
  const ytdPct = primo > 0 ? ((ultimo - primo) / primo) * 100 : null;
  const su = ytdPct != null && ytdPct >= 0;
  const stroke = su ? "text-emerald-500" : "text-rose-500";
  const meseDa = MESI_ABBR[(punti[0].mese - 1) % 12] ?? "";
  const meseA = MESI_ABBR[(punti[n - 1].mese - 1) % 12] ?? "";

  return (
    <div className="mt-4 border-t pt-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground/70">Andamento margine {anno}</span>
        {ytdPct != null && (
          <span
            className={cn(
              "inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums",
              su ? "text-emerald-600 dark:text-emerald-500" : "text-rose-600 dark:text-rose-500",
            )}
          >
            {su ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
            {Math.abs(ytdPct).toLocaleString("it-IT", { maximumFractionDigits: 1 })}%
            <span className="ml-1 font-normal text-muted-foreground/60">
              {meseDa} → {meseA}
            </span>
          </span>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-10 w-full overflow-visible" preserveAspectRatio="none" role="img" aria-label="Andamento del margine del gruppo">
        <path d={d} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("stroke-current", stroke)} />
        <circle cx={x(n - 1)} cy={y(ultimo)} r="3" className={cn("fill-current", stroke)} />
      </svg>
    </div>
  );
}

// Riga del breakdown conti (gemella di RigaVoce della Home PV): pallino + label
// + valore, cliccabile per aprire la finestra di confronto.
function VoceConto({
  colore,
  label,
  value,
  segno,
  onClick,
}: {
  colore: "emerald" | "amber";
  label: string;
  value: string;
  segno?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center gap-3 rounded-xl bg-background/40 px-3.5 py-2.5 text-left transition-colors hover:bg-background/70"
    >
      <span className={cn("mt-0.5 size-2 shrink-0 rounded-full", colore === "emerald" ? "bg-emerald-400" : "bg-amber-400")} />
      <span className="flex-1 text-sm text-muted-foreground">
        {segno && <span className="mr-1 text-muted-foreground/50">{segno}</span>}
        {label}
      </span>
      <span className="text-sm font-semibold tabular-nums">{value}</span>
    </button>
  );
}

// ─── Card "I conti del gruppo" (gemella di KpiBlock) ───────────────────────
function ContiGruppoCard({
  overview,
  onApriSpesa,
  onApriMargini,
}: {
  overview: GruppoOverview;
  onApriSpesa: () => void;
  onApriMargini: () => void;
}) {
  const { kpi } = overview;
  const livello = kpi.livello_dati ?? "completo";
  const molPos = kpi.mol >= 0;
  // A cascata: con dati incompleti il MOL e' falso -> card neutra (no verde/rosso).
  const tint = livello === "completo" ? (molPos ? TINT.verde : TINT.rosso) : TINT.giallo;

  // Livello "nessuno": niente numeri, si indirizza a completare i PV.
  if (livello === "nessuno") {
    return (
      <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-6 sm:p-7">
        <div className="mb-4 flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">I conti del gruppo</h2>
          <span className="text-xs text-muted-foreground/70">{overview.periodo_label}</span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <div className="rounded-full bg-amber-500/15 p-3 ring-1 ring-amber-500/20">
            <Receipt className="size-6 text-amber-500" />
          </div>
          <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">Dati ancora incompleti</p>
          <p className="max-w-xs text-sm text-muted-foreground">
            Mancano fatturato e costi nei punti vendita: completa i dati per leggere
            food cost e margini del gruppo.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={cn("relative flex h-full flex-col overflow-hidden rounded-2xl border p-6 sm:p-7", tint.card)}>
      <div className={cn("pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl", tint.orb1)} />
      <div className={cn("pointer-events-none absolute -bottom-20 left-1/4 size-52 rounded-full blur-3xl", tint.orb2)} />

      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">I conti del gruppo</h2>
        <span className="text-xs text-muted-foreground/70">{overview.periodo_label}</span>
      </div>

      {livello === "completo" ? (
        /* MOL gruppo + margine medio → apre il confronto Margini e Coperti */
        <button
          type="button"
          onClick={onApriMargini}
          className="group flex flex-1 flex-col items-center justify-center gap-1 rounded-xl py-4 text-center transition-colors hover:bg-background/40"
        >
          <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">MOL del gruppo</span>
          <div className={cn("text-5xl font-black tabular-nums leading-none sm:text-6xl", tint.text)}>{euro(kpi.mol)}</div>
          <div className="mt-1 inline-flex items-center gap-2 text-xs text-muted-foreground/70">
            <span className={cn("rounded-full px-2 py-0.5 font-medium", tint.badge)}>margine {pct(kpi.margine_medio_perc)}</span>
            <span className="inline-flex items-center gap-0.5 font-medium text-primary">
              confronta i PV <ArrowRight className="size-3" />
            </span>
          </div>
        </button>
      ) : (
        /* Livello "food": food cost si', MOL no (sarebbe gonfiato). Si mostra il
           food cost come dato principale e si avvisa che mancano dati per il MOL. */
        <button
          type="button"
          onClick={onApriSpesa}
          className="group flex flex-1 flex-col items-center justify-center gap-1 rounded-xl py-4 text-center transition-colors hover:bg-background/40"
        >
          <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">Food cost del gruppo</span>
          <div className={cn("text-5xl font-black tabular-nums leading-none sm:text-6xl", tint.text)}>
            {kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}
          </div>
          <span className="mt-1 text-xs text-muted-foreground/70">
            {kpi.pv_da_completare} {kpi.pv_da_completare === 1 ? "PV" : "PV"} senza costo personale: MOL non ancora calcolabile
          </span>
        </button>
      )}

      {/* Breakdown: Fatturato e Food cost sempre; Personale/Spese/MOL solo se completo. */}
      <div className="mt-auto space-y-1.5">
        <VoceConto colore="emerald" label="Fatturato gruppo" value={euro(kpi.fatturato)} onClick={onApriMargini} />
        <VoceConto
          colore="amber"
          segno="−"
          label="Food cost"
          value={kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}
          onClick={onApriSpesa}
        />
        {livello === "completo" && (
          <>
            <VoceConto colore="amber" segno="−" label="Costo personale" value={euro(kpi.costo_personale)} onClick={onApriMargini} />
            <VoceConto colore="amber" segno="−" label="Spese generali" value={euro(kpi.spese_generali)} onClick={onApriMargini} />
          </>
        )}
      </div>

      {livello === "completo" && <MolSparkline punti={overview.mol_mensile} anno={overview.mol_mensile_anno} />}
    </div>
  );
}

// ─── Card "Salute del gruppo" (gemella di SaluteCard) ──────────────────────
function AnelloSalute({ indice, colore }: { indice: number; colore: ColoreTint }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const offset = c - (Math.max(0, Math.min(100, indice)) / 100) * c;
  const tint = TINT[colore];
  return (
    <div className="relative size-32 shrink-0">
      <svg viewBox="0 0 120 120" className="size-32 -rotate-90">
        <circle cx="60" cy="60" r={r} className="stroke-muted" strokeWidth="10" fill="none" />
        <circle
          cx="60" cy="60" r={r}
          className={cn("transition-all", tint.ring)}
          stroke="currentColor" strokeWidth="10" fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-3xl font-bold tabular-nums", tint.text)}>{indice}</span>
        <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">su 100</span>
      </div>
    </div>
  );
}

function SaluteGruppoCard({
  indice,
  colore,
  salutePv,
  onApriPV,
  switching,
}: {
  indice: number;
  colore: ColoreTint;
  salutePv: SalutePV[];
  onApriPV: (id: string) => void;
  switching: boolean;
}) {
  const tint = TINT[colore];
  return (
    <div className={cn("relative flex h-full flex-col overflow-hidden rounded-2xl border p-6 sm:p-7", tint.card)}>
      <div className={cn("pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl", tint.orb1)} />
      <div className={cn("pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full blur-3xl", tint.orb2)} />
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Salute del gruppo</h2>
        <span className="text-xs text-muted-foreground/70">media {salutePv.length} {salutePv.length === 1 ? "sede" : "sedi"}</span>
      </div>
      <div className="flex flex-1 flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-7">
        <AnelloSalute indice={indice} colore={colore} />
        <div className="flex-1 space-y-3">
          <span className={cn("inline-block rounded-full px-3 py-1 text-xs font-medium", tint.badge)}>{tint.label}</span>
          <ul className="space-y-1.5">
            {salutePv.map((pv) => {
              const t = TINT[pv.colore];
              return (
                <li key={pv.ristorante_id}>
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => onApriPV(pv.ristorante_id)}
                    className="flex w-full items-center gap-3 rounded-xl bg-background/40 px-3 py-2 text-left text-sm transition-colors hover:bg-background/70 disabled:opacity-50"
                  >
                    <span className={cn("size-2.5 shrink-0 rounded-full", t.dot)} />
                    <span className="flex-1 truncate">{pv.nome}</span>
                    <span className={cn("text-sm font-semibold tabular-nums", t.text)}>{pv.indice}</span>
                    <ChevronRight className="size-4 shrink-0 text-muted-foreground/40" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      </div>
    </div>
  );
}

// ─── Card-azione "Confronti / strumenti" (apre una finestra) ───────────────
function ConfrontoCard({
  icon: Icon,
  titolo,
  sottotitolo,
  onClick,
}: {
  icon: typeof Receipt;
  titolo: string;
  sottotitolo: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-center gap-4 rounded-2xl border bg-card p-5 text-left transition-colors hover:bg-accent"
    >
      <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <Icon className="size-5" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{titolo}</span>
        <span className="block text-xs text-muted-foreground">{sottotitolo}</span>
      </span>
      <ArrowRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

export function SintesiCatena({ overview }: { overview: GruppoOverview }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);
  const [spesaOpen, setSpesaOpen] = useState(false);
  const [marginiOpen, setMarginiOpen] = useState(false);
  const [tagOpen, setTagOpen] = useState(false);

  // Deep link catena→PV: cambia la sede attiva e naviga alla pagina giusta del PV
  // (default Home). Il "fare" è nel PV; la catena indirizza.
  async function vaiAlPV(ristoranteId: string, page = "/dashboard") {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: ristoranteId }),
      });
      if (!res.ok) throw new Error();
      router.push(page);
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  const { ranking } = overview;

  return (
    <div className="space-y-6">
      {/* Header gruppo + selettore "Vai a un PV" */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Building2 className="size-6 text-primary" />
          Gruppo {overview.nome_gruppo}
          <span className="text-base font-normal text-muted-foreground">· {overview.num_pv} punti vendita</span>
        </h1>
        <div className="flex items-center gap-2">
          <ConfigAssistenteCatena />
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
              <DropdownMenuLabel className="text-xs text-muted-foreground">Apri un punto vendita</DropdownMenuLabel>
              {ranking.map((pv) => (
                <DropdownMenuItem key={pv.ristorante_id} disabled={switching} onClick={() => vaiAlPV(pv.ristorante_id)}>
                  {pv.nome}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Briefing di gruppo — la voce macro, in cima */}
      <BriefingGruppo briefing={overview.briefing} nomeGruppo={overview.nome_gruppo} />

      {/* Due card grandi come la Home PV: Conti + Salute */}
      <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
        <ContiGruppoCard
          overview={overview}
          onApriSpesa={() => setSpesaOpen(true)}
          onApriMargini={() => setMarginiOpen(true)}
        />
        <SaluteGruppoCard
          indice={overview.salute_indice}
          colore={overview.salute_colore}
          salutePv={overview.salute_pv}
          onApriPV={(id) => vaiAlPV(id)}
          switching={switching}
        />
      </div>

      {/* Strumenti di confronto del gruppo: si aprono in finestra (no pagine) */}
      <div className="grid gap-4 sm:grid-cols-3">
        <ConfrontoCard icon={Receipt} titolo="Spesa per PV" sottotitolo="Dove spende di più ogni sede" onClick={() => setSpesaOpen(true)} />
        <ConfrontoCard icon={TrendingUp} titolo="Margini e coperti" sottotitolo="Chi rende di più, per metrica" onClick={() => setMarginiOpen(true)} />
        <ConfrontoCard icon={Tags} titolo="Tag di catena" sottotitolo="Confronta un prodotto fra i PV" onClick={() => setTagOpen(true)} />
      </div>

      {/* Da vedere nella catena (segnali) */}
      <CardSegnali vaiAlPV={vaiAlPV} switching={switching} />

      {/* Ranking punti vendita per margine % */}
      <div className="rounded-2xl border bg-card">
        <div className="flex items-baseline justify-between gap-2 border-b px-5 py-4">
          <h2 className="text-sm font-semibold">Ranking punti vendita</h2>
          <span className="flex items-baseline gap-3 text-xs text-muted-foreground">
            <span>{overview.periodo_label} · per margine %</span>
            <button type="button" onClick={() => setMarginiOpen(true)} className="font-medium text-primary hover:underline">
              Confronta →
            </button>
          </span>
        </div>
        <ul className="divide-y">
          {ranking.map((pv) => {
            const t = TINT[(pv.colore as ColoreTint) ?? "grigio"];
            return (
              <li key={pv.ristorante_id}>
                <button
                  type="button"
                  disabled={switching}
                  onClick={() => vaiAlPV(pv.ristorante_id)}
                  className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-accent disabled:opacity-50"
                >
                  <span className={cn("size-2.5 shrink-0 rounded-full", t.dot)} />
                  <span className="flex-1 truncate text-sm font-medium">{pv.nome}</span>
                  {pv.dati_incompleti ? (
                    <span className="text-xs text-muted-foreground">dati incompleti</span>
                  ) : (
                    <span className="flex items-baseline gap-3">
                      <span className={cn("text-sm font-semibold tabular-nums", t.text)}>{pct(pv.margine_perc)}</span>
                      <span className="w-24 text-right text-xs text-muted-foreground tabular-nums">{euro(pv.fatturato)}</span>
                    </span>
                  )}
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground/50" />
                </button>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Finestre: caricano i dati solo all'apertura (lazy). */}
      <FinestraSpesaPV open={spesaOpen} onOpenChange={setSpesaOpen} />
      <FinestraMarginiCoperti open={marginiOpen} onOpenChange={setMarginiOpen} />
      <TagCatenaDialog open={tagOpen} onOpenChange={setTagOpen} />
    </div>
  );
}
