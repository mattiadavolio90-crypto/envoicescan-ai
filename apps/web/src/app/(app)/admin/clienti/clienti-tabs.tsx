"use client";

import { useState } from "react";
import { ClientiClient } from "./clienti-client";
import { CostiAiTab, RetentionTab } from "./sistema-tabs";
import type { Cliente } from "@/lib/admin";

const TABS = ["clienti", "costi", "retention"] as const;
const TAB_LABELS: Record<string, string> = { clienti: "Clienti", costi: "Costi AI", retention: "Retention" };

export function ClientiTabs({ clientiIniziali }: { clientiIniziali: Cliente[] }) {
  const [tab, setTab] = useState<(typeof TABS)[number]>("clienti");
  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b">
        {TABS.map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>
      {tab === "clienti" && <ClientiClient clientiIniziali={clientiIniziali} />}
      {tab === "costi" && <CostiAiTab />}
      {tab === "retention" && <RetentionTab />}
    </div>
  );
}
