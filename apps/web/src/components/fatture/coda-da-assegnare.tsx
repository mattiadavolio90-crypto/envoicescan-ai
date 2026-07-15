"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { MapPin, AlertTriangle, Split } from "lucide-react";
import { RipartisciDialog } from "@/components/fatture/ripartisci-dialog";

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

// Avviso in Home (con le notifiche) che appare SOLO ai clienti multi-sede quando
// una fattura SDI non è stata smistata automaticamente (indirizzo assente o
// ambiguo). Il cliente sceglie la sede e la fattura rientra in elaborazione.
// Per i clienti mono-sede non renderizza nulla. Linguaggio visivo allineato al
// widget notifiche della Home (bordo sinistro ambra, icona severity).
export function CodaDaAssegnare() {
  const router = useRouter();
  const [items, setItems] = useState<FatturaDaAssegnare[]>([]);
  const [sedi, setSedi] = useState<Sede[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [ripartisci, setRipartisci] = useState<FatturaDaAssegnare | null>(null);

  useEffect(() => {
    let alive = true;
    // Prima le sedi (fetch leggera): se l'account e' mono-sede (la maggioranza)
    // la coda non si applica e NON facciamo la seconda fetch su /da-assegnare.
    // Prima si chiamavano sempre entrambe in parallelo, 2 round-trip sprecati su
    // ogni Home per i mono-sede.
    fetch("/api/account/sedi", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((sediRes) => {
        if (!alive) return;
        const lista = (sediRes?.sedi ?? []) as Sede[];
        setSedi(lista);
        if (lista.length < 2) return; // mono-sede: niente seconda fetch
        return fetch("/api/fatture/da-assegnare", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .then((coda) => {
            if (alive && coda?.items) setItems(coda.items as FatturaDaAssegnare[]);
          });
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
    <div className="rounded-xl border border-l-4 border-l-amber-500 bg-card p-4 space-y-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="size-5 text-amber-500 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-medium">
            {items.length === 1
              ? "1 fattura da assegnare a una sede"
              : `${items.length} fatture da assegnare a una sede`}
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Non sono riuscito a capire da solo a quale sede appartengono (indirizzo della sede legale
            o non riconosciuto). Se appartiene a un locale, scegli la sede e la fattura rientra subito
            in elaborazione. Se è un <span className="font-medium">costo comune</span> (commercialista,
            auto…), premi <span className="font-medium">“Ripartisci sul gruppo”</span>: il costo viene
            diviso fra le sedi senza finire dentro un singolo locale.
          </p>
        </div>
      </div>

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
              <button
                disabled={busy !== null}
                onClick={() => setRipartisci(f)}
                className="inline-flex items-center gap-1.5 rounded-md border border-primary/40 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10 hover:border-primary disabled:opacity-50"
              >
                <Split className="size-3.5" />
                Ripartisci sul gruppo
              </button>
            </div>
          </li>
        ))}
      </ul>

      <RipartisciDialog
        open={ripartisci !== null}
        onOpenChange={(v) => !v && setRipartisci(null)}
        queueId={ripartisci?.queue_id}
        descrizioneDefault={ripartisci?.fornitore ? `Costo comune ${ripartisci.fornitore}` : ""}
        sedi={sedi.map((s) => ({ id: s.id, nome: s.nome }))}
        onDone={() => {
          if (ripartisci) setItems((prev) => prev.filter((i) => i.queue_id !== ripartisci.queue_id));
          setRipartisci(null);
          router.refresh();
        }}
      />
    </div>
  );
}
