import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { AccountClient } from "@/app/(app)/impostazioni/account-client";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

async function fetchAccountData(token: string) {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;
  const res = await fetch(`${WORKER_URL}/api/account/me`, { headers, cache: "no-store" });
  if (!res.ok) return null;
  return res.json();
}

// Impostazioni dentro la PWA mobile: riusa AccountClient (gia' responsive,
// nessun link verso la vista desktop) sotto il layout mobile con bottom nav.
export default async function MobileImpostazioniPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const data = await fetchAccountData(token);

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold tracking-tight">Account</h1>
      {data ? (
        <AccountClient data={data} />
      ) : (
        <p className="text-sm text-muted-foreground">
          Impossibile caricare i dati. Riprova più tardi.
        </p>
      )}
    </div>
  );
}
