"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MENU_ADMIN, voceAttiva } from "@/lib/admin-clienti";

export function AdminMenu() {
  const pathname = usePathname() ?? "";
  return (
    <nav className="flex gap-1 border-b overflow-x-auto" aria-label="Pannello admin">
      {MENU_ADMIN.map((v) => {
        const attiva = voceAttiva(pathname, v.href);
        return (
          <Link
            key={v.href}
            href={v.href}
            aria-current={attiva ? "page" : undefined}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
              attiva ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {v.label}
          </Link>
        );
      })}
    </nav>
  );
}
