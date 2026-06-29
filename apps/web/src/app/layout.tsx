import type { Metadata, Viewport } from "next";
import { Inter, Quicksand, Sora } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { CookieNotice } from "@/components/legal/cookie-notice";
import { ThemeProvider } from "@/components/theme-provider";
import { PwaRegister } from "@/components/pwa-register";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const quicksand = Quicksand({ subsets: ["latin"], weight: ["700"], variable: "--font-wordmark" });
// Font display della landing scrollytelling (geometrico, deciso). Solo --font-sora:
// non viene applicato globalmente, lo usa la landing via la classe font-display.
const sora = Sora({ subsets: ["latin"], weight: ["600", "700", "800"], variable: "--font-sora" });

// NB: manifest e flag PWA (appleWebApp, mobile-web-app-capable) NON stanno qui,
// ma nel layout (app): la landing pubblica "/" non deve far comparire il prompt
// "Installa ONEFLUX" di Chrome. Il manifest vive solo dentro l'app.
export const metadata: Metadata = {
  title: {
    default: "ONEFLUX",
    template: "%s · ONEFLUX",
  },
  description: "Gestione costi ristorante",
};

export const viewport: Viewport = {
  themeColor: "#0ea5e9",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // NIENTE await sul worker qui: bloccava il primo paint di ogni pagina (~1s) e
  // allungava lo splash statico della PWA. Il tema lo gestisce next-themes da
  // localStorage prima del paint (anti-flash) e ThemeProvider lo riallinea
  // all'account lato client. Default "dark" finche' next-themes non monta.
  const tema = "dark";

  return (
    <html lang="it" suppressHydrationWarning className={cn(tema, "font-sans", inter.variable, quicksand.variable, sora.variable)}>
      <body className="antialiased">
        {/* Boot overlay PWA: NON e' nel JSX. Lo crea e lo rimuove interamente
            boot-overlay.js (gira beforeInteractive, prima di React). Motivo: un
            nodo renderizzato da React e poi rimosso da uno script esterno
            corrompeva l'idratazione e faceva fallire la PRIMA navigazione SPA
            ("couldn't load" al primo tocco). Tenendolo fuori da React, l'albero
            idratato resta integro. */}
        <Script src="/boot-overlay.js" strategy="beforeInteractive" />
        <ThemeProvider defaultTheme={tema}>
          <TooltipProvider>
            {children}
            <CookieNotice />
            <Toaster />
            <PwaRegister />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
