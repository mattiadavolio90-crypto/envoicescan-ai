import { redirect } from "next/navigation";
import Link from "next/link";
import { cookies } from "next/headers";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { type MarketplaceLeadList } from "@/lib/assistenza";
import { RichiesteClient } from "./richieste-client";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

async function fetchLeads(token: string): Promise<MarketplaceLeadList | null> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/marketplace/leads`, { headers: h, cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as MarketplaceLeadList;
  } catch {
    return null;
  }
}

export default async function RichiestePage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const data = await fetchLeads(token);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/admin" />}>
          <ChevronLeft className="size-4 mr-1" /> Admin
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Richieste servizi</h1>
      </div>

      <RichiesteClient initial={data?.leads ?? []} />
    </div>
  );
}
