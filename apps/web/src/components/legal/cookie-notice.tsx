"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const STORAGE_KEY = "oneflux_cookie_notice_v1";

/**
 * Avviso informativo cookie. Il servizio usa SOLO cookie tecnici strettamente
 * necessari (Provv. Garante 10/06/2021): non serve un cookie-wall con
 * Accetta/Rifiuta, ma è dovuta l'informativa. Banner non bloccante, dismissibile,
 * stato persistito in localStorage.
 */
export function CookieNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) setVisible(true);
    } catch {
      // localStorage non disponibile (es. modalità privata restrittiva): non mostrare
    }
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Informativa cookie"
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80"
    >
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-relaxed text-muted-foreground">
          🍪 Usiamo <strong className="text-foreground">solo cookie tecnici</strong> necessari al
          funzionamento del servizio. Nessun cookie di profilazione o tracciamento.{" "}
          <Link href="/privacy" className="text-primary underline underline-offset-2">
            Maggiori informazioni
          </Link>
          .
        </p>
        <Button size="sm" onClick={dismiss} className="shrink-0 self-end sm:self-auto">
          Ho capito
        </Button>
      </div>
    </div>
  );
}
