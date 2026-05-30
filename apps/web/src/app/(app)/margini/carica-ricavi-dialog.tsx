"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Upload, FileSpreadsheet, X, CheckCircle2, AlertCircle, Calendar,
  ChevronLeft, ChevronRight, Trash2, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatEuro, MESI_NOMI_SHORT, scorporoNetto } from "./periodi";
import type {
  RicaviGiornalieriResponse, RicavoGiornaliero,
  RicaviBatchUpsertResponse, RicaviImportXlsResponse,
} from "@/lib/ricavi";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  dataDa: string;
  dataA: string;
  onImported: () => void;
};

type View = "home" | "xls" | "griglia";

const SOURCE_LABEL: Record<string, { label: string; color: string }> = {
  manuale: { label: "Manuale", color: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
  xls: { label: "XLS", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  email: { label: "Email", color: "bg-sky-500/15 text-sky-700 dark:text-sky-400" },
};

export function CaricaRicaviDialog({ open, onOpenChange, dataDa, dataA, onImported }: Props) {
  const [view, setView] = useState<View>("home");

  function handleClose() {
    onOpenChange(false);
    setTimeout(() => setView("home"), 250);
  }

  function handleImported() {
    onImported();
    handleClose();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(1100px,92vw)] w-full max-h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0 flex-row items-start justify-between gap-4">
          <div className="space-y-1">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Upload className="size-4 text-primary" />
              {view === "home" && "Carica ricavi"}
              {view === "xls" && "Importa da gestionale (XLS)"}
              {view === "griglia" && "Inserimento manuale"}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {view === "home" && "Scegli come vuoi inserire i ricavi nel piano di marginalità."}
              {view === "xls" && "Carica il file esportato dal gestionale Passbi · rolling 7 giorni."}
              {view === "griglia" && "Clicca un giorno del calendario per inserire o modificare i ricavi."}
            </DialogDescription>
          </div>
          <button
            onClick={handleClose}
            className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors shrink-0"
            aria-label="Chiudi"
          >
            <X className="size-4" />
          </button>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {view === "home" && (
            <HomeView onSelectXls={() => setView("xls")} onSelectGriglia={() => setView("griglia")} />
          )}
          {view === "xls" && (
            <XlsView onImported={handleImported} onBack={() => setView("home")} />
          )}
          {view === "griglia" && (
            <GrigliaView dataDa={dataDa} dataA={dataA} onSaved={handleImported} onBack={() => setView("home")} onClose={handleClose} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Home ──────────────────────────────────────────────────────────────── */
function HomeView({ onSelectXls, onSelectGriglia }: { onSelectXls: () => void; onSelectGriglia: () => void }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto">
      <button
        onClick={onSelectXls}
        className="flex items-start gap-4 rounded-xl border border-border p-5 hover:bg-muted/40 hover:border-emerald-500/40 transition-all text-left group"
      >
        <div className="size-12 rounded-xl bg-emerald-500/10 flex items-center justify-center shrink-0 group-hover:bg-emerald-500/20 transition-colors">
          <FileSpreadsheet className="size-6 text-emerald-600" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">Importa da XLS</p>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            File esportato dal gestionale Passbi. Rolling 7 giorni con aggiornamento automatico.
          </p>
          <span className="inline-block mt-2 text-[10px] font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-700 dark:text-emerald-400">
            Passbi v1
          </span>
        </div>
      </button>

      <button
        onClick={onSelectGriglia}
        className="flex items-start gap-4 rounded-xl border border-border p-5 hover:bg-muted/40 hover:border-sky-500/40 transition-all text-left group"
      >
        <div className="size-12 rounded-xl bg-sky-500/10 flex items-center justify-center shrink-0 group-hover:bg-sky-500/20 transition-colors">
          <Calendar className="size-6 text-sky-600" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold">Inserimento manuale</p>
          <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
            Calendario mensile: clicca un giorno per inserire i ricavi. Oppure imposta il totale del mese.
          </p>
          <span className="inline-block mt-2 text-[10px] font-medium px-2 py-0.5 rounded-full bg-sky-500/10 text-sky-700 dark:text-sky-400">
            Giornaliero · Mensile
          </span>
        </div>
      </button>
    </div>
  );
}

/* ─── XLS View ──────────────────────────────────────────────────────────── */
function XlsView({ onImported, onBack }: { onImported: () => void; onBack: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RicaviImportXlsResponse | null>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setLoading(false);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/ricavi/import-xls", { method: "POST", body: fd });
      if (!res.ok) throw new Error();
      const data: RicaviImportXlsResponse = await res.json();
      setResult(data);
      if (data.inserted + data.updated > 0) {
        toast.success(`${data.inserted + data.updated} giorni importati`);
        onImported();
      } else {
        toast.warning("Nessuna riga valida importata");
      }
    } catch {
      toast.error("Errore nell'import del file");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-xl mx-auto space-y-5">
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
        ← Indietro
      </button>

      <div className="flex items-center gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-4 py-3">
        <FileSpreadsheet className="size-4 text-emerald-600 shrink-0" />
        <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">Passbi v1</span>
        <span className="text-xs text-muted-foreground">· formato riconosciuto automaticamente</span>
      </div>

      {!result && (
        <>
          <label
            htmlFor="xls-file-dialog"
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed py-12 cursor-pointer transition-colors ${
              file ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-muted/20"
            }`}
          >
            <Upload className="size-10 text-muted-foreground/50 mb-3" />
            {file ? (
              <>
                <p className="text-sm font-semibold">{file.name}</p>
                <p className="text-xs text-muted-foreground mt-1">{(file.size / 1024).toFixed(1)} KB · clicca per cambiare</p>
              </>
            ) : (
              <>
                <p className="text-sm font-semibold">Clicca per selezionare il file</p>
                <p className="text-xs text-muted-foreground mt-1">.xlsx · .xls · .csv</p>
              </>
            )}
            <input
              ref={inputRef}
              id="xls-file-dialog"
              type="file"
              accept=".xlsx,.xls,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel,text/csv"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>

          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={onBack}>Annulla</Button>
            <Button size="sm" disabled={!file || loading} onClick={handleUpload} className="min-w-24">
              {loading ? "Importazione…" : "Importa"}
            </Button>
          </div>
        </>
      )}

      {result && (
        <div className="space-y-3">
          <div className="rounded-lg border border-border p-4 space-y-2">
            <div className="flex items-center gap-2 font-medium text-sm">
              <CheckCircle2 className="size-4 text-emerald-500" />
              Import completato
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="rounded-md bg-muted/30 p-2"><p className="text-muted-foreground">Righe lette</p><p className="font-bold text-base mt-0.5">{result.parsed_rows}</p></div>
              <div className="rounded-md bg-emerald-500/10 p-2"><p className="text-emerald-700 dark:text-emerald-400">Inserite</p><p className="font-bold text-base mt-0.5 text-emerald-700 dark:text-emerald-400">{result.inserted}</p></div>
              <div className="rounded-md bg-sky-500/10 p-2"><p className="text-sky-700 dark:text-sky-400">Aggiornate</p><p className="font-bold text-base mt-0.5 text-sky-700 dark:text-sky-400">{result.updated}</p></div>
              <div className="rounded-md bg-muted/30 p-2"><p className="text-muted-foreground">Scartate</p><p className="font-bold text-base mt-0.5">{result.skipped}</p></div>
            </div>
          </div>
          {result.errors.length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 max-h-32 overflow-y-auto">
              <div className="flex items-center gap-2 font-medium text-sm text-amber-700 dark:text-amber-400 mb-1.5">
                <AlertCircle className="size-4" />Avvisi ({result.errors.length})
              </div>
              <ul className="text-xs space-y-0.5 text-muted-foreground">
                {result.errors.slice(0, 10).map((e, i) => <li key={i}>· {e}</li>)}
                {result.errors.length > 10 && <li className="italic">… e altri {result.errors.length - 10}</li>}
              </ul>
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={reset}>Carica un altro</Button>
            <Button size="sm" onClick={onBack}><X className="size-3.5 mr-1" />Chiudi</Button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Griglia View ──────────────────────────────────────────────────────── */
type GiornoEdit = {
  data: string;
  iva10: string;
  iva22: string;
  altri: string;
  source: "manuale" | "xls" | "email";
  dirty: boolean;
};

type ModalitaMese = "giornaliero" | "mensile";

function buildMesiList(dataDa: string, dataA: string) {
  const mesi: { anno: number; mese: number; label: string }[] = [];
  const y0 = parseInt(dataDa.slice(0, 4), 10), m0 = parseInt(dataDa.slice(5, 7), 10);
  const y1 = parseInt(dataA.slice(0, 4), 10), m1 = parseInt(dataA.slice(5, 7), 10);
  for (let y = y0; y <= y1; y++) {
    const mFrom = y === y0 ? m0 : 1;
    const mTo = y === y1 ? m1 : 12;
    for (let m = mFrom; m <= mTo; m++) {
      mesi.push({ anno: y, mese: m, label: `${MESI_NOMI_SHORT[m - 1]} ${y}` });
    }
  }
  return mesi;
}

function daysInMonth(anno: number, mese: number): string[] {
  const count = new Date(anno, mese, 0).getDate();
  const days: string[] = [];
  for (let d = 1; d <= count; d++) {
    days.push(`${anno}-${String(mese).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  }
  return days;
}

function GrigliaView({
  dataDa, dataA, onSaved, onBack, onClose,
}: { dataDa: string; dataA: string; onSaved: () => void; onBack: () => void; onClose: () => void }) {
  const mesi = useMemo(() => buildMesiList(dataDa, dataA), [dataDa, dataA]);
  const [meseSel, setMeseSel] = useState(mesi[mesi.length - 1]);
  const [righe, setRighe] = useState<GiornoEdit[]>([]);
  const [modalita, setModalita] = useState<ModalitaMese>("giornaliero");
  const [loadingDati, setLoadingDati] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mensiIva10, setMensiIva10] = useState("");
  const [mensiIva22, setMensiIva22] = useState("");
  const [mensiAltri, setMensiAltri] = useState("");

  const meseKey = meseSel ? `${meseSel.anno}-${String(meseSel.mese).padStart(2, "0")}` : "";

  useEffect(() => {
    if (!meseSel) return;
    setLoadingDati(true);
    const pad = (n: number) => String(n).padStart(2, "0");
    const dataDaM = `${meseSel.anno}-${pad(meseSel.mese)}-01`;
    const dataAM = `${meseSel.anno}-${pad(meseSel.mese)}-${new Date(meseSel.anno, meseSel.mese, 0).getDate()}`;

    Promise.all([
      fetch(`/api/ricavi/giornalieri?${new URLSearchParams({ data_da: dataDaM, data_a: dataAM })}`)
        .then((r) => r.ok ? r.json() as Promise<RicaviGiornalieriResponse> : null).catch(() => null),
      fetch(`/api/ricavi/modalita?anno=${meseSel.anno}&mese=${meseSel.mese}`)
        .then((r) => r.ok ? r.json() : null).catch(() => null),
    ]).then(([ricaviData, modalitaData]) => {
      const days = daysInMonth(meseSel.anno, meseSel.mese);
      const byDate = new Map<string, RicavoGiornaliero>();
      for (const item of ricaviData?.items ?? []) byDate.set(item.data, item);
      setRighe(days.map((d) => {
        const ex = byDate.get(d);
        return {
          data: d,
          iva10: ex ? String(ex.fatturato_iva10 || "") : "",
          iva22: ex ? String(ex.fatturato_iva22 || "") : "",
          altri: ex ? String(ex.altri_ricavi_noiva || "") : "",
          source: ex?.source ?? "manuale",
          dirty: false,
        };
      }));
      const mod: ModalitaMese = modalitaData?.modalita ?? "giornaliero";
      setModalita(mod);
      if (mod === "mensile" && modalitaData) {
        setMensiIva10(String(modalitaData.fatturato_iva10 || ""));
        setMensiIva22(String(modalitaData.fatturato_iva22 || ""));
        setMensiAltri(String(modalitaData.altri_ricavi_noiva || ""));
      } else {
        setMensiIva10(""); setMensiIva22(""); setMensiAltri("");
      }
      setLoadingDati(false);
    });
  }, [meseKey]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSwitchModalita(nuova: ModalitaMese) {
    if (nuova === modalita) return;
    if (nuova === "mensile") {
      const ok = confirm(`Passando a Mensile per ${meseSel?.label}, i dati giornalieri esistenti verranno disabilitati nei Margini (ma NON eliminati). Continuare?`);
      if (!ok) return;
    }
    setModalita(nuova);
  }

  const nettoGriglia = useMemo(() =>
    righe.reduce((sum, r) => sum + scorporoNetto(
      parseFloat(r.iva10.replace(",", ".")) || 0,
      parseFloat(r.iva22.replace(",", ".")) || 0,
      parseFloat(r.altri.replace(",", ".")) || 0,
    ), 0), [righe]);

  const nettoMensile = useMemo(() => scorporoNetto(
    parseFloat(mensiIva10.replace(",", ".")) || 0,
    parseFloat(mensiIva22.replace(",", ".")) || 0,
    parseFloat(mensiAltri.replace(",", ".")) || 0,
  ), [mensiIva10, mensiIva22, mensiAltri]);

  async function handleSave() {
    if (!meseSel) return;
    setSaving(true);
    try {
      if (modalita === "giornaliero") {
        const dirty = righe.filter((r) => r.dirty);
        if (dirty.length === 0) { toast.info("Nessuna modifica da salvare"); setSaving(false); return; }
        const res = await fetch("/api/ricavi/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: dirty.map((r) => ({
            data: r.data,
            fatturato_iva10: parseFloat(r.iva10.replace(",", ".")) || 0,
            fatturato_iva22: parseFloat(r.iva22.replace(",", ".")) || 0,
            altri_ricavi_noiva: parseFloat(r.altri.replace(",", ".")) || 0,
          })) }),
        });
        if (!res.ok) throw new Error();
        const result: RicaviBatchUpsertResponse = await res.json();
        toast.success(`Salvati ${result.inserted + result.updated} giorni`);
      } else {
        const res = await fetch("/api/ricavi/modalita", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            anno: meseSel.anno, mese: meseSel.mese, modalita: "mensile",
            fatturato_iva10: parseFloat(mensiIva10.replace(",", ".")) || 0,
            fatturato_iva22: parseFloat(mensiIva22.replace(",", ".")) || 0,
            altri_ricavi_noiva: parseFloat(mensiAltri.replace(",", ".")) || 0,
          }),
        });
        if (!res.ok) throw new Error();
        toast.success(`Ricavi mensili ${meseSel.label} salvati`);
      }
      onSaved();
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSaving(false);
    }
  }

  function setRigaValues(idx: number, vals: { iva10: string; iva22: string; altri: string }) {
    setRighe((prev) => prev.map((r, i) => i === idx ? { ...r, ...vals, dirty: true } : r));
  }

  const giorniCompilati = useMemo(
    () => righe.filter((r) => r.iva10 || r.iva22 || r.altri).length,
    [righe],
  );

  if (!meseSel) return null;

  // Calcolo offset prima cella: lunedì = colonna 0
  const primoGiornoDow = new Date(meseSel.anno, meseSel.mese - 1, 1).getDay(); // 0=Dom
  const offsetLun = (primoGiornoDow + 6) % 7; // sposta in modo che Lun=0
  const dirtyCount = righe.filter((r) => r.dirty).length;

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
        ← Indietro
      </button>

      {/* Selettore mese + toggle modalità */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => { const i = mesi.findIndex((m) => m.label === meseSel.label); if (i > 0) setMeseSel(mesi[i - 1]); }}
            disabled={mesi[0]?.label === meseSel.label}
            className="size-9 flex items-center justify-center rounded-md border border-input hover:bg-muted disabled:opacity-30 transition-colors"
          ><ChevronLeft className="size-4" /></button>
          <select
            value={meseSel.label}
            onChange={(e) => { const f = mesi.find((m) => m.label === e.target.value); if (f) setMeseSel(f); }}
            className="rounded-md border border-input bg-background px-3 py-2 text-sm font-semibold min-w-32"
          >
            {mesi.map((m) => <option key={m.label} value={m.label}>{m.label}</option>)}
          </select>
          <button
            onClick={() => { const i = mesi.findIndex((m) => m.label === meseSel.label); if (i < mesi.length - 1) setMeseSel(mesi[i + 1]); }}
            disabled={mesi[mesi.length - 1]?.label === meseSel.label}
            className="size-9 flex items-center justify-center rounded-md border border-input hover:bg-muted disabled:opacity-30 transition-colors"
          ><ChevronRight className="size-4" /></button>
        </div>

        <div className="flex rounded-md border border-input overflow-hidden text-xs ml-auto">
          <button
            onClick={() => handleSwitchModalita("giornaliero")}
            className={`px-4 py-2 font-medium transition-colors ${modalita === "giornaliero" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >Giornaliero</button>
          <button
            onClick={() => handleSwitchModalita("mensile")}
            className={`px-4 py-2 font-medium border-l border-input transition-colors ${modalita === "mensile" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >Mensile</button>
        </div>
      </div>

      {loadingDati ? (
        <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : modalita === "mensile" ? (
        /* Blocco mensile */
        <div className="space-y-4 max-w-xl">
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
            ⚠️ In modalità Mensile i Margini usano questo totale. I dati giornalieri esistenti restano salvati ma vengono ignorati.
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              { label: "IVA 10% (lordo)", val: mensiIva10, set: setMensiIva10 },
              { label: "IVA 22% (lordo)", val: mensiIva22, set: setMensiIva22 },
              { label: "Altri (no IVA)", val: mensiAltri, set: setMensiAltri },
            ].map(({ label, val, set }) => (
              <div key={label} className="space-y-1.5">
                <Label className="text-xs">{label} €</Label>
                <Input type="number" step="0.01" min="0" value={val}
                  onChange={(e) => set(e.target.value)} placeholder="0,00"
                  className="text-right tabular-nums" />
              </div>
            ))}
          </div>
          <div className="rounded-lg border border-border bg-muted/20 p-3 text-sm flex items-center justify-between">
            <span className="text-muted-foreground">Fatturato netto stimato del mese</span>
            <strong className="text-primary tabular-nums text-lg">{nettoMensile > 0 ? formatEuro(nettoMensile) : "—"}</strong>
          </div>
        </div>
      ) : (
        /* Calendario mensile */
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">
              Clicca un giorno per inserire i ricavi (lordi). Lo scorporo IVA è automatico.
            </span>
            <span className="flex items-center gap-3">
              <span className="text-muted-foreground">{giorniCompilati} giorni compilati</span>
              <span className="font-semibold text-foreground">Netto mese: {formatEuro(nettoGriglia)}</span>
            </span>
          </div>

          {/* Intestazione giorni settimana */}
          <div className="grid grid-cols-7 gap-1.5">
            {["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map((d) => (
              <div key={d} className="text-center text-[11px] font-semibold uppercase tracking-wider text-muted-foreground py-1">
                {d}
              </div>
            ))}
          </div>

          {/* Griglia giorni */}
          <div className="grid grid-cols-7 gap-1.5">
            {Array.from({ length: offsetLun }).map((_, i) => <div key={`pad-${i}`} />)}
            {righe.map((r, idx) => {
              const date = new Date(r.data + "T00:00:00");
              const giorno = parseInt(r.data.slice(8), 10);
              const isWeekend = date.getDay() === 0 || date.getDay() === 6;
              const i10 = (parseFloat(r.iva10.replace(",", ".")) || 0) / 1.10;
              const i22 = (parseFloat(r.iva22.replace(",", ".")) || 0) / 1.22;
              const alt = parseFloat(r.altri.replace(",", ".")) || 0;
              const netto = i10 + i22 + alt;
              const hasData = !!(r.iva10 || r.iva22 || r.altri);
              return (
                <GiornoCell
                  key={r.data}
                  giorno={giorno}
                  netto={netto}
                  hasData={hasData}
                  dirty={r.dirty}
                  isWeekend={isWeekend}
                  source={r.source}
                  iva10={r.iva10}
                  iva22={r.iva22}
                  altri={r.altri}
                  onSave={(vals) => setRigaValues(idx, vals)}
                />
              );
            })}
          </div>

          {/* Riepilogo totali */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
            <TotaleBox label="IVA 10% (netto)" value={righe.reduce((s, r) => s + (parseFloat(r.iva10.replace(",", ".")) || 0) / 1.10, 0)} />
            <TotaleBox label="IVA 22% (netto)" value={righe.reduce((s, r) => s + (parseFloat(r.iva22.replace(",", ".")) || 0) / 1.22, 0)} />
            <TotaleBox label="Altri (no IVA)" value={righe.reduce((s, r) => s + (parseFloat(r.altri.replace(",", ".")) || 0), 0)} />
            <TotaleBox label="Netto totale" value={nettoGriglia} primary />
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between pt-3 border-t border-border">
        <span className="text-xs text-muted-foreground">
          {modalita === "giornaliero" && dirtyCount > 0 && `${dirtyCount} giorni modificati`}
        </span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => { onSaved(); onClose(); }}>
            <RefreshCw className="size-3 mr-1" />
            Aggiorna e chiudi
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving || (modalita === "giornaliero" && dirtyCount === 0)}
            className="min-w-28"
          >
            {saving ? "Salvataggio…" : `Salva ${meseSel.label}`}
          </Button>
        </div>
      </div>
    </div>
  );
}

function TotaleBox({ label, value, primary = false }: { label: string; value: number; primary?: boolean }) {
  return (
    <div className={`rounded-lg border p-2.5 ${primary ? "border-primary/30 bg-primary/5" : "border-border bg-muted/20"}`}>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`text-sm font-bold tabular-nums mt-0.5 ${primary ? "text-primary" : ""}`}>{formatEuro(value)}</p>
    </div>
  );
}

/* ─── Cella giorno del calendario con popover di inserimento ──────────────── */
function GiornoCell({
  giorno, netto, hasData, dirty, isWeekend, source,
  iva10, iva22, altri, onSave,
}: {
  giorno: number;
  netto: number;
  hasData: boolean;
  dirty: boolean;
  isWeekend: boolean;
  source: "manuale" | "xls" | "email";
  iva10: string;
  iva22: string;
  altri: string;
  onSave: (vals: { iva10: string; iva22: string; altri: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [d10, setD10] = useState(iva10);
  const [d22, setD22] = useState(iva22);
  const [dAltri, setDAltri] = useState(altri);

  useEffect(() => {
    if (open) { setD10(iva10); setD22(iva22); setDAltri(altri); }
  }, [open, iva10, iva22, altri]);

  const previewNetto = scorporoNetto(
    parseFloat(d10.replace(",", ".")) || 0,
    parseFloat(d22.replace(",", ".")) || 0,
    parseFloat(dAltri.replace(",", ".")) || 0,
  );

  function confirm() {
    onSave({ iva10: d10, iva22: d22, altri: dAltri });
    setOpen(false);
  }

  function clear() {
    setD10(""); setD22(""); setDAltri("");
    onSave({ iva10: "", iva22: "", altri: "" });
    setOpen(false);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            className={`min-h-16 rounded-lg border p-2 flex flex-col items-start justify-between text-left transition-all hover:border-primary/50 hover:shadow-sm ${
              dirty
                ? "border-sky-500/60 bg-sky-500/10"
                : hasData
                ? "border-emerald-500/40 bg-emerald-500/5"
                : isWeekend
                ? "border-border bg-muted/30"
                : "border-border bg-card"
            }`}
          >
            <div className="flex items-center justify-between w-full">
              <span className={`text-sm font-bold ${hasData || dirty ? "" : "text-muted-foreground"}`}>{giorno}</span>
              {source !== "manuale" && hasData && (
                <span className={`text-[8px] px-1 rounded font-semibold ${SOURCE_LABEL[source]?.color}`}>
                  {SOURCE_LABEL[source]?.label}
                </span>
              )}
            </div>
            <span className={`text-xs tabular-nums font-semibold w-full ${netto > 0 ? "text-primary" : "text-muted-foreground/30"}`}>
              {netto > 0 ? formatEuro(netto) : "—"}
            </span>
          </button>
        }
      />
      <PopoverContent className="w-72" align="center">
        <div className="space-y-3">
          <p className="text-sm font-semibold border-b border-border pb-2">Giorno {giorno}</p>
          {[
            { label: "IVA 10% (lordo €)", val: d10, set: setD10 },
            { label: "IVA 22% (lordo €)", val: d22, set: setD22 },
            { label: "Altri ricavi no IVA (€)", val: dAltri, set: setDAltri },
          ].map(({ label, val, set }) => (
            <div key={label} className="space-y-1">
              <Label className="text-xs">{label}</Label>
              <Input
                type="number" step="0.01" min="0" value={val}
                onChange={(e) => set(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") confirm(); }}
                placeholder="0,00"
                className="text-right tabular-nums h-9"
                autoFocus={label.startsWith("IVA 10")}
              />
            </div>
          ))}
          <div className="rounded-md bg-muted/30 px-2.5 py-1.5 text-xs flex items-center justify-between">
            <span className="text-muted-foreground">Netto</span>
            <strong className="text-primary tabular-nums">{previewNetto > 0 ? formatEuro(previewNetto) : "—"}</strong>
          </div>
          <div className="flex items-center justify-between gap-2 pt-1">
            {hasData ? (
              <button onClick={clear} className="text-xs text-rose-600 hover:text-rose-700 flex items-center gap-1">
                <Trash2 className="size-3" /> Svuota
              </button>
            ) : <span />}
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>Annulla</Button>
              <Button size="sm" onClick={confirm}>Conferma</Button>
            </div>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
