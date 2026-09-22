import Link from "next/link";
import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import { type HomeKpi } from "@/lib/home";
import { calcolaSparkline, tintContiPV, type PuntoMol } from "@/lib/catena-confronti";
import { formatEuro } from "@/lib/format";
import { tintaTrend } from "@/lib/home-kpi";
import { costoMerceLabel, type Settore } from "@/lib/categorie-spesa";
import { SALUTE_TINT } from "@/lib/salute-tint";
import { cn } from "@/lib/utils";

function Trend({
  delta,
  suffix,
  buonoSeSu,
  sopprimi = false,
  neutro = false,
}: {
  delta: number | null;
  suffix: string;
  buonoSeSu: boolean;
  // Quando il valore corrente della voce e' 0 (tipicamente dato del mese non
  // ancora caricato), il confronto con un mese che aveva dati produce un crollo
  // fuorviante ("−100%", "−29pp" da/verso zero). In quel caso mostriamo "—":
  // un calo a zero quasi sempre significa "manca il dato", non un crollo reale.
  sopprimi?: boolean;
  // Mostra il delta ma MAI in verde: usato sul MOL quando il valore corrente e'
  // negativo. Un MOL che sale da -5000 a -1188 e' "meno peggio", non una vittoria:
  // colorarlo di verde con freccia in su festeggerebbe una perdita. Decisione
  // Mattia 19/06 (niente falsa celebrazione del MOL). Resta visibile (la freccia
  // su/giu) ma in tono neutro.
  neutro?: boolean;
}) {
  const { mostra, tinta, direzione } = tintaTrend({ delta, buonoSeSu, sopprimi, neutro });
  if (!mostra) return <span className="text-xs text-muted-foreground/40">—</span>;
  const Icon = direzione === "piatto" ? Minus : direzione === "su" ? ArrowUp : ArrowDown;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums",
        tinta === null && "text-muted-foreground",
        tinta === true && "text-positivo",
        tinta === false && "text-negativo",
      )}
    >
      <Icon className="size-3" />
      {Math.abs(delta!).toLocaleString("it-IT")}
      {suffix}
    </span>
  );
}

function RigaVoce({
  colore,
  label,
  value,
  delta,
  suffix,
  buonoSeSu,
  segno,
  valoreZero = false,
  href,
}: {
  colore: "emerald" | "amber";
  label: string;
  value: string;
  delta: number | null;
  suffix: string;
  buonoSeSu: boolean;
  segno?: string;
  // true = il valore corrente della voce e' 0/assente: il trend va soppresso
  // (vedi commento in Trend).
  valoreZero?: boolean;
  // Pagina dove approfondire/sistemare la voce. Rende la riga cliccabile: vedo
  // un numero che non mi piace -> un click e sono dove lo controllo.
  href?: string;
}) {
  const dotCn = colore === "emerald" ? "bg-positivo" : "bg-incerto";
  const contenuto = (
    <>
      <span className={cn("mt-0.5 size-2 shrink-0 rounded-full", dotCn)} />
      <span className="flex-1 text-sm text-muted-foreground">
        {segno && <span className="mr-1 text-muted-foreground/50">{segno}</span>}
        {label}
      </span>
      <span className="flex items-baseline gap-2">
        <span className="text-sm font-semibold tabular-nums">{value}</span>
        <span className="w-12 text-right">
          <Trend delta={delta} suffix={suffix} buonoSeSu={buonoSeSu} sopprimi={valoreZero} />
        </span>
      </span>
    </>
  );
  const base = "flex items-center gap-3 rounded-xl bg-background/40 px-3.5 py-2.5";
  if (href) {
    return (
      <Link href={href} className={cn(base, "transition-colors hover:bg-background/70")}>
        {contenuto}
      </Link>
    );
  }
  return <div className={base}>{contenuto}</div>;
}

// Fascia "Andamento MOL nell'anno": una sezione a sé in fondo alla card, con la
// sua etichetta (anno + range mesi), la mini-linea piu' larga e una % di
// variazione YTD (dal primo all'ultimo mese con dati). Prima la sparkline era
// schiacciata sotto al numero grande, senza scala ne' periodo: un graffio
// illeggibile. Qui ha spazio e contesto -> si capisce cosa racconta.
//
// La geometria e la % NON si calcolano qui: le fa calcolaSparkline in lib/,
// dove sono coperte da test. Fino all'1/9 questo file ne teneva una copia
// integrale — stessa formula scritta due volte, con la soglia dei 2 punti gia'
// divergente fra le due. Qui resta solo il disegno.
function MolAndamento({
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
  // Con i costi mancanti questa curva e' quella del MOL gonfiato: ambra come la
  // card, e il delta senza verde/rosso. Copiato da `MolSparkline` della catena
  // (sintesi-catena.tsx), che risolveva gia' lo stesso caso: fino al 17/09/2026
  // la Home neutralizzava il numero grande e il Trend ma lasciava qui sotto una
  // curva verde con la freccia in su, cioe' la stessa contraddizione ottanta
  // righe piu' in basso.
  const colore = affidabile ? stroke : "text-incerto";
  const coloreDelta = affidabile
    ? su ? "text-positivo" : "text-negativo"
    : "text-muted-foreground";

  return (
    <div className="mt-4 border-t pt-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground/70">
          Andamento margine{anno ? ` ${anno}` : ""}{!affidabile && " · dati incompleti"}
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
      <svg
        viewBox="0 0 240 40"
        className="h-10 w-full overflow-visible"
        preserveAspectRatio="none"
        role="img"
        aria-label="Andamento del margine nei mesi dell'anno"
      >
        <path d={d} fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={cn("stroke-current", colore)} />
        <circle cx={cx} cy={cy} r="3" className={cn("fill-current", colore)} />
      </svg>
    </div>
  );
}

export function KpiBlock({ kpi, settore }: { kpi: HomeKpi; settore?: Settore | null }) {
  if (!kpi.has_data) return null;
  const molPos = kpi.mol >= 0;
  /**
   * Con i costi mancanti il MOL non e' un risultato: e' un buco.
   *
   * Il banner ambra qui sotto lo dichiara dal 18/06, ma fino al 17/09/2026 il
   * numero restava verde e gigante e il trend restava "in meglio" — la pagina si
   * contraddiceva nella stessa schermata. Su una sede reale mostrava 416.798 €
   * in verde su un mese con costi e personale a zero, cioe' un margine del 100%.
   *
   * Il giallo, non il grigio: e' quello che la Catena fa gia' col MOL di gruppo
   * (`tintConti`, «il presidio che impedisce a un MOL gonfiato di sembrare una
   * vittoria»), e lega il numero al banner ambra che lo spiega. Stessa palette
   * condivisa, cosi' le due viste non divergono.
   *
   * La decisione sta in `tintContiPV` (lib/catena-confronti) e non qui: dentro
   * il .tsx nessun test la raggiungerebbe.
   */
  const tint = SALUTE_TINT[tintContiPV(kpi)];
  const molAttendibile = !kpi.costi_mancanti;

  return (
    <div
      className={cn(
        "relative flex h-full flex-col overflow-hidden rounded-2xl border p-5 sm:p-6",
        tint.card,
      )}
    >
      <div className={cn("pointer-events-none absolute -right-16 -top-16 size-56 rounded-full blur-3xl", tint.orb1)} />
      <div className={cn("pointer-events-none absolute -bottom-20 left-1/4 size-52 rounded-full blur-3xl", tint.orb2)} />

      <div className="mb-4 flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">I tuoi conti</h2>
        <span className="text-xs text-muted-foreground/70">{kpi.periodo_label}</span>
      </div>

      {/* MOL — il numero che conta. Cliccabile: porta alla pagina Margini. */}
      <Link
        href="/margini"
        className="group flex flex-1 flex-col items-center justify-center gap-1 rounded-xl py-4 text-center transition-colors hover:bg-background/40"
      >
        <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">
          = MOL (margine)
        </span>
        <div className={cn("text-4xl font-black tabular-nums leading-none sm:text-5xl", tint.text)}>
          {formatEuro(kpi.mol)}
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground/60">
          {kpi.confronto_label && <span>{kpi.confronto_label}</span>}
          {/* MOL negativo -> trend neutro (mai verde): "meno in perdita" non e' una
              vittoria da festeggiare. Stessa cosa coi costi mancanti: il delta
              confronta un margine gonfiato con uno vero. */}
          <Trend delta={kpi.mol_delta_pct} suffix="%" buonoSeSu neutro={!molPos || !molAttendibile} />
        </div>
      </Link>

      {/* Costi mancanti: il mese ha ricavi ma zero fatture costo (food cost 0%).
          Il MOL e' gonfiato — lo diciamo chiaro invece di mostrare un margine
          finto e un trend "in meglio". Coerente con la card Salute e il briefing. */}
      {kpi.costi_mancanti && (
        <Link
          href="/analisi-fatture"
          className="mt-2 flex items-start gap-2 rounded-xl border border-incerto/30 bg-incerto/10 px-3 py-2 text-xs text-incerto transition-colors hover:bg-incerto/10"
        >
          <span className="mt-px">⚠</span>
          <span>
            Mancano le fatture costo di {kpi.periodo_label.toLowerCase()}: il{" "}
            {costoMerceLabel(settore).toLowerCase()} risulta 0 e questo margine non è reale.
            Si aggiorna da solo appena arrivano.
          </span>
        </Link>
      )}

      {/* Breakdown */}
      <div className="mt-auto space-y-1.5">
        <RigaVoce
          colore="emerald"
          label="Fatturato"
          value={formatEuro(kpi.fatturato)}
          delta={kpi.fatturato_delta_pct}
          suffix="%"
          buonoSeSu
          valoreZero={kpi.fatturato === 0}
          href="/margini"
        />
        <RigaVoce
          colore="amber"
          // La Home scrive "Food cost" con la c minuscola, `costoMerceLabel`
          // restituisce "Food Cost": usarla qui cambierebbe un'etichetta a un
          // ristorante, che e' esattamente il vincolo da non violare.
          label={settore === "retail" ? costoMerceLabel(settore) : "Food cost"}
          value={
            kpi.food_cost_pct != null
              ? `${kpi.food_cost_pct.toLocaleString("it-IT")}%`
              : "—"
          }
          delta={kpi.food_cost_delta_pp}
          suffix="pp"
          buonoSeSu={false}
          segno="−"
          valoreZero={kpi.food_cost_pct == null || kpi.food_cost_pct === 0}
          href="/prezzi"
        />
        <RigaVoce
          colore="amber"
          label="Costo personale"
          value={formatEuro(kpi.costo_personale)}
          delta={kpi.personale_delta_pct}
          suffix="%"
          buonoSeSu={false}
          segno="−"
          valoreZero={kpi.costo_personale === 0}
          href="/margini"
        />
        <RigaVoce
          colore="amber"
          label="Spese generali"
          value={formatEuro(kpi.spese_generali)}
          delta={kpi.spese_delta_pct}
          suffix="%"
          buonoSeSu={false}
          segno="−"
          valoreZero={kpi.spese_generali === 0}
          href="/margini"
        />
      </div>

      {/* Andamento MOL nell'anno: fascia a sé in fondo, con periodo e % YTD.
          Nessuna soglia qui: la decide calcolaSparkline (che con < 2 punti
          torna null). Prima questo call-site diceva `> 0` mentre la guardia
          vera era `< 2` — due numeri per la stessa regola, in due file. */}
      <MolAndamento punti={kpi.mol_mensile} anno={kpi.mol_mensile_anno} affidabile={molAttendibile} />
    </div>
  );
}
