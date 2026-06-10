"use client";

import { useTransition, useState, useEffect } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";

const LAYERS = [
  { key: "tutto", label: "Tutto" },
  { key: "appuntamenti", label: "Appuntamenti" },
  { key: "spese", label: "Spese" },
  { key: "personale", label: "Personale" },
];

function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function LayerSwitcher({ active }: { active: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  // Contatori "oggi" per i layer operativi quotidiani.
  const [oggi, setOggi] = useState<{ appuntamenti: number; personale: number }>({ appuntamenti: 0, personale: 0 });

  useEffect(() => {
    const t = todayISO();
    const mese = t.slice(0, 7);
    (async () => {
      try {
        const [ev, tu] = await Promise.allSettled([
          fetch(`/api/workspace/diario?mese=${mese}`).then(r => r.json()),
          fetch(`/api/workspace/personale?da=${t}&a=${t}`).then(r => r.json()),
        ]);
        const appuntamenti = ev.status === "fulfilled"
          ? (ev.value?.eventi ?? []).filter((e: { data_evento: string }) => e.data_evento === t).length
          : 0;
        const personale = tu.status === "fulfilled" ? (tu.value?.turni ?? []).length : 0;
        setOggi({ appuntamenti, personale });
      } catch { /* badge non critici */ }
    })();
  }, []);

  function setLayer(key: string) {
    const params = new URLSearchParams(sp.toString());
    params.set("layer", key);
    startTransition(() => router.push(`${pathname}?${params.toString()}`));
  }

  function badge(key: string): number {
    if (key === "appuntamenti") return oggi.appuntamenti;
    if (key === "personale") return oggi.personale;
    return 0;
  }

  return (
    <div className={`flex gap-1 border-b border-border ${pending ? "opacity-70" : ""}`}>
      {LAYERS.map((l) => {
        const n = badge(l.key);
        return (
          <button
            key={l.key}
            disabled={pending}
            onClick={() => setLayer(l.key)}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors disabled:opacity-60 ${
              active === l.key
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            {l.label}
            {n > 0 && (
              <span className="inline-flex min-w-4 items-center justify-center rounded-full bg-primary/15 px-1 text-[10px] font-bold text-primary" title="Oggi">
                {n}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
