"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { MapPin, AlertTriangle, Split, CheckCircle2 } from "lucide-react";
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

// Coda delle fatture che l'app non ha saputo attribuire a un locale (P.IVA condivisa
// fra più sedi + indirizzo assente/ambiguo). È un fenomeno DI GRUPPO: esiste solo per
// le catene same-P.IVA (per le catene a P.IVA distinte lo smistamento avviene a monte).
// Perciò vive SOLO in modalità catena — nel contesto PV il componente non renderizza
// nulla (una fattura in coda non appartiene a nessun locale, non va mostrata dentro uno).
//
//  - contesto="catena": card "Gestione fatture di gruppo" nella Sintesi catena, con
//    conteggio, testo esplicativo e stato vuoto positivo.
//  - contesto="pv" (default): return null (retrocompatibile, la coda non compare in Home).
export function CodaDaAssegnare({ contesto = "pv" }: { contesto?: "pv" | "catena" }) {
  const router = useRouter();
  const [items, setItems] = useState<FatturaDaAssegnare[]>([]);
  const [sedi, setSedi] = useState<Sede[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [ripartisci, setRipartisci] = useState<FatturaDaAssegnare | null>(null);

  useEffect(() => {
    // Nel contesto PV non serve alcuna fetch: la coda non si mostra qui.
    if (contesto !== "catena") return;
    let alive = true;
    // Prima le sedi (fetch leggera): la coda ha senso solo per i multi-sede.
    fetch("/api/account/sedi", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((sediRes) => {
        if (!alive) return;
        const lista = (sediRes?.sedi ?? []) as Sede[];
        setSedi(lista);
        if (lista.length < 2) {
          setLoaded(true);
          return;
        }
        return fetch("/api/fatture/da-assegnare", { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .then((coda) => {
            if (!alive) return;
            if (coda?.items) setItems(coda.items as FatturaDaAssegnare[]);
            setLoaded(true);
          });
      })
      .catch(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, [contesto]);

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

  // Contesto PV o account mono-sede: la coda di gruppo non si applica.
  if (contesto !== "catena" || (loaded && sedi.length < 2)) return null;

  // Stato vuoto positivo: la card resta (rassicura che il flusso funziona) ma senza lista.
  if (loaded && items.length === 0) {
    return (
      <div className="rounded-2xl border bg-card p-5">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          <Split className="size-4" />
          Gestione fatture di gruppo
        </div>
        <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
          <CheckCircle2 className="size-4 text-emerald-500" />
          Tutte le fatture sono al loro posto.
        </p>
      </div>
    );
  }

  // Ancora in caricamento: niente flash, aspetta la prima fetch.
  if (!loaded) return null;

  return (
    <div className="rounded-2xl border border-l-4 border-l-amber-500 bg-card p-5 space-y-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="size-5 text-amber-500 shrink-0" />
        <div className="min-w-0">
          <p className="text-sm font-semibold">
            Gestione fatture di gruppo
            <span className="ml-2 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
              {items.length}
            </span>
          </p>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Sono arrivate a nome della società ma non indicano il locale: dimmi tu dove vanno.
            Se è di un singolo locale, scegli la sede. Se è un{" "}
            <span className="font-medium">costo comune</span> (commercialista, auto…), premi{" "}
            <span className="font-medium">“Dividi tra i locali”</span>: il costo viene diviso fra le
            sedi senza finire dentro un solo locale.
          </p>
        </div>
      </div>

      <ul className="space-y-3">
        {items.map((f) => (
          <li
            key={f.queue_id}
            className="rounded-xl border border-border bg-background/40 p-3 space-y-2"
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
                Dividi tra i locali
              </button>
            </div>
          </li>
        ))}
      </ul>

      <RipartisciDialog
        open={ripartisci !== null}
        onOpenChange={(v) => !v && setRipartisci(null)}
        queueId={ripartisci?.queue_id}
        fornitore={ripartisci?.fornitore ?? undefined}
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
