"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw, DollarSign, Shield, Clock, CheckCircle, AlertTriangle } from "lucide-react";

const VISION_DAILY_LIMIT = 50;

// ─── TAB COSTI AI ─────────────────────────────────────────────────────────────
function CostiAiTab() {
  const [days, setDays] = useState("30");
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/sistema/costi-ai?days=${days}`);
      if (!res.ok) { toast.error("Errore caricamento costi"); return; }
      setData(await res.json());
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, [days]);

  useEffect(() => { load(); }, [load]);

  const summary: Record<string, unknown>[] = (data?.summary as Record<string, unknown>[]) || [];
  const visionOggi = data?.vision_oggi_by_ristorante as Record<string, number> || {};

  const totCosti = summary.reduce((s, r) => s + Number(r.ai_cost_total || 0), 0);
  const totPdf = summary.reduce((s, r) => s + Number(r.ai_pdf_count || 0), 0);
  const totCateg = summary.reduce((s, r) => s + Number(r.ai_categorization_count || 0), 0);
  const totTokens = summary.reduce((s, r) => s + Number(r.total_tokens || 0), 0);
  const visionOggiTot = Object.values(visionOggi).reduce((s, v) => s + v, 0);
  const visionPeak = Object.values(visionOggi).reduce((m, v) => Math.max(m, v), 0);

  return (
    <div className="space-y-6">
      <div className="flex gap-2 items-center">
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Ultimi 7gg</SelectItem>
            <SelectItem value="30">Ultimi 30gg</SelectItem>
            <SelectItem value="90">Ultimi 90gg</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: "Costo totale", value: `$${totCosti.toFixed(4)}`, icon: DollarSign, color: "text-violet-600" },
          { label: "Vision (PDF)", value: totPdf.toLocaleString(), icon: Shield, color: "text-sky-600" },
          { label: "Categorizzazioni", value: totCateg.toLocaleString(), icon: CheckCircle, color: "text-emerald-600" },
          { label: "Token totali", value: totTokens.toLocaleString(), icon: Clock, color: "text-orange-600" },
        ].map((k) => (
          <Card key={k.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">{k.label}</CardTitle>
              <k.icon className={`size-4 ${k.color}`} />
            </CardHeader>
            <CardContent><div className="text-xl font-bold tabular-nums">{k.value}</div></CardContent>
          </Card>
        ))}
      </div>

      {/* Vision quota oggi */}
      <Card>
        <CardHeader><CardTitle className="text-sm font-medium">Vision quota oggi</CardTitle></CardHeader>
        <CardContent className="flex gap-6 flex-wrap text-sm">
          <div><p className="text-muted-foreground text-xs">Vision oggi (tot.)</p><p className="text-xl font-bold tabular-nums">{visionOggiTot}</p></div>
          <div><p className="text-muted-foreground text-xs">Limite per ristorante</p><p className="text-xl font-bold tabular-nums">{VISION_DAILY_LIMIT}</p></div>
          <div><p className="text-muted-foreground text-xs">Picco singolo rist.</p><p className={`text-xl font-bold tabular-nums ${visionPeak >= VISION_DAILY_LIMIT * 0.9 ? "text-red-600" : visionPeak >= VISION_DAILY_LIMIT * 0.7 ? "text-amber-600" : ""}`}>{visionPeak}</p></div>
          <div><p className="text-muted-foreground text-xs">Residuo minimo</p><p className="text-xl font-bold tabular-nums">{Math.max(0, VISION_DAILY_LIMIT - visionPeak)}</p></div>
        </CardContent>
      </Card>

      {/* Tabella per cliente */}
      {summary.length > 0 && (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="border-b bg-muted/50 text-left">
              <th className="px-4 py-2 font-medium">Cliente</th>
              <th className="px-4 py-2 font-medium">Vision</th>
              <th className="px-4 py-2 font-medium">Categ.</th>
              <th className="px-4 py-2 font-medium">Costo tot.</th>
              <th className="px-4 py-2 font-medium hidden md:table-cell">Token</th>
              <th className="px-4 py-2 font-medium hidden lg:table-cell">Ultimo uso</th>
            </tr></thead>
            <tbody className="divide-y">
              {summary.map((r, i) => (
                <tr key={i} className="hover:bg-muted/30">
                  <td className="px-4 py-2">
                    <p className="font-medium truncate max-w-[150px]">{String(r.nome_ristorante || "—")}</p>
                    <p className="text-xs text-muted-foreground truncate max-w-[150px]">{String(r.ragione_sociale || "")}</p>
                  </td>
                  <td className="px-4 py-2 tabular-nums">{String(r.ai_pdf_count || 0)}</td>
                  <td className="px-4 py-2 tabular-nums">{String(r.ai_categorization_count || 0)}</td>
                  <td className="px-4 py-2 tabular-nums font-medium">${Number(r.ai_cost_total || 0).toFixed(4)}</td>
                  <td className="px-4 py-2 tabular-nums hidden md:table-cell text-muted-foreground">{Number(r.total_tokens || 0).toLocaleString()}</td>
                  <td className="px-4 py-2 hidden lg:table-cell text-muted-foreground text-xs">{r.ai_last_usage ? new Date(String(r.ai_last_usage)).toLocaleDateString("it-IT") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── TAB RETENTION ───────────────────────────────────────────────────────────
// ─── TAB IMPORT RICAVI ────────────────────────────────────────────────────────
type ImportRicaviItem = {
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

// ── Salute import PER RISTORANTE ──────────────────────────────────────────────
type SaluteRistorante = {
  ristorante_id: string;
  nome_ristorante: string;
  stato: "ok" | "warning" | "critico";
  ultima_data: string | null;
  giorni_silenzio: number | null;
  buchi: string[];
  n_buchi: number;
  coda_problemi: number;
};

const SALUTE_CLASS: Record<string, string> = {
  critico: "border-red-500/40 bg-red-500/5",
  warning: "border-amber-500/40 bg-amber-500/5",
  ok: "border-emerald-500/30 bg-emerald-500/5",
};
const SALUTE_DOT: Record<string, string> = {
  critico: "bg-red-500",
  warning: "bg-amber-500",
  ok: "bg-emerald-500",
};

function formatGiornoMese(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}

function SaluteRistoranteCard({ r }: { r: SaluteRistorante }) {
  const problemi: string[] = [];
  if (r.giorni_silenzio == null) problemi.push("nessun ricavo registrato");
  else if (r.stato === "critico" && r.giorni_silenzio > 0)
    problemi.push(`nessun dato da ${r.giorni_silenzio} giorn${r.giorni_silenzio === 1 ? "o" : "i"}`);
  if (r.n_buchi > 0)
    problemi.push(`${r.n_buchi} giorn${r.n_buchi === 1 ? "o" : "i"} mancant${r.n_buchi === 1 ? "e" : "i"}: ${r.buchi.map(formatGiornoMese).join(", ")}`);
  if (r.coda_problemi > 0)
    problemi.push(`${r.coda_problemi} import bloccat${r.coda_problemi === 1 ? "o" : "i"} in coda`);

  return (
    <div className={`rounded-lg border p-3 ${SALUTE_CLASS[r.stato] || ""}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`size-2.5 rounded-full shrink-0 ${SALUTE_DOT[r.stato] || ""}`} />
          <p className="font-medium truncate">{r.nome_ristorante}</p>
        </div>
        <span className="text-xs text-muted-foreground shrink-0">
          {r.ultima_data ? `ultimo: ${formatGiornoMese(r.ultima_data)}` : "mai"}
        </span>
      </div>
      {r.stato === "ok" ? (
        <p className="mt-1 text-xs text-emerald-600 flex items-center gap-1">
          <CheckCircle className="size-3.5" /> Aggiornato, nessun problema.
        </p>
      ) : (
        <ul className="mt-1.5 space-y-0.5">
          {problemi.map((p, i) => (
            <li key={i} className="flex items-start gap-1 text-xs text-foreground/80">
              <AlertTriangle className={`size-3.5 mt-0.5 shrink-0 ${r.stato === "critico" ? "text-red-600" : "text-amber-600"}`} />
              {p}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ImportRicaviTab() {
  const [items, setItems] = useState<ImportRicaviItem[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [salute, setSalute] = useState<SaluteRistorante[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [resImport, resSalute] = await Promise.all([
        fetch("/api/admin/sistema/ricavi-import"),
        fetch("/api/admin/sistema/ricavi-salute"),
      ]);
      if (!resImport.ok) { toast.error("Errore caricamento import ricavi"); return; }
      const data = await resImport.json();
      setItems((data.items as ImportRicaviItem[]) || []);
      setCounts((data.counts as Record<string, number>) || {});
      if (resSalute.ok) {
        const ds = await resSalute.json();
        setSalute((ds.items as SaluteRistorante[]) || []);
      }
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const totProblemi = Object.values(counts).reduce((s, v) => s + v, 0);
  const saluteProblemi = (salute || []).filter((r) => r.stato !== "ok");

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        {items && totProblemi > 0 && (
          <div className="flex gap-2 text-xs">
            {(["dead", "unknown_sender", "failed"] as const).map((s) =>
              counts[s] ? (
                <span key={s} className={`rounded-full border px-2 py-0.5 font-medium ${IMPORT_STATUS_CLASS[s]}`}>
                  {counts[s]} {IMPORT_STATUS_LABEL[s]}
                </span>
              ) : null
            )}
          </div>
        )}
      </div>

      {/* Salute per ristorante — silenzio, buchi, coda bloccata */}
      {salute && salute.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold">Stato per ristorante</h3>
            {saluteProblemi.length > 0 && (
              <span className="rounded-full border border-red-500/30 bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-600">
                {saluteProblemi.length} con problemi
              </span>
            )}
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {salute.map((r) => <SaluteRistoranteCard key={r.ristorante_id} r={r} />)}
          </div>
        </div>
      )}

      <h3 className="text-sm font-semibold pt-2">Record di coda bloccati</h3>
      {items && items.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-600">
          <CheckCircle className="size-4" /> Tutto ok — nessun import ricavi bloccato.
        </div>
      ) : items && items.length > 0 ? (
        <div className="space-y-2">
          {items.map((it) => (
            <Card key={it.id}>
              <CardContent className="flex flex-col gap-1 py-3">
                <div className="flex items-center justify-between gap-2">
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${IMPORT_STATUS_CLASS[it.status] || ""}`}>
                    {IMPORT_STATUS_LABEL[it.status] || it.status}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {it.created_at ? new Date(it.created_at).toLocaleString("it-IT") : "—"}
                  </span>
                </div>
                <p className="text-sm font-medium">{it.email_sender || "mittente ignoto"}</p>
                <p className="text-xs text-muted-foreground">
                  {it.attachment_name || "—"}
                  {it.email_subject ? ` · ${it.email_subject}` : ""}
                  {it.attempt_count != null && it.max_attempts != null ? ` · tentativi ${it.attempt_count}/${it.max_attempts}` : ""}
                </p>
                {it.last_error && (
                  <p className="flex items-start gap-1 text-xs text-red-600">
                    <AlertTriangle className="size-3.5 mt-0.5 shrink-0" /> {it.last_error}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        loading ? <p className="text-muted-foreground text-sm">Caricamento…</p> : null
      )}

      <p className="text-xs text-muted-foreground">
        Import ricavi via email (Passbi → coda worker). Qui appaiono solo i casi problematici:
        mittente non mappato, in retry o bloccati. Mittente sconosciuto → aggiungere il mapping
        in Ragione sociale / sender map, poi rimettere il record in coda.
      </p>
    </div>
  );
}

// ─── TAB RETENTION ────────────────────────────────────────────────────────────
function RetentionTab() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/retention");
      if (!res.ok) { toast.error("Errore caricamento retention"); return; }
      setStatus(await res.json());
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const lastRun = status?.last_run_at ? new Date(String(status.last_run_at)).toLocaleString("it-IT") : "Mai eseguito";
  const isOk = status?.status === "ok";

  return (
    <div className="space-y-4">
      <Button variant="outline" size="sm" onClick={load} disabled={loading}>
        <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
      </Button>
      {status ? (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Ultimo ciclo", value: lastRun },
            { label: "Righe eliminate", value: String(status.rows_deleted || 0) },
            { label: "Di cui dal cestino", value: String(status.rows_from_trash || 0) },
            { label: "Stato", value: isOk ? "OK" : "Errore" },
          ].map((k) => (
            <Card key={k.label}>
              <CardHeader className="pb-2"><CardTitle className="text-xs font-medium text-muted-foreground">{k.label}</CardTitle></CardHeader>
              <CardContent>
                <p className={`text-sm font-bold ${k.label === "Stato" && !isOk ? "text-red-600" : ""}`}>{k.value}</p>
              </CardContent>
            </Card>
          ))}
          {Boolean(status.error_message) && (
            <div className="col-span-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              {String(status.error_message)}
            </div>
          )}
        </div>
      ) : (
        loading ? <p className="text-muted-foreground text-sm">Caricamento…</p> : null
      )}
      <p className="text-xs text-muted-foreground">La retention gira automaticamente ogni ~24 ore tramite il worker. Elimina fatture con più di 2 anni dalla data documento.</p>
    </div>
  );
}

// (Il pannello "Agent notturno" è stato spostato in Admin → Categorie.)

// ─── ROOT CLIENT ─────────────────────────────────────────────────────────────
const TABS = ["costi", "retention", "import"] as const;
const TAB_LABELS: Record<string, string> = { costi: "Costi AI", retention: "Retention", import: "Import Ricavi" };

export function SistemaClient() {
  const [tab, setTab] = useState<"costi" | "retention" | "import">("costi");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      {tab === "costi" && <CostiAiTab />}
      {tab === "retention" && <RetentionTab />}
      {tab === "import" && <ImportRicaviTab />}
    </div>
  );
}
