"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bell } from "lucide-react";
import { cn } from "@/lib/utils";

// Campanella avvisi nell'header. Sostituisce la vecchia tab "Avvisi" della bottom
// nav: le notifiche stanno in alto (pattern universale, gesto familiare). E' un
// <Link> SPA con prefetch, non un router.push da dropdown: navigazione pulita,
// lontana dal bug "page couldn't load" della PWA standalone.
export function NotificheBell({ unread }: { unread: number }) {
  const pathname = usePathname();
  const active = pathname === "/m/notifiche" || pathname.startsWith("/m/notifiche/");

  return (
    <Link
      href="/m/notifiche"
      prefetch
      aria-label={unread > 0 ? `Avvisi (${unread} da gestire)` : "Avvisi"}
      className={cn(
        "relative flex size-9 items-center justify-center rounded-md transition-colors active:bg-accent",
        active ? "text-primary" : "text-muted-foreground",
      )}
    >
      <Bell className="size-5" />
      {unread > 0 && (
        <span className="absolute -right-0.5 -top-0.5 flex min-w-4 items-center justify-center rounded-full bg-emerald-600 px-1 text-[9px] font-bold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );
}
