"use client";

import { useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

const TABS = [
  { key: "articoli", label: "Articoli" },
  { key: "categorie", label: "Categorie" },
  { key: "fornitori", label: "Fornitori" },
];

export function TabsSwitcher({ active }: { active: string }) {
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
      {TABS.map((t) => (
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
