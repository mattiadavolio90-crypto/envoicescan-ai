"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Sparkles, AlertTriangle, ChevronRight, ClipboardList } from "lucide-react";
import { cn } from "@/lib/utils";
import { AscoltaButton } from "@/components/ascolta-button";
import type { GruppoOverview } from "@/lib/gruppo";
import { messaggioFattureDaCollocare, metricaPrincipaleConti } from "@/lib/catena-confronti";
import { SALUTE_TINT, ETICHETTA_INCOMPLETO } from "@/lib/salute-tint";
import { DaFareCatena } from "@/app/(app)/catena/da-fare-catena";

// Punto e testo per colore della Salute: dalla palette unica (lib/salute-tint).
// Qui vivevano la terza e la quarta copia, gia' identiche per caso (9/9/2026).
const DOT: Record<string, string> = Object.fromEntries(
  Object.entries(SALUTE_TINT).map(([k, v]) => [k, v.dot]),
);
const TXT: Record<string, string> = Object.fromEntries(
  Object.entries(SALUTE_TINT).map(([k, v]) => [k, v.text]),
);

function euro(n: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n);
}
function pct(n: number | null): string {
  if (n == null) return "—";
  return `${n.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%`;
}

// Vista catena su mobile (monitoraggio): briefing di gruppo + «Da fare» per punto
// vendita + conti + salute + ranking, tutto impilato. Toccare un PV ci SCENDE:
// cambia sede, passa in modalità PV (cookie) e torna alla home mobile, che
// mostrerà quel locale.
export function MobileCatena({ overview }: { overview: GruppoOverview }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);

  async function drill(id: string) {
    if (switching) return;
    setSwitching(true);
    try {
      const res = await fetch("/api/account/cambia-sede", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ristorante_id: id }),
      });
      if (!res.ok) throw new Error();
      document.cookie = `oneflux_view=pv; path=/; max-age=${60 * 60 * 24 * 30}; samesite=lax${
        window.location.protocol === "https:" ? "; secure" : ""
      }`;
      router.push("/m/briefing");
      router.refresh();
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  const { kpi } = overview;
  const molPos = kpi.mol >= 0;
  // Stessa funzione del desktop (9/9/2026): il MOL e' il numero grande anche con
  // dati di costo incompleti — prima qui, come sul desktop, al suo posto c'era il
  // food cost. /m e' un frontend separato: la scelta del ramo e il testo
  // dell'avviso vengono dalla funzione condivisa, cosi' non possono divergere.
  // Porta anche lo stato "vuoto" (nessun dato), che qui prima non esisteva: si
  // finiva nel ramo food cost con un "—" grande e una frase sul MOL.
  const metrica = metricaPrincipaleConti(kpi);
  const affidabile = metrica.stato === "mol" && metrica.affidabile;
  const avviso = metrica.stato === "mol" ? metrica.avviso : null;
  const nonDeterminabile = metrica.stato === "errore";
  const vuoto = metrica.stato === "vuoto";
  // codaRaggiungibile=false: su /m la coda da assegnare non esiste, quindi il testo
  // rimanda al computer invece che "qui sotto".
  const msgDaCollocare = messaggioFattureDaCollocare(overview.briefing, false);

  return (
    <div className="space-y-4">
      {/* Briefing di gruppo */}
      <div className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-sky-500/10 via-violet-500/[0.05] to-background p-5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-primary/80">
            <Sparkles className="size-3.5" />
            Il tuo assistente · catena
          </div>
          {/* Come sul desktop: l'unica azione del giorno entra nell'audio. */}
          <AscoltaButton
            testo={[
              `${overview.briefing.saluto}, ${overview.nome_gruppo}.`,
              overview.briefing.narrativa,
              msgDaCollocare,
            ]
              .filter(Boolean)
              .join(" ")}
          />
        </div>
        <h1 className="mt-2 text-xl font-bold tracking-tight">
          {overview.briefing.saluto}, {overview.nome_gruppo}
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-foreground/90">{overview.briefing.narrativa}</p>
        {/* Stessa funzione del desktop, con codaRaggiungibile=false: qui la coda da
            assegnare non esiste. Prima questo messaggio era una copia a mano,
            SENZA il ramo che evita il doppio imperativo quando la narrativa ha
            gia' parlato — il vincolo esisteva solo sul desktop. */}
        {msgDaCollocare && (
          <p className="mt-3 flex items-start gap-2 text-sm font-medium text-amber-700 dark:text-amber-500">
            <ClipboardList className="mt-0.5 size-4 shrink-0" />
            <span>{msgDaCollocare}</span>
          </p>
        )}
      </div>

      {/* «Da fare oggi» come nella Home desktop (fase G): un elenco solo, una riga
          per punto vendita con segnali, osservazioni e avvisi. La coda da collocare
          non c'e': su /m non si raggiunge, ne parla il riquadro qui sopra. Toccare
          «Vedi PV» scende nel locale (la pagina del desktop si ignora). */}
      <DaFareCatena nDaCollocare={null} vaiAlPV={(id) => void drill(id)} switching={switching} />

      {/* Conti del gruppo (compatto) — il MOL sempre; ambra finche' non e' reale */}
      <div
        className={cn(
          "rounded-2xl border p-5 text-center",
          nonDeterminabile || vuoto
            ? "bg-card"
            : !affidabile
              ? "bg-gradient-to-br from-amber-500/10 to-background"
              : molPos
                ? "bg-gradient-to-br from-emerald-500/10 to-background"
                : "bg-gradient-to-br from-rose-500/10 to-background",
        )}
      >
        {nonDeterminabile ? (
          <>
            <div className="flex items-center justify-center gap-2 text-sm font-semibold">
              <AlertTriangle className="size-4 text-rose-500" />
              Conti del gruppo non disponibili
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              Non è stato possibile leggere i dati dei punti vendita: i numeri del
              gruppo non sono affidabili in questo momento.
            </p>
          </>
        ) : vuoto ? (
          <>
            <div className="text-sm font-semibold text-amber-700 dark:text-amber-400">Dati ancora incompleti</div>
            <p className="mt-2 text-xs text-muted-foreground">
              Mancano fatturato e costi nei punti vendita: completa i dati per leggere
              food cost e margini del gruppo.
            </p>
          </>
        ) : (
          <>
            <div className="text-xs font-medium uppercase tracking-widest text-muted-foreground/60">
              MOL del gruppo · {overview.periodo_label}
            </div>
            <div className={cn("mt-1 text-4xl font-black tabular-nums", affidabile ? (molPos ? TXT.verde : TXT.rosso) : TXT.giallo)}>
              {euro(kpi.mol)}
            </div>
            {/* margine_medio_perc e' lo stesso MOL in percentuale: solo se reale.
                Con costi incompleti al suo posto c'e' il food cost, che invece
                regge — e cosi' compare UNA volta, non piu' come numero grande. */}
            <div className="mt-1 text-xs text-muted-foreground">
              {affidabile
                ? `margine ${pct(kpi.margine_medio_perc)}`
                : `food cost ${kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}`}
              {" "}· fatturato {euro(kpi.fatturato)}
            </div>
            {avviso && (
              <p className="mt-2 flex items-start justify-center gap-1.5 text-xs text-amber-700 dark:text-amber-400">
                <AlertTriangle className="mt-px size-3.5 shrink-0" />
                <span>{avviso}</span>
              </p>
            )}
            {affidabile && (
              <div className="mt-3 grid grid-cols-3 gap-2 border-t pt-3 text-center">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Food cost</div>
                  <div className="text-sm font-semibold tabular-nums">{pct(kpi.food_cost_pct)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Personale</div>
                  <div className="text-sm font-semibold tabular-nums">{euro(kpi.costo_personale)}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-muted-foreground/60">Spese gen.</div>
                  <div className="text-sm font-semibold tabular-nums">{euro(kpi.spese_generali)}</div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Salute del gruppo */}
      <div className="rounded-2xl border bg-card p-4">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-sm font-semibold">Salute del gruppo</span>
          <span className={cn("text-sm font-bold tabular-nums", TXT[overview.salute_colore])}>
            {overview.salute_indice != null ? `${overview.salute_indice}%` : "—"}
          </span>
        </div>
        <ul className="space-y-1">
          {overview.salute_pv.map((pv) => (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => drill(pv.ristorante_id)}
                className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left active:bg-accent disabled:opacity-50"
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", DOT[pv.colore])} />
                <span className="min-w-0 flex-1 truncate text-sm">{pv.nome}</span>
                <span className={cn("text-sm font-semibold tabular-nums", TXT[pv.colore])}>
                  {pv.indice ?? "—"}
                </span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/40" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      {/* Ranking punti vendita */}
      <div className="rounded-2xl border bg-card">
        <div className="border-b px-4 py-3 text-sm font-semibold">
          Ranking punti vendita
          <span className="ml-2 text-xs font-normal text-muted-foreground">per margine %</span>
        </div>
        <ul className="divide-y">
          {overview.ranking.map((pv) => (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => drill(pv.ristorante_id)}
                className="flex w-full items-center gap-2.5 px-4 py-3 text-left active:bg-accent disabled:opacity-50"
              >
                <span className={cn("size-2.5 shrink-0 rounded-full", DOT[(pv.colore as string) ?? "grigio"])} />
                <span className="min-w-0 flex-1 truncate text-sm font-medium">{pv.nome}</span>
                {pv.dati_incompleti ? (
                  <span className="text-xs text-muted-foreground">{ETICHETTA_INCOMPLETO}</span>
                ) : (
                  <span className={cn("text-sm font-semibold tabular-nums", TXT[(pv.colore as string) ?? "grigio"])}>
                    {pct(pv.margine_perc)}
                  </span>
                )}
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/40" />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
