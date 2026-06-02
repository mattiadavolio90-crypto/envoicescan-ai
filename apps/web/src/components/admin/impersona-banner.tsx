"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

export function ImpersonaBanner() {
  const router = useRouter();
  const [targetEmail, setTargetEmail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/admin/impersona/status")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data?.active) setTargetEmail(data.email ?? "cliente");
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  if (!targetEmail) return null;

  async function handleExit() {
    try {
      await fetch("/api/admin/impersona/exit", { method: "POST" });
      toast.success("Impersonazione terminata");
      router.push("/admin/clienti");
      router.refresh();
    } catch {
      toast.error("Errore nell'uscita dall'impersonazione");
    }
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between bg-amber-500 px-4 py-2 text-sm font-medium text-amber-950">
      <span>
        Stai vedendo l&apos;app come <strong>{targetEmail}</strong>
      </span>
      <button
        onClick={handleExit}
        className="ml-4 rounded bg-amber-950/15 px-3 py-1 text-xs font-semibold hover:bg-amber-950/25 transition-colors"
      >
        Esci
      </button>
    </div>
  );
}
