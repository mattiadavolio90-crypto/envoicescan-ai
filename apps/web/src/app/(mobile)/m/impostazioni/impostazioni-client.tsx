"use client";

import { useEffect, useState } from "react";
import { AccountClient } from "@/app/(app)/impostazioni/account-client";

// Carica i dati account LATO CLIENT (dopo il mount), come fanno Diario e Turni.
// Cosi' la pagina si apre SEMPRE: il render server non dipende da una chiamata
// al worker (che, se lenta/fallita in SSR, faceva "this page couldn't load"
// nel WebView della PWA). I dati arrivano subito dopo, con skeleton nel mentre.
export function ImpostazioniClient() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [stato, setStato] = useState<"loading" | "ok" | "errore">("loading");

  useEffect(() => {
    let annullato = false;
    (async () => {
      try {
        const res = await fetch("/api/account/me", { cache: "no-store" });
        if (!res.ok) throw new Error();
        const d = await res.json();
        if (!annullato) {
          setData(d);
          setStato("ok");
        }
      } catch {
        if (!annullato) setStato("errore");
      }
    })();
    return () => {
      annullato = true;
    };
  }, []);

  if (stato === "loading") {
    return (
      <div className="space-y-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-32 animate-pulse rounded-2xl border bg-muted/40" />
        ))}
      </div>
    );
  }

  if (stato === "errore" || !data) {
    return (
      <p className="text-sm text-muted-foreground">
        Impossibile caricare i dati. Tira giù per aggiornare o riprova più tardi.
      </p>
    );
  }

  // AccountClient tipizza `data` internamente; il fetch restituisce la stessa
  // forma di /api/account/me usata dalla pagina desktop.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return <AccountClient data={data as any} />;
}
