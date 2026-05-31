import { fetchDashboardStats } from "@/lib/dashboard";
import { fetchBriefing } from "@/lib/home";
import { HomeBriefing } from "./home-briefing";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Receipt, Package, Euro } from "lucide-react";

const MESI_IT = [
  "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
  "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
];

function fmtEuro(n: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
}

function fmtEuroFull(n: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(n);
}

function meseLabel(yyyymm: string): string {
  const [y, m] = yyyymm.split("-");
  const idx = parseInt(m, 10) - 1;
  return `${MESI_IT[idx] ?? m} ${y.slice(2)}`;
}

function pctDelta(curr: number, prev: number): { value: number; positive: boolean } | null {
  if (prev <= 0) return null;
  const v = ((curr - prev) / prev) * 100;
  return { value: Math.abs(Math.round(v)), positive: v >= 0 };
}

export default async function DashboardPage() {
  const [stats, briefing] = await Promise.all([
    fetchDashboardStats(),
    fetchBriefing(),
  ]);

  if (!stats) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Impossibile caricare i dati. Riprova tra qualche istante.
          </CardContent>
        </Card>
      </div>
    );
  }

  const { kpi, spesa_mensile, top_fornitori, top_categorie } = stats;
  const delta = pctDelta(kpi.spesa_mese_corrente, kpi.spesa_mese_precedente);
  const maxMese = spesa_mensile.reduce((m, p) => Math.max(m, p.spesa), 0);
  const isEmpty = kpi.righe_totali === 0;

  return (
    <div className="space-y-8">
      {briefing ? (
        <HomeBriefing briefing={briefing} />
      ) : (
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Panoramica dei tuoi acquisti — aggiornata in tempo reale
          </p>
        </div>
      )}

      {isEmpty ? (
        <Card>
          <CardContent className="py-16 text-center">
            <Receipt className="mx-auto size-12 text-muted-foreground/40" />
            <p className="mt-4 text-base font-medium">Nessuna fattura registrata</p>
            <p className="text-sm text-muted-foreground mt-1">
              Carica le tue prime fatture dalla sezione Upload per iniziare.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          <h2 className="text-sm font-semibold text-muted-foreground">Panoramica</h2>
          {/* KPI CARDS */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Spesa totale</CardTitle>
                <Euro className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{fmtEuroFull(kpi.spesa_totale)}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  Da {kpi.prima_fattura?.slice(0, 10) ?? "—"}
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Mese corrente</CardTitle>
                {delta ? (
                  delta.positive ? (
                    <TrendingUp className="size-4 text-emerald-600" />
                  ) : (
                    <TrendingDown className="size-4 text-rose-600" />
                  )
                ) : (
                  <Euro className="size-4 text-muted-foreground" />
                )}
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{fmtEuroFull(kpi.spesa_mese_corrente)}</div>
                {delta && (
                  <p className={`text-xs mt-1 ${delta.positive ? "text-emerald-600" : "text-rose-600"}`}>
                    {delta.positive ? "+" : "-"}{delta.value}% vs mese precedente
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Fatture</CardTitle>
                <Receipt className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{kpi.fatture_uniche.toLocaleString("it-IT")}</div>
                <p className="text-xs text-muted-foreground mt-1">Documenti registrati</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                <CardTitle className="text-sm font-medium text-muted-foreground">Prodotti</CardTitle>
                <Package className="size-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{kpi.righe_totali.toLocaleString("it-IT")}</div>
                <p className="text-xs text-muted-foreground mt-1">Righe acquisto totali</p>
              </CardContent>
            </Card>
          </div>

          {/* GRAFICO SPESA MENSILE */}
          <Card>
            <CardHeader>
              <CardTitle>Spesa mensile</CardTitle>
              <CardDescription>Ultimi {spesa_mensile.length} mesi</CardDescription>
            </CardHeader>
            <CardContent>
              {spesa_mensile.length === 0 ? (
                <p className="text-sm text-muted-foreground py-8 text-center">Nessun dato disponibile</p>
              ) : (
                <div className="flex items-end justify-between gap-2 h-56">
                  {spesa_mensile.map((p) => {
                    const heightPct = maxMese > 0 ? (p.spesa / maxMese) * 100 : 0;
                    return (
                      <div key={p.mese} className="flex-1 flex flex-col items-center gap-2 min-w-0">
                        <div className="text-[10px] font-medium text-muted-foreground whitespace-nowrap">
                          {fmtEuro(p.spesa)}
                        </div>
                        <div className="w-full bg-muted rounded-t flex-1 flex items-end">
                          <div
                            className="w-full bg-primary rounded-t transition-all hover:opacity-80"
                            style={{ height: `${heightPct}%`, minHeight: p.spesa > 0 ? "2px" : "0" }}
                            title={`${meseLabel(p.mese)}: ${fmtEuroFull(p.spesa)}`}
                          />
                        </div>
                        <div className="text-xs text-muted-foreground whitespace-nowrap">
                          {meseLabel(p.mese)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* TOP FORNITORI + CATEGORIE */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Top fornitori</CardTitle>
                <CardDescription>I 5 fornitori con più spesa</CardDescription>
              </CardHeader>
              <CardContent>
                <TopList items={top_fornitori} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top categorie</CardTitle>
                <CardDescription>Le 5 categorie di spesa principali</CardDescription>
              </CardHeader>
              <CardContent>
                <TopList items={top_categorie} />
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}

function TopList({ items }: { items: { nome: string; spesa: number; righe: number }[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-4">Nessun dato disponibile</p>;
  }
  const max = items[0]?.spesa ?? 0;
  return (
    <div className="space-y-3">
      {items.map((item, i) => {
        const pct = max > 0 ? (item.spesa / max) * 100 : 0;
        return (
          <div key={`${item.nome}-${i}`} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium truncate flex-1 pr-2">{item.nome}</span>
              <span className="text-muted-foreground tabular-nums">{fmtEuroFull(item.spesa)}</span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
            </div>
            <p className="text-xs text-muted-foreground">{item.righe} righe</p>
          </div>
        );
      })}
    </div>
  );
}
