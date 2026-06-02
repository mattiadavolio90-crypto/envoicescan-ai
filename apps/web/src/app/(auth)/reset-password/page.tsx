"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Logo, Wordmark } from "@/components/brand/logo";

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const isOnboarding = searchParams.get("onboarding") === "1";

  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const t = searchParams.get("token") ?? "";
    if (t) setToken(t);
  }, [searchParams]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password !== confirm) {
      setError("Le password non coincidono");
      return;
    }
    if (password.length < 8) {
      setError("La password deve essere di almeno 8 caratteri");
      return;
    }
    if (isOnboarding && !privacyAccepted) {
      setError("Devi accettare l'Informativa Privacy e i Termini di Servizio per continuare");
      return;
    }
    setLoading(true);
    try {
      const res = await fetch("/api/auth/reset-confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: token.trim(),
          password,
          privacy_accepted: isOnboarding ? privacyAccepted : false,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || data.error || "Errore nel reset");
        return;
      }
      setDone(true);
      setTimeout(() => router.push("/login"), 3000);
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
          <Logo variant="icon" size={40} glow className="shrink-0" />
          <div>
            <CardTitle><Wordmark glow /></CardTitle>
            <CardDescription>
              {isOnboarding ? "Benvenuto — imposta la tua password" : "Nuova password"}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {done ? (
          <div className="space-y-4">
            <div className="rounded-md bg-emerald-500/10 border border-emerald-500/30 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
              {isOnboarding
                ? "Account attivato con successo! Verrai reindirizzato al login tra pochi secondi."
                : "Password reimpostata con successo! Verrai reindirizzato al login tra pochi secondi."}
            </div>
            <p className="text-xs text-center text-muted-foreground">
              <Link href="/login" className="text-primary hover:underline">Vai al login →</Link>
            </p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {isOnboarding && (
              <div className="rounded-md bg-primary/5 border border-primary/20 px-4 py-3 text-sm text-foreground">
                Il tuo account è stato creato. Scegli una password per iniziare.
              </div>
            )}
            {!searchParams.get("token") && (
              <div className="space-y-1.5">
                <Label htmlFor="token">Codice ricevuto via email</Label>
                <Input
                  id="token"
                  type="text"
                  required
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Incolla il codice dall'email"
                  disabled={loading}
                  autoFocus
                />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="password">
                {isOnboarding ? "Scegli una password" : "Nuova password"}
              </Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Almeno 8 caratteri"
                disabled={loading}
                autoFocus={!!searchParams.get("token")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="confirm">Conferma password</Label>
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Ripeti la password"
                disabled={loading}
              />
            </div>
            {isOnboarding && (
              <label className="flex items-start gap-2.5 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 shrink-0 accent-primary cursor-pointer"
                  checked={privacyAccepted}
                  onChange={(e) => setPrivacyAccepted(e.target.checked)}
                  disabled={loading}
                />
                <span>
                  Ho letto e accetto l&apos;
                  <Link href="/privacy" target="_blank" className="text-primary hover:underline">
                    Informativa Privacy
                  </Link>{" "}
                  e i{" "}
                  <Link href="/termini" target="_blank" className="text-primary hover:underline">
                    Termini di Servizio
                  </Link>
                  . Acconsento al trattamento dei miei dati per l&apos;erogazione del servizio
                  (GDPR UE 2016/679, art. 6.1.b).
                </span>
              </label>
            )}
            {error && (
              <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}
            <Button
              type="submit"
              className="w-full"
              disabled={
                loading ||
                !token.trim() ||
                !password ||
                !confirm ||
                (isOnboarding && !privacyAccepted)
              }
            >
              {loading
                ? "Salvataggio..."
                : isOnboarding
                ? "Attiva il mio account"
                : "Imposta nuova password"}
            </Button>
            {!isOnboarding && (
              <p className="text-xs text-center text-muted-foreground pt-1">
                <Link href="/login" className="text-primary hover:underline">← Torna al login</Link>
              </p>
            )}
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
