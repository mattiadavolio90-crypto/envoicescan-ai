"use client";

import { useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { TAB_SEZIONI, type TabDef } from "@/lib/tab-flags";

// Le tab sono in @/lib/tab-flags (unica fonte, condivisa col pannello admin).
// `disponibili` arriva gia' filtrato dal server component: qui non si decide
// nulla sui permessi, si rende cio' che il guard ha consentito.
export function TabsSwitcher({ active, disponibili }: { active: string; disponibili?: TabDef[] }) {
  const elenco = disponibili ?? TAB_SEZIONI["analisi_fatture"];
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  function setTab(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("tab", key);
    // I toggle del tab Articoli (nuovi/verifica) sono in URL: li azzeriamo al cambio tab.
    params.delete("nuovi");
    params.delete("verifica");
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  return (
    <div className={`flex gap-1 border-b border-border ${pending ? "opacity-70" : ""}`}>
      {elenco.map((t) => (
        <button
          key={t.key}
          disabled={pending}
          onClick={() => setTab(t.key)}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors disabled:opacity-60 ${
            active === t.key
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
