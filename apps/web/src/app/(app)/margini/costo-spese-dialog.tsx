"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Wallet } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatEuro } from "./periodi";

export type TipoSpesaCella = "fb" | "generale";

type Props = {
  open: boolean;
  tipo: TipoSpesaCella;
  anno: number;
  mese: number;
  label: string;
  valore: number;
  onClose: () => void;
  onSaved: () => void;
};

type CalcoloSpese = {
  totale_fb: number;
  totale_generale: number;
  n_voci_fb: number;
  n_voci_generale: number;
};

function toStr(v: number) {
  return v > 0 ? String(Math.round(v * 100) / 100).replace(".", ",") : "";
}

const META: Record<TipoSpesaCella, { titolo: string; campo: string; colore: string }> = {
  fb: { titolo: "Altri Costi F&B", campo: "altri_costi_fb", colore: "text-orange-500" },
  generale: { titolo: "Altre Spese Generali", campo: "altri_costi_spese", colore: "text-purple-500" },
};

export function CostoSpeseDialog({ open, tipo, anno, mese, label, valore, onClose, onSaved }: Props) {
  const meta = META[tipo];
  const [importo, setImporto] = useState("");
  const [recuperando, setRecuperando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [sintesi, setSintesi] = useState<CalcoloSpese | null>(null);

  useEffect(() => {
    if (open) {
      setImporto(toStr(valore));
      setSintesi(null);
    }
  }, [open, valore]);

  async function recuperaDaSpese() {
    setRecuperando(true);
    try {
      const res = await fetch(`/api/margini/costo-spese-extra?anno=${anno}&mese=${mese}`, { cache: "no-store" });
      if (!res.ok) throw new Error();
      const d: CalcoloSpese = await res.json();
      setSintesi(d);
      const totale = tipo === "fb" ? d.totale_fb : d.totale_generale;
      const nVoci = tipo === "fb" ? d.n_voci_fb : d.n_voci_generale;
      if (nVoci === 0) {
        toast.info(`Nessuna spesa di questo tipo registrata per ${label} nel tab Spese`);
        return;
      }
      setImporto(toStr(totale));
      toast.success("Valore recuperato dalle spese — puoi modificarlo prima di salvare");
    } catch {
      toast.error("Errore nel recupero dal tab Spese");
    } finally {
      setRecuperando(false);
    }
  }

  async function salva() {
    const val = parseFloat(importo.replace(",", ".")) || 0;
    if (val < 0) { toast.error("Il valore non può essere negativo"); return; }
    setSalvando(true);
    try {
      const res = await fetch("/api/margini/cella", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ anno, mese, field: meta.campo, value: val }),
      });
      if (!res.ok) throw new Error();
      toast.success(`${meta.titolo} salvato`);
      onSaved();
      onClose();
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSalvando(false);
    }
  }

  const nVoci = sintesi ? (tipo === "fb" ? sintesi.n_voci_fb : sintesi.n_voci_generale) : 0;
  const val = parseFloat(importo.replace(",", ".")) || 0;

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className={`size-4 ${meta.colore}`} />
            {meta.titolo} — {label}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-1">
          <Button
            variant="outline"
            className="w-full justify-center"
            onClick={recuperaDaSpese}
            disabled={recuperando}
          >
            <RefreshCw className={`size-4 mr-2 ${recuperando ? "animate-spin" : ""}`} />
            {recuperando ? "Recupero…" : "Recupera dal tab Spese"}
          </Button>

          {sintesi && nVoci > 0 && (
            <p className="text-xs text-muted-foreground -mt-1 text-center">
              {nVoci} {nVoci === 1 ? "voce" : "voci"} di spesa nel mese
            </p>
          )}

          <div className="relative flex items-center">
            <div className="flex-1 border-t border-border" />
            <span className="px-2 text-[11px] uppercase tracking-wider text-muted-foreground">oppure inserisci a mano</span>
            <div className="flex-1 border-t border-border" />
          </div>

          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{meta.titolo} (€)</label>
            <Input
              type="text"
              inputMode="decimal"
              value={importo}
              onChange={e => setImporto(e.target.value.replace(/[^0-9,.]/g, ""))}
              placeholder="0"
            />
          </div>

          <p className="text-xs text-muted-foreground text-right">
            Totale: <span className="font-semibold tabular-nums text-foreground">{formatEuro(val)}</span>
          </p>

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onClose} disabled={salvando}>Annulla</Button>
            <Button onClick={salva} disabled={salvando}>{salvando ? "Salvo…" : "Salva"}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
