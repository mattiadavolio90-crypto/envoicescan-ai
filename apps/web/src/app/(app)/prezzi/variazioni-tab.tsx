"use client";

import { useState, useEffect, useCallback, useMemo, memo } from "react";
import { RefreshCw, ChevronDown, Search, TriangleAlert, CheckCircle2, Calendar, Settings2, Star } from "lucide-react";
import { toast } from "sonner";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import type { VariazioniResponse, VariazionePrezzo, StoricoPrezzoResponse, StoricoPrezzoPoint } from "@/lib/prezzi";
import { Input } from "@/components/ui/input";
import { InfoPopover } from "@/components/ui/info-popover";
import { AnteprimaFatturaDialog } from "./anteprima-fattura-dialog";
import { parseDecimaleIt } from "@/lib/format";
import { puntiSparkline } from "@/lib/sparkline-punti";

const ANNO_CORRENTE = new Date().getFullYear();
const PAGE_SIZE = 100;
const MESI_LUNGHI = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"];

type ModoPeriodo = "anno" | "mese" | "custom";

function isoDateRange(anno: number, mese: number | null): { data_da: string; data_a: string } {
  if (mese === null) return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
  const lastDay = new Date(anno, mese, 0).getDate();
  const mm = String(mese).padStart(2, "0");
  return { data_da: `${anno}-${mm}-01`, data_a: `${anno}-${mm}-${lastDay}` };
}

function fmtRangeIt(da: string, a: string): string {
  const f = (iso: string) => {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y.slice(2)}`;
  };
  return `${f(da)} → ${f(a)}`;
}

function fmtEuro(v: number, withSign = false): string {
  const sign = withSign && v > 0 ? "+" : v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(v))}`;
}

function fmtPct(v: number): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function fmtData(s: string): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return s;
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

// Chiave preferito: gemella di _pulisci_desc_key/_pulisci_forn_key del worker.
// Rimuove i suffissi UI (" ⚠️ >6m"), UPPER+TRIM. Serve per aggiornare in modo
// ottimistico il Set locale dei preferiti coerentemente col campo `preferito`
// che arriva dal server.
const SUFFISSI_UI = [" ⚠️ >6M", " ⚠ >6M"];
function prefKey(prodotto: string, fornitore: string): string {
  let d = prodotto.trim().toUpperCase();
  for (const s of SUFFISSI_UI) {
    if (d.endsWith(s)) {
      d = d.slice(0, -s.length).trim();
      break;
    }
  }
  return `${d}|${fornitore.trim().toUpperCase()}`;
}

type Gravita = "critico" | "alto" | "medio";

function gravita(r: VariazionePrezzo): Gravita {
  const imp = Math.abs(r.impatto_stimato);
  if (imp >= 100) return "critico";
  if (imp >= 30) return "alto";
  return "medio";
}

// La gravita' misura QUANTO e' grande la variazione, non se e' buona o cattiva:
// un risparmio del 95% e' "critico" quanto un rincaro del 95%. Per questo e' una
// scala di grigi; il giudizio (rosso/verde) sta sull'impatto in euro accanto.
const GRAVITA_STYLE: Record<Gravita, { dot: string; ring: string; label: string }> = {
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
const COL_MEDIA = "w-20";
const COL_PENULTIMO = "w-20";
const COL_ULTIMO = "w-24";

/** Fallback: ricava i punti dalla stringa di presentazione "€1,20 → €1,35".
 *  Perde i decimali oltre il secondo — usare `storico_valori` quando c'e'. */
function parseStorico(s: string): number[] {
  if (!s) return [];
  return s
    .split("→")
    .map((p) => parseDecimaleIt(p))
    .filter((n) => !isNaN(n));
}

function Sparkline({ values }: { values: number[] }) {
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

function PrezzoChart({
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
      label: `€${p.prezzo_unitario.toFixed(2)}`,
    }));
  } else if (fallbackPrezzi && fallbackPrezzi.length >= 2) {
    const fb = fallbackPrezzi;
    const fbMedia = fb.reduce((a, b) => a + b, 0) / fb.length;
    chartData = fb.map((p, i) => ({
      data: `#${i + 1}`,
      prezzo: p,
      var_pct: fbMedia > 0 ? Math.round(((p - fbMedia) / fbMedia) * 1000) / 10 : 0,
      label: `€${p.toFixed(2)}`,
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
        Media: <span className="font-semibold text-foreground">€{mediaLabel.toFixed(2)}</span>
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
              return [`${v > 0 ? "+" : ""}${v.toFixed(1)}% (${payload?.label ?? ""})`, "Variazione"];
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
function ListaAcquisti({
  punti,
  media,
  onApriFattura,
}: {
  punti: StoricoPrezzoPoint[];
  media: number;
  onApriFattura: (p: StoricoPrezzoPoint) => void;
}) {
  const conFattura = punti.filter((p) => p.fattura);
  if (conFattura.length === 0) return null;

  // Dal più recente: i punti arrivano ordinati per data crescente dal worker.
  const ordinati = [...conFattura].reverse();

  return (
    <div className="mt-4">
      <p className="text-xs font-medium text-muted-foreground mb-2">
        Acquisti nel periodo ({ordinati.length}) — clicca per aprire la fattura
      </p>
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/40">
              <tr>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Data</th>
                <th className="text-left px-3 py-2 text-muted-foreground font-medium">Fattura</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Qtà</th>
                <th className="text-right px-3 py-2 text-muted-foreground font-medium">Prezzo unit.</th>
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
                    onClick={() => onApriFattura(p)}
                    className="cursor-pointer hover:bg-muted/30 transition-colors"
                  >
                    <td className="px-3 py-2 tabular-nums">{fmtData(p.data)}</td>
                    <td className="px-3 py-2 max-w-[160px]">
                      <span className="text-primary truncate inline-block max-w-full align-bottom" title={p.numero_documento || "—"}>
                        {p.numero_documento || "—"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{p.quantita ?? "—"}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">€{p.prezzo_unitario.toFixed(4)}</td>
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

const AlertCard = memo(function AlertCard({
  r,
  expanded,
  preferito,
  storico,
  storicoLoading,
  onToggle,
  onToggleStar,
  onApriFattura,
}: {
  r: VariazionePrezzo;
  expanded: boolean;
  preferito: boolean;
  storico: StoricoPrezzoResponse | null;
  storicoLoading: boolean;
  onToggle: (r: VariazionePrezzo) => void;
  onToggleStar: (r: VariazionePrezzo) => void;
  onApriFattura: (r: VariazionePrezzo, p: StoricoPrezzoPoint) => void;
}) {
  const g = gravita(r);
  const style = GRAVITA_STYLE[g];
  // storico_valori arriva grezzo dal worker; parseStorico resta come fallback per
  // le response servite dalla cache prima del deploy che ha aggiunto il campo.
  const spark = r.storico_valori ?? parseStorico(r.storico);

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
            <p className="font-semibold text-sm truncate" title={r.prodotto}>{r.prodotto}</p>
            <p className="text-xs text-muted-foreground truncate" title={`${r.fornitore} · ${r.categoria} · ${fmtData(r.data)}`}>
              {r.fornitore} · {r.categoria} · {fmtData(r.data)}
            </p>
          </div>

          {/* Le tre etichette ("MEDIA PERIODO / PENULTIMO / ULTIMO") stavano qui
              dentro, cioe' ripetute in ognuna delle 76 righe della pagina. Dal
              17/09/2026 stanno una volta sola nell'intestazione sopra la lista.
              Le larghezze fisse COL_* sono condivise con quell'intestazione:
              servono a tenere le colonne in fila (prima ondulavano di 20-40 px
              da una riga all'altra, a seconda della lunghezza delle cifre) e
              cambiarne una qui senza cambiarla la' scolla i titoli dai dati. */}
          <div className={`text-right shrink-0 ${COL_MEDIA}`}>
            <p className="text-xs tabular-nums text-muted-foreground">€{r.media.toFixed(2)}</p>
          </div>

          <div className={`text-right shrink-0 ${COL_PENULTIMO}`}>
            <p className="text-xs tabular-nums text-muted-foreground">€{r.penultimo.toFixed(2)}</p>
          </div>

          <div className={`text-right shrink-0 ${COL_ULTIMO}`}>
            <p className="text-xs font-bold tabular-nums text-foreground">€{r.ultimo.toFixed(2)}</p>
            {/* Percentuale neutra dal 17/09/2026. Prima era rossa sui rialzi e
                verde sui ribassi: nella stessa riga il bordo e il pallino
                dicevano invece l'ENTITA' (`Math.abs` dell'impatto), cosi' un
                ribasso da 200 € — una buona notizia — usciva con bordo rosso
                "critico" e numero verde. Due segnali che si annullavano. Il
                segno resta leggibile nel numero stesso e, dove pesa davvero,
                nell'impatto in euro qui a destra. */}
            <p className="text-lg font-bold leading-tight tabular-nums">
              {fmtPct(r.aumento_perc)}
            </p>
          </div>

          <Sparkline values={spark} />

          {/* Etichetta nell'intestazione, come le tre colonne di prezzo. Questo
              e' l'unico valore della riga che resta colorato: il colore segue il
              SEGNO (rosso = ti costa di piu'), che e' l'unica delle tre
              semantiche di rosso della vecchia riga a dire se la notizia e'
              buona o cattiva. */}
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
                  onApriFattura={(p) => onApriFattura(r, p)}
                />
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
});

type KpiTone = "positivo" | "negativo";

const KPI_TONE: Record<KpiTone, { border: string; hover: string; value: string }> = {
  positivo: { border: "border-positivo/40", hover: "hover:border-positivo/70", value: "text-positivo" },
  negativo: { border: "border-negativo/40", hover: "hover:border-negativo/70", value: "text-negativo" },
};

function KpiCard({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone: KpiTone }) {
  const t = KPI_TONE[tone];
  return (
    <div className={`rounded-xl border ${t.border} ${t.hover} bg-card px-4 py-3 flex flex-col gap-1 transition-colors`}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-none">{label}</span>
      <span className={`text-2xl font-bold tracking-tight leading-tight ${t.value}`}>{value}</span>
      {sub && <span className="text-[11px] text-muted-foreground leading-tight truncate" title={sub}>{sub}</span>}
    </div>
  );
}

export function VariazioniTab({ initialSoglia }: { initialSoglia: number }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null); // null = tutto l'anno
  const [modo, setModo] = useState<ModoPeriodo>("anno");
  const [customDa, setCustomDa] = useState("");
  const [customA, setCustomA] = useState("");
  const [soglia, setSoglia] = useState(initialSoglia);
  const [sogliaInput, setSogliaInput] = useState(String(initialSoglia));
  const [data, setData] = useState<VariazioniResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");
  const [preferiti, setPreferiti] = useState<Set<string>>(new Set());
  const [soloPreferiti, setSoloPreferiti] = useState(false);
  const [currentRange, setCurrentRange] = useState<{ data_da: string; data_a: string }>(
    isoDateRange(ANNO_CORRENTE, null),
  );
  // Anteprima fattura aperta da una riga della lista acquisti.
  const [anteprima, setAnteprima] = useState<{ punto: StoricoPrezzoPoint; prodotto: string } | null>(null);
  const [page, setPage] = useState(1);
  const apriFattura = useCallback(
    (r: VariazionePrezzo, p: StoricoPrezzoPoint) => setAnteprima({ punto: p, prodotto: r.prodotto }),
    [],
  );

  // Carica per range esplicito: cosi' lo stesso fetch serve anno, mese e custom.
  const loadRange = useCallback(async (range: { data_da: string; data_a: string }, sogliaArg: number) => {
    if (!range.data_da || !range.data_a) return;
    setLoading(true);
    setExpandedKey(null);
    setStorico(null);
    setFiltroCategoria("");
    setFiltroFornitore("");
    setCurrentRange(range);
    try {
      const qs = new URLSearchParams({ ...range, soglia: String(sogliaArg) });
      const res = await fetch(`/api/prezzi/variazioni?${qs}`);
      if (!res.ok) throw new Error();
      const json: VariazioniResponse = await res.json();
      setData(json);
      // Set preferiti iniziale dal campo `preferito` della response: cosi' la
      // stella riflette lo stato salvato e gli aggiornamenti ottimistici partono
      // da una base corretta.
      setPreferiti(
        new Set(
          (json.variazioni ?? [])
            .filter((v) => v.preferito)
            .map((v) => prefKey(v.prodotto, v.fornitore)),
        ),
      );
    } catch {
      toast.error("Errore nel caricamento variazioni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRange(isoDateRange(ANNO_CORRENTE, null), initialSoglia);
  }, [loadRange, initialSoglia]);

  // Torna a pagina 1 quando cambia il set filtrato: restare su una pagina che
  // non esiste più mostrerebbe una lista vuota anche con risultati disponibili.
  useEffect(() => {
    setPage(1);
  }, [search, filtroCategoria, filtroFornitore, soloPreferiti, data]);

  // Applica un preset di periodo aggiornando stato + ricaricando.
  function applyAnno(y: number) {
    setAnno(y);
    setModo("anno");
    setMese(null);
    loadRange(isoDateRange(y, null), soglia);
  }
  function applyMese(m: number) {
    setMese(m);
    setModo("mese");
    loadRange(isoDateRange(anno, m), soglia);
  }
  function applyCustom(da: string, a: string) {
    setCustomDa(da);
    setCustomA(a);
    if (da && a) loadRange({ data_da: da, data_a: a }, soglia);
  }

  // Range attivo in base al modo (per ricaricare dopo il salvataggio soglia).
  function rangeAttivo(): { data_da: string; data_a: string } {
    if (modo === "custom" && customDa && customA) return { data_da: customDa, data_a: customA };
    if (modo === "mese") return isoDateRange(anno, mese);
    return isoDateRange(anno, null);
  }

  // Filtro di SOLA VISUALIZZAZIONE: muove la soglia per vedere cosa supererebbe
  // in questa pagina, senza salvare nulla. La soglia che fa scattare gli AVVISI si
  // imposta nel configuratore assistente (Home) ed e' quella di partenza qui.
  function applicaFiltroSoglia() {
    const val = parseDecimaleIt(sogliaInput) || 5;
    setSoglia(val);
    loadRange(rangeAttivo(), val);
  }

  const toggleCard = useCallback(async (r: VariazionePrezzo) => {
    const key = `${r.prodotto}|${r.fornitore}`;
    if (expandedKey === key) {
      setExpandedKey(null);
      return;
    }
    setExpandedKey(key);
    setStorico(null);
    setStoricoLoading(true);
    try {
      const qs = new URLSearchParams({
        prodotto: r.prodotto,
        fornitore: r.fornitore,
        data_da: currentRange.data_da,
        data_a: currentRange.data_a,
      });
      const res = await fetch(`/api/prezzi/storico-prodotto?${qs}`);
      if (!res.ok) throw new Error();
      setStorico(await res.json());
    } catch {
      toast.error("Errore nel caricamento storico");
    } finally {
      setStoricoLoading(false);
    }
  }, [expandedKey, currentRange]);

  // Stella ottimistica: aggiorna subito il Set locale, poi persiste. Su errore
  // fa rollback e mostra un toast — la stella non resta in uno stato falso.
  const toggleStar = useCallback(async (r: VariazionePrezzo) => {
    const key = prefKey(r.prodotto, r.fornitore);
    const eraPreferito = preferiti.has(key);
    setPreferiti((prev) => {
      const next = new Set(prev);
      if (eraPreferito) next.delete(key);
      else next.add(key);
      return next;
    });
    try {
      let res: Response;
      if (eraPreferito) {
        const qs = new URLSearchParams({ prodotto: r.prodotto, fornitore: r.fornitore });
        res = await fetch(`/api/prezzi/preferiti?${qs}`, { method: "DELETE" });
      } else {
        res = await fetch("/api/prezzi/preferiti", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prodotto: r.prodotto, fornitore: r.fornitore }),
        });
      }
      if (!res.ok) throw new Error();
    } catch {
      setPreferiti((prev) => {
        const next = new Set(prev);
        if (eraPreferito) next.add(key);
        else next.delete(key);
        return next;
      });
      toast.error("Non sono riuscito ad aggiornare i preferiti");
    }
  }, [preferiti]);

  const variazioni = useMemo(() => data?.variazioni ?? [], [data]);

  const sorted = useMemo(
    () => [...variazioni].sort((a, b) => Math.abs(b.impatto_stimato) - Math.abs(a.impatto_stimato)),
    [variazioni],
  );

  // valori unici per i select categoria/fornitore
  const categorieDisp = useMemo(
    () => Array.from(new Set(sorted.map((r) => r.categoria).filter(Boolean))).sort(),
    [sorted],
  );
  const fornitoriDisp = useMemo(
    () => Array.from(new Set(sorted.map((r) => r.fornitore).filter(Boolean))).sort(),
    [sorted],
  );

  const filtered = useMemo(() => sorted.filter((r) => {
    const matchSearch =
      !search ||
      r.prodotto.toLowerCase().includes(search.toLowerCase()) ||
      r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchCat = !filtroCategoria || r.categoria === filtroCategoria;
    const matchForn = !filtroFornitore || r.fornitore === filtroFornitore;
    const matchPref = !soloPreferiti || preferiti.has(prefKey(r.prodotto, r.fornitore));
    return matchSearch && matchCat && matchForn && matchPref;
  }), [sorted, search, filtroCategoria, filtroFornitore, soloPreferiti, preferiti]);

  const nPreferiti = preferiti.size;

  // KPI calcolati sul filtered
  const nCritici = useMemo(() => filtered.filter((r) => gravita(r) === "critico").length, [filtered]);
  const impattoFiltrato = useMemo(() => filtered.reduce((acc, r) => acc + r.impatto_stimato, 0), [filtered]);
  const scostamentoFiltrato = useMemo(
    () => (filtered.length > 0 ? filtered.reduce((acc, r) => acc + r.aumento_perc, 0) / filtered.length : 0),
    [filtered],
  );

  // KPI di sintesi mostrati in cima al tab (specifici di "Variazioni Prezzo")
  const rincari = useMemo(() => filtered.filter((r) => r.aumento_perc > 0), [filtered]);
  const risparmi = useMemo(() => filtered.filter((r) => r.aumento_perc < 0), [filtered]);
  const rincaroMedio = rincari.length > 0 ? rincari.reduce((a, r) => a + r.aumento_perc, 0) / rincari.length : 0;
  const risparmioMedio = risparmi.length > 0 ? risparmi.reduce((a, r) => a + r.aumento_perc, 0) / risparmi.length : 0;

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const visible = useMemo(
    () => filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filtered, safePage],
  );

  const chipBase =
    "px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1.5 disabled:opacity-60";
  const chipActive = "bg-primary text-primary-foreground border-primary";
  const chipIdle = "bg-background border-input hover:bg-muted";

  return (
    <div className="space-y-4">
      {/* ── Filtro periodo (stile Analisi Fatture) ── */}
      <div className="space-y-2">
        <div className={`flex flex-wrap items-center gap-1.5 ${loading ? "opacity-70" : ""}`}>
          <select
            value={anno}
            disabled={loading}
            onChange={(e) => applyAnno(Number(e.target.value))}
            className="h-8 rounded-full border border-input bg-background px-3 text-xs font-medium"
          >
            {Array.from({ length: 5 }, (_, i) => ANNO_CORRENTE - i).map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <button
            disabled={loading}
            onClick={() => applyAnno(anno)}
            className={`${chipBase} ${modo === "anno" ? chipActive : chipIdle}`}
          >
            Anno in corso
          </button>
          <button
            disabled={loading}
            onClick={() => { setModo("mese"); if (mese !== null) loadRange(isoDateRange(anno, mese), soglia); }}
            className={`${chipBase} ${modo === "mese" ? chipActive : chipIdle}`}
          >
            <Calendar className="size-3" />
            Seleziona mese
          </button>
          <button
            disabled={loading}
            onClick={() => setModo("custom")}
            className={`${chipBase} ${modo === "custom" ? chipActive : chipIdle}`}
          >
            <Settings2 className="size-3" />
            Personalizzato
          </button>
          {currentRange.data_da && currentRange.data_a && (
            <span className="ml-2 text-xs font-medium text-primary-text">
              {fmtRangeIt(currentRange.data_da, currentRange.data_a)}
            </span>
          )}
          <div className="ml-auto flex items-center gap-1">
            <InfoPopover title="Come leggere le Variazioni prezzo" ariaLabel="Come leggere le Variazioni prezzo" align="end">
              <p className="text-muted-foreground">
                Come sono cambiati i prezzi d&apos;acquisto dei tuoi prodotti nel periodo, confrontando primo e ultimo prezzo nelle fatture.
              </p>
              <div className="space-y-1.5 text-muted-foreground">
                <p><strong className="text-foreground">Media</strong> = il prezzo medio del prodotto nel periodo.</p>
                <p><TriangleAlert className="inline size-3.5 text-incerto" /> = prezzo <strong className="text-foreground">aumentato</strong> oltre la soglia che hai impostato · <CheckCircle2 className="inline size-3.5 text-positivo" /> = stabile o in calo.</p>
                <p>Clicca un prodotto per vedere lo <strong className="text-foreground">storico</strong> nel tempo e la fattura di origine.</p>
              </div>
              <div className="border-t border-border pt-2 space-y-1.5 text-muted-foreground">
                <p className="font-medium text-foreground">Impatto/mese</p>
                <p>Quanto ti costa davvero il rincaro ogni mese, non solo in %:</p>
                <p className="text-foreground text-xs bg-muted/50 rounded px-2 py-1">aumento di prezzo × quantità abituale × acquisti al mese</p>
                <p>Così un piccolo rincaro su ciò che ordini spesso può pesare più di un grosso aumento su qualcosa di raro. La lista parte dall&apos;impatto più alto.</p>
              </div>
              <div className="border-t border-border pt-2 text-muted-foreground">
                <p>Dati dalle tue fatture reali: servono almeno due acquisti dello stesso prodotto.</p>
              </div>
            </InfoPopover>
            <button
              onClick={() => loadRange(rangeAttivo(), soglia)}
              disabled={loading}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium transition-colors hover:bg-muted disabled:opacity-50"
            >
              <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
              Aggiorna
            </button>
          </div>
        </div>

        {modo === "mese" && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Mese:</span>
            <select
              value={mese ?? ""}
              onChange={(e) => applyMese(Number(e.target.value))}
              className="h-7 rounded-md border border-input bg-background px-2 text-xs"
            >
              <option value="" disabled>Seleziona un mese</option>
              {MESI_LUNGHI.map((label, i) => (
                <option key={i + 1} value={i + 1}>{label} {anno}</option>
              ))}
            </select>
          </div>
        )}

        {modo === "custom" && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dal</span>
            <Input
              type="date"
              value={customDa}
              onChange={(e) => applyCustom(e.target.value, customA)}
              className="h-7 w-36 text-xs"
            />
            <span className="text-xs text-muted-foreground">al</span>
            <Input
              type="date"
              value={customA}
              onChange={(e) => applyCustom(customDa, e.target.value)}
              className="h-7 w-36 text-xs"
            />
          </div>
        )}
      </div>

      {/* ── Soglia di visualizzazione (NON imposta gli avvisi) ── */}
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm text-muted-foreground">Mostra variazioni da</label>
        <input
          type="number"
          min="0"
          max="50"
          step="0.5"
          value={sogliaInput}
          onChange={(e) => setSogliaInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") applicaFiltroSoglia(); }}
          className="w-16 rounded-md border border-border px-2 py-1.5 text-sm bg-background text-right"
        />
        <span className="text-sm text-muted-foreground">% in su</span>
        <button
          onClick={applicaFiltroSoglia}
          disabled={loading}
          className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
        >
          <Search className="size-3" />
          Applica
        </button>
        <span className="text-xs text-muted-foreground basis-full sm:basis-auto">
          Filtro solo per questa pagina. La soglia degli avvisi si imposta nell&apos;assistente, in Home.
        </span>
      </div>

      {/* ── KPI di sintesi (specifici del tab Variazioni) ── */}
      {data && variazioni.length > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <KpiCard
            label="Rincari medi"
            value={rincari.length > 0 ? fmtPct(rincaroMedio) : "—"}
            sub={`${rincari.length} prodott${rincari.length === 1 ? "o" : "i"} in aumento`}
            tone="negativo"
          />
          <KpiCard
            label="Risparmi medi"
            value={risparmi.length > 0 ? fmtPct(risparmioMedio) : "—"}
            sub={`${risparmi.length} prodott${risparmi.length === 1 ? "o" : "i"} in calo`}
            tone="positivo"
          />
          <KpiCard
            label="Scostamento medio"
            value={filtered.length > 0 ? fmtPct(scostamentoFiltrato) : "—"}
            sub={`su ${filtered.length} variazion${filtered.length === 1 ? "e" : "i"}`}
            tone={scostamentoFiltrato < 0 ? "positivo" : "negativo"}
          />
          <KpiCard
            label="Impatto stimato/mese"
            value={impattoFiltrato !== 0 ? fmtEuro(impattoFiltrato, true) : "—"}
            /* Come gli altri KPI del tab, e' calcolato sul filtrato: senza dirlo,
               un impatto ristretto a un fornitore si leggeva come totale. Stessa
               convenzione di sconti-tab/nc-tab ("filtrati da N"). */
            sub={
              filtered.length !== variazioni.length
                ? `su ${filtered.length} di ${variazioni.length} variazioni`
                : "effetto sui costi mensili"
            }
            tone={impattoFiltrato < 0 ? "positivo" : "negativo"}
          />
        </div>
      )}

      {/* Filtri di secondo livello — visibili solo quando ci sono dati */}
      {variazioni.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          <div className="inline-flex rounded-full border border-border p-0.5 bg-background">
            <button
              onClick={() => setSoloPreferiti(false)}
              className={`px-3 py-1 text-xs font-medium rounded-full transition-colors ${!soloPreferiti ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              Tutti
            </button>
            <button
              onClick={() => setSoloPreferiti(true)}
              className={`inline-flex items-center gap-1 px-3 py-1 text-xs font-medium rounded-full transition-colors ${soloPreferiti ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              <Star className={`size-3 ${soloPreferiti ? "fill-current" : "fill-incerto text-incerto"}`} />
              Preferiti{nPreferiti > 0 ? ` (${nPreferiti})` : ""}
            </button>
          </div>
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cerca prodotto…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-md border border-border pl-9 pr-3 py-1.5 text-sm bg-background w-52"
            />
          </div>
          <select
            value={filtroCategoria}
            onChange={(e) => setFiltroCategoria(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutte le categorie</option>
            {categorieDisp.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={filtroFornitore}
            onChange={(e) => setFiltroFornitore(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutti i fornitori</option>
            {fornitoriDisp.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          {(search || filtroCategoria || filtroFornitore) && (
            <button
              onClick={() => { setSearch(""); setFiltroCategoria(""); setFiltroFornitore(""); }}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Azzera filtri
            </button>
          )}
        </div>
      )}

      {/* N. variazioni + legenda gravità — appena sopra la lista */}
      {data && variazioni.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <TriangleAlert className="size-4 text-negativo shrink-0" />
          <p className="text-sm font-semibold">
            {filtered.length} variazioni
            {filtered.length !== variazioni.length && (
              <span className="text-muted-foreground font-normal"> (filtrate da {variazioni.length})</span>
            )}
            {nCritici > 0 && <span className="font-medium text-foreground"> · {nCritici} critiche</span>}
          </p>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-foreground shrink-0" />Critico</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-muted-foreground shrink-0" />Alto</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-muted-foreground/50 shrink-0" />Medio</span>
          </div>
        </div>
      )}

      {/* Stato vuoto. "Stabili" e' una RASSICURAZIONE, e vale solo se le fatture
          ci sono: fino al 17/09/2026 usciva anche su un anno senza una sola
          fattura caricata, dove l'app non sa nulla dei prezzi.
          `fatture_nel_periodo` e' opzionale (le response in cache prima di quel
          deploy non ce l'hanno): `undefined` vuol dire "non lo so" e tiene il
          messaggio neutro, mai la rassicurazione. */}
      {data && variazioni.length === 0 && (
        data.fatture_nel_periodo === 0 ? (
          <div className="rounded-lg border border-border bg-card py-10 text-center">
            <Calendar className="size-8 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm font-medium">Nessuna fattura nel periodo</p>
            <p className="text-xs text-muted-foreground mt-1">
              Senza fatture non è possibile confrontare i prezzi. Caricale o scegli un altro periodo.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-card py-10 text-center">
            <CheckCircle2 className="size-8 text-positivo mx-auto mb-2" />
            <p className="text-sm font-medium">Nessuna variazione sopra il {soglia}%</p>
            {/* La rassicurazione solo con fatture CONTATE (> 0). `null`/assente
                = "non lo so" (response in cache da prima del 17/09/2026): il
                messaggio resta al fatto nudo, senza affermare nulla sui prezzi. */}
            {(data.fatture_nel_periodo ?? 0) > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                I prezzi dei tuoi fornitori sono stabili nel {anno}.
              </p>
            )}
          </div>
        )
      )}

      {/* Loading iniziale */}
      {!data && loading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg border border-border bg-card animate-pulse" />
          ))}
        </div>
      )}

      {/* Lista card */}
      {variazioni.length > 0 && (
        <>
          {/* Intestazione: le tre etichette una volta sola invece che dentro
              ognuna delle righe. La struttura ricalca quella di AlertCard —
              stessi spazi vuoti per stella, pallino, nome, sparkline e chevron —
              perche' le colonne restino incolonnate. Nascosta sotto sm: li' la
              riga va a capo e un'intestazione a colonne non corrisponderebbe
              piu' a nulla. */}
          <div
            aria-hidden
            className="hidden sm:flex items-center gap-3 px-4 pb-1 text-[10px] uppercase tracking-wide text-muted-foreground"
          >
            <span className="size-4 shrink-0" />
            <span className="size-2.5 shrink-0" />
            <span className="min-w-0 flex-1" />
            <span className={`text-right shrink-0 ${COL_MEDIA}`}>Media periodo</span>
            <span className={`text-right shrink-0 ${COL_PENULTIMO}`}>Penultimo</span>
            <span className={`text-right shrink-0 ${COL_ULTIMO}`}>Ultimo</span>
            <span className="w-24 shrink-0" />
            <span className="text-right shrink-0 w-28">Impatto/mese</span>
            <span className="size-4 shrink-0" />
          </div>

          <div className="space-y-2">
            {visible.map((r) => {
              const key = `${r.prodotto}|${r.fornitore}`;
              return (
                <AlertCard
                  key={key}
                  r={r}
                  expanded={expandedKey === key}
                  preferito={preferiti.has(prefKey(r.prodotto, r.fornitore))}
                  storico={expandedKey === key ? storico : null}
                  storicoLoading={expandedKey === key && storicoLoading}
                  onToggle={toggleCard}
                  onToggleStar={toggleStar}
                  onApriFattura={apriFattura}
                />
              );
            })}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Pagina {safePage} di {totalPages} · {filtered.length.toLocaleString("it-IT")} variazioni
              </span>
              <div className="flex gap-2">
                <button
                  className="px-2 py-1 rounded border border-input bg-background hover:bg-muted disabled:opacity-50"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ← Precedente
                </button>
                <button
                  className="px-2 py-1 rounded border border-input bg-background hover:bg-muted disabled:opacity-50"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  Successiva →
                </button>
              </div>
            </div>
          )}
          {filtered.length === 0 && soloPreferiti && nPreferiti === 0 && (
            <div className="rounded-lg border border-dashed border-border py-10 text-center">
              <Star className="size-7 text-incerto mx-auto mb-2" />
              <p className="text-sm font-medium">Non hai ancora prodotti preferiti</p>
              <p className="text-xs text-muted-foreground mt-1">Tocca la ⭐ accanto a un prodotto per seguirne i prezzi qui.</p>
            </div>
          )}
          {filtered.length === 0 && !(soloPreferiti && nPreferiti === 0) && (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun risultato per i filtri selezionati</p>
          )}
        </>
      )}

      <AnteprimaFatturaDialog
        open={anteprima !== null}
        fileOrigine={anteprima?.punto.fattura ?? null}
        numeroDocumento={anteprima?.punto.numero_documento}
        prodotto={anteprima?.prodotto ?? ""}
        onClose={() => setAnteprima(null)}
      />
    </div>
  );
}
