"use client";

import { useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { TAB_SEZIONI, type TabDef } from "@/lib/tab-flags";
import { Calculator, FlaskConical, Users } from "lucide-react";

// Le icone restano qui: TAB_SEZIONI e' logica pura eseguita da node nei test
// (tests/helpers_ts.py) e non puo' importare componenti React.
const ICONE: Record<string, typeof Calculator> = {
  calcolo: Calculator,
  coperti: Users,
  analisi: FlaskConical,
};

// Le tab sono in @/lib/tab-flags (unica fonte, condivisa col pannello admin).
// `disponibili` arriva gia' filtrato dal server component: qui non si decide
// nulla sui permessi, si rende cio' che il guard ha consentito.
export function TabsSwitcher({ active, disponibili }: { active: string; disponibili?: TabDef[] }) {
  const elenco = disponibili ?? TAB_SEZIONI["margini"];
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  function setTab(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("tab", key);
    startTransition(() => router.push(`${pathname}?${params.toString()}`));
  }

  return (
    <div className={`flex gap-1 border-b border-border ${pending ? "opacity-70" : ""}`}>
      {elenco.map((t) => {
        const Icon = ICONE[t.key];
        const isActive = active === t.key;
        return (
          <button
            key={t.key}
            disabled={pending}
            onClick={() => setTab(t.key)}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors disabled:opacity-60 ${
              isActive
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {Icon && <Icon className="size-3.5" />}
            {t.label}
          </button>
        );
      })}
    </div>
  );
}
