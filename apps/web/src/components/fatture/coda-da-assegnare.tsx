"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { MapPin } from "lucide-react";

type FatturaDaAssegnare = {
  queue_id: number;
  fornitore: string | null;
  numero_fattura: string | null;
  data_fattura: string | null;
  importo_totale: number | null;
  indirizzo_destinatario: string | null;
  created_at: string | null;
};

type Sede = { id: string; nome: string; indirizzo: string | null; comune: string | null };

// Banner che appare SOLO ai clienti multi-sede quando una fattura SDI non è stata
// smistata automaticamente (indirizzo ambiguo). Il cliente sceglie la sede e la
// fattura rientra in elaborazione. Per i clienti mono-sede non renderizza nulla.
export function CodaDaAssegnare() {
  const router = useRouter();
  const [items, setItems] = useState<FatturaDaAssegnare[]>([]);
  const [sedi, setSedi] = useState<Sede[]>([]);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      fetch("/api/fatture/da-assegnare", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)),
      fetch("/api/account/sedi", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([coda, sediRes]) => {
        if (!alive) return;
        if (coda?.items) setItems(coda.items as FatturaDaAssegnare[]);
        if (sediRes?.sedi) setSedi(sediRes.sedi as Sede[]);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  async function assegna(queueId: number, ristoranteId: string) {
    if (busy !== null) return;
    setBusy(queueId);
    try {
      const res = await fetch("/api/fatture/da-assegnare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queue_id: queueId, ristorante_id: ristoranteId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || data?.error);
      setItems((prev) => prev.filter((i) => i.queue_id !== queueId));
      toast.success("Fattura assegnata alla sede");
      router.refresh();
    } catch {
      toast.error("Impossibile assegnare la fattura");
    } finally {
      setBusy(null);
    }
  }

  // Niente da mostrare: nessuna fattura in sospeso, oppure account mono-sede.
  if (items.length === 0 || sedi.length < 2) return null;

  return (
    <div className="rounded-lg border border-amber-400/40 bg-amber-50 dark:bg-amber-950/20 p-4 space-y-3">
      <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
        <MapPin className="size-4" />
        <span className="font-medium text-sm">
          {items.length === 1
            ? "1 fattura da assegnare a una sede"
            : `${items.length} fatture da assegnare a una sede`}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        Non siamo riusciti a capire automaticamente a quale sede appartengono queste fatture.
        Scegli tu la sede corretta.
      </p>

      <ul className="space-y-3">
        {items.map((f) => (
          <li
            key={f.queue_id}
            className="rounded-md border border-border bg-background p-3 space-y-2"
          >
            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
              <span className="font-medium">
                {f.fornitore ? `Fornitore P.IVA ${f.fornitore}` : "Fattura"}
              </span>
              {f.numero_fattura && <span className="text-muted-foreground">n. {f.numero_fattura}</span>}
              {f.data_fattura && <span className="text-muted-foreground">{f.data_fattura}</span>}
              {f.importo_totale != null && (
                <span className="ml-auto font-medium tabular-nums">
                  € {f.importo_totale.toLocaleString("it-IT", { minimumFractionDigits: 2 })}
                </span>
              )}
            </div>

            {f.indirizzo_destinatario && (
              <div className="text-xs text-muted-foreground">
                Indirizzo in fattura: <span className="font-medium">{f.indirizzo_destinatario}</span>
              </div>
            )}

            <div className="flex flex-wrap gap-2 pt-1">
              {sedi.map((s) => (
                <button
                  key={s.id}
                  disabled={busy !== null}
                  onClick={() => assegna(f.queue_id, s.id)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-sky-500/10 hover:border-sky-500 disabled:opacity-50"
                >
                  <MapPin className="size-3.5" />
                  {s.nome}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
