"use client";

import { useState, useMemo, Fragment } from "react";
import { toast } from "sonner";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { RefreshCw, FileText, TrendingUp, Map, RotateCw, Link2, ChevronDown, ChevronRight, AlertTriangle, CheckCircle, Mail } from "lucide-react";
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
type RicaviItem = {
  ristorante_id: string;
  nome_ristorante: string;
  stato: "ok" | "warning" | "critico";
  ultima_data: string | null;
  giorni_silenzio: number | null;
  buchi: string[];
  n_buchi: number;
  coda_problemi: number;
};
type RicaviImportItem = {
  id: string;
  status: string;
  email_sender: string | null;
  email_subject: string | null;
  attachment_name: string | null;
  created_at: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  last_error: string | null;
};
type Mapping = { id: string; ragione_sociale: string; ristorante_id: string; created_at: string };
type Cliente = { id: string; email: string; nome_ristorante: string; sedi: Sede[] };

type Props = {
  fattureIniziali: { items: FattureItem[]; counts: Record<string, number>; orfane: Problema[] };
  ricaviIniziali: { items: RicaviItem[]; counts: Record<string, number> };
  ricaviImportIniziali: { items: RicaviImportItem[]; counts: Record<string, number> };
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

const IMPORT_STATUS_LABEL: Record<string, string> = {
  unknown_sender: "Mittente sconosciuto",
  failed: "In retry",
  dead: "Bloccato",
};
const IMPORT_STATUS_CLASS: Record<string, string> = {
  dead: "bg-red-500/15 text-red-600 border-red-500/30",
  unknown_sender: "bg-amber-500/15 text-amber-600 border-amber-500/30",
  failed: "bg-orange-500/15 text-orange-600 border-orange-500/30",
};

function formatGiornoMese(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}

// Problemi ricavi di un ristorante in frasi leggibili (riuso della logica di Sistema&Salute).
function ricaviProblemi(r: RicaviItem): string[] {
  const out: string[] = [];
  if (r.giorni_silenzio == null) out.push("nessun ricavo registrato");
  else if (r.stato === "critico" && r.giorni_silenzio > 0)
    out.push(`nessun dato da ${r.giorni_silenzio} giorn${r.giorni_silenzio === 1 ? "o" : "i"}`);
  if (r.n_buchi > 0)
    out.push(`${r.n_buchi} giorn${r.n_buchi === 1 ? "o" : "i"} mancant${r.n_buchi === 1 ? "e" : "i"}: ${r.buchi.map(formatGiornoMese).join(", ")}`);
  if (r.coda_problemi > 0)
    out.push(`${r.coda_problemi} import bloccat${r.coda_problemi === 1 ? "o" : "i"} in coda`);
  return out;
}

export function FlussoDatiClient({ fattureIniziali, ricaviIniziali, ricaviImportIniziali, mappingsIniziali, clienti }: Props) {
  const [fatture, setFatture] = useState(fattureIniziali);
  const [ricavi] = useState(ricaviIniziali);
  const [ricaviImport] = useState(ricaviImportIniziali);
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

  const nProblemiFatture = fatture.items.reduce((acc, it) => acc + it.n_unknown + it.n_dead + it.n_failed + it.n_da_assegnare, 0)
    + fatture.orfane.length;
  const nProblemiRicavi = ricavi.items.filter((r) => r.stato !== "ok").length;
  const nRicaviNonRiconosciuti = ricaviImport.items.length;
  const nProblemi = nProblemiFatture + nProblemiRicavi + nRicaviNonRiconosciuti;

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

      {/* Banner problemi unificato (fatture + ricavi) */}
      {nProblemi > 0 ? (
        <div className="rounded-md border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700">
          <span className="font-medium">{nProblemi} {nProblemi === 1 ? "cosa richiede" : "cose richiedono"} attenzione.</span>{" "}
          {[
            nProblemiFatture > 0 ? `${nProblemiFatture} sulle fatture` : null,
            nProblemiRicavi > 0 ? `${nProblemiRicavi} ristorant${nProblemiRicavi === 1 ? "e" : "i"} coi ricavi` : null,
            nRicaviNonRiconosciuti > 0 ? `${nRicaviNonRiconosciuti} email ricavi non riconosciut${nRicaviNonRiconosciuti === 1 ? "a" : "e"}` : null,
          ].filter(Boolean).join(" · ")}.
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700">
          <CheckCircle className="size-4" /> Tutto a posto: fatture e ricavi arrivano regolarmente.
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

      {/* Ricavi non riconosciuti (email gestionali bloccate in coda) */}
      {ricaviImport.items.length > 0 && (
        <Card className="p-4 border-amber-500/40">
          <p className="text-sm font-medium mb-2 flex items-center gap-1">
            <Mail className="size-4" /> Email ricavi non elaborate ({ricaviImport.items.length})
          </p>
          <p className="text-xs text-muted-foreground mb-3">
            Email dei gestionali arrivate ma non importate: mittente non riconosciuto, in retry o bloccate.
            Per il mittente sconosciuto aggiungi il mapping da <span className="font-medium">Mapping ricavi</span>, poi l’import riparte da solo.
          </p>
          <div className="space-y-2">
            {ricaviImport.items.map((it) => (
              <div key={it.id} className="rounded border p-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${IMPORT_STATUS_CLASS[it.status] || ""}`}>
                    {IMPORT_STATUS_LABEL[it.status] || it.status}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {it.created_at ? new Date(it.created_at).toLocaleString("it-IT") : "—"}
                  </span>
                </div>
                <p className="mt-1 font-medium">{it.email_sender || "mittente ignoto"}</p>
                <p className="text-xs text-muted-foreground">
                  {it.attachment_name || "—"}
                  {it.email_subject ? ` · ${it.email_subject}` : ""}
                  {it.attempt_count != null && it.max_attempts != null ? ` · tentativi ${it.attempt_count}/${it.max_attempts}` : ""}
                </p>
                {it.last_error && (
                  <p className="mt-0.5 flex items-start gap-1 text-xs text-red-600">
                    <AlertTriangle className="size-3.5 mt-0.5 shrink-0" /> {it.last_error}
                  </p>
                )}
              </div>
            ))}
          </div>
          <div className="mt-3">
            <Button size="sm" variant="outline" onClick={() => setMappingOpen(true)}>
              <Link2 className="size-4 mr-1" /> Apri Mapping ricavi
            </Button>
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
              const ricList = ristIds.map((id) => ricaviPerRist[id]).filter(Boolean) as RicaviItem[];
              const ric = ricList.find((r) => r.stato !== "ok") || ricList[0];
              const ricLabel = statoRicaviLabel(ric);
              const ricConProblemi = ricList.filter((r) => r.stato !== "ok");
              const hasMapping = ristIds.some((id) => mappingRistSet.has(id));
              const isMulti = it.sedi.length > 1;
              const aperto = espanso === it.user_id;
              const espandibile = it.problemi.length > 0 || ricConProblemi.length > 0;
              return (
                <Fragment key={it.user_id}>
                  <tr className={espandibile ? "hover:bg-muted/30 cursor-pointer" : ""}
                    onClick={() => espandibile && setEspanso(aperto ? null : it.user_id)}>
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
                      {espandibile ? (aperto ? <ChevronDown className="size-4 inline" /> : <ChevronRight className="size-4 inline" />) : null}
                    </td>
                  </tr>
                  {aperto && espandibile && (
                    <tr className="bg-muted/20">
                      <td colSpan={5} className="px-4 py-3">
                        {ricConProblemi.length > 0 && (
                          <div className="mb-3 space-y-2">
                            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
                              <TrendingUp className="size-3.5" /> Ricavi
                            </p>
                            {ricConProblemi.map((r) => (
                              <div key={r.ristorante_id} className="rounded border bg-background p-2 text-sm">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-medium">{r.nome_ristorante}</span>
                                  <span className="text-xs text-muted-foreground">
                                    {r.ultima_data ? `ultimo: ${formatGiornoMese(r.ultima_data)}` : "mai"}
                                  </span>
                                </div>
                                <ul className="mt-1 space-y-0.5">
                                  {ricaviProblemi(r).map((p, i) => (
                                    <li key={i} className="flex items-start gap-1 text-xs text-foreground/80">
                                      <AlertTriangle className={`size-3.5 mt-0.5 shrink-0 ${r.stato === "critico" ? "text-red-600" : "text-amber-600"}`} />
                                      {p}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ))}
                          </div>
                        )}
                        {it.problemi.length > 0 && (
                        <div className="space-y-2">
                          {ricConProblemi.length > 0 && (
                            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground flex items-center gap-1">
                              <FileText className="size-3.5" /> Fatture
                            </p>
                          )}
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
                        )}
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
