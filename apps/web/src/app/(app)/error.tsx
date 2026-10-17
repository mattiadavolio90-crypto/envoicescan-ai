"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

// Rete di sicurezza per le pagine di (app), gemella di (mobile)/m/error.tsx: la
// sidebar resta, al posto della pagina un «Riprova». Ci arriva anche la guardia di
// pagina quando la sessione non si puo' verificare (worker irraggiungibile sulla
// navigazione client, dove il layout non si rigira). `unstable_retry` rilegge la
// pagina dal server; `reset` la renderebbe di nuovo con lo stesso errore.
export default function AppError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    console.error("Errore pagina:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-sm text-muted-foreground">
        Questa pagina non si è caricata. Il servizio potrebbe essere in riavvio.
      </p>
      <Button variant="outline" onClick={() => unstable_retry()}>
        <RefreshCw className="size-4" />
        Riprova
      </Button>
    </div>
  );
}
