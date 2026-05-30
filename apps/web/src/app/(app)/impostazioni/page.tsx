import { getCurrentUser } from "@/lib/auth";
import { redirect } from "next/navigation";
import { AccountClient } from "./account-client";

const WORKER_URL =
  process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

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

export default async function ImpostazioniPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const data = await fetchAccountData(token);

  if (!data) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold tracking-tight">Account</h1>
        <p className="text-muted-foreground text-sm">Impossibile caricare i dati. Riprova più tardi.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Account</h1>
      <AccountClient data={data} />
    </div>
  );
}
