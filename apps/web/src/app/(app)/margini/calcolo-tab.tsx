"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Info, Lock, BarChart3, Upload, X as XIcon, Pencil } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell as RCell,
} from "recharts";
import { toast } from "sonner";
import { formatEuro, formatEuroCompact, scorporoNetto } from "./periodi";
import { CaricaRicaviDialog } from "./carica-ricavi-dialog";
import { CostoPersonaleDialog } from "./costo-personale-dialog";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

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

type ValueColor = "white" | "sign" | "purple" | "sky" | "orange";

type RowDef = {
  key: string;
  label: string;
  type: "input-readonly" | "input-readonly-tooltip" | "input-editable" | "computed";
  field?: EditableField;
  section: Section;
  isMetric?: boolean;
  isMolMargin?: boolean;
  derive?: (m: MesePivot) => number;   // righe virtuali calcolate
  labelColor?: string;                 // classe tailwind per la prima colonna
  valueColor: ValueColor;              // colore dei valori nelle celle
};

const ROWS: RowDef[] = [
  { key: "fatturato_iva10",       label: "Ricavi IVA 10%",         type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  { key: "fatturato_iva22",       label: "Ricavi IVA 22%",         type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  { key: "altri_ricavi_noiva",    label: "Altri ricavi (no IVA)",  type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  { key: "fatturato_netto",       label: "= Fatturato Netto",      type: "computed", section: "ricavi", isMetric: true, labelColor: "text-sky-500 dark:text-sky-400", valueColor: "sky" },
  { key: "costi_fb_auto",         label: "Costi F&B (Fatture)",    type: "input-readonly", section: "fb", valueColor: "white" },
  { key: "altri_costi_fb",        label: "Altri Costi F&B",        type: "input-editable", field: "altri_costi_fb", section: "fb", valueColor: "white" },
  { key: "costi_fb_totali",       label: "= Costi F&B Totali",     type: "computed", section: "fb", isMetric: true, labelColor: "text-orange-500 dark:text-orange-400", valueColor: "orange" },
  { key: "primo_margine",         label: "= 1° Margine",           type: "computed", section: "margine", isMetric: true, labelColor: "text-emerald-500 dark:text-emerald-400", valueColor: "sign" },
  { key: "costi_spese_auto",      label: "Spese Gen. (Fatture)",   type: "input-readonly", section: "spese", valueColor: "white" },
  { key: "altri_costi_spese",     label: "Altre Spese Generali",   type: "input-editable", field: "altri_costi_spese", section: "spese", valueColor: "white" },
  { key: "costo_dipendenti",      label: "Costo Personale Lordo",  type: "input-editable", field: "costo_dipendenti", section: "personale", valueColor: "white" },
  { key: "costo_personale_extra", label: "Costo Personale Extra",  type: "input-editable", field: "costo_personale_extra", section: "personale", valueColor: "white" },
  { key: "totale_costi",          label: "= Costi gestione totali", type: "computed", section: "spese", isMetric: true, derive: (m) => m.costi_fb_totali + m.costi_spese_totali + m.costi_personale, labelColor: "text-violet-500 dark:text-violet-400", valueColor: "purple" },
  { key: "mol",                   label: "= 2° Margine (MOL)",     type: "computed", section: "margine", isMetric: true, isMolMargin: true, labelColor: "text-green-600 dark:text-green-300", valueColor: "sign" },
];

// Separatori tra blocchi: bordo top più marcato prima di questi indici
const SEP_BEFORE = new Set([4, 8, 12]);

function rowVal(row: RowDef, m: MesePivot): number {
  if (row.derive) return row.derive(m);
  return (m[row.key as keyof MesePivot] as number) ?? 0;
}

// Colore dei valori (e della % incidenza) in base al value-color mode.
function valueColorCls(vc: ValueColor, raw: number): string {
  if (vc === "sign") {
    return raw > 0
      ? "text-emerald-600 dark:text-emerald-400"
      : raw < 0
      ? "text-rose-600 dark:text-rose-400"
      : "text-muted-foreground";
  }
  if (vc === "purple") return "text-violet-600 dark:text-violet-400";
  if (vc === "sky") return "text-sky-600 dark:text-sky-400";
  if (vc === "orange") return "text-orange-600 dark:text-orange-400";
  return ""; // white = foreground
}

function pctIncidenza(raw: number, netto: number): string | null {
  if (!netto || netto === 0 || raw === 0) return null;
  return `${((raw / netto) * 100).toFixed(0)}%`;
}

const ANNO_MESE_CORRENTE = (() => {
  const d = new Date();
  return { anno: d.getFullYear(), mese: d.getMonth() + 1 };
})();

const SECTION_CONFIG: Record<Section, { color: string; bg: string; border: string; rgb: string }> = {
  ricavi: {
    color: "text-sky-700 dark:text-sky-300",
    bg: "bg-sky-500/8",
    border: "border-l-sky-500",
    rgb: "14,165,233",
  },
  fb: {
    color: "text-orange-700 dark:text-orange-300",
    bg: "bg-orange-500/8",
    border: "border-l-orange-500",
    rgb: "249,115,22",
  },
  spese: {
    color: "text-purple-700 dark:text-purple-300",
    bg: "bg-purple-500/8",
    border: "border-l-purple-500",
    rgb: "168,85,247",
  },
  personale: {
    color: "text-pink-700 dark:text-pink-300",
    bg: "bg-pink-500/8",
    border: "border-l-pink-500",
    rgb: "236,72,153",
  },
  margine: {
    color: "text-emerald-700 dark:text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-l-emerald-500",
    rgb: "16,185,129",
  },
};

type Props = {
  dataDa: string;
  dataA: string;
};

export function CalcoloTab({ dataDa, dataA }: Props) {
  const [data, setData] = useState<AnalisiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [caricaOpen, setCaricaOpen] = useState(false);
  const [dettaglioOpen, setDettaglioOpen] = useState(false);
  const [dettaglioMeseSel, setDettaglioMeseSel] = useState<{ anno: number; mese: number; label: string } | null>(null);
  const [costoPersMese, setCostoPersMese] = useState<MesePivot | null>(null);

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

  async function postCella(anno: number, mese: number, field: EditableField, value: number) {
    const res = await fetch("/api/margini/cella", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anno, mese, field, value }),
    });
    if (!res.ok) throw new Error();
  }

  async function saveCell(
    anno: number,
    mese: number,
    field: EditableField,
    value: number,
    prevValue: number,
  ) {
    try {
      await postCella(anno, mese, field, value);
      toast.success("Salvato", {
        action: {
          label: "Annulla",
          onClick: async () => {
            try {
              await postCella(anno, mese, field, prevValue);
              toast.success("Modifica annullata");
              load();
            } catch {
              toast.error("Impossibile annullare");
            }
          },
        },
      });
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
          Usa &quot;Carica ricavi&quot; per inserire i ricavi o carica fatture per popolare automaticamente i costi.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="size-3" />
          Modifica le righe in bianco; le altre sono calcolate o ereditate dalle fatture.
        </p>
        <button
          onClick={() => { setDettaglioMeseSel(mesiVisibili[mesiVisibili.length - 1] ?? null); setDettaglioOpen(true); }}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-input hover:bg-muted transition-colors"
        >
          <BarChart3 className="size-3" />
          Dettaglio giornaliero
        </button>
        <button
          onClick={() => setCaricaOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Upload className="size-3" />
          Carica ricavi
        </button>
      </div>

      <CaricaRicaviDialog
        open={caricaOpen}
        onOpenChange={setCaricaOpen}
        dataDa={dataDa}
        dataA={dataA}
        onImported={() => { setCaricaOpen(false); load(); }}
      />

      {dettaglioOpen && (
        <DettaglioGiornalieroDialog
          mese={dettaglioMeseSel}
          mesi={mesiVisibili}
          onMeseChange={setDettaglioMeseSel}
          onClose={() => setDettaglioOpen(false)}
        />
      )}

      {/* Legenda colori */}
      <div className="flex flex-wrap gap-1.5">
        {([
          { label: "Ricavi", section: "ricavi" as Section },
          { label: "Costi F&B", section: "fb" as Section },
          { label: "Costi Gestione", section: "spese" as Section },
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

      {/* Tabella trasposta — desktop */}
      <div className="hidden md:block rounded-lg border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full table-auto text-[15px] border-collapse">
            <colgroup>
              <col className="w-[220px]" />
              {mesiVisibili.map((m) => (
                <col key={`c-${m.anno}-${m.mese}`} className="w-[140px]" />
              ))}
              <col className="w-[160px]" />
            </colgroup>
            <thead className="bg-muted/40">
              <tr className="text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="sticky left-0 z-20 bg-muted/40 text-left px-3 py-2.5 font-semibold border-r border-border">
                  Voce
                </th>
                {mesiVisibili.map((m) => {
                  const isCurrent = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
                  return (
                    <th
                      key={`${m.anno}-${m.mese}`}
                      className={`text-right px-3 py-2.5 font-semibold ${
                        isCurrent
                          ? "text-sky-500 dark:text-sky-400 border-l border-r border-sky-500/50"
                          : "border-r border-border"
                      }`}
                    >
                      {isCurrent && <span className="mr-1 inline-block size-1.5 rounded-full bg-sky-400 align-middle" />}
                      {m.label}
                    </th>
                  );
                })}
                <th className="sticky right-0 z-20 bg-sky-500/8 text-right px-3 py-2.5 font-bold border-l-2 border-r border-sky-500/50 text-sky-600 dark:text-sky-400">
                  Totale
                </th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, ri) => {
                const isMetric = row.isMetric;
                return (
                  <tr
                    key={ri}
                    className={`${SEP_BEFORE.has(ri) ? "border-t-[3px] border-t-border" : "border-t border-border"} ${
                      isMetric ? "font-semibold bg-muted/[0.04]" : ""
                    }`}
                  >
                    <td
                      className={`sticky left-0 z-10 bg-card px-3 py-2 border-r border-border whitespace-nowrap ${
                        isMetric ? `font-bold ${row.labelColor ?? ""}` : ""
                      }`}
                    >
                      {row.label}
                    </td>
                    {mesiVisibili.map((m) => {
                      const isCurrent = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
                      return (
                        <Cell
                          key={`${m.anno}-${m.mese}`}
                          row={row}
                          mese={m}
                          isCurrent={isCurrent}
                          onSave={saveCell}
                          onOpenCosto={setCostoPersMese}
                        />
                      );
                    })}
                    {/* Total column */}
                    <TotalCell row={row} totali={data.totali} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Vista mobile — card per mese */}
      <div className="md:hidden">
        <MobileMeseView mesi={mesiVisibili} totali={data.totali} onSave={saveCell} onOpenCosto={setCostoPersMese} />
      </div>

      {/* Analisi visiva: cascata conto economico + gauge + commenti */}
      <AnalisiVisiva data={data} />

      {costoPersMese && (
        <CostoPersonaleDialog
          open
          anno={costoPersMese.anno}
          mese={costoPersMese.mese}
          label={costoPersMese.label}
          costoDipendenti={costoPersMese.costo_dipendenti}
          costoExtra={costoPersMese.costo_personale_extra}
          onClose={() => setCostoPersMese(null)}
          onSaved={load}
        />
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
  isCurrent,
  onSave,
  onOpenCosto,
}: {
  row: RowDef;
  mese: MesePivot;
  isCurrent: boolean;
  onSave: (anno: number, mese: number, field: EditableField, value: number, prevValue: number) => void;
  onOpenCosto: (m: MesePivot) => void;
}) {
  const raw = rowVal(row, mese);
  const isMetric = row.isMetric;
  const colorCls = valueColorCls(row.valueColor, raw);
  const pct = pctIncidenza(raw, mese.fatturato_netto);
  const display = raw === 0 ? "—" : formatEuro(raw);

  const currentCls = isCurrent
    ? "border-l border-r border-sky-500/50"
    : "border-r border-border";

  // Righe personale: cella cliccabile che apre il widget (recupera da Personale o manuale)
  if (row.section === "personale" && row.type === "input-editable") {
    return (
      <td className={`text-right p-0 align-middle ${currentCls}`}>
        <button
          type="button"
          onClick={() => onOpenCosto(mese)}
          title="Imposta costo (recupera da Personale o inserisci a mano)"
          className="w-full px-3 py-2 text-right tabular-nums hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset outline-none transition-colors group/cella"
        >
          <span className="inline-flex items-center justify-end gap-1">
            {display === "—" ? <span className="text-muted-foreground/60">—</span> : display}
            <Pencil className="size-3 opacity-0 group-hover/cella:opacity-40 transition-opacity" />
          </span>
          {pct && <span className="block text-[11px] tabular-nums opacity-70">{pct}</span>}
        </button>
      </td>
    );
  }

  if (row.type === "input-editable" && row.field) {
    return (
      <EditableCell
        value={raw}
        netto={mese.fatturato_netto}
        isCurrent={isCurrent}
        onSave={(v) => onSave(mese.anno, mese.mese, row.field!, v, raw)}
      />
    );
  }

  const tooltip =
    row.type === "input-readonly-tooltip" ? "Modifica da Carica ricavi"
    : row.type === "input-readonly" ? "Calcolato dalle fatture caricate"
    : undefined;
  const showLock = row.type === "input-readonly-tooltip" || row.type === "input-readonly";

  return (
    <td className={`text-right px-3 py-2 align-middle ${currentCls}`}>
      <div
        title={tooltip}
        className={`inline-flex items-center justify-end gap-1 tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls} ${showLock ? "cursor-help" : ""}`}
      >
        {display}
        {showLock && <Lock className="size-3 opacity-30" />}
      </div>
      {pct && <div className={`text-[11px] tabular-nums opacity-70 ${colorCls}`}>{pct}</div>}
    </td>
  );
}

function EditableCell({
  value,
  netto,
  isCurrent,
  onSave,
}: {
  value: number;
  netto: number;
  isCurrent: boolean;
  onSave: (v: number) => void;
}) {
  const initStr = value > 0 ? String(Math.round(value)) : "";
  const [local, setLocal] = useState(initStr);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setLocal(value > 0 ? String(Math.round(value)) : "");
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

  const liveVal = parseFloat(local.replace(",", ".")) || 0;
  const pct = pctIncidenza(liveVal, netto);

  const currentCls = isCurrent
    ? "border-l border-r border-sky-500/50"
    : "border-r border-border";

  return (
    <td className={`p-0 align-middle ${currentCls}`}>
      <input
        type="number"
        step="1"
        min="0"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setLocal(value > 0 ? String(Math.round(value)) : "");
            (e.target as HTMLInputElement).blur();
          }
        }}
        placeholder="—"
        className={`w-full px-3 pt-2 pb-0 text-right tabular-nums bg-transparent border-0 outline-none transition-colors text-[15px] ${
          saved
            ? "bg-emerald-500/10"
            : saving
            ? "bg-sky-500/5"
            : "hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset"
        }`}
      />
      {pct && (
        <div className="px-3 pb-1.5 text-right text-[11px] tabular-nums opacity-70">{pct}</div>
      )}
    </td>
  );
}

function TotalCell({
  row,
  totali,
}: {
  row: RowDef;
  totali: MesePivot;
}) {
  const raw = rowVal(row, totali);
  const display = raw === 0 ? "—" : formatEuro(raw);
  const isMetric = row.isMetric;
  const colorCls = valueColorCls(row.valueColor, raw);
  const pct = pctIncidenza(raw, totali.fatturato_netto);

  return (
    <td className="sticky right-0 z-10 bg-sky-500/8 text-right px-3 py-2 tabular-nums border-l-2 border-r border-sky-500/50 align-middle">
      <div className={`tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls}`}>{display}</div>
      {pct && <div className={`text-[11px] tabular-nums opacity-70 ${colorCls}`}>{pct}</div>}
    </td>
  );
}

/* ============================================================ */
/* Vista mobile — card per mese                                  */
/* ============================================================ */
function MobileMeseView({
  mesi,
  totali,
  onSave,
  onOpenCosto,
}: {
  mesi: MesePivot[];
  totali: MesePivot;
  onSave: (anno: number, mese: number, field: EditableField, value: number, prevValue: number) => void;
  onOpenCosto: (m: MesePivot) => void;
}) {
  const [selIdx, setSelIdx] = useState(mesi.length - 1);
  const isTotal = selIdx >= mesi.length;
  const current = isTotal ? totali : mesi[Math.min(selIdx, mesi.length - 1)];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-muted-foreground font-medium">Mese</label>
        <select
          value={selIdx}
          onChange={(e) => setSelIdx(Number(e.target.value))}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm"
        >
          {mesi.map((m, i) => (
            <option key={`${m.anno}-${m.mese}`} value={i}>{m.label}</option>
          ))}
          <option value={mesi.length}>Totale periodo</option>
        </select>
      </div>

      <div className="rounded-lg border border-border bg-card divide-y divide-border overflow-hidden">
        {ROWS.map((row, ri) => {
          const raw = rowVal(row, current);
          const isMetric = row.isMetric;
          const editable = row.type === "input-editable" && !isTotal;
          const isPersonale = row.section === "personale" && row.type === "input-editable";
          const colorCls = valueColorCls(row.valueColor, raw);
          const pct = pctIncidenza(raw, current.fatturato_netto);

          return (
            <div key={ri} className="flex items-center justify-between gap-3 px-3 py-2.5">
              <span className={`text-sm ${isMetric ? `font-semibold ${row.labelColor ?? ""}` : ""}`}>
                {row.label}
              </span>
              {isPersonale && !isTotal ? (
                <button
                  type="button"
                  onClick={() => onOpenCosto(current)}
                  className="inline-flex items-center gap-1.5 text-sm tabular-nums px-2 py-1 rounded-md border border-input hover:bg-muted transition-colors"
                >
                  {raw === 0 ? "Imposta" : formatEuro(raw)}
                  <Pencil className="size-3 opacity-40" />
                </button>
              ) : editable ? (
                <MobileEditInput
                  value={raw}
                  onSave={(v) => onSave(current.anno, current.mese, row.field!, v, raw)}
                />
              ) : (
                <span className={`text-sm shrink-0 text-right tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls}`}>
                  {raw === 0 ? "—" : formatEuro(raw)}
                  {pct && <span className="block text-[10px] opacity-65">{pct}</span>}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MobileEditInput({
  value,
  onSave,
}: {
  value: number;
  onSave: (v: number) => void | Promise<void>;
}) {
  const [local, setLocal] = useState(value > 0 ? String(Math.round(value)) : "");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setLocal(value > 0 ? String(Math.round(value)) : "");
  }, [value]);

  async function commit() {
    const newVal = parseFloat(local.replace(",", ".")) || 0;
    if (Math.abs(newVal - value) < 0.001) return;
    await onSave(newVal);
    setSaved(true);
    setTimeout(() => setSaved(false), 800);
  }

  return (
    <input
      type="number"
      step="1"
      min="0"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setLocal(value > 0 ? String(Math.round(value)) : "");
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder="—"
      className={`w-32 h-8 px-2 text-right tabular-nums rounded border bg-transparent outline-none transition-colors text-sm ${
        saved
          ? "border-emerald-500 bg-emerald-500/10"
          : "border-input focus:border-primary focus:bg-background"
      }`}
    />
  );
}

/* ============================================================ */
/* Analisi visiva: cascata conto economico + gauge + commenti    */
/* ============================================================ */
const GAUGE_GREEN = "#10b981";
const GAUGE_AMBER = "#f59e0b";
const GAUGE_ROSE = "#f43f5e";

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v));
}

function AnalisiVisiva({ data }: { data: AnalisiResponse }) {
  const t = data.totali;
  const hasData = t.fatturato_netto > 0 || t.costi_fb_totali > 0;

  const fc = data.food_cost_perc;
  const fcColor = fc <= 28 ? GAUGE_GREEN : fc <= 33 ? GAUGE_AMBER : GAUGE_ROSE;
  const pm = data.primo_margine_perc;
  const pmColor = pm >= 67 ? GAUGE_GREEN : pm >= 60 ? GAUGE_AMBER : GAUGE_ROSE;
  const sg = data.spese_gen_perc;
  const sgColor = sg <= 15 ? GAUGE_GREEN : sg <= 22 ? GAUGE_AMBER : GAUGE_ROSE;
  const mol = data.mol_perc;
  const molColor = mol >= 10 ? GAUGE_GREEN : mol >= 5 ? GAUGE_AMBER : GAUGE_ROSE;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-5">
      <h3 className="text-base font-semibold flex items-center gap-1.5">
        <BarChart3 className="size-4 text-primary" />
        Analisi visiva
      </h3>

      {!hasData ? (
        <p className="text-sm text-muted-foreground py-6 text-center">
          Inserisci ricavi e carica fatture per generare l&apos;analisi.
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-20 items-stretch">
          {/* Cascata P&L */}
          <div className="flex flex-col justify-around">
            <CascataPL t={t} />
          </div>

          {/* Gauge con diagnosi integrata */}
          <div className="flex flex-col gap-0 divide-y divide-border">
            {[
              { label: "Food Cost",      valueText: `${fc.toFixed(0)}%`,  fraction: clamp01(fc / 100),  trackColor: "#f97316", valueColor: fcColor },
              { label: "1° Margine",     valueText: `${pm.toFixed(0)}%`,  fraction: clamp01(pm / 100),  trackColor: "#10b981", valueColor: pmColor },
              { label: "Costi Gestione", valueText: `${sg.toFixed(0)}%`,  fraction: clamp01(sg / 100),  trackColor: "#8b5cf6", valueColor: sgColor },
              { label: "MOL",            valueText: `${mol.toFixed(0)}%`, fraction: clamp01(mol / 100), trackColor: "#22c55e", valueColor: molColor },
            ].map((g) => {
              const commento = data.commenti.find(
                (c) => c.kpi_nome.toLowerCase().replace(/[°\s]/g, "") === g.label.toLowerCase().replace(/[°\s]/g, "")
              );
              return (
                <div key={g.label} className="flex items-center gap-6 py-5">
                  <Gauge {...g} size="sm" />
                  <div className="flex flex-col gap-1.5 min-w-0">
                    <span className="text-base font-bold leading-tight">
                      {commento?.emoji} {g.label}
                    </span>
                    <span className="text-sm text-muted-foreground leading-snug">
                      {commento?.commento ?? "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function CascataPL({ t }: { t: MesePivot }) {
  const steps: { label: string; value: number; kind: "result" | "cost"; rgb: string }[] = [
    { label: "Fatturato Netto", value: t.fatturato_netto, kind: "result", rgb: "14,165,233" },
    { label: "− Costi F&B", value: t.costi_fb_totali, kind: "cost", rgb: "249,115,22" },
    { label: "= 1° Margine", value: t.primo_margine, kind: "result", rgb: t.primo_margine >= 0 ? "16,185,129" : "244,63,94" },
    { label: "− Costi Gestione", value: t.costi_spese_totali, kind: "cost", rgb: "168,85,247" },
    { label: "= MOL", value: t.mol, kind: "result", rgb: t.mol >= 0 ? "16,185,129" : "244,63,94" },
  ];
  const refMax = Math.max(1, ...steps.map((s) => Math.abs(s.value)));

  return (
    <div className="flex flex-col gap-6">
      {steps.map((s) => {
        const w = Math.min(100, (Math.abs(s.value) / refMax) * 100);
        const isResult = s.kind === "result";
        return (
          <div key={s.label} className="flex items-center gap-3">
            <span className={`w-36 sm:w-40 shrink-0 text-base ${isResult ? "font-bold" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            <div className={`flex-1 h-9 rounded overflow-hidden ${isResult ? "bg-muted/40" : "bg-muted/20"}`}>
              <div
                className="h-full rounded transition-all duration-500"
                style={{
                  width: `${w}%`,
                  backgroundColor: `rgb(${s.rgb})`,
                  opacity: isResult ? 0.95 : 0.65,
                  boxShadow: isResult ? `0 0 14px rgba(${s.rgb},0.5)` : undefined,
                }}
              />
            </div>
            <span
              className={`w-28 sm:w-32 shrink-0 text-right text-base tabular-nums ${isResult ? "font-bold" : "text-muted-foreground"}`}
              style={isResult ? { color: `rgb(${s.rgb})` } : undefined}
            >
              {formatEuro(s.value)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function Gauge({
  label,
  valueText,
  fraction,
  trackColor,
  valueColor,
  size = "md",
}: {
  label: string;
  valueText: string;
  fraction: number;
  trackColor: string;
  valueColor: string;
  size?: "sm" | "md";
}) {
  const f = clamp01(fraction);
  const r = 36;
  const startDeg = 225;
  const sweepDeg = 270;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const sx = 50 + r * Math.cos(toRad(startDeg));
  const sy = 50 + r * Math.sin(toRad(startDeg));
  const endDeg = startDeg + sweepDeg;
  const ex = 50 + r * Math.cos(toRad(endDeg));
  const ey = 50 + r * Math.sin(toRad(endDeg));
  const largeArc = sweepDeg > 180 ? 1 : 0;
  const ARC = `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`;

  const svgSize = size === "sm" ? "w-20 h-20 shrink-0" : "w-full max-w-[110px]";

  return (
    <div className={`flex flex-col items-center gap-1 ${size === "sm" ? "shrink-0" : ""}`}>
      <svg viewBox="0 0 100 100" className={svgSize}>
        {/* Traccia di sfondo */}
        <path
          d={ARC}
          fill="none"
          stroke="currentColor"
          className="text-muted-foreground/15"
          strokeWidth="10"
          strokeLinecap="round"
          pathLength={100}
        />
        {/* Arco riempito con colore KPI */}
        <path
          d={ARC}
          fill="none"
          stroke={trackColor}
          strokeWidth="10"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${f * 100} 100`}
          style={{ filter: f > 0.05 ? `drop-shadow(0 0 4px ${trackColor}90)` : undefined }}
        />
        {/* Valore centrato con colore performance */}
        <text
          x="50"
          y="53"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="18"
          fontWeight="bold"
          fill={valueColor}
        >
          {valueText}
        </text>
      </svg>
      {size !== "sm" && (
        <span className="text-[11px] text-muted-foreground font-medium text-center leading-tight">{label}</span>
      )}
    </div>
  );
}

/* ============================================================ */
/* DettaglioGiornalieroDialog                                    */
/* ============================================================ */
type RicavoGiorno = {
  data: string;
  fatturato_netto: number;
};

function DettaglioGiornalieroDialog({
  mese, mesi, onMeseChange, onClose,
}: {
  mese: { anno: number; mese: number; label: string } | null;
  mesi: MesePivot[];
  onMeseChange: (m: { anno: number; mese: number; label: string }) => void;
  onClose: () => void;
}) {
  const [giorni, setGiorni] = useState<RicavoGiorno[]>([]);
  const [loading, setLoading] = useState(true);

  const anno = mese?.anno ?? 0;
  const meseNum = mese?.mese ?? 0;
  const label = mese?.label ?? "";

  useEffect(() => {
    if (!meseNum) return;
    setLoading(true);
    setGiorni([]);
    const pad = (n: number) => String(n).padStart(2, "0");
    const lastDay = new Date(anno, meseNum, 0).getDate();
    const dataDa = `${anno}-${pad(meseNum)}-01`;
    const dataA = `${anno}-${pad(meseNum)}-${lastDay}`;

    fetch(`/api/ricavi/giornalieri?data_da=${dataDa}&data_a=${dataA}`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        const items: { data: string; fatturato_iva10: number; fatturato_iva22: number; altri_ricavi_noiva: number }[] = d?.items ?? [];
        const byDate = new Map(items.map((i) => [
          i.data,
          scorporoNetto(i.fatturato_iva10, i.fatturato_iva22, i.altri_ricavi_noiva),
        ]));
        const result: RicavoGiorno[] = [];
        for (let d = 1; d <= lastDay; d++) {
          const key = `${anno}-${pad(meseNum)}-${pad(d)}`;
          result.push({ data: key, fatturato_netto: byDate.get(key) ?? 0 });
        }
        setGiorni(result);
      })
      .catch(() => setGiorni([]))
      .finally(() => setLoading(false));
  }, [anno, meseNum]);

  const compilati = giorni.filter((g) => g.fatturato_netto > 0);
  const totale = compilati.reduce((s, g) => s + g.fatturato_netto, 0);
  const media = compilati.length > 0 ? totale / compilati.length : 0;
  const migliore = compilati.reduce<RicavoGiorno | null>((best, g) => (!best || g.fatturato_netto > best.fatturato_netto) ? g : best, null);
  const peggiore = compilati.reduce<RicavoGiorno | null>((worst, g) => (!worst || g.fatturato_netto < worst.fatturato_netto) ? g : worst, null);

  const chartData = giorni.map((g) => ({
    giorno: parseInt(g.data.slice(8), 10),
    netto: g.fatturato_netto,
  }));

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(760px,92vw)] w-full p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              📅 Fatturato giornaliero
            </DialogTitle>
            <button onClick={onClose} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors shrink-0">
              <XIcon className="size-4" />
            </button>
          </div>
          {/* Selettore mese */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {mesi.map((m) => {
              const active = m.anno === anno && m.mese === meseNum;
              return (
                <button
                  key={`${m.anno}-${m.mese}`}
                  onClick={() => onMeseChange({ anno: m.anno, mese: m.mese, label: m.label })}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${
                    active
                      ? "bg-sky-500 text-white border-sky-500"
                      : "border-input hover:bg-muted"
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </DialogHeader>

        <div className="px-6 py-5 space-y-5">
          {loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Caricamento…</p>
          ) : compilati.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Nessun dato giornaliero per {label}.</p>
          ) : (
            <>
              {/* Bar chart */}
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} vertical={false} />
                  <XAxis
                    dataKey="giorno"
                    tick={{ fontSize: 11, fill: "#ffffff" }}
                    tickLine={false}
                    axisLine={false}
                    interval={1}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#ffffff" }}
                    tickLine={false}
                    axisLine={false}
                    width={52}
                    tickFormatter={(v: number) => formatEuroCompact(v)}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--muted))", opacity: 0.4 }}
                    formatter={(v: unknown) => [formatEuro(typeof v === "number" ? v : 0), "Fatturato netto"]}
                    labelFormatter={(l) => `Giorno ${l}`}
                    contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "hsl(var(--card))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}
                  />
                  <Bar dataKey="netto" radius={[3, 3, 0, 0]} maxBarSize={28}>
                    {chartData.map((entry, i) => (
                      <RCell key={i} fill={entry.netto > 0 ? "#0ea5e9" : "hsl(var(--muted))"} opacity={entry.netto > 0 ? 0.9 : 0.3} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>

              {/* 4 statistiche */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatBox label="Giorni compilati" value={`${compilati.length} / ${giorni.length}`} />
                <StatBox label="Media giornaliera" value={formatEuro(media)} color="text-sky-600 dark:text-sky-400" />
                <StatBox
                  label="Giorno migliore"
                  value={migliore ? formatEuro(migliore.fatturato_netto) : "—"}
                  sub={migliore ? `${parseInt(migliore.data.slice(8), 10)} ${label}` : undefined}
                  color="text-emerald-600 dark:text-emerald-400"
                />
                <StatBox
                  label="Giorno peggiore"
                  value={peggiore ? formatEuro(peggiore.fatturato_netto) : "—"}
                  sub={peggiore ? `${parseInt(peggiore.data.slice(8), 10)} ${label}` : undefined}
                  color="text-rose-600 dark:text-rose-400"
                />
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
