"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { MapPin, Split, CheckCircle2, ChevronRight, Eye } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(n);
}

// Coda delle fatture che l'app non ha saputo attribuire a un locale (P.IVA condivisa
// fra più sedi + indirizzo assente/ambiguo). È un fenomeno DI GRUPPO: esiste solo per
// le catene same-P.IVA. Perciò vive SOLO in modalità catena — nel contesto PV il
// componente non renderizza nulla.
//
// In catena si mostra come CARD COMPATTA (riepilogo + totale): un click apre la
// finestra con la lista completa e le azioni (assegna a un locale / dividi sul gruppo),
// stesso pattern delle altre finestre catena (Spesa, Costi di gruppo, Margini). Così la
// Sintesi resta una plancia a colpo d'occhio, senza scroll infinito.
export function CodaDaAssegnare({ contesto = "pv" }: { contesto?: "pv" | "catena" }) {
  const router = useRouter();
  const [items, setItems] = useState<FatturaDaAssegnare[]>([]);
  const [sedi, setSedi] = useState<Sede[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [ripartisci, setRipartisci] = useState<FatturaDaAssegnare | null>(null);
  const [finestraOpen, setFinestraOpen] = useState(false);
  const [anteprima, setAnteprima] = useState<FatturaDaAssegnare | null>(null);

  useEffect(() => {
    if (contesto !== "catena") return;
    let alive = true;
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

  if (contesto !== "catena" || (loaded && sedi.length < 2)) return null;
  if (!loaded) return null;

  const totale = items.reduce((a, f) => a + (f.importo_totale ?? 0), 0);
  const vuoto = items.length === 0;

  return (
    <>
      {/* Card compatta: riepilogo a colpo d'occhio, apre la finestra con la lista. */}
      <button
        type="button"
        onClick={() => !vuoto && setFinestraOpen(true)}
        disabled={vuoto}
        className={
          vuoto
            ? "flex w-full items-center gap-3 rounded-2xl border bg-card p-5 text-left"
            : "group flex w-full items-center gap-4 rounded-2xl border border-l-4 border-l-amber-500 bg-card p-5 text-left transition-colors hover:bg-accent"
        }
      >
        <span
          className={
            vuoto
              ? "flex size-11 shrink-0 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500"
              : "flex size-11 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-600 dark:text-amber-400"
          }
        >
          {vuoto ? <CheckCircle2 className="size-5" /> : <Split className="size-5" />}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2 text-sm font-semibold">
            Gestione fatture di gruppo
            {!vuoto && (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                {items.length}
              </span>
            )}
          </span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            {vuoto
              ? "Tutte le fatture sono al loro posto."
              : `Fatture arrivate a nome della società, da collocare · totale ${euro(totale)}`}
          </span>
        </span>
        {!vuoto && (
          <ChevronRight className="size-4 shrink-0 text-muted-foreground/50 transition-transform group-hover:translate-x-0.5" />
        )}
      </button>

      {/* Finestra con la lista completa e le azioni. */}
      <Dialog open={finestraOpen} onOpenChange={setFinestraOpen}>
        <DialogContent className="max-h-[90vh] w-[min(96vw,48rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
              <span className="flex items-center gap-2">
                <Split className="size-4 text-amber-500" />
                Gestione fatture di gruppo
                <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                  {items.length}
                </span>
              </span>
              {!vuoto && (
                <span className="text-xs font-normal text-muted-foreground">
                  Totale <span className="font-semibold tabular-nums text-foreground">{euro(totale)}</span>
                </span>
              )}
            </DialogTitle>
          </DialogHeader>

          <div className="max-h-[calc(90vh-5rem)] overflow-auto px-5 pb-5 pt-3">
            <p className="mb-3 text-sm font-medium text-amber-600 dark:text-amber-400">
              Scegli la sede se è di un locale, oppure “Dividi tra i locali” se è un costo comune.
            </p>

            {items.length === 0 ? (
              <div className="py-12 text-center text-sm text-muted-foreground">
                Nessuna fattura da collocare.
              </div>
            ) : (
              <ul className="space-y-3">
                {items.map((f) => (
                  <li key={f.queue_id} className="rounded-xl border border-border bg-card p-3 space-y-2">
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
                      <button
                        onClick={() => setAnteprima(f)}
                        className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent"
                      >
                        <Eye className="size-3.5" />
                        Anteprima
                      </button>
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
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Anteprima essenziale: la fattura è ancora in coda (non ancora processata,
          nessuna riga prodotto disponibile) → mostriamo i metadati del documento
          già noti dal webhook, in un formato leggibile. Il dettaglio riga-per-riga
          (come in Gestione Fatture) richiede un parser XML dedicato non ancora
          pronto — pianificato dopo il go-live. */}
      <Dialog open={anteprima !== null} onOpenChange={(v) => !v && setAnteprima(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Anteprima fattura</DialogTitle>
          </DialogHeader>
          {anteprima && (
            <div className="space-y-3 text-sm">
              <p className="text-xs text-muted-foreground">
                Documento ancora in coda: il dettaglio riga per riga sarà disponibile dopo averlo
                collocato.
              </p>
              <dl className="space-y-2 rounded-lg border bg-muted/30 p-3">
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Fornitore</dt>
                  <dd className="text-right font-medium">
                    {anteprima.fornitore ? `P.IVA ${anteprima.fornitore}` : "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Numero</dt>
                  <dd className="text-right font-medium">{anteprima.numero_fattura ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted-foreground">Data</dt>
                  <dd className="text-right font-medium">{anteprima.data_fattura ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-3 border-t pt-2">
                  <dt className="text-muted-foreground">Importo</dt>
                  <dd className="text-right text-base font-bold tabular-nums">
                    {anteprima.importo_totale != null
                      ? `€ ${anteprima.importo_totale.toLocaleString("it-IT", { minimumFractionDigits: 2 })}`
                      : "—"}
                  </dd>
                </div>
                {anteprima.indirizzo_destinatario && (
                  <div className="border-t pt-2">
                    <dt className="text-muted-foreground">Indirizzo in fattura</dt>
                    <dd className="mt-0.5 font-medium">{anteprima.indirizzo_destinatario}</dd>
                  </div>
                )}
              </dl>
            </div>
          )}
        </DialogContent>
      </Dialog>

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
    </>
  );
}
