"use client";

// Le schede dell'Osservatorio prezzi, condivise col prezzi di catena (13/10/2026):
// la stessa riga, lo stesso grafico, la stessa lista acquisti, gli stessi KPI.
// Erano dentro app/(app)/prezzi/variazioni-tab.tsx; spostate qui senza cambiare
// cosa vede il PV, perche' la catena non ne facesse una copia che diverge.

import { memo, type ReactNode } from "react";
import { ChevronDown, Info, Star, TriangleAlert } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { StoricoPrezzoResponse, StoricoPrezzoPoint } from "@/lib/prezzi";
import { parseDecimaleIt, formatEuro } from "@/lib/format";
import { puntiSparkline } from "@/lib/sparkline-punti";
import {
  LEGENDA_GRAVITA,
  NOTA_OLTRE_SEI_MESI,
  SPIEGAZIONE_DA_CONTROLLARE,
  gravita,
  nomeProdotto,
  type Gravita,
} from "@/lib/prezzi-viste";

// Simbolo in coda come il resto del prodotto. Il «+» pero' resta e non si puo'
// delegare a formatEuro, che non lo produce: nell'impatto/mese distingue un rincaro
// («+18,05 €») da un risparmio, ed e' l'informazione della colonna.
export function fmtEuro(v: number, withSign = false, decimali = 2): string {
  const segno = withSign && v > 0 ? "+" : "";
  return `${segno}${formatEuro(v, decimali)}`;
}

export function fmtPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toLocaleString("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

export function fmtData(s: string): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

export { LEGENDA_GRAVITA, gravita, type Gravita };

// La gravita' misura QUANTO e' grande la variazione, non se e' buona o cattiva:
// un risparmio del 95% e' "critico" quanto un rincaro del 95%. Per questo e' una
// scala di grigi; il giudizio (rosso/verde) sta sull'impatto in euro accanto.
export const GRAVITA_STYLE: Record<Gravita, { dot: string; ring: string; label: string }> = {
  critico: { dot: "bg-foreground", ring: "border-l-foreground", label: "Critico" },
  alto: { dot: "bg-muted-foreground", ring: "border-l-muted-foreground", label: "Alto" },
  medio: { dot: "bg-muted-foreground/50", ring: "border-l-muted-foreground/50", label: "Medio" },
};

/**
 * Larghezze delle tre colonne di prezzo, condivise fra l'intestazione della
 * lista e ogni riga. Sono l'unico modo per allineare colonne dentro card in
 * flex: senza, ogni riga si dimensiona sul proprio contenuto e i numeri non
 * stanno incolonnati. `w-20` regge "€1.234,56"; l'ultimo e' piu' largo perche'
 * sotto ci sta anche la percentuale ("+123,4%").
 */
export const COL_MEDIA = "w-20";
export const COL_PENULTIMO = "w-20";
export const COL_ULTIMO = "w-24";
/** Larghezza della colonna «Punto vendita» (solo catena), condivisa con l'intestazione. */
export const COL_PUNTO_VENDITA = "w-44";

/** Fallback: ricava i punti dalla stringa di presentazione "€1,20 → €1,35".
 *  Perde i decimali oltre il secondo — usare `storico_valori` quando c'e'. */
function parseStorico(s: string): number[] {
  if (!s) return [];
  return s
    .split("→")
    .map((p) => parseDecimaleIt(p))
    .filter((n) => !isNaN(n));
}

export function Sparkline({ values }: { values: number[] }) {
  const w = 96;
  const h = 32;
  const points = puntiSparkline(values, { w, h });
  if (!points) return <div className="h-8 w-24" />;
  // Grigio dal 17/09/2026: la direzione la dice gia' la linea stessa (sale o
  // scende) e, dove conta, l'impatto in euro. Colorarla era il terzo rosso
  // della riga.
  const stroke = "rgb(148 163 184)";
  const coppie = points.split(" ").map((p) => p.split(","));
  return (
    <svg width={w} height={h} className="overflow-visible shrink-0">
      <polyline points={points} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      {/* I pallini stanno sui punti della linea: si leggono da `points` invece
          di ricalcolare la stessa formula, che e' il modo in cui due disegni
          della stessa curva finiscono per divergere. */}
      {coppie.map(([cx, cy], i) => (
        <circle
          key={i}
          cx={cx}
          cy={cy}
          r={i === coppie.length - 1 ? 2.5 : 1.5}
          fill={i === coppie.length - 1 ? stroke : "rgb(148 163 184)"}
        />
      ))}
    </svg>
  );
}

type ChartPoint = { data: string; var_pct: number; prezzo: number; label: string };

const TOOLTIP_STYLE = {
  backgroundColor: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  fontSize: 11,
  color: "var(--foreground)",
};

export function PrezzoChart({
  storico,
  media,
  fallbackPrezzi,
}: {
  storico: StoricoPrezzoResponse | null;
  media: number;
  fallbackPrezzi?: number[];
}) {
  const punti = storico?.punti ?? [];
  const mediaUsata = storico?.prezzo_medio ?? media;

  let chartData: ChartPoint[];

  if (punti.length >= 2) {
    chartData = punti.map((p) => ({
      data: fmtData(p.data),
      prezzo: p.prezzo_unitario,
      var_pct: mediaUsata > 0 ? Math.round(((p.prezzo_unitario - mediaUsata) / mediaUsata) * 1000) / 10 : 0,
      label: fmtEuro(p.prezzo_unitario),
    }));
  } else if (fallbackPrezzi && fallbackPrezzi.length >= 2) {
    const fb = fallbackPrezzi;
    const fbMedia = fb.reduce((a, b) => a + b, 0) / fb.length;
    chartData = fb.map((p, i) => ({
      data: `#${i + 1}`,
      prezzo: p,
      var_pct: fbMedia > 0 ? Math.round(((p - fbMedia) / fbMedia) * 1000) / 10 : 0,
      label: fmtEuro(p),
    }));
  } else {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        Dati insufficienti per il grafico
      </p>
    );
  }

  const maxAbs = Math.max(...chartData.map((d) => Math.abs(d.var_pct)), 1);
  const domain: [number, number] = [-Math.ceil(maxAbs * 1.2), Math.ceil(maxAbs * 1.2)];
  const mediaLabel = punti.length >= 2 ? mediaUsata : (fallbackPrezzi ?? []).reduce((a, b) => a + b, 0) / (fallbackPrezzi?.length || 1);

  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Media: <span className="font-semibold text-foreground">{fmtEuro(mediaLabel)}</span>
        {punti.length < 2 && fallbackPrezzi && fallbackPrezzi.length >= 2 && (
          <span className="ml-2 text-incerto">(ultimi {fallbackPrezzi.length} acquisti disponibili)</span>
        )}
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={chartData} margin={{ top: 8, right: 24, bottom: 4, left: 8 }}>
          <XAxis dataKey="data" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
          <YAxis
            domain={domain}
            tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`}
          />
          <Tooltip
            formatter={(value, _name, props) => {
              const v = typeof value === "number" ? value : 0;
              const payload = props.payload as ChartPoint | undefined;
              return [`${fmtPct(v)} (${payload?.label ?? ""})`, "Variazione"];
            }}
            labelStyle={{ fontSize: 11, color: "var(--muted-foreground)" }}
            itemStyle={{ color: "var(--foreground)" }}
            contentStyle={TOOLTIP_STYLE}
          />
          <ReferenceLine
            y={0}
            stroke="var(--muted-foreground)"
            strokeDasharray="4 4"
            strokeWidth={1.5}
            label={{
              value: "Media",
              position: "insideTopRight",
              fontSize: 10,
              fill: "var(--muted-foreground)",
              dy: -4,
            }}
          />
          <Line type="monotone" dataKey="var_pct" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: "var(--primary)" }} activeDot={{ r: 5, fill: "var(--primary)", stroke: "var(--card)", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// Lista degli acquisti (= punti storico, dal più recente) sotto il grafico.
// Ogni riga è una riga di fattura cliccabile per aprire l'anteprima. Niente
// fetch extra: sono gli stessi dati del grafico, arricchiti col file_origine.
export function ListaAcquisti({
  punti,
  media,
  onApriFattura,
  puntoVendita,
}: {
  punti: StoricoPrezzoPoint[];
  media: number;
  /** Assente: righe non cliccabili. */
  onApriFattura?: (p: StoricoPrezzoPoint) => void;
  /** Catena: di quale punto vendita sono gli acquisti. */
  puntoVendita?: string;
}) {
  const conFattura = onApriFattura ? punti.filter((p) => p.fattura) : punti;
  if (conFattura.length === 0) return null;

  // Dal più recente: i punti arrivano ordinati per data crescente dal worker.
  const ordinati = [...conFattura].reverse();

  return (
    <div className="mt-4">
      <p className="text-xs font-medium text-muted-foreground mb-2">
        Acquisti{puntoVendita ? ` di ${puntoVendita}` : ""} nel periodo ({ordinati.length}){onApriFattura ? " — clicca per aprire la fattura" : ""}
      </p>
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Data</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Fattura</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Quantità</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Prezzo unitario</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Totale</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Rispetto alla media</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50">
              {ordinati.map((p, i) => {
                const delta = media > 0 ? ((p.prezzo_unitario - media) / media) * 100 : 0;
                return (
                  <tr
                    key={`${p.fattura}-${i}`}
                    onClick={onApriFattura ? () => onApriFattura(p) : undefined}
                    className={onApriFattura ? "cursor-pointer hover:bg-muted/30 transition-colors" : undefined}
                  >
                    <td className="px-3 py-2 tabular-nums">{fmtData(p.data)}</td>
                    <td className="px-3 py-2 max-w-[160px]">
                      <span className={`${onApriFattura ? "text-primary" : ""} truncate inline-block max-w-full align-bottom`} title={p.numero_documento || "—"}>
                        {p.numero_documento || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.quantita ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">{fmtEuro(p.prezzo_unitario, false, 4)}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {p.totale_riga != null ? fmtEuro(p.totale_riga) : "—"}
                    </td>
                    <td className={`px-3 py-2 text-right tabular-nums ${delta > 0.05 ? "text-negativo" : delta < -0.05 ? "text-positivo" : "text-muted-foreground"}`}>
                      {Math.abs(delta) < 0.05 ? "—" : fmtPct(delta)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

/** I campi che la scheda legge: comuni alla variazione del PV e a quella di catena. */
export type RigaVariazione = {
  prodotto: string;
  fornitore: string;
  categoria: string;
  data: string;
  media: number;
  penultimo: number;
  ultimo: number;
  aumento_perc: number;
  impatto_stimato: number;
  /** Stringa «€1,20 → €1,35»: solo fallback per risposte vecchie in cache. */
  storico?: string;
  storico_valori?: number[];
};

/**
 * Una variazione di prezzo: la stessa scheda nell'Osservatorio del PV e nella
 * scheda «Prezzi» di catena (Mattia, 13/10/2026: «voglio coerenza con prezzi
 * dei punti vendita singoli»). La catena aggiunge solo la colonna del punto
 * vendita (`puntoVendita`), con la stessa larghezza dell'intestazione.
 */
function VariazioneCardBase<R extends RigaVariazione>({
  r,
  expanded,
  preferito,
  storico,
  storicoLoading,
  onToggle,
  onToggleStar,
  onApriFattura,
  puntoVendita,
  nomePuntoVendita,
}: {
  r: R;
  expanded: boolean;
  preferito: boolean;
  storico: StoricoPrezzoResponse | null;
  storicoLoading: boolean;
  onToggle: (r: R) => void;
  onToggleStar: (r: R) => void;
  onApriFattura?: (r: R, p: StoricoPrezzoPoint) => void;
  puntoVendita?: ReactNode;
  /** Il nome del punto vendita sopra la lista acquisti (catena). */
  nomePuntoVendita?: string;
}) {
  const g = gravita(r);
  const style = GRAVITA_STYLE[g];
  // storico_valori arriva grezzo dal worker; parseStorico resta come fallback per
  // le response servite dalla cache prima del deploy che ha aggiunto il campo.
  const spark = r.storico_valori ?? parseStorico(r.storico ?? "");
  const { nome, oltreSeiMesi } = nomeProdotto(r.prodotto);

  return (
    <div className={`rounded-lg border border-l-4 ${style.ring} border-border bg-card overflow-hidden`}>
      <button onClick={() => onToggle(r)} className="w-full text-left px-4 py-3 hover:bg-muted/30 transition-colors">
        <div className="flex items-center gap-3 flex-wrap">
          <span
            role="button"
            tabIndex={0}
            onClick={(e) => { e.stopPropagation(); onToggleStar(r); }}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onToggleStar(r); } }}
            aria-label={preferito ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
            aria-pressed={preferito}
            className="shrink-0 -m-1 p-1 rounded hover:bg-muted transition-colors cursor-pointer"
          >
            <Star className={`size-4 transition-colors ${preferito ? "fill-incerto text-incerto" : "text-muted-foreground/50 hover:text-incerto"}`} />
          </span>
          <span className={`size-2.5 rounded-full ${style.dot} shrink-0`} aria-hidden />

          <div className="min-w-0 flex-1">
            <p className="font-semibold text-sm truncate" title={nome}>{nome}</p>
            <p className="text-xs text-muted-foreground truncate" title={`${r.fornitore} · ${r.categoria} · ${fmtData(r.data)}`}>
              {r.fornitore} · {r.categoria} · {fmtData(r.data)}
            </p>
            {/* « ⚠️ >6m» in coda al nome non si capiva (13/10/2026): per esteso. */}
            {oltreSeiMesi && (
              <p className="text-xs text-incerto truncate" title={NOTA_OLTRE_SEI_MESI}>{NOTA_OLTRE_SEI_MESI}</p>
            )}
          </div>

          {puntoVendita !== undefined && <div className={`min-w-0 shrink-0 ${COL_PUNTO_VENDITA}`}>{puntoVendita}</div>}

          {/* Le tre etichette ("MEDIA PERIODO / PRIMA / ORA") stanno una volta
              sola nell'intestazione sopra la lista (17/09/2026). Le larghezze
              fisse COL_* sono condivise con quell'intestazione: servono a tenere
              le colonne in fila, e cambiarne una qui senza cambiarla la' scolla i
              titoli dai dati. */}
          <div className={`text-right shrink-0 ${COL_MEDIA}`}>
            <p className="text-xs tabular-nums text-muted-foreground">{fmtEuro(r.media)}</p>
          </div>

          <div className={`text-right shrink-0 ${COL_PENULTIMO}`}>
            <p className="text-xs tabular-nums text-muted-foreground">{fmtEuro(r.penultimo)}</p>
          </div>

          <div className={`text-right shrink-0 ${COL_ULTIMO}`}>
            <p className="text-xs font-bold tabular-nums text-foreground">{fmtEuro(r.ultimo)}</p>
            {/* Percentuale neutra dal 17/09/2026: il giudizio (rosso/verde) sta
                sull'impatto in euro qui a destra, che segue il SEGNO. */}
            <p className="text-lg font-bold leading-tight tabular-nums">
              {fmtPct(r.aumento_perc)}
            </p>
          </div>

          <Sparkline values={spark} />

          <div className="text-right shrink-0 w-28">
            <p className={`text-sm font-semibold ${r.impatto_stimato > 0 ? "text-negativo" : r.impatto_stimato < 0 ? "text-positivo" : "text-muted-foreground"}`}>
              {r.impatto_stimato !== 0 ? fmtEuro(r.impatto_stimato, true) : "—"}
            </p>
          </div>

          <ChevronDown className={`size-4 text-muted-foreground transition-transform shrink-0 ${expanded ? "rotate-180" : ""}`} />
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 py-3 bg-muted/10">
          {storicoLoading ? (
            <div className="h-20 flex items-center justify-center text-sm text-muted-foreground">Caricamento storico…</div>
          ) : (
            <>
              <PrezzoChart
                storico={storico}
                media={r.media}
                fallbackPrezzi={spark.length >= 2 ? spark : undefined}
              />
              {storico && (
                <ListaAcquisti
                  punti={storico.punti}
                  media={storico.prezzo_medio || r.media}
                  onApriFattura={onApriFattura ? (p) => onApriFattura(r, p) : undefined}
                  puntoVendita={nomePuntoVendita}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export const VariazioneCard = memo(VariazioneCardBase) as typeof VariazioneCardBase;

/**
 * Le etichette delle colonne una volta sola sopra la lista. Ricalca la riga di
 * VariazioneCard — stessi spazi per stella, pallino, nome, sparkline e chevron —
 * perche' le colonne restino incolonnate. Nascosta sotto sm: li' la riga va a
 * capo e un'intestazione a colonne non corrisponderebbe piu' a nulla.
 */
export function IntestazioneVariazioni({ conPuntoVendita = false }: { conPuntoVendita?: boolean }) {
  return (
    <div
      aria-hidden
      className="hidden sm:flex items-center gap-3 px-4 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground"
    >
      <span className="size-4 shrink-0" />
      <span className="size-2.5 shrink-0" />
      <span className="min-w-0 flex-1" />
      {conPuntoVendita && <span className={`shrink-0 ${COL_PUNTO_VENDITA}`}>Punto vendita</span>}
      <span className={`text-right shrink-0 ${COL_MEDIA}`}>Media periodo</span>
      <span className={`text-right shrink-0 ${COL_PENULTIMO}`}>Prima</span>
      <span className={`text-right shrink-0 ${COL_ULTIMO}`}>Ora</span>
      <span className="w-24 shrink-0" />
      <span className="text-right shrink-0 w-28">Impatto/mese</span>
      <span className="size-4 shrink-0" />
    </div>
  );
}

/** «N variazioni (filtrate da M) · K critiche» e la legenda della striscia. */
export function ContaVariazioni({
  n,
  base,
  critiche,
  nome = "variazioni",
  nomeCritiche = "critiche",
  filtrate = "filtrate",
}: {
  n: number;
  base: number;
  critiche: number;
  nome?: string;
  nomeCritiche?: string;
  /** Il participio concorda col nome: «prodotti (filtrati da N)». */
  filtrate?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <TriangleAlert className="size-4 text-negativo shrink-0" />
      <p className="text-sm font-semibold">
        {n} {nome}
        {n !== base && <span className="text-muted-foreground font-normal"> ({filtrate} da {base})</span>}
        {critiche > 0 && <span className="font-medium text-foreground"> · {critiche} {nomeCritiche}</span>}
      </p>
      <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-foreground shrink-0" />Critico</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-muted-foreground shrink-0" />Alto</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-muted-foreground/50 shrink-0" />Medio</span>
      </div>
    </div>
  );
}

// «neutro» per un conteggio, che non e' ne' buono ne' cattivo (catena: prodotti
// con prezzi diversi fra i PV).
export type KpiTone = "positivo" | "negativo" | "neutro";

const KPI_TONE: Record<KpiTone, { border: string; hover: string; value: string }> = {
  positivo: { border: "border-positivo/40", hover: "hover:border-positivo/70", value: "text-positivo" },
  negativo: { border: "border-negativo/40", hover: "hover:border-negativo/70", value: "text-negativo" },
  neutro: { border: "border-border", hover: "hover:border-foreground/30", value: "text-foreground" },
};

export function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: KpiTone }) {
  const t = KPI_TONE[tone];
  return (
    <div className={`rounded-xl border ${t.border} ${t.hover} bg-card px-4 py-3 flex flex-col gap-1 transition-colors`}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">{label}</span>
      <span className={`text-2xl font-bold tracking-tight leading-tight ${t.value}`}>{value}</span>
      {sub && <span className="text-[11px] text-muted-foreground leading-tight truncate" title={sub}>{sub}</span>}
    </div>
  );
}

/** Al posto dei totali nella vista «Confezione diversa?»: il perche' di quelle righe. */
export function SpiegazioneDaControllare() {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span>{SPIEGAZIONE_DA_CONTROLLARE}</span>
    </p>
  );
}
