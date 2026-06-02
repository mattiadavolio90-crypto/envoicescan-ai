import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { CookieNotice } from "@/components/legal/cookie-notice";
import { ThemeProvider } from "@/components/theme-provider";
import { getCurrentUser } from "@/lib/auth";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: {
    default: "ONEFLUX",
    template: "%s · ONEFLUX",
  },
  description: "Gestione costi ristorante",
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
        <ThemeProvider defaultTheme={tema} temaAccount={tema}>
          <TooltipProvider>
            {children}
            <CookieNotice />
            <Toaster />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
