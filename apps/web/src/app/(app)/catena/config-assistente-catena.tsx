"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, Loader2, MapPin } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

type SegnaleCfg = { key: string; label: string; descrizione: string; enabled: boolean };
type PvCfg = { ristorante_id: string; nome: string; incluso: boolean };

// "Configura assistente catena": come il box Configura della Home PV, ma per il
// GRUPPO — quali segnali "Da vedere" attivi e su quali punti vendita. Separato
// dalle preferenze del singolo PV. Salvando, il worker ricalcola i segnali.
export function ConfigAssistenteCatena() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [nome, setNome] = useState("");
  const [segnali, setSegnali] = useState<SegnaleCfg[]>([]);
  const [pv, setPv] = useState<PvCfg[]>([]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetch("/api/gruppo/assistant-config", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        setNome(j.nome_gruppo ?? "");
        setSegnali(j.segnali ?? []);
        setPv(j.pv ?? []);
      })
      .catch(() => toast.error("Errore nel caricamento della configurazione"))
      .finally(() => setLoading(false));
  }, [open]);

  function toggleSegnale(key: string, v: boolean) {
    setSegnali((prev) => prev.map((s) => (s.key === key ? { ...s, enabled: v } : s)));
  }
  function togglePv(id: string, v: boolean) {
    setPv((prev) => prev.map((p) => (p.ristorante_id === id ? { ...p, incluso: v } : p)));
  }

  async function salva() {
    setSaving(true);
    try {
      const res = await fetch("/api/gruppo/assistant-config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome_gruppo: nome.trim() || null,
          segnali_disattivati: segnali.filter((s) => !s.enabled).map((s) => s.key),
          pv_esclusi: pv.filter((p) => !p.incluso).map((p) => p.ristorante_id),
        }),
      });
      if (!res.ok) throw new Error();
      setOpen(false);
      router.refresh();
      toast.success("Configurazione salvata");
    } catch {
      toast.error("Non sono riuscito a salvare. Riprova.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" className="gap-1.5" />}>
        <Sparkles className="size-4" />
        Configura assistente
      </DialogTrigger>
      <DialogContent className="flex max-h-[90dvh] flex-col sm:max-w-md">
        <DialogHeader className="shrink-0">
          <DialogTitle>Configura l&apos;assistente di catena</DialogTitle>
          <DialogDescription>
            Scegli quali avvisi ricevere nella catena e su quali punti vendita.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Caricamento…</p>
          ) : (
            <div className="space-y-5 py-2">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Nome del gruppo</label>
                <Input
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  placeholder="Es. SUSHILAND"
                  maxLength={60}
                />
                <p className="text-xs text-muted-foreground">
                  Usato per il saluto («Buongiorno, {nome.trim() || "…"}») e in testata alla catena.
                </p>
              </div>

              <div className="space-y-1">
                <p className="text-sm font-medium">Avvisi «Da vedere»</p>
                <div className="divide-y rounded-lg border">
                  {segnali.map((s) => (
                    <div key={s.key} className="px-3 py-2.5">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-sm">{s.label}</span>
                        <Switch checked={s.enabled} onCheckedChange={(v: boolean) => toggleSegnale(s.key, v)} />
                      </div>
                      <p className="mt-0.5 pr-10 text-xs text-muted-foreground">{s.descrizione}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="space-y-1">
                <p className="text-sm font-medium">Punti vendita monitorati</p>
                <div className="divide-y rounded-lg border">
                  {pv.map((p) => (
                    <div
                      key={p.ristorante_id}
                      className="flex items-center justify-between gap-3 px-3 py-2.5"
                    >
                      <span className="flex items-center gap-2 text-sm">
                        <MapPin className="size-3.5 text-muted-foreground" />
                        {p.nome}
                      </span>
                      <Switch checked={p.incluso} onCheckedChange={(v: boolean) => togglePv(p.ristorante_id, v)} />
                    </div>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  I punti vendita spenti non generano avvisi e non entrano nei confronti dei prezzi.
                </p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0">
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={saving}>
            Annulla
          </Button>
          <Button onClick={salva} disabled={saving || loading}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Salva
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
