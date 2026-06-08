"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sparkles, CalendarDays, ArrowRightLeft, MessageCircle, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = {
  href: string;
  label: string;
  icon: typeof Sparkles;
};

// 5 tab. Gli Avvisi NON sono qui: vivono come campanella con badge nell'header
// (pattern universale: le notifiche stanno in alto, non nella nav in basso).
const TABS: Tab[] = [
  { href: "/m/briefing", label: "Home", icon: Sparkles },
  { href: "/m/diario", label: "Agenda", icon: CalendarDays },
  { href: "/m/turni", label: "Movimenti", icon: ArrowRightLeft },
  { href: "/m/chat", label: "Assistente", icon: MessageCircle },
  // Profilo (Impostazioni) come tab: si naviga con <Link> SPA come le altre.
  // Prima ci si arrivava con router.push da dentro il dropdown a 3 puntini,
  // che in PWA standalone si mangiava la navigazione ("page couldn't load").
  { href: "/m/impostazioni", label: "Profilo", icon: Settings },
];

export function BottomNav({ chatEnabled }: { chatEnabled: boolean }) {
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
          return (
            <Link
              key={t.href}
              href={t.href}
              // prefetch esplicito: i chunk di ogni tab si scaricano in anticipo,
              // cosi' il cambio tab e' istantaneo e non dipende dalla rete nel
              // momento del tocco (era una causa dei "couldn't load" navigando).
              prefetch
              className={cn(
                "relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <span className="relative">
                <Icon className={cn("size-6 transition-transform", active && "scale-110")} />
              </span>
              <span className="max-w-full truncate leading-none">{t.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
