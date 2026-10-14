"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import {
  Plus, X, RefreshCw, Download, ChevronDown, ChevronUp,
  Search, Check, Trash2, Tags, Lightbulb, Calendar, Settings2, Pencil, Star,
} from "lucide-react";
import { toast } from "sonner";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer,
} from "recharts";
import { InfoPopover } from "@/components/ui/info-popover";
import { Button } from "@/components/ui/button";
import { TitoloApribile } from "@/components/tag/titolo-apribile";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { NativeSelect } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { mostraGuasto } from "@/lib/esito-caricamento";
import { formatEuro } from "@/lib/format";
import { intervalloPeriodo } from "@/lib/periodo";
import { type PeriodoPreset, periodoScelto } from "@/lib/tag-periodo";
import type {
  CartellaTag, CustomTag, TagSuggestion, TagAnalisiResponse, TagProdotto,
} from "@/lib/tag";
import { EMOJI_TAG } from "@/lib/tag";
import { etichettaProdotti } from "@/lib/tag-selezione";
import {
  type VistaTag,
  leggiStatoComodo, primoTagMostrato, raggruppa, scriviStatoComodo, soloPreferiti,
} from "@/lib/tag-cartelle";
import { PannelloTag } from "@/components/tag/pannello-tag";
import { ModificaTagDialog } from "@/components/tag/modifica-tag-dialog";
import { sorgenteSede } from "@/lib/tag-sorgenti";

// Vista scelta e cartelle chiuse: comodita' di chi guarda, per browser. Lo stato
// vero (cartelle, stelle) sta nel DB.
const CHIAVE_STATO_COMODO = "oneflux:analisi-e-tag:barra";

function leggiStorage(): string | null {
  try {
    return window.localStorage.getItem(CHIAVE_STATO_COMODO);
  } catch {
    return null;
  }
}

function scriviStorage(valore: string) {
  try {
    window.localStorage.setItem(CHIAVE_STATO_COMODO, valore);
  } catch {
    // Finestra privata o storage bloccato: la barra funziona lo stesso.
  }
}

function primoDaMostrare(tags: CustomTag[], cartelle: CartellaTag[], vista: VistaTag, chiuse: number[]) {
  return primoTagMostrato(vista, raggruppa(tags, cartelle), soloPreferiti(tags), chiuse);
}

const ANNO_CORRENTE = new Date().getFullYear();
const MESI_FULL = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];


// Guscio sulla fonte unica (lib/periodo): qui le chiavi si chiamano `da`/`a`
// e tre call site le destrutturano cosi'. Rinominarle sarebbe un cambiamento
// piu' grande del difetto che risolve; la MATEMATICA e' una sola.
function isoRange(anno: number, mese: number | null) {
  const { data_da, data_a } = intervalloPeriodo(anno, mese);
  return { da: data_da, a: data_a };
}

/* ── Filtro periodo: nella testata del riquadro del tag ── */
function FiltroPeriodoTag({
  anno, mese, dataDa, dataA, preset, onChange,
}: {
  anno: number;
  mese: number | null;
  dataDa: string | null;
  dataA: string | null;
  preset: PeriodoPreset;
  onChange: (v: { anno: number; mese: number | null; preset: PeriodoPreset; dataDa?: string; dataA?: string }) => void;
}) {
  function scegli(v: PeriodoPreset) {
    const nuovo = periodoScelto(v, { anno, mese, preset, dataDa, dataA }, new Date());
    if (nuovo) onChange(nuovo);
  }

  const annoOggi = new Date().getFullYear();

  function applyMese(yearMonth: string) {
    if (!yearMonth) return;
    const [y, m] = yearMonth.split("-").map(Number);
    onChange({ anno: y, mese: m, preset: "mese_specifico" });
  }

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Periodo</span>
      <SegmentedControl
        aria-label="Periodo dell'analisi"
        value={preset}
        onChange={scegli}
        options={[
          { value: "anno_corrente", label: "Anno in corso" },
          { value: "mese_specifico", label: <><Calendar /> Mese</> },
          { value: "personalizzato", label: <><Settings2 /> Personalizzato</> },
        ]}
      />
      {preset === "mese_specifico" && (
        <NativeSelect
          aria-label="Mese"
          value={mese != null ? `${anno}-${String(mese).padStart(2, "0")}` : ""}
          onValueChange={applyMese}
          className="h-7 w-44 text-xs"
        >
          {Array.from({ length: 4 }, (_, i) => annoOggi - i).flatMap(y =>
            MESI_FULL.map((label, mi) => {
              const val = `${y}-${String(mi + 1).padStart(2, "0")}`;
              return <option key={val} value={val}>{label} {y}</option>;
            })
          )}
        </NativeSelect>
      )}
      {preset === "personalizzato" && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>Dal</span>
          <Input
            type="date"
            aria-label="Dal"
            value={dataDa ?? ""}
            onChange={e => onChange({ anno, mese, preset: "personalizzato", dataDa: e.target.value || undefined, dataA: dataA ?? undefined })}
            className="h-7 w-36 text-xs"
          />
          <span>al</span>
          <Input
            type="date"
            aria-label="Al"
            value={dataA ?? ""}
            onChange={e => onChange({ anno, mese, preset: "personalizzato", dataDa: dataDa ?? undefined, dataA: e.target.value || undefined })}
            className="h-7 w-36 text-xs"
          />
        </div>
      )}
    </div>
  );
}

function fmtEuro(v: number) {
  // Simbolo in coda, come il resto del prodotto (lib/format): qui stava in testa.
  return formatEuro(v, 2);
}
function fmtPct(v: number, signed = false) {
  return `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtData(s: string) {
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

const TOOLTIP_STYLE = {
  backgroundColor: "var(--card)",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  fontSize: 11,
  color: "var(--foreground)",
};

/* ── Componenti KPI ── */
function KpiCard({ label, value, sub, tone, className }: { label: string; value: string; sub?: string; tone: string; className?: string }) {
  return (
    <div className={cn(`rounded-lg border ${tone} bg-card px-4 pt-3 pb-2.5 flex flex-col gap-1 min-w-0 transition-colors`, className)}>
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium leading-tight min-h-[28px] flex items-start">{label}</p>
      <p className="text-xl font-bold tracking-tight truncate" title={value}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

// Dove sta ciascuno dei cinque numeri, perche' nessuna riga resti a meta'. Stretto
// (2 colonne): il totale da solo, poi 2+2. Medio (6): 3+2, gli ultimi due piu'
// larghi. Largo (5): tutti in fila. Le larghezze sono del riquadro, non dello schermo.
const KPI_POSTI = [
  "col-span-2 @lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-3 @3xl:col-span-1",
  "@lg:col-span-3 @3xl:col-span-1",
] as const;

/* ── Grafico trend ── */
function TrendChart({ punti, media }: { punti: { data: string; prezzo: number; var_perc: number }[]; media: number }) {
  if (punti.length < 2) return (
    <p className="text-sm text-muted-foreground py-6 text-center">Dati insufficienti per il grafico</p>
  );
  const data = punti.map(p => ({
    data: fmtData(p.data),
    prezzo: p.prezzo,
    var_perc: p.var_perc,
  }));
  const maxAbs = Math.max(...data.map(d => Math.abs(d.var_perc)), 1);
  const domain: [number, number] = [-Math.ceil(maxAbs * 1.2), Math.ceil(maxAbs * 1.2)];
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">
        Media periodo: <span className="font-semibold text-foreground">{fmtEuro(media)}</span>
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 8, right: 46, bottom: 4, left: 8 }}>
          <XAxis dataKey="data" tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false} />
          <YAxis domain={domain} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} tickLine={false} axisLine={false}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`} />
          <Tooltip
            formatter={(v) => {
              const n = typeof v === "number" ? v : 0;
              return [`${n > 0 ? "+" : ""}${n.toFixed(1)}%`, "Variazione vs media"];
            }}
            labelStyle={{ fontSize: 11, color: "var(--muted-foreground)" }}
            itemStyle={{ color: "var(--foreground)" }}
            contentStyle={TOOLTIP_STYLE}
          />
          <ReferenceLine y={0} stroke="var(--muted-foreground)" strokeDasharray="4 4" strokeWidth={1.5}
            label={{ value: "Media", position: "right", fontSize: 10, fill: "var(--muted-foreground)" }} />
          <Line type="monotone" dataKey="var_perc" stroke="var(--primary)" strokeWidth={2}
            dot={{ r: 3, fill: "var(--primary)" }} activeDot={{ r: 5, fill: "var(--primary)", stroke: "var(--card)", strokeWidth: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Card suggerimento espandibile ── */
function SuggestionCard({
  s, onAccepted, onDismissed,
}: {
  s: TagSuggestion;
  onAccepted: () => void;
  onDismissed: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [tagName, setTagName] = useState(
    s.suggestion_type === "new_tag" ? (s.suggested_tag_name ?? "") : (s.tag_name ?? "")
  );
  const [selected, setSelected] = useState<Set<string>>(
    new Set(s.items.map(i => i.descrizione_key))
  );
  // Un tag accettato da qui nasceva SEMPRE senza emoji: il backend riceveva
  // `emoji=None` cablato e il selettore esisteva solo nella creazione manuale,
  // quindi l'unico rimedio era riaprire il tag e modificarlo a mano.
  const [emoji, setEmoji] = useState("");
  const [acting, setActing] = useState(false);

  function toggleItem(key: string) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleAll() {
    setSelected(prev =>
      prev.size === s.items.length ? new Set() : new Set(s.items.map(i => i.descrizione_key))
    );
  }

  async function accept() {
    if (selected.size === 0) { toast.error("Seleziona almeno un prodotto"); return; }
    setActing(true);
    try {
      // Senza descrizioni_key il backend ricadeva su selected_by_default (sempre
      // true) e associava TUTTI i prodotti, comprese le righe deselezionate qui.
      const descrizioni_key = s.items
        .map((i) => i.descrizione_key)
        .filter((k) => selected.has(k));
      const body = s.suggestion_type === "new_tag"
        ? { suggestion_type: "new_tag", tag_name: tagName.trim() || s.suggested_tag_name, emoji: emoji || null, descrizioni_key }
        : { suggestion_type: "extend_tag", tag_id: s.target_tag_id, descrizioni_key };
      const res = await fetch(`/api/tag/suggestions/${s.id}/accept`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      toast.success(
        s.suggestion_type === "new_tag"
          ? `Tag "${tagName || s.suggested_tag_name}" creato`
          : `Prodotti aggiunti al tag "${s.tag_name ?? "esistente"}"`
      );
      onAccepted();
    } catch {
      toast.error("Errore nell'accettazione");
    } finally {
      setActing(false);
    }
  }

  async function dismiss() {
    setActing(true);
    try {
      await fetch(`/api/tag/suggestions/${s.id}/dismiss`, { method: "POST" });
      toast.success("Suggerimento ignorato");
      onDismissed();
    } catch {
      toast.error("Errore");
    } finally {
      setActing(false);
    }
  }

  const isNewTag = s.suggestion_type === "new_tag";

  return (
    <div className="rounded-xl border border-incerto/30 bg-card overflow-hidden">
      {/* Header cliccabile */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full text-left px-4 py-3 hover:bg-incerto/5 transition-colors"
      >
        <div className="flex items-start justify-between gap-3 min-w-0">
          <div className="min-w-0">
            <p className="text-sm font-semibold">
              {isNewTag ? `Crea tag "${s.suggested_tag_name}"` : `Aggiungi al tag "${s.tag_name ?? "esistente"}"`}
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {s.matched_products_count} prodott{s.matched_products_count === 1 ? "o" : "i"} ·{" "}
              {s.matched_rows_count} acquist{s.matched_rows_count === 1 ? "o" : "i"} negli ultimi 30 giorni
            </p>
            {!expanded && (
              <p className="text-xs text-muted-foreground mt-1 truncate" title={s.items.slice(0, 3).map(i => i.descrizione).join(" · ")}>
                {s.items.slice(0, 3).map(i => i.descrizione).join(" · ")}
                {s.items.length > 3 && ` + altri ${s.items.length - 3}`}
              </p>
            )}
          </div>
          {expanded ? <ChevronUp className="size-4 text-muted-foreground shrink-0 mt-0.5" /> : <ChevronDown className="size-4 text-muted-foreground shrink-0 mt-0.5" />}
        </div>
      </button>

      {/* Dettaglio espanso */}
      {expanded && (
        <div className="border-t border-incerto/20 px-4 pb-4 pt-3 space-y-3">
          {/* Nome tag modificabile */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              {isNewTag ? "Nome del nuovo tag" : "Tag di destinazione"}
            </label>
            <input
              className="w-full rounded-md border border-border px-3 py-1.5 text-sm bg-background font-medium"
              value={tagName}
              onChange={e => setTagName(e.target.value)}
              disabled={!isNewTag}
              placeholder="Nome tag…"
            />
          </div>

          {/* Emoji: solo per un tag NUOVO. Su extend_tag il tag esiste gia' e ha
              la sua, sceglierne un'altra qui la sovrascriverebbe di nascosto. */}
          {isNewTag && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Emoji <span className="normal-case font-normal">(opzionale)</span>
              </label>
              <div className="flex flex-wrap gap-1">
                {EMOJI_TAG.map(em => (
                  <button
                    key={em}
                    type="button"
                    aria-pressed={emoji === em}
                    onClick={() => setEmoji(prev => (prev === em ? "" : em))}
                    className={`w-8 h-8 text-base rounded-md border transition-colors flex items-center justify-center ${
                      emoji === em ? "border-primary bg-primary/10" : "border-border hover:bg-muted"
                    }`}
                  >
                    {em}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Lista prodotti con checkbox */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                Prodotti ({selected.size}/{s.items.length} selezionati)
              </label>
              <button
                type="button"
                onClick={toggleAll}
                className="text-xs text-primary hover:underline"
              >
                {selected.size === s.items.length ? "Deseleziona tutti" : "Seleziona tutti"}
              </button>
            </div>
            <div className="rounded-lg border border-border divide-y divide-border max-h-52 overflow-y-auto">
              {s.items.map(item => {
                const sel = selected.has(item.descrizione_key);
                return (
                  <button
                    key={item.descrizione_key}
                    type="button"
                    onClick={() => toggleItem(item.descrizione_key)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors hover:bg-muted/40 ${sel ? "" : "opacity-50"}`}
                  >
                    <span className={`size-4 rounded border flex items-center justify-center shrink-0 transition-colors ${sel ? "bg-primary border-primary" : "border-border"}`}>
                      {sel && <Check className="size-2.5 text-primary-foreground" />}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-medium" title={item.descrizione}>{item.descrizione}</span>
                    <span className="text-xs text-muted-foreground shrink-0">{item.occorrenze} occ.</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Azioni */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={accept}
              disabled={acting || selected.size === 0}
              className="flex-1 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {acting ? "…" : isNewTag ? `✓ Crea tag` : `✓ Aggiungi al tag`}
            </button>
            <button
              onClick={dismiss}
              disabled={acting}
              className="px-4 py-2 text-sm rounded-lg border border-border hover:bg-muted disabled:opacity-50 transition-colors"
            >
              Ignora
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Banner Suggerimenti ── */
function SuggerimentiBanner({
  suggestions, onRefresh, refreshing, aperto, onChiudi,
}: {
  suggestions: TagSuggestion[];
  onRefresh: () => void;
  refreshing: boolean;
  aperto: boolean;
  onChiudi: () => void;
}) {
  const [mostraTutti, setMostraTutti] = useState(false);
  const [query, setQuery] = useState("");

  const filtrati = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return suggestions;
    return suggestions.filter(s => {
      const nome = (s.suggestion_type === "new_tag" ? s.suggested_tag_name : s.tag_name) || "";
      if (nome.toLowerCase().includes(q)) return true;
      return (s.items || []).some(i => i.descrizione.toLowerCase().includes(q));
    });
  }, [suggestions, query]);

  if (suggestions.length === 0 || !aperto) return null;

  // Con una ricerca attiva si mostra tutto cio' che combacia: nascondere i
  // risultati dietro un "mostra altri" vanificherebbe la ricerca stessa.
  const visibili = query.trim() || mostraTutti ? filtrati : filtrati.slice(0, 5);
  const nascosti = filtrati.length - visibili.length;

  return (
    <div className="rounded-xl border border-incerto/40 bg-incerto/8 p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Lightbulb className="size-4 text-incerto shrink-0" />
          <span className="text-sm font-semibold text-incerto">
            {suggestions.length} suggeriment{suggestions.length === 1 ? "o" : "i"} intelligent{suggestions.length === 1 ? "e" : "i"}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="p-1.5 rounded-md hover:bg-incerto/10 transition-colors text-incerto disabled:opacity-50"
            title="Aggiorna suggerimenti"
          >
            <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={onChiudi}
            className="p-1.5 rounded-md hover:bg-incerto/10 transition-colors text-incerto"
            title="Chiudi suggerimenti"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </div>

      {suggestions.length > 5 && (
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground pointer-events-none" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Cerca fra i suggerimenti…"
            className="w-full rounded-md border border-incerto/30 bg-background/60 pl-8 pr-3 py-1.5 text-sm"
          />
        </div>
      )}

      {filtrati.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">Nessun suggerimento per «{query.trim()}».</p>
      ) : (
        <div className="space-y-2">
          {visibili.map(s => (
            <SuggestionCard key={s.id} s={s} onAccepted={onRefresh} onDismissed={onRefresh} />
          ))}
        </div>
      )}

      {!query.trim() && (nascosti > 0 || mostraTutti) && (
        <button
          onClick={() => setMostraTutti(v => !v)}
          className="w-full py-2 text-sm font-medium rounded-lg border border-incerto/30 text-incerto hover:bg-incerto/10 transition-colors"
        >
          {mostraTutti ? "Mostra solo i primi 5" : `Mostra tutti (altri ${nascosti})`}
        </button>
      )}
    </div>
  );
}

/* ── Componente principale ── */
export function AnalisiETagClient({
  initialTags,
  initialCartelle,
  initialSuggestions,
  caricamentoFallito = false,
}: {
  initialTags: CustomTag[];
  initialCartelle: CartellaTag[];
  initialSuggestions: TagSuggestion[];
  /**
   * Il caricamento server e' fallito (worker giu', timeout): senza questo flag
   * un cliente che HA dei tag leggeva «Nessun tag ancora — Crea il primo tag»,
   * cioe' un invito a rifare da capo un lavoro che aveva gia' fatto.
   */
  caricamentoFallito?: boolean;
}) {
  const [tags, setTags] = useState<CustomTag[]>(initialTags);
  const [cartelle, setCartelle] = useState<CartellaTag[]>(initialCartelle);
  const [suggestions, setSuggestions] = useState<TagSuggestion[]>(initialSuggestions);
  // Il server non vede localStorage: si parte dalla vista «Tutte» e il montaggio
  // corregge con la vista ricordata.
  const [selectedTagId, setSelectedTagId] = useState<number | null>(
    () => primoDaMostrare(initialTags, initialCartelle, "tutte", []),
  );
  const [vista, setVista] = useState<VistaTag>("tutte");
  const [chiuse, setChiuse] = useState<number[]>([]);
  const [comodoLetto, setComodoLetto] = useState(false);

  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null);
  const [periodoPreset, setPeriodoPreset] = useState<PeriodoPreset>("anno_corrente");
  const [dataDaCustom, setDataDaCustom] = useState<string | null>(null);
  const [dataACustom, setDataACustom] = useState<string | null>(null);

  const [analisi, setAnalisi] = useState<TagAnalisiResponse | null>(null);
  const [loadingAnalisi, setLoadingAnalisi] = useState(false);

  const [prodotti, setProdotti] = useState<TagProdotto[]>([]);
  const [loadingProdotti, setLoadingProdotti] = useState(false);
  const [suggerimentiAperti, setSuggerimentiAperti] = useState(false);

  const [dialogTag, setDialogTag] = useState<{ open: boolean; tag: CustomTag | null }>({ open: false, tag: null });
  // Il riquadro si chiude dall'interno di un salvataggio asincrono, con in mano
  // il selectedTagId del render in cui e' partito: per un tag appena creato
  // sarebbe ancora quello vecchio. Il ricaricamento si fa quindi in un effetto,
  // che legge lo stato gia' aggiornato.
  const [chiusureDialog, setChiusureDialog] = useState(0);
  // Si ricarica solo se il riquadro ha cambiato qualcosa: chiuderlo con Annulla
  // non deve rifare analisi e prodotti.
  const dialogHaModificato = useRef(false);
  const [confermaElimina, setConfermaElimina] = useState(false);
  // Guardia sincrona: un doppio clic sul «Elimina tag» del dialog mandava due
  // DELETE, e il secondo mostrava un errore dopo «Tag eliminato».
  const eliminando = useRef(false);

  const [refreshingSuggestions, setRefreshingSuggestions] = useState(false);
  // Il grafico parte chiuso a ogni tag scelto (Mattia, 14/10/2026).
  const [showTrend, setShowTrend] = useState(false);
  useEffect(() => { setShowTrend(false); }, [selectedTagId]);
  const [showFornitori, setShowFornitori] = useState(true);

  // ── Load analisi (range diretto) ──
  const loadAnalisiRange = useCallback(async (tagId: number, da: string, dataA: string) => {
    setLoadingAnalisi(true);
    setAnalisi(null);
    try {
      const res = await fetch(`/api/tag/${tagId}/analisi?data_da=${da}&data_a=${dataA}`);
      if (!res.ok) throw new Error();
      setAnalisi(await res.json());
    } catch {
      toast.error("Errore nel caricamento analisi");
    } finally {
      setLoadingAnalisi(false);
    }
  }, []);

  // ── Load analisi (anno + mese) ──
  const loadAnalisi = useCallback(async (tagId: number, a: number, m: number | null) => {
    const { da, a: dataA } = isoRange(a, m);
    return loadAnalisiRange(tagId, da, dataA);
  }, [loadAnalisiRange]);

  // Il periodo mostrato dai chip, compreso il «Personalizzato»: ricaricare con
  // anno/mese riportava l'analisi all'anno mentre i chip dicevano altro.
  function loadAnalisiPeriodoCorrente(tagId: number) {
    if (periodoPreset === "personalizzato" && dataDaCustom && dataACustom) {
      return loadAnalisiRange(tagId, dataDaCustom, dataACustom);
    }
    return loadAnalisi(tagId, anno, mese);
  }

  // ── Load prodotti ──
  const loadProdotti = useCallback(async (tagId: number) => {
    setLoadingProdotti(true);
    try {
      const res = await fetch(`/api/tag/${tagId}/prodotti`);
      if (!res.ok) throw new Error();
      const d = await res.json();
      setProdotti(d.prodotti ?? []);
    } catch {
      toast.error("Errore nel caricamento prodotti");
    } finally {
      setLoadingProdotti(false);
    }
  }, []);

  // ── Load tags e suggestions ──
  const reloadTags = useCallback(async () => {
    const [tagsRes, sugRes] = await Promise.all([
      fetch("/api/tag").then(r => r.json()).catch(() => null),
      fetch("/api/tag/suggestions").then(r => r.json()).catch(() => null),
    ]);
    if (tagsRes?.tags) setTags(tagsRes.tags);
    if (Array.isArray(tagsRes?.cartelle)) setCartelle(tagsRes.cartelle);
    if (sugRes?.suggestions) setSuggestions(sugRes.suggestions);
  }, []);

  const refreshSuggestions = useCallback(async () => {
    setRefreshingSuggestions(true);
    try {
      const res = await fetch("/api/tag/suggestions?refresh=true");
      const d = await res.json();
      setSuggestions(d.suggestions ?? []);
      // refresh_ok === false: il motore non ha girato e la lista e' quella
      // vecchia. Senza questo avviso il fallimento sembra "nessuna novita'".
      if (d.refresh_ok === false) {
        toast.error("Aggiornamento non riuscito: la lista mostrata non è aggiornata");
      }
    } catch {
      toast.error("Errore aggiornamento suggerimenti");
    } finally {
      setRefreshingSuggestions(false);
    }
  }, []);

  // Seleziona tag → carica analisi e prodotti
  function selectTag(id: number) {
    setSelectedTagId(id);
    loadAnalisiPeriodoCorrente(id);
    loadProdotti(id);
  }

  // Mount: vista ricordata, poi analisi + prodotti del primo tag mostrato
  useEffect(() => {
    const stato = leggiStatoComodo(leggiStorage());
    setVista(stato.vista);
    setChiuse(stato.chiuse);
    setComodoLetto(true);
    const primo = primoDaMostrare(initialTags, initialCartelle, stato.vista, stato.chiuse);
    setSelectedTagId(primo);
    if (primo) {
      loadAnalisi(primo, anno, mese);
      loadProdotti(primo);
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (comodoLetto) scriviStorage(scriviStatoComodo({ vista, chiuse }));
  }, [comodoLetto, vista, chiuse]);

  // ── Stella: solo organizzazione, non cambia l'analisi ──
  async function alternaPreferito(tag: CustomTag) {
    const nuovo = !tag.preferito;
    setTags(prev => prev.map(t => (t.id === tag.id ? { ...t, preferito: nuovo } : t)));
    try {
      const res = await fetch(`/api/tag/${tag.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferito: nuovo }),
      });
      if (!res.ok) throw new Error();
    } catch {
      // Indietro solo se nessun altro clic ha gia' cambiato la stella nel frattempo.
      setTags(prev => prev.map(t => (t.id === tag.id && t.preferito === nuovo ? { ...t, preferito: !nuovo } : t)));
      toast.error("Non sono riuscito ad aggiornare i preferiti");
    }
  }

  useEffect(() => {
    if (chiusureDialog > 0 && selectedTagId) {
      loadProdotti(selectedTagId);
      loadAnalisiPeriodoCorrente(selectedTagId);
    }
  }, [chiusureDialog]);  // eslint-disable-line react-hooks/exhaustive-deps

  // ── Elimina tag ──
  async function deleteTag(tagId: number) {
    if (eliminando.current) return;
    eliminando.current = true;
    try {
      const res = await fetch(`/api/tag/${tagId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Tag eliminato");
      const newTags = tags.filter(t => t.id !== tagId);
      setTags(newTags);
      if (selectedTagId === tagId) {
        const next = primoDaMostrare(newTags, cartelle, vista, chiuse);
        setSelectedTagId(next);
        setAnalisi(null);
        setProdotti([]);
        if (next) { loadAnalisiPeriodoCorrente(next); loadProdotti(next); }
      }
    } catch {
      toast.error("Errore nell'eliminazione");
    } finally {
      eliminando.current = false;
    }
  }

  // ── Export XLS ──
  async function exportXls() {
    if (!selectedTagId || !analisi || analisi.vuoto) return;
    const tag = tags.find(t => t.id === selectedTagId);
    const { da, a } = isoRange(anno, mese);
    try {
      const { utils, writeFile } = await import("xlsx");
      const wb = utils.book_new();

      // Sheet KPI
      if (analisi.kpi) {
        const kpiData = [
          ["Metrica", "Valore"],
          ["Spesa Totale", analisi.kpi.spesa_totale],
          ["Quantità Normalizzata", analisi.kpi.quantita_norm_totale],
          ["Prezzo Medio Ponderato", analisi.kpi.prezzo_medio_ponderato ?? "—"],
          ["Fornitori Distinti", analisi.kpi.num_fornitori],
          ["Fatture Coinvolte", analisi.kpi.num_fatture],
        ];
        utils.book_append_sheet(wb, utils.aoa_to_sheet(kpiData), "KPI");
      }

      // Sheet Trend
      if (analisi.trend.punti.length > 0) {
        const header = ["Data", "Prezzo", "Var% vs media"];
        const rows = analisi.trend.punti.map(p => [p.data, p.prezzo, p.var_perc]);
        utils.book_append_sheet(wb, utils.aoa_to_sheet([header, ...rows]), "Trend prezzi");
      }

      // Sheet Fornitori
      if (analisi.fornitori.fornitori.length > 0) {
        const header = ["Fornitore", "Spesa (€)", "Acquisti", "Quantità", "Prezzo medio", "Δ% vs media", "% sul tag"];
        const rows = analisi.fornitori.fornitori.map(f => [
          f.fornitore, f.spesa_totale, f.num_acquisti, f.quantita_totale,
          f.prezzo_medio ?? "—", f.delta_pct, f.incidenza_spesa,
        ]);
        utils.book_append_sheet(wb, utils.aoa_to_sheet([header, ...rows]), "Fornitori");
      }

      const nomeTag = tag?.nome ?? "tag";
      writeFile(wb, `analisi_${nomeTag}_${da}_${a}.xlsx`);
    } catch {
      toast.error("Errore nell'export");
    }
  }

  const selectedTag = tags.find(t => t.id === selectedTagId) ?? null;
  const { kpi, trend, fornitori } = analisi ?? { kpi: null, trend: { punti: [], prezzo_medio_periodo: 0 }, fornitori: { fornitori: [], aggregati: null } };

  /* ══════════════════════════════════════════════════════════ RENDER */
  // Due riquadri (Fase 3, 13/10/2026): a sinistra la lista dei tag, a destra il
  // tag scelto con periodo e analisi. Le colonne partono da 1280 px: sotto, la
  // lista sta sopra e l'analisi sotto. Accanto c'e' gia' il menu dell'app, per
  // questo la lista e' una scheda con bordo e titolo e non una fascia.
  return (
    <div className="grid items-start gap-6 xl:grid-cols-[17rem_minmax(0,1fr)]">
      <PannelloTag
        sorgente={sorgenteSede}
        tags={tags}
        cartelle={cartelle}
        setTags={setTags}
        setCartelle={setCartelle}
        vista={vista}
        onVista={setVista}
        chiuse={chiuse}
        onChiuse={setChiuse}
        selectedTagId={selectedTagId}
        onSelezionaTag={selectTag}
        onNuovoTag={() => setDialogTag({ open: true, tag: null })}
        onRicarica={reloadTags}
        info={
          <InfoPopover title="Come funzionano i Tag">
            <p className="text-muted-foreground">
              I tag sono <strong className="text-foreground">etichette tue</strong> per raggruppare prodotti che l&apos;app non distingue da sola (es. &ldquo;Bio&rdquo;, &ldquo;Fornitore X&rdquo;, &ldquo;Vegano&rdquo;), e analizzarne spesa e andamento insieme.
            </p>
            <div className="space-y-1.5 text-muted-foreground">
              <p><strong className="text-foreground">Crea un tag</strong> con <em>Nuovo tag</em> e spunta i prodotti che vuoi raggrupparvi. Per cambiarlo più tardi (nome, emoji, cartella, prodotti da aggiungere o togliere) usa <em>Modifica tag</em> accanto al suo nome.</p>
              <p><strong className="text-foreground">Cartelle e preferiti</strong> servono solo a tenere in ordine la lista: raccogli i tag in cartelle (trascinale dalla maniglia per riordinarle, trascina un tag per spostarlo) e segna con la ☆ quelli che usi di più. Non cambiano nessuna analisi.</p>
              <p><strong className="text-foreground">Suggerimenti</strong>: l&apos;app propone tag pronti in base a quello che compri spesso — accettali con un clic.</p>
              <p>Scegli un tag dalla lista per vedere <strong className="text-foreground">quanto spendi</strong>, il trend nel tempo e i fornitori coinvolti, nel periodo scelto.</p>
            </div>
          </InfoPopover>
        }
        suggerimenti={
          <Button
            variant="ghost"
            size="sm"
            aria-pressed={suggestions.length > 0 ? suggerimentiAperti : undefined}
            className={cn("w-full justify-start gap-2", suggerimentiAperti && suggestions.length > 0 && "bg-muted text-foreground")}
            onClick={async () => {
              if (suggestions.length > 0) { setSuggerimentiAperti(v => !v); return; }
              await refreshSuggestions();
              await reloadTags();
              setSuggerimentiAperti(true);
            }}
            disabled={refreshingSuggestions}
            title={suggestions.length > 0 ? "Mostra o nascondi i suggerimenti" : "Analizza prodotti non taggati e trova suggerimenti"}
          >
            {refreshingSuggestions
              ? <RefreshCw className="animate-spin text-incerto" />
              : <Lightbulb className="text-incerto" />}
            <span className="flex-1 text-left">{refreshingSuggestions ? "Analisi in corso…" : "Suggerimenti"}</span>
            {!refreshingSuggestions && suggestions.length > 0 && (
              <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-incerto px-1.5 py-0.5 text-[10px] font-bold text-white tabular-nums">
                {suggestions.length}
              </span>
            )}
          </Button>
        }
      />

      <div className="min-w-0 space-y-5">
        {/* ── Suggerimenti: in cima alla colonna del tag ── */}
        <SuggerimentiBanner
          suggestions={suggestions}
          onRefresh={async () => { await refreshSuggestions(); await reloadTags(); }}
          refreshing={refreshingSuggestions}
          aperto={suggerimentiAperti}
          onChiudi={() => setSuggerimentiAperti(false)}
        />

        {/* ── Empty state ── */}
        {tags.length === 0 && (
          <div className="rounded-xl border border-dashed border-border bg-card py-16 text-center">
            <Tags className="size-10 text-muted-foreground mx-auto mb-3" />
            {mostraGuasto(caricamentoFallito, tags.length) ? (
              <>
                <p className="text-sm font-medium">Tag non disponibili in questo momento</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Non è stato possibile caricarli. Ricarica la pagina fra un momento: i tuoi tag non sono stati persi.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium">Nessun tag ancora</p>
                <p className="text-xs text-muted-foreground mt-1 mb-4">Crea il primo tag per raggruppare i tuoi prodotti e analizzare la spesa</p>
                <Button onClick={() => setDialogTag({ open: true, tag: null })}>
                  <Plus />
                  Crea primo tag
                </Button>
              </>
            )}
          </div>
        )}

        {/* Ci sono tag ma nessuno e' scelto (tutte le cartelle chiuse, nessun preferito). */}
        {tags.length > 0 && !selectedTag && (
          <div className="rounded-xl border border-dashed border-border bg-card py-16 text-center">
            <Tags className="size-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm font-medium">Scegli un tag dalla lista</p>
            <p className="text-xs text-muted-foreground mt-1">Vedrai quanto spendi, il trend dei prezzi e i fornitori nel periodo scelto.</p>
          </div>
        )}

        {/* ── Riquadro del tag scelto ── */}
        {selectedTag && (
          <section aria-label={`Tag ${selectedTag.nome}`} className="@container overflow-hidden rounded-xl border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 pb-3 pt-4">
              <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
                {selectedTag.emoji && <span className="text-2xl leading-none" aria-hidden>{selectedTag.emoji}</span>}
                <h2 className="min-w-0 truncate text-xl font-semibold tracking-tight" title={selectedTag.nome}>{selectedTag.nome}</h2>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-pressed={!!selectedTag.preferito}
                  aria-label={selectedTag.preferito ? "Togli dai preferiti" : "Aggiungi ai preferiti"}
                  title={selectedTag.preferito ? "Togli dai preferiti" : "Aggiungi ai preferiti"}
                  onClick={() => alternaPreferito(selectedTag)}
                >
                  <Star className={selectedTag.preferito ? "fill-incerto text-incerto" : "text-muted-foreground"} />
                </Button>
                <Button
                  variant="link"
                  size="sm"
                  className="px-1 text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
                  onClick={() => setDialogTag({ open: true, tag: selectedTag })}
                  disabled={loadingProdotti}
                >
                  {loadingProdotti ? "…" : etichettaProdotti(prodotti.length)}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => setDialogTag({ open: true, tag: selectedTag })}>
                  <Pencil />
                  Modifica tag
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Elimina tag"
                  title="Elimina tag"
                  onClick={() => setConfermaElimina(true)}
                >
                  <Trash2 />
                </Button>
              </div>
            </div>

            <div className="border-b px-5 pb-4">
              <FiltroPeriodoTag
                anno={anno}
                mese={mese}
                dataDa={dataDaCustom}
                dataA={dataACustom}
                preset={periodoPreset}
                onChange={({ anno: a, mese: m, preset, dataDa: dd, dataA: da }) => {
                  setAnno(a);
                  setMese(m);
                  setPeriodoPreset(preset);
                  setDataDaCustom(dd ?? null);
                  setDataACustom(da ?? null);
                  if (selectedTagId) {
                    const range = preset === "personalizzato" && dd && da
                      ? { da: dd, a: da }
                      : isoRange(a, m);
                    loadAnalisiRange(selectedTagId, range.da, range.a);
                  }
                }}
              />
            </div>

            <div className="space-y-6 p-5">
              {/* KPI: le colonne seguono la larghezza del riquadro, non dello
                  schermo (col menu aperto o chiuso cambia di 13rem). */}
              {loadingAnalisi && (
                <div className="grid grid-cols-2 gap-3 @lg:grid-cols-6 @3xl:grid-cols-5">
                  {KPI_POSTI.map((posto, i) => <div key={i} className={cn("h-20 rounded-lg border bg-card animate-pulse", posto)} />)}
                </div>
              )}
              {!loadingAnalisi && analisi?.vuoto === false && kpi && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3 @lg:grid-cols-6 @3xl:grid-cols-5">
                    <KpiCard className={KPI_POSTI[0]} label="Totale spesa" value={fmtEuro(kpi.spesa_totale)} tone="border-primary/40 hover:border-primary/70" />
                    <KpiCard className={KPI_POSTI[1]} label={kpi.quantita_label} value={kpi.quantita_norm_totale.toLocaleString("it-IT", { maximumFractionDigits: 1 })} tone="border-border hover:border-muted-foreground/40" />
                    <KpiCard className={KPI_POSTI[2]} label={kpi.prezzo_label} value={kpi.prezzo_medio_ponderato != null ? fmtEuro(kpi.prezzo_medio_ponderato) : "—"} tone="border-border hover:border-muted-foreground/40" />
                    <KpiCard className={KPI_POSTI[3]} label="Fornitori" value={String(kpi.num_fornitori)} tone="border-border hover:border-muted-foreground/40" />
                    <KpiCard className={KPI_POSTI[4]} label="Fatture" value={String(kpi.num_fatture)} tone="border-border hover:border-muted-foreground/40" />
                  </div>
                  {kpi.unita_dominante && (kpi.spesa_esclusa_mix ?? 0) !== 0 && (
                    <p className="text-xs text-muted-foreground">
                      Questo tag contiene unità di misura diverse: quantità e prezzo medio
                      si riferiscono alla sola parte in <strong>{kpi.unita_dominante}</strong>.
                      Restano fuori dal calcolo {fmtEuro(kpi.spesa_esclusa_mix ?? 0)} di spesa,
                      comunque inclusi nel totale.
                    </p>
                  )}
                </div>
              )}
              {!loadingAnalisi && analisi?.vuoto && (
                <div className="rounded-lg border border-dashed border-border py-10 text-center">
                  <p className="text-sm text-muted-foreground">Nessun dato nel periodo selezionato per questo tag.</p>
                </div>
              )}

              {!loadingAnalisi && analisi?.vuoto === false && (
                <>
                  {/* Trend */}
                  <section className="space-y-3 border-t pt-5" aria-label="Trend prezzi nel periodo">
                    <div className="flex items-center justify-between gap-3">
                      <TitoloApribile titolo="Trend prezzi nel periodo" aperto={showTrend} onCambia={setShowTrend} />
                      <Button variant="outline" size="icon-sm" onClick={exportXls} title="Esporta XLS" aria-label="Esporta XLS">
                        <Download />
                      </Button>
                    </div>
                    {showTrend && <TrendChart punti={trend.punti} media={trend.prezzo_medio_periodo} />}
                  </section>

                  {/* Fornitori */}
                  <section className="space-y-3 border-t pt-5" aria-label="Fornitori">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold">Fornitori</h3>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-expanded={showFornitori}
                        className="text-muted-foreground aria-expanded:bg-transparent aria-expanded:text-muted-foreground hover:aria-expanded:bg-muted"
                        aria-label={showFornitori ? "Nascondi i fornitori" : "Mostra i fornitori"}
                        onClick={() => setShowFornitori(v => !v)}
                      >
                        {showFornitori ? <ChevronUp /> : <ChevronDown />}
                      </Button>
                    </div>
                    {showFornitori && fornitori.fornitori.length > 0 && (
                      <div className="overflow-x-auto rounded-lg border">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="border-b border-border bg-muted/30">
                              <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Fornitore</th>
                              <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Spesa</th>
                              <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Acquisti</th>
                              <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">Prezzo medio</th>
                              {/* La media di riferimento e' prezzo_medio_tag, che il worker
                                  manda in fornitori.aggregati (tag_analytics_service.py:386) e
                                  che il client scartava: la colonna mostrava scostamenti da un
                                  numero mai visibile. E' anche il campo corretto il 24/8 da
                                  media semplice a ponderata. */}
                              <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">
                                Rispetto alla media
                                {fornitori.aggregati?.prezzo_medio_tag != null && (
                                  <span className="block font-normal text-[10px] text-muted-foreground/70">
                                    {/* Solo il valore: quantita_label e' un'intestazione di
                                        colonna ("⚖️ Quantità Totale KG"), non un'unita'. */}
                                    {fmtEuro(fornitori.aggregati.prezzo_medio_tag)}
                                  </span>
                                )}
                              </th>
                              <th className="text-right px-4 py-2 text-xs font-medium text-muted-foreground">% sul tag</th>
                            </tr>
                          </thead>
                          <tbody>
                            {fornitori.fornitori.map((f, i) => (
                              <tr key={i} className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors">
                                <td className="px-4 py-2.5 font-medium">{f.fornitore}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums">{fmtEuro(f.spesa_totale)}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">{f.num_acquisti}</td>
                                <td className="px-4 py-2.5 text-right tabular-nums">{f.prezzo_medio != null ? fmtEuro(f.prezzo_medio) : "—"}</td>
                                <td className={`px-4 py-2.5 text-right tabular-nums font-semibold ${f.delta_pct > 5 ? "text-negativo" : f.delta_pct < -5 ? "text-positivo" : "text-muted-foreground"}`}>
                                  {fmtPct(f.delta_pct, true)}
                                </td>
                                <td className="px-4 py-2.5 text-right">
                                  <div className="flex items-center gap-2 justify-end">
                                    <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
                                      <div className="h-full bg-primary rounded-full" style={{ width: `${Math.min(100, f.incidenza_spesa)}%` }} />
                                    </div>
                                    <span className="tabular-nums text-xs w-10">{f.incidenza_spesa.toFixed(1)}%</span>
                                  </div>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {showFornitori && fornitori.fornitori.length === 0 && (
                      <p className="text-sm text-muted-foreground">Nessun dato fornitori.</p>
                    )}
                  </section>
                </>
              )}
            </div>
          </section>
        )}
      </div>

      {/* ── Dialogs ── */}
      <ConfirmDialog
        open={confermaElimina && selectedTag !== null}
        titolo={`Eliminare il tag «${selectedTag?.nome ?? ""}»?`}
        messaggio="Si cancellano il tag e la sua lista di prodotti. Le fatture e le altre analisi non cambiano."
        confermaLabel="Elimina tag"
        onConferma={() => { if (selectedTag) deleteTag(selectedTag.id); }}
        onClose={() => setConfermaElimina(false)}
      />
      <ModificaTagDialog
        sorgente={sorgenteSede}
        open={dialogTag.open}
        onOpenChange={v => {
          setDialogTag(d => ({ ...d, open: v }));
          if (v) dialogHaModificato.current = false;
          else if (dialogHaModificato.current) {
            dialogHaModificato.current = false;
            setChiusureDialog(n => n + 1);
          }
        }}
        onProdottiCambiati={() => { dialogHaModificato.current = true; }}
        tag={dialogTag.tag}
        cartelle={cartelle}
        onSaved={(saved, isNew) => {
          dialogHaModificato.current = true;
          if (isNew) {
            setTags(prev => [...prev, saved].sort((a, b) => a.nome.localeCompare(b.nome)));
            setSelectedTagId(saved.id);
            setAnalisi(null);
            setProdotti([]);
          } else {
            setTags(prev => prev.map(t => (t.id === saved.id ? { ...t, ...saved } : t)));
          }
        }}
      />
    </div>
  );
}
