"use client";

import { useState } from "react";
import { X, AlertTriangle, Info, CheckCircle, XCircle } from "lucide-react";
import { type Notifica } from "@/lib/notifiche";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

function SeverityIcon({ severity }: { severity: Notifica["severity"] }) {
  if (severity === "warning") return <AlertTriangle className="size-5 text-amber-500 shrink-0" />;
  if (severity === "error") return <XCircle className="size-5 text-destructive shrink-0" />;
  if (severity === "success") return <CheckCircle className="size-5 text-emerald-500 shrink-0" />;
  return <Info className="size-5 text-sky-500 shrink-0" />;
}

type Props = {
  notifiche: Notifica[];
};

export function NotificheList({ notifiche }: Props) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState<Set<string>>(new Set());

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

  const visible = notifiche.filter((n) => !dismissed.has(n.id));

  if (visible.length === 0) {
    return (
      <p className="text-sm text-muted-foreground text-center py-8">
        Tutte le notifiche sono state archiviate.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {visible.map((n) => (
        <Card key={n.id}>
          <CardContent className="flex items-start gap-3 py-4">
            <SeverityIcon severity={n.severity} />
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm">{n.title}</p>
              {n.body && (
                <p className="text-sm text-muted-foreground mt-0.5">{n.body}</p>
              )}
              {n.created_at && (
                <p className="text-xs text-muted-foreground mt-1.5">
                  {new Date(n.created_at).toLocaleDateString("it-IT", {
                    day: "2-digit",
                    month: "short",
                    year: "numeric",
                  })}
                </p>
              )}
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
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
