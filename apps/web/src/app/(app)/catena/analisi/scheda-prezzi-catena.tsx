"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Calendar, CheckCircle2, RefreshCw, Search, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { InfoPopover } from "@/components/ui/info-popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/utils";
import { intervalloPeriodo } from "@/lib/periodo";
import type { StoricoPrezzoPoint, StoricoPrezzoResponse } from "@/lib/prezzi";
import { AnteprimaFatturaDialog } from "../../prezzi/anteprima-fattura-dialog";
import {
  chiaveDivario,
  chiaveStellaCatena,
  etichettaDiffusione,
  filtraDivari,
  filtraVariazioni,
  pvDeiPrezzi,
  sogliaDaApplicare,
  spiegazioneDiffusione,
  stelleIniziali,
  testoSoglia,
  totaliPrezzi,
  valoriFiltro,
  type DivarioPrezzo,
  type GruppoPrezzi,
  type VariazionePrezzoCatena,
} from "@/lib/catena-prezzi";
import {
  ETICHETTA_DA_CONTROLLARE,
  SPIEGAZIONE_DA_CONTROLLARE,
  coppiaPreferito,
  nomeProdotto,
  type VistaPrezzi,
} from "@/lib/prezzi-viste";
import {
  ContaVariazioni,
  IntestazioneVariazioni,
  KpiCard,
  SpiegazioneDaControllare,
  VariazioneCard,
  fmtData,
  fmtEuro,
  fmtPct,
} from "@/components/prezzi/variazione-card";
import { ANNO_CORRENTE, FiltroPeriodoPrezzi, type ModoPeriodo } from "@/components/prezzi/filtro-periodo-prezzi";

type Lista = "variazioni" | "divari";

const PAGE_SIZE = 100;

// Stessi controlli dell'Osservatorio del PV (variazioni-tab.tsx): stesse classi,
// perche' le due pagine si leggano allo stesso modo.
const CAMPO = "rounded-md border border-border bg-background px-2 py-1.5 text-sm";

// Scheda «Prezzi» di Analisi catena. Dal 13/10/2026 ha la struttura
// dell'Osservatorio del PV (Mattia: «voglio coerenza con prezzi dei punti
// vendita singoli»): filtro del periodo, totali, filtri, e le stesse schede per
// riga. Prima stava in un riquadro bianco con una tabella, e nel tema chiaro
// filtri, totali e righe erano bianco su bianco. Due liste: i rincari di ogni
// punto vendita, con la sede su ogni riga, e lo stesso prodotto pagato diverso
// fra le sedi. Le regole stanno in lib/catena-prezzi.ts.
export function SchedaPrezziCatena() {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [modo, setModo] = useState<ModoPeriodo>("anno");
  const [mese, setMese] = useState<number | null>(null);
  const [customDa, setCustomDa] = useState("");
  const [customA, setCustomA] = useState("");
  const [range, setRange] = useState(() => intervalloPeriodo(ANNO_CORRENTE, null));
  // null = la soglia degli avvisi dell'account, che il worker usa e rimanda:
  // la casella parte da li', come nell'Osservatorio del PV.
  const [soglia, setSoglia] = useState<number | null>(null);
  const [sogliaInput, setSogliaInput] = useState("");
  const [lista, setLista] = useState<Lista>("variazioni");
  const [mostra, setMostra] = useState<VistaPrezzi>("tutti");
  const [stelle, setStelle] = useState<Set<string>>(new Set());
  const [pv, setPv] = useState("");
  const [ricerca, setRicerca] = useState("");
  const [categoria, setCategoria] = useState("");
  const [fornitore, setFornitore] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<GruppoPrezzi | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [aperta, setAperta] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  // Anteprima di una fattura dalla lista acquisti, come nell'Osservatorio: la
  // fattura e' della sede della riga (Mattia, 13/10/2026).
  const [anteprima, setAnteprima] = useState<{ punto: StoricoPrezzoPoint; v: VariazionePrezzoCatena } | null>(null);
  const apriFattura = useCallback((v: VariazionePrezzoCatena, p: StoricoPrezzoPoint) => setAnteprima({ punto: p, v }), []);
  const reqRef = useRef(0);
  // Una stella cambiata nelle variazioni sposta anche i «Preferiti» dei divari,
  // che il worker calcola: passando a quella lista si ricarica.
  const stelleCambiate = useRef(false);

  const carica = useCallback(() => {
    if (!range.data_da || !range.data_a) return;
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

  function applyAnno(y: number) {
    setAnno(y);
    setModo("anno");
    setMese(null);
    setRange(intervalloPeriodo(y, null));
  }
  function applyMese(m: number) {
    setMese(m);
    setModo("mese");
    setRange(intervalloPeriodo(anno, m));
  }
  function applyCustom(da: string, a: string) {
    setCustomDa(da);
    setCustomA(a);
    if (da && a) setRange({ data_da: da, data_a: a });
  }

  function applicaSoglia() {
    const esito = sogliaDaApplicare(sogliaInput, soglia ?? data?.soglia ?? null);
    setSogliaInput(esito.testo);
    if (esito.nuova != null) setSoglia(esito.nuova);
  }

  const elencoPv = useMemo(() => pvDeiPrezzi(data), [data]);
  const opzioni = useMemo(
    () => valoriFiltro(lista === "variazioni" ? data?.variazioni ?? [] : data?.divari ?? []),
    [data, lista],
  );
  const variazioni = useMemo(
    () => filtraVariazioni(data?.variazioni ?? [], { pv, ricerca, categoria, fornitore, vista: mostra }, stelle),
    [data, pv, ricerca, categoria, fornitore, mostra, stelle],
  );
  const divari = useMemo(
    () => filtraDivari(data?.divari ?? [], { pv, ricerca, categoria, fornitore, vista: mostra }),
    [data, pv, ricerca, categoria, fornitore, mostra],
  );
  // Il «filtrate da N» si misura sulla vista senza i filtri, come nel PV. Anche i
  // contatori delle viste (Preferiti, Confezione diversa?) non seguono la ricerca:
  // seguendola, una ricerca vuota faceva sparire la voce e tornare a «Tutti».
  const base = useMemo(
    () =>
      lista === "variazioni"
        ? filtraVariazioni(data?.variazioni ?? [], { pv: "", ricerca: "", vista: mostra }, stelle).length
        : filtraDivari(data?.divari ?? [], { pv: "", ricerca: "", vista: mostra }).length,
    [data, lista, mostra, stelle],
  );
  const nDaControllare = useMemo(
    () =>
      lista === "variazioni"
        ? filtraVariazioni(data?.variazioni ?? [], { pv, ricerca: "", vista: "da_controllare" }).length
        : filtraDivari(data?.divari ?? [], { pv, ricerca: "", vista: "da_controllare" }).length,
    [data, pv, lista],
  );
  const nStelle = useMemo(
    () =>
      lista === "variazioni"
        ? filtraVariazioni(data?.variazioni ?? [], { pv, ricerca: "", vista: "preferiti" }, stelle).length
        : filtraDivari(data?.divari ?? [], { pv, ricerca: "", vista: "preferiti" }).length,
    [data, pv, lista, stelle],
  );
  const totali = totaliPrezzi(variazioni, divari, pv);
  const nomePv = elencoPv.find((p) => p.id === pv)?.nome;
  const righe = lista === "variazioni" ? variazioni.length : divari.length;
  const pagine = Math.max(1, Math.ceil(righe / PAGE_SIZE));
  const pagina = Math.min(page, pagine);
  const filtriAttivi = Boolean(ricerca || categoria || fornitore);

  // Una voce che sparisce dal selettore (nessuna riga «Confezione diversa?» in
  // questo periodo) riporta su «Tutti»: restarci mostrerebbe una lista vuota
  // senza un perche'.
  useEffect(() => {
    if (mostra === "da_controllare" && nDaControllare === 0) setMostra("tutti");
  }, [mostra, nDaControllare]);

  // Categoria e fornitore valgono per la lista in cui sono stati scelti.
  useEffect(() => {
    setCategoria("");
    setFornitore("");
  }, [lista, data]);

  useEffect(() => {
    setPage(1);
  }, [lista, mostra, pv, ricerca, categoria, fornitore, data]);

  useEffect(() => {
    if (lista === "divari" && stelleCambiate.current) {
      stelleCambiate.current = false;
      carica();
    }
  }, [lista, carica]);

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
        stelleCambiate.current = true;
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
  const finestra = data?.divario_finestra_giorni ?? 60;

  return (
    <div className="space-y-4">
      <FiltroPeriodoPrezzi
        anno={anno}
        modo={modo}
        mese={mese}
        customDa={customDa}
        customA={customA}
        range={range}
        loading={loading}
        onAnno={applyAnno}
        onModoMese={() => {
          setModo("mese");
          if (mese !== null) setRange(intervalloPeriodo(anno, mese));
        }}
        onMese={applyMese}
        onModoCustom={() => setModo("custom")}
        onCustom={applyCustom}
        destra={
          <>
            <InfoPopover title="Come leggere i prezzi della catena" ariaLabel="Come leggere i prezzi della catena" align="end">
              <p className="text-muted-foreground">
                <strong className="text-foreground">Variazioni di prezzo</strong>: come è cambiato il prezzo di ogni
                prodotto in ogni punto vendita, confrontando gli ultimi due acquisti dallo stesso fornitore. È lo
                stesso calcolo dell&apos;Osservatorio di ogni punto vendita.
              </p>
              <div className="space-y-1.5 text-muted-foreground">
                <p>
                  <strong className="text-foreground">«Aumentato in 3 PV su 4»</strong>: lo stesso cambiamento c&apos;è
                  in più punti vendita, quindi probabilmente l&apos;ha deciso il fornitore.{" "}
                  <strong className="text-foreground">«Solo qui»</strong>: gli altri punti vendita che comprano il
                  prodotto non l&apos;hanno avuto.
                </p>
                <p>
                  <strong className="text-foreground">Impatto/mese</strong> = aumento di prezzo × quantità abituale ×
                  acquisti al mese.
                </p>
              </div>
              <div className="space-y-1.5 border-t border-border pt-2 text-muted-foreground">
                <p>
                  <strong className="text-foreground">Stesso prodotto, prezzi diversi</strong>: l&apos;ultimo prezzo
                  pagato da ogni punto vendita per lo stesso prodotto dallo stesso fornitore. Si confrontano solo i
                  punti vendita che l&apos;hanno comprato a meno di {finestra} giorni l&apos;uno dall&apos;altro: per
                  un confronto più stretto scegli un mese o un periodo personalizzato.
                </p>
                <p>
                  <strong className="text-foreground">Pagato in più</strong> = (prezzo del punto vendita − prezzo più
                  basso) × quantità comprata nel periodo.
                </p>
              </div>
              <div className="space-y-1.5 border-t border-border pt-2 text-muted-foreground">
                <p>
                  <strong className="text-foreground">Mostra da … % in su</strong> filtra solo questa pagina. La
                  soglia degli avvisi si imposta nell&apos;assistente, in Home.
                </p>
                <p>
                  <strong className="text-foreground">{ETICHETTA_DA_CONTROLLARE}</strong> {SPIEGAZIONE_DA_CONTROLLARE}
                </p>
              </div>
            </InfoPopover>
            <Button variant="outline" size="sm" onClick={carica} disabled={loading}>
              <RefreshCw className={loading ? "animate-spin" : ""} />
              Aggiorna
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <SegmentedControl
          aria-label="Lista"
          value={lista}
          onChange={setLista}
          options={[
            { value: "variazioni", label: "Variazioni di prezzo" },
            { value: "divari", label: "Stesso prodotto, prezzi diversi" },
          ]}
        />
        <select value={pv} onChange={(e) => setPv(e.target.value)} aria-label="Punto vendita" className={CAMPO}>
          <option value="">Tutti i punti vendita</option>
          {elencoPv.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </select>
      </div>

      {data && !vuoto && mostra === "da_controllare" && <SpiegazioneDaControllare />}
      {data && !vuoto && mostra !== "da_controllare" && (
        <div className="grid grid-cols-2 gap-3">
          {lista === "variazioni" ? (
            <>
              <KpiCard
                label="Variazione media"
                value={variazioni.length > 0 ? fmtPct(totali.variazioneMedia) : "—"}
                sub={`${totali.aumenti} in aumento · ${totali.cali} in calo`}
                tone={totali.variazioneMedia < 0 ? "positivo" : "negativo"}
              />
              <KpiCard
                label="Impatto stimato/mese"
                value={totali.impattoNetto !== 0 ? fmtEuro(totali.impattoNetto, true) : "—"}
                sub={nomePv ?? "Tutti i punti vendita"}
                tone={totali.impattoNetto < 0 ? "positivo" : "negativo"}
              />
            </>
          ) : (
            <>
              <KpiCard
                label="Prodotti con prezzi diversi"
                value={String(totali.divari)}
                sub={nomePv ?? "Tutti i punti vendita"}
                tone="neutro"
              />
              <KpiCard
                label="Pagato in più nel periodo"
                value={totali.extraDivari !== 0 ? fmtEuro(totali.extraDivari) : "—"}
                sub={nomePv ? `Da ${nomePv}, rispetto al punto vendita che paga meno` : "Rispetto al punto vendita che paga meno"}
                tone="negativo"
              />
            </>
          )}
        </div>
      )}

      {data && !vuoto && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1.5">
            <label htmlFor="soglia-prezzi-catena" className="whitespace-nowrap text-sm text-muted-foreground">
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
              className="w-12 bg-transparent text-right text-sm outline-none disabled:opacity-50"
            />
            <span className="whitespace-nowrap text-sm text-muted-foreground">% in su</span>
          </div>
          <SegmentedControl
            aria-label="Mostra"
            value={mostra}
            onChange={setMostra}
            options={[
              { value: "tutti" as const, label: "Tutti" },
              {
                value: "preferiti" as const,
                label: (
                  <>
                    <Star className={cn("size-3", mostra === "preferiti" ? "fill-current" : "fill-incerto text-incerto")} />
                    Preferiti{nStelle > 0 ? ` (${nStelle})` : ""}
                  </>
                ),
              },
              ...(nDaControllare > 0
                ? [{ value: "da_controllare" as const, label: `${ETICHETTA_DA_CONTROLLARE} (${nDaControllare})`, title: SPIEGAZIONE_DA_CONTROLLARE }]
                : []),
            ]}
          />
          <div className="relative">
            <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Cerca prodotto…"
              value={ricerca}
              onChange={(e) => setRicerca(e.target.value)}
              aria-label="Cerca prodotto o fornitore"
              className={cn(CAMPO, "w-52 pl-9 pr-3")}
            />
          </div>
          <select value={categoria} onChange={(e) => setCategoria(e.target.value)} aria-label="Categoria" className={CAMPO}>
            <option value="">Tutte le categorie</option>
            {opzioni.categorie.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <select value={fornitore} onChange={(e) => setFornitore(e.target.value)} aria-label="Fornitore" className={CAMPO}>
            <option value="">Tutti i fornitori</option>
            {opzioni.fornitori.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          {filtriAttivi && (
            <Button
              variant="ghost"
              size="xs"
              onClick={() => {
                setRicerca("");
                setCategoria("");
                setFornitore("");
              }}
            >
              Azzera filtri
            </Button>
          )}
        </div>
      )}

      {loading && !data ? (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg border border-border bg-card" />
          ))}
        </div>
      ) : loadError && !data ? (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card py-10 text-center">
          <AlertTriangle className="size-7 text-negativo" />
          <p className="text-sm text-muted-foreground">Non è stato possibile caricare i dati.</p>
          <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
            Riprova
          </Button>
        </div>
      ) : !data ? null : vuoto ? (
        <div className="rounded-lg border border-border bg-card py-10 text-center">
          <Calendar className="mx-auto mb-2 size-8 text-muted-foreground/40" />
          <p className="text-sm font-medium">Nessuna fattura nel periodo</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Senza fatture non è possibile confrontare i prezzi. Scegli un altro periodo.
          </p>
        </div>
      ) : righe === 0 ? (
        <div className="rounded-lg border border-border bg-card py-10 text-center">
          {mostra === "preferiti" ? (
            <>
              <Star className="mx-auto mb-2 size-7 text-incerto" />
              <p className="text-sm font-medium">Nessun preferito in questa lista</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Tocca la ⭐ accanto a un prodotto, qui o nell&apos;Osservatorio di un punto vendita, per seguirlo.
              </p>
            </>
          ) : filtriAttivi ? (
            <p className="text-sm text-muted-foreground">Nessun risultato per i filtri selezionati</p>
          ) : (
            <>
              <CheckCircle2 className="mx-auto mb-2 size-8 text-positivo" />
              <p className="text-sm font-medium">
                {lista === "variazioni"
                  ? `Nessuna variazione sopra il ${data.soglia}%`
                  : `Nessun prodotto pagato più del ${data.soglia}% in un punto vendita che in un altro`}
              </p>
            </>
          )}
        </div>
      ) : lista === "variazioni" ? (
        <>
          <ContaVariazioni
            n={variazioni.length}
            base={base}
          />
          <IntestazioneVariazioni conPuntoVendita />
          <div className="space-y-2">
            {variazioni.slice((pagina - 1) * PAGE_SIZE, pagina * PAGE_SIZE).map((v) => {
              const chiave = chiaveStellaCatena(v);
              return (
                <VariazioneCard
                  key={chiave}
                  r={v}
                  expanded={aperta === chiave}
                  preferito={stelle.has(chiave)}
                  storico={aperta === chiave ? storico : null}
                  storicoLoading={aperta === chiave && storicoLoading}
                  onToggle={apriVariazione}
                  onToggleStar={toggleStella}
                  onApriFattura={apriFattura}
                  puntoVendita={<PuntoVenditaRiga v={v} />}
                  nomePuntoVendita={v.nome_pv}
                />
              );
            })}
          </div>
          <Paginazione pagina={pagina} pagine={pagine} totale={righe} nome="variazioni" onPagina={setPage} />
        </>
      ) : (
        <>
          <ContaVariazioni
            n={divari.length}
            base={base}
            nome="prodotti"
            filtrate="filtrati"
          />
          <div className="space-y-2">
            {divari.slice((pagina - 1) * PAGE_SIZE, pagina * PAGE_SIZE).map((d) => (
              <DivarioCard key={chiaveDivario(d)} d={d} pv={pv} />
            ))}
          </div>
          <Paginazione pagina={pagina} pagine={pagine} totale={righe} nome="prodotti" onPagina={setPage} />
        </>
      )}

      <AnteprimaFatturaDialog
        open={anteprima !== null}
        fileOrigine={anteprima?.punto.fattura ?? null}
        numeroDocumento={anteprima?.punto.numero_documento}
        prodotto={anteprima ? nomeProdotto(anteprima.v.prodotto).nome : ""}
        ristoranteId={anteprima?.v.ristorante_id}
        puntoVendita={anteprima?.v.nome_pv}
        onClose={() => setAnteprima(null)}
      />
    </div>
  );
}

/** La colonna «Punto vendita» della riga: il nome e se il cambiamento c'e' anche altrove. */
function PuntoVenditaRiga({ v }: { v: VariazionePrezzoCatena }) {
  const etichetta = etichettaDiffusione(v);
  const listino = v.n_pv_stesso_verso >= 2;
  return (
    <>
      <p className="truncate text-sm" title={v.nome_pv}>
        {v.nome_pv}
      </p>
      {etichetta && (
        <span
          title={spiegazioneDiffusione(v) ?? undefined}
          className={cn(
            "mt-0.5 inline-block max-w-full truncate rounded-full border px-2 py-0.5 text-[11px]",
            listino ? "border-foreground/30 text-foreground" : "border-border text-muted-foreground",
          )}
        >
          {etichetta}
        </span>
      )}
    </>
  );
}

/**
 * Lo stesso prodotto pagato diverso fra i punti vendita. Stessa scheda delle
 * variazioni (striscia a sinistra per il peso in euro, pallino, nome) e sotto la
 * tabella dei punti vendita con l'intestazione colorata della lista acquisti
 * dell'Osservatorio: nel tema chiaro e' cio' che separa la tabella dalla scheda.
 */
function DivarioCard({ d, pv }: { d: DivarioPrezzo; pv: string }) {
  const { nome } = nomeProdotto(d.prodotto);
  return (
    <div className={`overflow-hidden rounded-lg border border-border bg-card shadow-sm`}>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        {d.preferito ? (
          <Star className="size-4 shrink-0 fill-incerto text-incerto" aria-label="Preferito in un punto vendita del confronto" />
        ) : (
          <span className="size-4 shrink-0" />
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold" title={nome}>
            {nome}
          </p>
          <p className="truncate text-xs text-muted-foreground" title={`${d.fornitore} · ${d.categoria}`}>
            {d.fornitore} · {d.categoria}
          </p>
        </div>
        <div className="w-28 shrink-0 text-right">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Differenza</p>
          <p className="text-lg font-bold leading-tight tabular-nums">{fmtPct(d.divario_perc)}</p>
        </div>
        <div className="w-28 shrink-0 text-right">
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">Pagato in più</p>
          <p className={cn("text-sm font-semibold tabular-nums", d.extra_stimato > 0 ? "text-negativo" : "text-muted-foreground")}>
            {d.extra_stimato > 0 ? fmtEuro(d.extra_stimato) : "—"}
          </p>
        </div>
      </div>
      <div className="overflow-x-auto border-t border-border">
        <table className="w-full text-xs">
          <thead className="bg-muted/40">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-muted-foreground">Punto vendita</th>
              <th className="px-3 py-2 text-left font-medium text-muted-foreground">Ultimo acquisto</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Prezzo</th>
              <th className="px-3 py-2 text-right font-medium text-muted-foreground">Rispetto al più basso</th>
              <th className="px-4 py-2 text-right font-medium text-muted-foreground">Pagato in più</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {d.per_pv.map((p) => (
              <tr key={p.ristorante_id} className={cn(p.ristorante_id === pv && "bg-muted/30")}>
                <td className="max-w-[16rem] px-4 py-2">
                  <span className={cn("block truncate", p.ultimo === d.prezzo_max && "font-semibold")} title={p.nome_pv}>
                    {p.nome_pv}
                  </span>
                </td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{fmtData(p.data)}</td>
                <td className="px-3 py-2 text-right font-medium tabular-nums">{fmtEuro(p.ultimo)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                  {p.scarto_perc > 0 ? fmtPct(p.scarto_perc) : "il prezzo più basso"}
                </td>
                <td className={cn("px-4 py-2 text-right tabular-nums", p.extra_stimato > 0 ? "text-negativo" : "text-muted-foreground")}>
                  {p.extra_stimato > 0 ? fmtEuro(p.extra_stimato) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Paginazione({
  pagina,
  pagine,
  totale,
  nome,
  onPagina,
}: {
  pagina: number;
  pagine: number;
  totale: number;
  nome: string;
  onPagina: (p: number) => void;
}) {
  if (pagine <= 1) return null;
  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-muted-foreground">
        Pagina {pagina} di {pagine} · {totale.toLocaleString("it-IT")} {nome}
      </span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={pagina <= 1} onClick={() => onPagina(pagina - 1)}>
          ← Precedente
        </Button>
        <Button variant="outline" size="sm" disabled={pagina >= pagine} onClick={() => onPagina(pagina + 1)}>
          Successiva →
        </Button>
      </div>
    </div>
  );
}
