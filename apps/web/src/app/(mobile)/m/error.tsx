"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";

// Rete di sicurezza per tutto il gruppo /m: se una pagina o un suo componente
// lancia durante il render lato client, invece di una schermata bianca o del
// "this page couldn't load" del WebView mostriamo un fallback gentile con un
// pulsante per riprovare. Vale per tutte le tab, non solo Impostazioni.
// `unstable_retry` rilegge la schermata dal server: `reset` la rendeva di nuovo
// con lo stesso errore (es. la guardia di pagina col worker irraggiungibile).
export default function MobileError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    // Lasciamo traccia in console: utile se serve diagnosticare da remoto.
    console.error("Errore pagina mobile:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-6 text-center">
      <p className="text-sm text-muted-foreground">
        Qualcosa è andato storto nel caricare questa schermata.
      </p>
      <button
        type="button"
        onClick={() => unstable_retry()}
        className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium active:bg-accent"
      >
        <RefreshCw className="size-4" />
        Riprova
      </button>
    </div>
  );
}
