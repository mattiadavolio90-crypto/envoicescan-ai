import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { getCurrentUser, SESSION_COOKIE } from "@/lib/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Users, CheckCircle, DollarSign, ChevronRight, Brain, Settings, Map, LifeBuoy } from "lucide-react";
import Link from "next/link";
import { FattureMensiliCard } from "./fatture-mensili-card";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

async function fetchOverview(token: string): Promise<{ data: Record<string, unknown> | null; error: string | null }> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/overview`, { headers: h, cache: "no-store" });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      console.error(`[admin/overview] ${res.status}:`, body.slice(0, 300));
      return { data: null, error: `Worker ${res.status}: ${body.slice(0, 150)}` };
    }
    return { data: await res.json(), error: null };
  } catch (err) {
    console.error("[admin/overview] fetch error:", err);
    return { data: null, error: String(err) };
  }
}

async function fetchRicaviProblemi(token: string): Promise<number> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}/api/admin/sistema/ricavi-salute`, { headers: h, cache: "no-store" });
    if (!res.ok) return 0;
    const data = await res.json();
    const counts = (data?.counts as Record<string, number>) ?? {};
    return (counts.critico ?? 0) + (counts.warning ?? 0);
  } catch (err) {
    console.error("[admin/ricavi-salute] fetch error:", err);
    return 0;
  }
}

const NAV_CARDS = [
  {
    href: "/admin/clienti",
    title: "Clienti",
    desc: "Lista, crea, impersona, gestisci",
    icon: Users,
    border: "border-sky-500",
    bg: "hover:bg-sky-500/8",
    iconColor: "text-sky-500",
  },
  {
    href: "/admin/categorie",
    title: "Categorie",
    desc: "Coda revisione, suggerimenti AI, memoria",
    icon: Brain,
    border: "border-violet-500",
    bg: "hover:bg-violet-500/8",
    iconColor: "text-violet-500",
  },
  {
    href: "/admin/sistema",
    title: "Sistema & Salute",
    desc: "Costi, retention, import ricavi",
    icon: Settings,
    border: "border-emerald-500",
    bg: "hover:bg-emerald-500/8",
    iconColor: "text-emerald-500",
  },
  {
    href: "/admin/flusso-dati",
    title: "Flusso dati",
    desc: "Fatture Invoicetronic, ricavi, mapping",
    icon: Map,
    border: "border-orange-500",
    bg: "hover:bg-orange-500/8",
    iconColor: "text-orange-500",
  },
  {
    href: "/admin/richieste",
    title: "Richieste servizi",
    desc: "Coda lead dal marketplace Assistenza",
    icon: LifeBuoy,
    border: "border-pink-500",
    bg: "hover:bg-pink-500/8",
    iconColor: "text-pink-500",
  },
];

export default async function AdminPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");

  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? "";
  const [{ data: overview, error: overviewError }, ricaviProblemi] = await Promise.all([
    fetchOverview(token),
    fetchRicaviProblemi(token),
  ]);
  const overviewSubErrors = (overview?._errors as string[] | undefined) ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Pannello Admin</h1>
        {overviewError && (
          <p className="text-xs text-amber-500 max-w-xs truncate" title={overviewError}>
            Worker: {overviewError}
          </p>
        )}
      </div>

      {overviewSubErrors.length > 0 && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 space-y-1">
          <p className="font-medium">Alcuni dati non sono stati calcolati (i KPI relativi possono mostrare 0):</p>
          <ul className="list-disc list-inside">
            {overviewSubErrors.map((e, i) => <li key={i} className="truncate" title={e}>{e}</li>)}
          </ul>
        </div>
      )}

      {/* KPI cards — bordo blu uniforme */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="ring-1 ring-sky-500/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Clienti totali</CardTitle>
            <Users className="size-4 text-sky-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">{overview?.n_clienti != null ? String(overview.n_clienti) : "—"}</div>
          </CardContent>
        </Card>

        <Card className="ring-1 ring-sky-500/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Account attivi</CardTitle>
            <CheckCircle className="size-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">{overview?.n_attivi != null ? String(overview.n_attivi) : "—"}</div>
          </CardContent>
        </Card>

        <FattureMensiliCard
          label="Fatture questo mese"
          value={overview?.fatture_mese != null ? String(overview.fatture_mese) : "—"}
          fattureMese={Number(overview?.fatture_mese ?? 0)}
          fattureMensili={(overview?.fatture_per_mese as { mese: string; count: number }[]) ?? []}
        />

        <Card className="ring-1 ring-sky-500/60">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Costi AI (30gg)</CardTitle>
            <DollarSign className="size-4 text-violet-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold tabular-nums">
              {overview ? `$${Number(overview.costi_ai_mese).toFixed(4)}` : "—"}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Navigation cards — 4 colori */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {NAV_CARDS.map((item) => {
          const alert = item.href === "/admin/sistema" && ricaviProblemi > 0 ? ricaviProblemi : 0;
          return (
            <Card key={item.href} className={`border ${alert ? "border-red-500 ring-1 ring-red-500/40" : item.border} ${item.bg} transition-colors`}>
              <Link href={item.href} className="block p-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <item.icon className={`size-5 ${alert ? "text-red-500" : item.iconColor} shrink-0`} />
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-semibold">{item.title}</p>
                        {alert > 0 && (
                          <span className="rounded-full bg-red-500/15 border border-red-500/30 px-2 py-0.5 text-xs font-medium text-red-600">
                            {alert} import ricavi
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground mt-0.5">{item.desc}</p>
                    </div>
                  </div>
                  <ChevronRight className="size-5 text-muted-foreground shrink-0" />
                </div>
              </Link>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
