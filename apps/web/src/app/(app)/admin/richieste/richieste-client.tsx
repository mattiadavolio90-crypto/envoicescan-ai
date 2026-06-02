"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Check, Archive, RotateCcw, Mail, Inbox, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type MarketplaceLead } from "@/lib/assistenza";

type Filtro = "nuovo" | "gestito" | "archiviato" | "tutti";

const FILTRI: { key: Filtro; label: string }[] = [
  { key: "nuovo", label: "Nuove" },
  { key: "gestito", label: "Gestite" },
  { key: "archiviato", label: "Archiviate" },
  { key: "tutti", label: "Tutte" },
];

const STATO_BADGE: Record<MarketplaceLead["stato"], string> = {
  nuovo: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
  gestito: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  archiviato: "bg-muted text-muted-foreground",
};

export function RichiesteClient({ initial }: { initial: MarketplaceLead[] }) {
  const [leads, setLeads] = useState<MarketplaceLead[]>(initial);
  const [filtro, setFiltro] = useState<Filtro>("nuovo");
  const [busy, setBusy] = useState<Set<string>>(new Set());

  const counts = useMemo(() => {
    const c = { nuovo: 0, gestito: 0, archiviato: 0, tutti: leads.length };
    for (const l of leads) c[l.stato] += 1;
    return c;
  }, [leads]);

  const visibili = useMemo(
    () => (filtro === "tutti" ? leads : leads.filter((l) => l.stato === filtro)),
    [leads, filtro],
  );

  async function cambiaStato(id: string, stato: MarketplaceLead["stato"]) {
    setBusy((p) => new Set(p).add(id));
    try {
      const res = await fetch(`/api/admin/marketplace/leads/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ stato }),
      });
      if (!res.ok) throw new Error();
      setLeads((prev) => prev.map((l) => (l.id === id ? { ...l, stato } : l)));
    } catch {
      toast.error("Errore aggiornamento");
    } finally {
      setBusy((p) => {
        const n = new Set(p);
        n.delete(id);
        return n;
      });
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {FILTRI.map((f) => {
          const attivo = filtro === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFiltro(f.key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                attivo
                  ? "border-foreground bg-foreground text-background"
                  : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground",
              )}
            >
              {f.label}
              <span
                className={cn(
                  "min-w-4 rounded-full px-1 text-center text-[10px] font-bold tabular-nums",
                  attivo ? "bg-background/20" : "bg-muted",
                )}
              >
                {counts[f.key]}
              </span>
            </button>
          );
        })}
      </div>

      {visibili.length === 0 ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <Inbox className="size-10 opacity-30" />
          <p className="text-sm">Nessuna richiesta in questa categoria.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {visibili.map((l) => (
            <div key={l.id} className="rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{l.servizio_label}</span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[11px] font-medium",
                    STATO_BADGE[l.stato],
                  )}
                >
                  {l.stato}
                </span>
                {l.created_at && (
                  <span className="ml-auto text-xs text-muted-foreground">
                    {new Date(l.created_at).toLocaleString("it-IT", {
                      day: "2-digit",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                )}
              </div>

              <div className="mt-2 text-sm">
                <span className="font-medium">{l.ristorante_nome || l.contatto_nome || "—"}</span>
                {l.contatto_email && (
                  <a
                    href={`mailto:${l.contatto_email}`}
                    className="ml-2 inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
                  >
                    <Mail className="size-3.5" />
                    {l.contatto_email}
                  </a>
                )}
              </div>

              {l.messaggio && (
                <p className="mt-2 whitespace-pre-line rounded-lg bg-muted/50 p-3 text-sm text-muted-foreground">
                  {l.messaggio}
                </p>
              )}

              <div className="mt-3 flex flex-wrap gap-2">
                {l.stato !== "gestito" && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy.has(l.id)}
                    onClick={() => cambiaStato(l.id, "gestito")}
                    className="gap-1.5"
                  >
                    {busy.has(l.id) ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
                    Segna gestita
                  </Button>
                )}
                {l.stato !== "archiviato" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy.has(l.id)}
                    onClick={() => cambiaStato(l.id, "archiviato")}
                    className="gap-1.5 text-muted-foreground"
                  >
                    <Archive className="size-3.5" />
                    Archivia
                  </Button>
                )}
                {l.stato !== "nuovo" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy.has(l.id)}
                    onClick={() => cambiaStato(l.id, "nuovo")}
                    className="gap-1.5 text-muted-foreground"
                  >
                    <RotateCcw className="size-3.5" />
                    Riapri
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
