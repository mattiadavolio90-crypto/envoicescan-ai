"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, Lock, Loader2, MessageCircle } from "lucide-react";
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
import { type AssistantConfig, type ConfigTopic } from "@/lib/home";

export function ConfigAssistente({ config }: { config: AssistantConfig }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [nome, setNome] = useState(config.nome_referente);
  const [topics, setTopics] = useState<ConfigTopic[]>(config.topics);
  const [chatEnabled, setChatEnabled] = useState(config.chat_ai_enabled);
  const [saving, setSaving] = useState(false);

  function toggle(key: string, enabled: boolean) {
    setTopics((prev) =>
      prev.map((t) => (t.key === key && !t.bloccato ? { ...t, enabled } : t)),
    );
  }

  async function salva() {
    setSaving(true);
    const topics_disabled = topics.filter((t) => !t.enabled && !t.bloccato).map((t) => t.key);
    try {
      const res = await fetch("/api/home/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome_referente: nome.trim() || null,
          topics_disabled,
          chat_ai_enabled: chatEnabled,
        }),
      });
      if (!res.ok) throw new Error();
      setOpen(false);
      // router.refresh() rigenera i Server Component della Home (saluto/avvisi
      // aggiornati) senza il reload completo della pagina, che era lento e
      // perdeva lo stato della SPA.
      router.refresh();
    } catch {
      toast.error("Non sono riuscito a salvare le impostazioni. Riprova.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            size="sm"
            className="gap-1.5 bg-sky-500 text-white shadow-sm hover:bg-sky-600 dark:bg-sky-500 dark:hover:bg-sky-400"
          />
        }
      >
        <Sparkles className="size-4" />
        Configura assistente
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Configura il tuo assistente</DialogTitle>
          <DialogDescription>
            Scegli come ti saluta e quali avvisi vuoi ricevere in Home.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          <div className="flex items-center justify-between gap-3 rounded-lg border bg-card px-3 py-2.5">
            <div className="flex items-center gap-2 text-sm">
              <MessageCircle className="size-4 text-primary" />
              <div>
                <p className="font-medium">Chat AI in Home</p>
                <p className="text-xs text-muted-foreground">
                  Il pulsante per chiedere all&apos;assistente dei tuoi dati
                </p>
              </div>
            </div>
            <Switch checked={chatEnabled} onCheckedChange={(v: boolean) => setChatEnabled(v)} />
          </div>

          <div className="space-y-1.5">
            <label className="text-sm font-medium">Il tuo nome</label>
            <Input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Es. Mattia"
              maxLength={40}
            />
            <p className="text-xs text-muted-foreground">
              Usato per il saluto: &quot;Buongiorno {nome.trim() || "…"}&quot;
            </p>
          </div>

          <div className="space-y-1">
            <p className="text-sm font-medium">Avvisi attivi</p>
            <div className="divide-y rounded-lg border">
              {topics.map((t) => (
                <div key={t.key} className="flex items-center justify-between gap-3 px-3 py-2.5">
                  <div className="flex items-center gap-2 text-sm">
                    {t.label}
                    {t.bloccato && (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Lock className="size-3" />
                        sempre attivo
                      </span>
                    )}
                  </div>
                  <Switch
                    checked={t.enabled}
                    disabled={t.bloccato}
                    onCheckedChange={(v: boolean) => toggle(t.key, v)}
                  />
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Gli avvisi sui caricamenti falliti restano sempre attivi: sono problemi tecnici
              da non perdere.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)} disabled={saving}>
            Annulla
          </Button>
          <Button onClick={salva} disabled={saving}>
            {saving && <Loader2 className="size-4 animate-spin" />}
            Salva
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
