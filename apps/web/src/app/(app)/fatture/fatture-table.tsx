"use client";

import { useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { AlertTriangle, ChevronLeft, ChevronRight } from "lucide-react";
import { type RigaFattura } from "@/lib/fatture";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Props = {
  righe: RigaFattura[];
  total: number;
  page: number;
  totalPages: number;
  categorie: string[];
};

function formatEur(v: number | null): string {
  if (v == null) return "—";
  return v.toLocaleString("it-IT", { style: "currency", currency: "EUR" });
}

function formatData(v: string | null): string {
  if (!v) return "—";
  const [y, m, d] = v.split("-");
  return `${d}/${m}/${y}`;
}

function CategoriaCell({
  riga,
  categorie,
}: {
  riga: RigaFattura;
  categorie: string[];
}) {
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState(riga.categoria ?? "");
  const [saving, setSaving] = useState(false);

  async function save(newCat: string) {
    if (!newCat || newCat === current) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/fatture/${riga.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ categoria: newCat }),
      });
      if (res.ok) {
        setCurrent(newCat);
      }
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }

  if (editing) {
    return (
      <select
        value={current}
        disabled={saving}
        onChange={(e) => save(e.target.value)}
        className="h-7 text-xs w-44 rounded border border-input bg-background px-2 focus:outline-none focus:ring-1 focus:ring-ring"
      >
        {categorie.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  }

  return (
    <button
      className="text-left text-xs hover:underline hover:text-primary transition-colors max-w-44 truncate block"
      onClick={() => setEditing(true)}
      title="Clicca per modificare la categoria"
    >
      {current || <span className="text-muted-foreground italic">N/D</span>}
    </button>
  );
}

export function FattureTable({ righe, total, page, totalPages, categorie }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  function goToPage(p: number) {
    const params = new URLSearchParams(sp.toString());
    params.set("page", String(p));
    router.push(`${pathname}?${params.toString()}`);
  }

  if (righe.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground text-sm">
        Nessuna riga trovata con i filtri selezionati.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="rounded-lg border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-24">Data</TableHead>
              <TableHead className="w-40">Fornitore</TableHead>
              <TableHead>Descrizione</TableHead>
              <TableHead className="w-44">Categoria</TableHead>
              <TableHead className="text-right w-24">Q.tà</TableHead>
              <TableHead className="text-right w-28">Totale</TableHead>
              <TableHead className="w-8"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {righe.map((r) => (
              <TableRow key={r.id} className={r.needs_review ? "bg-amber-50/40" : undefined}>
                <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                  {formatData(r.data_documento)}
                </TableCell>
                <TableCell className="text-xs font-medium max-w-40 truncate" title={r.fornitore}>
                  {r.fornitore}
                </TableCell>
                <TableCell className="text-xs max-w-64 truncate" title={r.descrizione}>
                  {r.descrizione}
                </TableCell>
                <TableCell>
                  <CategoriaCell riga={r} categorie={categorie} />
                </TableCell>
                <TableCell className="text-right text-xs text-muted-foreground">
                  {r.quantita != null ? r.quantita.toLocaleString("it-IT") : "—"}
                  {r.unita_misura ? ` ${r.unita_misura}` : ""}
                </TableCell>
                <TableCell className="text-right text-xs font-medium tabular-nums">
                  {formatEur(r.totale_riga)}
                </TableCell>
                <TableCell>
                  {r.needs_review && (
                    <AlertTriangle className="size-3.5 text-amber-500" title="Da verificare" />
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Paginazione */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Pagina {page} di {totalPages} · {total.toLocaleString("it-IT")} righe totali
          </span>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => goToPage(page - 1)}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => goToPage(page + 1)}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
