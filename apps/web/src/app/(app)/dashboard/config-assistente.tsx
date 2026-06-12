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
  // Soglia alert prezzi: qui e' l'unico posto dove si IMPOSTA (in pagina Prezzi e'
  // solo un filtro di visualizzazione). Stringa per gestire input parziali ("5,").
  const [soglia, setSoglia] = useState(String(config.price_alert_threshold ?? 5));
  const [soloPreferiti, setSoloPreferiti] = useState(config.alert_prezzi_solo_preferiti ?? false);
  const [saving, setSaving] = useState(false);

  // L'avviso "Alert prezzi" governa la soglia: se è spento, il campo soglia non
  // serve (non scatterebbe comunque). Lo nascondiamo per non confondere.
  const alertPrezziAttivo = topics.find((t) => t.key === "price_alert")?.enabled ?? true;

  function toggle(key: string, enabled: boolean) {
    setTopics((prev) =>
      prev.map((t) => (t.key === key && !t.bloccato ? { ...t, enabled } : t)),
    );
  }

  async function salva() {
    setSaving(true);
    const topics_disabled = topics.filter((t) => !t.enabled && !t.bloccato).map((t) => t.key);
    // Clamp [0,50] come il backend; valore non numerico -> default 5.
    const sogliaNum = Math.min(50, Math.max(0, parseFloat(soglia.replace(",", ".")) || 5));
    try {
      const res = await fetch("/api/home/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome_referente: nome.trim() || null,
          topics_disabled,
          chat_ai_enabled: chatEnabled,
          price_alert_threshold: sogliaNum,
          alert_prezzi_solo_preferiti: soloPreferiti,
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
      <DialogContent className="flex max-h-[90dvh] flex-col sm:max-w-md">
        <DialogHeader className="shrink-0">
          <DialogTitle>Configura il tuo assistente</DialogTitle>
          <DialogDescription>
            Scegli come ti saluta e quali avvisi vuoi ricevere in Home.
          </DialogDescription>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-y-auto">
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
                <div key={t.key} className="px-3 py-2.5">
                  <div className="flex items-center justify-between gap-3">
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
                  {t.descrizione && (
                    <p className="mt-0.5 pr-10 text-xs text-muted-foreground">{t.descrizione}</p>
                  )}
                  {/* Soglia alert prezzi: appare sotto "Alert prezzi" quando è attivo.
                      È l'unico punto dove si imposta la sensibilità dell'avviso. */}
                  {t.key === "price_alert" && alertPrezziAttivo && (
                    <div className="mt-2 space-y-2">
                      <div className="flex items-center gap-2">
                        <label className="text-xs text-muted-foreground">Mi interessa da un rincaro del</label>
                        <Input
                          type="number"
                          min="0"
                          max="50"
                          step="0.5"
                          value={soglia}
                          onChange={(e) => setSoglia(e.target.value)}
                          className="h-7 w-16 text-right text-sm"
                        />
                        <span className="text-xs text-muted-foreground">% in su</span>
                      </div>
                      <div className="flex items-start justify-between gap-3 rounded-md border bg-muted/30 px-2.5 py-2">
                        <div className="text-xs">
                          <p className="font-medium">Solo sui prodotti preferiti</p>
                          <p className="text-muted-foreground">
                            Avvisami solo sui prodotti con la ⭐ in pagina Prezzi (e sui tuoi tag). Se non hai preferiti, ricevi solo gli avvisi sui tag.
                          </p>
                        </div>
                        <Switch checked={soloPreferiti} onCheckedChange={(v: boolean) => setSoloPreferiti(v)} />
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Gli avvisi sui caricamenti falliti restano sempre attivi: sono problemi tecnici
              da non perdere.
            </p>
          </div>
        </div>
        </div>

        <DialogFooter className="shrink-0">
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
