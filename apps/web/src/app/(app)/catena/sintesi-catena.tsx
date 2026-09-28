"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { Receipt, ChevronRight, ArrowRight, TriangleAlert } from "lucide-react";
import {
  type GruppoOverview,
  type GruppoBriefing,
  type SalutePV,
  type RankingPV,
} from "@/lib/gruppo";
import { cn } from "@/lib/utils";
import { formatEuro as euro, formatPct } from "@/lib/format";
import {
  messaggioFattureDaCollocare,
  metricaPrincipaleConti,
  tintConti,
} from "@/lib/catena-confronti";
import { LINK_ANALISI_MARGINI, LINK_ANALISI_SPESA } from "@/lib/catena-schede";
import { cambiaSedeEAttendi } from "@/lib/cambia-sede";
import { RiquadroAssistente } from "@/components/home/riquadro-assistente";
import { TestataHome } from "@/components/home/testata-home";
import {
  AndamentoMargine,
  CardHome,
  EtichettaKpi,
  RiepilogoCompletezza,
  TesseraVoce,
} from "@/components/home/card-home";
import { DaFareCatena } from "./da-fare-catena";
import { NotificheWidget } from "../dashboard/notifiche-widget";
import { ConfigAssistenteCatena } from "./config-assistente-catena";
import { ETICHETTA_INCOMPLETO, SALUTE_TINT } from "@/lib/salute-tint";

function pct(n: number | null): string {
  return n == null ? "—" : formatPct(n);
}

// Palette per stato salute/colore: la STESSA della Home PV (lib/salute-tint),
// non una copia — le due erano già divergenti sul tema scuro (9/9/2026).
const TINT = SALUTE_TINT;

type ColoreTint = keyof typeof TINT;

// ─── Briefing di gruppo: lo stesso riquadro della Home del punto vendita ────
function BriefingGruppo({ briefing, nomeGruppo }: { briefing: GruppoBriefing; nomeGruppo: string }) {
  // Le fatture da collocare sono una voce del «Da fare» qui sotto (28/9/2026).
  // Nell'audio restano: e' l'unica azione di gruppo del giorno, e chi ascolta
  // non vede la lista.
  const msgDaCollocare = messaggioFattureDaCollocare(briefing);
  return (
    <RiquadroAssistente
      etichetta="Il tuo assistente · catena"
      saluto={`${briefing.saluto}, ${nomeGruppo}`}
      narrativa={briefing.narrativa}
      testoAscolta={[`${briefing.saluto}, ${nomeGruppo}.`, briefing.narrativa, msgDaCollocare]
        .filter(Boolean)
        .join(" ")}
    />
  );
}

// ─── Card "I conti del gruppo": stessi pezzi della Home PV (card-home) ─────

// Stato senza numeri (errore di lettura, dati assenti): la stessa card, piccola.
function ContiSenzaNumeri({
  periodo,
  icona,
  titolo,
  testo,
  tono,
  riprova = false,
}: {
  periodo: string;
  icona: React.ReactNode;
  titolo: string;
  testo: string;
  tono: "negativo" | "incerto";
  riprova?: boolean;
}) {
  return (
    <CardHome titolo="I conti del gruppo" meta={periodo}>
      <div className="flex items-start gap-3">
        <div className={cn("rounded-full p-2", tono === "negativo" ? "bg-negativo/10 text-negativo" : "bg-incerto/10 text-incerto")}>
          {icona}
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-sm font-semibold">{titolo}</p>
          <p className="text-sm text-muted-foreground">{testo}</p>
          {riprova && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="w-fit text-xs font-medium text-primary-text transition-colors hover:underline"
            >
              Riprova
            </button>
          )}
        </div>
      </div>
    </CardHome>
  );
}

function ContiGruppoCard({
  overview,
  onApriSpesa,
  onApriMargini,
}: {
  overview: GruppoOverview;
  onApriSpesa: () => void;
  onApriMargini: () => void;
}) {
  const { kpi } = overview;
  // La scelta del ramo e il testo dell'avviso vengono dalla funzione pura in
  // lib/catena-confronti.ts (condivisa con /m, e testabile — questo .tsx no).
  // Il default prudente sul campo assente sta li', insieme a quello di tintConti.
  const metrica = metricaPrincipaleConti(kpi);
  // A cascata: con dati incompleti il MOL e' falso -> numero giallo, mai verde.
  const tint = TINT[tintConti(kpi)];
  const affidabile = metrica.stato === "mol" && metrica.affidabile;
  const avviso = metrica.stato === "mol" ? metrica.avviso : null;

  // Livello "non determinabile": la completezza non e' stata letta. Non si mostra
  // NESSUN numero come se fosse valido — ne' il MOL ne' il food cost: entrambi
  // dipendono da dati che non sappiamo se ci siano. Si dice che non si sa e si
  // offre il retry, come fa il PV con BlockRetry.
  if (metrica.stato === "errore") {
    return (
      <ContiSenzaNumeri
        periodo={overview.periodo_label}
        icona={<TriangleAlert className="size-5" />}
        titolo="Conti del gruppo non disponibili"
        testo="Non è stato possibile leggere i dati dei punti vendita: i numeri del gruppo non sono affidabili in questo momento."
        tono="negativo"
        riprova
      />
    );
  }

  // Livello "nessuno": niente numeri, si indirizza a completare i PV.
  if (metrica.stato === "vuoto") {
    return (
      <ContiSenzaNumeri
        periodo={overview.periodo_label}
        icona={<Receipt className="size-5" />}
        titolo="Dati ancora incompleti"
        testo="Mancano fatturato e costi nei punti vendita: completa i dati per leggere food cost e margini del gruppo."
        tono="incerto"
      />
    );
  }

  return (
    <CardHome titolo="I conti del gruppo" meta={overview.periodo_label}>
      {/* MOL del gruppo → scheda Margini e coperti di Analisi catena. SEMPRE, anche con
          dati di costo incompleti (9/9/2026): il PV lo mostra sempre, e qui
          nasconderlo dietro il food cost faceva sembrare le due viste due
          prodotti diversi. Quando non e' reale lo dice l'avviso sotto, non il
          silenzio; il colore lo decide tintConti (giallo finche' non e' reale).
          L'andamento segue il MOL: se il numero si vede, si vede la sua curva. */}
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <button
          type="button"
          onClick={onApriMargini}
          className="flex min-w-0 flex-col items-start gap-1 rounded-md text-left hover:opacity-80"
        >
          <EtichettaKpi>MOL del gruppo</EtichettaKpi>
          <span className={cn("text-2xl font-bold leading-tight tabular-nums", tint.text)}>{euro(kpi.mol)}</span>
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            {/* margine_medio_perc e' Σmol/Σnetto (gruppo.py:76): lo STESSO numero
                gonfiato, in percentuale. Un numero falso con l'avviso e' la
                decisione; due sarebbero rumore. Solo quando il MOL e' reale. */}
            {affidabile && <span className="tabular-nums">margine {pct(kpi.margine_medio_perc)}</span>}
            <span className="inline-flex items-center gap-0.5 font-medium text-primary-text">
              confronta i PV <ArrowRight className="size-3" />
            </span>
          </span>
        </button>
        <AndamentoMargine punti={overview.mol_mensile} anno={overview.mol_mensile_anno} affidabile={affidabile} />
      </div>

      {/* Dati di costo incompleti: il MOL sopra e' gonfiato verso l'alto (mancano
          costi). Lo si dice chiaro — il banner ambra del PV per le fatture
          mancanti fa lo stesso — e si porta a vedere QUALI PV: la scheda
          Margini e Coperti li marca come "Incompleto". */}
      {avviso && (
        <button
          type="button"
          onClick={onApriMargini}
          className="flex items-start gap-2 rounded-lg border border-incerto/30 bg-incerto/10 px-3 py-2 text-left text-xs text-incerto transition-colors hover:border-incerto/60"
        >
          <TriangleAlert className="mt-px size-3.5 shrink-0" />
          <span>
            {avviso}. <span className="font-medium">Vedi quali PV →</span>
          </span>
        </button>
      )}

      {/* Fatturato e Food cost sempre (il food cost UNA volta). Personale/Spese
          solo con costi completi.
          DIVERGENZA DELIBERATA dal PV (9/9/2026): KpiBlock con `costi_mancanti`
          mostra il MOL E tutte le voci, Personale e Spese incluse. Qui no:
          li' i costi mancano a UNA sede e le voci sono comunque i suoi numeri;
          qui una somma di gruppo a cui manca il personale di 2 PV su 4,
          etichettata "Costo personale", sarebbe un secondo numero falso sotto
          il primo — e senza un avviso suo. Scelta di prodotto, non un bug: se
          si vuole il dettaglio parziale, serve anche il suo caveat. */}
      <div className="grid grid-cols-2 gap-2">
        <TesseraVoce label="Fatturato (IVA incl.)" valore={euro(kpi.fatturato)} onClick={onApriMargini} />
        <TesseraVoce
          label="Food cost"
          segno="−"
          valore={kpi.food_cost_pct != null ? pct(kpi.food_cost_pct) : "—"}
          onClick={onApriSpesa}
        />
        {affidabile && (
          <>
            <TesseraVoce label="Costo personale" segno="−" valore={euro(kpi.costo_personale)} onClick={onApriMargini} />
            <TesseraVoce label="Spese generali" segno="−" valore={euro(kpi.spese_generali)} onClick={onApriMargini} />
          </>
        )}
      </div>
    </CardHome>
  );
}

// ─── Card "Completezza dati e margini per sede" ────────────────────────────
function SaluteGruppoCard({
  indice,
  colore,
  salutePv,
  ranking,
  onApriPV,
  switching,
}: {
  indice: number | null;
  colore: ColoreTint;
  salutePv: SalutePV[];
  ranking: RankingPV[];
  onApriPV: (id: string) => void;
  switching: boolean;
}) {
  // Margine% e fatturato per PV (dal ranking) → mostrati accanto all'indice di salute,
  // così questa card assorbe il vecchio "Ranking punti vendita" (una lista di PV sola).
  const rankById = new Map(ranking.map((r) => [r.ristorante_id, r]));
  return (
    <CardHome titolo="Completezza dati e margini per sede">
      <RiepilogoCompletezza
        indice={indice}
        colore={colore}
        nota={`media di ${salutePv.length} ${salutePv.length === 1 ? "sede" : "sedi"}`}
      />
      <ul className="divide-y divide-border">
        {salutePv.map((pv) => {
          const t = TINT[pv.colore];
          const r = rankById.get(pv.ristorante_id);
          return (
            <li key={pv.ristorante_id}>
              <button
                type="button"
                disabled={switching}
                onClick={() => onApriPV(pv.ristorante_id)}
                className="flex w-full items-center gap-3 rounded-md px-1 py-1.5 text-left text-sm transition-colors hover:bg-muted/60 disabled:opacity-50"
              >
                <span className={cn("size-2 shrink-0 rounded-full", t.dot)} />
                {/* min-w, non solo flex-1: fino al 16/09/2026 il nome era l'UNICO
                    elemento della riga senza shrink-0. A 1140px (un portatile)
                    l'unico che poteva cedere era lui, e truncate lo portava a
                    larghezza ZERO: la riga non diceva di quale sede. Il nome e'
                    il dato, non l'accessorio. */}
                <span className="min-w-[7ch] flex-1 truncate" title={pv.nome}>{pv.nome}</span>
                {r?.dati_incompleti ? (
                  // Dati incompleti: l'indice sotto è inaffidabile (calcolato su dati
                  // parziali), quindi NON lo affianchiamo a un margine% che darebbe
                  // l'illusione di due numeri attendibili. Il dettaglio di cosa manca
                  // vive nel «Da fare» — un solo posto per quell'info.
                  <span className="min-w-0 truncate text-xs text-muted-foreground">{ETICHETTA_INCOMPLETO}</span>
                ) : r && r.margine_perc != null ? (
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    margine {pct(r.margine_perc)}
                  </span>
                ) : null}
                {/* L'unita' sta sul numero: nudo (0, 25, 49) sembrava euro o un voto. */}
                <span
                  className={cn(
                    "w-11 text-right text-sm font-semibold tabular-nums",
                    r?.dati_incompleti ? "text-muted-foreground/60" : t.text,
                  )}
                >
                  {pv.indice != null ? `${pv.indice}%` : "—"}
                </span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground/60" />
              </button>
            </li>
          );
        })}
      </ul>
    </CardHome>
  );
}

// Home della catena (28/9/2026): recap e assistenza. Coda da collocare e costi
// di gruppo stanno in Gestione Fatture, i confronti fra sedi in Analisi catena.
export function SintesiCatena({ overview }: { overview: GruppoOverview }) {
  const router = useRouter();
  const [switching, setSwitching] = useState(false);

  // Deep link catena→PV: cambia la sede attiva e naviga alla pagina giusta del PV
  // (default Home). Il "fare" è nel PV; la catena indirizza.
  async function vaiAlPV(ristoranteId: string, page = "/dashboard") {
    if (switching) return;
    setSwitching(true);
    try {
      // Attende che il cambio sia visibile ai processi worker prima di navigare:
      // scendere subito faceva renderizzare il PV con la sede ancora vecchia, e per
      // i PV di catena le righe ripartite non comparivano affatto.
      const confermato = await cambiaSedeEAttendi(ristoranteId);
      router.push(page);
      if (!confermato) toast.message("Punto vendita in apertura, un attimo…");
    } catch {
      toast.error("Impossibile aprire il punto vendita");
      setSwitching(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Stessi blocchi, nello stesso ordine, della Home del punto vendita:
          testata · assistente · Da fare · card. Lo switch PV e' nella sidebar.
          «Carica fatture» non c'e': sta in Analisi Fatture del punto vendita. */}
      <TestataHome
        vista="catena"
        nome={`Gruppo ${overview.nome_gruppo}`}
        dettaglio={`${overview.num_pv} punti vendita`}
        azioni={<ConfigAssistenteCatena />}
      />

      <section className="space-y-5">
        <BriefingGruppo briefing={overview.briefing} nomeGruppo={overview.nome_gruppo} />
        <DaFareCatena
          nDaCollocare={overview.briefing?.n_fatture_da_collocare}
          vaiAlPV={vaiAlPV}
          switching={switching}
        />
      </section>

      {/* Avvisi, come nel punto vendita: un pulsante che apre l'elenco. In
          catena sono quelli di tutte le sedi, ognuno col nome della sua. Senza
          wrapper: senza avvisi il widget non rende niente, e un div vuoto
          lascerebbe un buco nella spaziatura. */}
      <NotificheWidget ambito="gruppo" onVaiSede={(id, pagina) => vaiAlPV(id, pagina)} />

      {/* Le due card della Home PV, nello stesso ordine: conti e completezza. */}
      <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
        <ContiGruppoCard
          overview={overview}
          onApriSpesa={() => router.push(LINK_ANALISI_SPESA)}
          onApriMargini={() => router.push(LINK_ANALISI_MARGINI)}
        />
        <SaluteGruppoCard
          indice={overview.salute_indice}
          colore={overview.salute_colore}
          salutePv={overview.salute_pv}
          ranking={overview.ranking}
          onApriPV={(id) => vaiAlPV(id)}
          switching={switching}
        />
      </div>

      {/* Spazio riservato in fondo: il FAB "Chiedi a ONEFLUX" (fixed bottom-right)
          altrimenti resta sovrapposto all'ultimo contenuto durante lo scroll. */}
      <div aria-hidden className="h-20" />
    </div>
  );
}
