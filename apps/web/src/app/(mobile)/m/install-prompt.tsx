"use client";

import { useEffect, useState } from "react";
import { Download, X, Share, Plus } from "lucide-react";

const STORAGE_KEY = "oneflux_install_prompt_dismissed_v1";

// Evento Chrome/Android per l'installazione PWA (non tipizzato nei lib standard).
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

// L'evento e' catturato globalmente da public/pwa-install-capture.js (gira
// prima dell'idratazione) e conservato qui, perche' Chrome lo emette una sola
// volta a inizio caricamento, spesso prima che questo componente monti.
declare global {
  interface Window {
    __oneflux_bip?: BeforeInstallPromptEvent | null;
  }
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
  const [showIosSheet, setShowIosSheet] = useState(false);
  const [visible, setVisible] = useState(false);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    // Già installata o già rifiutata → non mostrare nulla.
    if (isStandalone()) return;
    try {
      if (localStorage.getItem(STORAGE_KEY) === "1") return;
    } catch {
      /* localStorage non disponibile: prosegui */
    }

    if (isIos()) {
      // iOS non emette beforeinstallprompt: mostriamo subito il banner-istruzioni.
      setIos(true);
      setVisible(true);
      return;
    }

    // Android/Chrome: l'evento beforeinstallprompt e' gia' stato catturato e
    // conservato da pwa-install-capture.js (che NON fa preventDefault, per non
    // sopprimere il prompt nativo sulle pagine senza banner). Qui su /m, invece,
    // abbiamo il banner custom: facciamo noi preventDefault per evitare il
    // doppione (nativo + custom) e usiamo l'evento conservato.
    const bip = window.__oneflux_bip;
    if (bip) {
      bip.preventDefault();
      setDeferred(bip);
      setVisible(true);
    }

    const onInstallable = () => {
      const ev = window.__oneflux_bip;
      if (ev) {
        ev.preventDefault();
        setDeferred(ev);
        setVisible(true);
      }
    };
    window.addEventListener("oneflux:installable", onInstallable);

    // Se l'evento arriva DOPO che siamo gia' montati (es. navigazione che
    // ricarica /m), lo intercettiamo anche direttamente qui per fare in tempo
    // a chiamare preventDefault prima che Chrome mostri il nativo.
    const onBeforeInstall = (e: Event) => {
      e.preventDefault();
      window.__oneflux_bip = e as BeforeInstallPromptEvent;
      setDeferred(e as BeforeInstallPromptEvent);
      setVisible(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // Quando l'utente installa, nascondiamo tutto.
    const onInstalled = () => setVisible(false);
    window.addEventListener("appinstalled", onInstalled);

    return () => {
      window.removeEventListener("oneflux:installable", onInstallable);
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  function dismiss() {
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setVisible(false);
    setShowIosSheet(false);
  }

  async function installaAndroid() {
    if (!deferred) return;
    await deferred.prompt();
    const { outcome } = await deferred.userChoice;
    if (outcome === "accepted") setVisible(false);
    else dismiss();
    setDeferred(null);
    window.__oneflux_bip = null;
  }

  if (!visible) return null;

  return (
    <>
      {/* Banner: appena sopra la bottom nav */}
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
            onClick={ios ? () => setShowIosSheet(true) : installaAndroid}
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

      {/* Foglio istruzioni iOS (Apple non offre prompt automatico) */}
      {showIosSheet && (
        <div
          className="fixed inset-0 z-[60] flex items-end bg-black/40"
          onClick={() => setShowIosSheet(false)}
        >
          <div
            className="w-full rounded-t-3xl border-t border-border bg-background p-5"
            style={{ paddingBottom: "calc(1.25rem + env(safe-area-inset-bottom))" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-muted" />
            <h2 className="text-base font-semibold">Aggiungi alla schermata Home</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Su iPhone l&apos;installazione si fa da Safari in due passaggi:
            </p>
            <ol className="mt-4 space-y-3">
              <li className="flex items-center gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">1</span>
                <span className="flex items-center gap-1.5 text-sm">
                  Tocca <Share className="inline size-4 text-primary" /> <strong>Condividi</strong> (in basso)
                </span>
              </li>
              <li className="flex items-center gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-bold text-primary">2</span>
                <span className="flex items-center gap-1.5 text-sm">
                  Scegli <Plus className="inline size-4 text-primary" /> <strong>Aggiungi a Home</strong>
                </span>
              </li>
            </ol>
            <button
              onClick={() => setShowIosSheet(false)}
              className="mt-5 w-full rounded-xl bg-primary py-3 text-sm font-semibold text-primary-foreground active:scale-[0.99]"
            >
              Ho capito
            </button>
          </div>
        </div>
      )}
    </>
  );
}
