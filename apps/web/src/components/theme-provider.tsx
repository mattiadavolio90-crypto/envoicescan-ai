"use client";

import { useEffect } from "react";
import { ThemeProvider as NextThemesProvider, useTheme } from "next-themes";

// Riallinea next-themes (localStorage) alla preferenza dell'account (DB) quando
// i due divergono: cosi' la scelta "segue l'account" anche su un dispositivo
// nuovo o dopo che la preferenza e' stata cambiata altrove. Senza questo,
// localStorage avrebbe sempre la precedenza e ignorerebbe il DB.
function SyncAccountTheme({ temaAccount }: { temaAccount: string }) {
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    if (theme && theme !== temaAccount) {
      setTheme(temaAccount);
    }
    // Solo al mount: dopo, la fonte di verita' e' l'azione dell'utente.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

export function ThemeProvider({
  children,
  defaultTheme,
  temaAccount,
}: {
  children: React.ReactNode;
  defaultTheme: string;
  temaAccount: string;
}) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme={defaultTheme}
      enableSystem={false}
      disableTransitionOnChange
    >
      <SyncAccountTheme temaAccount={temaAccount} />
      {children}
    </NextThemesProvider>
  );
}
