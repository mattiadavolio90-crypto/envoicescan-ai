"use client";

import { useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/reset-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error || "Errore nell'invio email");
        return;
      }
      setSent(true);
    } catch {
      setError("Errore di connessione. Riprova.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="flex aspect-square size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground font-bold">
            O
          </div>
          <div>
            <CardTitle>ONEFLUX</CardTitle>
            <CardDescription>Recupero password</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {sent ? (
          <div className="space-y-4">
            <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
              Se l&apos;email è registrata riceverai un link per reimpostare la password. Controlla la casella di posta (anche la cartella spam).
            </div>
            <p className="text-xs text-center text-muted-foreground pt-2">
              <Link href="/login" className="text-primary hover:underline">
                ← Torna al login
              </Link>
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Inserisci l&apos;email del tuo account e ti invieremo un link per reimpostare la password.
            </p>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nome@ristorante.it"
                disabled={loading}
                autoFocus
              />
            </div>
            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
            <Button type="submit" className="w-full" disabled={loading || !email.trim()}>
              {loading ? "Invio in corso..." : "Invia link di recupero"}
            </Button>
            <p className="text-xs text-center text-muted-foreground pt-1">
              <Link href="/login" className="text-primary hover:underline">
                ← Torna al login
              </Link>
            </p>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
