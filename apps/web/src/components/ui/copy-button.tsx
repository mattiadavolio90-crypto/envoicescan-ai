"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "sonner";

// «Copia» di un testo pronto da incollare altrove (la bozza al fornitore in
// Osservatorio → Score, il link per un sotto-utente quando l'email non parte).
// Nessun invio.
export function CopyButton({ testo }: { testo: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(testo);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Copia non riuscita");
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
    >
      {copied ? <Check className="size-3.5 text-positivo" /> : <Copy className="size-3.5" />}
      {copied ? "Copiato" : "Copia"}
    </button>
  );
}
