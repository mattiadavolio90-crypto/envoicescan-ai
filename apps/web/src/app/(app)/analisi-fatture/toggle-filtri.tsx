"use client";

import { useTransition } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { AlertTriangle, Sparkles } from "lucide-react";

export function ToggleFiltri({
  soloNuovi,
  soloVerifica,
}: {
  soloNuovi: boolean;
  soloVerifica: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const [pending, startTransition] = useTransition();

  function set(key: string, on: boolean) {
    const params = new URLSearchParams(sp.toString());
    if (on) params.set(key, "1");
    else params.delete(key);
    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
    });
  }

  return (
    <div className={`flex items-center gap-4 ${pending ? "opacity-70" : ""}`}>
      <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={soloNuovi}
          onChange={(e) => set("nuovi", e.target.checked)}
        />
        <Sparkles className="size-3.5 text-amber-500" /> Nuovi caricati
      </label>
      <label className="text-xs inline-flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={soloVerifica}
          onChange={(e) => set("verifica", e.target.checked)}
        />
        <AlertTriangle className="size-3.5 text-amber-500" /> Solo verifica categoria
      </label>
    </div>
  );
}
