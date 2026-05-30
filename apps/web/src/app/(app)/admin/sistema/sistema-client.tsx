"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RefreshCw, DollarSign, Shield, Clock, CheckCircle, Bot, Play, Moon } from "lucide-react";

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

// ─── TAB AGENT NOTTURNO ───────────────────────────────────────────────────────
type AgentStatus = {
  enabled: boolean;
  ora_utc: number;
  last_run_at: string | null;
  last_digest: Record<string, unknown> | null;
  running: boolean;
};

function AgentNotturnoTab() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [running, setRunning] = useState(false);
  const [oraUtc, setOraUtc] = useState("2");

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno");
      if (!res.ok) { toast.error("Errore caricamento stato agent"); return; }
      const d: AgentStatus = await res.json();
      setStatus(d);
      setOraUtc(String(d.ora_utc ?? 2));
    } catch { toast.error("Errore di connessione"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  async function handleToggle(enabled: boolean) {
    setToggling(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno/toggle", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, ora_utc: parseInt(oraUtc) || 2 }),
      });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore"); return; }
      toast.success(enabled ? "Agent notturno abilitato" : "Agent notturno disabilitato");
      load();
    } catch { toast.error("Errore di connessione"); }
    finally { setToggling(false); }
  }

  async function handleEseguiOra() {
    if (!confirm("Eseguire subito l'agent notturno? Classificherà le righe in coda con suggerimenti certi.")) return;
    setRunning(true);
    try {
      const res = await fetch("/api/admin/sistema/agent-notturno/esegui-ora", { method: "POST" });
      const d = await res.json();
      if (!res.ok) { toast.error(d.detail || "Errore avvio"); return; }
      toast.success(d.message || "Agent avviato — ricarica tra qualche secondo");
      setTimeout(load, 5000);
    } catch { toast.error("Errore di connessione"); }
    finally { setRunning(false); }
  }

  const digest = status?.last_digest as Record<string, unknown> | null;
  const oraItaliana = status ? `${((status.ora_utc + 2) % 24).toString().padStart(2, "0")}:00` : "—";

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`size-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Aggiorna
        </Button>
      </div>

      {/* Card principale toggle */}
      <Card className={status?.enabled ? "border-emerald-500/50" : "border-muted"}>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div className="flex items-center gap-2">
            <Moon className={`size-5 ${status?.enabled ? "text-emerald-500" : "text-muted-foreground"}`} />
            <CardTitle className="text-base">Agent Notturno AI</CardTitle>
          </div>
          <div className="flex items-center gap-2">
            {status?.running && (
              <span className="text-xs text-amber-600 font-medium animate-pulse">In esecuzione…</span>
            )}
            <span className={`text-sm font-semibold ${status?.enabled ? "text-emerald-600" : "text-muted-foreground"}`}>
              {status?.enabled ? "Attivo" : "Disattivato"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Classifica automaticamente ogni notte le righe in coda: diciture sicure, sconti/omaggi e
            righe con suggerimento deterministico certo. Tutto viene loggato nel tab Attività AI con possibilità di annullare.
          </p>

          <div className="flex flex-wrap gap-3 items-end">
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">Ora esecuzione (UTC)</label>
              <Select value={oraUtc} onValueChange={setOraUtc}>
                <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Array.from({ length: 24 }, (_, h) => (
                    <SelectItem key={h} value={String(h)}>{String(h).padStart(2, "0")}:00 UTC ({String((h + 2) % 24).padStart(2, "0")}:00 IT)</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2">
              {status?.enabled ? (
                <Button variant="outline" onClick={() => handleToggle(false)} disabled={toggling}>
                  {toggling ? "…" : "Disabilita"}
                </Button>
              ) : (
                <Button onClick={() => handleToggle(true)} disabled={toggling}>
                  <Moon className="size-4 mr-1" />
                  {toggling ? "…" : "Abilita"}
                </Button>
              )}
              <Button variant="outline" onClick={handleEseguiOra} disabled={running || status?.running}>
                <Play className="size-4 mr-1" />
                {running ? "Avvio…" : "Esegui ora"}
              </Button>
            </div>
          </div>

          {status?.enabled && (
            <p className="text-xs text-muted-foreground">
              Esecuzione programmata ogni giorno alle <strong>{oraItaliana} ora italiana</strong> ({status.ora_utc}:00 UTC)
            </p>
          )}
        </CardContent>
      </Card>

      {/* Ultimo digest */}
      {status?.last_run_at && (
        <Card>
          <CardHeader><CardTitle className="text-sm font-medium">Ultima esecuzione</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              {new Date(status.last_run_at).toLocaleString("it-IT", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}
            </p>
            {digest && !digest.errore ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Totale classificate", value: String(digest.classificate ?? "—"), icon: Bot, color: "text-violet-600" },
                  { label: "Auto-review", value: String(digest.auto_review ?? "—"), icon: CheckCircle, color: "text-emerald-600" },
                  { label: "Suggerite", value: String(digest.suggerite ?? "—"), icon: Shield, color: "text-sky-600" },
                  { label: "Errori", value: String(digest.errori ?? "—"), icon: Clock, color: Number(digest.errori) > 0 ? "text-red-600" : "text-muted-foreground" },
                ].map((k) => (
                  <Card key={k.label} className="p-3">
                    <p className="text-xs text-muted-foreground">{k.label}</p>
                    <p className={`text-xl font-bold tabular-nums ${k.color}`}>{k.value}</p>
                  </Card>
                ))}
              </div>
            ) : digest?.errore ? (
              <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                {String(digest.errore)}
              </div>
            ) : null}
            {digest?.elapsed_s !== undefined && (
              <p className="text-xs text-muted-foreground">Durata: {String(digest.elapsed_s)}s</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ─── ROOT CLIENT ─────────────────────────────────────────────────────────────
const TABS = ["costi", "agent", "retention"] as const;
const TAB_LABELS: Record<string, string> = { costi: "Costi AI", agent: "Agent AI", retention: "Retention" };

export function SistemaClient() {
  const [tab, setTab] = useState<"costi" | "agent" | "retention">("costi");
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
      {tab === "agent" && <AgentNotturnoTab />}
      {tab === "retention" && <RetentionTab />}
    </div>
  );
}
