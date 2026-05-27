import { Suspense } from "react";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { TabsSwitcher } from "./tabs-switcher";
import { VariazioniTab } from "./variazioni-tab";
import { ScontiTab } from "./sconti-tab";
import { NcTab } from "./nc-tab";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

async function fetchSogliaAlert(): Promise<number> {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return 5;
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/prezzi/soglia-alert`, {
      headers: h,
      cache: "no-store",
    });
    if (!res.ok) return 5;
    const data = await res.json();
    return data.soglia ?? 5;
  } catch {
    return 5;
  }
}

export default async function PrezziPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string }>;
}) {
  const sp = await searchParams;
  const tab = sp.tab ?? "variazioni";
  const soglia = await fetchSogliaAlert();

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Controllo Prezzi</h1>
      <Suspense>
        <TabsSwitcher active={tab} />
      </Suspense>
      <div className="mt-2">
        {tab === "variazioni" && (
          <Suspense>
            <VariazioniTab initialSoglia={soglia} />
          </Suspense>
        )}
        {tab === "sconti" && (
          <Suspense>
            <ScontiTab />
          </Suspense>
        )}
        {tab === "nc" && (
          <Suspense>
            <NcTab />
          </Suspense>
        )}
      </div>
    </div>
  );
}
