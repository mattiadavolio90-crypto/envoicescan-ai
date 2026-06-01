"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Bell,
  X,
  AlertTriangle,
  Info,
  CheckCircle,
  XCircle,
  Loader2,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { type Notifica } from "@/lib/notifiche";
import { ctaDi, pulisci, raggruppa } from "../notifiche/notifiche-shared";

function SeverityIcon({ severity }: { severity: Notifica["severity"] }) {
  if (severity === "warning") return <AlertTriangle className="size-5 text-amber-500 shrink-0" />;
  if (severity === "error") return <XCircle className="size-5 text-destructive shrink-0" />;
  if (severity === "success") return <CheckCircle className="size-5 text-emerald-500 shrink-0" />;
  return <Info className="size-5 text-sky-500 shrink-0" />;
}

// Bordo sinistro colorato = priorita' a colpo d'occhio (allineato alla pagina).
const SEVERITY_ACCENT: Record<Notifica["severity"], string> = {
  error: "border-l-destructive",
  warning: "border-l-amber-500",
  info: "border-l-sky-500",
  success: "border-l-emerald-500",
};

type Props = { count: number };

export function NotificheWidget({ count }: Props) {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [notifiche, setNotifiche] = useState<Notifica[]>([]);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [dismissing, setDismissing] = useState<Set<string>>(new Set());

  async function carica() {
    setLoadingList(true);
    try {
      const res = await fetch("/api/notifiche", { cache: "no-store" });
      if (res.ok) {
        const data = (await res.json()) as { notifiche?: Notifica[] };
        setNotifiche(data.notifiche ?? []);
      }
    } finally {
      setLoaded(true);
      setLoadingList(false);
    }
  }

  function onOpenChange(v: boolean) {
    setOpen(v);
    if (v && !loaded) carica();
  }

  async function archivia(id: string) {
    setDismissing((prev) => new Set(prev).add(id));
    try {
      await fetch("/api/notifiche/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
    } finally {
      setDismissed((prev) => new Set(prev).add(id));
      setDismissing((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  const visibili = notifiche.filter((n) => !dismissed.has(n.id));
  const gruppi = raggruppa(visibili);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger
        render={
          <Button
            size="sm"
            variant="outline"
            className="w-fit gap-1.5 border-amber-500/40 text-amber-600 hover:border-amber-500/60 hover:bg-amber-50 hover:text-amber-700 dark:text-amber-500 dark:hover:bg-amber-950/30"
          />
        }
      >
        <Bell className="size-3.5" />
        Vedi tutte le notifiche
        {count > 0 && (
          <span className="ml-0.5 flex min-w-4 items-center justify-center rounded-full bg-amber-500/20 px-1 text-[11px] font-bold text-amber-700 dark:text-amber-400">
            {count}
          </span>
        )}
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Notifiche</DialogTitle>
          <DialogDescription>
            Tutti gli avvisi del tuo assistente. Archivia quelli che hai gestito.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-3 overflow-y-auto py-1">
          {loadingList && !loaded ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Carico le notifiche…
            </div>
          ) : visibili.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
              <Bell className="size-10 opacity-30" />
              <p className="text-sm">Nessuna notifica attiva</p>
            </div>
          ) : (
            gruppi.map((g) => (
              <div key={g.key} className="space-y-2.5">
                <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {g.label}
                  <span className="ml-1.5 text-muted-foreground/60">{g.notifiche.length}</span>
                </p>
                {g.notifiche.map((n) => {
                  const cta = ctaDi(n);
                  return (
                    <div
                      key={n.id}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border border-l-4 bg-card p-3.5",
                        SEVERITY_ACCENT[n.severity],
                      )}
                    >
                      <SeverityIcon severity={n.severity} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{pulisci(n.title)}</p>
                        {n.body && (
                          <p className="mt-0.5 whitespace-pre-line text-sm text-muted-foreground">
                            {pulisci(n.body)}
                          </p>
                        )}
                        <div className="mt-2 flex items-center gap-3">
                          {cta && (
                            <Link
                              href={cta.href}
                              onClick={() => setOpen(false)}
                              className={cn(buttonVariants({ size: "sm", variant: "outline" }), "h-7 text-xs")}
                            >
                              {cta.label}
                            </Link>
                          )}
                          {n.created_at && (
                            <span className="text-xs text-muted-foreground">
                              {new Date(n.created_at).toLocaleDateString("it-IT", {
                                day: "2-digit",
                                month: "short",
                              })}
                            </span>
                          )}
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-7 shrink-0 text-muted-foreground"
                        disabled={dismissing.has(n.id)}
                        onClick={() => archivia(n.id)}
                        title="Archivia"
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
