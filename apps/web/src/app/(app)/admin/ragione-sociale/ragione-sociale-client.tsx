"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Plus, Trash2 } from "lucide-react";

type Mapping = { id: string; ragione_sociale: string; ristorante_id: string; created_at: string };
type Sede = { id: string; label: string };
type Props = { mappingsIniziali: Mapping[]; sedi: Sede[] };

export function RagioneSocialeClient({ mappingsIniziali, sedi }: Props) {
  const [mappings, setMappings] = useState<Mapping[]>(mappingsIniziali);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [ragione, setRagione] = useState("");
  const [sedeId, setSedeId] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCrea() {
    if (!ragione.trim() || !sedeId) { toast.error(sedi.length === 0 ? "Nessun ristorante disponibile — worker non raggiungibile" : "Compila tutti i campi"); return; }
    setSaving(true);
    try {
      const res = await fetch("/api/admin/ragione-sociale-map", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ragione_sociale: ragione.trim(), ristorante_id: sedeId }),
      });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Errore"); return; }
      setMappings((prev) => [...prev, data]);
      toast.success("Mapping creato");
      setDialogOpen(false);
      setRagione(""); setSedeId("");
    } catch { toast.error("Errore di connessione"); }
    finally { setSaving(false); }
  }

  async function handleElimina(id: string) {
    if (!confirm("Eliminare questo mapping?")) return;
    try {
      await fetch(`/api/admin/ragione-sociale-map/${id}`, { method: "DELETE" });
      setMappings((prev) => prev.filter((m) => m.id !== id));
      toast.success("Mapping eliminato");
    } catch { toast.error("Errore"); }
  }

  const sedeLabel = (id: string) => sedi.find((s) => s.id === id)?.label ?? id;

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="size-4 mr-1" /> Nuovo mapping
        </Button>
      </div>

      {mappings.length === 0 ? (
        <div className="rounded-lg border p-8 text-center text-sm text-muted-foreground">
          Nessun mapping configurato. Aggiungine uno per collegare ragioni sociali ai ristoranti.
        </div>
      ) : (
        <div className="rounded-lg border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left">
                <th className="px-4 py-3 font-medium">Ragione sociale (email gestionale)</th>
                <th className="px-4 py-3 font-medium">→ Ristorante ONEFLUX</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {mappings.map((m) => (
                <tr key={m.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium">{m.ragione_sociale}</td>
                  <td className="px-4 py-3 text-muted-foreground">{sedeLabel(m.ristorante_id)}</td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={() => handleElimina(m.id)}>
                      <Trash2 className="size-4" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Nuovo mapping</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label>Ragione sociale (come appare nell&apos;email gestionale)</Label>
              <Input placeholder="Es: MARIO ROSSI SRL" value={ragione} onChange={(e) => setRagione(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Ristorante ONEFLUX</Label>
              {sedi.length === 0 ? (
                <p className="text-xs text-destructive">Nessun ristorante caricato — worker non raggiungibile</p>
              ) : (
                <NativeSelect value={sedeId} onValueChange={setSedeId} placeholder="Seleziona ristorante…">
                  {sedi.map((s) => (
                    <option key={s.id} value={s.id}>{s.label}</option>
                  ))}
                </NativeSelect>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={saving}>Annulla</Button>
            <Button onClick={handleCrea} disabled={saving || !ragione.trim() || !sedeId}>
              {saving ? "Salvataggio…" : "Crea mapping"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
