import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { CookieNotice } from "@/components/legal/cookie-notice";
import { ThemeProvider } from "@/components/theme-provider";
import { PwaRegister } from "@/components/pwa-register";
import { getCurrentUser } from "@/lib/auth";

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

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await getCurrentUser();
  const tema = user?.tema ?? "dark";

  // Classe del tema renderizzata server-side dal DB: il primo paint e' gia'
  // corretto (niente flash). next-themes prende il controllo dopo il mount e,
  // se localStorage diverge dal DB, lo riallinea (vedi ThemeProvider).
  return (
    <html lang="it" suppressHydrationWarning className={cn(tema, "font-sans", inter.variable)}>
      <body className="antialiased">
        {/* Boot overlay PWA: parte col primo paint, copre lo splash statico del
            sistema con l'animazione di brand. Lo script inline lo mostra solo in
            modalita' standalone (PWA installata) e lo chiude dopo ~1.3s. */}
        <div id="oneflux-boot" aria-hidden style={{ display: "none" }}>
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
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone===true;var b=document.getElementById('oneflux-boot');if(!b)return;if(!s){b.parentNode.removeChild(b);return;}b.style.display='flex';setTimeout(function(){document.body.classList.add('app-ready');setTimeout(function(){if(b&&b.parentNode)b.parentNode.removeChild(b);},400);},1300);}catch(e){var b2=document.getElementById('oneflux-boot');if(b2&&b2.parentNode)b2.parentNode.removeChild(b2);}})();`,
          }}
        />
        <ThemeProvider defaultTheme={tema} temaAccount={tema}>
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
