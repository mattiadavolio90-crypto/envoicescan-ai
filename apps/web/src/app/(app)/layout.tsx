import type { Metadata } from "next";
import { redirect } from "next/navigation";
import Link from "next/link";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/nav/app-sidebar";
import { Wordmark } from "@/components/brand/logo";
import { Separator } from "@/components/ui/separator";
import { getCurrentSession } from "@/lib/auth";
import { ImpersonaBanner } from "@/components/admin/impersona-banner";
import { MobileRedirect } from "@/components/mobile-redirect";
import { PrivacyConsentModal } from "@/components/legal/privacy-consent-modal";
import { LifeBuoy, WifiOff } from "lucide-react";

// PWA solo dentro l'app: manifest + flag installazione vivono qui, non nel root,
// cosi' la landing pubblica "/" non mostra il prompt "Installa ONEFLUX" di Chrome.
export const metadata: Metadata = {
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

function getInitials(nome: string | null, email: string): string {
  if (nome) {
    const parts = nome.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return nome.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getCurrentSession();

  // Token scaduto / assente -> al login. Il login rigenera il cookie.
  if (session.status === "invalid") {
    redirect("/login");
  }

  // Worker non raggiungibile (cold-start Railway, rete): NON sloggare l'utente.
  // Mostra un messaggio con possibilita' di riprovare. Prima un timeout qui
  // mandava al login un utente con sessione valida, oppure faceva renderizzare
  // la home a vuoto (tutti i blocchi in 401/timeout).
  if (session.status === "unavailable") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
        <WifiOff className="size-10 text-muted-foreground/50" />
        <div>
          <p className="text-base font-medium">Servizio momentaneamente non raggiungibile</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Il server sta riavviando. Riprova tra qualche secondo.
          </p>
        </div>
        <Link
          href="/dashboard"
          className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          Riprova
        </Link>
      </div>
    );
  }

  const user = session.user;

  return (
    <>
    <MobileRedirect />
    <PrivacyConsentModal needsConsent={user.privacy_accepted === false} />
    <ImpersonaBanner />
    <SidebarProvider>
      <AppSidebar
        userEmail={user.email}
        userInitials={getInitials(user.sede_attiva_nome ?? user.nome_ristorante, user.email)}
        ristoranteNome={user.sede_attiva_nome ?? user.nome_ristorante ?? "Ristorante"}
        isAdmin={user.is_admin}
        pagineAbilitate={user.pagine_abilitate}
      />
      <SidebarInset>
        <header className="relative flex h-14 items-center gap-2 px-4 border-b border-border">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="h-4" />
          <Wordmark className="pointer-events-none absolute left-1/2 -translate-x-1/2 text-2xl" />
          <div className="ml-auto flex items-center gap-0.5">
            <Link
              href="/assistenza"
              title="Servizi per il tuo locale"
              className="inline-flex items-center justify-center size-9 rounded-md text-primary transition-colors hover:bg-accent"
            >
              <LifeBuoy className="size-5" />
            </Link>
            {/* Campanella eliminata (decisione 19/06): agli Avvisi si accede dalla
                Home (widget) o dalla pagina /notifiche, non da un'icona in header. */}
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
    </>
  );
}
