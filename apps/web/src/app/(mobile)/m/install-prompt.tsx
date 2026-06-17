"use client";

import { useEffect, useState } from "react";
import { Download, X, Share, Plus } from "lucide-react";

// "A ogni sessione": il rifiuto vale solo per la sessione corrente (sessionStorage),
// quindi alla riapertura dell'app il banner riappare finche' la PWA non e' installata.
const STORAGE_KEY = "oneflux_install_prompt_dismissed_session";

// Ritardo prima di mostrare il banner: evita la comparsa "a freddo" appena si
// entra su /m (subito dopo il login l'utente sta ancora orientandosi).
const SHOW_DELAY_MS = 4000;

// Evento Chrome/Android per l'installazione PWA (non tipizzato nei lib standard).
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}


function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    // iOS Safari espone navigator.standalone
    (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function isIos(): boolean {
  if (typeof window === "undefined") return false;
  return /iphone|ipad|ipod/i.test(window.navigator.userAgent);
}

export function InstallPrompt() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [visible, setVisible] = useState(false);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    // Già installata o già rifiutata in questa sessione → non mostrare nulla.
    if (isStandalone()) return;
    try {
      if (sessionStorage.getItem(STORAGE_KEY) === "1") return;
    } catch {
      /* sessionStorage non disponibile: prosegui */
    }

    if (isIos()) {
      // iOS non emette beforeinstallprompt: mostriamo il banner-istruzioni dopo
      // un breve ritardo (no comparsa a freddo subito dopo il login).
      setIos(true);
      const t = setTimeout(() => setVisible(true), SHOW_DELAY_MS);
      return () => clearTimeout(t);
    }

    // Android/Chrome: ascoltiamo l'evento e mostriamo il banner custom. Qui su
    // /m facciamo preventDefault per sostituire il mini-infobar nativo col
    // nostro banner. Fuori da /m non c'e' questo componente, quindi il nativo di
    // Chrome resta disponibile (es. /admin), come dev'essere.
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // Quando l'utente installa, nascondiamo tutto.
    const onInstalled = () => setVisible(false);
    window.addEventListener("appinstalled", onInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  function dismiss() {
    try {
      sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setVisible(false);
  }

  async function installaAndroid() {
    if (!deferred) return;
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") setVisible(false);
    else dismiss();
    setDeferred(null);
  }

  if (!visible) return null;

  // ── iOS: istruzioni dirette nel banner (Apple non offre prompt automatico) ──
  if (ios) {
    return (
      <div
        className="fixed inset-x-0 z-50 px-3"
        style={{ bottom: "calc(72px + env(safe-area-inset-bottom))" }}
      >
        <div className="mx-auto max-w-md rounded-2xl border border-primary/30 bg-background/95 p-3.5 shadow-lg backdrop-blur">
          <div className="flex items-start gap-3">
            <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Download className="size-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold">Installa ONEFLUX sul telefono</p>
              <ol className="mt-2 space-y-1.5">
                <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">1</span>
                  Tocca <Share className="inline size-4 text-primary" /> <strong className="text-foreground">Condividi</strong> in basso
                </li>
                <li className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">2</span>
                  Scegli <Plus className="inline size-4 text-primary" /> <strong className="text-foreground">Aggiungi a Home</strong>
                </li>
              </ol>
            </div>
            <button
              onClick={dismiss}
              className="-mr-1 -mt-1 shrink-0 rounded-md p-1 text-muted-foreground active:bg-muted"
              aria-label="Chiudi"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
        {/* Freccia che punta verso il pulsante Condividi di Safari (in basso) */}
        <div className="pointer-events-none mx-auto mt-1 flex max-w-md justify-center">
          <span className="animate-bounce text-2xl text-primary">↓</span>
        </div>
      </div>
    );
  }

  // ── Android/Chrome: banner con installazione nativa ──
  return (
    <div
      className="fixed inset-x-0 z-50 px-3"
      style={{ bottom: "calc(72px + env(safe-area-inset-bottom))" }}
    >
      <div className="mx-auto flex max-w-md items-center gap-3 rounded-2xl border border-primary/30 bg-background/95 p-3 shadow-lg backdrop-blur">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Download className="size-5" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">Installa ONEFLUX</p>
          <p className="text-xs text-muted-foreground">Aggiungila alla schermata Home, come un&apos;app.</p>
        </div>
        <button
          onClick={installaAndroid}
          className="shrink-0 rounded-lg bg-primary px-3.5 py-2 text-sm font-semibold text-primary-foreground active:scale-95"
        >
          Installa
        </button>
        <button
          onClick={dismiss}
          className="shrink-0 rounded-md p-1 text-muted-foreground active:bg-muted"
          aria-label="Chiudi"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}
