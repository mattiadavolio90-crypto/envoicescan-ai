"use client";

import { useState, useMemo, useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, Save, Info } from "lucide-react";
import { toast } from "sonner";
import type { MarginiMese } from "@/lib/margini";

const MESI_SHORT = ["Gen","Feb","Mar","Apr","Mag","Giu","Lug","Ago","Set","Ott","Nov","Dic"];
const ANNO_CORRENTE = new Date().getFullYear();

type MeseState = Omit<MarginiMese, "mese">;

type Computed = {
  fatt_netto: number;
  costi_fb_tot: number;
  primo_margine: number;
  costi_spese_tot: number;
  costi_pers: number;
  mol: number;
};

type Totals = MeseState & Computed;

function emptyMese(): MeseState {
  return {
    fatturato_iva10: 0, fatturato_iva22: 0, altri_ricavi_noiva: 0,
    altri_costi_fb: 0, altri_costi_spese: 0, costo_dipendenti: 0,
    costo_personale_extra: 0, costi_fb_auto: 0, costi_spese_auto: 0,
  };
}

function computeMese(d: MeseState): Computed {
  const fatt_netto = d.fatturato_iva10 / 1.10 + d.fatturato_iva22 / 1.22 + d.altri_ricavi_noiva;
  const costi_fb_tot = d.costi_fb_auto + d.altri_costi_fb;
  const primo_margine = fatt_netto - costi_fb_tot;
  const costi_spese_tot = d.costi_spese_auto + d.altri_costi_spese;
  const costi_pers = d.costo_dipendenti + d.costo_personale_extra;
  const mol = primo_margine - costi_spese_tot - costi_pers;
  return { fatt_netto, costi_fb_tot, primo_margine, costi_spese_tot, costi_pers, mol };
}

function fmt(v: number): string {
  if (v === 0) return "—";
  return new Intl.NumberFormat("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Math.round(v));
}

function fmtEuro(v: number): string {
  if (v === 0) return "—";
  const sign = v < 0 ? "-" : "";
  return `${sign}€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(Math.abs(Math.round(v)))}`;
}

function fmtPct(v: number): string {
  return v === 0 ? "—" : `${v.toFixed(1)}%`;
}

function sumField(mesi: Record<number, MeseState>, key: keyof MeseState): number {
  return Object.values(mesi).reduce((acc, m) => acc + (m[key] as number), 0);
}

type RowDef =
  | { type: "input"; key: keyof MeseState; label: string }
  | { type: "auto"; key: keyof MeseState; label: string }
  | { type: "computed"; label: string; getValue: (c: Computed) => number; highlight: "blue" | "green" | "mol" };

const ROW_DEFS: RowDef[] = [
  { type: "input",    key: "fatturato_iva10",       label: "Ricavi IVA 10%" },
  { type: "input",    key: "fatturato_iva22",       label: "Ricavi IVA 22%" },
  { type: "input",    key: "altri_ricavi_noiva",    label: "Altri ricavi (no IVA)" },
  { type: "computed", label: "= Fatturato Netto",   getValue: c => c.fatt_netto,    highlight: "blue" },
  { type: "auto",     key: "costi_fb_auto",         label: "Costi F&B (Fatture)" },
  { type: "input",    key: "altri_costi_fb",        label: "Altri Costi F&B" },
  { type: "computed", label: "= Costi F&B Totali",  getValue: c => c.costi_fb_tot,  highlight: "blue" },
  { type: "computed", label: "= 1° Margine",        getValue: c => c.primo_margine, highlight: "green" },
  { type: "auto",     key: "costi_spese_auto",      label: "Spese Gen. (Fatture)" },
  { type: "input",    key: "altri_costi_spese",     label: "Altre Spese Generali" },
  { type: "input",    key: "costo_dipendenti",      label: "Costo Personale Lordo" },
  { type: "input",    key: "costo_personale_extra", label: "Costo Personale Extra" },
  { type: "computed", label: "= 2° Margine (MOL)",  getValue: c => c.mol,           highlight: "mol" },
];

const SEPARATOR_BEFORE = new Set([3, 7]);
const HL: Record<string, string> = {
  blue: "bg-sky-50 dark:bg-sky-950/30 font-semibold",
  green: "bg-emerald-50 dark:bg-emerald-950/20 font-semibold",
};

function molCls(v: number) {
  if (v > 0) return "bg-emerald-100 dark:bg-emerald-900/30 font-bold text-emerald-700 dark:text-emerald-400";
  if (v < 0) return "bg-rose-100 dark:bg-rose-900/30 font-bold text-rose-700 dark:text-rose-400";
  return "bg-muted font-bold";
}

type Props = { anno: number; mesi: MarginiMese[] };

export function CalcoloTab({ anno, mesi }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [, startNav] = useTransition();

  const initState = useMemo<Record<number, MeseState>>(() => {
    const s: Record<number, MeseState> = {};
    for (let m = 1; m <= 12; m++) {
      const found = mesi.find(x => x.mese === m);
      s[m] = found ? { ...found } : emptyMese();
    }
    return s;
  }, [mesi]);

  const [mesiState, setMesiState] = useState<Record<number, MeseState>>(initState);
  const [isDirty, setIsDirty] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  function updateMese(m: number, key: keyof MeseState, raw: string) {
    const val = raw === "" ? 0 : parseFloat(raw.replace(",", ".")) || 0;
    setMesiState(prev => ({ ...prev, [m]: { ...prev[m], [key]: val } }));
    setIsDirty(true);
  }

  function changeAnno(newAnno: number) {
    const params = new URLSearchParams(sp.toString());
    params.set("anno", String(newAnno));
    startNav(() => router.push(`${pathname}?${params.toString()}`));
  }

  async function handleSave() {
    setIsSaving(true);
    try {
      const body = {
        anno,
        mesi: Array.from({ length: 12 }, (_, i) => ({ mese: i + 1, ...mesiState[i + 1] })),
      };
      const res = await fetch("/api/margini", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      setIsDirty(false);
      toast.success("Dati salvati");
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setIsSaving(false);
    }
  }

  const computed = useMemo(() => {
    const c: Record<number, Computed> = {};
    for (let m = 1; m <= 12; m++) c[m] = computeMese(mesiState[m]);
    return c;
  }, [mesiState]);

  const totals = useMemo<Totals>(() => {
    const iva10 = sumField(mesiState, "fatturato_iva10");
    const iva22 = sumField(mesiState, "fatturato_iva22");
    const altri = sumField(mesiState, "altri_ricavi_noiva");
    const fatt_netto = iva10 / 1.10 + iva22 / 1.22 + altri;
    const fbAuto = sumField(mesiState, "costi_fb_auto");
    const altriFb = sumField(mesiState, "altri_costi_fb");
    const costi_fb_tot = fbAuto + altriFb;
    const primo_margine = fatt_netto - costi_fb_tot;
    const speseAuto = sumField(mesiState, "costi_spese_auto");
    const altreSpese = sumField(mesiState, "altri_costi_spese");
    const costi_spese_tot = speseAuto + altreSpese;
    const pers = sumField(mesiState, "costo_dipendenti");
    const extra = sumField(mesiState, "costo_personale_extra");
    const costi_pers = pers + extra;
    const mol = primo_margine - costi_spese_tot - costi_pers;
    return {
      fatturato_iva10: iva10, fatturato_iva22: iva22, altri_ricavi_noiva: altri,
      costi_fb_auto: fbAuto, altri_costi_fb: altriFb,
      costi_spese_auto: speseAuto, altri_costi_spese: altreSpese,
      costo_dipendenti: pers, costo_personale_extra: extra,
      fatt_netto, costi_fb_tot, primo_margine, costi_spese_tot, costi_pers, mol,
    };
  }, [mesiState]);

  function getTotForRow(row: RowDef): number {
    if (row.type === "computed") return row.getValue(totals);
    return totals[row.key as keyof Totals] as number;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => changeAnno(anno - 1)}
            className="size-7 flex items-center justify-center rounded border border-border hover:bg-muted transition-colors"
          >
            <ChevronLeft className="size-4" />
          </button>
          <span className="text-lg font-bold w-14 text-center">{anno}</span>
          <button
            onClick={() => changeAnno(anno + 1)}
            disabled={anno >= ANNO_CORRENTE}
            className="size-7 flex items-center justify-center rounded border border-border hover:bg-muted transition-colors disabled:opacity-40"
          >
            <ChevronRight className="size-4" />
          </button>
        </div>
        <button
          onClick={handleSave}
          disabled={isSaving || !isDirty}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Save className="size-3.5" />
          {isSaving ? "Salvataggio…" : "Salva Anno"}
        </button>
      </div>

      <div className="flex items-start gap-1.5 text-xs text-muted-foreground p-2 rounded-md bg-muted/40 border border-border/50">
        <Info className="size-3.5 mt-0.5 shrink-0" />
        <span>
          Inserisci i ricavi e i costi manuali. I campi con sfondo grigio (Costi da Fatture) sono calcolati
          automaticamente dalle fatture caricate. Le righe <span className="font-medium text-foreground">= </span>
          sono calcolate in tempo reale. Clicca <span className="font-medium text-foreground">Salva Anno</span> per salvare.
        </span>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-max text-xs border-collapse">
          <thead>
            <tr className="bg-muted/60">
              <th className="sticky left-0 z-10 bg-muted/80 text-left px-3 py-2 font-semibold border-r border-border min-w-[210px]">
                Voce
              </th>
              {MESI_SHORT.map(m => (
                <th key={m} className="text-center px-1 py-2 font-semibold border-r border-border min-w-[88px]">
                  {m}
                </th>
              ))}
              <th className="text-center px-2 py-2 font-semibold bg-muted min-w-[100px]">TOT ANNO</th>
            </tr>
          </thead>
          <tbody>
            {ROW_DEFS.map((row, ri) => (
              <tr
                key={ri}
                className={`border-t border-border ${SEPARATOR_BEFORE.has(ri) ? "border-t-2 border-t-border/60" : ""}`}
              >
                {/* Label */}
                <td
                  className={`sticky left-0 z-10 px-3 py-1.5 border-r border-border whitespace-nowrap ${
                    row.type === "computed"
                      ? row.highlight === "mol"
                        ? "bg-muted font-semibold"
                        : `${HL[row.highlight]} bg-clip-padding`
                      : row.type === "auto"
                      ? "bg-muted/30 text-muted-foreground"
                      : "bg-background"
                  }`}
                >
                  {row.label}
                </td>

                {/* Month cells */}
                {Array.from({ length: 12 }, (_, i) => i + 1).map(m => {
                  const c = computed[m];
                  if (row.type === "computed") {
                    const v = row.getValue(c);
                    const cls = row.highlight === "mol" ? molCls(v) : HL[row.highlight];
                    return (
                      <td key={m} className={`text-right px-2 py-1.5 border-r border-border ${cls}`}>
                        {fmt(v)}
                      </td>
                    );
                  }
                  if (row.type === "auto") {
                    return (
                      <td key={m} className="text-right px-2 py-1.5 border-r border-border bg-muted/20 text-muted-foreground">
                        {fmt(mesiState[m][row.key] as number)}
                      </td>
                    );
                  }
                  const val = mesiState[m][row.key] as number;
                  return (
                    <td key={m} className="border-r border-border p-0">
                      <input
                        type="number"
                        step="1"
                        min="0"
                        value={val === 0 ? "" : val}
                        placeholder="0"
                        onChange={e => updateMese(m, row.key, e.target.value)}
                        className="w-full h-full px-2 py-1.5 text-right bg-transparent border-0 outline-none focus:bg-sky-50 dark:focus:bg-sky-950/20 focus:ring-inset focus:ring-1 focus:ring-sky-400 text-xs"
                      />
                    </td>
                  );
                })}

                {/* Total */}
                {(() => {
                  const tv = getTotForRow(row);
                  const cls =
                    row.type === "computed"
                      ? row.highlight === "mol"
                        ? molCls(tv)
                        : HL[row.highlight]
                      : row.type === "auto"
                      ? "text-muted-foreground"
                      : "";
                  return (
                    <td className={`text-right px-2 py-1.5 font-medium bg-muted/40 ${cls}`}>
                      {fmt(tv)}
                    </td>
                  );
                })()}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* KPI */}
      {(totals.fatt_netto !== 0 || totals.mol !== 0) && (
        <KpiRow totals={totals} />
      )}
    </div>
  );
}

function KpiRow({ totals }: { totals: Totals }) {
  const fn = totals.fatt_netto > 0 ? totals.fatt_netto : 1;
  const fc_pct = totals.fatt_netto > 0 ? totals.costi_fb_tot / fn * 100 : 0;
  const pm_pct = totals.fatt_netto > 0 ? totals.primo_margine / fn * 100 : 0;
  const mol_pct = totals.fatt_netto > 0 ? totals.mol / fn * 100 : 0;

  const kpis = [
    { label: "Fatturato Netto", value: fmtEuro(totals.fatt_netto), color: "" },
    {
      label: "Food Cost %", value: fmtPct(fc_pct),
      color: fc_pct > 35 ? "text-rose-600" : fc_pct > 30 ? "text-amber-600" : "text-emerald-600",
    },
    {
      label: "1° Margine %", value: fmtPct(pm_pct),
      color: pm_pct < 60 ? "text-rose-600" : pm_pct < 67 ? "text-amber-600" : "text-emerald-600",
    },
    {
      label: "2° Margine (MOL)", value: fmtEuro(totals.mol),
      color: totals.mol >= 0 ? "text-emerald-600" : "text-rose-600",
    },
    {
      label: "MOL %", value: fmtPct(mol_pct),
      color: mol_pct < 5 ? "text-rose-600" : mol_pct < 10 ? "text-amber-600" : "text-emerald-600",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {kpis.map(k => (
        <div key={k.label} className="rounded-md border border-border p-3 bg-card">
          <p className="text-xs text-muted-foreground">{k.label}</p>
          <p className={`text-base font-bold mt-0.5 ${k.color}`}>{k.value}</p>
        </div>
      ))}
    </div>
  );
}
