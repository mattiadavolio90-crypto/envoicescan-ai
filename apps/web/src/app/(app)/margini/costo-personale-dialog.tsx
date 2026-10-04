"use client";

import { useEffect, useState } from "react";
import { RefreshCw, Users } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatEuro } from "./periodi";
import { parseNumeroItOZero } from "@/lib/format";
import {
  type CalcoloTurni, esitoRecuperoTurni, mostraCostoAssenze,
  sintesiRecuperoTurni, totalePersonale, vociPersonaleValide,
  celleDaSalvare,
} from "@/lib/costo-personale-turni";

type Props = {
  open: boolean;
  anno: number;
  mese: number;
  label: string;
  costoDipendenti: number;
  costoExtra: number;
  costoChiamata: number;
  onClose: () => void;
  onSaved: () => void;
};

function toStr(v: number) {
  return v > 0 ? String(Math.round(v * 100) / 100).replace(".", ",") : "";
}

export function CostoPersonaleDialog({
  open, anno, mese, label, costoDipendenti, costoExtra, costoChiamata, onClose, onSaved,
}: Props) {
  const [lordo, setLordo] = useState("");
  const [extra, setExtra] = useState("");
  const [chiamata, setChiamata] = useState("");
  const [recuperando, setRecuperando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [sintesi, setSintesi] = useState<CalcoloTurni | null>(null);

  useEffect(() => {
    if (open) {
      setLordo(toStr(costoDipendenti));
      setExtra(toStr(costoExtra));
      setChiamata(toStr(costoChiamata));
      setSintesi(null);
    }
  }, [open, costoDipendenti, costoExtra, costoChiamata]);

  async function recuperaDaPersonale() {
    setRecuperando(true);
    try {
      const res = await fetch(`/api/margini/costo-personale-turni?anno=${anno}&mese=${mese}`, { cache: "no-store" });
      if (!res.ok) throw new Error();
      const d: CalcoloTurni = await res.json();
      setSintesi(d);
      const esito = esitoRecuperoTurni(d);
      if (esito.azione === "nessun_turno") {
        toast.info(`Nessun turno registrato per ${label} nel tab Personale`);
        return;
      }
      if (esito.azione === "non_valorizzati") {
        // Niente da scrivere: i campi restano come sono, o un "Recupera" a vuoto
        // azzererebbe il costo personale del mese nel MOL.
        toast.warning("I turni del mese non hanno un costo orario impostato: imposta il costo nel tab Personale o inserisci a mano");
        return;
      }
      setLordo(toStr(esito.lordo));
      setExtra(toStr(esito.extra));
      setChiamata(toStr(esito.chiamata));
      if (esito.nSenzaCosto > 0) {
        toast.warning(`${esito.nSenzaCosto} turni senza costo orario sono stati ignorati nel calcolo`);
      } else {
        toast.success("Valori recuperati dai turni — puoi modificarli prima di salvare");
      }
    } catch {
      toast.error("Errore nel recupero dal tab Personale");
    } finally {
      setRecuperando(false);
    }
  }

  async function salvaCampo(field: string, value: number) {
    const res = await fetch("/api/margini/cella", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anno, mese, field, value }),
    });
    if (!res.ok) throw new Error();
  }

  async function salva() {
    const vLordo = parseNumeroItOZero(lordo);
    const vExtra = parseNumeroItOZero(extra);
    const vChiamata = parseNumeroItOZero(chiamata);
    if (!vociPersonaleValide(vLordo, vExtra, vChiamata)) { toast.error("I valori non possono essere negativi"); return; }
    setSalvando(true);
    try {
      for (const [field, value] of celleDaSalvare(vLordo, vExtra, vChiamata)) {
        await salvaCampo(field, value);
      }
      toast.success("Costo del personale salvato");
      onSaved();
      onClose();
    } catch {
      toast.error("Errore nel salvataggio");
    } finally {
      setSalvando(false);
    }
  }

  const vLordo = parseNumeroItOZero(lordo);
  const vExtra = parseNumeroItOZero(extra);
  const vChiamata = parseNumeroItOZero(chiamata);
  const totale = totalePersonale(vLordo, vExtra, vChiamata);
  const rigaSintesi = sintesiRecuperoTurni(sintesi);

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="size-4 text-primary" />
            Costo del personale — {label}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 mt-1">
          <Button
            variant="outline"
            className="w-full justify-center"
            onClick={recuperaDaPersonale}
            disabled={recuperando}
          >
            <RefreshCw className={`size-4 mr-2 ${recuperando ? "animate-spin" : ""}`} />
            {recuperando ? "Recupero…" : "Recupera dal tab Personale"}
          </Button>

          {sintesi && (sintesi.n_turni > 0 || sintesi.n_giorni_assenza > 0) && (
            <div className="text-xs text-muted-foreground -mt-1 text-center space-y-1">
              {rigaSintesi && <p>{rigaSintesi}</p>}
              {mostraCostoAssenze(sintesi) && (
                <p>
                  Ferie/malattia a carico: {formatEuro(sintesi.costo_assenze_a_carico)} su{" "}
                  {sintesi.n_giorni_assenza} {sintesi.n_giorni_assenza === 1 ? "giorno" : "giorni"} — non
                  incluso qui sopra, aggiungilo a mano se lo vuoi nel MOL.
                </p>
              )}
            </div>
          )}

          <div className="relative flex items-center">
            <div className="flex-1 border-t border-border" />
            <span className="px-2 text-[11px] uppercase tracking-wider text-muted-foreground">oppure inserisci a mano</span>
            <div className="flex-1 border-t border-border" />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {([
              ["Lordo (€)", lordo, setLordo],
              ["Ore extra (€)", extra, setExtra],
              ["Chiamata (€)", chiamata, setChiamata],
            ] as const).map(([etichetta, valore, imposta]) => (
              <div key={etichetta}>
                <label className="text-xs font-medium text-muted-foreground mb-1 block">{etichetta}</label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={valore}
                  onChange={e => imposta(e.target.value.replace(/[^0-9,.]/g, ""))}
                  placeholder="0"
                />
              </div>
            ))}
          </div>

          <p className="text-xs text-muted-foreground text-right">
            Totale personale: <span className="font-semibold tabular-nums text-foreground">{formatEuro(totale)}</span>
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
