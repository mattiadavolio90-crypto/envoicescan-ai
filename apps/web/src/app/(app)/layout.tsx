import { redirect } from "next/navigation";
import Link from "next/link";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/nav/app-sidebar";
import { Wordmark } from "@/components/brand/logo";
import { Separator } from "@/components/ui/separator";
import { getCurrentUser } from "@/lib/auth";
import { fetchNotifiche } from "@/lib/notifiche";
import { ImpersonaBanner } from "@/components/admin/impersona-banner";
import { MobileRedirect } from "@/components/mobile-redirect";
import { Bell, LifeBuoy } from "lucide-react";

function getInitials(nome: string | null, email: string): string {
  if (nome) {
    const parts = nome.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return nome.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();

  if (!user) {
    redirect("/login");
  }

  // Fonte UNICA del contatore: le notifiche reali non archiviate
  // (notification_inbox), le stesse che vedi nel widget Home e nella pagina
  // /notifiche. Prima il badge contava le "azioni" del briefing — una fonte
  // diversa — e il numero non combaciava con cio' che si apriva davvero.
  const notifiche = await fetchNotifiche();
  const unreadNotifiche = notifiche?.unread ?? 0;

  return (
    <>
    <MobileRedirect />
    <ImpersonaBanner />
    <SidebarProvider>
      <AppSidebar
        userEmail={user.email}
        userInitials={getInitials(user.nome_ristorante, user.email)}
        ristoranteNome={user.nome_ristorante ?? "Ristorante"}
        isAdmin={user.is_admin}
      />
      <SidebarInset>
        <header className="flex h-14 items-center gap-2 px-4 border-b border-border">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="h-4" />
          <Wordmark className="text-sm" />
          <div className="ml-auto flex items-center gap-0.5">
            <Link
              href="/assistenza"
              title="Servizi per il tuo locale"
              className="inline-flex items-center justify-center size-9 rounded-md text-primary transition-colors hover:bg-accent"
            >
              <LifeBuoy className="size-5" />
            </Link>
            <Link
              href="/dashboard"
              title="Vai alle notifiche in Home"
              className="relative inline-flex items-center justify-center size-9 rounded-md text-primary transition-colors hover:bg-accent"
            >
              <Bell className="size-5" />
              {unreadNotifiche > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex min-w-5 items-center justify-center rounded-full bg-emerald-600 px-1 text-[10px] font-bold text-white">
                  {unreadNotifiche > 9 ? "9+" : unreadNotifiche}
                </span>
              )}
            </Link>
          </div>
        </header>
        <main className="flex-1 p-6">{children}</main>
      </SidebarInset>
    </SidebarProvider>
    </>
  );
}
