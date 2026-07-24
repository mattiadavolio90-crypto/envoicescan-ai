"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Upload, X,
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
  RicaviBatchUpsertResponse,
} from "@/lib/ricavi";

type Props = {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  dataDa: string;
  dataA: string;
  onImported: () => void;
};

const SOURCE_LABEL: Record<string, { label: string; color: string }> = {
  manuale: { label: "Manuale", color: "bg-slate-500/15 text-slate-700 dark:text-slate-300" },
  xls: { label: "XLS", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  email: { label: "Email", color: "bg-sky-500/15 text-sky-700 dark:text-sky-400" },
};

export function CaricaRicaviDialog({ open, onOpenChange, dataDa, dataA, onImported }: Props) {
  function handleClose() {
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(1100px,92vw)] w-full max-h-[90vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0 flex-row items-start justify-between gap-4">
          <div className="space-y-1">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Upload className="size-4 text-primary" />
              Inserimento manuale
            </DialogTitle>
            <DialogDescription className="text-xs">
              Scegli se inserire i ricavi mensilmente o giornalmente.
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
          <GrigliaView dataDa={dataDa} dataA={dataA} onSaved={onImported} onClose={handleClose} />
        </div>
      </DialogContent>
    </Dialog>
  );
}

/* ─── Griglia View ──────────────────────────────────────────────────────── */
type GiornoEdit = {
  data: string;
  iva10: string;
  iva22: string;
  altri: string;
  coperti: string;
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
  dataDa, dataA, onSaved, onClose,
}: { dataDa: string; dataA: string; onSaved: () => void; onClose: () => void }) {
  const mesi = useMemo(() => buildMesiList(dataDa, dataA), [dataDa, dataA]);
  const [meseSel, setMeseSel] = useState(mesi[mesi.length - 1]);
  const [righe, setRighe] = useState<GiornoEdit[]>([]);
  const [modalita, setModalita] = useState<ModalitaMese>("mensile");
  const [loadingDati, setLoadingDati] = useState(false);
  const [saving, setSaving] = useState(false);
  const [mensiIva10, setMensiIva10] = useState("");
  const [mensiIva22, setMensiIva22] = useState("");
  const [mensiAltri, setMensiAltri] = useState("");
  const [mensiCoperti, setMensiCoperti] = useState("");

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
          coperti: ex && ex.coperti != null ? String(ex.coperti) : "",
          source: ex?.source ?? "manuale",
          dirty: false,
        };
      }));
      const mod: ModalitaMese = modalitaData?.modalita ?? "giornaliero";
      if (mod === "mensile" && modalitaData) {
        setMensiIva10(String(modalitaData.fatturato_iva10 || ""));
        setMensiIva22(String(modalitaData.fatturato_iva22 || ""));
        setMensiAltri(String(modalitaData.altri_ricavi_noiva || ""));
        setMensiCoperti(modalitaData.coperti != null ? String(modalitaData.coperti) : "");
      } else {
        const items = ricaviData?.items ?? [];
        const sommaIva10 = items.reduce((s, it) => s + (it.fatturato_iva10 || 0), 0);
        const sommaIva22 = items.reduce((s, it) => s + (it.fatturato_iva22 || 0), 0);
        const sommaAltri = items.reduce((s, it) => s + (it.altri_ricavi_noiva || 0), 0);
        const sommaCoperti = items.reduce((s, it) => s + (it.coperti || 0), 0);
        setMensiIva10(sommaIva10 > 0 ? String(sommaIva10) : "");
        setMensiIva22(sommaIva22 > 0 ? String(sommaIva22) : "");
        setMensiAltri(sommaAltri > 0 ? String(sommaAltri) : "");
        setMensiCoperti(sommaCoperti > 0 ? String(sommaCoperti) : "");
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

  async function handleSave(opts?: { silentIfClean?: boolean }) {
    if (!meseSel) return;
    setSaving(true);
    try {
      if (modalita === "giornaliero") {
        const dirty = righe.filter((r) => r.dirty);
        if (dirty.length === 0) {
          if (!opts?.silentIfClean) toast.info("Nessuna modifica da salvare");
          setSaving(false);
          return;
        }
        const res = await fetch("/api/ricavi/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ items: dirty.map((r) => ({
            data: r.data,
            fatturato_iva10: parseFloat(r.iva10.replace(",", ".")) || 0,
            fatturato_iva22: parseFloat(r.iva22.replace(",", ".")) || 0,
            altri_ricavi_noiva: parseFloat(r.altri.replace(",", ".")) || 0,
            coperti: r.coperti.trim() !== "" ? Math.max(0, Math.round(parseFloat(r.coperti.replace(",", ".")) || 0)) : null,
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
            coperti: mensiCoperti.trim() !== "" ? Math.max(0, Math.round(parseFloat(mensiCoperti.replace(",", ".")) || 0)) : null,
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

  function setRigaValues(idx: number, vals: { iva10: string; iva22: string; altri: string; coperti: string }) {
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
            ⚠️ Inserendo i dati in modalità mensile, avranno precedenza rispetto ai dati inseriti giornalieri. Usare la modalità mensile solo se non si caricano i ricavi giornalieri.
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
          <div className="space-y-1.5 max-w-xs">
            <Label className="text-xs">Coperti del mese (opzionale)</Label>
            <Input type="number" step="1" min="0" value={mensiCoperti}
              onChange={(e) => setMensiCoperti(e.target.value)} placeholder="es. 1200"
              className="text-right tabular-nums" />
            <p className="text-[11px] text-muted-foreground">
              Totale persone servite nel mese. Serve per lo scontrino medio e il tab Coperti.
            </p>
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
                  coperti={r.coperti}
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
          <Button
            variant="ghost"
            size="sm"
            disabled={saving}
            onClick={async () => { await handleSave({ silentIfClean: true }); onClose(); }}
          >
            <RefreshCw className="size-3 mr-1" />
            Aggiorna e chiudi
          </Button>
          <Button
            size="sm"
            onClick={() => handleSave()}
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
  iva10, iva22, altri, coperti, onSave,
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
  coperti: string;
  onSave: (vals: { iva10: string; iva22: string; altri: string; coperti: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [d10, setD10] = useState(iva10);
  const [d22, setD22] = useState(iva22);
  const [dAltri, setDAltri] = useState(altri);
  const [dCoperti, setDCoperti] = useState(coperti);

  useEffect(() => {
    if (open) { setD10(iva10); setD22(iva22); setDAltri(altri); setDCoperti(coperti); }
  }, [open, iva10, iva22, altri, coperti]);

  const previewNetto = scorporoNetto(
    parseFloat(d10.replace(",", ".")) || 0,
    parseFloat(d22.replace(",", ".")) || 0,
    parseFloat(dAltri.replace(",", ".")) || 0,
  );

  function confirm() {
    onSave({ iva10: d10, iva22: d22, altri: dAltri, coperti: dCoperti });
    setOpen(false);
  }

  function clear() {
    setD10(""); setD22(""); setDAltri(""); setDCoperti("");
    onSave({ iva10: "", iva22: "", altri: "", coperti: "" });
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
          <div className="space-y-1">
            <Label className="text-xs">Coperti (opzionale)</Label>
            <Input
              type="number" step="1" min="0" value={dCoperti}
              onChange={(e) => setDCoperti(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") confirm(); }}
              placeholder="0"
              className="text-right tabular-nums h-9"
            />
          </div>
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
