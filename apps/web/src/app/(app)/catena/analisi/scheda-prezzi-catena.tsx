"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, ChevronDown, Search, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { AREA_TABELLA, PannelloScheda } from "@/components/ui/pannello-scheda";
import { cn } from "@/lib/utils";
import { formatEuro } from "@/lib/format";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";
import { intervalloMese } from "@/lib/periodo";
import type { StoricoPrezzoResponse } from "@/lib/prezzi";
import {
  chiaveStellaCatena,
  etichettaDiffusione,
  filtraDivari,
  filtraVariazioni,
  pvDeiPrezzi,
  sogliaDaApplicare,
  stelleIniziali,
  testoSoglia,
  totaliPrezzi,
  type GruppoPrezzi,
  type VariazionePrezzoCatena,
} from "@/lib/catena-prezzi";
import { SPIEGAZIONE_DA_CONTROLLARE, coppiaPreferito, type VistaPrezzi } from "@/lib/prezzi-viste";

type Lista = "variazioni" | "divari";

function euro2(v: number): string {
  return formatEuro(v, 2);
}

function euroSegno(v: number): string {
  return `${v > 0 ? "+" : ""}${formatEuro(v, 2)}`;
}

function pct(v: number): string {
  const segno = v > 0 ? "+" : "";
  return `${segno}${v.toLocaleString("it-IT", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
}

function dataBreve(s: string): string {
  const d = new Date(s);
  if (!s || isNaN(d.getTime())) return s || "—";
  return d.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit", year: "2-digit" });
}

// Come nell'Osservatorio: il colore sta sull'euro e segue il SEGNO (rosso = costa
// di piu'), la percentuale resta neutra.
function classeImpatto(v: number): string {
  return v > 0 ? "text-negativo" : v < 0 ? "text-positivo" : "text-muted-foreground";
}

function Kpi({ label, valore, sotto, classe }: { label: string; valore: string; sotto?: string; classe?: string }) {
  return (
    <div className="rounded-xl border bg-card px-4 py-3">
      <span className="block text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={cn("block text-xl font-bold tracking-tight", classe)}>{valore}</span>
      {sotto && <span className="block text-[11px] text-muted-foreground">{sotto}</span>}
    </div>
  );
}

function StoricoPv({ storico, loading }: { storico: StoricoPrezzoResponse | null; loading: boolean }) {
  if (loading) return <p className="py-3 text-sm text-muted-foreground">Caricamento acquisti…</p>;
  if (!storico || storico.punti.length === 0) {
    return <p className="py-3 text-sm text-muted-foreground">Nessun acquisto da mostrare nel periodo.</p>;
  }
  const punti = [...storico.punti].reverse();
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-muted-foreground">
          <th className="py-1 pr-3 text-left font-medium">Data</th>
          <th className="py-1 pr-3 text-left font-medium">Documento</th>
          <th className="py-1 pr-3 text-right font-medium">Quantità</th>
          <th className="py-1 text-right font-medium">Prezzo</th>
        </tr>
      </thead>
      <tbody>
        {punti.map((p, i) => (
          <tr key={i} className="border-t border-border/60">
            <td className="py-1 pr-3 tabular-nums">{dataBreve(p.data)}</td>
            <td className="py-1 pr-3">{p.numero_documento || "—"}</td>
            <td className="py-1 pr-3 text-right tabular-nums">
              {p.quantita != null ? p.quantita.toLocaleString("it-IT", { maximumFractionDigits: 3 }) : "—"}
            </td>
            <td className="py-1 text-right font-medium tabular-nums">{euro2(p.prezzo_unitario)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Scheda «Prezzi» di Analisi catena (Mattia, 11/10/2026). Due viste: i rincari di
// ogni punto vendita, con la sede su ogni riga, e lo stesso prodotto pagato
// diverso fra le sedi. Le regole stanno in lib/catena-prezzi.ts.
export function SchedaPrezziCatena() {
  const [periodo, setPeriodo] = useState<string>("anno");
  // null = la soglia degli avvisi dell'account, che il worker usa e rimanda:
  // la casella parte da li', come nell'Osservatorio del PV.
  const [soglia, setSoglia] = useState<number | null>(null);
  const [sogliaInput, setSogliaInput] = useState("");
  const [lista, setLista] = useState<Lista>("variazioni");
  const [mostra, setMostra] = useState<VistaPrezzi>("tutti");
  const [stelle, setStelle] = useState<Set<string>>(new Set());
  const [pv, setPv] = useState("");
  const [ricerca, setRicerca] = useState("");
  const [data, setData] = useState<GruppoPrezzi | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [aperta, setAperta] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  const range = useMemo(
    () =>
      periodo === "anno"
        ? { data_da: `${annoCorrente}-01-01`, data_a: `${annoCorrente}-12-31` }
        : intervalloMese(annoCorrente, Number(periodo)),
    [periodo, annoCorrente],
  );

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    setAperta(null);
    const qs = new URLSearchParams(range);
    if (soglia != null) qs.set("soglia", String(soglia));
    fetch(`/api/gruppo/prezzi?${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j: GruppoPrezzi) => {
        if (my !== reqRef.current) return;
        setData(j);
        setStelle(stelleIniziali(j.variazioni));
        if (soglia == null) setSogliaInput(testoSoglia(j.soglia));
      })
      .catch(() => {
        if (my === reqRef.current) {
          setLoadError(true);
          toast.error("Errore nel caricamento dei prezzi della catena");
        }
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [range, soglia]);

  useEffect(() => {
    carica();
  }, [carica]);

  function applicaSoglia() {
    const esito = sogliaDaApplicare(sogliaInput, soglia ?? data?.soglia ?? null);
    setSogliaInput(esito.testo);
    if (esito.nuova != null) setSoglia(esito.nuova);
  }

  const elencoPv = useMemo(() => pvDeiPrezzi(data), [data]);
  const variazioni = useMemo(
    () => filtraVariazioni(data?.variazioni ?? [], { pv, ricerca, vista: mostra }, stelle),
    [data, pv, ricerca, mostra, stelle],
  );
  const divari = useMemo(() => filtraDivari(data?.divari ?? [], { pv, ricerca, vista: mostra }), [data, pv, ricerca, mostra]);
  const nDaControllare = useMemo(
    () =>
      lista === "variazioni"
        ? filtraVariazioni(data?.variazioni ?? [], { pv, ricerca, vista: "da_controllare" }).length
        : filtraDivari(data?.divari ?? [], { pv, ricerca, vista: "da_controllare" }).length,
    [data, pv, ricerca, lista],
  );
  const nStelle = useMemo(
    () => filtraVariazioni(data?.variazioni ?? [], { pv, ricerca, vista: "preferiti" }, stelle).length,
    [data, pv, ricerca, stelle],
  );
  const totali = totaliPrezzi(variazioni, divari, pv);
  const nomePv = elencoPv.find((p) => p.id === pv)?.nome;

  // Una voce che sparisce dal selettore (nessuna riga da controllare in questo
  // periodo, «Preferiti» nella lista dei divari) riporta su «Tutti»: restarci
  // mostrerebbe una lista vuota senza un perche'.
  useEffect(() => {
    if ((mostra === "da_controllare" && nDaControllare === 0) || (mostra === "preferiti" && lista === "divari")) {
      setMostra("tutti");
    }
  }, [mostra, nDaControllare, lista]);

  // Stella ottimistica, come nell'Osservatorio: subito a video, rollback se il
  // salvataggio non riesce. E' la stella del PV della riga.
  const toggleStella = useCallback(
    async (v: VariazionePrezzoCatena) => {
      const chiave = chiaveStellaCatena(v);
      const era = stelle.has(chiave);
      const cambia = (accesa: boolean) =>
        setStelle((prev) => {
          const next = new Set(prev);
          if (accesa) next.add(chiave);
          else next.delete(chiave);
          return next;
        });
      cambia(!era);
      const corpo = { ristorante_id: v.ristorante_id, ...coppiaPreferito(v) };
      try {
        const res = era
          ? await fetch(`/api/gruppo/prezzi/preferiti?${new URLSearchParams(corpo)}`, { method: "DELETE" })
          : await fetch("/api/gruppo/prezzi/preferiti", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(corpo),
            });
        if (!res.ok) throw new Error();
      } catch {
        cambia(era);
        toast.error("Non sono riuscito ad aggiornare i preferiti");
      }
    },
    [stelle],
  );

  const apriVariazione = useCallback(
    async (v: VariazionePrezzoCatena) => {
      const chiave = chiaveStellaCatena(v);
      if (aperta === chiave) {
        setAperta(null);
        return;
      }
      setAperta(chiave);
      setStorico(null);
      setStoricoLoading(true);
      try {
        const qs = new URLSearchParams({ ristorante_id: v.ristorante_id, prodotto: v.prodotto, fornitore: v.fornitore, ...range });
        const res = await fetch(`/api/gruppo/prezzi/storico?${qs}`, { cache: "no-store" });
        if (!res.ok) throw new Error();
        setStorico(await res.json());
      } catch {
        toast.error("Errore nel caricamento degli acquisti");
      } finally {
        setStoricoLoading(false);
      }
    },
    [aperta, range],
  );

  const vuoto = data != null && data.acquisti_nel_periodo === 0;

  return (
    <PannelloScheda
      titolo="Prezzi dei fornitori nei punti vendita"
      azioni={
        <>
          <NativeSelect value={periodo} onValueChange={setPeriodo} className="h-8 w-48 text-xs" aria-label="Periodo">
            <option value="anno">Anno in corso ({annoCorrente})</option>
            {MESI.slice(0, meseCorrente).map((m, i) => (
              <option key={i + 1} value={String(i + 1)}>
                {m} {annoCorrente}
              </option>
            ))}
          </NativeSelect>
          <NativeSelect value={pv} onValueChange={setPv} className="h-8 w-48 text-xs" aria-label="Punto vendita">
            <option value="">Tutti i punti vendita</option>
            {elencoPv.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </NativeSelect>
          {/* Casella libera come nell'Osservatorio del PV (non una tendina): parte
              dalla soglia degli avvisi e filtra solo questa scheda. */}
          <div className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2">
            <label htmlFor="soglia-prezzi-catena" className="whitespace-nowrap text-xs text-muted-foreground">
              Mostra da
            </label>
            <input
              id="soglia-prezzi-catena"
              type="text"
              inputMode="decimal"
              value={sogliaInput}
              onChange={(e) => setSogliaInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") applicaSoglia();
              }}
              onBlur={applicaSoglia}
              disabled={loading}
              className="w-10 bg-transparent text-right text-xs text-foreground outline-none disabled:opacity-50"
            />
            <span className="whitespace-nowrap text-xs text-muted-foreground">% in su</span>
          </div>
        </>
      }
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SegmentedControl
          aria-label="Lista"
          value={lista}
          onChange={setLista}
          options={[
            { value: "variazioni", label: "Variazioni nei PV" },
            { value: "divari", label: "Stesso prodotto, prezzi diversi" },
          ]}
        />
        <SegmentedControl
          aria-label="Mostra"
          value={mostra}
          onChange={setMostra}
          options={[
            { value: "tutti" as const, label: "Tutti" },
            ...(lista === "variazioni"
              ? [
                  {
                    value: "preferiti" as const,
                    label: (
                      <>
                        <Star className={cn("size-3", mostra === "preferiti" ? "fill-current" : "fill-incerto text-incerto")} />
                        Preferiti{nStelle > 0 ? ` (${nStelle})` : ""}
                      </>
                    ),
                  },
                ]
              : []),
            ...(nDaControllare > 0
              ? [{ value: "da_controllare" as const, label: `Da controllare (${nDaControllare})`, title: SPIEGAZIONE_DA_CONTROLLARE }]
              : []),
          ]}
        />
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={ricerca}
            onChange={(e) => setRicerca(e.target.value)}
            placeholder="Cerca prodotto o fornitore"
            className="h-8 w-64 pl-8 text-xs"
          />
        </div>
      </div>

      {data && !vuoto && mostra === "da_controllare" && (
        <p className="mb-4 rounded-lg border border-border bg-card px-4 py-3 text-sm text-muted-foreground">
          {SPIEGAZIONE_DA_CONTROLLARE}
        </p>
      )}
      {data && !vuoto && mostra !== "da_controllare" && (
        <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
          {lista === "variazioni" ? (
            <>
              <Kpi label="Prezzi aumentati" valore={String(totali.aumenti)} sotto={nomePv ?? "Tutti i punti vendita"} />
              <Kpi label="Prezzi calati" valore={String(totali.cali)} />
              <Kpi
                label="Impatto/mese"
                valore={euroSegno(totali.impattoNetto)}
                classe={classeImpatto(totali.impattoNetto)}
                sotto="Somma degli aumenti e dei cali"
              />
            </>
          ) : (
            <>
              <Kpi label="Prodotti con prezzi diversi" valore={String(totali.divari)} sotto={nomePv ?? "Tutti i punti vendita"} />
              <Kpi
                label="Pagato in più nel periodo"
                valore={euro2(totali.extraDivari)}
                classe={classeImpatto(totali.extraDivari)}
                sotto={nomePv ? `Da ${nomePv}, rispetto al PV che paga meno` : "Rispetto al PV che paga meno"}
              />
            </>
          )}
        </div>
      )}

      <div className={AREA_TABELLA}>
        {loading && !data ? (
          <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
        ) : loadError && !data ? (
          <div className="flex flex-col items-center gap-3 py-16 text-center">
            <AlertTriangle className="size-7 text-negativo" />
            <p className="text-sm text-muted-foreground">Non è stato possibile caricare i dati.</p>
            <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
              Riprova
            </Button>
          </div>
        ) : !data ? null : vuoto ? (
          <div className="py-16 text-center text-sm text-muted-foreground">
            Nessun acquisto nel periodo ({data.periodo_label}).
          </div>
        ) : lista === "variazioni" ? (
          variazioni.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              {mostra === "preferiti"
                ? "Nessun preferito fra le variazioni del periodo. Tocca la stella accanto a un prodotto per seguirlo."
                : `Nessun prezzo cambiato di almeno il ${data.soglia}% nel periodo.`}
            </div>
          ) : (
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead className="sticky top-0 z-30 bg-card shadow-[0_1px_0_0_var(--color-border)]">
                <tr>
                  <th className="w-8" aria-label="Preferito" />
                  <th className="px-3 py-2 text-left font-semibold">Prodotto</th>
                  <th className="px-3 py-2 text-left font-semibold">Punto vendita</th>
                  <th className="px-3 py-2 text-right font-semibold">Prima</th>
                  <th className="px-3 py-2 text-right font-semibold">Ora</th>
                  <th className="px-3 py-2 text-right font-semibold">Variazione</th>
                  <th className="px-3 py-2 text-right font-semibold">Impatto/mese</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {variazioni.map((v) => {
                  const chiave = chiaveStellaCatena(v);
                  const diffusione = etichettaDiffusione(v);
                  const isAperta = aperta === chiave;
                  return (
                    <Fragment key={chiave}>
                      <tr
                        className="cursor-pointer border-t hover:bg-muted/30"
                        onClick={() => apriVariazione(v)}
                        aria-expanded={isAperta}
                      >
                        <td className="pl-3">
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleStella(v);
                            }}
                            aria-label={stelle.has(chiave) ? "Rimuovi dai preferiti" : "Aggiungi ai preferiti"}
                            aria-pressed={stelle.has(chiave)}
                            title={`Preferito di ${v.nome_pv}`}
                          >
                            <Star
                              className={cn(
                                "size-4 transition-colors",
                                stelle.has(chiave) ? "fill-incerto text-incerto" : "text-muted-foreground/50 hover:text-incerto",
                              )}
                            />
                          </Button>
                        </td>
                        <td className="max-w-[18rem] px-3 py-2">
                          <span className="block truncate font-medium" title={v.prodotto}>{v.prodotto}</span>
                          <span className="block truncate text-xs text-muted-foreground" title={`${v.fornitore} · ${v.categoria}`}>
                            {v.fornitore} · {v.categoria} · {dataBreve(v.data)}
                          </span>
                        </td>
                        <td className="max-w-[12rem] px-3 py-2">
                          <span className="block truncate" title={v.nome_pv}>{v.nome_pv}</span>
                          {diffusione && (
                            <span
                              className={cn(
                                "mt-0.5 inline-block rounded-full border px-2 py-px text-[11px]",
                                v.n_pv_stesso_verso >= 2 ? "border-incerto/50 text-foreground" : "text-muted-foreground",
                              )}
                              title={
                                v.n_pv_stesso_verso >= 2
                                  ? "Lo stesso cambio di prezzo c'è in più punti vendita: viene dal fornitore"
                                  : "Gli altri punti vendita che comprano questo prodotto non hanno lo stesso cambio"
                              }
                            >
                              {diffusione}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{euro2(v.penultimo)}</td>
                        <td className="px-3 py-2 text-right font-semibold tabular-nums">{euro2(v.ultimo)}</td>
                        <td className="px-3 py-2 text-right font-semibold tabular-nums">{pct(v.aumento_perc)}</td>
                        <td className={cn("px-3 py-2 text-right font-semibold tabular-nums", classeImpatto(v.impatto_stimato))}>
                          {v.impatto_stimato !== 0 ? euroSegno(v.impatto_stimato) : "—"}
                        </td>
                        <td className="px-2 py-2">
                          <ChevronDown className={cn("size-4 text-muted-foreground transition-transform", isAperta && "rotate-180")} />
                        </td>
                      </tr>
                      {isAperta && (
                        <tr>
                          <td colSpan={8} className="bg-muted/10 px-6 pb-3">
                            <p className="pt-2 text-xs text-muted-foreground">Acquisti di {v.nome_pv} nel periodo</p>
                            <StoricoPv storico={storico} loading={storicoLoading} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )
        ) : divari.length === 0 ? (
          <div className="py-16 text-center text-sm text-muted-foreground">
            Nessun prodotto pagato più del {data.soglia}% in un punto vendita che in un altro.
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Ultimo prezzo pagato da ogni punto vendita per lo stesso prodotto dallo stesso fornitore. Sono confrontati
              solo i punti vendita che lo hanno comprato a non più di {data.divario_finestra_giorni} giorni l&apos;uno
              dall&apos;altro. «Pagato in più» = differenza col prezzo più basso × quantità comprata nel periodo.
            </p>
            {divari.map((d) => (
              <div key={`${d.prodotto}|${d.fornitore}`} className="rounded-lg border bg-card">
                <div className="flex flex-wrap items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold" title={d.prodotto}>{d.prodotto}</p>
                    <p className="truncate text-xs text-muted-foreground" title={`${d.fornitore} · ${d.categoria}`}>
                      {d.fornitore} · {d.categoria}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-muted-foreground">Divario</p>
                    <p className="text-lg font-bold tabular-nums">{pct(d.divario_perc)}</p>
                  </div>
                  <div className="w-32 text-right">
                    <p className="text-xs text-muted-foreground">Pagato in più</p>
                    <p className={cn("text-sm font-semibold tabular-nums", classeImpatto(d.extra_stimato))}>
                      {euro2(d.extra_stimato)}
                    </p>
                  </div>
                </div>
                <table className="w-full border-t text-xs">
                  <tbody>
                    {d.per_pv.map((p) => (
                      <tr
                        key={p.ristorante_id}
                        className={cn("border-t border-border/60 first:border-t-0", p.ristorante_id === pv && "bg-muted/30")}
                      >
                        <td className="max-w-[14rem] px-4 py-1.5">
                          <span className={cn("block truncate", p.ultimo === d.prezzo_max && "font-semibold")} title={p.nome_pv}>
                            {p.nome_pv}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-muted-foreground tabular-nums">{dataBreve(p.data)}</td>
                        <td className="px-3 py-1.5 text-right font-medium tabular-nums">{euro2(p.ultimo)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {p.scarto_perc > 0 ? pct(p.scarto_perc) : "il più basso"}
                        </td>
                        <td className={cn("w-32 px-4 py-1.5 text-right tabular-nums", classeImpatto(p.extra_stimato))}>
                          {p.extra_stimato > 0 ? euro2(p.extra_stimato) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </div>
    </PannelloScheda>
  );
}
