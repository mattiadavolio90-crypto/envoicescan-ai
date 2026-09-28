import Link from "next/link";
import { ArrowDown, ArrowUp, Minus, TriangleAlert } from "lucide-react";
import { type HomeKpi } from "@/lib/home";
import { tintContiPV } from "@/lib/catena-confronti";
import { formatEuro } from "@/lib/format";
import { tintaTrend } from "@/lib/home-kpi";
import { costoMerceLabel, type Settore } from "@/lib/categorie-spesa";
import { SALUTE_TINT } from "@/lib/salute-tint";
import { cn } from "@/lib/utils";
import { AndamentoMargine, CardHome, EtichettaKpi, TesseraVoce } from "@/components/home/card-home";

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


export function KpiBlock({ kpi, settore }: { kpi: HomeKpi; settore?: Settore | null }) {
  if (!kpi.has_data) return null;
  const molPos = kpi.mol >= 0;
  /**
   * Con i costi mancanti il MOL non e' un risultato: e' un buco.
   *
   * Il banner ambra qui sotto lo dichiara dal 18/06, ma fino al 17/09/2026 il
   * numero restava verde e il trend restava "in meglio" — la pagina si
   * contraddiceva nella stessa schermata. Su una sede reale mostrava 416.798 €
   * in verde su un mese con costi e personale a zero, cioe' un margine del 100%.
   *
   * Il giallo, non il grigio: e' quello che la Catena fa gia' col MOL di gruppo
   * (`tintConti`), e lega il numero al banner ambra che lo spiega.
   *
   * La decisione sta in `tintContiPV` (lib/catena-confronti) e non qui: dentro
   * il .tsx nessun test la raggiungerebbe.
   */
  const tint = SALUTE_TINT[tintContiPV(kpi)];
  const molAttendibile = !kpi.costi_mancanti;

  return (
    <CardHome titolo="I tuoi conti" meta={kpi.periodo_label}>
      {/* MOL — il numero che conta, l'unico colorato. Porta alla pagina Margini.
          Accanto, l'andamento nell'anno (nessuna soglia qui: calcolaSparkline
          torna null con meno di 2 punti). */}
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <Link href="/margini" className="flex min-w-0 flex-col gap-1 rounded-md hover:opacity-80">
          <EtichettaKpi>MOL (margine)</EtichettaKpi>
          <span className={cn("text-2xl font-bold leading-tight tabular-nums", tint.text)}>
            {formatEuro(kpi.mol)}
          </span>
          <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            {kpi.confronto_label && <span>{kpi.confronto_label}</span>}
            {/* MOL negativo -> trend neutro (mai verde): "meno in perdita" non e'
                una vittoria. Stessa cosa coi costi mancanti: il delta confronta
                un margine gonfiato con uno vero. */}
            <Trend delta={kpi.mol_delta_pct} suffix="%" buonoSeSu neutro={!molPos || !molAttendibile} />
          </span>
        </Link>
        <AndamentoMargine punti={kpi.mol_mensile} anno={kpi.mol_mensile_anno} affidabile={molAttendibile} />
      </div>

      {/* Costi mancanti: il mese ha ricavi ma zero fatture costo (food cost 0%).
          Il MOL e' gonfiato — lo diciamo chiaro invece di mostrare un margine
          finto. Coerente con la card della completezza e il briefing. */}
      {kpi.costi_mancanti && (
        <Link
          href="/analisi-fatture"
          className="flex items-start gap-2 rounded-lg border border-incerto/30 bg-incerto/10 px-3 py-2 text-xs text-incerto transition-colors hover:border-incerto/60"
        >
          <TriangleAlert className="mt-px size-3.5 shrink-0" />
          <span>
            Mancano le fatture costo di {kpi.periodo_label.toLowerCase()}: il{" "}
            {costoMerceLabel(settore).toLowerCase()} risulta 0 e questo margine non è reale.
            Si aggiorna da solo appena arrivano.
          </span>
        </Link>
      )}

      <div className="grid grid-cols-2 gap-2">
        <TesseraVoce
          label="Fatturato"
          valore={formatEuro(kpi.fatturato)}
          extra={<Trend delta={kpi.fatturato_delta_pct} suffix="%" buonoSeSu sopprimi={kpi.fatturato === 0} />}
          href="/margini"
        />
        <TesseraVoce
          // La Home scrive "Food cost" con la c minuscola, `costoMerceLabel`
          // restituisce "Food Cost": usarla qui cambierebbe un'etichetta a un
          // ristorante, che e' esattamente il vincolo da non violare.
          label={settore === "retail" ? costoMerceLabel(settore) : "Food cost"}
          segno="−"
          valore={kpi.food_cost_pct != null ? `${kpi.food_cost_pct.toLocaleString("it-IT")}%` : "—"}
          extra={
            <Trend
              delta={kpi.food_cost_delta_pp}
              suffix="pp"
              buonoSeSu={false}
              sopprimi={kpi.food_cost_pct == null || kpi.food_cost_pct === 0}
            />
          }
          href="/prezzi"
        />
        <TesseraVoce
          label="Costo personale"
          segno="−"
          valore={formatEuro(kpi.costo_personale)}
          extra={<Trend delta={kpi.personale_delta_pct} suffix="%" buonoSeSu={false} sopprimi={kpi.costo_personale === 0} />}
          href="/margini"
        />
        <TesseraVoce
          label="Spese generali"
          segno="−"
          valore={formatEuro(kpi.spese_generali)}
          extra={<Trend delta={kpi.spese_delta_pct} suffix="%" buonoSeSu={false} sopprimi={kpi.spese_generali === 0} />}
          href="/margini"
        />
      </div>
    </CardHome>
  );
}
