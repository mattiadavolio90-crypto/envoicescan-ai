"use client";

import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { type VoceInventario, type ArticoloInventario, UM_INVENTARIO } from "@/lib/inventario";

const selectCls =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500";

interface Props {
  open: boolean;
  voce: VoceInventario | null;
  dataInventario: string;
  onClose: () => void;
  onSaved: () => void;
}

export function InventarioAggiungiDialog({ open, voce, dataInventario, onClose, onSaved }: Props) {
  const isEdit = voce != null;

  const [articoli, setArticoli] = useState<ArticoloInventario[]>([]);
  const [nomePopoverOpen, setNomePopoverOpen] = useState(false);
  const [daFattura, setDaFattura] = useState(false);

  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState("");
  const [quantita, setQuantita] = useState("");
  const [um, setUm] = useState("KG");
  const [prezzoUm, setPrezzoUm] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDaFattura(false);
    setNomePopoverOpen(false);
    if (isEdit && voce) {
      setNome(voce.nome);
      setCategoria(voce.categoria);
      setQuantita(String(voce.quantita));
      setUm(voce.um);
      setPrezzoUm(String(voce.prezzo_unitario));
      setNote(voce.note ?? "");
    } else {
      setNome("");
      setCategoria("");
      setQuantita("");
      setUm("KG");
      setPrezzoUm("");
      setNote("");
    }
    fetch("/api/workspace/inventario/articoli")
      .then(r => r.json())
      .then(d => setArticoli(d.articoli ?? []))
      .catch(() => {});
  }, [open, isEdit, voce]);

  const suggerimenti = !isEdit && nome.length >= 2
    ? articoli.filter(a => a.nome.toLowerCase().includes(nome.toLowerCase())).slice(0, 8)
    : [];

  function selezionaArticolo(art: ArticoloInventario) {
    setNome(art.nome);
    setCategoria(art.categoria);
    setPrezzoUm(art.prezzo_unitario > 0 ? String(art.prezzo_unitario) : "");
    setUm(art.um);
    setDaFattura(true);
    setNomePopoverOpen(false);
  }

  function onNomeChange(v: string) {
    setNome(v);
    setDaFattura(false);
    setNomePopoverOpen(v.length >= 2);
  }

  async function salva() {
    if (!nome.trim()) { toast.error("Inserisci il nome del prodotto"); return; }
    const q = parseFloat(quantita);
    if (isNaN(q) || q < 0) { toast.error("Quantità non valida"); return; }
    const p = parseFloat(prezzoUm) || 0;

    setSaving(true);
    try {
      if (isEdit && voce) {
        const res = await fetch(`/api/workspace/inventario/${voce.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nome: nome.trim(), categoria: categoria.trim(),
            quantita: q, um, prezzo_unitario: p,
            note: note.trim() || null,
          }),
        });
        if (!res.ok) throw new Error();
        toast.success("Voce aggiornata");
      } else {
        const res = await fetch("/api/workspace/inventario", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            data_inventario: dataInventario,
            nome: nome.trim(), categoria: categoria.trim(),
            quantita: q, um, prezzo_unitario: p,
            note: note.trim() || null,
          }),
        });
        if (!res.ok) throw new Error();
        toast.success("Voce aggiunta");
      }
      onSaved();
      onClose();
    } catch {
      toast.error("Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  const valoreCalcolato =
    quantita && prezzoUm && !isNaN(parseFloat(quantita)) && !isNaN(parseFloat(prezzoUm))
      ? parseFloat(quantita) * parseFloat(prezzoUm)
      : null;

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="w-full sm:max-w-lg gap-5">
        <DialogTitle>{isEdit ? "Modifica voce" : "Aggiungi prodotto"}</DialogTitle>

        {/* Nome prodotto con autocomplete dalle fatture */}
        <div className="relative space-y-1.5">
          <Label className="text-sm font-medium block">Nome prodotto</Label>
          <Input
            value={nome}
            onChange={e => onNomeChange(e.target.value)}
            onFocus={() => { if (nome.length >= 2) setNomePopoverOpen(true); }}
            onBlur={() => setTimeout(() => setNomePopoverOpen(false), 150)}
            placeholder="Digita per cercare nelle fatture o inserisci manualmente…"
            className="focus:ring-sky-500 focus:border-sky-500"
            autoFocus={!isEdit}
          />
          {nomePopoverOpen && suggerimenti.length > 0 && (
            <div className="absolute z-50 w-full mt-1 rounded-md border border-border bg-popover shadow-md max-h-52 overflow-y-auto">
              {suggerimenti.map((a, i) => (
                <button
                  key={i}
                  onMouseDown={() => selezionaArticolo(a)}
                  className="w-full text-left px-3 py-2.5 text-sm hover:bg-accent transition-colors"
                >
                  <span className="font-medium">{a.nome}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {a.categoria} · {a.um}
                    {a.prezzo_unitario > 0 && ` · €${a.prezzo_unitario.toFixed(4)}`}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Categoria */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium block">Categoria</Label>
          <Input
            value={categoria}
            onChange={e => setCategoria(e.target.value)}
            placeholder="Es. LATTICINI"
            className="focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        {/* Quantità + UM + Prezzo/UM */}
        <div className="grid grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label className="text-sm font-medium block">Quantità</Label>
            <Input
              type="number"
              min={0}
              step="0.001"
              value={quantita}
              onChange={e => setQuantita(e.target.value)}
              placeholder="0"
              className="focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-sm font-medium block">UM</Label>
            {/* UM bloccata se prodotto selezionato da fattura (in modalità aggiungi) */}
            {daFattura && !isEdit ? (
              <div className="h-10 w-full flex items-center px-3 rounded-md border border-border bg-muted text-sm font-medium">
                {um}
              </div>
            ) : (
              <select value={um} onChange={e => setUm(e.target.value)} className={selectCls}>
                {UM_INVENTARIO.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            )}
          </div>
          <div className="space-y-1.5">
            <Label className="text-sm font-medium block whitespace-nowrap">Prezzo/UM (€)</Label>
            <Input
              type="number"
              min={0}
              step="0.0001"
              value={prezzoUm}
              onChange={e => setPrezzoUm(e.target.value)}
              placeholder="0.00"
              className="focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
        </div>

        {/* Valore live */}
        {valoreCalcolato !== null && (
          <p className="text-sm text-muted-foreground -mt-1">
            Valore:{" "}
            <span className="font-semibold text-foreground">
              {new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(valoreCalcolato)}
            </span>
          </p>
        )}

        {/* Note */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium block">Note (opzionale)</Label>
          <Input
            value={note}
            onChange={e => setNote(e.target.value)}
            placeholder="Es. marca, lotto, scaffale…"
            className="focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
          <Button onClick={salva} disabled={saving}>
            {saving ? "Salvataggio…" : isEdit ? "Aggiorna" : "Aggiungi"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
