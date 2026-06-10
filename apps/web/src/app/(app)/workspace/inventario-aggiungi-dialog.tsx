"use client";

import { useState, useEffect } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { type VoceInventario, type ArticoloInventario, UM_INVENTARIO } from "@/lib/inventario";

const selectCls =
  "h-10 w-full rounded-md border border-input bg-background px-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500";

function fmtEuro(v: number) {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

interface BozzaVoce {
  nome: string;
  categoria: string;
  quantita: number;
  um: string;
  prezzo_unitario: number;
  note: string | null;
}

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
  // true finché l'utente non tocca a mano il prezzo: permette l'auto-fill dal nome
  const [prezzoAuto, setPrezzoAuto] = useState(true);

  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState("");
  const [quantita, setQuantita] = useState("");
  const [um, setUm] = useState("KG");
  const [prezzoUm, setPrezzoUm] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  // Coda di prodotti da inserire insieme (solo in modalità aggiungi)
  const [bozze, setBozze] = useState<BozzaVoce[]>([]);

  function resetForm() {
    setNome("");
    setCategoria("");
    setQuantita("");
    setUm("KG");
    setPrezzoUm("");
    setNote("");
    setDaFattura(false);
    setPrezzoAuto(true);
    setNomePopoverOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    setBozze([]);
    if (isEdit && voce) {
      setNome(voce.nome);
      setCategoria(voce.categoria);
      setQuantita(String(voce.quantita));
      setUm(voce.um);
      setPrezzoUm(String(voce.prezzo_unitario));
      setNote(voce.note ?? "");
      setDaFattura(false);
      setPrezzoAuto(false);
      setNomePopoverOpen(false);
    } else {
      resetForm();
    }
    fetch("/api/workspace/inventario/articoli")
      .then(r => r.json())
      .then(d => setArticoli(d.articoli ?? []))
      .catch(() => {});
  }, [open, isEdit, voce]);

  const suggerimenti = !isEdit && nome.length >= 2
    ? articoli.filter(a => a.nome.toLowerCase().includes(nome.toLowerCase())).slice(0, 8)
    : [];

  function applicaArticolo(art: ArticoloInventario, lockUm: boolean) {
    setCategoria(art.categoria);
    setUm(art.um);
    if (prezzoAuto) {
      setPrezzoUm(art.prezzo_unitario > 0 ? String(art.prezzo_unitario) : "");
    }
    setDaFattura(lockUm);
  }

  function selezionaArticolo(art: ArticoloInventario) {
    setNome(art.nome);
    // selezione esplicita: forza il prezzo dalla fattura e blocca la UM
    setPrezzoUm(art.prezzo_unitario > 0 ? String(art.prezzo_unitario) : "");
    setPrezzoAuto(true);
    setCategoria(art.categoria);
    setUm(art.um);
    setDaFattura(true);
    setNomePopoverOpen(false);
  }

  function onNomeChange(v: string) {
    setNome(v);
    setNomePopoverOpen(v.length >= 2);
    // Auto-fill se il nome digitato coincide esattamente con un articolo noto
    const match = articoli.find(a => a.nome.toLowerCase() === v.trim().toLowerCase());
    if (match) {
      applicaArticolo(match, false);
    } else {
      setDaFattura(false);
    }
  }

  function onPrezzoChange(v: string) {
    setPrezzoUm(v);
    setPrezzoAuto(false); // l'utente ha preso il controllo manuale del prezzo
  }

  function leggiForm(): BozzaVoce | null {
    if (!nome.trim()) { toast.error("Inserisci il nome del prodotto"); return null; }
    const q = parseFloat(quantita);
    if (isNaN(q) || q < 0) { toast.error("Quantità non valida"); return null; }
    const p = parseFloat(prezzoUm) || 0;
    return {
      nome: nome.trim(),
      categoria: categoria.trim(),
      quantita: q,
      um,
      prezzo_unitario: p,
      note: note.trim() || null,
    };
  }

  function aggiungiAllaLista() {
    const b = leggiForm();
    if (!b) return;
    setBozze(prev => [...prev, b]);
    resetForm();
    setTimeout(() => {
      document.querySelector<HTMLInputElement>('[data-slot="input"]')?.focus();
    }, 0);
  }

  function rimuoviBozza(i: number) {
    setBozze(prev => prev.filter((_, idx) => idx !== i));
  }

  async function salva() {
    setSaving(true);
    try {
      if (isEdit && voce) {
        const b = leggiForm();
        if (!b) { setSaving(false); return; }
        const res = await fetch(`/api/workspace/inventario/${voce.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...b, note: b.note }),
        });
        if (!res.ok) throw new Error();
        toast.success("Voce aggiornata");
      } else {
        // Includi anche l'eventuale prodotto ancora nel form se compilato
        const voci = [...bozze];
        if (nome.trim()) {
          const b = leggiForm();
          if (!b) { setSaving(false); return; }
          voci.push(b);
        }
        if (voci.length === 0) { toast.error("Aggiungi almeno un prodotto"); setSaving(false); return; }
        const res = await fetch("/api/workspace/inventario/batch", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ data_inventario: dataInventario, voci }),
        });
        if (!res.ok) throw new Error();
        toast.success(voci.length === 1 ? "Voce aggiunta" : `${voci.length} voci aggiunte`);
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

  const formCompilato = nome.trim().length > 0;
  const totaleSalva = bozze.length + (formCompilato ? 1 : 0);

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="w-full sm:max-w-lg gap-5">
        <DialogTitle>{isEdit ? "Modifica voce" : "Aggiungi prodotti"}</DialogTitle>

        {/* Lista prodotti già accodati (solo in aggiunta) */}
        {!isEdit && bozze.length > 0 && (
          <div className="rounded-md border border-border divide-y divide-border max-h-40 overflow-y-auto">
            {bozze.map((b, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <span className="font-medium truncate block">{b.nome}</span>
                  <span className="text-xs text-muted-foreground">
                    {b.quantita} {b.um} × {b.prezzo_unitario > 0 ? fmtEuro(b.prezzo_unitario) : "—"}
                    {" = "}
                    <span className="text-foreground">{fmtEuro(b.quantita * b.prezzo_unitario)}</span>
                  </span>
                </div>
                <Button
                  size="icon"
                  variant="ghost"
                  className="size-7 text-muted-foreground hover:text-destructive shrink-0"
                  onClick={() => rimuoviBozza(i)}
                  title="Rimuovi"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        )}

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
              onChange={e => onPrezzoChange(e.target.value)}
              placeholder="0.00"
              className="focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
        </div>

        {/* Valore live */}
        {valoreCalcolato !== null && (
          <p className="text-sm text-muted-foreground -mt-1">
            Valore:{" "}
            <span className="font-semibold text-foreground">{fmtEuro(valoreCalcolato)}</span>
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

        <div className="flex items-center justify-between gap-2 pt-1">
          {!isEdit ? (
            <Button variant="outline" onClick={aggiungiAllaLista} disabled={saving || !formCompilato}>
              <Plus className="size-4 mr-1.5" />Aggiungi un altro
            </Button>
          ) : <span />}
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
            <Button onClick={salva} disabled={saving || (!isEdit && totaleSalva === 0)}>
              {saving
                ? "Salvataggio…"
                : isEdit
                  ? "Aggiorna"
                  : totaleSalva > 1
                    ? `Salva ${totaleSalva} prodotti`
                    : "Salva"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
