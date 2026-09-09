"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import {
  Building2,
  TrendingUp,
  Receipt,
  ChevronRight,
  Sparkles,
  Tags,
  ArrowUp,
  ArrowDown,
  ArrowRight,
  Split,
  ClipboardList,
  TriangleAlert,
} from "lucide-react";
import {
  type GruppoOverview,
  type GruppoBriefing,
  type SalutePV,
  type RankingPV,
  type MolMensile,
} from "@/lib/gruppo";
import { cn } from "@/lib/utils";
import { formatEuro as euro, formatPct } from "@/lib/format";
import {
  calcolaSparkline,
  messaggioFattureDaCollocare,
  metricaPrincipaleConti,
  offsetAnello,
  tintConti,
} from "@/lib/catena-confronti";
import { cambiaSedeEAttendi } from "@/lib/cambia-sede";
import { AscoltaButton } from "@/components/ascolta-button";
import { FinestraSpesaPV } from "./finestra-spesa-pv";
import { FinestraMarginiCoperti } from "./finestra-margini-coperti";
import { FinestraCostiGruppo } from "./finestra-costi-gruppo";
import { CodaDaAssegnare } from "@/components/fatture/coda-da-assegnare";
import { UploadModal } from "@/app/(app)/analisi-fatture/upload-modal";
import { CardSegnali } from "./card-segnali";
import { TagCatenaDialog } from "./gruppo-tag-section";
import { ConfigAssistenteCatena } from "./config-assistente-catena";
import { SALUTE_TINT } from "@/lib/salute-tint";

function pct(n: number | null): string {
  return n == null ? "—" : formatPct(n);
}

// Palette per stato salute/colore: la STESSA della Home PV (lib/salute-tint),
// non una copia — le due erano già divergenti sul tema scuro (9/9/2026).
const TINT = SALUTE_TINT;

type ColoreTint = keyof typeof TINT;

// ─── Briefing di gruppo (hero) ─────────────────────────────────────────────
function BriefingGruppo({ briefing, nomeGruppo }: { briefing: GruppoBriefing; nomeGruppo: string }) {
  // Default codaVisibile=true: sul desktop la coda da assegnare sta subito sotto.
  const msgDaCollocare = messaggioFattureDaCollocare(briefing);
  return (
    <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/10 via-violet-500/[0.04] to-background p-6 sm:p-8">
      <div className="pointer-events-none absolute -right-16 -top-16 size-56 rounded-full bg-sky-400/15 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full bg-violet-400/10 blur-3xl" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-primary/80">
          <Sparkles className="size-4" />
          <span>Il tuo assistente · catena</span>
        </div>
        {/* La riga "fatture da collocare" entra nell'audio: e' l'unica AZIONE
            del giorno, e da quando non sta piu' nella narrativa chi ascolta non
            la sentirebbe affatto. */}
        <AscoltaButton
          testo={[`${briefing.saluto}, ${nomeGruppo}.`, briefing.narrativa, msgDaCollocare]
            .filter(Boolean)
            .join(" ")}
        />
      </div>
      <h1 className="mt-3 text-2xl font-bold tracking-tight sm:text-3xl">
        {briefing.saluto}, {nomeGruppo}
      </h1>
      <p className="mt-4 max-w-none text-base leading-relaxed text-foreground/90 sm:text-lg">
        {briefing.narrativa}
      </p>
      {msgDaCollocare && (
        <p className="mt-3 flex items-center gap-2 text-sm font-medium text-amber-700 dark:text-amber-500">
          <ClipboardList className="size-4 shrink-0" />
          {msgDaCollocare}
        </p>
      )}
    </div>
  );
}

// ─── Sparkline andamento MOL del gruppo (come MolAndamento della Home) ──────

function MolSparkline({ punti, anno, affidabile }: { punti: MolMensile[]; anno: number; affidabile: boolean }) {
  const W = 240;
  const H = 40;
  const spark = calcolaSparkline(punti, W, H, 4);
  if (!spark) return null;
  const { d, ytdPct, su, stroke, meseDa, meseA, cx, cy } = spark;
  // Con dati di costo incompleti la curva e' quella del MOL gonfiato: ambra come
  // la card, e il delta SENZA verde/rosso — un "in meglio" potrebbe essere solo
  // un costo che manca, non una vittoria da certificare (stessa regola del
  // Trend neutro del PV sul MOL negativo).
  const colore = affidabile ? stroke : "text-amber-500";
  const coloreDelta = affidabile
    ? su ? "text-emerald-600 dark:text-emerald-500" : "text-rose-600 dark:text-rose-500"
    : "text-muted-foreground";

  return (
    <div className="mt-4 border-t pt-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground/70">
          Andamento margine {anno}{!affidabile && " · dati incompleti"}
        </span>
        {ytdPct != null && (
          <span
            className={cn("inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums", coloreDelta)}
          >
            {/* La freccia e' un giudizio quanto il colore: su un MOL gonfiato
                niente direzione certificata, resta solo il numero. */}
            {affidabile && (su ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
            {Math.abs(ytdPct).toLocaleString("it-IT", { maximumFractionDigits: 1 })}%
            <span className="ml-1 font-normal text-muted-foreground/60">
              {meseDa} → {meseA}
            </span>
          </span>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-10 w-full overflow-visible" preserveAspectRatio="none" role="img" aria-label="Andamento del margine del gruppo">
        <path d={d} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("stroke-current", colore)} />
        <circle cx={cx} cy={cy} r="3" className={cn("fill-current", colore)} />
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
      <span className="min-w-0 flex-1 text-sm text-muted-foreground">
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
  // La scelta del ramo e il testo dell'avviso vengono dalla funzione pura in
  // lib/catena-confronti.ts (condivisa con /m, e testabile — questo .tsx no).
  // Il default prudente sul campo assente sta li', insieme a quello di tintConti.
  const metrica = metricaPrincipaleConti(kpi);
  // A cascata: con dati incompleti il MOL e' falso -> card neutra (no verde/rosso).
  const tint = TINT[tintConti(kpi)];
  const affidabile = metrica.stato === "mol" && metrica.affidabile;
  const avviso = metrica.stato === "mol" ? metrica.avviso : null;

  // Livello "non determinabile": la completezza non e' stata letta. Non si mostra
  // NESSUN numero come se fosse valido — ne' il MOL ne' il food cost: entrambi
  // dipendono da dati che non sappiamo se ci siano. Si dice che non si sa e si
  // offre il retry, come fa il PV con BlockRetry.
  if (metrica.stato === "errore") {
    return (
      <div className="relative flex h-full flex-col overflow-hidden rounded-2xl border bg-card p-6 sm:p-7">
        <div className="mb-4 flex items-baseline justify-between gap-2">
          <h2 className="text-sm font-semibold">I conti del gruppo</h2>
          <span className="text-xs text-muted-foreground/70">{overview.periodo_label}</span>
        </div>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <div className="rounded-full bg-rose-500/15 p-3 ring-1 ring-rose-500/20">
            <TriangleAlert className="size-6 text-rose-500" />
          </div>
          <p className="text-sm font-semibold">Conti del gruppo non disponibili</p>
          <p className="max-w-xs text-sm text-muted-foreground">
            Non è stato possibile leggere i dati dei punti vendita: i numeri del
            gruppo non sono affidabili in questo momento.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="text-xs font-medium text-primary transition-colors hover:underline"
          >
            Riprova
          </button>
        </div>
      </div>
    );
  }

  // Livello "nessuno": niente numeri, si indirizza a completare i PV.
  if (metrica.stato === "vuoto") {
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

      {/* MOL del gruppo → apre il confronto Margini e Coperti. SEMPRE, anche con
          dati di costo incompleti (9/9/2026): il PV lo mostra sempre, e qui
          nasconderlo dietro il food cost faceva sembrare le due viste due
          prodotti diversi. Quando non e' reale lo dice l'avviso sotto, non il
          silenzio; il colore lo decide tintConti (giallo finche' non e' reale). */}
      <button
        type="button"
        onClick={onApriMargini}
        className="group flex flex-1 flex-col items-center justify-center gap-1 rounded-xl py-4 text-center transition-colors hover:bg-background/40"
      >
        <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">MOL del gruppo</span>
        <div className={cn("text-5xl font-black tabular-nums leading-none sm:text-6xl", tint.text)}>{euro(kpi.mol)}</div>
        <div className="mt-1 inline-flex items-center gap-2 text-xs text-muted-foreground/70">
          {/* margine_medio_perc e' Σmol/Σnetto (gruppo.py:76): lo STESSO numero
              gonfiato, in percentuale. Un numero falso con l'avviso e' la
              decisione; due sarebbero rumore. Solo quando il MOL e' reale. */}
          {affidabile && (
            <span className={cn("rounded-full px-2 py-0.5 font-medium", tint.badge)}>margine {pct(kpi.margine_medio_perc)}</span>
          )}
          <span className="inline-flex items-center gap-0.5 font-medium text-primary">
            confronta i PV <ArrowRight className="size-3" />
          </span>
        </div>
      </button>

      {/* Dati di costo incompleti: il MOL sopra e' gonfiato verso l'alto (mancano
          costi). Lo si dice chiaro — il banner ambra del PV per le fatture
          mancanti fa lo stesso — e si porta a vedere QUALI PV: la finestra
          Margini e Coperti li marca come "dati incompleti". */}
      {avviso && (
        <button
          type="button"
          onClick={onApriMargini}
          className="mb-1 flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-left text-xs text-amber-700 transition-colors hover:bg-amber-500/15 dark:text-amber-400"
        >
          <TriangleAlert className="mt-px size-3.5 shrink-0" />
          <span>
            {avviso}. <span className="font-medium">Vedi quali PV →</span>
          </span>
        </button>
      )}

      {/* Breakdown: Fatturato e Food cost sempre (il food cost UNA volta: prima,
          nel ramo incompleto, stava anche come numero grande). Personale/Spese
          solo con costi completi.
          DIVERGENZA DELIBERATA dal PV (9/9/2026): KpiBlock con `costi_mancanti`
          mostra il MOL E tutto il breakdown, Personale e Spese inclusi. Qui no:
          li' i costi mancano a UNA sede e le righe sono comunque i suoi numeri;
          qui una somma di gruppo a cui manca il personale di 2 PV su 4,
          etichettata "Costo personale", sarebbe un secondo numero falso sotto
          il primo — e senza un avviso suo. Scelta di prodotto, non un bug: se
          si vuole il breakdown parziale, serve anche il suo caveat. */}
      <div className="mt-auto space-y-1.5">
        <VoceConto colore="emerald" label="Fatturato gruppo (IVA incl.)" value={euro(kpi.fatturato)} onClick={onApriMargini} />
        <VoceConto
          colore="amber"
          segno="−"
          label="Food cost"
          value={kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}
          onClick={onApriSpesa}
        />
        {affidabile && (
          <>
            <VoceConto colore="amber" segno="−" label="Costo personale" value={euro(kpi.costo_personale)} onClick={onApriMargini} />
            <VoceConto colore="amber" segno="−" label="Spese generali" value={euro(kpi.spese_generali)} onClick={onApriMargini} />
          </>
        )}
      </div>

      {/* L'andamento segue il MOL: se il numero si vede, si vede la sua curva —
          in ambra finche' non e' reale. Il PV la mostra sempre. */}
      <MolSparkline punti={overview.mol_mensile} anno={overview.mol_mensile_anno} affidabile={affidabile} />
    </div>
  );
}

// ─── Card "Salute del gruppo" (gemella di SaluteCard) ──────────────────────
function AnelloSalute({ indice, colore }: { indice: number | null; colore: ColoreTint }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  // indice null = non determinabile: anello VUOTO e "—" al centro. Uno zero
  // disegnerebbe un anello a fondo scala, cioe' "sede messa malissimo", che e'
  // un'affermazione — e non sappiamo niente.
  const offset = indice != null ? offsetAnello(indice, r) : c;
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
        {/* Stessa unità della card Salute del PV ("78%"): era "78 su 100" qui e
            "78/100" sul mobile — tre letture per lo stesso numero (9/9/2026). */}
        <span className={cn("text-3xl font-bold tabular-nums", tint.text)}>
          {indice != null ? `${indice}%` : "—"}
        </span>
        {indice == null && (
          <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">
            non disponibile
          </span>
        )}
      </div>
    </div>
  );
}

function SaluteGruppoCard({
  indice,
  colore,
  salutePv,
  ranking,
  onApriPV,
  switching,
}: {
  indice: number | null;
  colore: ColoreTint;
  salutePv: SalutePV[];
  ranking: RankingPV[];
  onApriPV: (id: string) => void;
  switching: boolean;
}) {
  const tint = TINT[colore];
  // Margine% e fatturato per PV (dal ranking) → mostrati accanto all'indice di salute,
  // così questa card assorbe il vecchio "Ranking punti vendita" (una lista di PV sola).
  const rankById = new Map(ranking.map((r) => [r.ristorante_id, r]));
  return (
    <div className={cn("relative flex h-full flex-col overflow-hidden rounded-2xl border p-6 sm:p-7", tint.card)}>
      <div className={cn("pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl", tint.orb1)} />
      <div className={cn("pointer-events-none absolute -bottom-20 left-1/3 size-52 rounded-full blur-3xl", tint.orb2)} />
      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Salute e margini per sede</h2>
        <span className="text-xs text-muted-foreground/70">media {salutePv.length} {salutePv.length === 1 ? "sede" : "sedi"}</span>
      </div>
      <div className="flex min-w-0 flex-1 flex-col items-center gap-6 sm:flex-row sm:items-center sm:gap-7">
        <AnelloSalute indice={indice} colore={colore} />
        <div className="min-w-0 flex-1 space-y-3">
          <span className={cn("inline-block rounded-full px-3 py-1 text-xs font-medium", tint.badge)}>{tint.label}</span>
          <ul className="space-y-1.5">
            {salutePv.map((pv) => {
              const t = TINT[pv.colore];
              const r = rankById.get(pv.ristorante_id);
              return (
                <li key={pv.ristorante_id}>
                  <button
                    type="button"
                    disabled={switching}
                    onClick={() => onApriPV(pv.ristorante_id)}
                    className="flex w-full items-center gap-3 rounded-xl bg-background/40 px-3 py-2 text-left text-sm transition-colors hover:bg-background/70 disabled:opacity-50"
                  >
                    <span className={cn("size-2.5 shrink-0 rounded-full", t.dot)} />
                    <span className="min-w-0 flex-1 truncate">{pv.nome}</span>
                    {r?.dati_incompleti ? (
                      // Dati incompleti: l'indice sotto è inaffidabile (calcolato su dati
                      // parziali), quindi NON lo affianchiamo a un margine% che darebbe
                      // l'illusione di due numeri attendibili. Il dettaglio di cosa manca
                      // vive in "Da vedere nella catena" — un solo posto per quell'info.
                      <span className="shrink-0 text-xs text-muted-foreground/60">dati incompleti</span>
                    ) : r && r.margine_perc != null ? (
                      <span className="shrink-0 text-xs font-medium text-muted-foreground tabular-nums">
                        margine {pct(r.margine_perc)}
                      </span>
                    ) : null}
                    <span
                      className={cn(
                        "w-8 text-right text-sm font-semibold tabular-nums",
                        r?.dati_incompleti ? "text-muted-foreground/40" : t.text,
                      )}
                    >
                      {pv.indice ?? "—"}
                    </span>
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
  const [costiGruppoOpen, setCostiGruppoOpen] = useState(false);

  // Deep link catena→PV: cambia la sede attiva e naviga alla pagina giusta del PV
  // (default Home). Il "fare" è nel PV; la catena indirizza.
  async function vaiAlPV(ristoranteId: string, page = "/dashboard") {
    if (switching) return;
    setSwitching(true);
    try {
      // Attende che il cambio sia visibile ai processi worker prima di navigare:
      // scendere subito faceva renderizzare il PV con la sede ancora vecchia, e per
      // i PV di catena le righe ripartite non comparivano affatto.
      const confermato = await cambiaSedeEAttendi(ristoranteId);
      router.push(page);
      if (!confermato) toast.message("Punto vendita in apertura, un attimo…");
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header gruppo (lo switch PV è nella sidebar, in basso a sinistra) */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Building2 className="size-6 text-primary" />
          Gruppo {overview.nome_gruppo}
          <span className="text-base font-normal text-muted-foreground">· {overview.num_pv} punti vendita</span>
        </h1>
        <div className="flex items-center gap-2">
          {/* Caricare fatture dalla catena: il documento decide da solo il locale
              (P.IVA/indirizzo), la sede da cui si carica non c'entra. Prima l'unico
              punto di upload era dentro una pagina PV, quindi da qui bisognava
              scendere in un locale a caso per caricare — e per le catene same-P.IVA
              (OFFSIDE) le ambigue finivano nella coda qui sotto, cioè in un posto
              che dal PV non si vede. Qui invece carico e le colloco nello stesso
              schermo. Stesso identico componente del PV: nessun secondo canale. */}
          <UploadModal contesto="catena" />
          <ConfigAssistenteCatena />
        </div>
      </div>

      {/* Briefing di gruppo — la voce macro, in cima */}
      <BriefingGruppo briefing={overview.briefing} nomeGruppo={overview.nome_gruppo} />

      {/* Fatture di gruppo + Costi di gruppo: stessa origine (documenti a nome
          società, non di un singolo locale) → un unico riquadro con le due card
          affiancate, così la parentela si vede dalla posizione e non solo dal
          colore. La coda resta la voce prominente (bordo ambra, badge conteggio);
          "Costi di gruppo" era isolata in mezzo alle altre 3 card di confronto,
          lontana dalla coda che la alimenta. */}
      <div className="rounded-2xl border border-sky-500/20 bg-sky-500/[0.03] p-3 sm:p-4">
        <span className="mb-2 inline-block px-1 text-xs font-medium uppercase tracking-wide text-sky-700/70 dark:text-sky-400/70">
          Gruppo
        </span>
        <div className="grid gap-3 sm:grid-cols-2">
          <CodaDaAssegnare contesto="catena" />
          <ConfrontoCard icon={Split} titolo="Costi di gruppo" sottotitolo="Costi comuni divisi fra le sedi" onClick={() => setCostiGruppoOpen(true)} />
        </div>
      </div>

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
          ranking={overview.ranking}
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

      {/* Spazio riservato in fondo: il FAB "Chiedi a ONEFLUX" (fixed bottom-right)
          altrimenti resta sovrapposto all'ultimo contenuto durante lo scroll. */}
      <div aria-hidden className="h-20" />

      {/* Finestre: caricano i dati solo all'apertura (lazy). */}
      <FinestraSpesaPV open={spesaOpen} onOpenChange={setSpesaOpen} />
      <FinestraCostiGruppo open={costiGruppoOpen} onOpenChange={setCostiGruppoOpen} />
      <FinestraMarginiCoperti open={marginiOpen} onOpenChange={setMarginiOpen} />
      <TagCatenaDialog open={tagOpen} onOpenChange={setTagOpen} />
    </div>
  );
}
