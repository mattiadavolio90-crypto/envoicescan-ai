"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { Moon, Sun } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const PIANO_LABEL: Record<string, string> = {
  base: "Base",
  plus: "Plus",
  pro: "Pro",
};

const PIANO_PREZZO: Record<string, string> = {
  base: "€39/mese",
  plus: "€49/mese",
  pro: "€69/mese",
};

type AccountData = {
  email: string;
  nome_ristorante: string;
  ragione_sociale: string | null;
  partita_iva: string | null;
  piano: string;
  limite_fatture_mese: number;
  fatture_usate_mese: number;
  chat_usate_oggi?: number;
  chat_limite_giorno?: number;
  price_alert_threshold: number | null;
  tema?: "dark" | "light";
  membro_dal: string | null;
  ultimo_accesso: string | null;
  is_admin: boolean;
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

function UsageBar({
  label,
  usate,
  limite,
  avviso,
}: {
  label: string;
  usate: number;
  limite: number;
  avviso: string;
}) {
  const pct = limite > 0 ? Math.min(100, Math.round((usate / limite) * 100)) : 0;
  const color =
    pct >= 90 ? "bg-red-500" : pct >= 70 ? "bg-amber-500" : "bg-primary";
  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">
          {usate} / {limite}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {pct >= 90 && (
        <p className="text-xs text-red-600 dark:text-red-400">{avviso}</p>
      )}
    </div>
  );
}

function CambioPasswordForm() {
  const [attuale, setAttuale] = useState("");
  const [nuova, setNuova] = useState("");
  const [conferma, setConferma] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(false);
    if (nuova !== conferma) {
      setError("Le nuove password non coincidono");
      return;
    }
    if (nuova.length < 8) {
      setError("La nuova password deve essere di almeno 8 caratteri");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/account/cambia-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password_attuale: attuale, nuova_password: nuova }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || data.error || "Errore nel cambio password");
        return;
      }
      setSuccess(true);
      setAttuale("");
      setNuova("");
      setConferma("");
    } catch {
      setError("Errore di connessione. Riprova.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Cambio password</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
          <div className="space-y-1.5">
            <Label htmlFor="pwd-attuale">Password attuale</Label>
            <Input
              id="pwd-attuale"
              type="password"
              autoComplete="current-password"
              required
              value={attuale}
              onChange={(e) => setAttuale(e.target.value)}
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pwd-nuova">Nuova password</Label>
            <Input
              id="pwd-nuova"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={nuova}
              onChange={(e) => setNuova(e.target.value)}
              placeholder="Almeno 8 caratteri"
              disabled={loading}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="pwd-conferma">Conferma nuova password</Label>
            <Input
              id="pwd-conferma"
              type="password"
              autoComplete="new-password"
              required
              value={conferma}
              onChange={(e) => setConferma(e.target.value)}
              disabled={loading}
            />
          </div>
          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          {success && (
            <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400">
              Password aggiornata con successo.
            </div>
          )}
          <Button
            type="submit"
            disabled={loading || !attuale || !nuova || !conferma}
          >
            {loading ? "Salvataggio..." : "Aggiorna password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function AspettoCard({ temaSalvato }: { temaSalvato: "dark" | "light" }) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => setMounted(true), []);

  // Prima del mount usiamo il valore dal DB per evitare un flash dell'opzione
  // attiva sbagliata (next-themes legge il tema solo lato client).
  const attivo = mounted ? theme : temaSalvato;

  async function scegli(nuovo: "dark" | "light") {
    if (nuovo === attivo || saving) return;
    // Il tema si applica subito e resta: next-themes lo persiste in
    // localStorage sul dispositivo. Il salvataggio sul DB e' "best effort"
    // (serve solo a far seguire la preferenza su altri dispositivi): se fallisce
    // NON ripristiniamo il tema, altrimenti la scelta dell'utente lampeggerebbe
    // e tornerebbe indietro.
    setTheme(nuovo);
    setSaving(true);
    try {
      const res = await fetch("/api/account/preferenze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tema: nuovo }),
      });
      if (!res.ok) throw new Error();
      toast.success("Tema aggiornato");
    } catch {
      toast.error("Tema applicato su questo dispositivo, ma non salvato sull'account. Riprova piu' tardi.");
    } finally {
      setSaving(false);
    }
  }

  const opzioni = [
    { val: "light" as const, label: "Chiaro", icon: Sun },
    { val: "dark" as const, label: "Scuro", icon: Moon },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Aspetto</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-1.5">
          <Label>Tema dell&apos;interfaccia</Label>
          <div className="grid grid-cols-2 gap-3 max-w-sm">
            {opzioni.map((o) => {
              const selezionato = attivo === o.val;
              return (
                <button
                  key={o.val}
                  type="button"
                  onClick={() => scegli(o.val)}
                  disabled={saving}
                  aria-pressed={selezionato}
                  className={cn(
                    "flex items-center justify-center gap-2 rounded-lg border px-4 py-3 text-sm font-medium transition-colors disabled:opacity-60",
                    selezionato
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-border hover:bg-accent"
                  )}
                >
                  <o.icon className="size-4" />
                  {o.label}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-muted-foreground">
            La preferenza viene salvata sul tuo account e applicata su ogni dispositivo.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export function AccountClient({ data }: { data: AccountData }) {
  const pianoLabel = PIANO_LABEL[data.piano] ?? data.piano;
  const pianoPrezzo = PIANO_PREZZO[data.piano] ?? "";

  return (
    <div className="space-y-6">
      {/* Ristorante */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Il tuo ristorante</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <dt className="text-muted-foreground">Nome ristorante</dt>
              <dd className="font-medium mt-0.5">{data.nome_ristorante || "—"}</dd>
            </div>
            {data.ragione_sociale && (
              <div>
                <dt className="text-muted-foreground">Ragione sociale</dt>
                <dd className="font-medium mt-0.5">{data.ragione_sociale}</dd>
              </div>
            )}
            <div>
              <dt className="text-muted-foreground">P.IVA</dt>
              <dd className="font-medium mt-0.5">{data.partita_iva || "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Email</dt>
              <dd className="font-medium mt-0.5">{data.email}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Membro dal</dt>
              <dd className="font-medium mt-0.5">{fmtDate(data.membro_dal)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Ultimo accesso</dt>
              <dd className="font-medium mt-0.5">{fmtDate(data.ultimo_accesso)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {/* Piano e contatori */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Piano abbonamento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-primary/10 text-primary text-sm font-semibold px-3 py-1">
              {pianoLabel}
            </span>
            {pianoPrezzo && (
              <span className="text-sm text-muted-foreground">{pianoPrezzo}</span>
            )}
          </div>
          <UsageBar
            label="Fatture questo mese"
            usate={data.fatture_usate_mese}
            limite={data.limite_fatture_mese}
            avviso="Hai quasi esaurito il tuo limite mensile."
          />
          <p className="text-xs text-muted-foreground">
            Il contatore si azzera il 1° di ogni mese.
          </p>

          {data.chat_limite_giorno != null && (
            <div className="border-t pt-4">
              {data.chat_limite_giorno > 0 ? (
                <>
                  <UsageBar
                    label="Domande all'assistente AI (oggi)"
                    usate={data.chat_usate_oggi ?? 0}
                    limite={data.chat_limite_giorno}
                    avviso="Hai quasi esaurito le domande di oggi."
                  />
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    Il contatore si azzera ogni giorno a mezzanotte.
                  </p>
                </>
              ) : (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">Assistente AI</span>
                  <span className="text-muted-foreground">
                    Non incluso nel piano —{" "}
                    <span className="font-medium text-foreground">passa a un piano superiore</span>
                  </span>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Aspetto (tema chiaro/scuro) */}
      <AspettoCard temaSalvato={data.tema ?? "dark"} />

      {/* Cambio password */}
      <CambioPasswordForm />
    </div>
  );
}
