"use client";

import React, { useEffect, useState } from "react";
import {
  RefreshCw,
  Calendar,
  Settings2,
  ShieldCheck,
  Eye,
  ChevronRight,
  Copy,
  Check,
  Info,
  TriangleAlert,
  Sparkles,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { InfoPopover } from "@/components/ui/info-popover";
import type {
  ScoreFornitore,
  ScoreFornitoriResponse,
  ScoreStato,
  ScoreSottometrica,
  MetricaStato,
} from "@/lib/prezzi";

const ANNO_CORRENTE = new Date().getFullYear();
const MESI_FULL = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];

type PeriodoPreset = "anno_corrente" | "mese_specifico" | "personalizzato";

function fmtItDate(iso: string) {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y.slice(2)}`;
}

function fmtEuro(v: number): string {
  return `€ ${new Intl.NumberFormat("it-IT", { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v)}`;
}

function isoDateRange(anno: number, mese: number | null): { data_da: string; data_a: string } {
  if (mese === null) return { data_da: `${anno}-01-01`, data_a: `${anno}-12-31` };
  const mm = String(mese).padStart(2, "0");
  const lastDay = new Date(anno, mese, 0).getDate();
  return { data_da: `${anno}-${mm}-01`, data_a: `${anno}-${mm}-${lastDay}` };
}

// ─── Mappa stato → etichetta + colori (dark UI sobria, no gamification) ──────
const STATO_META: Record<ScoreStato, { label: string; dot: string; text: string; ring: string }> = {
  affidabile:          { label: "Affidabile",        dot: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400", ring: "border-l-emerald-500" },
  da_monitorare:       { label: "Da monitorare",     dot: "bg-amber-400",   text: "text-amber-600 dark:text-amber-400",     ring: "border-l-amber-400" },
  instabile:           { label: "Instabile",         dot: "bg-rose-500",    text: "text-rose-600 dark:text-rose-400",       ring: "border-l-rose-500" },
  provvisorio:         { label: "Provvisorio",       dot: "bg-sky-400",     text: "text-sky-600 dark:text-sky-400",         ring: "border-l-sky-400" },
  dati_insufficienti:  { label: "Dati insufficienti",dot: "bg-muted-foreground/40", text: "text-muted-foreground",         ring: "border-l-border" },
};

function affidabilitaLabel(a: ScoreFornitore["affidabilita_dato"]): string {
  return a === "alta" ? "Affidabilità del dato: alta"
    : a === "media" ? "Affidabilità del dato: media"
    : "Affidabilità del dato: bassa";
}

// Stato per asse: lettura qualitativa, niente voto numerico.
const METRICA_META: Record<MetricaStato, { label: string; dot: string; text: string }> = {
  stabile:        { label: "Stabile",        dot: "bg-emerald-500",         text: "text-emerald-600 dark:text-emerald-400" },
  da_monitorare:  { label: "Da monitorare",  dot: "bg-amber-400",           text: "text-amber-600 dark:text-amber-400" },
  instabile:      { label: "Da verificare",  dot: "bg-rose-500",            text: "text-rose-600 dark:text-rose-400" },
  non_valutabile: { label: "Non valutabile", dot: "bg-muted-foreground/40", text: "text-muted-foreground" },
};

function MetricaRiga({ m }: { m: ScoreSottometrica }) {
  const meta = METRICA_META[m.stato];
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">{m.label}</span>
        <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${meta.text}`}>
          <span className={`size-1.5 rounded-full ${meta.dot}`} />
          {meta.label}
        </span>
      </div>
      <p className="text-xs text-muted-foreground leading-snug">{m.spiegazione}</p>
    </div>
  );
}

// Pastiglia di stato sintetico del fornitore (riga di testa, no numero).
function StatoBadge({ stato, size = "md" }: { stato: ScoreStato; size?: "sm" | "md" }) {
  const meta = STATO_META[stato];
  const cls = size === "sm" ? "text-xs gap-1" : "text-sm gap-1.5";
  return (
    <span className={`inline-flex items-center font-semibold ${cls} ${meta.text}`}>
      <span className={`${size === "sm" ? "size-1.5" : "size-2"} rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}

function CopyButton({ testo }: { testo: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(testo);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Copia non riuscita");
    }
  }
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
    >
      {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
      {copied ? "Copiato" : "Copia"}
    </button>
  );
}

// ─── Dialog dettaglio fornitore ──────────────────────────────────────────────
function DettaglioDialog({
  f,
  open,
  onClose,
}: {
  f: ScoreFornitore | null;
  open: boolean;
  onClose: () => void;
}) {
  if (!f) return null;
  const testoBozza = f.bozza.testo;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto p-6 sm:p-8">
        <DialogHeader className="pr-8">
          <DialogTitle className="flex items-center gap-2 text-lg">
            {f.fornitore}
          </DialogTitle>
          <DialogDescription>
            Lettura della relazione commerciale {f.periodo ? `· ${f.periodo}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* 1. Sintesi relazione */}
          <section className="rounded-lg border border-border bg-card p-5 space-y-2">
            <div className="flex items-center gap-2 flex-wrap">
              <StatoBadge stato={f.stato} />
              <span className="text-xs text-muted-foreground">
                · {affidabilitaLabel(f.affidabilita_dato).replace("Affidabilità del dato: ", "dato ")}
              </span>
            </div>
            <p className="text-sm text-foreground leading-relaxed">{f.frase_sintesi}</p>
          </section>

          {/* Lettura per asse (solo se valutato) */}
          {f.sottometriche.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lettura per area</h3>
              <div className="grid sm:grid-cols-2 gap-x-8 gap-y-5">
                {f.sottometriche.map((m) => <MetricaRiga key={m.chiave} m={m} />)}
              </div>
            </section>
          )}

          {/* 2. Segnali osservati */}
          {f.segnali.length > 0 && (
            <section className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Segnali osservati</h3>
              <ul className="space-y-2.5">
                {f.segnali.map((s, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm leading-relaxed">
                    {s.tono === "positivo" ? (
                      <Sparkles className="size-4 text-emerald-500 mt-0.5 shrink-0" />
                    ) : s.tono === "neutro" ? (
                      <Info className="size-4 text-sky-500 mt-0.5 shrink-0" />
                    ) : (
                      <TriangleAlert className="size-4 text-amber-500 mt-0.5 shrink-0" />
                    )}
                    <span className="text-foreground">{s.testo}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* Limiti del dato */}
          <section className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground space-y-1.5">
            <p className="flex items-center gap-1.5 font-medium text-foreground">
              <Info className="size-3.5" /> Limiti del dato
            </p>
            <p>
              Basato su {f.n_fatture} document{f.n_fatture === 1 ? "o" : "i"}, {f.n_prodotti} prodott{f.n_prodotti === 1 ? "o" : "i"},
              {" "}{f.mesi_coperti} mes{f.mesi_coperti === 1 ? "e" : "i"} coperti{f.periodo ? ` (${f.periodo})` : ""}.
              Spesa nel periodo: {fmtEuro(f.spesa_periodo)}.
            </p>
            <p className="leading-relaxed">
              Questa lettura non è un giudizio sul listino né un confronto col mercato: dice solo
              quanto la relazione con questo fornitore è stata stabile e leggibile nel tempo, sui tuoi dati.
            </p>
          </section>

          {/* 3. Bozza trattativa — solo se c'è qualcosa da negoziare */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Bozza di confronto</h3>
            {f.bozza.attiva ? (
              <>
                <p className="text-xs text-muted-foreground">Testo suggerito da copiare e usare come preferisci (mail, messaggio, telefonata). Nessun invio automatico.</p>
                <div className="rounded-lg border border-border bg-muted/20 p-4">
                  <pre className="whitespace-pre-wrap break-words font-sans text-sm text-foreground leading-relaxed">{testoBozza}</pre>
                  <div className="mt-4 flex justify-end">
                    <CopyButton testo={testoBozza} />
                  </div>
                </div>
              </>
            ) : (
              <div className="flex items-start gap-2.5 rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
                <Sparkles className="size-4 text-emerald-500 mt-0.5 shrink-0" />
                <p>{f.bozza.motivo || "Non emergono motivi per una trattativa con questo fornitore."}</p>
              </div>
            )}
          </section>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Etichette brevi degli assi per la striscia compatta in lista.
const ASSE_BREVE: Record<ScoreSottometrica["chiave"], string> = {
  stabilita: "Prezzi",
  coerenza: "Condizioni",
  impatto: "Impatto",
  documentale: "Documenti",
};

// ─── Riga fornitore nella lista ──────────────────────────────────────────────
function FornitoreRow({ f, onOpen }: { f: ScoreFornitore; onOpen: () => void }) {
  const meta = STATO_META[f.stato];
  return (
    <div className={`rounded-lg border border-l-4 ${meta.ring} border-border bg-card overflow-hidden`}>
      <div className="flex items-center gap-4 px-4 py-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-semibold text-sm truncate">{f.fornitore}</p>
            <StatoBadge stato={f.stato} size="sm" />
          </div>
          <p className="text-xs text-muted-foreground truncate">{f.frase_sintesi}</p>
          {/* Striscia per asse: dove sta l'attenzione, a colpo d'occhio */}
          {f.sottometriche.length > 0 && (
            <div className="flex flex-wrap gap-x-3 gap-y-1 pt-0.5">
              {f.sottometriche.map((m) => {
                const mm = METRICA_META[m.stato];
                return (
                  <span key={m.chiave} className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                    <span className={`size-1.5 rounded-full ${mm.dot}`} />
                    {ASSE_BREVE[m.chiave]}
                  </span>
                );
              })}
            </div>
          )}
          <p className="text-[11px] text-muted-foreground/80">
            {f.n_fatture} fatt. · {f.n_prodotti} prod. · {f.periodo || "—"}
          </p>
        </div>
        <button
          onClick={onOpen}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted shrink-0"
        >
          <Eye className="size-3.5" />
          Dettagli
          <ChevronRight className="size-3.5" />
        </button>
      </div>
    </div>
  );
}

export function ScoreTab() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null);
  const [preset, setPreset] = useState<PeriodoPreset>("anno_corrente");
  const [dataDaCustom, setDataDaCustom] = useState("");
  const [dataACustom, setDataACustom] = useState("");
  const [showMese, setShowMese] = useState(false);
  const [showCustom, setShowCustom] = useState(false);
  const [data, setData] = useState<ScoreFornitoriResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [selected, setSelected] = useState<ScoreFornitore | null>(null);

  async function load(da?: string, a?: string) {
    setLoading(true);
    setError(false);
    try {
      let data_da: string;
      let data_a: string;
      if (da && a) {
        data_da = da; data_a = a;
      } else {
        const r = isoDateRange(anno, mese);
        data_da = r.data_da; data_a = r.data_a;
      }
      const qs = new URLSearchParams({ data_da, data_a });
      const res = await fetch(`/api/prezzi/score-fornitori?${qs}`);
      if (!res.ok) throw new Error();
      setData(await res.json());
    } catch {
      setError(true);
      toast.error("Errore nel caricamento dello score fornitori");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  function applyAnno() {
    setPreset("anno_corrente");
    setMese(null);
    setShowMese(false);
    setShowCustom(false);
    const r = isoDateRange(ANNO_CORRENTE, null);
    setAnno(ANNO_CORRENTE);
    load(r.data_da, r.data_a);
  }
  function applyMese(yearMonth: string) {
    if (!yearMonth) return;
    const [y, m] = yearMonth.split("-").map(Number);
    setAnno(y);
    setMese(m);
    setPreset("mese_specifico");
    const r = isoDateRange(y, m);
    load(r.data_da, r.data_a);
  }
  function applyCustom(da: string, a: string) {
    if (!da || !a) return;
    setPreset("personalizzato");
    load(da, a);
  }

  const fornitori = data?.fornitori ?? [];
  const valutati = fornitori.filter((f) => f.score !== null);
  const insufficienti = fornitori.filter((f) => f.score === null);

  const chipBase = "px-3 py-1.5 text-xs font-medium rounded-full border transition-colors inline-flex items-center gap-1";
  const chipActive = "bg-primary text-primary-foreground border-primary";
  const chipIdle = "bg-background border-input hover:bg-muted";

  return (
    <div className="space-y-4">
      {/* Filtro periodo (coerente con gli altri tab) */}
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {(["anno_corrente", "mese_specifico", "personalizzato"] as PeriodoPreset[]).map((p) => {
            const labels: Record<PeriodoPreset, React.ReactNode> = {
              anno_corrente: "Anno in corso",
              mese_specifico: <><Calendar className="size-3 inline mr-1" />Seleziona mese</>,
              personalizzato: <><Settings2 className="size-3 inline mr-1" />Personalizzato</>,
            };
            return (
              <button
                key={p}
                onClick={() => {
                  if (p === "anno_corrente") applyAnno();
                  else if (p === "mese_specifico") { setShowMese(true); setShowCustom(false); setPreset("mese_specifico"); }
                  else { setShowCustom(true); setShowMese(false); setPreset("personalizzato"); }
                }}
                className={`${chipBase} ${preset === p ? chipActive : chipIdle}`}
              >
                {labels[p]}
              </button>
            );
          })}
          {preset === "personalizzato" && dataDaCustom && dataACustom && (
            <span className="ml-2 text-xs font-medium text-sky-500 dark:text-sky-400">
              {fmtItDate(dataDaCustom)} → {fmtItDate(dataACustom)}
            </span>
          )}
          <button
            onClick={() => load()}
            disabled={loading}
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Aggiorna
          </button>
        </div>

        {showMese && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Mese:</span>
            <select
              value={mese != null ? `${anno}-${String(mese).padStart(2, "0")}` : ""}
              onChange={(e) => applyMese(e.target.value)}
              className="h-7 text-xs rounded-md border border-input bg-background px-2"
            >
              <option value="" disabled>Seleziona un mese</option>
              {Array.from({ length: 4 }, (_, i) => ANNO_CORRENTE - i).flatMap((y) =>
                MESI_FULL.map((label, mi) => {
                  const val = `${y}-${String(mi + 1).padStart(2, "0")}`;
                  return <option key={val} value={val}>{label} {y}</option>;
                })
              )}
            </select>
          </div>
        )}

        {showCustom && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Dal</span>
            <input
              type="date"
              value={dataDaCustom}
              onChange={(e) => { setDataDaCustom(e.target.value); applyCustom(e.target.value, dataACustom); }}
              className="h-7 text-xs rounded-md border border-input bg-background px-2 w-36"
            />
            <span className="text-xs text-muted-foreground">al</span>
            <input
              type="date"
              value={dataACustom}
              onChange={(e) => { setDataACustom(e.target.value); applyCustom(dataDaCustom, e.target.value); }}
              className="h-7 text-xs rounded-md border border-input bg-background px-2 w-36"
            />
          </div>
        )}
      </div>

      {/* Nota sul significato — spiegabilità prima di tutto */}
      {data && fornitori.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <ShieldCheck className="size-4 text-sky-500 mt-0.5 shrink-0" />
          <p className="flex-1">
            Per ogni fornitore leggi quanto è stato <span className="text-foreground">stabile, coerente
            e leggibile</span> nel tempo sui tuoi acquisti, area per area. Non è un voto sul listino
            né un confronto col mercato.
          </p>
          <div className="-my-1.5 -mr-1.5 shrink-0">
            <InfoPopover title="Come funziona lo Score Fornitori" ariaLabel="Come funziona lo Score Fornitori" align="end">
              <p className="text-muted-foreground">
                Quanto un fornitore è stato <strong className="text-foreground">stabile e leggibile nel tempo</strong>, solo dalle tue fatture. Niente confronti col mercato o con altri ristoranti.
              </p>
              <div className="space-y-1.5 text-muted-foreground">
                <p><strong className="text-foreground">Prezzi</strong> = quanto oscillano i prezzi che paghi.</p>
                <p><strong className="text-foreground">Condizioni</strong> = se sconti e omaggi restano costanti.</p>
                <p><strong className="text-foreground">Impatto</strong> = quanto i rincari pesano sulla spesa con lui.</p>
                <p><strong className="text-foreground">Documenti</strong> = note di credito e storni (un segnale, non una colpa).</p>
              </div>
              <div className="border-t border-border pt-2 space-y-1.5 text-muted-foreground">
                <p>Ogni area è <span className="text-emerald-600 dark:text-emerald-400 font-medium">Stabile</span>, <span className="text-amber-600 dark:text-amber-400 font-medium">Da monitorare</span> o <span className="text-rose-600 dark:text-rose-400 font-medium">Da verificare</span>. Lo stato in alto non è mai più ottimista dell&apos;area peggiore.</p>
                <p>Con pochi dati mostra <em>Dati insufficienti</em> o <em>Provvisorio</em>: meglio nessun giudizio che uno sbagliato.</p>
              </div>
            </InfoPopover>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 rounded-lg border border-border bg-card animate-pulse" />
          ))}
        </div>
      )}

      {/* Errore */}
      {!loading && error && (
        <div className="rounded-lg border border-rose-500/40 bg-card py-10 text-center">
          <TriangleAlert className="size-7 text-rose-500 mx-auto mb-2" />
          <p className="text-sm font-medium">Non sono riuscito a calcolare lo score</p>
          <button onClick={() => load()} className="mt-3 text-xs text-primary hover:underline">Riprova</button>
        </div>
      )}

      {/* Empty totale */}
      {!loading && !error && data && fornitori.length === 0 && (
        <div className="rounded-lg border border-dashed border-border py-12 text-center">
          <ShieldCheck className="size-8 text-muted-foreground/50 mx-auto mb-2" />
          <p className="text-sm font-medium">Non ci sono ancora abbastanza dati per uno score affidabile</p>
          <p className="text-xs text-muted-foreground mt-1">
            Servono più fatture nel periodo per leggere la relazione con i fornitori.
          </p>
        </div>
      )}

      {/* Lista fornitori valutati */}
      {!loading && !error && valutati.length > 0 && (
        <div className="space-y-2">
          {valutati.map((f) => (
            <FornitoreRow key={f.fornitore} f={f} onOpen={() => setSelected(f)} />
          ))}
        </div>
      )}

      {/* Fornitori con dati insufficienti, in coda e visivamente attenuati */}
      {!loading && !error && insufficienti.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground pt-2">
            Storico troppo limitato per un giudizio ({insufficienti.length})
          </p>
          {insufficienti.map((f) => (
            <FornitoreRow key={f.fornitore} f={f} onOpen={() => setSelected(f)} />
          ))}
        </div>
      )}

      <DettaglioDialog f={selected} open={selected !== null} onClose={() => setSelected(null)} />
    </div>
  );
}
