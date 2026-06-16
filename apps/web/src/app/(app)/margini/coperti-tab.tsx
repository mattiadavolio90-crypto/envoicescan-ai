"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Info, Users, Upload, BarChart3, TrendingUp, TrendingDown,
  Trophy, CalendarDays, Receipt, X as XIcon, Sprout, Table2,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell as RCell,
  LineChart, Line,
} from "recharts";
import { toast } from "sonner";
import { formatEuro, formatEuroCompact } from "./periodi";
import { CaricaRicaviDialog } from "./carica-ricavi-dialog";
import { InfoPopover } from "@/components/ui/info-popover";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import type {
  CopertiAnalisiResponse, CopertiMese, CopertiGiorno, CopertiCategorieResponse,
} from "@/lib/ricavi";

const DOW_LABELS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const ANNO_MESE_CORRENTE = (() => {
  const d = new Date();
  return { anno: d.getFullYear(), mese: d.getMonth() + 1 };
})();

function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("it-IT").format(Math.round(v));
}

type Props = { dataDa: string; dataA: string };

export function CopertiTab({ dataDa, dataA }: Props) {
  const [data, setData] = useState<CopertiAnalisiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [caricaOpen, setCaricaOpen] = useState(false);
  const [dettaglioOpen, setDettaglioOpen] = useState(false);
  const [vista, setVista] = useState<"totale" | "media">("totale");

  // Request-id: solo l'ultima fetch scrive lo stato. Evita che una risposta
  // lenta di un periodo vecchio sovrascriva quella nuova (race su cambio filtro).
  const reqIdRef = useRef(0);
  const load = useCallback(async () => {
    const myReq = ++reqIdRef.current;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/ricavi/coperti-analisi?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error();
      const json = await res.json();
      if (myReq === reqIdRef.current) setData(json);
    } catch {
      if (myReq === reqIdRef.current) toast.error("Errore nel caricamento coperti");
    } finally {
      if (myReq === reqIdRef.current) setLoading(false);
    }
  }, [dataDa, dataA]);

  useEffect(() => { load(); }, [load]);

  const mesiVisibili = useMemo(
    () => (data?.mesi ?? []).filter((m) => (m.coperti ?? 0) > 0 || m.ricavi_netto > 0),
    [data],
  );

  const numMesiAttivi = useMemo(
    () => mesiVisibili.filter((m) => (m.coperti ?? 0) > 0).length,
    [mesiVisibili],
  );

  if (loading && !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        Caricamento dati coperti…
      </div>
    );
  }

  const hasCoperti = (data?.totale_coperti ?? 0) > 0;

  if (!data || !hasCoperti) {
    return (
      <>
        <div className="rounded-lg border border-border bg-card p-8 text-center space-y-3">
          <Users className="size-8 mx-auto text-muted-foreground/40" />
          <p className="text-sm font-medium">Nessun dato coperti nel periodo selezionato</p>
          <p className="text-xs text-muted-foreground max-w-md mx-auto">
            I coperti arrivano dal file del gestionale (colonna “Coperti ristorante”) o
            puoi inserirli a mano da <strong>Carica dati</strong>.
          </p>
          <button
            onClick={() => setCaricaOpen(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <Upload className="size-3" /> Carica dati
          </button>
        </div>
        <CaricaRicaviDialog
          open={caricaOpen} onOpenChange={setCaricaOpen}
          dataDa={dataDa} dataA={dataA}
          onImported={() => { setCaricaOpen(false); load(); }}
        />
      </>
    );
  }

  const isMedia = vista === "media";
  const k = data.kpi;

  return (
    <div className="space-y-4">
      {/* Toolbar — stesso layout di Marginalità */}
      <div className="flex items-center gap-2 flex-wrap">
        <InfoPopover title="Come leggere i coperti">
          <p className="text-muted-foreground">
            Il <strong className="text-foreground">coperto</strong> è una persona servita. Il totale del
            giorno somma tutti i documenti emessi (fatture, scontrini, proforma).
          </p>
          <div className="space-y-1.5 text-muted-foreground">
            <p><strong className="text-foreground">Scontrino medio</strong>: quanto spende in media ogni
              persona. Lo mostriamo sia netto (coerente con i Margini) sia lordo (come sullo scontrino fisico).</p>
            <p><strong className="text-foreground">Media per giorno settimana</strong>: in quali giorni il
              locale si riempie di più.</p>
            <p><strong className="text-foreground">Dettaglio giornaliero</strong>: l’andamento giorno per
              giorno, con i giorni sopra/sotto la media evidenziati.</p>
          </div>
        </InfoPopover>
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="size-3" />
          La tabella mostra i totali mensili. Per il giorno-per-giorno usa “Dettaglio giornaliero”.
        </p>

        {/* Toggle Totale / Media */}
        <div className="ml-auto inline-flex items-center rounded-md border border-input p-0.5 text-xs font-semibold">
          <button
            onClick={() => setVista("totale")}
            className={`px-2.5 py-1 rounded transition-colors ${vista === "totale" ? "bg-sky-500 text-white" : "text-muted-foreground hover:bg-muted"}`}
            title="Somma del periodo"
          >Totale</button>
          <button
            onClick={() => setVista("media")}
            className={`px-2.5 py-1 rounded transition-colors ${vista === "media" ? "bg-sky-500 text-white" : "text-muted-foreground hover:bg-muted"}`}
            title={`Media sui ${numMesiAttivi} mesi con coperti`}
          >Media</button>
        </div>
        <button
          onClick={() => setDettaglioOpen(true)}
          disabled={!data.ha_dati_giornalieri}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-input hover:bg-muted transition-colors disabled:opacity-40"
          title={data.ha_dati_giornalieri ? "Andamento giorno per giorno" : "Nessun dato giornaliero nel periodo"}
        >
          <BarChart3 className="size-3" /> Dettaglio giornaliero
        </button>
        <button
          onClick={() => setCaricaOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Upload className="size-3" /> Carica dati
        </button>
      </div>

      <CaricaRicaviDialog
        open={caricaOpen} onOpenChange={setCaricaOpen}
        dataDa={dataDa} dataA={dataA}
        onImported={() => { setCaricaOpen(false); load(); }}
      />

      {dettaglioOpen && (
        <DettaglioCopertiDialog
          giorni={data.giorni}
          mediaPeriodo={k.coperti_medi_giorno ?? 0}
          onClose={() => setDettaglioOpen(false)}
        />
      )}

      {/* Card KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          icon={<Users className="size-4" />}
          label="Coperti totali"
          value={fmtInt(k.coperti_totali)}
          delta={k.delta_coperti_pct}
          deltaLabel={k.confronto_label}
          accent="sky"
        />
        <KpiCard
          icon={<CalendarDays className="size-4" />}
          label="Media / giorno"
          value={k.coperti_medi_giorno != null ? fmtInt(k.coperti_medi_giorno) : "—"}
          accent="violet"
        />
        <KpiCard
          icon={<Receipt className="size-4" />}
          label="Scontrino medio"
          value={k.scontrino_medio_netto != null ? formatEuro(k.scontrino_medio_netto) : "—"}
          sub={k.scontrino_medio_lordo != null ? `${formatEuro(k.scontrino_medio_lordo)} lordo` : undefined}
          accent="emerald"
        />
        <KpiCard
          icon={<Trophy className="size-4" />}
          label="Giorno più pieno"
          value={k.giorno_top ? `${fmtInt(k.giorno_top.coperti)}` : "—"}
          sub={k.giorno_top ? formatDataBreve(k.giorno_top.data) : undefined}
          accent="amber"
        />
      </div>

      {/* Tabella mensile — desktop */}
      <div className="hidden md:block rounded-lg border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full table-auto text-[15px] border-collapse">
            <colgroup>
              <col className="w-[200px]" />
              {mesiVisibili.map((m) => <col key={`c-${m.anno}-${m.mese}`} className="w-[130px]" />)}
              <col className="w-[150px]" />
            </colgroup>
            <thead className="bg-muted/40">
              <tr className="text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="sticky left-0 z-20 bg-muted/40 text-left px-3 py-2.5 font-semibold border-r border-border">Voce</th>
                {mesiVisibili.map((m) => {
                  const isCur = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
                  return (
                    <th key={`${m.anno}-${m.mese}`}
                      className={`text-right px-3 py-2.5 font-semibold ${isCur ? "text-sky-500 dark:text-sky-400 border-l border-r border-sky-500/50" : "border-r border-border"}`}>
                      {isCur && <span className="mr-1 inline-block size-1.5 rounded-full bg-sky-400 align-middle" />}
                      {m.label}
                    </th>
                  );
                })}
                <th className="sticky right-0 z-20 bg-sky-500/8 text-right px-3 py-2.5 font-bold border-l-2 border-r border-sky-500/50 text-sky-600 dark:text-sky-400">
                  {isMedia ? "Media" : "Totale"}
                </th>
              </tr>
            </thead>
            <tbody>
              <MeseRow label="Coperti" mesi={mesiVisibili}
                value={(m) => fmtInt(m.coperti)}
                total={fmtInt(aggregaCoperti(mesiVisibili, isMedia, numMesiAttivi))}
                metric color="text-sky-600 dark:text-sky-400" />
              <MeseRow label="Ricavi netti" mesi={mesiVisibili}
                value={(m) => m.ricavi_netto > 0 ? formatEuro(m.ricavi_netto) : "—"}
                total={formatEuro(aggregaRicavi(mesiVisibili, isMedia, numMesiAttivi))} />
              <MeseRow label="Scontrino medio (netto)" mesi={mesiVisibili}
                value={(m) => m.scontrino_medio_netto != null ? formatEuro(m.scontrino_medio_netto) : "—"}
                total={k.scontrino_medio_netto != null ? formatEuro(k.scontrino_medio_netto) : "—"}
                metric color="text-emerald-600 dark:text-emerald-400" />
              <MeseRow label="Scontrino medio (lordo)" mesi={mesiVisibili}
                value={(m) => m.scontrino_medio_lordo != null ? formatEuro(m.scontrino_medio_lordo) : "—"}
                total={k.scontrino_medio_lordo != null ? formatEuro(k.scontrino_medio_lordo) : "—"}
                color="text-muted-foreground" />
            </tbody>
          </table>
        </div>
      </div>

      {/* Tabella mensile — mobile (card per mese) */}
      <div className="md:hidden space-y-2">
        {mesiVisibili.map((m) => {
          const isCur = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
          return (
            <div key={`${m.anno}-${m.mese}`} className={`rounded-lg border bg-card p-3 ${isCur ? "border-sky-500/50" : "border-border"}`}>
              <p className="text-sm font-semibold mb-2">{m.label}</p>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <Stat label="Coperti" value={fmtInt(m.coperti)} color="text-sky-600 dark:text-sky-400" />
                <Stat label="Ricavi netti" value={m.ricavi_netto > 0 ? formatEuro(m.ricavi_netto) : "—"} />
                <Stat label="Scontrino netto" value={m.scontrino_medio_netto != null ? formatEuro(m.scontrino_medio_netto) : "—"} color="text-emerald-600 dark:text-emerald-400" />
                <Stat label="Scontrino lordo" value={m.scontrino_medio_lordo != null ? formatEuro(m.scontrino_medio_lordo) : "—"} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Grafici: media per giorno-settimana + trend scontrino medio */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <MediaPerDowChart media={k.media_per_dow} />
        <TrendScontrinoChart mesi={mesiVisibili} />
      </div>

      {/* Efficienza materia prima (analisi spreco per scostamento) */}
      {k.costo_fb_per_coperto != null && (
        <EfficienzaSection kpi={k} mesi={mesiVisibili} dataDa={dataDa} dataA={dataA} />
      )}
    </div>
  );
}

/* ─── Efficienza materia prima ────────────────────────────────────────────── */
function EfficienzaSection({
  kpi, mesi, dataDa, dataA,
}: {
  kpi: CopertiAnalisiResponse["kpi"];
  mesi: CopertiMese[];
  dataDa: string;
  dataA: string;
}) {
  const [categorieOpen, setCategorieOpen] = useState(false);
  const chartData = mesi
    .filter((m) => m.costo_fb_per_coperto != null)
    .map((m) => ({
      label: m.label,
      fbPerCoperto: m.costo_fb_per_coperto,
      scontrino: m.scontrino_medio_netto,
    }));

  const delta = kpi.costo_fb_per_coperto_delta_pct;
  // Trend "buono" = costo per coperto in calo (spreco/efficienza migliora)
  const deltaBuono = delta != null && delta <= 0;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4">
      <div className="flex items-start gap-2">
        <h3 className="text-base font-semibold flex items-center gap-1.5">
          <Sprout className="size-4 text-emerald-500" />
          Efficienza materia prima
        </h3>
        <InfoPopover title="Cos'è e come leggerla">
          <p className="text-muted-foreground">
            Costo della <strong className="text-foreground">materia prima per coperto</strong> (fatture
            F&amp;B ÷ persone servite). Se <strong className="text-foreground">sale mentre lo scontrino
            medio resta fermo</strong>, è un segnale di spreco o porzioni troppo generose.
          </p>
        </InfoPopover>
        <button
          onClick={() => setCategorieOpen(true)}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-input hover:bg-muted transition-colors shrink-0"
        >
          <Table2 className="size-3" />
          Per categoria
        </button>
      </div>

      {categorieOpen && (
        <CopertiCategorieDialog
          dataDa={dataDa}
          dataA={dataA}
          onClose={() => setCategorieOpen(false)}
        />
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-stretch">
        {/* Card sintesi */}
        <div className="flex flex-col justify-center gap-3">
          <div className="rounded-lg border border-border bg-muted/20 p-3">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
              Costo materia prima / coperto
            </p>
            <p className="text-2xl font-bold tabular-nums mt-1 text-emerald-600 dark:text-emerald-400">
              {kpi.costo_fb_per_coperto != null ? formatEuro(kpi.costo_fb_per_coperto) : "—"}
            </p>
            {delta != null && (
              <p className={`text-xs mt-1 flex items-center gap-0.5 ${deltaBuono ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
                {deltaBuono ? <TrendingDown className="size-3" /> : <TrendingUp className="size-3" />}
                {delta >= 0 ? "+" : ""}{delta}% nel periodo
              </p>
            )}
          </div>
          {kpi.efficienza_commento && (
            <p className="text-xs text-muted-foreground leading-relaxed">
              {kpi.efficienza_commento}
            </p>
          )}
        </div>

        {/* Grafico costo/coperto vs scontrino medio */}
        <div className="lg:col-span-2">
          {chartData.length < 2 ? (
            <p className="text-xs text-muted-foreground py-8 text-center">
              Servono almeno due mesi con coperti e fatture per vedere il confronto.
            </p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => formatEuroCompact(v)} />
                <Tooltip
                  formatter={(v: unknown, name: unknown) => [formatEuro(typeof v === "number" ? v : 0), name === "fbPerCoperto" ? "Materia prima/coperto" : "Scontrino medio"]}
                  contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
                  labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
                  itemStyle={{ color: "var(--foreground)" }}
                />
                <Line type="monotone" dataKey="fbPerCoperto" stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} name="fbPerCoperto" />
                <Line type="monotone" dataKey="scontrino" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} name="scontrino" />
              </LineChart>
            </ResponsiveContainer>
          )}
          <div className="flex items-center justify-center gap-4 mt-2 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-orange-500" /> Materia prima/coperto</span>
            <span className="flex items-center gap-1"><span className="inline-block w-3 h-0.5 bg-emerald-500" /> Scontrino medio</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Helpers di aggregazione colonna Totale/Media ────────────────────────── */
function aggregaCoperti(mesi: CopertiMese[], isMedia: boolean, nMesi: number): number | null {
  const conDati = mesi.filter((m) => m.coperti != null);
  if (conDati.length === 0) return null;
  const tot = conDati.reduce((s, m) => s + (m.coperti ?? 0), 0);
  return isMedia ? tot / Math.max(1, nMesi) : tot;
}
function aggregaRicavi(mesi: CopertiMese[], isMedia: boolean, nMesi: number): number {
  const tot = mesi.reduce((s, m) => s + m.ricavi_netto, 0);
  return isMedia ? tot / Math.max(1, nMesi) : tot;
}

/* ─── Riga tabella mensile ────────────────────────────────────────────────── */
function MeseRow({
  label, mesi, value, total, metric, color,
}: {
  label: string;
  mesi: CopertiMese[];
  value: (m: CopertiMese) => string;
  total: string;
  metric?: boolean;
  color?: string;
}) {
  return (
    <tr className={`border-t border-border ${metric ? "font-semibold bg-muted/[0.04]" : ""}`}>
      <td className={`sticky left-0 z-10 bg-card px-3 py-2 border-r border-border whitespace-nowrap ${color ?? ""}`}>
        {label}
      </td>
      {mesi.map((m) => {
        const isCur = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
        return (
          <td key={`${m.anno}-${m.mese}`}
            className={`text-right px-3 py-2 tabular-nums ${isCur ? "border-l border-r border-sky-500/50" : "border-r border-border"} ${color ?? ""}`}>
            {value(m)}
          </td>
        );
      })}
      <td className={`sticky right-0 z-10 bg-sky-500/8 text-right px-3 py-2 tabular-nums font-bold border-l-2 border-r border-sky-500/50 ${color ?? "text-sky-600 dark:text-sky-400"}`}>
        {total}
      </td>
    </tr>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className={`font-semibold tabular-nums ${color ?? ""}`}>{value}</p>
    </div>
  );
}

/* ─── Card KPI ────────────────────────────────────────────────────────────── */
const ACCENTS: Record<string, string> = {
  sky: "text-sky-600 dark:text-sky-400",
  violet: "text-violet-600 dark:text-violet-400",
  emerald: "text-emerald-600 dark:text-emerald-400",
  amber: "text-amber-600 dark:text-amber-400",
};

function KpiCard({
  icon, label, value, sub, delta, deltaLabel, accent = "sky",
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  delta?: number | null;
  deltaLabel?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <div className={`flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-medium ${ACCENTS[accent]}`}>
        {icon}{label}
      </div>
      <p className="text-xl font-bold tabular-nums mt-1.5">{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
      {delta != null && (
        <p className={`text-[11px] mt-0.5 flex items-center gap-0.5 ${delta >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
          {delta >= 0 ? <TrendingUp className="size-3" /> : <TrendingDown className="size-3" />}
          {delta >= 0 ? "+" : ""}{delta}% {deltaLabel}
        </p>
      )}
    </div>
  );
}

/* ─── Grafico media per giorno settimana ──────────────────────────────────── */
function MediaPerDowChart({ media }: { media: (number | null)[] }) {
  const chartData = DOW_LABELS.map((label, i) => ({ label, media: media[i] ?? 0, has: media[i] != null }));
  const maxV = Math.max(1, ...chartData.map((d) => d.media));
  const hasAny = chartData.some((d) => d.has);

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-3">
        <CalendarDays className="size-4 text-violet-500" />
        Media coperti per giorno settimana
      </h3>
      {!hasAny ? (
        <p className="text-xs text-muted-foreground py-8 text-center">Nessun dato giornaliero.</p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={32} allowDecimals={false} />
            <Tooltip
              cursor={{ fill: "var(--muted)", opacity: 0.4 }}
              formatter={(v: unknown) => [fmtInt(typeof v === "number" ? v : 0), "Media coperti"]}
              contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
              labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
              itemStyle={{ color: "var(--foreground)" }}
            />
            <Bar dataKey="media" radius={[3, 3, 0, 0]} maxBarSize={40}>
              {chartData.map((d, i) => (
                <RCell key={i} fill={d.media >= maxV * 0.85 ? "#8b5cf6" : "#a78bfa"} opacity={d.has ? 0.9 : 0.2} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/* ─── Grafico trend scontrino medio nel tempo ─────────────────────────────── */
function TrendScontrinoChart({ mesi }: { mesi: CopertiMese[] }) {
  const chartData = mesi
    .filter((m) => m.scontrino_medio_netto != null)
    .map((m) => ({ label: m.label, netto: m.scontrino_medio_netto, lordo: m.scontrino_medio_lordo }));

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold flex items-center gap-1.5 mb-3">
        <Receipt className="size-4 text-emerald-500" />
        Trend scontrino medio
      </h3>
      {chartData.length < 2 ? (
        <p className="text-xs text-muted-foreground py-8 text-center">
          Servono almeno due mesi con coperti per vedere il trend.
        </p>
      ) : (
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => formatEuroCompact(v)} />
            <Tooltip
              formatter={(v: unknown, name: unknown) => [formatEuro(typeof v === "number" ? v : 0), name === "netto" ? "Netto" : "Lordo"]}
              contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
              labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
              itemStyle={{ color: "var(--foreground)" }}
            />
            <Line type="monotone" dataKey="netto" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
            <Line type="monotone" dataKey="lordo" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 3" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

/* ─── Dialog: costo materia prima/coperto per categoria ───────────────────── */
function CopertiCategorieDialog({
  dataDa, dataA, onClose,
}: {
  dataDa: string;
  dataA: string;
  onClose: () => void;
}) {
  const [data, setData] = useState<CopertiCategorieResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetch(`/api/ricavi/coperti-categorie?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setData(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [dataDa, dataA]);

  const fmtEuro2 = (v: number | null) =>
    v == null ? "—" : `${v.toFixed(2).replace(".", ",")} €`;

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(900px,94vw)] w-full max-h-[88vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Sprout className="size-4 text-emerald-500" />
              Costo materia prima per coperto · per categoria
              <InfoPopover title="Come si calcola">
                <p className="text-muted-foreground">
                  Per ogni categoria: <strong className="text-foreground">spesa in fatture F&amp;B del mese
                  ÷ coperti del mese</strong>. La colonna <strong className="text-foreground">Media</strong> è
                  pesata (spesa totale ÷ coperti totali del periodo).
                </p>
                <p className="text-muted-foreground">
                  Sono escluse le spese generali e lo SHOP (non sono materia prima). I mesi senza
                  fatture caricate mostrano “—”.
                </p>
              </InfoPopover>
            </DialogTitle>
            <button onClick={onClose} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors shrink-0">
              <XIcon className="size-4" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Quanto pesa ogni categoria di materia prima su un coperto, mese per mese. Ordinate dalla più cara.
          </p>
        </DialogHeader>

        <div className="flex-1 overflow-auto px-6 py-5">
          {loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Caricamento…</p>
          ) : !data || data.righe.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Nessun dato: servono coperti e fatture F&amp;B classificate nel periodo.
            </p>
          ) : (
            <table className="w-full text-sm border-collapse">
              <thead className="bg-muted/40">
                <tr className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="sticky left-0 z-10 bg-muted/40 text-left px-3 py-2.5 font-semibold border-r border-border">
                    Categoria
                  </th>
                  {data.mesi_label.map((l) => (
                    <th key={l} className="text-right px-3 py-2.5 font-semibold border-r border-border whitespace-nowrap">{l}</th>
                  ))}
                  <th className="sticky right-0 z-10 bg-emerald-500/8 text-right px-3 py-2.5 font-bold border-l-2 border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
                    Media
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.righe.map((r) => (
                  <tr key={r.categoria} className="border-t border-border">
                    <td className="sticky left-0 z-10 bg-card px-3 py-2 border-r border-border whitespace-nowrap font-medium">
                      {r.categoria}
                    </td>
                    {r.per_mese.map((m) => (
                      <td key={`${m.anno}-${m.mese}`} className="text-right px-3 py-2 tabular-nums border-r border-border text-muted-foreground">
                        {fmtEuro2(m.valore)}
                      </td>
                    ))}
                    <td className="sticky right-0 z-10 bg-emerald-500/8 text-right px-3 py-2 tabular-nums font-bold border-l-2 border-emerald-500/50 text-emerald-700 dark:text-emerald-400">
                      {fmtEuro2(r.media)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="px-6 pb-5 pt-3 border-t border-border flex justify-end shrink-0">
          <button onClick={onClose} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-border hover:bg-muted transition-colors">
            Chiudi
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Dialog dettaglio giornaliero (riempimento relativo) ─────────────────── */
function formatDataBreve(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return `${d.getDate()} ${["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"][d.getMonth()]}`;
}

function DettaglioCopertiDialog({
  giorni, mediaPeriodo, onClose,
}: {
  giorni: CopertiGiorno[];
  mediaPeriodo: number;
  onClose: () => void;
}) {
  const chartData = giorni.map((g) => ({
    data: g.data,
    label: formatDataBreve(g.data),
    coperti: g.coperti,
    sopra: g.coperti >= mediaPeriodo,
  }));

  const top = giorni.reduce<CopertiGiorno | null>((b, g) => (!b || g.coperti > b.coperti ? g : b), null);
  const min = giorni.reduce<CopertiGiorno | null>((w, g) => (!w || g.coperti < w.coperti ? g : w), null);
  const totale = giorni.reduce((s, g) => s + g.coperti, 0);

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(820px,94vw)] w-full p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Users className="size-4 text-primary" /> Coperti giornalieri
            </DialogTitle>
            <button onClick={onClose} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors">
              <XIcon className="size-4" />
            </button>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Verde = sopra la media periodo ({fmtInt(mediaPeriodo)}/giorno) · Rosso = sotto
          </p>
        </DialogHeader>

        <div className="px-6 py-5 space-y-5">
          {chartData.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Nessun dato giornaliero nel periodo.</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={16} />
                  <YAxis tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                    formatter={(v: unknown) => [fmtInt(typeof v === "number" ? v : 0), "Coperti"]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
                    labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
                    itemStyle={{ color: "var(--foreground)" }}
                  />
                  <Bar dataKey="coperti" radius={[3, 3, 0, 0]} maxBarSize={26}>
                    {chartData.map((entry, i) => (
                      <RCell key={i} fill={entry.sopra ? "#10b981" : "#f43f5e"} opacity={0.85} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatBox label="Giorni con dati" value={`${giorni.length}`} />
                <StatBox label="Coperti totali" value={fmtInt(totale)} color="text-sky-600 dark:text-sky-400" />
                <StatBox label="Giorno più pieno" value={top ? fmtInt(top.coperti) : "—"} sub={top ? formatDataBreve(top.data) : undefined} color="text-emerald-600 dark:text-emerald-400" />
                <StatBox label="Giorno più scarico" value={min ? fmtInt(min.coperti) : "—"} sub={min ? formatDataBreve(min.data) : undefined} color="text-rose-600 dark:text-rose-400" />
              </div>
            </>
          )}
        </div>

        <div className="px-6 pb-5 flex justify-end">
          <button onClick={onClose} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-border hover:bg-muted transition-colors">
            Chiudi
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function StatBox({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${color ?? ""}`}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}
