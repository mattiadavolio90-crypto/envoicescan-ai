"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw, DollarSign, Shield, Clock, AlertTriangle, CheckCircle } from "lucide-react";

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
  const timeseries: Record<string, unknown>[] = (data?.timeseries as Record<string, unknown>[]) || [];
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

// ─── TAB INTEGRITÀ ────────────────────────────────────────────────────────────
const LABELS_PROBLEMI: Record<string, string> = {
  date_invalide: "Date invalide",
  importi_estremi: "Importi estremi (>€50k)",
  quantita_negative: "Quantità negative",
  descrizioni_vuote: "Descrizioni vuote",
  totali_errati: "Totali non corrispondenti",
};

function IntegritaTab() {
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [giorni, setGiorni] = useState("90");

  async function runScan() {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/integrita", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ giorni: giorni === "tutti" ? null : Number(giorni) }),
      });
      if (!res.ok) { toast.error("Errore scan"); return; }
      setResult(await res.json());
      toast.success("Scan completato");
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }

  const problemi = (result?.problemi as Record<string, unknown[]>) || {};
  const totale = (result?.totale_problemi as number) || 0;
  const fatture = (result?.fatture_analizzate as number) || 0;

  return (
    <div className="space-y-4">
      <div className="flex gap-2 items-center">
        <Select value={giorni} onValueChange={setGiorni}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="30">Ultimi 30gg</SelectItem>
            <SelectItem value="90">Ultimi 90gg</SelectItem>
            <SelectItem value="180">Ultimi 180gg</SelectItem>
            <SelectItem value="tutti">Tutto lo storico</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={runScan} disabled={loading}>
          <Shield className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Analisi in corso…" : "Verifica integrità"}
        </Button>
      </div>

      {result && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            {totale === 0
              ? <p className="flex items-center gap-2 text-emerald-600 font-medium"><CheckCircle className="size-5" /> Nessun problema trovato su {fatture.toLocaleString()} fatture</p>
              : <p className="flex items-center gap-2 text-amber-600 font-medium"><AlertTriangle className="size-5" /> {totale} problemi trovati su {fatture.toLocaleString()} fatture</p>
            }
          </div>
          {Object.entries(problemi).map(([key, rows]) =>
            rows.length > 0 ? (
              <Card key={key}>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <AlertTriangle className="size-4 text-amber-500" />
                    {LABELS_PROBLEMI[key] || key}
                    <span className="ml-auto text-xs font-normal text-muted-foreground">{rows.length} righe</span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="rounded border overflow-hidden">
                    <table className="w-full text-xs">
                      <tbody className="divide-y">
                        {rows.slice(0, 20).map((r, i) => (
                          <tr key={i} className="hover:bg-muted/20">
                            <td className="px-3 py-1.5 font-medium truncate max-w-[180px]">{String((r as Record<string, unknown>).fornitore || "—")}</td>
                            <td className="px-3 py-1.5 truncate max-w-[180px] text-muted-foreground">{String((r as Record<string, unknown>).descrizione || "—")}</td>
                            <td className="px-3 py-1.5 text-muted-foreground">{String((r as Record<string, unknown>).data || (r as Record<string, unknown>).data_documento || "—")}</td>
                            {(r as Record<string, unknown>).valore !== undefined && <td className="px-3 py-1.5 tabular-nums text-red-600">€{Number((r as Record<string, unknown>).valore).toFixed(2)}</td>}
                            {(r as Record<string, unknown>).diff !== undefined && <td className="px-3 py-1.5 tabular-nums text-amber-600">Δ€{Number((r as Record<string, unknown>).diff).toFixed(2)}</td>}
                          </tr>
                        ))}
                        {rows.length > 20 && <tr><td colSpan={5} className="px-3 py-1.5 text-center text-muted-foreground">… e altre {rows.length - 20}</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

// ─── TAB RETENTION ───────────────────────────────────────────────────────────
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
          {status.error_message && (
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

// ─── ROOT CLIENT ─────────────────────────────────────────────────────────────
const TABS = ["costi", "integrita", "retention"] as const;
const TAB_LABELS: Record<string, string> = { costi: "Costi AI", integrita: "Integrità DB", retention: "Retention" };

export function SistemaClient() {
  const [tab, setTab] = useState<"costi" | "integrita" | "retention">("costi");
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
      {tab === "integrita" && <IntegritaTab />}
      {tab === "retention" && <RetentionTab />}
    </div>
  );
}
