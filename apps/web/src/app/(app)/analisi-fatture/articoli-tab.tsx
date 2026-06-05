"use client";

import { memo, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronDown,
  ChevronRight,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";
// xlsx importato lazy in exportXls (libreria pesante, serve solo all'export)
import { type ArticoloAggregato, type RigaFattura } from "@/lib/fatture";
import { Input } from "@/components/ui/input";
import { categoriaIcon, formatData, formatEuro } from "./periodi";

type Props = {
  articoli: ArticoloAggregato[];
  categorie: string[];
  soloNuovi: boolean;
  soloVerifica: boolean;
  filtri: {
    data_da?: string;
    data_a?: string;
    tipo_prodotti?: string;
  };
};

type SortKey =
  | "descrizione"
  | "categoria"
  | "fornitore"
  | "ultimo_acquisto"
  | "quantita_totale"
  | "prezzo_unit_medio"
  | "totale_speso"
  | "num_acquisti";

type SortDir = "asc" | "desc" | null;

const TIPO_OPTIONS = [
  { key: "tutti", label: "Tutti" },
  { key: "food_beverage", label: "Food & Beverage" },
  { key: "spese_generali", label: "Spese Generali" },
];

const SPESE_GENERALI_SET = new Set([
  "SERVIZI E CONSULENZE",
  "UTENZE E LOCALI",
  "MANUTENZIONE E ATTREZZATURE",
  "MATERIALE DI CONSUMO",
]);

const PAGE_SIZE = 100;

function compareValues(a: unknown, b: unknown, dir: SortDir): number {
  if (dir === null) return 0;
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  let cmp: number;
  if (typeof a === "number" && typeof b === "number") cmp = a - b;
  else cmp = String(a).localeCompare(String(b), "it", { sensitivity: "base" });
  return dir === "asc" ? cmp : -cmp;
}

function SortableHeader({
  label,
  sortKey,
  current,
  align,
  onClick,
}: {
  label: string;
  sortKey: SortKey;
  current: { key: SortKey | null; dir: SortDir };
  align?: "left" | "right";
  onClick: (k: SortKey) => void;
}) {
  const isActive = current.key === sortKey && current.dir !== null;
  const Icon = isActive ? (current.dir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;
  return (
    <button
      onClick={() => onClick(sortKey)}
      className={`group inline-flex items-center gap-1 hover:text-foreground transition-colors ${
        align === "right" ? "justify-end" : ""
      }`}
    >
      <span>{label}</span>
      <Icon
        className={`size-3 ${
          isActive ? "text-primary" : "text-muted-foreground/40 group-hover:text-muted-foreground"
        }`}
      />
    </button>
  );
}

export function ArticoliTab({
  articoli,
  categorie,
  soloNuovi,
  soloVerifica,
  filtri,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  // Filtri CLIENT-SIDE (no round-trip server)
  const [search, setSearch] = useState("");
  const [fornitoreFilter, setFornitoreFilter] = useState("");
  const [categoriaFilter, setCategoriaFilter] = useState("");

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<{ key: SortKey | null; dir: SortDir }>({
    key: "totale_speso",
    dir: "desc",
  });

  // Reset paginazione quando cambiano filtri client / URL
  useEffect(() => {
    setPage(1);
  }, [search, fornitoreFilter, categoriaFilter, soloNuovi, soloVerifica, sort]);

  // Reset dropdown selection quando cambia tipo (il valore scelto potrebbe non esistere nel nuovo set)
  useEffect(() => {
    setFornitoreFilter("");
    setCategoriaFilter("");
  }, [filtri.tipo_prodotti]);

  // Fornitori disponibili derivati dagli articoli già filtrati per tipo (server-side)
  const fornitoriFiltered = useMemo(() => {
    const set = new Set<string>();
    for (const a of articoli) {
      if (a.fornitore_principale) set.add(a.fornitore_principale);
    }
    return [...set].sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" }));
  }, [articoli]);

  // Categorie disponibili filtrate per tipo
  const categorieFiltered = useMemo(() => {
    const tipo = filtri.tipo_prodotti;
    if (tipo === "food_beverage") return categorie.filter((c) => !SPESE_GENERALI_SET.has(c.toUpperCase()));
    if (tipo === "spese_generali") return categorie.filter((c) => SPESE_GENERALI_SET.has(c.toUpperCase()));
    return categorie;
  }, [categorie, filtri.tipo_prodotti]);

  function cycleSort(k: SortKey) {
    setSort((prev) => {
      if (prev.key !== k) return { key: k, dir: "asc" };
      if (prev.dir === "asc") return { key: k, dir: "desc" };
      if (prev.dir === "desc") return { key: null, dir: null };
      return { key: k, dir: "asc" };
    });
  }

  function setUrlParam(updates: Record<string, string | undefined>) {
    const params = new URLSearchParams(sp.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === undefined || v === "") params.delete(k);
      else params.set(k, v);
    }
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  // Applico filtri client-side
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    return articoli.filter((a) => {
      if (fornitoreFilter && a.fornitore_principale !== fornitoreFilter) {
        if (!a.altri_fornitori.includes(fornitoreFilter)) return false;
      }
      if (categoriaFilter && a.categoria !== categoriaFilter) return false;
      if (soloNuovi && !a.is_nuovo) return false;
      if (soloVerifica && !a.needs_review) return false;
      if (term) {
        const inDesc = a.descrizione.toLowerCase().includes(term);
        const inForn = a.fornitore_principale.toLowerCase().includes(term);
        const inCat = (a.categoria ?? "").toLowerCase().includes(term);
        if (!inDesc && !inForn && !inCat) return false;
      }
      return true;
    });
  }, [articoli, search, fornitoreFilter, categoriaFilter, soloNuovi, soloVerifica]);

  const sorted = useMemo(() => {
    if (!sort.key || !sort.dir) return filtered;
    const k = sort.key;
    const d = sort.dir;
    return [...filtered].sort((a, b) => {
      const va = k === "fornitore" ? a.fornitore_principale : (a as Record<string, unknown>)[k];
      const vb = k === "fornitore" ? b.fornitore_principale : (b as Record<string, unknown>)[k];
      return compareValues(va, vb, d);
    });
  }, [filtered, sort]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const visible = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  function toggleExpand(desc: string) {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(desc)) n.delete(desc);
      else n.add(desc);
      return n;
    });
  }

  async function exportXls() {
    const XLSX = await import("xlsx");
    const data = sorted.map((a) => ({
      Descrizione: a.descrizione,
      Categoria: a.categoria ?? "",
      Fornitore: a.fornitore_principale,
      "Altri fornitori": a.altri_fornitori.join("; "),
      "Ultimo acquisto": a.ultimo_acquisto ?? "",
      Quantità: a.quantita_totale,
      UM: a.unita_misura ?? "",
      "€ medio": a.prezzo_unit_medio ?? "",
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
    <div className="space-y-3">
      {/* Sub-filtri */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1">
          {TIPO_OPTIONS.map((t) => (
            <button
              key={t.key}
              disabled={pending}
              onClick={() => setUrlParam({ tipo: t.key === "tutti" ? undefined : t.key })}
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
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-7 text-xs pl-7"
          />
        </div>

        <select
          value={fornitoreFilter}
          onChange={(e) => setFornitoreFilter(e.target.value)}
          className="h-7 text-xs rounded-md border border-input bg-background px-2 max-w-48"
        >
          <option value="">Tutti i fornitori</option>
          {fornitoriFiltered.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>

        <select
          value={categoriaFilter}
          onChange={(e) => setCategoriaFilter(e.target.value)}
          className="h-7 text-xs rounded-md border border-input bg-background px-2 max-w-48"
        >
          <option value="">Tutte le categorie</option>
          {categorieFiltered.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <button
          onClick={exportXls}
          disabled={sorted.length === 0}
          className="ml-auto text-xs px-2.5 py-1 rounded-md border border-input bg-background hover:bg-muted font-medium disabled:opacity-50"
        >
          Esporta Excel
        </button>
      </div>

      {/* Toggle: Nuovi / Solo verifica */}
      <div className={`flex items-center gap-2 ${pending ? "opacity-70" : ""}`}>
        <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer select-none px-3 py-1.5 rounded-md border border-sky-500/30 bg-sky-500/5">
          <input
            type="checkbox"
            checked={soloNuovi}
            onChange={(e) => setUrlParam({ nuovi: e.target.checked ? "1" : undefined })}
          />
          <Sparkles className="size-3.5 text-amber-500" />
          Nuovi caricati
        </label>
        <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer select-none px-3 py-1.5 rounded-md border border-sky-500/30 bg-sky-500/5">
          <input
            type="checkbox"
            checked={soloVerifica}
            onChange={(e) => setUrlParam({ verifica: e.target.checked ? "1" : undefined })}
          />
          <AlertTriangle className="size-3.5 text-amber-500" />
          Solo verifica categoria
        </label>
      </div>

      {/* Counter */}
      <div className="text-xs text-muted-foreground pt-2 border-t border-border/50">
        {sorted.length === articoli.length
          ? `${sorted.length} prodotti`
          : `${sorted.length} di ${articoli.length} prodotti`}
      </div>

      {sorted.length === 0 ? (
        <div className="text-center py-16 text-sm text-muted-foreground">
          Nessun prodotto trovato con i filtri selezionati.
        </div>
      ) : (
        <>
          <div className="rounded-lg border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 border-b">
                <tr className="text-xs text-muted-foreground">
                  <th className="w-6"></th>
                  <th className="text-left px-3 py-2 font-medium">
                    <SortableHeader label="Descrizione" sortKey="descrizione" current={sort} onClick={cycleSort} />
                  </th>
                  <th className="text-left px-3 py-2 font-medium">
                    <SortableHeader label="Categoria" sortKey="categoria" current={sort} onClick={cycleSort} />
                  </th>
                  <th className="text-left px-3 py-2 font-medium">
                    <SortableHeader label="Fornitore" sortKey="fornitore" current={sort} onClick={cycleSort} />
                  </th>
                  <th className="text-left px-3 py-2 font-medium whitespace-nowrap">
                    <SortableHeader label="Ultimo acq." sortKey="ultimo_acquisto" current={sort} onClick={cycleSort} />
                  </th>
                  <th className="text-right px-3 py-2 font-medium">
                    <SortableHeader label="Q.tà" sortKey="quantita_totale" current={sort} align="right" onClick={cycleSort} />
                  </th>
                  <th className="text-right px-3 py-2 font-medium whitespace-nowrap">
                    <SortableHeader label="€ medio" sortKey="prezzo_unit_medio" current={sort} align="right" onClick={cycleSort} />
                  </th>
                  <th className="text-right px-3 py-2 font-medium">
                    <SortableHeader label="Totale" sortKey="totale_speso" current={sort} align="right" onClick={cycleSort} />
                  </th>
                  <th className="text-right px-3 py-2 font-medium">
                    <SortableHeader label="N°" sortKey="num_acquisti" current={sort} align="right" onClick={cycleSort} />
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((a) => (
                  <ArticoloRiga
                    key={a.descrizione}
                    articolo={a}
                    expanded={expanded.has(a.descrizione)}
                    onToggle={() => toggleExpand(a.descrizione)}
                    categorie={categorie}
                    dataDa={filtri.data_da}
                    dataA={filtri.data_a}
                  />
                ))}
              </tbody>
            </table>
          </div>

          {/* Paginazione */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Pagina {safePage} di {totalPages} · {sorted.length.toLocaleString("it-IT")} prodotti
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
        </>
      )}
    </div>
  );
}

const ArticoloRiga = memo(function ArticoloRiga({
  articolo,
  expanded,
  onToggle,
  categorie,
  dataDa,
  dataA,
}: {
  articolo: ArticoloAggregato;
  expanded: boolean;
  onToggle: () => void;
  categorie: string[];
  dataDa?: string;
  dataA?: string;
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

  const fbCats = useMemo(
    () =>
      categorie
        .filter((c) => !SPESE_GENERALI_SET.has(c.toUpperCase()) && c !== "Da Classificare")
        .sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })),
    [categorie],
  );
  const sgCats = useMemo(
    () =>
      categorie
        .filter((c) => SPESE_GENERALI_SET.has(c.toUpperCase()))
        .sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })),
    [categorie],
  );
  const hasDaClassificare = categorie.includes("Da Classificare");

  return (
    <>
      <tr className="border-b hover:bg-sky-100/40 dark:hover:bg-sky-900/20 transition-colors">
        <td className="px-1 align-top pt-2.5">
          <button onClick={onToggle} className="text-muted-foreground hover:text-foreground">
            {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
          </button>
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
              {fbCats.length > 0 && (
                <optgroup label="🥗 Food & Beverage">
                  {fbCats.map((c) => (
                    <option key={c} value={c}>
                      {categoriaIcon(c)} {c}
                    </option>
                  ))}
                </optgroup>
              )}
              {sgCats.length > 0 && (
                <optgroup label="📊 Spese Generali">
                  {sgCats.map((c) => (
                    <option key={c} value={c}>
                      {categoriaIcon(c)} {c}
                    </option>
                  ))}
                </optgroup>
              )}
              {hasDaClassificare && (
                <option value="Da Classificare" style={{ color: "red" }}>
                  Da Classificare
                </option>
              )}
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
                  {trendPct > 0 ? <ArrowUp className="size-2.5" /> : <ArrowDown className="size-2.5" />}
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
        <td className="px-3 py-2 text-xs text-right text-muted-foreground">{articolo.num_acquisti}</td>
      </tr>
      {expanded && (
        <tr className="bg-muted/20 border-b">
          <td></td>
          <td colSpan={9} className="px-3 py-2">
            <RigheArticolo descrizione={articolo.descrizione} dataDa={dataDa} dataA={dataA} />
          </td>
        </tr>
      )}
    </>
  );
});

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

  const cutoffNuovo = Date.now() - 24 * 60 * 60 * 1000;

  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted-foreground border-b">
          <th className="text-left py-1 font-medium">Data</th>
          <th className="text-left py-1 font-medium">Fornitore</th>
          <th className="text-right py-1 font-medium">Q.tà</th>
          <th className="text-right py-1 font-medium">€ unit.</th>
          <th className="text-right py-1 font-medium">Totale</th>
          <th className="text-left py-1 font-medium whitespace-nowrap">N° fattura</th>
          <th className="text-left py-1 font-medium">File</th>
        </tr>
      </thead>
      <tbody>
        {righe.map((r) => {
          const isNuova =
            r.created_at && new Date(r.created_at).getTime() >= cutoffNuovo;
          return (
            <tr
              key={r.id}
              className="border-b last:border-0 hover:bg-sky-100/40 dark:hover:bg-sky-900/20 transition-colors"
            >
              <td className="py-1 text-muted-foreground">{formatData(r.data_documento)}</td>
              <td className="py-1">
                {r.fornitore}
                {isNuova && (
                  <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-semibold whitespace-nowrap">
                    Nuovo
                  </span>
                )}
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
              <td className="py-1 text-muted-foreground whitespace-nowrap">
                {r.numero_documento || <em className="opacity-50">—</em>}
              </td>
              <td className="py-1 text-muted-foreground truncate max-w-40" title={r.file_origine}>
                {r.file_origine}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
