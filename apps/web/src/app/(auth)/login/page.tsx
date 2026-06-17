"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Logo, Wordmark } from "@/components/brand/logo";
import { LogoSpinner } from "@/components/brand/logo-spinner";
import { isPhoneViewport } from "@/lib/device";

// Su TELEFONO, in assenza di un next esplicito, il default e' /m (la PWA): cosi'
// il login fa un full reload direttamente sulla vista mobile, senza il rimbalzo
// SPA /dashboard -> /m. Quel rimbalzo "mangiava" l'evento beforeinstallprompt
// (sparato una sola volta a inizio caricamento pagina), togliendo il banner
// "Installa ONEFLUX". Atterrando direttamente su /m con un vero page load,
// l'evento arriva mentre il listener di /m e' gia' montato.
// I TABLET (iPad/Android tablet) vanno sempre su desktop: schermo grande, app
// completa (vedi lib/device.ts).
function defaultNext(): string {
  if (isPhoneViewport()) return "/m";
  return "/dashboard";
}

function LoginForm() {
  const searchParams = useSearchParams();
  const next = searchParams.get("next");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [overlay, setOverlay] = useState<"hidden" | "in" | "out">("hidden");
  const [error, setError] = useState<string | null>(null);

  function dismissOverlay() {
    setOverlay("out");
    setLoading(false);
    setTimeout(() => setOverlay("hidden"), 300);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setOverlay("in");
    setError(null);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || "Errore durante il login");
        dismissOverlay();
        return;
      }

      const destination = next || (data.user?.is_admin ? "/admin" : defaultNext());
      window.location.href = destination;
    } catch (err) {
      console.error(err);
      setError("Errore di connessione. Riprova.");
      dismissOverlay();
    }
  }

  return (
    <>
      {overlay !== "hidden" && <LoginOverlay closing={overlay === "out"} />}
      <Card className="w-full max-w-lg">
      <CardHeader className="space-y-4 pt-8">
        <div className="flex flex-col items-center gap-3 text-center">
          <Logo variant="icon" size={72} glow className="shrink-0" />
          <div className="space-y-1">
            <CardTitle>
              <Wordmark glow className="text-3xl tracking-[0.18em]" />
            </CardTitle>
            <CardDescription className="text-base">Accedi al tuo account</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-8">
        <form onSubmit={handleSubmit} className="space-y-5">
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
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              disabled={loading}
            />
          </div>

          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/30 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <LogoSpinner size={18} />
                Accesso in corso...
              </span>
            ) : (
              "Accedi"
            )}
          </Button>

          <p className="text-xs text-center text-muted-foreground pt-2">
            <Link href="/forgot-password" className="text-primary hover:underline">
              Hai dimenticato la password?
            </Link>
          </p>

          <p className="text-[0.7rem] text-center text-muted-foreground pt-1">
            Accedendo accetti la{" "}
            <Link href="/privacy" className="hover:underline">
              Privacy Policy
            </Link>{" "}
            e i{" "}
            <Link href="/termini" className="hover:underline">
              Termini di Servizio
            </Link>
            . Usiamo solo cookie tecnici.
          </p>
        </form>
      </CardContent>
    </Card>
    </>
  );
}

function LoginOverlay({ closing = false }: { closing?: boolean }) {
  return (
    <div
      className={`oneflux-login-overlay${closing ? " oneflux-login-overlay-out" : ""}`}
      role="status"
      aria-label="Accesso in corso"
    >
      <div className="oneflux-login-stage" style={{ width: 140, height: 140 }}>
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-ring" />
        <span className="oneflux-login-mark text-primary" style={{ width: 96, height: 96 }}>
          <svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg" className="size-full">
            <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="6" fill="none" />
            <circle cx="50" cy="50" r="31" stroke="currentColor" strokeWidth="2.5" fill="none" />
            <g className="oneflux-spinner-x" style={{ transformOrigin: "50% 50%" }}>
              <path d="M36 36 C48 44 48 56 64 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
              <path d="M64 36 C52 44 52 56 36 64" stroke="currentColor" strokeWidth="7" strokeLinecap="round" fill="none" />
            </g>
          </svg>
        </span>
      </div>
      <span className="sr-only">Accesso in corso…</span>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
