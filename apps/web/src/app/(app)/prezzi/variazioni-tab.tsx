"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { RefreshCw, Search, CheckCircle2, Calendar, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { toast } from "sonner";
import type { VariazioniResponse, VariazionePrezzo, StoricoPrezzoResponse, StoricoPrezzoPoint } from "@/lib/prezzi";
import { InfoPopover } from "@/components/ui/info-popover";
import { AnteprimaFatturaDialog } from "./anteprima-fattura-dialog";
import { parseDecimaleIt } from "@/lib/format";
import { intervalloPeriodo as isoDateRange } from "@/lib/periodo";
import {
  ETICHETTA_DA_CONTROLLARE,
  SPIEGAZIONE_DA_CONTROLLARE,
  chiavePreferito,
  contaDaControllare,
  coppiaPreferito,
  inVista,
  type VistaPrezzi,
} from "@/lib/prezzi-viste";
import {
  ContaVariazioni,
  IntestazioneVariazioni,
  KpiCard,
  LEGENDA_GRAVITA,
  SpiegazioneDaControllare,
  VariazioneCard,
  fmtEuro,
  fmtPct,
  gravita,
} from "@/components/prezzi/variazione-card";
import { ANNO_CORRENTE, FiltroPeriodoPrezzi, type ModoPeriodo } from "@/components/prezzi/filtro-periodo-prezzi";

const PAGE_SIZE = 100;

export function VariazioniTab({ initialSoglia }: { initialSoglia: number }) {
  const [anno, setAnno] = useState(ANNO_CORRENTE);
  const [mese, setMese] = useState<number | null>(null); // null = tutto l'anno
  const [modo, setModo] = useState<ModoPeriodo>("anno");
  const [customDa, setCustomDa] = useState("");
  const [customA, setCustomA] = useState("");
  const [soglia, setSoglia] = useState(initialSoglia);
  const [sogliaInput, setSogliaInput] = useState(String(initialSoglia));
  const [data, setData] = useState<VariazioniResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");

  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const [storico, setStorico] = useState<StoricoPrezzoResponse | null>(null);
  const [storicoLoading, setStoricoLoading] = useState(false);
  const [filtroCategoria, setFiltroCategoria] = useState("");
  const [filtroFornitore, setFiltroFornitore] = useState("");
  const [preferiti, setPreferiti] = useState<Set<string>>(new Set());
  const [vista, setVista] = useState<VistaPrezzi>("tutti");
  const [currentRange, setCurrentRange] = useState<{ data_da: string; data_a: string }>(
    isoDateRange(ANNO_CORRENTE, null),
  );
  // Anteprima fattura aperta da una riga della lista acquisti.
  const [anteprima, setAnteprima] = useState<{ punto: StoricoPrezzoPoint; prodotto: string } | null>(null);
  const [page, setPage] = useState(1);
  const apriFattura = useCallback(
    (r: VariazionePrezzo, p: StoricoPrezzoPoint) => setAnteprima({ punto: p, prodotto: r.prodotto }),
    [],
  );

  // Carica per range esplicito: cosi' lo stesso fetch serve anno, mese e custom.
  const loadRange = useCallback(async (range: { data_da: string; data_a: string }, sogliaArg: number) => {
    if (!range.data_da || !range.data_a) return;
    setLoading(true);
    setExpandedKey(null);
    setStorico(null);
    setFiltroCategoria("");
    setFiltroFornitore("");
    setCurrentRange(range);
    try {
      const qs = new URLSearchParams({ ...range, soglia: String(sogliaArg) });
      const res = await fetch(`/api/prezzi/variazioni?${qs}`);
      if (!res.ok) throw new Error();
      const json: VariazioniResponse = await res.json();
      setData(json);
      // Set preferiti iniziale dal campo `preferito` della response: cosi' la
      // stella riflette lo stato salvato e gli aggiornamenti ottimistici partono
      // da una base corretta.
      setPreferiti(
        new Set(
          (json.variazioni ?? [])
            .filter((v) => v.preferito)
            .map((v) => chiavePreferito(v)),
        ),
      );
    } catch {
      toast.error("Errore nel caricamento variazioni");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRange(isoDateRange(ANNO_CORRENTE, null), initialSoglia);
  }, [loadRange, initialSoglia]);

  // Torna a pagina 1 quando cambia il set filtrato: restare su una pagina che
  // non esiste più mostrerebbe una lista vuota anche con risultati disponibili.
  useEffect(() => {
    setPage(1);
  }, [search, filtroCategoria, filtroFornitore, vista, data]);

  // Applica un preset di periodo aggiornando stato + ricaricando.
  function applyAnno(y: number) {
    setAnno(y);
    setModo("anno");
    setMese(null);
    loadRange(isoDateRange(y, null), soglia);
  }
  function applyMese(m: number) {
    setMese(m);
    setModo("mese");
    loadRange(isoDateRange(anno, m), soglia);
  }
  function applyCustom(da: string, a: string) {
    setCustomDa(da);
    setCustomA(a);
    if (da && a) loadRange({ data_da: da, data_a: a }, soglia);
  }

  // Range attivo in base al modo (per ricaricare dopo il salvataggio soglia).
  function rangeAttivo(): { data_da: string; data_a: string } {
    if (modo === "custom" && customDa && customA) return { data_da: customDa, data_a: customA };
    if (modo === "mese") return isoDateRange(anno, mese);
    return isoDateRange(anno, null);
  }

  // Filtro di SOLA VISUALIZZAZIONE: muove la soglia per vedere cosa supererebbe
  // in questa pagina, senza salvare nulla. La soglia che fa scattare gli AVVISI si
  // imposta nel configuratore assistente (Home) ed e' quella di partenza qui.
  function applicaFiltroSoglia() {
    const val = parseDecimaleIt(sogliaInput) || 5;
    setSoglia(val);
    loadRange(rangeAttivo(), val);
  }

  const toggleCard = useCallback(async (r: VariazionePrezzo) => {
    const key = chiavePreferito(r);
    if (expandedKey === key) {
      setExpandedKey(null);
      return;
    }
    setExpandedKey(key);
    setStorico(null);
    setStoricoLoading(true);
    try {
      const qs = new URLSearchParams({
        prodotto: r.prodotto,
        fornitore: r.fornitore,
        data_da: currentRange.data_da,
        data_a: currentRange.data_a,
      });
      const res = await fetch(`/api/prezzi/storico-prodotto?${qs}`);
      if (!res.ok) throw new Error();
      setStorico(await res.json());
    } catch {
      toast.error("Errore nel caricamento storico");
    } finally {
      setStoricoLoading(false);
    }
  }, [expandedKey, currentRange]);

  // Stella ottimistica: aggiorna subito il Set locale, poi persiste. Su errore
  // fa rollback e mostra un toast — la stella non resta in uno stato falso.
  const toggleStar = useCallback(async (r: VariazionePrezzo) => {
    const key = chiavePreferito(r);
    const coppia = coppiaPreferito(r);
    const eraPreferito = preferiti.has(key);
    setPreferiti((prev) => {
      const next = new Set(prev);
      if (eraPreferito) next.delete(key);
      else next.add(key);
      return next;
    });
    try {
      let res: Response;
      if (eraPreferito) {
        const qs = new URLSearchParams(coppia);
        res = await fetch(`/api/prezzi/preferiti?${qs}`, { method: "DELETE" });
      } else {
        res = await fetch("/api/prezzi/preferiti", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(coppia),
        });
      }
      if (!res.ok) throw new Error();
    } catch {
      setPreferiti((prev) => {
        const next = new Set(prev);
        if (eraPreferito) next.add(key);
        else next.delete(key);
        return next;
      });
      toast.error("Non sono riuscito ad aggiornare i preferiti");
    }
  }, [preferiti]);

  const variazioni = useMemo(() => data?.variazioni ?? [], [data]);

  const sorted = useMemo(
    () => [...variazioni].sort((a, b) => Math.abs(b.impatto_stimato) - Math.abs(a.impatto_stimato)),
    [variazioni],
  );

  // valori unici per i select categoria/fornitore
  const categorieDisp = useMemo(
    () => Array.from(new Set(sorted.map((r) => r.categoria).filter(Boolean))).sort(),
    [sorted],
  );
  const fornitoriDisp = useMemo(
    () => Array.from(new Set(sorted.map((r) => r.fornitore).filter(Boolean))).sort(),
    [sorted],
  );

  const filtered = useMemo(() => sorted.filter((r) => {
    const matchSearch =
      !search ||
      r.prodotto.toLowerCase().includes(search.toLowerCase()) ||
      r.fornitore.toLowerCase().includes(search.toLowerCase());
    const matchCat = !filtroCategoria || r.categoria === filtroCategoria;
    const matchForn = !filtroFornitore || r.fornitore === filtroFornitore;
    const matchVista = inVista(r, vista, preferiti.has(chiavePreferito(r)));
    return matchSearch && matchCat && matchForn && matchVista;
  }), [sorted, search, filtroCategoria, filtroFornitore, vista, preferiti]);

  const nDaControllare = useMemo(() => contaDaControllare(variazioni), [variazioni]);
  // Il «filtrate da N» si misura sulla vista, non sul totale: le righe da
  // controllare non sono «filtrate via» da Tutti, stanno in un'altra lista.
  const baseVista = vista === "da_controllare" ? nDaControllare : variazioni.length - nDaControllare;
  // Un nuovo periodo senza righe da controllare toglie la voce dal selettore:
  // restarci sopra mostrerebbe una lista vuota senza modo di capire perche'.
  useEffect(() => {
    if (vista === "da_controllare" && nDaControllare === 0) setVista("tutti");
  }, [vista, nDaControllare]);

  const nPreferiti = preferiti.size;

  // KPI calcolati sul filtered
  const nCritici = useMemo(() => filtered.filter((r) => gravita(r) === "critico").length, [filtered]);
  const impattoFiltrato = useMemo(() => filtered.reduce((acc, r) => acc + r.impatto_stimato, 0), [filtered]);
  const scostamentoFiltrato = useMemo(
    () => (filtered.length > 0 ? filtered.reduce((acc, r) => acc + r.aumento_perc, 0) / filtered.length : 0),
    [filtered],
  );

  // KPI di sintesi mostrati in cima al tab (specifici di "Variazioni Prezzo")
  const rincari = useMemo(() => filtered.filter((r) => r.aumento_perc > 0), [filtered]);
  const risparmi = useMemo(() => filtered.filter((r) => r.aumento_perc < 0), [filtered]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const visible = useMemo(
    () => filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filtered, safePage],
  );

  return (
    <div className="space-y-4">
      {/* ── Filtro periodo (condiviso con la scheda Prezzi di catena) ── */}
      <FiltroPeriodoPrezzi
        anno={anno}
        modo={modo}
        mese={mese}
        customDa={customDa}
        customA={customA}
        range={currentRange}
        loading={loading}
        onAnno={applyAnno}
        onModoMese={() => { setModo("mese"); if (mese !== null) loadRange(isoDateRange(anno, mese), soglia); }}
        onMese={applyMese}
        onModoCustom={() => setModo("custom")}
        onCustom={applyCustom}
        destra={
          <>
                <InfoPopover title="Come leggere le variazioni di prezzo" ariaLabel="Come leggere le variazioni di prezzo" align="end">
                  <p className="text-muted-foreground">
                    Come sono cambiati i prezzi d&apos;acquisto dei tuoi prodotti nel periodo, confrontando gli ultimi due acquisti di ogni prodotto dallo stesso fornitore.
                  </p>
                  <div className="space-y-1.5 text-muted-foreground">
                    <p><strong className="text-foreground">Media</strong> = il prezzo medio del prodotto nel periodo.</p>
                    <p>{LEGENDA_GRAVITA}</p>
                    <p>Clicca un prodotto per vedere lo <strong className="text-foreground">storico</strong> nel tempo e la fattura di origine.</p>
                  </div>
                  <div className="border-t border-border pt-2 space-y-1.5 text-muted-foreground">
                    <p className="font-medium text-foreground">Impatto/mese</p>
                    <p>Quanto ti costa davvero il rincaro ogni mese, non solo in %:</p>
                    <p className="text-foreground text-xs bg-muted/50 rounded px-2 py-1">aumento di prezzo × quantità abituale × acquisti al mese</p>
                    <p>Così un piccolo rincaro su ciò che ordini spesso può pesare più di un grosso aumento su qualcosa di raro. La lista parte dall&apos;impatto più alto.</p>
                  </div>
                  <div className="border-t border-border pt-2 space-y-1.5 text-muted-foreground">
                    <p><strong className="text-foreground">Mostra variazioni da … % in su</strong> filtra solo questa pagina. La soglia degli avvisi si imposta nell&apos;assistente, in Home.</p>
                    <p>Dati dalle tue fatture reali: servono almeno due acquisti dello stesso prodotto.</p>
                  </div>
                </InfoPopover>
                <Button variant="outline" size="sm" onClick={() => loadRange(rangeAttivo(), soglia)} disabled={loading}>
                  <RefreshCw className={loading ? "animate-spin" : ""} />
                  Aggiorna
                </Button>
          </>
        }
      />

      {/* ── KPI di sintesi (specifici del tab Variazioni) ──
          Erano quattro. «Rincari medi» e «Risparmi medi» sono usciti il
          22/09/2026: erano medie aritmetiche SEMPLICI delle percentuali
          (`reduce(...)/length`), quindi un prodotto da 8 EUR pesava quanto uno
          da 2.000, e non c'e' nessuna difesa contro le righe anomale — il
          backend confronta gli ultimi due prezzi unitari e basta
          (routers/prezzi.py:330-336). Una singola riga sballata di un
          fornitore produceva un -95% che dominava la media. Un numero che non
          orienta nessuna decisione e puo' mentire e' rumore, non sintesi.
          Il conteggio di quanti prodotti salgono e quanti scendono resta, ma
          sotto «Scostamento medio»: quello e' un dato onesto. */}
      {/* Nella vista «Da controllare» i totali non hanno senso (sono proprio le
          righe tenute fuori dai totali): al loro posto, il perche'. */}
      {data && variazioni.length > 0 && vista === "da_controllare" && <SpiegazioneDaControllare />}
      {data && variazioni.length > 0 && vista !== "da_controllare" && (
        <div className="grid grid-cols-2 gap-3">
          <KpiCard
            label="Variazione media"
            value={filtered.length > 0 ? fmtPct(scostamentoFiltrato) : "—"}
            sub={`${rincari.length} in aumento · ${risparmi.length} in calo`}
            tone={scostamentoFiltrato < 0 ? "positivo" : "negativo"}
          />
          <KpiCard
            label="Impatto stimato/mese"
            value={impattoFiltrato !== 0 ? fmtEuro(impattoFiltrato, true) : "—"}
            /* Come gli altri KPI del tab, e' calcolato sul filtrato: senza dirlo,
               un impatto ristretto a un fornitore si leggeva come totale. Stessa
               convenzione di sconti-tab/nc-tab ("filtrati da N"). */
            sub={
              filtered.length !== baseVista
                ? `su ${filtered.length} di ${baseVista} variazioni`
                : "effetto sui costi mensili"
            }
            tone={impattoFiltrato < 0 ? "positivo" : "negativo"}
          />
        </div>
      )}

      {/* Filtri di secondo livello. La riga compare gia' con le sole fatture nel
          periodo, non con le variazioni: la soglia sta qui dentro ed e' proprio
          cio' che puo' svuotare la lista — dietro `variazioni.length > 0` il
          cliente resterebbe chiuso fuori, senza modo di riabbassarla. */}
      {data && (data.fatture_nel_periodo ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2 items-center">
          {/* La soglia prima aveva una riga propria con bottone «Applica» e una
              frase di due righe: il primo prodotto finiva a 460 px dal titolo.
              La spiegazione e' passata nell'InfoPopover del periodo. */}
          <div className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1.5">
            <label htmlFor="soglia-variazioni" className="text-sm text-muted-foreground whitespace-nowrap">Mostra da</label>
            <input
              id="soglia-variazioni"
              type="number"
              min="0"
              max="50"
              step="0.5"
              value={sogliaInput}
              onChange={(e) => setSogliaInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") applicaFiltroSoglia(); }}
              onBlur={() => applicaFiltroSoglia()}
              disabled={loading}
              className="w-12 bg-transparent text-sm text-right outline-none disabled:opacity-50"
            />
            <span className="text-sm text-muted-foreground whitespace-nowrap">% in su</span>
          </div>
          {variazioni.length > 0 && (
          <>
          <SegmentedControl
            aria-label="Mostra"
            value={vista}
            onChange={setVista}
            options={[
              { value: "tutti", label: "Tutti" },
              {
                value: "preferiti",
                label: (
                  <>
                    <Star className={`size-3 ${vista === "preferiti" ? "fill-current" : "fill-incerto text-incerto"}`} />
                    Preferiti{nPreferiti > 0 ? ` (${nPreferiti})` : ""}
                  </>
                ),
              },
              ...(nDaControllare > 0
                ? [{ value: "da_controllare" as const, label: `${ETICHETTA_DA_CONTROLLARE} (${nDaControllare})`, title: SPIEGAZIONE_DA_CONTROLLARE }]
                : []),
            ]}
          />
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Cerca prodotto…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="rounded-md border border-border pl-9 pr-3 py-1.5 text-sm bg-background w-52"
            />
          </div>
          <select
            value={filtroCategoria}
            onChange={(e) => setFiltroCategoria(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutte le categorie</option>
            {categorieDisp.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={filtroFornitore}
            onChange={(e) => setFiltroFornitore(e.target.value)}
            className="rounded-md border border-border px-2 py-1.5 text-sm bg-background"
          >
            <option value="">Tutti i fornitori</option>
            {fornitoriDisp.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          {(search || filtroCategoria || filtroFornitore) && (
            <button
              onClick={() => { setSearch(""); setFiltroCategoria(""); setFiltroFornitore(""); }}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Azzera filtri
            </button>
          )}
          </>
          )}
        </div>
      )}

      {/* N. variazioni + legenda gravità — appena sopra la lista */}
      {data && variazioni.length > 0 && (
        <ContaVariazioni n={filtered.length} base={baseVista} critiche={nCritici} />
      )}

      {/* Stato vuoto. "Stabili" e' una RASSICURAZIONE, e vale solo se le fatture
          ci sono: fino al 17/09/2026 usciva anche su un anno senza una sola
          fattura caricata, dove l'app non sa nulla dei prezzi.
          `fatture_nel_periodo` e' opzionale (le response in cache prima di quel
          deploy non ce l'hanno): `undefined` vuol dire "non lo so" e tiene il
          messaggio neutro, mai la rassicurazione. */}
      {data && variazioni.length === 0 && (
        data.fatture_nel_periodo === 0 ? (
          <div className="rounded-lg border border-border bg-card py-10 text-center">
            <Calendar className="size-8 text-muted-foreground/40 mx-auto mb-2" />
            <p className="text-sm font-medium">Nessuna fattura nel periodo</p>
            <p className="text-xs text-muted-foreground mt-1">
              Senza fatture non è possibile confrontare i prezzi. Caricale o scegli un altro periodo.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-border bg-card py-10 text-center">
            <CheckCircle2 className="size-8 text-positivo mx-auto mb-2" />
            <p className="text-sm font-medium">Nessuna variazione sopra il {soglia}%</p>
            {/* La rassicurazione solo con fatture CONTATE (> 0). `null`/assente
                = "non lo so" (response in cache da prima del 17/09/2026): il
                messaggio resta al fatto nudo, senza affermare nulla sui prezzi. */}
            {(data.fatture_nel_periodo ?? 0) > 0 && (
              <p className="text-xs text-muted-foreground mt-1">
                I prezzi dei tuoi fornitori sono stabili nel {anno}.
              </p>
            )}
          </div>
        )
      )}

      {/* Loading iniziale */}
      {!data && loading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 rounded-lg border border-border bg-card animate-pulse" />
          ))}
        </div>
      )}

      {/* Lista card */}
      {variazioni.length > 0 && (
        <>
          <IntestazioneVariazioni />

          <div className="space-y-2">
            {visible.map((r) => {
              const key = chiavePreferito(r);
              return (
                <VariazioneCard
                  key={key}
                  r={r}
                  expanded={expandedKey === key}
                  preferito={preferiti.has(chiavePreferito(r))}
                  storico={expandedKey === key ? storico : null}
                  storicoLoading={expandedKey === key && storicoLoading}
                  onToggle={toggleCard}
                  onToggleStar={toggleStar}
                  onApriFattura={apriFattura}
                />
              );
            })}
          </div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                Pagina {safePage} di {totalPages} · {filtered.length.toLocaleString("it-IT")} variazioni
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={safePage <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  ← Precedente
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={safePage >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  Successiva →
                </Button>
              </div>
            </div>
          )}
          {filtered.length === 0 && vista === "preferiti" && nPreferiti === 0 && (
            <div className="rounded-lg border border-dashed border-border py-10 text-center">
              <Star className="size-7 text-incerto mx-auto mb-2" />
              <p className="text-sm font-medium">Non hai ancora prodotti preferiti</p>
              <p className="text-xs text-muted-foreground mt-1">Tocca la ⭐ accanto a un prodotto per seguirne i prezzi qui.</p>
            </div>
          )}
          {filtered.length === 0 && !(vista === "preferiti" && nPreferiti === 0) && (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun risultato per i filtri selezionati</p>
          )}
        </>
      )}

      <AnteprimaFatturaDialog
        open={anteprima !== null}
        fileOrigine={anteprima?.punto.fattura ?? null}
        numeroDocumento={anteprima?.punto.numero_documento}
        prodotto={anteprima?.prodotto ?? ""}
        onClose={() => setAnteprima(null)}
      />
    </div>
  );
}
