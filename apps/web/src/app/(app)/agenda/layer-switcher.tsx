"use client";

import { useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

const LAYERS = [
  { key: "tutto", label: "Tutto" },
  { key: "appuntamenti", label: "Appuntamenti" },
  { key: "spese", label: "Spese" },
  { key: "personale", label: "Personale" },
];

export function LayerSwitcher({ active }: { active: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  function setLayer(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("layer", key);
    startTransition(() => router.push(`${pathname}?${params.toString()}`));
  }

  return (
    <div className={`flex gap-1 border-b border-border ${pending ? "opacity-70" : ""}`}>
      {LAYERS.map((l) => (
        <button
          key={l.key}
          disabled={pending}
          onClick={() => setLayer(l.key)}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors disabled:opacity-60 ${
            active === l.key
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          {l.label}
        </button>
      ))}
    </div>
  );
}
