import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import Link from "next/link";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { ClientiClient } from "./clienti-client";
import type { Cliente } from "@/lib/admin";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function fetchClienti(token: string): Promise<Cliente[]> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/clienti`, { headers: h, cache: "no-store" });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function AdminClientiPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const clienti = await fetchClienti(token);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/admin" />}>
          <ChevronLeft className="size-4 mr-1" /> Admin
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Clienti</h1>
      </div>
      <ClientiClient clientiIniziali={clienti} />
    </div>
  );
}
