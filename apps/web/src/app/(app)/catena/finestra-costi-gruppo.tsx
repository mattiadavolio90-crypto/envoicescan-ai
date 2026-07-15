"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, CopyPlus, FileText, PencilLine } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

const MESI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

type Quota = {
  ristorante_id: string;
  sede: string;
  quota_perc: number;
  quota_importo: number;
};

type Costo = {
  id: string;
  origine: "fattura" | "manuale";
  file_origine: string | null;
  fornitore: string | null;
  descrizione: string;
  importo_totale: number;
  tipo: "generale" | "fb";
  regola: "equa" | "percentuali";
  quote: Quota[];
};

type CostiComuniRes = {
  anno: number;
  mese: number;
  costi: Costo[];
  totale: number;
};

export function FinestraCostiGruppo({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;
  const [mese, setMese] = useState<number>(meseCorrente);
  const [data, setData] = useState<CostiComuniRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const reqRef = useRef(0);

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    fetch(`/api/gruppo/costi-comuni?anno=${annoCorrente}&mese=${mese}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) toast.error("Errore nel caricamento dei costi di gruppo");
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [annoCorrente, mese]);

  useEffect(() => {
    if (!open) return;
    carica();
  }, [open, carica]);

  async function elimina(c: Costo) {
    if (busy) return;
    const msg =
      c.origine === "fattura"
        ? "Rimuovere la ripartizione? Il costo tornerà intero sulla sede intestataria."
        : "Eliminare questo costo di gruppo?";
    if (!window.confirm(msg)) return;
    setBusy(c.id);
    try {
      const res = await fetch(`/api/riparto/${c.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Ripartizione rimossa");
      carica();
    } catch {
      toast.error("Impossibile rimuovere la ripartizione");
    } finally {
      setBusy(null);
    }
  }

  async function duplica(c: Costo) {
    if (busy) return;
    setBusy(c.id);
    try {
      const res = await fetch(`/api/riparto/${c.id}/duplica`, { method: "POST" });
      if (!res.ok) throw new Error();
      toast.success("Duplicato sul mese successivo");
      carica();
    } catch {
      toast.error("Impossibile duplicare");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] w-[min(96vw,56rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>Costi di gruppo</span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect
                value={String(mese)}
                onValueChange={(v) => setMese(Number(v))}
                className="h-8 w-40 text-xs"
              >
                {MESI.slice(0, meseCorrente).map((m, i) => (
                  <option key={i + 1} value={String(i + 1)}>
                    {m} {annoCorrente}
                  </option>
                ))}
              </NativeSelect>
              <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
                <Plus className="size-3.5" />
                Aggiungi costo
              </Button>
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="max-h-[calc(90vh-5rem)] overflow-auto px-5 pb-5 pt-3">
          <p className="mb-3 text-xs text-muted-foreground">
            Costi di struttura intestati alla sede legale, divisi fra i punti vendita. La quota di
            ogni sede entra nel suo MOL; nell&apos;analisi fatture il documento resta intero.
          </p>

          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : !data || data.costi.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Nessun costo di gruppo in {MESI[mese - 1]}. Ripartisci una fattura dal suo dettaglio, o
              aggiungi un costo manuale (es. stipendi ufficio).
            </div>
          ) : (
            <ul className="space-y-3">
              {data.costi.map((c) => (
                <li key={c.id} className="rounded-lg border bg-card p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      {c.origine === "fattura" ? (
                        <FileText className="size-3.5 text-muted-foreground" />
                      ) : (
                        <PencilLine className="size-3.5 text-muted-foreground" />
                      )}
                      {c.descrizione}
                      <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[0.65rem] font-normal text-muted-foreground">
                        {c.tipo === "fb" ? "F&B" : "spese generali"}
                      </span>
                    </span>
                    <span className="font-semibold tabular-nums">{euro(c.importo_totale)}</span>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {c.quote.map((q) => (
                      <span key={q.ristorante_id}>
                        {q.sede}{" "}
                        <span className="font-medium text-foreground tabular-nums">{euro(q.quota_importo)}</span>{" "}
                        ({q.quota_perc.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%)
                      </span>
                    ))}
                    <span className="text-muted-foreground/70">
                      {c.regola === "equa" ? "parti uguali" : "percentuali"}
                    </span>
                  </div>

                  <div className="mt-2 flex gap-2">
                    {c.origine === "manuale" && (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => duplica(c)}
                        className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs transition-colors hover:bg-accent disabled:opacity-50"
                      >
                        <CopyPlus className="size-3.5" />
                        Duplica sul mese dopo
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => elimina(c)}
                      className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                    >
                      <Trash2 className="size-3.5" />
                      {c.origine === "fattura" ? "Rimuovi ripartizione" : "Elimina"}
                    </button>
                  </div>
                </li>
              ))}
              <li className="flex items-center justify-between border-t pt-3 text-sm font-semibold">
                <span>Totale costi di gruppo</span>
                <span className="tabular-nums">{euro(data.totale)}</span>
              </li>
            </ul>
          )}
        </div>

        <AggiungiCostoDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          anno={annoCorrente}
          mese={mese}
          onDone={() => {
            setAddOpen(false);
            carica();
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

// Dialog per aggiungere una voce di costo di gruppo manuale (senza fattura).
function AggiungiCostoDialog({
  open,
  onOpenChange,
  anno,
  mese,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  anno: number;
  mese: number;
  onDone: () => void;
}) {
  const [descrizione, setDescrizione] = useState("");
  const [importo, setImporto] = useState("");
  const [tipo, setTipo] = useState<"generale" | "fb">("generale");
  const [saving, setSaving] = useState(false);

  async function salva() {
    const imp = Number(importo.replace(",", "."));
    if (!descrizione.trim() || !(imp > 0)) {
      toast.error("Inserisci descrizione e importo");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/riparto/manuale", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          descrizione: descrizione.trim(),
          importo_totale: imp,
          tipo,
          anno,
          mese,
          regola: "equa",
        }),
      });
      if (!res.ok) throw new Error();
      toast.success("Costo di gruppo aggiunto (parti uguali)");
      setDescrizione("");
      setImporto("");
      onDone();
    } catch {
      toast.error("Impossibile aggiungere il costo");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Aggiungi costo di gruppo</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Descrizione</label>
            <input
              value={descrizione}
              onChange={(e) => setDescrizione(e.target.value)}
              placeholder="Es. Stipendi ufficio"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Importo (€)</label>
              <input
                value={importo}
                onChange={(e) => setImporto(e.target.value)}
                inputMode="decimal"
                placeholder="2000"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm tabular-nums"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Tipo</label>
              <NativeSelect value={tipo} onValueChange={(v) => setTipo(v as "generale" | "fb")} className="h-[38px] text-sm">
                <option value="generale">Spese generali</option>
                <option value="fb">F&B</option>
              </NativeSelect>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Diviso in parti uguali fra i punti vendita. Potrai modificarlo dalla lista.
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
              Annulla
            </Button>
            <Button size="sm" onClick={salva} disabled={saving}>
              {saving ? "Salvataggio…" : "Aggiungi"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
