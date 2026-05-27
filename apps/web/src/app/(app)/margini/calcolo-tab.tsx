"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, Lock, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { formatEuro, formatPct } from "./periodi";

type MesePivot = {
  anno: number;
  mese: number;
  label: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  fatturato_netto: number;
  costi_fb_auto: number;
  altri_costi_fb: number;
  costi_fb_totali: number;
  primo_margine: number;
  costi_spese_auto: number;
  altri_costi_spese: number;
  costi_spese_totali: number;
  costo_dipendenti: number;
  costo_personale_extra: number;
  costi_personale: number;
  mol: number;
};

type Commento = {
  kpi_nome: string;
  percentuale: string;
  commento: string;
  emoji: string;
  colore: string;
};

type AnalisiResponse = {
  mesi: MesePivot[];
  totali: MesePivot;
  fatt_medio_mensile: number;
  food_cost_perc: number;
  primo_margine_perc: number;
  spese_gen_perc: number;
  personale_perc: number;
  mol_perc: number;
  num_mesi_attivi: number;
  commenti: Commento[];
};

type EditableField =
  | "altri_costi_fb" | "altri_costi_spese" | "costo_dipendenti" | "costo_personale_extra";

type Section = "ricavi" | "fb" | "spese" | "personale" | "margine";

type RowDef = {
  key: keyof MesePivot;
  label: string;
  type: "input-readonly" | "input-readonly-tooltip" | "input-editable" | "computed";
  field?: EditableField;
  section: Section;
  isMetric?: boolean;
  isMolMargin?: boolean;
  isPrimoMargin?: boolean;
  isFattNetto?: boolean;
};

const ROWS: RowDef[] = [
  { key: "fatturato_iva10",       label: "Ricavi IVA 10%",         type: "input-readonly-tooltip", section: "ricavi" },
  { key: "fatturato_iva22",       label: "Ricavi IVA 22%",         type: "input-readonly-tooltip", section: "ricavi" },
  { key: "altri_ricavi_noiva",    label: "Altri ricavi (no IVA)",  type: "input-readonly-tooltip", section: "ricavi" },
  { key: "fatturato_netto",       label: "= Fatturato Netto",      type: "computed", section: "ricavi", isMetric: true, isFattNetto: true },
  { key: "costi_fb_auto",         label: "Costi F&B (Fatture)",    type: "input-readonly", section: "fb" },
  { key: "altri_costi_fb",        label: "Altri Costi F&B",        type: "input-editable", field: "altri_costi_fb", section: "fb" },
  { key: "costi_fb_totali",       label: "= Costi F&B Totali",     type: "computed", section: "fb", isMetric: true },
  { key: "primo_margine",         label: "= 1° Margine",           type: "computed", section: "margine", isMetric: true, isPrimoMargin: true },
  { key: "costi_spese_auto",      label: "Spese Gen. (Fatture)",   type: "input-readonly", section: "spese" },
  { key: "altri_costi_spese",     label: "Altre Spese Generali",   type: "input-editable", field: "altri_costi_spese", section: "spese" },
  { key: "costo_dipendenti",      label: "Costo Personale Lordo",  type: "input-editable", field: "costo_dipendenti", section: "personale" },
  { key: "costo_personale_extra", label: "Costo Personale Extra",  type: "input-editable", field: "costo_personale_extra", section: "personale" },
  { key: "mol",                   label: "= 2° Margine (MOL)",     type: "computed", section: "margine", isMetric: true, isMolMargin: true },
];

const SECTION_CONFIG: Record<Section, { color: string; bg: string; border: string }> = {
  ricavi: {
    color: "text-sky-700 dark:text-sky-300",
    bg: "bg-sky-500/8",
    border: "border-l-sky-500",
  },
  fb: {
    color: "text-orange-700 dark:text-orange-300",
    bg: "bg-orange-500/8",
    border: "border-l-orange-500",
  },
  spese: {
    color: "text-purple-700 dark:text-purple-300",
    bg: "bg-purple-500/8",
    border: "border-l-purple-500",
  },
  personale: {
    color: "text-pink-700 dark:text-pink-300",
    bg: "bg-pink-500/8",
    border: "border-l-pink-500",
  },
  margine: {
    color: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-l-emerald-500",
  },
};

type Props = {
  dataDa: string;
  dataA: string;
};

export function CalcoloTab({ dataDa, dataA }: Props) {
  const [data, setData] = useState<AnalisiResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/margini/analisi?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error();
      const d: AnalisiResponse = await res.json();
      setData(d);
    } catch {
      toast.error("Errore nel caricamento margini");
    } finally {
      setLoading(false);
    }
  }, [dataDa, dataA]);

  useEffect(() => {
    load();
  }, [load]);

  // Mostra solo mesi con almeno un valore (ricavi o costi)
  const mesiVisibili = useMemo(() => {
    if (!data) return [];
    return data.mesi.filter(
      (m) =>
        m.fatturato_netto > 0 ||
        m.costi_fb_totali > 0 ||
        m.costi_spese_totali > 0 ||
        m.costi_personale > 0,
    );
  }, [data]);

  async function saveCell(anno: number, mese: number, field: EditableField, value: number) {
    try {
      const res = await fetch("/api/margini/cella", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anno, mese, field, value }),
      });
      if (!res.ok) throw new Error();
      toast.success("Salvato");
      // Reload to refresh derived metrics
      load();
    } catch {
      toast.error("Errore nel salvataggio");
    }
  }

  if (loading && !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        Caricamento dati margini...
      </div>
    );
  }

  if (!data || mesiVisibili.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center space-y-2">
        <p className="text-sm font-medium">Nessun dato margini nel periodo selezionato</p>
        <p className="text-xs text-muted-foreground">
          Inserisci ricavi nel tab Ricavi o carica fatture per popolare automaticamente i costi.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-md border border-border hover:bg-muted disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} />
          Aggiorna
        </button>
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="size-3" />
          Modifica le righe in bianco; le altre sono calcolate o ereditate (Tab Ricavi, fatture).
        </p>
      </div>

      {/* Legenda colori */}
      <div className="flex flex-wrap gap-1.5">
        {([
          { label: "Ricavi", section: "ricavi" as Section },
          { label: "Costi F&B", section: "fb" as Section },
          { label: "Spese Generali", section: "spese" as Section },
          { label: "Personale", section: "personale" as Section },
          { label: "Totali & Margini", section: "margine" as Section },
        ]).map((c) => (
          <span
            key={c.label}
            className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${SECTION_CONFIG[c.section].color} border ${SECTION_CONFIG[c.section].border.replace("border-l-", "border-")}/40`}
          >
            {c.label}
          </span>
        ))}
      </div>

      {/* Tabella trasposta */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border-collapse">
            <thead className="bg-muted/40">
              <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="sticky left-0 z-20 bg-muted/40 text-left px-3 py-2 font-semibold border-r border-border min-w-[200px]">
                  Voce
                </th>
                {mesiVisibili.map((m) => (
                  <th
                    key={`${m.anno}-${m.mese}`}
                    className="text-right px-2 py-2 font-semibold border-r border-border min-w-[100px]"
                  >
                    {m.label}
                  </th>
                ))}
                <th className="sticky right-0 z-20 bg-primary/10 text-right px-3 py-2 font-bold border-l-2 border-primary min-w-[110px]">
                  Totale
                </th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, ri) => {
                const cfg = SECTION_CONFIG[row.section];
                const isMetric = row.isMetric;
                return (
                  <tr
                    key={ri}
                    className={`border-t border-border ${isMetric ? cfg.bg : ""} ${isMetric ? "font-semibold" : ""}`}
                  >
                    <td
                      className={`sticky left-0 z-10 px-3 py-1.5 border-r border-border whitespace-nowrap ${
                        isMetric ? `${cfg.bg} ${cfg.color} border-l-4 ${cfg.border} font-bold` : "bg-card"
                      }`}
                    >
                      {row.label}
                    </td>
                    {mesiVisibili.map((m) => (
                      <Cell
                        key={`${m.anno}-${m.mese}`}
                        row={row}
                        mese={m}
                        cfg={cfg}
                        onSave={saveCell}
                      />
                    ))}
                    {/* Total column */}
                    <TotalCell row={row} totali={data.totali} cfg={cfg} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* KPI riassunto periodo */}
      <PeriodoKpiRow data={data} />

      {/* Commenti automatici */}
      {data.commenti.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold flex items-center gap-1.5">
            💬 Analisi automatica
          </h3>
          <div className="space-y-1.5">
            {data.commenti.map((c, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-md border border-border bg-card p-3"
                style={{ borderLeftWidth: 4, borderLeftColor: c.colore }}
              >
                <span className="text-lg font-bold shrink-0" style={{ color: c.colore }}>
                  {c.emoji} {c.percentuale}
                </span>
                <div className="text-sm">
                  <strong>{c.kpi_nome}</strong>
                  <span className="text-muted-foreground"> · {c.commento}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================ */
/* Cell                                                          */
/* ============================================================ */
function Cell({
  row,
  mese,
  cfg,
  onSave,
}: {
  row: RowDef;
  mese: MesePivot;
  cfg: { bg: string; color: string; border: string };
  onSave: (anno: number, mese: number, field: EditableField, value: number) => void;
}) {
  const raw = mese[row.key] as number;
  const isMetric = row.isMetric;
  const isMolMargin = row.isMolMargin;
  const display = raw === 0 ? "—" : formatEuro(raw);

  // Color logic for MOL: positive emerald, negative rose
  const metricCls = isMolMargin
    ? raw > 0
      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 font-bold"
      : raw < 0
      ? "bg-rose-500/10 text-rose-700 dark:text-rose-400 font-bold"
      : "bg-muted/30 font-bold"
    : isMetric
    ? `${cfg.bg} ${cfg.color} font-bold`
    : "";

  if (row.type === "input-editable" && row.field) {
    return (
      <EditableCell
        value={raw}
        onSave={(v) => onSave(mese.anno, mese.mese, row.field!, v)}
      />
    );
  }

  if (row.type === "input-readonly-tooltip") {
    return (
      <td className={`text-right px-2 py-1.5 border-r border-border tabular-nums text-muted-foreground/80 ${metricCls}`}>
        <span title="Modifica da Tab Ricavi" className="inline-flex items-center gap-1 cursor-help">
          {display}
          <Lock className="size-3 opacity-40" />
        </span>
      </td>
    );
  }

  if (row.type === "input-readonly") {
    return (
      <td className={`text-right px-2 py-1.5 border-r border-border tabular-nums text-muted-foreground/80 ${metricCls}`}>
        <span title="Calcolato dalle fatture caricate" className="inline-flex items-center gap-1 cursor-help">
          {display}
          <Lock className="size-3 opacity-40" />
        </span>
      </td>
    );
  }

  // computed
  return (
    <td className={`text-right px-2 py-1.5 border-r border-border tabular-nums ${metricCls}`}>
      {display}
    </td>
  );
}

function EditableCell({
  value,
  onSave,
}: {
  value: number;
  onSave: (v: number) => void;
}) {
  const [local, setLocal] = useState(value > 0 ? String(value) : "");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setLocal(value > 0 ? String(value) : "");
  }, [value]);

  async function commit() {
    const newVal = parseFloat(local.replace(",", ".")) || 0;
    if (Math.abs(newVal - value) < 0.001) return;
    setSaving(true);
    try {
      await onSave(newVal);
      setSaved(true);
      setTimeout(() => setSaved(false), 800);
    } finally {
      setSaving(false);
    }
  }

  return (
    <td className="border-r border-border p-0">
      <input
        type="number"
        step="0.01"
        min="0"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setLocal(value > 0 ? String(value) : "");
            (e.target as HTMLInputElement).blur();
          }
        }}
        placeholder="—"
        className={`w-full h-full px-2 py-1.5 text-right tabular-nums bg-transparent border-0 outline-none transition-colors text-sm ${
          saved
            ? "bg-emerald-500/10"
            : saving
            ? "bg-sky-500/5"
            : "hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset"
        }`}
      />
    </td>
  );
}

function TotalCell({
  row,
  totali,
  cfg,
}: {
  row: RowDef;
  totali: MesePivot;
  cfg: { bg: string; color: string; border: string };
}) {
  const raw = totali[row.key] as number;
  const display = raw === 0 ? "—" : formatEuro(raw);

  const isMolMargin = row.isMolMargin;
  const isMetric = row.isMetric;

  const cls = isMolMargin
    ? raw > 0
      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 font-bold"
      : raw < 0
      ? "bg-rose-500/15 text-rose-700 dark:text-rose-400 font-bold"
      : "bg-primary/10 font-bold"
    : isMetric
    ? `${cfg.bg} ${cfg.color} font-bold`
    : "bg-primary/5";

  return (
    <td className={`sticky right-0 z-10 text-right px-3 py-1.5 tabular-nums border-l-2 border-primary ${cls}`}>
      {display}
    </td>
  );
}

/* ============================================================ */
/* KPI riassunto periodo                                         */
/* ============================================================ */
function PeriodoKpiRow({ data }: { data: AnalisiResponse }) {
  const cards = [
    { label: "Fatturato Totale", value: formatEuro(data.totali.fatturato_netto), sub: `${data.num_mesi_attivi} mesi attivi`, tone: "primary" as const },
    { label: "Fatturato Medio", value: formatEuro(data.fatt_medio_mensile), sub: "media mensile", tone: "default" as const },
    { label: "Food Cost", value: formatEuro(data.totali.costi_fb_totali), sub: `incidenza ${formatPct(data.food_cost_perc)}`, tone: "default" as const },
    { label: "1° Margine", value: formatEuro(data.totali.primo_margine), sub: `incidenza ${formatPct(data.primo_margine_perc)}`, tone: data.totali.primo_margine >= 0 ? "positive" as const : "negative" as const },
    { label: "Spese Generali", value: formatEuro(data.totali.costi_spese_totali), sub: `incidenza ${formatPct(data.spese_gen_perc)}`, tone: "default" as const },
    { label: "Costo del Lavoro", value: formatEuro(data.totali.costi_personale), sub: `incidenza ${formatPct(data.personale_perc)}`, tone: "default" as const },
    { label: "MOL", value: formatEuro(data.totali.mol), sub: `incidenza ${formatPct(data.mol_perc)}`, tone: data.totali.mol >= 0 ? "positive" as const : "negative" as const },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`rounded-lg border p-3 ${
            c.tone === "primary"
              ? "border-primary/30 bg-primary/5"
              : c.tone === "positive"
              ? "border-emerald-500/30 bg-emerald-500/5"
              : c.tone === "negative"
              ? "border-rose-500/30 bg-rose-500/5"
              : "border-border bg-card"
          }`}
        >
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{c.label}</p>
          <p
            className={`text-base font-bold mt-0.5 leading-tight ${
              c.tone === "primary"
                ? "text-primary"
                : c.tone === "positive"
                ? "text-emerald-700 dark:text-emerald-400"
                : c.tone === "negative"
                ? "text-rose-700 dark:text-rose-400"
                : ""
            }`}
          >
            {c.value}
          </p>
          <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{c.sub}</p>
        </div>
      ))}
    </div>
  );
}
