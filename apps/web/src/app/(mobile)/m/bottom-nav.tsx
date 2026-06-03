"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles, Bell, CalendarDays, Users, MessageCircle, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = {
  href: string;
  label: string;
  icon: typeof Sparkles;
};

const TABS: Tab[] = [
  { href: "/m/briefing", label: "Oggi", icon: Sparkles },
  { href: "/m/notifiche", label: "Avvisi", icon: Bell },
  { href: "/m/diario", label: "Diario", icon: CalendarDays },
  { href: "/m/turni", label: "Turni", icon: Users },
  { href: "/m/chat", label: "Assistente", icon: MessageCircle },
  // Profilo (Impostazioni) come tab: si naviga con <Link> SPA come le altre.
  // Prima ci si arrivava con router.push da dentro il dropdown a 3 puntini,
  // che in PWA standalone si mangiava la navigazione ("page couldn't load").
  { href: "/m/impostazioni", label: "Profilo", icon: Settings },
];

export function BottomNav({ unread, chatEnabled }: { unread: number; chatEnabled: boolean }) {
  const pathname = usePathname();
  // Tab Assistente nascosta se la chat non e' disponibile per il piano.
  const tabs = chatEnabled ? TABS : TABS.filter((t) => t.href !== "/m/chat");

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background/95 backdrop-blur-sm"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="mx-auto flex max-w-md items-stretch justify-around">
        {tabs.map((t) => {
          const active = pathname === t.href || pathname.startsWith(`${t.href}/`);
          const Icon = t.icon;
          const showBadge = t.href === "/m/notifiche" && unread > 0;
          return (
            <Link
              key={t.href}
              href={t.href}
              className={cn(
                "relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <span className="relative">
                <Icon className={cn("size-6 transition-transform", active && "scale-110")} />
                {showBadge && (
                  <span className="absolute -right-1.5 -top-1 flex min-w-4 items-center justify-center rounded-full bg-emerald-600 px-1 text-[9px] font-bold text-white">
                    {unread > 9 ? "9+" : unread}
                  </span>
                )}
              </span>
              <span className="max-w-full truncate leading-none">{t.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
