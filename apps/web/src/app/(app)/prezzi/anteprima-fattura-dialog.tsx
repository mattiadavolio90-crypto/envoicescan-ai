"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

type RigaFattura = {
  numero_riga: number;
  descrizione: string;
  quantita: number | null;
  unita_misura: string | null;
  prezzo_unitario: number | null;
  iva_percentuale: number | null;
  totale_riga: number | null;
  categoria: string | null;
};

function fmtEuro(v: number | null | undefined): string {
  if (v == null) return "—";
  return `€ ${new Intl.NumberFormat("it-IT", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v)}`;
}

// Match della riga in evidenza: stessa logica del backend (UPPER+TRIM, prefisso).
function matchProdotto(descrizione: string, prodotto: string): boolean {
  const d = descrizione.trim().toUpperCase();
  const p = prodotto.trim().toUpperCase();
  if (!d || !p) return false;
  return d === p || d.startsWith(p.slice(0, 30));
}

export function AnteprimaFatturaDialog({
  fileOrigine,
  numeroDocumento,
  prodotto,
  open,
  onClose,
}: {
  fileOrigine: string | null;
  numeroDocumento?: string;
  prodotto: string;
  open: boolean;
  onClose: () => void;
}) {
  const [righe, setRighe] = useState<RigaFattura[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !fileOrigine) return;
    let attivo = true;
    setLoading(true);
    setRighe([]);
    (async () => {
      try {
        const res = await fetch(
          `/api/scadenziario/anteprima?file_origine=${encodeURIComponent(fileOrigine)}`,
        );
        if (!res.ok) throw new Error();
        const json = await res.json();
        if (attivo) setRighe(json.righe ?? []);
      } catch {
        if (attivo) toast.error("Errore nel caricamento della fattura");
      } finally {
        if (attivo) setLoading(false);
      }
    })();
    return () => {
      attivo = false;
    };
  }, [open, fileOrigine]);

  const totale = righe.reduce((s, r) => s + (r.totale_riga || 0), 0);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            Fattura {numeroDocumento ? `n° ${numeroDocumento}` : ""}
          </DialogTitle>
          <DialogDescription>
            La riga di <span className="font-medium text-foreground">{prodotto}</span> è evidenziata.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border overflow-hidden">
          {loading ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : righe.length === 0 ? (
            <div className="px-4 py-8 text-center text-sm text-muted-foreground">Nessuna riga trovata.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-3 py-2 text-muted-foreground font-medium">Descrizione</th>
                    <th className="text-right px-3 py-2 text-muted-foreground font-medium">Qtà</th>
                    <th className="text-left px-3 py-2 text-muted-foreground font-medium">UM</th>
                    <th className="text-right px-3 py-2 text-muted-foreground font-medium">Prezzo</th>
                    <th className="text-right px-3 py-2 text-muted-foreground font-medium">IVA%</th>
                    <th className="text-right px-3 py-2 text-muted-foreground font-medium">Totale</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {righe.map((r, i) => {
                    const evid = matchProdotto(r.descrizione, prodotto);
                    return (
                      <tr
                        key={i}
                        className={evid ? "bg-amber-100/60 dark:bg-amber-500/15" : "hover:bg-muted/20"}
                      >
                        <td className="px-3 py-2 max-w-[260px]">
                          <p className={`truncate ${evid ? "font-semibold" : ""}`} title={r.descrizione}>
                            {r.descrizione}
                          </p>
                          {r.categoria && <p className="text-[10px] text-muted-foreground">{r.categoria}</p>}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{r.quantita ?? "—"}</td>
                        <td className="px-3 py-2 text-muted-foreground">{r.unita_misura ?? ""}</td>
                        <td className="px-3 py-2 text-right tabular-nums">
                          {r.prezzo_unitario != null ? `€${r.prezzo_unitario.toFixed(4)}` : "—"}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                          {r.iva_percentuale ?? "—"}%
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums font-medium">{fmtEuro(r.totale_riga)}</td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="border-t bg-muted/30">
                  <tr>
                    <td colSpan={5} className="px-3 py-2 text-right text-xs font-semibold text-muted-foreground">Totale</td>
                    <td className="px-3 py-2 text-right font-bold">{fmtEuro(totale)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
