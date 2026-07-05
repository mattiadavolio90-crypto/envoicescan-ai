import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser } from "@/lib/auth";
import { fetchNotifiche } from "@/lib/notifiche";
import { fetchConfig } from "@/lib/home";
import { Logo } from "@/components/brand/logo";
import { BottomNav } from "./bottom-nav";
import { HeaderMenu } from "./header-menu";
import { NotificheBell } from "./notifiche-bell";
import { InstallPrompt } from "./install-prompt";
import { PullToRefresh } from "./pull-to-refresh";
import { IncassoReminder } from "./incasso-reminder";
import { PrivacyConsentModal } from "@/components/legal/privacy-consent-modal";

export default async function MobileLayout({ children }: { children: React.ReactNode }) {
  // Le tre chiamate al worker partono insieme (prima auth era awaitata da sola,
  // poi le altre due: due round-trip in serie a ogni navigazione tra tab).
  const [user, notifiche, config] = await Promise.all([
    getCurrentUser(),
    fetchNotifiche(),
    fetchConfig(),
  ]);
  if (!user) redirect("/login");

  // In modalità catena (multi-sede, cookie != pv) l'header parla del gruppo, non
  // della sede attiva.
  const cookieStore = await cookies();
  const inChain = (user.num_sedi ?? 1) >= 2 && cookieStore.get("oneflux_view")?.value !== "pv";

  const unread = notifiche?.unread ?? 0;
  // Stessa regola del widget chat desktop: la chat c'e' solo se abilitata e il
  // piano ha un limite > 0 (i piani free hanno limite 0). Se non disponibile,
  // la tab Assistente sparisce dalla bottom nav (niente 403 secco al tocco).
  const chatEnabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;

  return (
    <div className="flex min-h-dvh flex-col bg-background">
      <PrivacyConsentModal needsConsent={user.privacy_accepted === false} />
      {/* Header compatto: solo logo + nome ristorante, niente sidebar */}
      <header
        className="sticky top-0 z-40 flex h-14 items-center gap-2.5 border-b border-border bg-background/95 px-4 backdrop-blur-sm"
        style={{ paddingTop: "env(safe-area-inset-top)" }}
      >
        <Logo variant="icon" size={22} />
        <span className="truncate text-sm font-semibold">
          {inChain ? "Tutti i punti vendita" : (user.sede_attiva_nome ?? user.nome_ristorante ?? "ONEFLUX")}
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <NotificheBell unread={unread} />
          <HeaderMenu />
        </div>
      </header>

      <PullToRefresh />

      {/* Contenuto: padding-bottom per la bottom nav (64px + safe area) */}
      <main className="flex-1 px-4 pt-4" style={{ paddingBottom: "calc(72px + env(safe-area-inset-bottom))" }}>
        {children}
      </main>

      <InstallPrompt />
      <IncassoReminder />
      <BottomNav chatEnabled={chatEnabled} />
    </div>
  );
}
