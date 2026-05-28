"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Plus, Trash2, RefreshCw, TrendingUp, ChevronDown, ChevronUp,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid,
} from "recharts";
import { toast } from "sonner";
import {
  Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger, SheetFooter,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UploadXlsModal } from "./upload-xls-modal";
import {
  formatEuro, formatEuroCompact, formatData, MESI_NOMI_SHORT,
} from "./periodi";
import type {
  RicaviGiornalieriResponse, RicavoGiornaliero, RicaviBatchUpsertResponse,
} from "@/lib/ricavi";

const SOURCE_LABEL: Record<string, { label: string; color: string }> = {
  manuale: { label: "Manuale", color: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
  xls: { label: "XLS", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  email: { label: "Email", color: "bg-sky-500/15 text-sky-700 dark:text-sky-400" },
};

type Props = {
  dataDa: string;
  dataA: string;
};

type RipartizioneCentri = {
  fatturato_food: number;
  fatturato_beverage: number;
  fatturato_alcolici: number;
  fatturato_dolci: number;
};

export function RicaviTab({ dataDa, dataA }: Props) {
  const router = useRouter();
  const [data, setData] = useState<RicaviGiornalieriResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [showCentri, setShowCentri] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `/api/ricavi/giornalieri?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error();
      const d: RicaviGiornalieriResponse = await res.json();
      setData(d);
    } catch {
      toast.error("Errore nel caricamento ricavi");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [dataDa, dataA]);

  useEffect(() => { load(); }, [load]);

  function onImported() {
    load();
    router.refresh();
  }

  return (
    <div className="space-y-5">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <UploadXlsModal onImported={onImported} />
        <AddGiornoSheet onSaved={onImported} dataDa={dataDa} dataA={dataA} />
        <Button variant="ghost" size="sm" onClick={load} disabled={loading} className="gap-1.5">
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          Aggiorna
        </Button>
        {data && (
          <SourceBadge items={data.items} />
        )}
      </div>

      {/* Grafico mensile */}
      {data && data.items.length > 0 && (
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            <TrendingUp className="size-4 text-primary" />
            Andamento mensile
          </h3>
          <MensileBarChart items={data.items} />
        </div>
      )}

      {/* Tabella giornaliera */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            Ricavi giornalieri
            {data && <span className="text-muted-foreground font-normal ml-2">({data.items.length} giorni)</span>}
          </h3>
        </div>
        {loading ? (
          <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
        ) : !data || data.items.length === 0 ? (
          <EmptyState />
        ) : (
          <GiornalieriTable items={data.items} onChanged={load} />
        )}
      </div>

      {/* Ripartizione centri */}
      <div className="rounded-lg border border-border bg-card overflow-hidden">
        <button
          onClick={() => setShowCentri((v) => !v)}
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-muted/30 transition-colors"
        >
          <span className="text-sm font-semibold">Ripartizione ricavi per centro</span>
          {showCentri ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
        </button>
        {showCentri && (
          <div className="border-t border-border p-4">
            <RipartizioneCentriSection dataDa={dataDa} dataA={dataA} />
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================ */
/* Source badge                                                  */
/* ============================================================ */
function SourceBadge({ items }: { items: RicavoGiornaliero[] }) {
  const counts = items.reduce<Record<string, number>>((acc, r) => {
    acc[r.source] = (acc[r.source] ?? 0) + 1;
    return acc;
  }, {});
  const entries = Object.entries(counts);
  if (entries.length === 0) return null;
  return (
    <div className="ml-auto flex items-center gap-1.5 text-xs">
      {entries.map(([src, n]) => {
        const conf = SOURCE_LABEL[src] ?? SOURCE_LABEL.manuale;
        return (
          <span key={src} className={`px-2 py-0.5 rounded-full font-medium ${conf.color}`}>
            {n} {conf.label}
          </span>
        );
      })}
    </div>
  );
}

/* ============================================================ */
/* Empty state                                                   */
/* ============================================================ */
function EmptyState() {
  return (
    <div className="py-12 px-4 text-center space-y-2">
      <p className="text-sm font-medium">Nessun ricavo nel periodo</p>
      <p className="text-xs text-muted-foreground">
        Carica un XLS o aggiungi giorni manualmente per iniziare.
      </p>
    </div>
  );
}

/* ============================================================ */
/* BarChart mensile stacked                                      */
/* ============================================================ */
type MensileRow = {
  mese: string;
  ym: string;
  iva10: number;
  iva22: number;
  altri: number;
};

function MensileBarChart({ items }: { items: RicavoGiornaliero[] }) {
  const data: MensileRow[] = useMemo(() => {
    const map = new Map<string, MensileRow>();
    for (const r of items) {
      const [yStr, mStr] = r.data.split("-");
      const y = parseInt(yStr, 10);
      const m = parseInt(mStr, 10);
      const key = `${y}-${String(m).padStart(2, "0")}`;
      const existing = map.get(key) ?? {
        mese: `${MESI_NOMI_SHORT[m - 1]} '${String(y).slice(2)}`,
        ym: key,
        iva10: 0, iva22: 0, altri: 0,
      };
      existing.iva10 += r.fatturato_iva10;
      existing.iva22 += r.fatturato_iva22;
      existing.altri += r.altri_ricavi_noiva;
      map.set(key, existing);
    }
    return Array.from(map.values()).sort((a, b) => a.ym.localeCompare(b.ym));
  }, [items]);

  if (data.length === 0) return null;

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.4} />
        <XAxis dataKey="mese" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
               tickLine={false} axisLine={false} />
        <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
               tickLine={false} axisLine={false}
               tickFormatter={(v: number) => formatEuroCompact(v)} />
        <Tooltip
          formatter={(value: unknown) => formatEuro(typeof value === "number" ? value : 0)}
          contentStyle={{ fontSize: 11, borderRadius: 6 }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
        <Bar dataKey="iva10" stackId="a" fill="#0ea5e9" name="IVA 10%" radius={[0, 0, 0, 0]} />
        <Bar dataKey="iva22" stackId="a" fill="#6366f1" name="IVA 22%" radius={[0, 0, 0, 0]} />
        <Bar dataKey="altri" stackId="a" fill="#10b981" name="Altri (no IVA)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ============================================================ */
/* Tabella giornaliera editable                                  */
/* ============================================================ */
function GiornalieriTable({
  items,
  onChanged,
}: {
  items: RicavoGiornaliero[];
  onChanged: () => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr className="text-xs uppercase tracking-wider text-muted-foreground">
            <th className="text-left px-4 py-2 font-medium">Data</th>
            <th className="text-right px-3 py-2 font-medium">IVA 10%</th>
            <th className="text-right px-3 py-2 font-medium">IVA 22%</th>
            <th className="text-right px-3 py-2 font-medium">Altri</th>
            <th className="text-right px-3 py-2 font-medium">Netto</th>
            <th className="text-center px-3 py-2 font-medium">Source</th>
            <th className="w-10"></th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <GiornoRow key={r.data} row={r} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GiornoRow({
  row,
  onChanged,
}: {
  row: RicavoGiornaliero;
  onChanged: () => void;
}) {
  const [iva10, setIva10] = useState(String(row.fatturato_iva10 || ""));
  const [iva22, setIva22] = useState(String(row.fatturato_iva22 || ""));
  const [altri, setAltri] = useState(String(row.altri_ricavi_noiva || ""));
  const [savingField, setSavingField] = useState<string | null>(null);
  const [savedField, setSavedField] = useState<string | null>(null);

  useEffect(() => {
    setIva10(String(row.fatturato_iva10 || ""));
    setIva22(String(row.fatturato_iva22 || ""));
    setAltri(String(row.altri_ricavi_noiva || ""));
  }, [row.fatturato_iva10, row.fatturato_iva22, row.altri_ricavi_noiva]);

  const parsedIva10 = parseFloat(iva10.replace(",", ".")) || 0;
  const parsedIva22 = parseFloat(iva22.replace(",", ".")) || 0;
  const parsedAltri = parseFloat(altri.replace(",", ".")) || 0;
  const netto = parsedIva10 / 1.10 + parsedIva22 / 1.22 + parsedAltri;

  async function postValue(field: "iva10" | "iva22" | "altri", value: number) {
    const payload = {
      data: row.data,
      fatturato_iva10: field === "iva10" ? value : row.fatturato_iva10,
      fatturato_iva22: field === "iva22" ? value : row.fatturato_iva22,
      altri_ricavi_noiva: field === "altri" ? value : row.altri_ricavi_noiva,
    };
    const res = await fetch("/api/ricavi/giornalieri", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error();
  }

  async function save(field: "iva10" | "iva22" | "altri", value: number) {
    const original = field === "iva10" ? row.fatturato_iva10
                   : field === "iva22" ? row.fatturato_iva22
                   : row.altri_ricavi_noiva;
    if (Math.abs(value - original) < 0.001) return;

    setSavingField(field);
    try {
      await postValue(field, value);
      setSavedField(field);
      setTimeout(() => setSavedField(null), 800);
      toast.success(`Salvato ${formatData(row.data)}`, {
        action: {
          label: "Annulla",
          onClick: async () => {
            try {
              await postValue(field, original);
              toast.success("Modifica annullata");
              onChanged();
            } catch {
              toast.error("Impossibile annullare");
            }
          },
        },
      });
      onChanged();
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSavingField(null);
    }
  }

  async function onDelete() {
    if (!confirm(`Eliminare i ricavi del ${formatData(row.data)}?`)) return;
    try {
      const res = await fetch(`/api/ricavi/giornalieri?data=${encodeURIComponent(row.data)}`, {
        method: "DELETE",
      });
      if (!res.ok) throw new Error();
      toast.success("Riga eliminata");
      onChanged();
    } catch {
      toast.error("Errore nell'eliminazione");
    }
  }

  const conf = SOURCE_LABEL[row.source] ?? SOURCE_LABEL.manuale;

  return (
    <tr className="border-t border-border hover:bg-muted/20 transition-colors">
      <td className="px-4 py-1.5 text-sm font-medium whitespace-nowrap">
        {formatData(row.data)}
      </td>
      <CellInput
        value={iva10}
        setValue={setIva10}
        onSave={(v) => save("iva10", v)}
        saving={savingField === "iva10"}
        saved={savedField === "iva10"}
      />
      <CellInput
        value={iva22}
        setValue={setIva22}
        onSave={(v) => save("iva22", v)}
        saving={savingField === "iva22"}
        saved={savedField === "iva22"}
      />
      <CellInput
        value={altri}
        setValue={setAltri}
        onSave={(v) => save("altri", v)}
        saving={savingField === "altri"}
        saved={savedField === "altri"}
      />
      <td className="px-3 py-1.5 text-right font-semibold tabular-nums text-primary">
        {netto > 0 ? formatEuro(netto) : "—"}
      </td>
      <td className="px-3 py-1.5 text-center">
        <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${conf.color}`}>
          {conf.label}
        </span>
      </td>
      <td className="px-2 py-1.5">
        <Button variant="ghost" size="sm" onClick={onDelete}
                className="size-7 p-0 text-muted-foreground hover:text-destructive">
          <Trash2 className="size-3.5" />
        </Button>
      </td>
    </tr>
  );
}

function CellInput({
  value, setValue, onSave, saving, saved,
}: {
  value: string;
  setValue: (v: string) => void;
  onSave: (v: number) => void;
  saving: boolean;
  saved: boolean;
}) {
  return (
    <td className="px-1 py-0.5">
      <input
        type="number"
        step="0.01"
        min="0"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => onSave(parseFloat(value.replace(",", ".")) || 0)}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            e.preventDefault();
            (e.target as HTMLInputElement).blur();
          }
        }}
        placeholder="0"
        className={`w-full h-7 px-2 text-right tabular-nums rounded border bg-transparent outline-none transition-colors ${
          saved
            ? "border-emerald-500 bg-emerald-500/10"
            : saving
            ? "border-sky-500 bg-sky-500/5"
            : "border-transparent hover:border-input focus:border-primary focus:bg-background"
        }`}
      />
    </td>
  );
}

/* ============================================================ */
/* Add giorno sheet                                              */
/* ============================================================ */
function AddGiornoSheet({
  onSaved,
  dataDa,
  dataA,
}: {
  onSaved: () => void;
  dataDa: string;
  dataA: string;
}) {
  const today = new Date().toISOString().slice(0, 10);
  const defaultDate = today >= dataDa && today <= dataA ? today : dataA;
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(defaultDate);
  const [iva10, setIva10] = useState("");
  const [iva22, setIva22] = useState("");
  const [altri, setAltri] = useState("");
  const [saving, setSaving] = useState(false);

  function reset() {
    setData(defaultDate);
    setIva10("");
    setIva22("");
    setAltri("");
  }

  async function handleSave() {
    setSaving(true);
    try {
      const payload = {
        data,
        fatturato_iva10: parseFloat(iva10.replace(",", ".")) || 0,
        fatturato_iva22: parseFloat(iva22.replace(",", ".")) || 0,
        altri_ricavi_noiva: parseFloat(altri.replace(",", ".")) || 0,
      };
      const res = await fetch("/api/ricavi/giornalieri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error();
      toast.success(`Ricavi ${formatData(data)} salvati`);
      reset();
      setOpen(false);
      onSaved();
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  const netto = (parseFloat(iva10.replace(",", ".")) || 0) / 1.10
              + (parseFloat(iva22.replace(",", ".")) || 0) / 1.22
              + (parseFloat(altri.replace(",", ".")) || 0);

  return (
    <Sheet open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
      <SheetTrigger
        render={
          <Button size="sm" className="gap-1.5">
            <Plus className="size-3.5" />
            Aggiungi giorno
          </Button>
        }
      />
      <SheetContent className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Aggiungi ricavi giornalieri</SheetTitle>
          <SheetDescription>
            Inserisci ricavi per un giorno. Se già esistono saranno sovrascritti.
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-4 px-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="data">Data</Label>
            <Input id="data" type="date" value={data} onChange={(e) => setData(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="iva10">Fatturato IVA 10% (€)</Label>
            <Input id="iva10" type="number" step="0.01" min="0" value={iva10}
                   onChange={(e) => setIva10(e.target.value)} placeholder="0,00" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="iva22">Fatturato IVA 22% (€)</Label>
            <Input id="iva22" type="number" step="0.01" min="0" value={iva22}
                   onChange={(e) => setIva22(e.target.value)} placeholder="0,00" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="altri">Altri ricavi (no IVA) (€)</Label>
            <Input id="altri" type="number" step="0.01" min="0" value={altri}
                   onChange={(e) => setAltri(e.target.value)} placeholder="0,00" />
          </div>
          <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
            <span className="text-muted-foreground">Fatturato netto: </span>
            <strong className="text-primary text-base">{netto > 0 ? formatEuro(netto) : "—"}</strong>
          </div>
        </div>
        <SheetFooter className="px-4">
          <Button variant="ghost" onClick={() => setOpen(false)}>Annulla</Button>
          <Button onClick={handleSave} disabled={saving || netto <= 0}>
            {saving ? "Salvataggio…" : "Salva"}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/* ============================================================ */
/* Ripartizione centri per mese                                  */
/* ============================================================ */
function RipartizioneCentriSection({ dataDa, dataA }: { dataDa: string; dataA: string }) {
  const meseStart = parseInt(dataDa.slice(5, 7), 10);
  const annoStart = parseInt(dataDa.slice(0, 4), 10);
  const meseEnd = parseInt(dataA.slice(5, 7), 10);
  const annoEnd = parseInt(dataA.slice(0, 4), 10);

  const mesi: { anno: number; mese: number; label: string }[] = [];
  for (let y = annoStart; y <= annoEnd; y++) {
    const mFrom = y === annoStart ? meseStart : 1;
    const mTo = y === annoEnd ? meseEnd : 12;
    for (let m = mFrom; m <= mTo; m++) {
      mesi.push({ anno: y, mese: m, label: `${MESI_NOMI_SHORT[m - 1]} ${y}` });
    }
  }

  const [meseSel, setMeseSel] = useState<string>(mesi[mesi.length - 1]?.label ?? "");
  const [values, setValues] = useState<RipartizioneCentri>({
    fatturato_food: 0, fatturato_beverage: 0, fatturato_alcolici: 0, fatturato_dolci: 0,
  });
  const [fattNetto, setFattNetto] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<"euro" | "perc">("euro");

  const meseObj = mesi.find((m) => m.label === meseSel);

  // Carica dati del mese selezionato
  useEffect(() => {
    if (!meseObj) return;
    let cancelled = false;
    setLoading(true);

    Promise.all([
      fetch(`/api/margini/fatturato-centri?anno=${meseObj.anno}&mese=${meseObj.mese}`)
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch(`/api/ricavi/giornalieri?${new URLSearchParams({
        data_da: `${meseObj.anno}-${String(meseObj.mese).padStart(2, "0")}-01`,
        data_a: `${meseObj.anno}-${String(meseObj.mese).padStart(2, "0")}-${new Date(meseObj.anno, meseObj.mese, 0).getDate()}`,
      })}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]).then(([splitData, ricaviData]: [Partial<RipartizioneCentri> | null, RicaviGiornalieriResponse | null]) => {
      if (cancelled) return;
      setValues({
        fatturato_food: splitData?.fatturato_food ?? 0,
        fatturato_beverage: splitData?.fatturato_beverage ?? 0,
        fatturato_alcolici: splitData?.fatturato_alcolici ?? 0,
        fatturato_dolci: splitData?.fatturato_dolci ?? 0,
      });
      setFattNetto(ricaviData?.totale_netto ?? 0);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [meseObj?.anno, meseObj?.mese]); // eslint-disable-line react-hooks/exhaustive-deps

  const totale = values.fatturato_food + values.fatturato_beverage
               + values.fatturato_alcolici + values.fatturato_dolci;
  const target = mode === "euro" ? fattNetto : 100;
  const totaleDisplay = mode === "euro"
    ? totale
    : fattNetto > 0 ? (totale / fattNetto) * 100 : 0;
  const valid = Math.abs(totale - (mode === "euro" ? fattNetto : fattNetto)) < 1;

  function update(key: keyof RipartizioneCentri, raw: string) {
    let v = parseFloat(raw.replace(",", ".")) || 0;
    if (mode === "perc") v = (v / 100) * fattNetto;
    setValues((prev) => ({ ...prev, [key]: v }));
  }

  async function handleSave() {
    if (!meseObj) return;
    setSaving(true);
    try {
      const res = await fetch("/api/margini/fatturato-centri", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anno: meseObj.anno, mese: meseObj.mese, ...values }),
      });
      if (!res.ok) throw new Error();
      toast.success(`Ripartizione ${meseSel} salvata`);
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  const centri: { key: keyof RipartizioneCentri; label: string; icon: string; color: string }[] = [
    { key: "fatturato_food", label: "FOOD", icon: "🍖", color: "border-orange-500/40" },
    { key: "fatturato_beverage", label: "BEVERAGE", icon: "☕", color: "border-sky-500/40" },
    { key: "fatturato_alcolici", label: "ALCOLICI", icon: "🍷", color: "border-purple-500/40" },
    { key: "fatturato_dolci", label: "DOLCI", icon: "🍰", color: "border-pink-500/40" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">Mese</Label>
          <select
            value={meseSel}
            onChange={(e) => setMeseSel(e.target.value)}
            className="rounded border border-input bg-background px-2 py-1 text-sm"
          >
            {mesi.map((m) => (
              <option key={m.label} value={m.label}>{m.label}</option>
            ))}
          </select>
        </div>
        <div className="flex rounded-md border border-input overflow-hidden">
          <button
            onClick={() => setMode("euro")}
            className={`px-3 py-1 text-xs font-medium ${mode === "euro" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >€ Valore</button>
          <button
            onClick={() => setMode("perc")}
            disabled={fattNetto <= 0}
            className={`px-3 py-1 text-xs font-medium border-l border-input disabled:opacity-50 ${mode === "perc" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >% Percentuale</button>
        </div>
        <div className="ml-auto text-xs text-muted-foreground">
          Fatturato netto {meseSel}: <strong className="text-foreground">{formatEuro(fattNetto)}</strong>
        </div>
      </div>

      {loading ? (
        <div className="py-8 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {centri.map((c) => {
              const raw = values[c.key];
              const displayVal = mode === "euro" ? raw : (fattNetto > 0 ? (raw / fattNetto) * 100 : 0);
              return (
                <div key={c.key} className={`rounded-md border p-3 ${c.color}`}>
                  <Label className="text-xs flex items-center gap-1">
                    <span>{c.icon}</span> {c.label}
                  </Label>
                  <div className="mt-1.5 flex items-center gap-1">
                    <Input
                      type="number"
                      step={mode === "euro" ? "1" : "0.1"}
                      min="0"
                      max={mode === "perc" ? "100" : undefined}
                      value={displayVal === 0 ? "" : displayVal.toFixed(mode === "euro" ? 0 : 1)}
                      onChange={(e) => update(c.key, e.target.value)}
                      placeholder="0"
                      className="text-right tabular-nums h-8"
                    />
                    <span className="text-xs text-muted-foreground">{mode === "euro" ? "€" : "%"}</span>
                  </div>
                  {mode === "euro" && fattNetto > 0 && (
                    <p className="text-[10px] text-muted-foreground mt-1">
                      {((raw / fattNetto) * 100).toFixed(1)}% del netto
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between rounded-md border border-border bg-muted/20 p-3">
            <div className="text-sm">
              <span className="text-muted-foreground">Totale: </span>
              <strong className={valid && totale > 0 ? "text-emerald-600" : totale > 0 ? "text-rose-600" : ""}>
                {mode === "euro"
                  ? `${formatEuro(totaleDisplay)} / ${formatEuro(target)}`
                  : `${totaleDisplay.toFixed(1)}% / 100,0%`}
              </strong>
              {totale > 0 && (
                <span className="ml-2">{valid ? "✅" : "❌ Non corrisponde al fatturato"}</span>
              )}
            </div>
            <Button size="sm" disabled={saving || fattNetto <= 0} onClick={handleSave}>
              {saving ? "Salvataggio…" : `Salva ${meseSel}`}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
