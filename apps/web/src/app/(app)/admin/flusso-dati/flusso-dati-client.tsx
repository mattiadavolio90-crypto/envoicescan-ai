"use client";

import { useState, useMemo, Fragment } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { RefreshCw, FileText, TrendingUp, Map, RotateCw, Link2, ChevronDown, ChevronRight } from "lucide-react";
import { RagioneSocialeClient } from "../ragione-sociale/ragione-sociale-client";

// ─── Tipi ───────────────────────────────────────────────────────────────────
type Sede = { id: string; nome_ristorante: string; partita_iva: string };
type Problema = {
  queue_id: number;
  status: string;
  piva_raw: string | null;
  fornitore: string | null;
  numero: string | null;
  importo: number | null;
  indirizzo: string | null;
  created_at: string;
  attempt_count: number | null;
  last_error: string | null;
};
type FattureItem = {
  user_id: string;
  nome: string;
  stato: "ok" | "warning" | "critico";
  n_sani: number;
  n_unknown: number;
  n_dead: number;
  n_failed: number;
  n_da_assegnare: number;
  sedi: Sede[];
  problemi: Problema[];
};
type RicaviItem = { ristorante_id: string; nome_ristorante: string; stato: string; giorni_silenzio: number | null; n_buchi: number; coda_problemi: number };
type Mapping = { id: string; ragione_sociale: string; ristorante_id: string; created_at: string };
type Cliente = { id: string; email: string; nome_ristorante: string; sedi: Sede[] };

type Props = {
  fattureIniziali: { items: FattureItem[]; counts: Record<string, number>; orfane: Problema[] };
  ricaviIniziali: { items: RicaviItem[]; counts: Record<string, number> };
  mappingsIniziali: Mapping[];
  clienti: Cliente[];
};

const STATO_DOT: Record<string, string> = {
  ok: "🟢",
  warning: "🟡",
  critico: "🔴",
};

const STATO_LABEL_FATTURE: Record<string, string> = {
  ok: "Tutto a posto",
  warning: "Da smistare",
  critico: "Problema",
};

function statoRicaviLabel(it: RicaviItem | undefined): { dot: string; testo: string } {
  if (!it) return { dot: "⚪", testo: "Manuale" };
  if (it.stato === "ok") return { dot: "🟢", testo: it.giorni_silenzio === 0 ? "Oggi" : `${it.giorni_silenzio}gg fa` };
  if (it.stato === "warning") return { dot: "🟡", testo: `${it.n_buchi} buchi` };
  return { dot: "🔴", testo: it.giorni_silenzio == null ? "Nessun dato" : `${it.giorni_silenzio}gg fa` };
}

export function FlussoDatiClient({ fattureIniziali, ricaviIniziali, mappingsIniziali, clienti }: Props) {
  const [fatture, setFatture] = useState(fattureIniziali);
  const [ricavi] = useState(ricaviIniziali);
  const [filtroCliente, setFiltroCliente] = useState("tutti");
  const [loading, setLoading] = useState(false);
  const [espanso, setEspanso] = useState<string | null>(null);
  const [mappingOpen, setMappingOpen] = useState(false);

  // dialog assegna sede / assegna piva
  const [azione, setAzione] = useState<{ tipo: "sede" | "piva"; prob: Problema; userId: string } | null>(null);
  const [sedeScelta, setSedeScelta] = useState("");
  const [busy, setBusy] = useState<number | null>(null);

  // indice ricavi per ristorante_id
  const ricaviPerRist = useMemo(() => {
    const m: Record<string, RicaviItem> = {};
    for (const r of ricavi.items) m[r.ristorante_id] = r;
    return m;
  }, [ricavi.items]);

  // mapping per ristorante_id (esiste un mapping ricavi?)
  const mappingRistSet = useMemo(() => new Set(mappingsIniziali.map((m) => m.ristorante_id)), [mappingsIniziali]);

  const sediFlat = useMemo(
    () =>
      clienti.flatMap((c) =>
        (c.sedi || []).map((s) => ({ id: s.id, label: `${s.nome_ristorante} (${c.email})` })),
      ),
    [clienti],
  );

  const items = useMemo(
    () => (filtroCliente === "tutti" ? fatture.items : fatture.items.filter((it) => it.user_id === filtroCliente)),
    [fatture.items, filtroCliente],
  );

  const nProblemi = fatture.items.reduce((acc, it) => acc + it.n_unknown + it.n_dead + it.n_failed + it.n_da_assegnare, 0);

  async function reload() {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/invoicetronic-salute?giorni=30");
      if (!res.ok) { toast.error("Errore aggiornamento"); return; }
      setFatture(await res.json());
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }

  async function riprova(prob: Problema) {
    if (!confirm(`Rimettere in coda la fattura ${prob.numero || prob.queue_id}? Verrà rielaborata al prossimo giro del worker.`)) return;
    setBusy(prob.queue_id);
    try {
      const res = await fetch("/api/admin/fatture-queue/riprova", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ queue_id: prob.queue_id }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore"); return; }
      toast.success("Fattura rimessa in coda");
      await reload();
    } catch { toast.error("Errore di connessione"); }
    finally { setBusy(null); }
  }

  async function confermaAzione() {
    if (!azione || !sedeScelta) { toast.error("Scegli una sede"); return; }
    setBusy(azione.prob.queue_id);
    try {
      if (azione.tipo === "sede") {
        const res = await fetch("/api/admin/fatture-queue/assegna-sede", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ queue_id: azione.prob.queue_id, ristorante_id: sedeScelta }),
        });
        const d = await res.json();
        if (!res.ok) { toast.error(d.detail || "Errore"); return; }
        toast.success(d.ok ? "Fattura assegnata alla sede" : "Era già assegnata");
      } else {
        const res = await fetch("/api/admin/fatture-queue/assegna-piva", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ piva: azione.prob.piva_raw, ristorante_id: sedeScelta }),
        });
        const d = await res.json();
        if (!res.ok) { toast.error(d.detail || "Errore"); return; }
        toast.success(`${d.sbloccate} fattura/e sbloccata/e`);
      }
      setAzione(null); setSedeScelta("");
      await reload();
    } catch { toast.error("Errore di connessione"); }
    finally { setBusy(null); }
  }

  // opzioni sede per il dialog: se assegno una P.IVA orfana scelgo fra TUTTE le sedi,
  // se smisto multi-sede scelgo fra le sedi del cliente.
  const sediDialog = useMemo(() => {
    if (!azione) return [];
    if (azione.tipo === "sede") {
      const cli = clienti.find((c) => c.id === azione.userId);
      return (cli?.sedi || []).map((s) => ({ id: s.id, label: `${s.nome_ristorante}${s.partita_iva ? ` — ${s.partita_iva}` : ""}` }));
    }
    return sediFlat;
  }, [azione, clienti, sediFlat]);

  return (
    <div className="space-y-4">
      {/* Barra filtro + azioni globali */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <NativeSelect value={filtroCliente} onValueChange={setFiltroCliente} className="w-56">
            <option value="tutti">Tutti i clienti</option>
            {fatture.items.map((it) => (
              <option key={it.user_id} value={it.user_id}>{it.nome}</option>
            ))}
          </NativeSelect>
          <Button variant="outline" size="sm" onClick={reload} disabled={loading}>
            <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
          </Button>
        </div>
        <Button variant="outline" size="sm" onClick={() => setMappingOpen(true)}>
          <Link2 className="size-4 mr-1" /> Mapping ricavi
        </Button>
      </div>

      {/* Banner problemi */}
      {nProblemi > 0 && (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700">
          {nProblemi} {nProblemi === 1 ? "fattura ha" : "fatture hanno"} bisogno di attenzione. Apri il dettaglio del cliente per sbloccarle.
        </div>
      )}

      {/* P.IVA orfane (fatture di nessun cliente noto) */}
      {fatture.orfane.length > 0 && (
        <Card className="p-4 border-amber-500/40">
          <p className="text-sm font-medium mb-2">⚠ P.IVA non riconosciute ({fatture.orfane.length})</p>
          <p className="text-xs text-muted-foreground mb-3">
            Fatture arrivate per P.IVA che non corrispondono a nessun ristorante. Assegnale a un cliente per sbloccarle.
          </p>
          <div className="space-y-2">
            {fatture.orfane.map((p) => (
              <div key={p.queue_id} className="flex items-center justify-between gap-3 rounded border p-2 text-sm">
                <div className="min-w-0">
                  <span className="font-mono">{p.piva_raw}</span>
                  <span className="text-muted-foreground"> · {p.numero || "—"} · €{p.importo ?? "—"}</span>
                </div>
                <Button size="sm" variant="outline" disabled={busy === p.queue_id}
                  onClick={() => { setAzione({ tipo: "piva", prob: p, userId: "" }); setSedeScelta(""); }}>
                  Assegna a…
                </Button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Tabella clienti */}
      <div className="rounded-lg border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-3 font-medium">Cliente</th>
              <th className="px-4 py-3 font-medium"><FileText className="size-4 inline mr-1" />Fatture</th>
              <th className="px-4 py-3 font-medium"><TrendingUp className="size-4 inline mr-1" />Ricavi</th>
              <th className="px-4 py-3 font-medium"><Map className="size-4 inline mr-1" />Mapping</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody className="divide-y">
            {items.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">Nessun cliente.</td></tr>
            ) : items.map((it) => {
              const ristIds = it.sedi.map((s) => s.id);
              const ric = ristIds.map((id) => ricaviPerRist[id]).find(Boolean);
              const ricLabel = statoRicaviLabel(ric);
              const hasMapping = ristIds.some((id) => mappingRistSet.has(id));
              const isMulti = it.sedi.length > 1;
              const aperto = espanso === it.user_id;
              return (
                <Fragment key={it.user_id}>
                  <tr className="hover:bg-muted/30 cursor-pointer"
                    onClick={() => setEspanso(aperto ? null : it.user_id)}>
                    <td className="px-4 py-3 font-medium">{it.nome}</td>
                    <td className="px-4 py-3">
                      {STATO_DOT[it.stato]} {it.stato === "ok"
                        ? `${it.n_sani} ok`
                        : it.n_unknown > 0 ? `${it.n_unknown} P.IVA ko`
                        : it.n_da_assegnare > 0 ? `${it.n_da_assegnare} da smistare`
                        : `${it.n_dead + it.n_failed} in errore`}
                    </td>
                    <td className="px-4 py-3">{ricLabel.dot} {ricLabel.testo}</td>
                    <td className="px-4 py-3">
                      {hasMapping ? "✓ ok" : <span className="text-muted-foreground">—</span>}
                      {isMulti && <span className="ml-2 text-xs text-muted-foreground">{it.sedi.length} sedi</span>}
                    </td>
                    <td className="px-4 py-3 text-right text-muted-foreground">
                      {it.problemi.length > 0 ? (aperto ? <ChevronDown className="size-4 inline" /> : <ChevronRight className="size-4 inline" />) : null}
                    </td>
                  </tr>
                  {aperto && it.problemi.length > 0 && (
                    <tr className="bg-muted/20">
                      <td colSpan={5} className="px-4 py-3">
                        <div className="space-y-2">
                          {it.problemi.map((p) => (
                            <div key={p.queue_id} className="flex flex-wrap items-center justify-between gap-3 rounded border bg-background p-2 text-sm">
                              <div className="min-w-0">
                                <span className="font-medium">{STATO_LABEL_FATTURE[fattureStato(p.status)] || p.status}</span>
                                <span className="text-muted-foreground"> · {p.numero || "—"} · €{p.importo ?? "—"} · {p.piva_raw}</span>
                                {p.status === "dead" && p.last_error && (
                                  <div className="text-xs text-red-600 mt-0.5">Errore: {p.last_error}</div>
                                )}
                              </div>
                              <div className="flex gap-2 shrink-0">
                                {p.status === "da_assegnare" && (
                                  <Button size="sm" variant="outline" disabled={busy === p.queue_id}
                                    onClick={() => { setAzione({ tipo: "sede", prob: p, userId: it.user_id }); setSedeScelta(""); }}>
                                    Scegli sede
                                  </Button>
                                )}
                                {p.status === "unknown_tenant" && (
                                  <Button size="sm" variant="outline" disabled={busy === p.queue_id}
                                    onClick={() => { setAzione({ tipo: "piva", prob: p, userId: it.user_id }); setSedeScelta(""); }}>
                                    Assegna a…
                                  </Button>
                                )}
                                {(p.status === "failed" || p.status === "dead") && (
                                  <Button size="sm" variant="outline" disabled={busy === p.queue_id} onClick={() => riprova(p)}>
                                    <RotateCw className="size-4 mr-1" /> Riprova
                                  </Button>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Dialog conferma azione (assegna sede / assegna piva) */}
      <Dialog open={!!azione} onOpenChange={(o) => { if (!o) { setAzione(null); setSedeScelta(""); } }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{azione?.tipo === "sede" ? "Scegli la sede" : "Assegna a un ristorante"}</DialogTitle>
            <DialogDescription>
              {azione?.tipo === "sede"
                ? "A quale sede appartiene questa fattura? Verrà rimessa in coda per l'elaborazione."
                : "A quale ristorante appartiene questa P.IVA? Tutte le fatture in attesa con questa P.IVA verranno sbloccate."}
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <NativeSelect value={sedeScelta} onValueChange={setSedeScelta} placeholder="Seleziona ristorante…">
              {sediDialog.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </NativeSelect>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setAzione(null); setSedeScelta(""); }}>Annulla</Button>
            <Button onClick={confermaAzione} disabled={!sedeScelta || busy != null}>Conferma</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog mapping ricavi (riusa il componente esistente) */}
      <Dialog open={mappingOpen} onOpenChange={setMappingOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Mapping ragione sociale (ricavi)</DialogTitle>
            <DialogDescription>
              Collega le ragioni sociali delle email dei gestionali al ristorante corretto.
            </DialogDescription>
          </DialogHeader>
          <RagioneSocialeClient mappingsIniziali={mappingsIniziali} sedi={sediFlat} />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function fattureStato(s: string): string {
  if (s === "unknown_tenant" || s === "dead" || s === "failed") return "critico";
  if (s === "da_assegnare") return "warning";
  return "ok";
}
