import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { PageHeader } from "@/components/ui/page-header";
import { AccountClient } from "./account-client";

async function workerGetJson(path: string, token: string) {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    const res = await fetch(`${WORKER_URL}${path}`, { headers, cache: "no-store" });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function ImpostazioniPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";
  const [data, sediRes] = await Promise.all([
    workerGetJson("/api/account/me", token),
    workerGetJson("/api/account/sedi", token),
  ]);

  if (!data) {
    return (
      <div className="space-y-4">
        <PageHeader icon="settings" title="Account" hint="I tuoi dati e le preferenze" />
        <p className="text-muted-foreground text-sm">Impossibile caricare i dati. Riprova più tardi.</p>
      </div>
    );
  }

  // In contesto catena (account multi-sede in modalità "chain") la pagina parla del
  // GRUPPO, non della sede attiva: i dati per-sede (piano, fatture) si vedono
  // scendendo nel punto vendita. La modalità è nel cookie impostato dalla sidebar.
  const sedi = (sediRes?.sedi ?? []) as {
    id: string;
    nome: string;
    indirizzo: string | null;
    comune: string | null;
    attiva: boolean;
  }[];
  const nomeGruppo = (sediRes?.nome_gruppo as string | null) ?? null;
  const viewMode = cookieStore.get("oneflux_view")?.value;
  const chain = sedi.length > 1 && viewMode !== "pv";

  return (
    <div className="space-y-6">
      <PageHeader
        icon="settings"
        title={chain ? "Account del gruppo" : "Account"}
        hint={chain ? "Dati del gruppo e preferenze" : "I tuoi dati e le preferenze"}
      />
      <AccountClient data={data} chain={chain} nomeGruppo={nomeGruppo} sedi={sedi} />
    </div>
  );
}
