"use client";

import { useState, useEffect, useCallback } from "react";
import { Plus, Pencil, Trash2, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

// ─── Tipi ────────────────────────────────────────────────────────────────────

type TipoSpesa = "fb" | "generale";

interface Spesa {
  id: string;
  data_spesa: string;
  tipo: TipoSpesa;
  importo: number;
  descrizione: string;
  note?: string | null;
}

interface SpeseResponse {
  voci: Spesa[];
  totale_fb: number;
  totale_generale: number;
  totale: number;
}

// ─── Utilità ──────────────────────────────────────────────────────────────────

function toISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const g = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${g}`;
}

function fmtData(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" });
}

function fmtEuro(v: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

const TIPO_LABEL: Record<TipoSpesa, string> = {
  fb: "Costo F&B",
  generale: "Spesa Generale",
};

const TIPO_BADGE: Record<TipoSpesa, string> = {
  fb: "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200",
  generale: "bg-purple-100 text-purple-800 dark:bg-purple-900/50 dark:text-purple-200",
};

// Ring per tipo — coerente con lo stile a card bordate di Personale.
const TIPO_RING: Record<TipoSpesa, string> = {
  fb: "ring-orange-500/50 hover:bg-orange-500/5",
  generale: "ring-purple-500/50 hover:bg-purple-500/5",
};

// ─── Dialog spesa ─────────────────────────────────────────────────────────────

interface SpesaDialogProps {
  open: boolean;
  spesa: Spesa | null;
  dataDefault: string;
  onClose: () => void;
  onSaved: () => void;
}

function SpesaDialog({ open, spesa, dataDefault, onClose, onSaved }: SpesaDialogProps) {
  const [data, setData] = useState(dataDefault);
  const [tipo, setTipo] = useState<TipoSpesa>("generale");
  const [importo, setImporto] = useState("");
  const [descrizione, setDescrizione] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setData(spesa?.data_spesa ?? dataDefault);
      setTipo(spesa?.tipo ?? "generale");
      setImporto(spesa?.importo ? String(spesa.importo).replace(".", ",") : "");
      setDescrizione(spesa?.descrizione ?? "");
      setNote(spesa?.note ?? "");
    }
  }, [open, spesa, dataDefault]);

  const importoNum = importo ? parseFloat(importo.replace(",", ".")) : NaN;

  async function salva() {
    if (!descrizione.trim()) { toast.error("La descrizione è obbligatoria"); return; }
    if (isNaN(importoNum) || importoNum < 0) { toast.error("Inserisci un importo valido"); return; }
    setSaving(true);
    try {
      const payload = {
        data_spesa: data,
        tipo,
        importo: importoNum,
        descrizione: descrizione.trim(),
        note: note.trim() || null,
      };
      const url = spesa ? `/api/workspace/spese/${spesa.id}` : "/api/workspace/spese";
      const method = spesa ? "PATCH" : "POST";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail ?? "Errore");
      toast.success(spesa ? "Spesa aggiornata" : "Spesa aggiunta");
      onSaved();
      onClose();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{spesa ? "Modifica spesa" : "Nuova spesa"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 mt-2">
          {/* Tipo */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Tipo di spesa *</label>
            <div className="grid grid-cols-2 gap-2">
              {(["fb", "generale"] as TipoSpesa[]).map(t => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTipo(t)}
                  className={`px-3 py-2 text-sm font-medium rounded-md border transition-colors ${
                    tipo === t
                      ? t === "fb"
                        ? "border-orange-500 bg-orange-500/10 text-orange-700 dark:text-orange-300"
                        : "border-purple-500 bg-purple-500/10 text-purple-700 dark:text-purple-300"
                      : "border-input text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {TIPO_LABEL[t]}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5">
              {tipo === "fb"
                ? "Costi di cibo & bevande non arrivati via fattura (es. spesa al mercato, contanti)."
                : "Spese di gestione non da fattura (es. utenze pagate a mano, piccole manutenzioni)."}
            </p>
          </div>

          {/* Data + importo */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Data *</label>
              <Input type="date" value={data} onChange={e => setData(e.target.value)} />
            </div>
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-1 block">Importo (€) *</label>
              <Input
                type="text"
                inputMode="decimal"
                value={importo}
                onChange={e => setImporto(e.target.value.replace(/[^0-9,.]/g, ""))}
                placeholder="es. 120,00"
              />
            </div>
          </div>

          {/* Descrizione */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Descrizione *</label>
            <Input
              value={descrizione}
              onChange={e => setDescrizione(e.target.value)}
              placeholder="es. Pesce dal mercato, bolletta gas…"
              autoFocus
            />
          </div>

          {/* Note */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Note</label>
            <Input value={note} onChange={e => setNote(e.target.value)} placeholder="Opzionale…" />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
            <Button onClick={salva} disabled={saving}>{saving ? "Salvo…" : "Salva"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── Vista Spese ───────────────────────────────────────────────────────────────

type FiltroTipo = "tutte" | TipoSpesa;

export function SpeseView() {
  const oggi = toISO(new Date());
  const [meseBase, setMeseBase] = useState(() => oggi.slice(0, 7));
  const [risposta, setRisposta] = useState<SpeseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editSpesa, setEditSpesa] = useState<Spesa | null>(null);
  const [dataDefault, setDataDefault] = useState(oggi);
  const [filtro, setFiltro] = useState<FiltroTipo>("tutte");

  const [da, fine] = (() => {
    const [ay, am] = meseBase.split("-").map(Number);
    const ultimoGiorno = new Date(ay, am, 0).getDate();
    return [`${meseBase}-01`, `${meseBase}-${String(ultimoGiorno).padStart(2, "0")}`];
  })();

  const load = useCallback(async (d: string, f: string) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/workspace/spese?da=${d}&a=${f}`);
      if (!res.ok) throw new Error();
      const j: SpeseResponse = await res.json();
      setRisposta(j);
    } catch {
      toast.error("Errore caricamento spese");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(da, fine); }, [da, fine, load]);

  function navPrev() {
    const [ay, am] = meseBase.split("-").map(Number);
    const prev = new Date(ay, am - 2, 1);
    setMeseBase(`${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`);
  }
  function navNext() {
    const [ay, am] = meseBase.split("-").map(Number);
    const next = new Date(ay, am, 1);
    setMeseBase(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
  }

  function labelMese() {
    const [ay, am] = meseBase.split("-").map(Number);
    return new Date(ay, am - 1, 1).toLocaleDateString("it-IT", { month: "long", year: "numeric" });
  }

  async function elimina(s: Spesa) {
    if (!confirm(`Eliminare la spesa "${s.descrizione}" (${fmtData(s.data_spesa)} · ${fmtEuro(s.importo)})?`)) return;
    try {
      const res = await fetch(`/api/workspace/spese/${s.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Spesa eliminata");
      load(da, fine);
    } catch {
      toast.error("Errore eliminazione spesa");
    }
  }

  function esportaCSV() {
    if (!risposta || risposta.voci.length === 0) return;
    const num = (v: number) => String(Math.round(v * 100) / 100).replace(".", ",");
    const headers = ["Data", "Tipo", "Descrizione", "Importo", "Note"];
    const rows = voci.map(s => [
      fmtData(s.data_spesa),
      TIPO_LABEL[s.tipo],
      s.descrizione,
      num(s.importo),
      s.note ?? "",
    ]);
    rows.push([]);
    rows.push(["TOTALE F&B", "", "", num(risposta.totale_fb), ""]);
    rows.push(["TOTALE GENERALI", "", "", num(risposta.totale_generale), ""]);
    const csv = [headers, ...rows]
      .map(r => r.map(c => `"${String(c ?? "").replace(/"/g, '""')}"`).join(";"))
      .join("\r\n");
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `spese_${da}_${fine}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV scaricato — aprilo con Excel");
  }

  const tutteVoci = risposta?.voci ?? [];
  const voci = filtro === "tutte" ? tutteVoci : tutteVoci.filter(v => v.tipo === filtro);
  const totFb = risposta?.totale_fb ?? 0;
  const totGenerale = risposta?.totale_generale ?? 0;
  const totale = risposta?.totale ?? 0;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 border border-border rounded-md">
          <button onClick={navPrev} className="p-1.5 hover:bg-muted rounded-l-md">
            <ChevronLeft className="size-4" />
          </button>
          <span className="px-3 text-sm font-medium min-w-[150px] text-center capitalize">{labelMese()}</span>
          <button onClick={navNext} className="p-1.5 hover:bg-muted rounded-r-md">
            <ChevronRight className="size-4" />
          </button>
        </div>

        {/* Filtro tipo */}
        <div className="flex rounded-md border border-border overflow-hidden">
          {([
            { k: "tutte" as FiltroTipo, l: "Tutte" },
            { k: "fb" as FiltroTipo, l: "F&B" },
            { k: "generale" as FiltroTipo, l: "Generali" },
          ]).map(f => (
            <button
              key={f.k}
              onClick={() => setFiltro(f.k)}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                filtro === f.k ? "bg-primary text-primary-foreground" : "hover:bg-muted text-muted-foreground"
              }`}
            >
              {f.l}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          {tutteVoci.length > 0 && (
            <Button variant="outline" onClick={esportaCSV}>
              <Download className="size-4 mr-1.5" />Esporta CSV
            </Button>
          )}
          <Button onClick={() => { setEditSpesa(null); setDataDefault(oggi >= da && oggi <= fine ? oggi : da); setDialogOpen(true); }}>
            <Plus className="size-4 mr-1.5" />Aggiungi spesa
          </Button>
        </div>
      </div>

      {/* KPI totali — stile coerente con Personale (card grandi) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card className="ring-1 ring-orange-500/50 bg-orange-50/60 dark:bg-orange-950/20">
          <CardContent className="py-5 px-6 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-orange-700 dark:text-orange-500">Costi F&amp;B extra</p>
            <p className="text-4xl font-black tabular-nums text-orange-700 dark:text-orange-400 leading-none">{fmtEuro(totFb)}</p>
          </CardContent>
        </Card>
        <Card className="ring-1 ring-purple-500/50 bg-purple-50/60 dark:bg-purple-950/20">
          <CardContent className="py-5 px-6 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-purple-700 dark:text-purple-500">Spese Generali extra</p>
            <p className="text-4xl font-black tabular-nums text-purple-700 dark:text-purple-400 leading-none">{fmtEuro(totGenerale)}</p>
          </CardContent>
        </Card>
        <Card className="ring-1 ring-sky-500/50 bg-sky-50/60 dark:bg-sky-950/20">
          <CardContent className="py-5 px-6 space-y-2">
            <p className="text-xs font-semibold uppercase tracking-widest text-sky-700 dark:text-sky-400">Totale extra</p>
            <p className="text-4xl font-black tabular-nums text-sky-700 dark:text-sky-300 leading-none">{fmtEuro(totale)}</p>
          </CardContent>
        </Card>
      </div>

      {/* Lista */}
      {loading ? (
        <div className="py-12 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : voci.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted-foreground">
          {tutteVoci.length === 0
            ? "Nessuna spesa extra in questo mese. Usa “Aggiungi spesa” per iniziare."
            : "Nessuna spesa di questo tipo nel mese."}
        </div>
      ) : (
        <div className="space-y-1.5">
          {voci.map(s => (
            <div key={s.id} className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 ring-1 transition-colors group ${TIPO_RING[s.tipo]}`}>
              <span className="text-xs text-muted-foreground tabular-nums w-12 shrink-0">{fmtData(s.data_spesa)}</span>
              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full shrink-0 ${TIPO_BADGE[s.tipo]}`}>
                {s.tipo === "fb" ? "F&B" : "Gen."}
              </span>
              <span className="text-sm flex-1 min-w-0 truncate">
                {s.descrizione}
                {s.note && <span className="ml-1.5 text-xs text-muted-foreground italic">· {s.note}</span>}
              </span>
              <span className="text-sm font-semibold tabular-nums shrink-0">{fmtEuro(s.importo)}</span>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <Button size="icon" variant="ghost" className="size-7" onClick={() => { setEditSpesa(s); setDialogOpen(true); }}>
                  <Pencil className="size-3.5" />
                </Button>
                <Button size="icon" variant="ghost" className="size-7 text-muted-foreground hover:text-destructive" onClick={() => elimina(s)}>
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <SpesaDialog
        open={dialogOpen}
        spesa={editSpesa}
        dataDefault={dataDefault}
        onClose={() => { setDialogOpen(false); setEditSpesa(null); }}
        onSaved={() => load(da, fine)}
      />
    </div>
  );
}
