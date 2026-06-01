import { redirect } from "next/navigation";
import Link from "next/link";
import { SidebarProvider, SidebarInset, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/nav/app-sidebar";
import { Separator } from "@/components/ui/separator";
import { getCurrentUser } from "@/lib/auth";
import { fetchBriefing } from "@/lib/home";
import { ImpersonaBanner } from "@/components/admin/impersona-banner";
import { Bell } from "lucide-react";

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

  // Fonte UNICA del contatore: le azioni "da fare" del briefing (le stesse
  // card della Home e del widget). Niente piu' numeri discordanti tra header,
  // sidebar e Home. Il briefing e' cache-ato su DB, quindi e' una lettura leggera.
  const briefing = await fetchBriefing();
  const unreadNotifiche = briefing?.tutto_ok ? 0 : briefing?.azioni.length ?? 0;

  return (
    <>
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
          <span className="text-sm text-muted-foreground">ONEFLUX</span>
          <div className="ml-auto flex items-center">
            <Link
              href="/dashboard"
              title="Vai alle notifiche in Home"
              className="relative inline-flex items-center justify-center size-9 rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
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
