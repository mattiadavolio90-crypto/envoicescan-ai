"use client";

import React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Info, Lock, BarChart3, Upload, X as XIcon, Pencil, Sigma, Divide, ChevronRight } from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { toast } from "sonner";
import { formatEuro, formatEuroCompact, scorporoNetto, IVA_DIVISORE_10, IVA_DIVISORE_22 } from "./periodi";
import { CaricaRicaviDialog } from "./carica-ricavi-dialog";
import { CostoPersonaleDialog } from "./costo-personale-dialog";
import { CostoSpeseDialog, type TipoSpesaCella } from "./costo-spese-dialog";
import {
  meseSenzaCosti, pctIncidenza, pivotMedia, rowVal, scrollDaNodi,
  coloreBarraRisultato, RIGHE_MARGINI, righeVisibili, separatoreSopra, rigaPiede,
  gruppiEspansiIniziali, alternaGruppo, apreCostoPersonale,
  type MesePivot, type RigaMargini, type ChiaveRigaMargini, type GruppoMargini,
} from "@/lib/margini-aggregati";
import { InfoPopover } from "@/components/ui/info-popover";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { parseDecimaleItOZero } from "@/lib/format";
import { type Settore } from "@/lib/categorie-spesa";
import { commentoPerKpi, nomeKpiMerce } from "@/lib/kpi-margini";

type Commento = {
  kpi_nome: string;
  percentuale: string;
  commento: string;
  emoji: string;
  colore: string;
};

type AnalisiResponse = {
  mesi: MesePivot[];
  totali: MesePivot;
  fatt_medio_mensile: number;
  food_cost_perc: number;
  primo_margine_perc: number;
  spese_gen_perc: number;
  personale_perc: number;
  mol_perc: number;
  num_mesi_attivi: number;
  commenti: Commento[];
};

type EditableField =
  | "altri_costi_fb" | "altri_costi_spese"
  | "costo_dipendenti" | "costo_personale_extra" | "costo_personale_chiamata";

type Section = "ricavi" | "fb" | "spese" | "personale" | "margine";

type ValueColor = "white" | "sign";

type Aspetto = {
  label: string;
  type: "input-readonly" | "input-readonly-tooltip" | "input-editable" | "computed";
  field?: EditableField;
  section: Section;
  isMetric?: boolean;
  isMolMargin?: boolean;
  valueColor: ValueColor;              // colore dei valori nelle celle
};

type RowDef = RigaMargini & Aspetto;

// L'aspetto di ogni riga. Ordine, gruppo e testata NON stanno qui: li decide
// RIGHE_MARGINI (lib/margini-aggregati), che un test esegue. Il Record sulle
// chiavi obbliga a dare un aspetto a ogni riga della struttura.
const ASPETTO: Record<ChiaveRigaMargini, Aspetto> = {
  fatturato_netto:          { label: "Incasso",               type: "computed", section: "ricavi", isMetric: true, valueColor: "white" },
  fatturato_iva10:          { label: "Ricavi IVA 10%",        type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  fatturato_iva22:          { label: "Ricavi IVA 22%",        type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  altri_ricavi_noiva:       { label: "Altri ricavi (no IVA)", type: "input-readonly-tooltip", section: "ricavi", valueColor: "white" },
  costi_fb_totali:          { label: "Spese F&B",             type: "computed", section: "fb", isMetric: true, valueColor: "white" },
  costi_fb_auto:            { label: "Costi F&B (Fatture)",   type: "input-readonly", section: "fb", valueColor: "white" },
  altri_costi_fb:           { label: "Altri Costi F&B",       type: "input-editable", field: "altri_costi_fb", section: "fb", valueColor: "white" },
  primo_margine:            { label: "Margine F&B",           type: "computed", section: "margine", isMetric: true, valueColor: "sign" },
  costi_spese_totali:       { label: "Spese generali",        type: "computed", section: "spese", isMetric: true, valueColor: "white" },
  costi_spese_auto:         { label: "Spese Gen. (Fatture)",  type: "input-readonly", section: "spese", valueColor: "white" },
  altri_costi_spese:        { label: "Altre Spese Generali",  type: "input-editable", field: "altri_costi_spese", section: "spese", valueColor: "white" },
  costi_personale:          { label: "Costo personale",       type: "computed", section: "personale", isMetric: true, valueColor: "white" },
  costo_dipendenti:         { label: "Lordo",                 type: "input-editable", field: "costo_dipendenti", section: "personale", valueColor: "white" },
  costo_personale_extra:    { label: "Ore extra",             type: "input-editable", field: "costo_personale_extra", section: "personale", valueColor: "white" },
  costo_personale_chiamata: { label: "Chiamata",              type: "input-editable", field: "costo_personale_chiamata", section: "personale", valueColor: "white" },
  mol:                      { label: "Guadagno finale (MOL)", type: "computed", section: "margine", isMetric: true, isMolMargin: true, valueColor: "sign" },
};

const ROWS: RowDef[] = RIGHE_MARGINI.map((r) => ({ ...r, ...ASPETTO[r.key] }));

// Separatori e piede si ricavano dalla RIGA, non dalla posizione: con i gruppi
// apribili la stessa riga cambia indice a ogni apertura. Aria (non un bordo
// piu' spesso, dal 23/09/2026) sopra ogni blocco nuovo — `separatoreSopra` —
// e respiro sul MOL, il punto d'arrivo della lettura come il totale in fondo a
// una fattura — `rigaPiede`.
function padYRiga(row: RowDef, precedente: RowDef | null): string {
  if (rigaPiede(row)) return "py-3.5";
  if (separatoreSopra(row, precedente)) return "pt-4 pb-2";
  return "py-2";
}

// Colore dei valori (e della % incidenza) in base al value-color mode.
//
// `incompleto`: il mese ha ricavi ma nessun costo caricato. Il giudizio di segno
// (verde = bene) si spegne, il numero resta. Senza questo gate la colonna piu'
// verde dell'anno era quella dei mesi in cui mancavano le fatture — misurato il
// 23/09/2026 su SUSHILAND: gennaio e febbraio, «Costi F&B —», MOL 384.120 EUR
// all'86% e 321.619 EUR all'84%, entrambi in verde. Nella stessa pagina
// «Analisi visiva» diceva gia' «Nessun giudizio: 4 mesi su 9 non ha costi
// registrati» (il gate esiste dal 16/09 lato worker, margini.py:914): la tabella
// e il commento si contraddicevano a 400px di distanza.
function valueColorCls(vc: ValueColor, raw: number, incompleto = false): string {
  if (vc === "sign") {
    if (incompleto) return "text-muted-foreground";
    return raw > 0
      ? "text-positivo"
      : raw < 0
      ? "text-negativo"
      : "text-muted-foreground";
  }
  // I totali dei gruppi sono dati senza giudizio: nel colore del testo, in
  // grassetto. Il colore resta solo dove c'e' un giudizio, Margine F&B e MOL
  // (Mattia, 5/10/2026: a gruppi chiusi la tabella era tutta azzurra).
  return ""; // white = foreground
}

// Contorno azzurro «retroilluminato» di tabella e Analisi visiva (Mattia, 5/10):
// bordo primary tenue + alone diffuso dello stesso colore, in entrambi i temi.
const BORDO_LUMINOSO =
  "border border-primary/40 shadow-[0_0_18px_-6px_color-mix(in_oklab,var(--primary)55%,transparent)]";

const ANNO_MESE_CORRENTE = (() => {
  const d = new Date();
  return { anno: d.getFullYear(), mese: d.getMonth() + 1 };
})();

type Props = {
  dataDa: string;
  dataA: string;
  settore?: Settore | null;
};

export function CalcoloTab({ dataDa, dataA, settore }: Props) {
  const [data, setData] = useState<AnalisiResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [caricaOpen, setCaricaOpen] = useState(false);
  const [dettaglioOpen, setDettaglioOpen] = useState(false);
  const [dettaglioMeseSel, setDettaglioMeseSel] = useState<{ anno: number; mese: number; label: string } | null>(null);
  const [costoPersMese, setCostoPersMese] = useState<MesePivot | null>(null);
  const [speseCella, setSpeseCella] = useState<{ mese: MesePivot; tipo: TipoSpesaCella } | null>(null);
  const [vista, setVista] = useState<"totale" | "media">("totale");
  // Gruppi aperti: stato React e basta, niente localStorage — a ogni apertura
  // della pagina la tabella torna corta (decisione 6 del 04/10/2026).
  const [espansi, setEspansi] = useState<GruppoMargini[]>(gruppiEspansiIniziali);
  const alterna = useCallback(
    (g: GruppoMargini) => setEspansi((e) => alternaGruppo(e, g)),
    [],
  );
  const righe = useMemo(() => righeVisibili(ROWS, espansi), [espansi]);

  const reqIdRef = useRef(0);
  const load = useCallback(async () => {
    const myReq = ++reqIdRef.current;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/margini/analisi?${new URLSearchParams({ data_da: dataDa, data_a: dataA })}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error();
      const d: AnalisiResponse = await res.json();
      if (myReq === reqIdRef.current) setData(d);
    } catch {
      if (myReq === reqIdRef.current) toast.error("Errore nel caricamento margini");
    } finally {
      if (myReq === reqIdRef.current) setLoading(false);
    }
  }, [dataDa, dataA]);

  useEffect(() => {
    load();
  }, [load]);

  // Mostra solo mesi con almeno un valore (ricavi o costi)
  const mesiVisibili = useMemo(() => {
    if (!data) return [];
    return data.mesi.filter(
      (m) =>
        m.fatturato_netto > 0 ||
        m.costi_fb_totali > 0 ||
        m.costi_spese_totali > 0 ||
        m.costi_personale > 0,
    );
  }, [data]);

  // Il periodo e' incompleto se lo e' anche un solo mese: sull'aggregato la
  // condizione sarebbe sempre falsa (vedi TotalCell).
  const periodoIncompleto = useMemo(
    () => mesiVisibili.some(meseSenzaCosti),
    [mesiVisibili],
  );

  // All'apertura la tabella mostra il MESE CORRENTE, non gennaio.
  //
  // Con nove mesi a 140px la tabella e' piu' larga dello schermo: entrando si
  // vedeva Gen-Lug e il mese in corso restava fuori a destra, da cercare a mano
  // ogni volta. I mesi passati non spariscono: si scorre indietro.
  //
  // `scrollLeft` diretto e non `scrollIntoView()`: quest'ultimo scrolla anche
  // l'ANTENATO, cioe' porterebbe la pagina a meta' tabella saltando le tessere
  // KPI. Qui si muove solo il contenitore orizzontale.
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const meseCorrenteRef = useRef<HTMLTableCellElement | null>(null);
  const giaScrollato = useRef(false);

  useEffect(() => {
    if (giaScrollato.current) return;
    const scroller = scrollerRef.current;
    const cella = meseCorrenteRef.current;
    if (!scroller || !cella) return;
    // Il conto E LA LARGHEZZA della colonna Totale stanno in
    // lib/margini-aggregati (scrollDaNodi): dentro l'useEffect nessun test
    // poteva eseguirli.
    scroller.scrollLeft = scrollDaNodi(scroller, cella);
    // Una volta sola: dopo comanda il cliente. Riscrollare a ogni ricalcolo
    // (cambio Totale/Media, salvataggio di una cella) gli strapperebbe la vista
    // da sotto le mani mentre guarda un altro mese.
    giaScrollato.current = true;
  }, [mesiVisibili]);

  // Colonna riepilogo: totali grezzi oppure medie mensili sul periodo.
  const isMedia = vista === "media";
  const totaliRiepilogo = useMemo(() => {
    if (!data) return null;
    return isMedia ? pivotMedia(data.totali, data.num_mesi_attivi) : data.totali;
  }, [data, isMedia]);

  async function postCella(anno: number, mese: number, field: EditableField, value: number) {
    const res = await fetch("/api/margini/cella", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ anno, mese, field, value }),
    });
    if (!res.ok) throw new Error();
  }

  async function saveCell(
    anno: number,
    mese: number,
    field: EditableField,
    value: number,
    prevValue: number,
  ) {
    try {
      await postCella(anno, mese, field, value);
      toast.success("Salvato", {
        action: {
          label: "Annulla",
          onClick: async () => {
            try {
              await postCella(anno, mese, field, prevValue);
              toast.success("Modifica annullata");
              load();
            } catch {
              toast.error("Impossibile annullare");
            }
          },
        },
      });
      // Reload to refresh derived metrics
      load();
    } catch {
      toast.error("Errore nel salvataggio");
    }
  }

  if (loading && !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        Caricamento dati margini...
      </div>
    );
  }

  if (!data || mesiVisibili.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center space-y-2">
        <p className="text-sm font-medium">Nessun dato margini nel periodo selezionato</p>
        <p className="text-xs text-muted-foreground">
          Usa &quot;Carica ricavi&quot; per inserire i ricavi o carica fatture per popolare automaticamente i costi.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <InfoPopover title="Come compilare la tabella margini">
          <p className="text-muted-foreground">
            La tabella mostra i totali: <em>Incasso</em>, <em>Spese F&amp;B</em>, <em>Spese generali</em> e <em>Costo personale</em>, con <em>Margine F&amp;B</em> e <em>Guadagno finale (MOL)</em> sempre in vista. Clicca il nome di un totale (la freccia) per aprire le voci che lo compongono; si richiude a ogni nuova visita.
          </p>
          <div className="space-y-1.5 text-muted-foreground">
            <p><strong className="text-foreground">Voci automatiche</strong> — es. <em>Costi F&amp;B (Fatture)</em> e <em>Spese Gen. (Fatture)</em>: arrivano dalle tue fatture, non si modificano.</p>
            <p><strong className="text-foreground">Voci modificabili</strong> — cliccale per inserire un valore.</p>
            <p className="pl-3">· <strong className="text-foreground">Costo personale</strong>: tre voci che si sommano — <em>Lordo</em>, <em>Ore extra</em> e <em>Chiamata</em>. Clicca la cella del mese, anche sul totale a gruppo chiuso, per <strong className="text-foreground">recuperarle dal tab Agenda → Personale</strong> (turni o stipendi del mese) oppure scriverle a mano.</p>
            <p className="pl-3">· <strong className="text-foreground">Altre Spese / Altri Costi F&amp;B</strong>: recupera dal tab <strong className="text-foreground">Agenda → Spese</strong> o inserisci un importo a mano.</p>
            <p><strong className="text-foreground">Totali in azzurro</strong>: calcolati in automatico dalle voci del loro gruppo. Il colore resta solo su <em>Margine F&amp;B</em> e <em>Guadagno finale (MOL)</em>: verde se positivo, rosso se negativo, grigio nei mesi senza costi caricati.</p>
          </div>
          <div className="border-t border-border pt-2 text-muted-foreground">
            <p>Usa <strong className="text-foreground">Totale / Media</strong> per vedere la somma del periodo o la media mensile, e <strong className="text-foreground">Carica ricavi</strong> per inserire gli incassi.</p>
          </div>
        </InfoPopover>
        <p className="text-xs text-muted-foreground flex items-center gap-1.5">
          <Info className="size-3" />
          Apri un totale per vederne le voci; quelle modificabili si cliccano.
        </p>
        {/* Toggle Totale / Media */}
        <div className="ml-auto inline-flex items-center rounded-md border border-input p-0.5 text-xs font-semibold">
          <button
            onClick={() => setVista("totale")}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
              vista === "totale" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
            }`}
            title="Somma del periodo"
          >
            <Sigma className="size-3" />
            Totale
          </button>
          <button
            onClick={() => setVista("media")}
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
              vista === "media" ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
            }`}
            title={`Media mensile sui ${data?.num_mesi_attivi ?? 0} mesi con dati`}
          >
            <Divide className="size-3" />
            Media
          </button>
        </div>
        <button
          onClick={() => { setDettaglioMeseSel(mesiVisibili[mesiVisibili.length - 1] ?? null); setDettaglioOpen(true); }}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md border border-input hover:bg-muted transition-colors"
        >
          <BarChart3 className="size-3" />
          Dettaglio giornaliero
        </button>
        <button
          onClick={() => setCaricaOpen(true)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <Upload className="size-3" />
          Carica ricavi
        </button>
      </div>

      <CaricaRicaviDialog
        open={caricaOpen}
        onOpenChange={setCaricaOpen}
        dataDa={dataDa}
        dataA={dataA}
        onImported={load}
      />

      {dettaglioOpen && (
        <DettaglioGiornalieroDialog
          mese={dettaglioMeseSel}
          mesi={mesiVisibili}
          onMeseChange={setDettaglioMeseSel}
          onClose={() => setDettaglioOpen(false)}
        />
      )}

      {/* Tabella trasposta — desktop */}
      <div className={`hidden md:block rounded-lg bg-card overflow-hidden ${BORDO_LUMINOSO}`}>
        <div className="overflow-x-auto" ref={scrollerRef}>
          <table className="w-full table-auto text-[15px] border-collapse">
            <colgroup>
              <col className="w-[220px]" />
              {mesiVisibili.map((m) => (
                <col key={`c-${m.anno}-${m.mese}`} className="w-[140px]" />
              ))}
              <col className="w-[160px]" />
            </colgroup>
            {/* Cappello: bordo inferiore pieno invece del filo, cosi' l'intestazione
                sembra appoggiata sopra il corpo invece che disegnata dentro. */}
            <thead className="bg-muted/40 border-b border-border">
              <tr className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {/* Sfondo OPACO, non bg-muted/40: una cella sticky semitrasparente
                    lascia trasparire le intestazioni dei mesi che le scorrono sotto. */}
                <th className="sticky left-0 z-20 bg-[color-mix(in_oklab,var(--color-muted)40%,var(--color-card))] text-left px-3 py-2.5 font-semibold border-r border-border">
                  Voce
                </th>
                {mesiVisibili.map((m) => {
                  const isCurrent = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
                  return (
                    <th
                      key={`${m.anno}-${m.mese}`}
                      ref={isCurrent ? meseCorrenteRef : undefined}
                      className={`text-right px-3 py-2.5 font-semibold ${
                        isCurrent
                          ? "text-primary-text border-l border-r border-primary/50 border-t-2 border-t-primary bg-[color-mix(in_oklab,var(--color-muted)55%,var(--color-card))]"
                          : "border-r border-border"
                      }`}
                    >
                      {isCurrent && <span className="mr-1 inline-block size-1.5 rounded-full bg-primary align-middle" />}
                      {m.label}
                    </th>
                  );
                })}
                <th className="sticky right-0 z-20 bg-[color-mix(in_oklab,var(--primary)8%,var(--color-card))] text-right px-3 py-2.5 font-bold border-l-2 border-r border-primary text-primary-text">
                  {isMedia ? "Media" : "Totale"}
                </th>
              </tr>
            </thead>
            <tbody>
              {righe.map((row, ri) => {
                const isMetric = row.isMetric;
                const piede = rigaPiede(row);
                // Aria sopra i blocchi e respiro sul piede (il MOL), ricavati
                // dalla riga e dalla riga visibile sopra (padYRiga). Deciso QUI e
                // passato alle celle: messo sul <tr> come `[&>*]:py-3.5`
                // competeva col `py-2` scritto sulle <td> a pari specificita', e
                // vinceva l'ultimo nel CSS generato.
                const padY = padYRiga(row, righe[ri - 1] ?? null);
                return (
                  <tr
                    key={row.key}
                    className={`border-t border-border ${
                      isMetric ? "font-semibold bg-muted/[0.04]" : ""
                    } ${
                      piede
                        ? "border-t-2 border-t-border bg-[color-mix(in_oklab,var(--primary)5%,var(--color-card))]"
                        : ""
                    }`}
                  >
                    {/* Le righe di DETTAGLIO vanno in grigio e rientrate sotto la
                        loro testata; testate, Margine F&B e MOL restano piene. A
                        gruppi chiusi la colonna mostra sei righe azzurre — le
                        quattro testate, il margine e il MOL — che disegnano la
                        struttura del conto economico. */}
                    <td
                      className={`sticky left-0 z-10 ${row.gruppo && !row.testata ? "pl-7 pr-3" : "px-3"} ${padY} border-r border-border whitespace-nowrap ${
                        piede
                          ? "bg-[color-mix(in_oklab,var(--primary)5%,var(--color-card))] text-base"
                          : "bg-card"
                      } ${
                        isMetric ? "font-bold text-primary-text" : "text-muted-foreground"
                      }`}
                    >
                      <EtichettaRiga row={row} espansi={espansi} onAlterna={alterna} />
                    </td>
                    {mesiVisibili.map((m) => {
                      const isCurrent = m.anno === ANNO_MESE_CORRENTE.anno && m.mese === ANNO_MESE_CORRENTE.mese;
                      return (
                        <Cell
                          key={`${m.anno}-${m.mese}`}
                          row={row}
                          mese={m}
                          isCurrent={isCurrent}
                          isPiede={piede}
                          padY={padY}
                          onSave={saveCell}
                          onOpenCosto={setCostoPersMese}
                          onOpenSpese={(mese, tipo) => setSpeseCella({ mese, tipo })}
                        />
                      );
                    })}
                    {/* Total / Media column */}
                    <TotalCell row={row} totali={totaliRiepilogo ?? data.totali} incompleto={periodoIncompleto} padY={padY} />
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Vista mobile — card per mese */}
      <div className="md:hidden">
        <MobileMeseView
          mesi={mesiVisibili}
          totali={totaliRiepilogo ?? data.totali}
          isMedia={isMedia}
          righe={righe}
          espansi={espansi}
          onAlterna={alterna}
          onSave={saveCell}
          onOpenCosto={setCostoPersMese}
          onOpenSpese={(mese, tipo) => setSpeseCella({ mese, tipo })}
        />
      </div>

      {/* Analisi visiva: cascata conto economico + gauge + commenti */}
      <AnalisiVisiva data={data} totaliVista={totaliRiepilogo ?? data.totali} isMedia={isMedia} settore={settore} incompleto={periodoIncompleto} />

      {costoPersMese && (
        <CostoPersonaleDialog
          open
          anno={costoPersMese.anno}
          mese={costoPersMese.mese}
          label={costoPersMese.label}
          costoDipendenti={costoPersMese.costo_dipendenti}
          costoExtra={costoPersMese.costo_personale_extra}
          costoChiamata={costoPersMese.costo_personale_chiamata}
          onClose={() => setCostoPersMese(null)}
          onSaved={load}
        />
      )}

      {speseCella && (
        <CostoSpeseDialog
          open
          tipo={speseCella.tipo}
          anno={speseCella.mese.anno}
          mese={speseCella.mese.mese}
          label={speseCella.mese.label}
          valore={speseCella.tipo === "fb" ? speseCella.mese.altri_costi_fb : speseCella.mese.altri_costi_spese}
          onClose={() => setSpeseCella(null)}
          onSaved={load}
        />
      )}
    </div>
  );
}

/* ============================================================ */
/* Etichetta: la testata di un gruppo apre e chiude il dettaglio */
/* ============================================================ */
function EtichettaRiga({
  row,
  espansi,
  onAlterna,
  className = "",
}: {
  row: RowDef;
  espansi: readonly GruppoMargini[];
  onAlterna: (g: GruppoMargini) => void;
  className?: string;
}) {
  if (!row.testata || !row.gruppo) return <span className={className}>{row.label}</span>;
  const gruppo = row.gruppo;
  const aperto = espansi.includes(gruppo);
  return (
    <button
      type="button"
      onClick={() => onAlterna(gruppo)}
      aria-expanded={aperto}
      title={aperto ? `Chiudi il dettaglio di ${row.label}` : `Apri il dettaglio di ${row.label}`}
      className={`inline-flex items-center gap-1.5 text-left rounded outline-none focus-visible:ring-1 focus-visible:ring-primary hover:underline underline-offset-4 ${className}`}
    >
      <ChevronRight
        aria-hidden="true"
        className={`size-3.5 shrink-0 text-primary-text transition-transform ${aperto ? "rotate-90" : ""}`}
      />
      {row.label}
    </button>
  );
}

/* ============================================================ */
/* Cell                                                          */
/* ============================================================ */
function Cell({
  row,
  mese,
  isCurrent,
  isPiede,
  padY,
  onSave,
  onOpenCosto,
  onOpenSpese,
}: {
  row: RowDef;
  mese: MesePivot;
  isCurrent: boolean;
  isPiede: boolean;
  padY: string;
  onSave: (anno: number, mese: number, field: EditableField, value: number, prevValue: number) => void;
  onOpenCosto: (m: MesePivot) => void;
  onOpenSpese: (m: MesePivot, tipo: TipoSpesaCella) => void;
}) {
  const raw = rowVal(row, mese);
  const isMetric = row.isMetric;
  const colorCls = valueColorCls(row.valueColor, raw, meseSenzaCosti(mese));
  const pct = pctIncidenza(raw, mese.fatturato_netto);
  const display = raw === 0 ? "—" : formatEuro(raw);

  // Il mese corrente ha una corsia propria per tutta l'altezza della tabella.
  //
  // Il fondo e' un GRIGIO (muted), non il blu: la colonna Totale usa gia'
  // `--primary` all'8% e due colonne azzurre a pochi centimetri si leggono come
  // la stessa cosa. Qui il blu resta solo sui bordi e sul pallino
  // nell'intestazione — colore uguale, canale diverso.
  const currentCls = isCurrent
    ? `border-l border-r border-primary/50 ${
        // Sul piede la riga ha gia' il suo fondo e deve restare CONTINUA: una
        // corsia grigia in mezzo lo spezzerebbe in due tronconi.
        isPiede ? "" : "bg-[color-mix(in_oklab,var(--color-muted)38%,var(--color-card))]"
      }`
    : "border-r border-border";

  // Righe personale (e la loro testata, anche a gruppo chiuso): cella
  // cliccabile che apre il widget (recupera da Personale o manuale)
  if (apreCostoPersonale(row)) {
    return (
      <td className={`text-right p-0 align-middle ${currentCls}`}>
        <button
          type="button"
          onClick={() => onOpenCosto(mese)}
          title="Imposta costo (recupera da Personale o inserisci a mano)"
          className={`w-full px-3 ${padY} text-right tabular-nums hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset outline-none transition-colors group/cella`}
        >
          <span className={`inline-flex items-center justify-end gap-1 ${isMetric ? "font-bold" : ""} ${colorCls}`}>
            {display === "—" ? <span className="text-muted-foreground/60">—</span> : display}
            <Pencil className="size-3 opacity-0 group-hover/cella:opacity-40 transition-opacity" />
          </span>
          {pct && <span className="block text-[11px] tabular-nums text-muted-foreground">{pct}</span>}
        </button>
      </td>
    );
  }

  // Righe spese extra (F&B / Generali): cella cliccabile che apre il widget (recupera dal tab Spese o manuale)
  if (row.type === "input-editable" && (row.field === "altri_costi_fb" || row.field === "altri_costi_spese")) {
    const tipo: TipoSpesaCella = row.field === "altri_costi_fb" ? "fb" : "generale";
    return (
      <td className={`text-right p-0 align-middle ${currentCls}`}>
        <button
          type="button"
          onClick={() => onOpenSpese(mese, tipo)}
          title="Imposta importo (recupera dal tab Spese o inserisci a mano)"
          className={`w-full px-3 ${padY} text-right tabular-nums hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset outline-none transition-colors group/cella`}
        >
          <span className="inline-flex items-center justify-end gap-1">
            {display === "—" ? <span className="text-muted-foreground/60">—</span> : display}
            <Pencil className="size-3 opacity-0 group-hover/cella:opacity-40 transition-opacity" />
          </span>
          {pct && <span className="block text-[11px] tabular-nums text-muted-foreground">{pct}</span>}
        </button>
      </td>
    );
  }

  if (row.type === "input-editable" && row.field) {
    return (
      <EditableCell
        value={raw}
        netto={mese.fatturato_netto}
        isCurrent={isCurrent}
        onSave={(v) => onSave(mese.anno, mese.mese, row.field!, v, raw)}
      />
    );
  }

  const tooltip =
    row.type === "input-readonly-tooltip" ? "Modifica da Carica ricavi"
    : row.type === "input-readonly" ? "Calcolato dalle fatture caricate (incluse le quote di costi di gruppo ripartite su questa sede)"
    : undefined;
  const showLock = row.type === "input-readonly-tooltip" || row.type === "input-readonly";

  return (
    <td className={`text-right px-3 ${padY} align-middle ${currentCls}`}>
      <div
        title={tooltip}
        className={`inline-flex items-center justify-end gap-1 tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls} ${showLock ? "cursor-help" : ""}`}
      >
        {display}
        {showLock && <Lock className="size-3 opacity-30" />}
      </div>
      {pct && <div className="text-[11px] tabular-nums text-muted-foreground">{pct}</div>}
    </td>
  );
}

function EditableCell({
  value,
  netto,
  isCurrent,
  onSave,
}: {
  value: number;
  netto: number;
  isCurrent: boolean;
  onSave: (v: number) => void;
}) {
  const initStr = value > 0 ? String(Math.round(value)) : "";
  const [local, setLocal] = useState(initStr);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setLocal(value > 0 ? String(Math.round(value)) : "");
  }, [value]);

  async function commit() {
    const newVal = parseDecimaleItOZero(local);
    if (Math.abs(newVal - value) < 0.001) return;
    setSaving(true);
    try {
      await onSave(newVal);
      setSaved(true);
      setTimeout(() => setSaved(false), 800);
    } finally {
      setSaving(false);
    }
  }

  const liveVal = parseDecimaleItOZero(local);
  const pct = pctIncidenza(liveVal, netto);

  const currentCls = isCurrent
    ? "border-l border-r border-primary/50"
    : "border-r border-border";

  return (
    <td className={`p-0 align-middle ${currentCls}`}>
      <input
        type="number"
        step="1"
        min="0"
        value={local}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setLocal(value > 0 ? String(Math.round(value)) : "");
            (e.target as HTMLInputElement).blur();
          }
        }}
        placeholder="—"
        className={`w-full px-3 pt-2 pb-0 text-right tabular-nums bg-transparent border-0 outline-none transition-colors text-[15px] ${
          saved
            ? "bg-positivo/10"
            : saving
            ? "bg-primary/5"
            : "hover:bg-muted/40 focus:bg-background focus:ring-1 focus:ring-primary focus:ring-inset"
        }`}
      />
      {pct && (
        <div className="px-3 pb-1.5 text-right text-[11px] tabular-nums text-muted-foreground">{pct}</div>
      )}
    </td>
  );
}

// `incompleto` arriva da fuori e NON si ricava da `totali`: sull'aggregato i
// costi di un mese solo bastano a far risultare il periodo "con costi" — e' lo
// stesso inganno che il worker descrive a margini.py:895 («basta che qualche
// mese i costi ce li abbia perche' la condizione sia falsa»). Il periodo e'
// incompleto se lo e' anche UN solo mese.
function TotalCell({
  row,
  totali,
  incompleto,
  padY,
}: {
  row: RowDef;
  totali: MesePivot;
  incompleto: boolean;
  padY: string;
}) {
  const raw = rowVal(row, totali);
  const display = raw === 0 ? "—" : formatEuro(raw);
  const isMetric = row.isMetric;
  const colorCls = valueColorCls(row.valueColor, raw, incompleto);
  const pct = pctIncidenza(raw, totali.fatturato_netto);

  return (
    <td className={`sticky right-0 z-10 bg-[color-mix(in_oklab,var(--primary)8%,var(--color-card))] text-right px-3 ${padY} tabular-nums border-l-2 border-r border-primary align-middle`}>
      <div className={`tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls}`}>{display}</div>
      {pct && <div className="text-[11px] tabular-nums text-muted-foreground">{pct}</div>}
    </td>
  );
}

/* ============================================================ */
/* Vista mobile — card per mese                                  */
/* ============================================================ */
function MobileMeseView({
  mesi,
  totali,
  isMedia,
  righe,
  espansi,
  onAlterna,
  onSave,
  onOpenCosto,
  onOpenSpese,
}: {
  mesi: MesePivot[];
  totali: MesePivot;
  isMedia: boolean;
  righe: RowDef[];
  espansi: readonly GruppoMargini[];
  onAlterna: (g: GruppoMargini) => void;
  onSave: (anno: number, mese: number, field: EditableField, value: number, prevValue: number) => void;
  onOpenCosto: (m: MesePivot) => void;
  onOpenSpese: (m: MesePivot, tipo: TipoSpesaCella) => void;
}) {
  const [selIdx, setSelIdx] = useState(mesi.length - 1);
  const isTotal = selIdx >= mesi.length;
  const current = isTotal ? totali : mesi[Math.min(selIdx, mesi.length - 1)];
  // Sul totale vale la regola del periodo (un solo mese scoperto lo rende
  // incompleto); sul singolo mese vale quel mese. Vedi TotalCell.
  const incompleto = isTotal ? mesi.some(meseSenzaCosti) : meseSenzaCosti(current);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <label className="text-xs text-muted-foreground font-medium">Mese</label>
        <select
          value={selIdx}
          onChange={(e) => setSelIdx(Number(e.target.value))}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm"
        >
          {mesi.map((m, i) => (
            <option key={`${m.anno}-${m.mese}`} value={i}>{m.label}</option>
          ))}
          <option value={mesi.length}>{isMedia ? "Media periodo" : "Totale periodo"}</option>
        </select>
      </div>

      <div className={`rounded-lg bg-card divide-y divide-border overflow-hidden ${BORDO_LUMINOSO}`}>
        {righe.map((row, ri) => {
          const raw = rowVal(row, current);
          const isMetric = row.isMetric;
          const editable = row.type === "input-editable" && !isTotal;
          const isPersonale = apreCostoPersonale(row);
          const isSpesa = row.type === "input-editable" && (row.field === "altri_costi_fb" || row.field === "altri_costi_spese");
          const tipoSpesa: TipoSpesaCella | null = row.field === "altri_costi_fb" ? "fb" : row.field === "altri_costi_spese" ? "generale" : null;
          const colorCls = valueColorCls(row.valueColor, raw, incompleto);
          const pct = pctIncidenza(raw, current.fatturato_netto);

          return (
            <div
              key={row.key}
              className={`flex items-center justify-between gap-3 ${
                separatoreSopra(row, righe[ri - 1] ?? null) ? "pt-4 pb-2.5" : "py-2.5"
              } ${row.gruppo && !row.testata ? "pl-7 pr-3" : "px-3"}`}
            >
              <EtichettaRiga
                row={row}
                espansi={espansi}
                onAlterna={onAlterna}
                className={`text-sm ${isMetric ? "font-semibold text-primary-text" : ""}`}
              />
              {isPersonale && !isTotal ? (
                <button
                  type="button"
                  onClick={() => onOpenCosto(current)}
                  className={`inline-flex items-center gap-1.5 text-sm tabular-nums px-2 py-1 rounded-md border border-input hover:bg-muted transition-colors ${raw === 0 ? "" : colorCls}`}
                >
                  {raw === 0 ? "Imposta" : formatEuro(raw)}
                  <Pencil className="size-3 opacity-40" />
                </button>
              ) : isSpesa && tipoSpesa && !isTotal ? (
                <button
                  type="button"
                  onClick={() => onOpenSpese(current, tipoSpesa)}
                  className="inline-flex items-center gap-1.5 text-sm tabular-nums px-2 py-1 rounded-md border border-input hover:bg-muted transition-colors"
                >
                  {raw === 0 ? "Imposta" : formatEuro(raw)}
                  <Pencil className="size-3 opacity-40" />
                </button>
              ) : editable ? (
                <MobileEditInput
                  value={raw}
                  onSave={(v) => onSave(current.anno, current.mese, row.field!, v, raw)}
                />
              ) : (
                <span className={`text-sm shrink-0 text-right tabular-nums ${isMetric ? "font-bold" : ""} ${colorCls}`}>
                  {raw === 0 ? "—" : formatEuro(raw)}
                  {pct && <span className="block text-[10px] text-muted-foreground">{pct}</span>}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MobileEditInput({
  value,
  onSave,
}: {
  value: number;
  onSave: (v: number) => void | Promise<void>;
}) {
  const [local, setLocal] = useState(value > 0 ? String(Math.round(value)) : "");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setLocal(value > 0 ? String(Math.round(value)) : "");
  }, [value]);

  async function commit() {
    const newVal = parseDecimaleItOZero(local);
    if (Math.abs(newVal - value) < 0.001) return;
    await onSave(newVal);
    setSaved(true);
    setTimeout(() => setSaved(false), 800);
  }

  return (
    <input
      type="number"
      step="1"
      min="0"
      value={local}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setLocal(value > 0 ? String(Math.round(value)) : "");
          (e.target as HTMLInputElement).blur();
        }
      }}
      placeholder="—"
      className={`w-32 h-8 px-2 text-right tabular-nums rounded border bg-transparent outline-none transition-colors text-sm ${
        saved
          ? "border-positivo bg-positivo/10"
          : "border-input focus:border-primary focus:bg-background"
      }`}
    />
  );
}

/* ============================================================ */
/* Analisi visiva: cascata conto economico + gauge + commenti    */
/* ============================================================ */
const GAUGE_GREEN = "var(--positivo)";
const GAUGE_AMBER = "var(--incerto)";
const GAUGE_ROSE = "var(--negativo)";
const GAUGE_NEUTRAL = "var(--muted-foreground)";

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v));
}

function AnalisiVisiva({
  data,
  totaliVista,
  isMedia,
  settore,
  incompleto,
}: {
  data: AnalisiResponse;
  totaliVista: MesePivot;
  isMedia: boolean;
  settore?: Settore | null;
  incompleto: boolean;
}) {
  const t = totaliVista;
  const hasData = t.fatturato_netto > 0 || t.costi_fb_totali > 0;

  // Il colore segue il giudizio del worker (l'emoji di _valuta_soglia_margine),
  // non una seconda tabella di soglie qui. Le due divergevano: il Python ha 4
  // bande (verde/giallo/arancio/rosso), il TS ne aveva 3, e sul MOL i due
  // giudizi si contraddicevano su tutta la banda 5-20% — il gauge poteva essere
  // ambra con il commento accanto rosso. La palette resta quella del gauge.
  // Il nome del KPI merce lo decide il worker in base al settore
  // (_nome_kpi_per_settore, routers/margini.py): un negozio riceve «Costo
  // Merce». Cercare qui il letterale "Food Cost" non troverebbe il suo
  // commento, e il gauge perderebbe colore E diagnosi senza un errore — e'
  // il difetto che il commento sopra descrive gia' per "Costi Gestione".
  const fc = data.food_cost_perc;
  const labelMerce = nomeKpiMerce(settore);
  const fcColor = coloreDaCommento(data.commenti, labelMerce);
  const pm = data.primo_margine_perc;
  const pmColor = coloreDaCommento(data.commenti, "1° Margine");
  const sg = data.spese_gen_perc;
  const sgColor = coloreDaCommento(data.commenti, "Spese Generali");
  const mol = data.mol_perc;
  const molColor = coloreDaCommento(data.commenti, "MOL");

  return (
    <div className={`rounded-lg bg-card p-4 space-y-5 ${BORDO_LUMINOSO}`}>
      <h3 className="text-base font-semibold flex items-center gap-1.5">
        <BarChart3 className="size-4 text-primary" />
        Analisi visiva
        {isMedia && (
          <span className="text-[11px] font-medium text-primary-text bg-accent px-2 py-0.5 rounded-full">
            valori medi mensili
          </span>
        )}
      </h3>

      {!hasData ? (
        <p className="text-sm text-muted-foreground py-6 text-center">
          Inserisci ricavi e carica fatture per generare l&apos;analisi.
        </p>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-20 items-stretch">
          {/* Cascata P&L */}
          <div className="flex flex-col justify-around">
            <CascataPL t={t} incompleto={incompleto} />
          </div>

          {/* Gauge con diagnosi integrata */}
          <div className="flex flex-col gap-0 divide-y divide-border">
            {[
              { label: labelMerce,       kpiNome: labelMerce,        valueText: `${fc.toFixed(0)}%`,  fraction: clamp01(fc / 100),  trackColor: "var(--grafico-1)", valueColor: fcColor },
              { label: "Margine F&B",    kpiNome: "1° Margine",      valueText: `${pm.toFixed(0)}%`,  fraction: clamp01(pm / 100),  trackColor: "var(--grafico-1)", valueColor: pmColor },
              { label: "Spese Generali", kpiNome: "Spese Generali",  valueText: `${sg.toFixed(0)}%`,  fraction: clamp01(sg / 100),  trackColor: "var(--grafico-1)", valueColor: sgColor },
              { label: "MOL",            kpiNome: "MOL",             valueText: `${mol.toFixed(0)}%`, fraction: clamp01(mol / 100), trackColor: "var(--grafico-1)", valueColor: molColor },
            ].map((g) => {
              // Il match e' sul nome che manda /api/margini/analisi (margini.py:1209-1213),
              // non sull'etichetta a video: il gauge si chiamava "Costi Gestione" e
              // cercava se stesso mentre il worker manda "Spese Generali", restando
              // senza emoji ne commento. Dal 18/09/2026 label e kpiNome NON coincidono
              // piu' per primo_margine (a video "Margine F&B", chiave "1° Margine"):
              // il match resta sul nome del worker, e' quello il contratto. Rinominare
              // kpiNome per allinearlo all'etichetta spegne emoji e commento.
              const commento = commentoPerKpi(data.commenti, g.kpiNome);
              return (
                <div key={g.label} className="flex items-center gap-6 py-5">
                  <Gauge {...g} size="sm" />
                  <div className="flex flex-col gap-1.5 min-w-0">
                    <span className="text-base font-bold leading-tight">
                      {commento?.emoji} {g.label}
                    </span>
                    <span className="text-sm text-muted-foreground leading-snug">
                      {commento?.commento ?? "—"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

function CascataPL({ t, incompleto }: { t: MesePivot; incompleto: boolean }) {
  const steps: { label: string; value: number; kind: "result" | "cost"; colore: string }[] = [
    { label: "Fatturato Netto", value: t.fatturato_netto, kind: "result", colore: "var(--grafico-1)" },
    { label: "− Costi F&B", value: t.costi_fb_totali, kind: "cost", colore: "var(--grafico-4)" },
    { label: "Margine F&B", value: t.primo_margine, kind: "result", colore: coloreBarraRisultato(t.primo_margine, incompleto) },
    { label: "− Spese Generali + Personale", value: t.costi_spese_totali + t.costi_personale, kind: "cost", colore: "var(--grafico-4)" },
    { label: "= MOL", value: t.mol, kind: "result", colore: coloreBarraRisultato(t.mol, incompleto) },
  ];
  const refMax = Math.max(1, ...steps.map((s) => Math.abs(s.value)));

  return (
    <div className="flex flex-col gap-6">
      {steps.map((s) => {
        const w = Math.min(100, (Math.abs(s.value) / refMax) * 100);
        const isResult = s.kind === "result";
        // A6 — una perdita non deve avere lo stesso disegno di un guadagno.
        //
        // Fino al 23/09/2026 la barra usava `Math.abs` e basta: un MOL di
        // −26.414 EUR era disegnato IDENTICO a un +26.414 EUR, cambiava solo il
        // colore. Il primo tentativo la faceva partire dalla meta' crescendo a
        // sinistra, come su un asse con lo zero al centro: provato a schermo su
        // CASATI e scartato da Mattia — nella cascata l'asse NON c'e' (la traccia
        // grigia copre solo la parte piena, le altre quattro barre partono da
        // sinistra), quindi l'unica barra centrata si legge come un errore di
        // allineamento, non come un segno.
        //
        // Qui la barra resta ancorata a sinistra come tutte le altre e la perdita
        // si dichiara con le STRISCE diagonali: un canale in piu' oltre al colore
        // (che da solo non basta a chi distingue male rosso e verde) e oltre al
        // meno sull'importo, che e' scritto in 15px accanto a una barra di 36.
        const perdita = isResult && s.value < 0;
        return (
          <div key={s.label} className="flex items-center gap-3">
            <span className={`w-36 sm:w-40 shrink-0 text-base ${isResult ? "font-bold" : "text-muted-foreground"}`}>
              {s.label}
            </span>
            <div
              className={`relative flex-1 h-9 rounded overflow-hidden ${isResult ? "bg-muted/40" : "bg-muted/20"}`}
              title={perdita ? `${s.label}: perdita di ${formatEuro(Math.abs(s.value))}` : undefined}
            >
              <div
                className="h-full rounded transition-all duration-500"
                style={{
                  width: `${w}%`,
                  backgroundColor: s.colore,
                  opacity: isResult ? 0.95 : 0.65,
                  boxShadow: isResult ? `0 0 14px color-mix(in oklch, ${s.colore} 50%, transparent)` : undefined,
                  // Le strisce sono sovrapposte al colore, non al posto suo: la
                  // barra resta rossa e leggibile, ma "rigata" — si distingue da
                  // una barra piena anche in bianco e nero.
                  backgroundImage: perdita
                    ? "repeating-linear-gradient(135deg, transparent 0 6px, color-mix(in oklab, black 22%, transparent) 6px 12px)"
                    : undefined,
                }}
              />
            </div>
            {/* A4 — gli importi restano SOLO sui tre risultati (Fatturato, Margine,
                MOL). Sulle due righe di costo erano il terzo posto in cui la
                pagina scriveva lo stesso numero (tessere in alto, colonna TOTALE
                della tabella, e qui): la barra grigia dice gia' quanto pesano
                rispetto al fatturato, che e' l'unica cosa che questo blocco
                aggiunge. */}
            <span
              className={`w-28 sm:w-32 shrink-0 text-right text-base tabular-nums ${isResult ? "font-bold" : "text-muted-foreground"}`}
              style={isResult ? { color: s.colore } : undefined}
            >
              {isResult ? formatEuro(s.value) : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Traduce l'emoji di giudizio del worker nella palette dei gauge. L'arancio
 *  del Python non ha un corrispettivo qui e ricade su ambra: e' comunque il
 *  giudizio del worker, non una soglia locale che gli contraddice. */
const GAUGE_PER_EMOJI: Record<string, string> = {
  "🟢": GAUGE_GREEN,
  "🟡": GAUGE_AMBER,
  "🟠": GAUGE_AMBER,
  "🔴": GAUGE_ROSE,
};

function coloreDaCommento(commenti: Commento[], kpiNome: string): string {
  const c = commentoPerKpi(commenti, kpiNome);
  // Senza commento il colore e' NEUTRO, non ambra: il worker popola `commenti`
  // solo se c'e' almeno un mese con fatturato > 0 (margini.py:1207), mentre il
  // gauge si renderizza anche con soli costi (hasData include costi_fb_totali).
  // Stato reale: OFFSIDE ha 0 mesi con fatturato e ~14.600 € di costi F&B, e le
  // percentuali sono tutte 0 — un giudizio ambra su dati assenti sarebbe una
  // valutazione inventata, come lo era il verde/rosso delle soglie locali.
  return (c && GAUGE_PER_EMOJI[c.emoji]) ?? GAUGE_NEUTRAL;
}

function Gauge({
  label,
  valueText,
  fraction,
  trackColor,
  valueColor,
  size = "md",
}: {
  label: string;
  valueText: string;
  fraction: number;
  trackColor: string;
  valueColor: string;
  size?: "sm" | "md";
}) {
  // A6 — una percentuale NEGATIVA non e' un anello vuoto.
  // `clamp01` schiacciava a 0 qualsiasi frazione negativa: un MOL a −55% usciva
  // come un cerchio quasi vuoto col puntino, indistinguibile da uno 0%. Il
  // gauge disegna la GRANDEZZA (il valore assoluto) e il colore porta il segno,
  // che e' gia' deciso dal giudizio del worker (`coloreDaCommento`). Il numero
  // al centro resta quello vero, col meno: e' li' che si legge il segno.
  const f = clamp01(Math.abs(fraction));
  const r = 36;
  const startDeg = 225;
  const sweepDeg = 270;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const sx = 50 + r * Math.cos(toRad(startDeg));
  const sy = 50 + r * Math.sin(toRad(startDeg));
  const endDeg = startDeg + sweepDeg;
  const ex = 50 + r * Math.cos(toRad(endDeg));
  const ey = 50 + r * Math.sin(toRad(endDeg));
  const largeArc = sweepDeg > 180 ? 1 : 0;
  const ARC = `M ${sx.toFixed(2)} ${sy.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`;

  const svgSize = size === "sm" ? "w-20 h-20 shrink-0" : "w-full max-w-[110px]";

  return (
    <div className={`flex flex-col items-center gap-1 ${size === "sm" ? "shrink-0" : ""}`}>
      <svg viewBox="0 0 100 100" className={svgSize}>
        {/* Traccia di sfondo */}
        <path
          d={ARC}
          fill="none"
          stroke="currentColor"
          className="text-muted-foreground/15"
          strokeWidth="10"
          strokeLinecap="round"
          pathLength={100}
        />
        {/* Arco riempito con colore KPI */}
        <path
          d={ARC}
          fill="none"
          stroke={trackColor}
          strokeWidth="10"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${f * 100} 100`}
          style={{ filter: f > 0.05 ? `drop-shadow(0 0 4px color-mix(in oklch, ${trackColor} 56%, transparent))` : undefined }}
        />
        {/* Valore centrato con colore performance */}
        <text
          x="50"
          y="53"
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="18"
          fontWeight="bold"
          fill={valueColor}
        >
          {valueText}
        </text>
      </svg>
      {size !== "sm" && (
        <span className="text-[11px] text-muted-foreground font-medium text-center leading-tight">{label}</span>
      )}
    </div>
  );
}

/* ============================================================ */
/* DettaglioGiornalieroDialog                                    */
/* ============================================================ */
type RicavoGiorno = {
  data: string;
  fatturato_netto: number;
  netto_iva10: number;
  netto_iva22: number;
  netto_noiva: number;
};

function DettaglioGiornalieroDialog({
  mese, mesi, onMeseChange, onClose,
}: {
  mese: { anno: number; mese: number; label: string } | null;
  mesi: MesePivot[];
  onMeseChange: (m: { anno: number; mese: number; label: string }) => void;
  onClose: () => void;
}) {
  const [giorni, setGiorni] = useState<RicavoGiorno[]>([]);
  const [loading, setLoading] = useState(true);
  const [mensile, setMensile] = useState(false);
  const [loadError, setLoadError] = useState(false);

  const anno = mese?.anno ?? 0;
  const meseNum = mese?.mese ?? 0;
  const label = mese?.label ?? "";

  useEffect(() => {
    if (!meseNum) return;
    setLoading(true);
    setGiorni([]);
    setMensile(false);
    setLoadError(false);
    const pad = (n: number) => String(n).padStart(2, "0");
    const lastDay = new Date(anno, meseNum, 0).getDate();
    const dataDa = `${anno}-${pad(meseNum)}-01`;
    const dataA = `${anno}-${pad(meseNum)}-${lastDay}`;

    // Se il mese è in modalità "mensile" l'override ha la precedenza: le righe
    // giornaliere eventualmente rimaste a DB sono orfane e un dettaglio per
    // giorno non esiste. Mostrarle come se fossero il mese produce medie e
    // "giorno migliore" inventati (stessa regola di ricavi.py:1055).
    fetch(`/api/ricavi/modalita?anno=${anno}&mese=${meseNum}`)
      .then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((m) => {
        if (m?.modalita === "mensile") {
          setMensile(true);
          setGiorni([]);
          setLoading(false);
          return null;
        }
        return fetch(`/api/ricavi/giornalieri?data_da=${dataDa}&data_a=${dataA}`)
          .then((r) => (r.ok ? r.json() : Promise.reject()));
      })
      .then((d) => {
        if (d === null) return;
        const items: { data: string; fatturato_iva10: number; fatturato_iva22: number; altri_ricavi_noiva: number }[] = d?.items ?? [];
        const byDate = new Map(items.map((i) => [
          i.data,
          {
            netto_iva10: i.fatturato_iva10 / IVA_DIVISORE_10,
            netto_iva22: i.fatturato_iva22 / IVA_DIVISORE_22,
            netto_noiva: i.altri_ricavi_noiva,
            fatturato_netto: scorporoNetto(i.fatturato_iva10, i.fatturato_iva22, i.altri_ricavi_noiva),
          },
        ]));
        const result: RicavoGiorno[] = [];
        for (let d = 1; d <= lastDay; d++) {
          const key = `${anno}-${pad(meseNum)}-${pad(d)}`;
          const v = byDate.get(key);
          result.push({
            data: key,
            fatturato_netto: v?.fatturato_netto ?? 0,
            netto_iva10: v?.netto_iva10 ?? 0,
            netto_iva22: v?.netto_iva22 ?? 0,
            netto_noiva: v?.netto_noiva ?? 0,
          });
        }
        setGiorni(result);
      })
      // Lista vuota su errore darebbe KPI a zero (media, giorno migliore/peggiore)
      // indistinguibili da un mese senza ricavi caricati.
      .catch(() => setLoadError(true))
      .finally(() => setLoading(false));
  }, [anno, meseNum]);

  const compilati = giorni.filter((g) => g.fatturato_netto > 0);
  const totale = compilati.reduce((s, g) => s + g.fatturato_netto, 0);
  const media = compilati.length > 0 ? totale / compilati.length : 0;
  const migliore = compilati.reduce<RicavoGiorno | null>((best, g) => (!best || g.fatturato_netto > best.fatturato_netto) ? g : best, null);
  const peggiore = compilati.reduce<RicavoGiorno | null>((worst, g) => (!worst || g.fatturato_netto < worst.fatturato_netto) ? g : worst, null);

  const chartData = giorni.map((g) => ({
    giorno: parseInt(g.data.slice(8), 10),
    netto: g.fatturato_netto,
    iva10: g.netto_iva10,
    iva22: g.netto_iva22,
    noiva: g.netto_noiva,
  }));

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent showCloseButton={false} className="!max-w-[min(760px,92vw)] w-full p-0 gap-0">
        <DialogHeader className="px-6 pt-5 pb-4 border-b border-border shrink-0">
          <div className="flex items-center justify-between gap-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              📅 Fatturato giornaliero
            </DialogTitle>
            <button onClick={onClose} className="size-8 flex items-center justify-center rounded-md text-muted-foreground hover:bg-muted transition-colors shrink-0">
              <XIcon className="size-4" />
            </button>
          </div>
          {/* Selettore mese */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {mesi.map((m) => {
              const active = m.anno === anno && m.mese === meseNum;
              return (
                <button
                  key={`${m.anno}-${m.mese}`}
                  onClick={() => onMeseChange({ anno: m.anno, mese: m.mese, label: m.label })}
                  className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-colors ${
                    active
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-input hover:bg-muted"
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </DialogHeader>

        <div className="px-6 py-5 space-y-5">
          {loading ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Caricamento…</p>
          ) : loadError ? (
            <p className="text-sm text-muted-foreground py-8 text-center">
              Non è stato possibile caricare il dettaglio giornaliero.
            </p>
          ) : mensile ? (
            <div className="py-8 text-center space-y-1.5">
              <p className="text-sm font-medium">{label} è caricato come totale mensile.</p>
              <p className="text-xs text-muted-foreground">
                Per questo mese non esiste un dettaglio giorno per giorno. Per vederlo,
                inserisci i ricavi in modalità giornaliera da “Carica ricavi”.
              </p>
            </div>
          ) : compilati.length === 0 ? (
            <p className="text-sm text-muted-foreground py-8 text-center">Nessun dato giornaliero per {label}.</p>
          ) : (
            <>
              {/* Bar chart */}
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.4} vertical={false} />
                  <XAxis
                    dataKey="giorno"
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    interval={1}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                    tickLine={false}
                    axisLine={false}
                    width={52}
                    tickFormatter={(v: number) => formatEuroCompact(v)}
                  />
                  <Tooltip
                    cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                    formatter={(v: unknown, name: unknown) => [formatEuro(typeof v === "number" ? v : 0), String(name)]}
                    labelFormatter={(l) => `Giorno ${l}`}
                    contentStyle={{ fontSize: 12, borderRadius: 8, backgroundColor: "var(--card)", borderColor: "var(--border)", color: "var(--foreground)" }}
                    labelStyle={{ color: "var(--foreground)", fontWeight: 600 }}
                    itemStyle={{ color: "var(--foreground)" }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11 }}
                    iconType="circle"
                    iconSize={8}
                  />
                  <Bar dataKey="iva10" name="IVA 10%" stackId="netto" fill="var(--grafico-1)" opacity={0.9} maxBarSize={28} />
                  <Bar dataKey="iva22" name="IVA 22%" stackId="netto" fill="var(--grafico-2)" opacity={0.9} maxBarSize={28} />
                  <Bar dataKey="noiva" name="Senza IVA" stackId="netto" fill="var(--grafico-3)" opacity={0.9} maxBarSize={28} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>

              {/* 4 statistiche */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatBox label="Giorni compilati" value={`${compilati.length} / ${giorni.length}`} />
                <StatBox label="Media giornaliera" value={formatEuro(media)} color="text-primary-text" />
                <StatBox
                  label="Giorno migliore"
                  value={migliore ? formatEuro(migliore.fatturato_netto) : "—"}
                  sub={migliore ? `${parseInt(migliore.data.slice(8), 10)} ${label}` : undefined}
                  color="text-positivo"
                />
                <StatBox
                  label="Giorno peggiore"
                  value={peggiore ? formatEuro(peggiore.fatturato_netto) : "—"}
                  sub={peggiore ? `${parseInt(peggiore.data.slice(8), 10)} ${label}` : undefined}
                  color="text-negativo"
                />
              </div>
            </>
          )}
        </div>

        <div className="px-6 pb-5 flex justify-end">
          <button onClick={onClose} className="inline-flex items-center gap-1.5 px-4 py-2 text-sm rounded-md border border-border hover:bg-muted transition-colors">
            Chiudi
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function StatBox({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-3">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium mb-1">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${color ?? ""}`}>{value}</p>
      {sub && <p className="text-[11px] text-muted-foreground mt-0.5">{sub}</p>}
    </div>
  );
}
