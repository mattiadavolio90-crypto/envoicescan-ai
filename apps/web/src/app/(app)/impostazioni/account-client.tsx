"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Moon, Sun, AlertTriangle, Building2, MapPin, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const PIANO_LABEL: Record<string, string> = {
  base: "Base",
  plus: "Plus",
  pro: "Pro",
};

const PIANO_PREZZO: Record<string, string> = {
  base: "€39/mese + IVA",
  plus: "€59/mese + IVA",
  pro: "€79/mese + IVA",
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
  chat_pool?: boolean;
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

// Solo admin: svuota tutti i dati del PROPRIO account (ambiente di test) per
// ripartire da zero. Backend gated da _verify_admin: opera solo sull'admin che
// chiama, mai su altri utenti. Doppia conferma: digitare "SVUOTA".
function ZonaPericolosa() {
  const router = useRouter();
  const [conferma, setConferma] = useState("");
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  async function handleSvuota() {
    setLoading(true);
    try {
      const res = await fetch("/api/account/svuota-dati", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conferma }),
      });
      const data = await res.json();
      if (!res.ok) {
        toast.error(data.detail || data.error || "Errore durante lo svuotamento");
        return;
      }
      toast.success("Dati svuotati. L'app è ripartita da zero.");
      setOpen(false);
      setConferma("");
      router.refresh();
    } catch {
      toast.error("Errore di connessione. Riprova.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2 text-destructive">
          <AlertTriangle className="size-4" />
          Zona pericolosa (admin)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground max-w-prose">
          Svuota <span className="font-medium text-foreground">tutti i dati del tuo account admin</span>{" "}
          (fatture, ricavi, margini, tag, scadenziario, notifiche…) per ripartire da
          zero nei test. L&apos;account resta attivo e la memoria AI globale non viene
          toccata. Non tocca i dati degli altri utenti.
        </p>
        <Button variant="destructive" onClick={() => setOpen(true)}>
          Svuota i miei dati
        </Button>
        <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setConferma(""); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Confermi lo svuotamento?</DialogTitle>
              <DialogDescription>
                Tutti i dati del tuo account admin verranno eliminati
                definitivamente. L&apos;operazione non è reversibile. Per procedere,
                scrivi <span className="font-semibold">SVUOTA</span> qui sotto.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor="conferma-svuota">Conferma</Label>
              <Input
                id="conferma-svuota"
                value={conferma}
                onChange={(e) => setConferma(e.target.value)}
                placeholder="SVUOTA"
                autoComplete="off"
                disabled={loading}
              />
            </div>
            <DialogFooter>
              <Button variant="outline" disabled={loading} onClick={() => setOpen(false)}>
                Annulla
              </Button>
              <Button
                variant="destructive"
                onClick={handleSvuota}
                disabled={loading || conferma.trim() !== "SVUOTA"}
              >
                {loading ? "Svuotamento..." : "Svuota definitivamente"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </CardContent>
    </Card>
  );
}

function PrivacyGdprCard() {
  const router = useRouter();
  const [downloading, setDownloading] = useState(false);
  const [open, setOpen] = useState(false);
  const [conferma, setConferma] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleEsporta() {
    setDownloading(true);
    try {
      const res = await fetch("/api/account/esporta-dati");
      if (!res.ok) {
        toast.error("Errore durante l'esportazione. Riprova.");
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `oneflux-dati-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Dati scaricati.");
    } catch {
      toast.error("Errore di connessione. Riprova.");
    } finally {
      setDownloading(false);
    }
  }

  async function handleElimina() {
    setLoading(true);
    try {
      const res = await fetch("/api/account/elimina", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conferma: "ELIMINA" }),
      });
      if (res.ok) {
        toast.success("Account eliminato.");
        router.replace("/login");
        return;
      }
      const data = await res.json().catch(() => ({}));
      toast.error(data?.detail || "Errore durante l'eliminazione.");
    } catch {
      toast.error("Errore di connessione. Riprova.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="border-destructive/40">
      <CardHeader>
        <CardTitle className="text-base">Privacy e dati</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Art. 20 — portabilità */}
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground max-w-prose">
            Scarica una copia di tutti i tuoi dati (profilo, fatture, ricette, margini,
            ricavi, diario…) in formato JSON strutturato.
          </p>
          <Button variant="outline" onClick={handleEsporta} disabled={downloading}>
            {downloading ? "Preparazione…" : "Scarica i miei dati"}
          </Button>
        </div>

        {/* Art. 17 — cancellazione */}
        <div className="space-y-2 border-t pt-4">
          <p className="text-sm text-muted-foreground max-w-prose">
            <span className="font-medium text-destructive">Elimina il tuo account</span> e
            tutti i dati collegati in modo <span className="font-medium text-foreground">permanente
            e irreversibile</span>. L&apos;operazione non può essere annullata.
          </p>
          <Button variant="destructive" onClick={() => setOpen(true)}>
            Elimina il mio account
          </Button>
          <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setConferma(""); }}>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Eliminare definitivamente l&apos;account?</DialogTitle>
                <DialogDescription>
                  Tutti i tuoi dati verranno eliminati in modo permanente e non
                  recuperabile. Per procedere, scrivi{" "}
                  <span className="font-semibold">ELIMINA</span> qui sotto.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-1.5">
                <Label htmlFor="conferma-elimina">Conferma</Label>
                <Input
                  id="conferma-elimina"
                  value={conferma}
                  onChange={(e) => setConferma(e.target.value)}
                  placeholder="ELIMINA"
                  autoComplete="off"
                  disabled={loading}
                />
              </div>
              <DialogFooter>
                <Button variant="outline" disabled={loading} onClick={() => setOpen(false)}>
                  Annulla
                </Button>
                <Button
                  variant="destructive"
                  onClick={handleElimina}
                  disabled={loading || conferma.trim().toUpperCase() !== "ELIMINA"}
                >
                  {loading ? "Eliminazione…" : "Elimina definitivamente"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
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

type Sede = {
  id: string;
  nome: string;
  indirizzo: string | null;
  comune: string | null;
  attiva: boolean;
};

// Vista GRUPPO (contesto catena): identità del gruppo + elenco sedi. I dati per
// sede (piano, fatture) restano nel punto vendita — qui si entra, non si modifica.
function GruppoCard({
  nomeGruppo,
  email,
  membroDal,
  numPv,
}: {
  nomeGruppo: string | null;
  email: string;
  membroDal: string | null;
  numPv: number;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="size-5 text-primary" />
          Il tuo gruppo
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-muted-foreground">Gruppo</dt>
            <dd className="mt-0.5 font-medium">{nomeGruppo || "—"}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Punti vendita</dt>
            <dd className="mt-0.5 font-medium">{numPv}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Email</dt>
            <dd className="mt-0.5 font-medium">{email}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Membro dal</dt>
            <dd className="mt-0.5 font-medium">{fmtDate(membroDal)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}

function SediGruppoCard({ sedi }: { sedi: Sede[] }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);

  async function apri(id: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: id }),
      });
      if (!res.ok) throw new Error();
      // Entrare in una sede = passare in modalità PV: la Home del PV imposta il
      // cookie di vista, così le sue Impostazioni mostrano i suoi dati (piano,
      // fatture), non più il gruppo.
      router.push("/dashboard");
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Punti vendita</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="mb-2 text-sm text-muted-foreground">
          Piano, fatture e dati di ogni sede si gestiscono dentro il punto vendita.
        </p>
        {sedi.map((s) => (
          <button
            key={s.id}
            type="button"
            disabled={switching}
            onClick={() => apri(s.id)}
            className="flex w-full items-center gap-3 rounded-xl border bg-background/40 px-4 py-3 text-left transition-colors hover:bg-accent disabled:opacity-50"
          >
            <MapPin className="size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium">{s.nome}</span>
              {(s.indirizzo || s.comune) && (
                <span className="block truncate text-xs text-muted-foreground">
                  {[s.indirizzo, s.comune].filter(Boolean).join(" · ")}
                </span>
              )}
            </span>
            <ArrowRight className="size-4 shrink-0 text-muted-foreground/50" />
          </button>
        ))}
      </CardContent>
    </Card>
  );
}

export function AccountClient({
  data,
  chain = false,
  nomeGruppo = null,
  sedi = [],
}: {
  data: AccountData;
  chain?: boolean;
  nomeGruppo?: string | null;
  sedi?: Sede[];
}) {
  const pianoLabel = PIANO_LABEL[data.piano] ?? data.piano;
  const pianoPrezzo = PIANO_PREZZO[data.piano] ?? "";

  // Contesto catena: identità del gruppo + elenco sedi al posto della scheda
  // "Il tuo ristorante" e del piano per-sede. Tema e password restano account-level.
  if (chain) {
    return (
      <div className="space-y-6">
        <GruppoCard nomeGruppo={nomeGruppo} email={data.email} membroDal={data.membro_dal} numPv={sedi.length} />
        <SediGruppoCard sedi={sedi} />
        <AspettoCard temaSalvato={data.tema ?? "dark"} />
        <CambioPasswordForm />
      </div>
    );
  }

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

      {/* Piano e contatori — solo per i clienti. Un admin non ha un piano
          abbonamento ne' limiti fatture/chat: per lui questa card non ha senso. */}
      {!data.is_admin && (
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
                    label={data.chat_pool ? "Domande all'assistente AI del gruppo (oggi)" : "Domande all'assistente AI (oggi)"}
                    usate={data.chat_usate_oggi ?? 0}
                    limite={data.chat_limite_giorno}
                    avviso="Hai quasi esaurito le domande di oggi."
                  />
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {data.chat_pool
                      ? "Pool condiviso tra tutti i punti vendita e la modalità catena. Si azzera ogni giorno a mezzanotte."
                      : "Il contatore si azzera ogni giorno a mezzanotte."}
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
      )}

      {/* Aspetto (tema chiaro/scuro) */}
      <AspettoCard temaSalvato={data.tema ?? "dark"} />

      {/* Cambio password */}
      <CambioPasswordForm />

      {/* Privacy e dati (GDPR) — solo clienti: export Art.20 + elimina account Art.17 */}
      {!data.is_admin && <PrivacyGdprCard />}

      {/* Zona pericolosa — solo admin: svuota i dati del proprio ambiente di test */}
      {data.is_admin && <ZonaPericolosa />}
    </div>
  );
}
