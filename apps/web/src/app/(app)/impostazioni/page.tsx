import { getCurrentUser } from "@/lib/auth";
import { redirect } from "next/navigation";
import { PageHeader } from "@/components/ui/page-header";
import { AccountClient } from "./account-client";

async function fetchAccountData(token: string) {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  const res = await fetch(`${WORKER_URL}/api/account/me`, {
    headers,
    cache: "no-store",
  });
  if (!res.ok) return null;
  return res.json();
}

import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

export default async function ImpostazioniPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const data = await fetchAccountData(token);

  if (!data) {
    return (
      <div className="space-y-4">
        <PageHeader icon="settings" title="Account" hint="I tuoi dati e le preferenze" />
        <p className="text-muted-foreground text-sm">Impossibile caricare i dati. Riprova più tardi.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader icon="settings" title="Account" hint="I tuoi dati e le preferenze" />
      <AccountClient data={data} />
    </div>
  );
}
