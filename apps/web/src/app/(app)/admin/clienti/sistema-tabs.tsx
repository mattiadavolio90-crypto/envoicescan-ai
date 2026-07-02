"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw, DollarSign, Shield, Clock, CheckCircle } from "lucide-react";

const VISION_DAILY_LIMIT = 50;

// ─── TAB COSTI AI ─────────────────────────────────────────────────────────────
export function CostiAiTab() {
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

// ─── TAB RETENTION ────────────────────────────────────────────────────────────
export function RetentionTab() {
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
      <p className="text-xs text-muted-foreground">La retention gira automaticamente ogni ~24 ore tramite il worker. Elimina fatture con più di 2 anni dalla data documento (cestino incluso). Qui controlli solo che il job notturno stia girando.</p>
    </div>
  );
}

// ─── TAB SALUTE WORKER (spia latenza / saturazione) ───────────────────────────
type SwRoute = { route: string; count: number; p50_ms: number; p95_ms: number; max_ms: number; slow: number; errors: number };

export function SaluteWorkerTab() {
  const [data, setData] = useState<{ routes: SwRoute[]; totale: { count: number; slow: number; errors: number }; slow_soglia_ms: number } | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/salute-worker");
      if (!res.ok) { toast.error("Errore caricamento salute worker"); return; }
      setData(await res.json());
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const soglia = data?.slow_soglia_ms ?? 4000;
  const routes = data?.routes ?? [];
  const tot = data?.totale ?? { count: 0, slow: 0, errors: 0 };

  // Colore p95: verde < metà soglia, ambra fino a soglia, rosso oltre.
  const p95Color = (ms: number) =>
    ms >= soglia ? "text-red-600" : ms >= soglia / 2 ? "text-amber-600" : "text-emerald-600";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
        <p className="text-xs text-muted-foreground">
          Misura la velocità del worker. Se il <b>p95</b> di una rotta si avvicina a {(soglia / 1000).toFixed(0)}s è ora di potenziare Railway.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Richieste (dal riavvio)", value: tot.count.toLocaleString(), warn: false },
          { label: `Lente (> ${(soglia / 1000).toFixed(0)}s)`, value: tot.slow.toLocaleString(), warn: tot.slow > 0 },
          { label: "Errori (5xx)", value: tot.errors.toLocaleString(), warn: tot.errors > 0 },
        ].map((k) => (
          <Card key={k.label}>
            <CardHeader className="pb-2"><CardTitle className="text-xs font-medium text-muted-foreground">{k.label}</CardTitle></CardHeader>
            <CardContent><p className={`text-xl font-bold tabular-nums ${k.warn ? "text-red-600" : ""}`}>{k.value}</p></CardContent>
          </Card>
        ))}
      </div>

      {routes.length > 0 ? (
        <div className="rounded-md border overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="text-left font-medium px-3 py-2">Rotta</th>
                <th className="text-right font-medium px-3 py-2">Richieste</th>
                <th className="text-right font-medium px-3 py-2">p50</th>
                <th className="text-right font-medium px-3 py-2">p95</th>
                <th className="text-right font-medium px-3 py-2">max</th>
                <th className="text-right font-medium px-3 py-2">lente</th>
                <th className="text-right font-medium px-3 py-2">errori</th>
              </tr>
            </thead>
            <tbody>
              {routes.map((r) => (
                <tr key={r.route} className="border-t">
                  <td className="px-3 py-2 font-mono text-xs">{r.route}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.count.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.p50_ms} ms</td>
                  <td className={`px-3 py-2 text-right tabular-nums font-semibold ${p95Color(r.p95_ms)}`}>{r.p95_ms} ms</td>
                  <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{r.max_ms} ms</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${r.slow > 0 ? "text-amber-600 font-semibold" : "text-muted-foreground"}`}>{r.slow}</td>
                  <td className={`px-3 py-2 text-right tabular-nums ${r.errors > 0 ? "text-red-600 font-semibold" : "text-muted-foreground"}`}>{r.errors}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        loading ? <p className="text-muted-foreground text-sm">Caricamento…</p> :
        <p className="text-muted-foreground text-sm">Ancora nessuna richiesta misurata su questo processo.</p>
      )}

      <p className="text-xs text-muted-foreground">
        Dati per-processo, azzerati a ogni riavvio del worker. p50 = tempo tipico, p95 = i casi peggiori (quelli che generano la schermata &quot;servizio non raggiungibile&quot;). Verde = sano, ambra = attenzione, rosso = oltre soglia.
      </p>
    </div>
  );
}
