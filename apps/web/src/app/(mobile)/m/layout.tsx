import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { fetchNotifiche } from "@/lib/notifiche";
import { Logo } from "@/components/brand/logo";
import { BottomNav } from "./bottom-nav";
import { HeaderMenu } from "./header-menu";

export default async function MobileLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const notifiche = await fetchNotifiche();
  const unread = notifiche?.unread ?? 0;

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      {/* Header compatto: solo logo + nome ristorante, niente sidebar */}
      <header
        className="sticky top-0 z-40 flex h-14 items-center gap-2.5 border-b border-border bg-background/95 px-4 backdrop-blur-sm"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <Logo variant="icon" size={22} />
        <span className="truncate text-sm font-semibold">
          {user.nome_ristorante ?? "ONEFLUX"}
        </span>
        <div className="ml-auto">
          <HeaderMenu />
        </div>
      </header>

      {/* Contenuto: padding-bottom per la bottom nav (64px + safe area) */}
      <main className="flex-1 px-4 pt-4" style={{ paddingBottom: "calc(72px + env(safe-area-inset-bottom))" }}>
        {children}
      </main>

      <BottomNav unread={unread} />
    </div>
  );
}
