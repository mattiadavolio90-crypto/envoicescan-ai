import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { CookieNotice } from "@/components/legal/cookie-notice";
import { ThemeProvider } from "@/components/theme-provider";
import { PwaRegister } from "@/components/pwa-register";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: {
    default: "ONEFLUX",
    template: "%s · ONEFLUX",
  },
  description: "Gestione costi ristorante",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "ONEFLUX",
  },
  other: {
    "mobile-web-app-capable": "yes",
  },
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
    <html lang="it" suppressHydrationWarning className={cn(tema, "font-sans", inter.variable)}>
      <body className="antialiased">
        {/* Boot overlay PWA: parte col primo paint, copre lo splash statico del
            sistema con l'animazione di brand. Lo script inline lo mostra solo in
            modalita' standalone (PWA installata) e lo chiude dopo ~1.3s. */}
        <div id="oneflux-boot" aria-hidden suppressHydrationWarning style={{ display: "none" }}>
          <div className="oneflux-login-stage" style={{ width: 160, height: 160 }}>
            <span className="oneflux-login-ring" />
            <span className="oneflux-login-ring" />
            <span className="oneflux-login-mark text-primary" style={{ width: 104, height: 104 }}>
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
        </div>
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
