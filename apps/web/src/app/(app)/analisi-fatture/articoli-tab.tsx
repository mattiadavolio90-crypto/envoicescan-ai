"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";
import * as XLSX from "xlsx";
import { type ArticoloAggregato, type RigaFattura } from "@/lib/fatture";
import { Input } from "@/components/ui/input";
import { categoriaIcon, formatData, formatEuro } from "./periodi";

type Props = {
  articoli: ArticoloAggregato[];
  categorie: string[];
  fornitori: string[];
  filtri: {
    data_da?: string;
    data_a?: string;
    tipo_prodotti?: string;
    search?: string;
    fornitore?: string;
    categoria?: string;
    solo_nuovi?: boolean;
    solo_da_verificare?: boolean;
  };
};

const TIPO_OPTIONS = [
  { key: "tutti", label: "Tutti" },
  { key: "food_beverage", label: "Food & Beverage" },
  { key: "spese_generali", label: "Spese Generali" },
];

export function ArticoliTab({ articoli, categorie, fornitori, filtri }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function setParam(updates: Record<string, string | undefined>) {
    const params = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === "") params.delete(k);
      else params.set(k, v);
    }
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  function toggleExpand(desc: string) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(desc)) n.delete(desc);
      else n.add(desc);
      return n;
    });
  }

  function exportXls() {
    const data = articoli.map((a) => ({
      Categoria: a.categoria ?? "",
      Descrizione: a.descrizione,
      Fornitore: a.fornitore_principale,
      "Altri fornitori": a.altri_fornitori.join("; "),
      "Ultimo acquisto": a.ultimo_acquisto ?? "",
      "Quantità": a.quantita_totale,
      UM: a.unita_misura ?? "",
      "Prezzo unit. medio": a.prezzo_unit_medio ?? "",
      "Trend prezzo %": a.prezzo_unit_trend_pct ?? "",
      "Totale speso": a.totale_speso,
      "N° acquisti": a.num_acquisti,
    }));
    const ws = XLSX.utils.json_to_sheet(data);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Articoli");
    XLSX.writeFile(wb, `articoli_${new Date().toISOString().slice(0, 10)}.xlsx`);
  }

  return (
    <div className={`space-y-3 ${pending ? "opacity-70" : ""}`}>
      {/* Sub-filtri */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {TIPO_OPTIONS.map((t) => (
            <button
              key={t.key}
              disabled={pending}
              onClick={() => setParam({ tipo: t.key === "tutti" ? undefined : t.key })}
              className={`px-2.5 py-1 text-xs font-medium rounded-md border transition-colors disabled:opacity-60 ${
                (filtri.tipo_prodotti ?? "tutti") === t.key
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-background border-input hover:bg-muted"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="relative w-56">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Cerca prodotto..."
            defaultValue={filtri.search ?? ""}
            onKeyDown={(e) => {
              if (e.key === "Enter")
                setParam({ search: (e.target as HTMLInputElement).value || undefined });
            }}
            onBlur={(e) => setParam({ search: e.target.value || undefined })}
            className="h-7 text-xs pl-7"
          />
        </div>

        <select
          value={filtri.fornitore ?? ""}
          onChange={(e) => setParam({ fornitore: e.target.value || undefined })}
          disabled={pending}
          className="h-7 text-xs rounded-md border border-input bg-background px-2 max-w-48"
        >
          <option value="">Tutti i fornitori</option>
          {fornitori.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>

        <select
          value={filtri.categoria ?? ""}
          onChange={(e) => setParam({ cat: e.target.value || undefined })}
          disabled={pending}
          className="h-7 text-xs rounded-md border border-input bg-background px-2 max-w-48"
        >
          <option value="">Tutte le categorie</option>
          {categorie.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filtri.solo_nuovi ?? false}
            onChange={(e) => setParam({ nuovi: e.target.checked ? "1" : undefined })}
          />
          <Sparkles className="size-3 text-amber-500" /> Solo nuovi
        </label>
        <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filtri.solo_da_verificare ?? false}
            onChange={(e) => setParam({ verifica: e.target.checked ? "1" : undefined })}
          />
          <AlertTriangle className="size-3 text-amber-500" /> Solo verifica categoria
        </label>

        <button
          onClick={exportXls}
          disabled={articoli.length === 0}
          className="ml-auto text-xs px-2.5 py-1 rounded-md border border-input bg-background hover:bg-muted font-medium disabled:opacity-50"
        >
          Esporta Excel
        </button>
      </div>

      {articoli.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          Nessun prodotto trovato con i filtri selezionati.
        </div>
      ) : (
        <div className="rounded-lg border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 border-b">
              <tr className="text-xs text-muted-foreground">
                <th className="w-6"></th>
                <th className="text-left px-3 py-2 font-medium">Categoria</th>
                <th className="text-left px-3 py-2 font-medium">Descrizione</th>
                <th className="text-left px-3 py-2 font-medium">Fornitore</th>
                <th className="text-left px-3 py-2 font-medium whitespace-nowrap">Ultimo acq.</th>
                <th className="text-right px-3 py-2 font-medium">Q.tà</th>
                <th className="text-right px-3 py-2 font-medium whitespace-nowrap">€ unit.</th>
                <th className="text-right px-3 py-2 font-medium">Totale</th>
                <th className="text-right px-3 py-2 font-medium">N°</th>
              </tr>
            </thead>
            <tbody>
              {articoli.map((a) => (
                <ArticoloRiga
                  key={a.descrizione}
                  articolo={a}
                  expanded={expanded.has(a.descrizione)}
                  onToggle={() => toggleExpand(a.descrizione)}
                  categorie={categorie}
                  filtri={filtri}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ArticoloRiga({
  articolo,
  expanded,
  onToggle,
  categorie,
  filtri,
}: {
  articolo: ArticoloAggregato;
  expanded: boolean;
  onToggle: () => void;
  categorie: string[];
  filtri: { data_da?: string; data_a?: string };
}) {
  const [editingCat, setEditingCat] = useState(false);
  const [currentCat, setCurrentCat] = useState(articolo.categoria ?? "");
  const [saving, setSaving] = useState(false);

  async function saveCategoria(newCat: string) {
    if (!newCat || newCat === currentCat) {
      setEditingCat(false);
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/fatture/categoria-batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          descrizione: articolo.descrizione,
          nuova_categoria: newCat,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setCurrentCat(newCat);
        toast.success(`Categoria aggiornata · ${data.righe_aggiornate} righe`);
      } else {
        toast.error(data.error ?? "Errore aggiornamento");
      }
    } catch {
      toast.error("Errore di rete");
    } finally {
      setSaving(false);
      setEditingCat(false);
    }
  }

  const icon = categoriaIcon(currentCat);
  const trendPct = articolo.prezzo_unit_trend_pct;

  return (
    <>
      <tr
        className={`border-b hover:bg-muted/30 ${articolo.is_nuovo ? "bg-amber-50/30" : ""}`}
      >
        <td className="px-1 align-top pt-2.5">
          <button onClick={onToggle} className="text-muted-foreground hover:text-foreground">
            {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
        </td>
        <td className="px-3 py-2">
          {editingCat ? (
            <select
              value={currentCat}
              disabled={saving}
              autoFocus
              onChange={(e) => saveCategoria(e.target.value)}
              onBlur={() => setEditingCat(false)}
              className="h-6 text-xs rounded border border-input bg-background px-1 max-w-44"
            >
              {categorie.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          ) : (
            <button
              onClick={() => setEditingCat(true)}
              className="text-xs inline-flex items-center gap-1.5 hover:text-primary hover:underline text-left"
            >
              <span className="text-base leading-none">{icon}</span>
              <span className="font-medium">
                {currentCat || <em className="text-muted-foreground">N/D</em>}
              </span>
              {saving && <Loader2 className="size-3 animate-spin" />}
            </button>
          )}
        </td>
        <td className="px-3 py-2 text-xs">
          <div className="flex items-center gap-1.5">
            <span className="font-medium truncate max-w-72" title={articolo.descrizione}>
              {articolo.descrizione}
            </span>
            {articolo.is_nuovo && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-semibold whitespace-nowrap">
                Nuovo
              </span>
            )}
            {articolo.needs_review && (
              <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-rose-100 text-rose-700 font-semibold inline-flex items-center gap-0.5 whitespace-nowrap">
                <AlertTriangle className="size-2.5" /> Verifica
              </span>
            )}
          </div>
        </td>
        <td className="px-3 py-2 text-xs">
          <span className="truncate inline-block max-w-32" title={articolo.fornitore_principale}>
            {articolo.fornitore_principale || <em className="text-muted-foreground">N/D</em>}
          </span>
          {articolo.altri_fornitori.length > 0 && (
            <span
              className="ml-1 text-[10px] text-muted-foreground bg-muted rounded px-1"
              title={articolo.altri_fornitori.join(", ")}
            >
              +{articolo.altri_fornitori.length}
            </span>
          )}
        </td>
        <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
          {formatData(articolo.ultimo_acquisto)}
        </td>
        <td className="px-3 py-2 text-xs text-right tabular-nums">
          {articolo.quantita_totale > 0
            ? `${articolo.quantita_totale.toLocaleString("it-IT", { maximumFractionDigits: 1 })} ${articolo.unita_misura ?? ""}`
            : "—"}
        </td>
        <td className="px-3 py-2 text-xs text-right tabular-nums whitespace-nowrap">
          {articolo.prezzo_unit_medio != null ? (
            <span className="inline-flex items-center gap-1">
              {formatEuro(articolo.prezzo_unit_medio, 2)}
              {trendPct !== null && Math.abs(trendPct) >= 1 && (
                <span
                  className={`text-[10px] font-semibold inline-flex items-center ${
                    trendPct > 0 ? "text-rose-600" : "text-emerald-600"
                  }`}
                  title={`Variazione vs periodo precedente: ${trendPct > 0 ? "+" : ""}${trendPct}%`}
                >
                  {trendPct > 0 ? (
                    <ArrowUp className="size-2.5" />
                  ) : (
                    <ArrowDown className="size-2.5" />
                  )}
                  {Math.abs(trendPct).toFixed(0)}%
                </span>
              )}
            </span>
          ) : (
            "—"
          )}
        </td>
        <td className="px-3 py-2 text-xs text-right font-semibold tabular-nums">
          {formatEuro(articolo.totale_speso)}
        </td>
        <td className="px-3 py-2 text-xs text-right text-muted-foreground">
          {articolo.num_acquisti}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-muted/20 border-b">
          <td></td>
          <td colSpan={8} className="px-3 py-2">
            <RigheArticolo
              descrizione={articolo.descrizione}
              dataDa={filtri.data_da}
              dataA={filtri.data_a}
            />
          </td>
        </tr>
      )}
    </>
  );
}

function RigheArticolo({
  descrizione,
  dataDa,
  dataA,
}: {
  descrizione: string;
  dataDa?: string;
  dataA?: string;
}) {
  const [righe, setRighe] = useState<RigaFattura[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ descrizione });
    if (dataDa) params.set("data_da", dataDa);
    if (dataA) params.set("data_a", dataA);
    fetch(`/api/fatture/righe-articolo?${params}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (!cancelled) setRighe(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [descrizione, dataDa, dataA]);

  if (loading) {
    return (
      <p className="text-xs text-muted-foreground inline-flex items-center gap-1.5">
        <Loader2 className="size-3 animate-spin" />
        Caricamento righe...
      </p>
    );
  }

  if (!righe || righe.length === 0) {
    return <p className="text-xs text-muted-foreground">Nessuna riga da mostrare.</p>;
  }

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted-foreground border-b">
          <th className="text-left py-1 font-medium">Data</th>
          <th className="text-left py-1 font-medium">Fornitore</th>
          <th className="text-left py-1 font-medium">Fattura</th>
          <th className="text-right py-1 font-medium">Q.tà</th>
          <th className="text-right py-1 font-medium">€ unit.</th>
          <th className="text-right py-1 font-medium">Totale</th>
        </tr>
      </thead>
      <tbody>
        {righe.map((r) => (
          <tr key={r.id} className="border-b last:border-0">
            <td className="py-1 text-muted-foreground">{formatData(r.data_documento)}</td>
            <td className="py-1">{r.fornitore}</td>
            <td className="py-1 text-muted-foreground truncate max-w-40" title={r.file_origine}>
              {r.file_origine}
            </td>
            <td className="py-1 text-right tabular-nums">
              {r.quantita ?? "—"} {r.unita_misura ?? ""}
            </td>
            <td className="py-1 text-right tabular-nums">
              {r.prezzo_unitario != null ? formatEuro(r.prezzo_unitario, 2) : "—"}
            </td>
            <td className="py-1 text-right tabular-nums font-medium">
              {r.totale_riga != null ? formatEuro(r.totale_riga, 2) : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
