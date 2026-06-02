import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { fetchNotifiche } from "@/lib/notifiche";
import { fetchConfig } from "@/lib/home";
import { Logo } from "@/components/brand/logo";
import { BottomNav } from "./bottom-nav";
import { HeaderMenu } from "./header-menu";
import { InstallPrompt } from "./install-prompt";
import { PullToRefresh } from "./pull-to-refresh";

export default async function MobileLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const [notifiche, config] = await Promise.all([fetchNotifiche(), fetchConfig()]);
  const unread = notifiche?.unread ?? 0;
  // Stessa regola del widget chat desktop: la chat c'e' solo se abilitata e il
  // piano ha un limite > 0 (i piani free hanno limite 0). Se non disponibile,
  // la tab Assistente sparisce dalla bottom nav (niente 403 secco al tocco).
  const chatEnabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;

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

      <PullToRefresh />

      {/* Contenuto: padding-bottom per la bottom nav (64px + safe area) */}
      <main className="flex-1 px-4 pt-4" style={{ paddingBottom: "calc(72px + env(safe-area-inset-bottom))" }}>
        {children}
      </main>

      <InstallPrompt />
      <BottomNav unread={unread} chatEnabled={chatEnabled} />
    </div>
  );
}
