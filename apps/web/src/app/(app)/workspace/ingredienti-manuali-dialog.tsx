"use client";

import { useState, useEffect } from "react";
import { Plus, Pencil, Trash2 } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onClose: () => void;
  onSaved: () => void;
}

const UM_LIST = ["KG", "LT", "PZ", "G", "ML"] as const;

// Tipo che corrisponde alla risposta dell'endpoint /ingredienti-manuali (campo DB prezzo_per_um)
interface IngredienteDB {
  id: string;
  nome: string;
  prezzo_per_um: number;
  um: string;
}

export function IngredientiManualiDialog({ open, onClose, onSaved }: Props) {
  const [lista, setLista] = useState<IngredienteDB[]>([]);
  const [loading, setLoading] = useState(false);

  // form nuovo
  const [nome, setNome] = useState("");
  const [prezzo, setPrezzo] = useState("");
  const [um, setUm] = useState<string>("KG");
  const [saving, setSaving] = useState(false);

  // modifica inline
  const [editId, setEditId] = useState<string | null>(null);
  const [editNome, setEditNome] = useState("");
  const [editPrezzo, setEditPrezzo] = useState("");
  const [editUm, setEditUm] = useState("KG");

  async function load() {
    setLoading(true);
    try {
      const res = await fetch("/api/workspace/foodcost/ingredienti-manuali");
      const data = await res.json();
      setLista(data.ingredienti ?? []);
    } catch {
      toast.error("Errore caricamento ingredienti");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { if (open) load(); }, [open]);

  async function handleCrea() {
    if (!nome.trim() || !prezzo) return;
    setSaving(true);
    try {
      const res = await fetch("/api/workspace/foodcost/ingredienti-manuali", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome: nome.trim(), prezzo_per_um: parseFloat(prezzo), um }),
      });
      if (!res.ok) {
        const d = await res.json();
        if (res.status === 409) toast.error("Ingrediente già esistente");
        else toast.error(d.error ?? "Errore salvataggio");
        return;
      }
      toast.success("Ingrediente creato");
      setNome(""); setPrezzo(""); setUm("KG");
      await load();
      onSaved();
    } catch {
      toast.error("Errore di rete");
    } finally {
      setSaving(false);
    }
  }

  async function handleAggiorna(id: string) {
    setSaving(true);
    try {
      await fetch(`/api/workspace/foodcost/ingredienti-manuali/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome: editNome.trim(), prezzo_per_um: parseFloat(editPrezzo), um: editUm }),
      });
      toast.success("Salvato");
      setEditId(null);
      await load();
      onSaved();
    } catch {
      toast.error("Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  async function handleElimina(id: string, nome: string) {
    if (!confirm(`Eliminare "${nome}"?`)) return;
    await fetch(`/api/workspace/foodcost/ingredienti-manuali/${id}`, { method: "DELETE" });
    toast.success("Eliminato");
    await load();
    onSaved();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Ingredienti manuali</DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground -mt-2">
          Ingredienti con prezzo stimato, non collegati alle fatture. Usali per testare ricette o per prodotti che non compaiono nelle fatture.
        </p>

        {/* Form nuovo */}
        <div className="space-y-2">
          <div>
            <Label className="text-xs">Nome ingrediente</Label>
            <Input
              placeholder="es. Mozzarella fior di latte, Farina 00, Olio EVO…"
              value={nome}
              onChange={e => setNome(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && nome.trim() && prezzo) handleCrea(); }}
            />
          </div>
          <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
            <div>
              <Label className="text-xs">Prezzo €/unità di misura</Label>
              <Input
                type="number"
                placeholder="0.00"
                min="0"
                step="0.01"
                value={prezzo}
                onChange={e => setPrezzo(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && nome.trim() && prezzo) handleCrea(); }}
              />
            </div>
            <div>
              <Label className="text-xs">UM</Label>
              <select
                value={um}
                onChange={e => setUm(e.target.value)}
                className="flex h-9 w-24 items-center rounded-md border border-input bg-background px-3 text-sm"
              >
                {UM_LIST.map(u => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <Button onClick={handleCrea} disabled={saving || !nome.trim() || !prezzo}>
              <Plus className="size-4 mr-1.5" />Aggiungi
            </Button>
          </div>
        </div>

        {/* Lista */}
        <div className="mt-2 max-h-72 overflow-y-auto divide-y divide-border rounded-md border border-border">
          {loading && (
            <p className="p-4 text-sm text-muted-foreground">Caricamento…</p>
          )}
          {!loading && lista.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">Nessun ingrediente manuale.</p>
          )}
          {lista.map(ing => (
            <div key={ing.id} className="flex items-center gap-2 px-3 py-2">
              {editId === ing.id ? (
                <>
                  <Input value={editNome} onChange={e => setEditNome(e.target.value)} className="flex-1 h-8 text-sm" />
                  <Input type="number" value={editPrezzo} onChange={e => setEditPrezzo(e.target.value)} className="w-20 h-8 text-sm" />
                  <select value={editUm} onChange={e => setEditUm(e.target.value)}
                    className="h-8 w-16 rounded-md border border-input bg-background px-2 text-sm">
                    {UM_LIST.map(u => <option key={u} value={u}>{u}</option>)}
                  </select>
                  <Button size="sm" variant="default" onClick={() => handleAggiorna(ing.id)} disabled={saving} className="h-8 px-2">Salva</Button>
                  <Button size="sm" variant="ghost" onClick={() => setEditId(null)} className="h-8 px-2">✕</Button>
                </>
              ) : (
                <>
                  <span className="flex-1 text-sm font-medium">{ing.nome}</span>
                  <span className="text-sm text-muted-foreground w-20 text-right">€{Number(ing.prezzo_per_um).toFixed(2)}</span>
                  <span className="text-xs text-muted-foreground w-8">/{ing.um}</span>
                  <Button size="icon" variant="ghost" className="size-7"
                    onClick={() => { setEditId(ing.id); setEditNome(ing.nome); setEditPrezzo(String(ing.prezzo_per_um)); setEditUm(ing.um); }}>
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="size-7 text-destructive hover:text-destructive"
                    onClick={() => handleElimina(ing.id, ing.nome)}>
                    <Trash2 className="size-3.5" />
                  </Button>
                </>
              )}
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Chiudi</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
