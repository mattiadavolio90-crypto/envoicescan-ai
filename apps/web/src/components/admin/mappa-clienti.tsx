"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  Building2, ChevronRight, FileText, Mail, Network, Receipt, ShoppingBag, Store, Users,
} from "lucide-react";
import {
  apertiAllInizio, idConFigli, soloProblemi, type IconaNodo, type NodoMappa, type StatoNodo,
} from "@/lib/admin-mappa";

const ICONE: Record<IconaNodo, React.ComponentType<{ className?: string }>> = {
  rete: Network, catena: Building2, locale: Store, negozio: ShoppingBag,
  sdi: FileText, cassa: Receipt, commercialista: Mail, utenti: Users,
};

const PALLINO: Record<StatoNodo, string> = {
  ok: "bg-emerald-500", oggi: "bg-amber-500", critico: "bg-red-500", spento: "bg-slate-400", ignoto: "bg-slate-300 dark:bg-slate-600",
};

const ETICHETTA: Record<StatoNodo, { testo: string; classe: string }> = {
  ok: { testo: "Tutto a posto", classe: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" },
  oggi: { testo: "Da guardare", classe: "bg-amber-500/10 text-amber-700 dark:text-amber-400" },
  critico: { testo: "Urgente", classe: "bg-red-500/10 text-red-700 dark:text-red-400" },
  spento: { testo: "Non attivo", classe: "bg-muted text-muted-foreground" },
  ignoto: { testo: "Dato non letto", classe: "bg-muted text-muted-foreground" },
};

// Connettori dell'albero orizzontale: un tratto orizzontale per ogni figlio e
// un tratto verticale che li unisce (meta' sopra il primo, meta' sotto l'ultimo).
const FIGLIO =
  "relative flex items-center " +
  "before:absolute before:-left-[18px] before:top-1/2 before:w-[18px] before:border-t-[1.5px] before:border-border before:content-[''] " +
  "after:absolute after:-left-[18px] after:-top-[5px] after:-bottom-[5px] after:border-l-[1.5px] after:border-border after:content-[''] " +
  "first:after:top-1/2 last:after:bottom-1/2 only:after:hidden";

function Legenda() {
  const voci: [StatoNodo, string][] = [["ok", "Tutto a posto"], ["oggi", "Da guardare"], ["critico", "Urgente"], ["spento", "Non attivo"]];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {voci.map(([s, t]) => (
        <span key={s} className="inline-flex items-center gap-1.5"><i className={`size-2.5 rounded-full ${PALLINO[s]}`} />{t}</span>
      ))}
    </div>
  );
}

export function MappaClienti({ radice }: { radice: NodoMappa }) {
  const [aperti, setAperti] = useState<Set<string>>(() => new Set(apertiAllInizio(radice)));
  const [filtro, setFiltro] = useState(false);
  const [sceltoId, setSceltoId] = useState<string>(() => radice.figli.find((f) => f.stato === "critico")?.id ?? radice.id);

  const vista = useMemo(() => (filtro ? soloProblemi(radice) : radice), [filtro, radice]);
  const indice = useMemo(() => {
    const m = new Map<string, NodoMappa>();
    const visita = (n: NodoMappa) => { m.set(n.id, n); n.figli.forEach(visita); };
    visita(radice);
    return m;
  }, [radice]);
  const scelto = indice.get(sceltoId) ?? radice;

  function apriChiudi(id: string) {
    setAperti((prima) => {
      const dopo = new Set(prima);
      if (dopo.has(id)) dopo.delete(id); else dopo.add(id);
      return dopo;
    });
  }

  function ramo(n: NodoMappa): React.ReactNode {
    const Icona = ICONE[n.icona];
    const aperto = aperti.has(n.id);
    const canale = n.tipo === "canale";
    const problema = n.stato === "oggi" || n.stato === "critico";
    return (
      <div className="flex items-center">
        <button
          type="button"
          onClick={() => setSceltoId(n.id)}
          aria-label={`${n.nome}: ${ETICHETTA[n.stato].testo}`}
          className={`relative flex min-w-0 items-center gap-2.5 rounded-lg border bg-card text-left transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-primary ${
            canale ? "border-dashed px-2 py-1" : n.tipo === "radice" ? "px-3.5 py-2.5" : "px-2.5 py-2"
          } ${scelto.id === n.id ? "border-primary ring-3 ring-primary/15" : ""}`}
        >
          <span className={`grid shrink-0 place-items-center rounded-md bg-muted text-muted-foreground ${canale ? "size-6" : "size-8"}`}>
            <Icona className={canale ? "size-3.5" : "size-4"} />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className={`max-w-[220px] truncate ${canale ? "text-xs font-medium" : "text-[13px] font-semibold"}`} title={n.nome}>{n.nome}</span>
            {n.sub && <span className="whitespace-nowrap text-[11px] tabular-nums text-muted-foreground">{n.sub}</span>}
          </span>
          <i className={`absolute -right-1 -top-1 size-2.5 rounded-full ring-2 ring-card ${PALLINO[n.stato]}`} />
        </button>
        {n.figli.length > 0 && (
          <>
            <span className="w-4 shrink-0 border-t-[1.5px] border-border" />
            <button
              type="button"
              onClick={() => apriChiudi(n.id)}
              aria-expanded={aperto}
              aria-label={`${aperto ? "Comprimi" : "Espandi"} ${n.nome}`}
              className={`grid h-6 min-w-6 shrink-0 place-items-center rounded-full border-[1.5px] px-1.5 text-[11px] font-semibold tabular-nums transition-colors ${
                aperto
                  ? "border-primary bg-primary/10 text-primary-text"
                  : problema && n.stato === "critico"
                    ? "border-red-500 text-red-600"
                    : problema
                      ? "border-amber-500 text-amber-700"
                      : "border-border text-muted-foreground"
              }`}
            >
              {aperto ? "−" : n.figli.length}
            </button>
            {aperto && (
              <div className="relative flex flex-col gap-2.5 pl-[34px]">
                {n.figli.map((f) => <div key={f.id} className={FIGLIO}>{ramo(f)}</div>)}
              </div>
            )}
          </>
        )}
      </div>
    );
  }

  const etichetta = ETICHETTA[scelto.stato];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Legenda />
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={filtro ? "default" : "outline"} aria-pressed={filtro} onClick={() => {
            setFiltro((f) => !f);
            if (!filtro) setAperti(new Set(idConFigli(soloProblemi(radice)).filter((id) => indice.get(id)?.tipo !== "sede")));
          }}>
            Solo con problemi
          </Button>
          <Button size="sm" variant="outline" onClick={() => setAperti(new Set(idConFigli(radice)))}>Espandi tutto</Button>
          <Button size="sm" variant="outline" onClick={() => setAperti(new Set([radice.id]))}>Comprimi tutto</Button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border bg-card px-4 py-5">
        <div className="inline-flex min-w-max">{ramo(vista)}</div>
      </div>

      <section className="space-y-2 rounded-xl border bg-card p-4" aria-live="polite">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-base font-semibold">{scelto.nome}</h2>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${etichetta.classe}`}>{etichetta.testo}</span>
        </div>
        {scelto.motivi.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {scelto.motivi.map((m, i) => <li key={i}>{m}</li>)}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Niente da segnalare.</p>
        )}
        {scelto.link && (
          <Button size="sm" nativeButton={false} render={<Link href={scelto.link} />}>
            {scelto.tipo === "radice" ? "Apri Oggi" : "Apri"} <ChevronRight className="ml-0.5 size-4" />
          </Button>
        )}
      </section>
    </div>
  );
}
