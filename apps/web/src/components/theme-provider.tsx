"use client";

import { useEffect } from "react";
import { ThemeProvider as NextThemesProvider, useTheme } from "next-themes";

// Riallinea next-themes (localStorage) alla preferenza dell'account quando i due
// divergono. Il tema dell'account viene letto LATO CLIENT da /api/auth/me dopo
// il mount: cosi' il root layout non deve bloccare il primo paint su una
// chiamata al worker. next-themes gestisce gia' l'anti-flash da localStorage.
function SyncAccountTheme() {
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    let annullato = false;
    (async () => {
      try {
        const res = await fetch("/api/auth/me", { cache: "no-store" });
        if (!res.ok) return;
        const user = (await res.json()) as { tema?: "dark" | "light" };
        if (annullato || !user?.tema) return;
        if (theme !== user.tema) setTheme(user.tema);
      } catch {
        /* offline o non loggato: resta il tema di localStorage */
      }
    })();
    return () => {
      annullato = true;
    };
    // Solo al mount: dopo, la fonte di verita' e' l'azione dell'utente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

export function ThemeProvider({
  children,
  defaultTheme,
}: {
  children: React.ReactNode;
  defaultTheme: string;
}) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme={defaultTheme}
      enableSystem={false}
      disableTransitionOnChange
    >
      <SyncAccountTheme />
      {children}
    </NextThemesProvider>
  );
}
