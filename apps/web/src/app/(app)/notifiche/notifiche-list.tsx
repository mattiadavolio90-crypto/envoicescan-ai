"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { X, AlertTriangle, Info, CheckCircle, XCircle, Bell } from "lucide-react";
import { type Notifica } from "@/lib/notifiche";
import { buttonVariants } from "@/components/ui/button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ctaDi, pulisci, raggruppa } from "./notifiche-shared";

function SeverityIcon({ severity }: { severity: Notifica["severity"] }) {
  if (severity === "warning") return <AlertTriangle className="size-5 text-amber-500 shrink-0" />;
  if (severity === "error") return <XCircle className="size-5 text-destructive shrink-0" />;
  if (severity === "success") return <CheckCircle className="size-5 text-emerald-500 shrink-0" />;
  return <Info className="size-5 text-sky-500 shrink-0" />;
}

// Bordo sinistro colorato = priorita' a colpo d'occhio.
const SEVERITY_ACCENT: Record<Notifica["severity"], string> = {
  error: "border-l-destructive",
  warning: "border-l-amber-500",
  info: "border-l-sky-500",
  success: "border-l-emerald-500",
};

type Filtro = "tutte" | "error" | "warning" | "info";

const FILTRI: { key: Filtro; label: string }[] = [
  { key: "tutte", label: "Tutte" },
  { key: "error", label: "Urgenti" },
  { key: "warning", label: "Da vedere" },
  { key: "info", label: "Informazioni" },
];

type Props = {
  notifiche: Notifica[];
  // hideCta: su mobile (PWA) nascondiamo i bottoni "vai a..." che porterebbero
  // fuori dall'app verso la vista desktop. Default false: desktop invariato.
  hideCta?: boolean;
};

export function NotificheList({ notifiche, hideCta = false }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());
  const [filtro, setFiltro] = useState<Filtro>("tutte");

  async function dismiss(id: string) {
    setLoading((prev) => new Set(prev).add(id));
    try {
      await fetch("/api/notifiche/dismiss", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      setDismissed((prev) => new Set(prev).add(id));
    } finally {
      setLoading((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  // Notifiche ancora visibili (non archiviate in questa sessione).
  const visible = useMemo(
    () => notifiche.filter((n) => !dismissed.has(n.id)),
    [notifiche, dismissed],
  );

  // Count per filtro: "Informazioni" raccoglie info + success.
  const counts = useMemo(() => {
    const c = { tutte: visible.length, error: 0, warning: 0, info: 0 };
    for (const n of visible) {
      if (n.severity === "error") c.error += 1;
      else if (n.severity === "warning") c.warning += 1;
      else c.info += 1;
    }
    return c;
  }, [visible]);

  const filtrate = useMemo(() => {
    if (filtro === "tutte") return visible;
    if (filtro === "info") return visible.filter((n) => n.severity === "info" || n.severity === "success");
    return visible.filter((n) => n.severity === filtro);
  }, [visible, filtro]);

  const gruppi = useMemo(() => raggruppa(filtrate), [filtrate]);

  if (visible.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
        <Bell className="size-10 opacity-30" />
        <p className="text-sm">Tutto archiviato. Non c&apos;è altro da vedere.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Filtri con count */}
      <div className="flex flex-wrap gap-2">
        {FILTRI.map((f) => {
          const n = counts[f.key];
          const attivo = filtro === f.key;
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFiltro(f.key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors",
                attivo
                  ? "border-foreground bg-foreground text-background"
                  : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground",
              )}
            >
              {f.label}
              <span
                className={cn(
                  "min-w-4 rounded-full px-1 text-center text-[10px] font-bold tabular-nums",
                  attivo ? "bg-background/20" : "bg-muted",
                )}
              >
                {n}
              </span>
            </button>
          );
        })}
      </div>

      {filtrate.length === 0 ? (
        <p className="py-8 text-center text-sm text-muted-foreground">
          Nessuna notifica in questa categoria.
        </p>
      ) : (
        gruppi.map((g) => (
          <section key={g.key} className="space-y-2.5">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {g.label}
              <span className="ml-1.5 text-muted-foreground/60">{g.notifiche.length}</span>
            </h2>
            <div className="space-y-2.5">
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
                        {!hideCta && cta && (
                          <Link
                            href={cta.href}
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
                      className="size-7 shrink-0"
                      disabled={loading.has(n.id)}
                      onClick={() => dismiss(n.id)}
                      title="Archivia"
                    >
                      <X className="size-4" />
                    </Button>
                  </div>
                );
              })}
            </div>
          </section>
        ))
      )}
    </div>
  );
}
