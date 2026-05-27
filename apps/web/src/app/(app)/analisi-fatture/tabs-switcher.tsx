"use client";

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

  function setTab(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("tab", key);
    // pulisco filtri specifici di un tab quando cambio
    params.delete("nuovi");
    params.delete("verifica");
    router.push(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex gap-1 border-b border-border">
      {TABS.map((t) => (
        <button
          key={t.key}
          onClick={() => setTab(t.key)}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
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
