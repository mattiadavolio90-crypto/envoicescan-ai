// Logica di confronto e aggregazione multi-sede della pagina `(app)/catena/`.
//
// Estratta dai .tsx perche' `tests/helpers_ts.py` non sa montare React: finche'
// queste funzioni stavano accanto a JSX, hook e dialog erano irraggiungibili dai
// test, e catena/ e' l'area che aggrega i punti vendita di 2 account su 7 —
// quelli piu' grandi del parco (3.851.753 EUR di costi al 31/8/2026).
//
// Copiate byte per byte dai componenti, SENZA correzioni. Se una si comporta in
// modo sorprendente e' perche' si comportava gia' cosi' in produzione: il test la
// fotografa, non la sistema. Le anomalie note sono annotate qui sotto una per una
// con il loro perche'; sono decisioni, non sviste.

// `import type` (non `import { type ... }`): la forma type-only sparisce del
// tutto allo strip dei tipi, mentre l'altra lascia in piedi la import statement e
// node andrebbe a caricare lib/gruppo.ts -> ./worker, un import relativo che il
// resolve hook di helpers_ts.py non riscrive. Verificato: rompe l'harness.
import type { MarginiCopertiPV, SpesaPivotRow, SprecoCategoriaRiga } from "@/lib/gruppo";

/* ─── finestra-margini-coperti.tsx: heatmap, soglie, ordinamento ─────────── */

// Soglie del pallino salute — le stesse del ranking calcolato dal worker.
// Esportate perche' un test possa verificare la coerenza senza riscrivere i
// letterali: se il backend cambia idea, qui si vede.
export const SOGLIA_MARGINE_VERDE = 15;
export const SOGLIA_MARGINE_GIALLO = 8;

// Servono almeno 2 valori per parlare di "migliore" e "peggiore": con un solo PV
// il confronto non esiste e l'evidenza sarebbe rumore. La stessa soglia compare
// 5 volte nell'area (margini-coperti 2x, spesa-pv, tag-section, sparkline).
export const MIN_VALORI_CONFRONTO = 2;

// Heatmap a token di tema (come "Spesa per PV"): intensità sfondo dalla frazione
// sul massimo di colonna. Dà "forma" alla tabella senza colori hardcoded.
export function heatStyle(v: number | null, max: number): Record<string, string> {
  if (v == null || max <= 0 || v <= 0) return {};
  const a = 0.05 + (v / max) * 0.30;
  return { backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(a * 100)}%, transparent)` };
}

// Pallino salute dal margine % — stesse soglie del ranking (≥15 verde, ≥8 giallo).
// Nota: `perc = 0` da' rosso, `perc = null` da' grigio. Qui la distinzione
// null/0 e' fatta BENE (0% e' un dato, null e' "non lo so"): il test la protegge.
export function margineDot(perc: number | null, incompleti: boolean): string {
  if (incompleti || perc == null) return "bg-muted-foreground/30";
  if (perc >= SOGLIA_MARGINE_VERDE) return "bg-emerald-500";
  if (perc >= SOGLIA_MARGINE_GIALLO) return "bg-amber-500";
  return "bg-rose-500";
}

// Colonne "di grandezza" su cui applicare la heatmap.
export const HEAT: ReadonlySet<string> = new Set(["fatturato", "coperti"]);

// Metriche con la LORO direzione: per €MP/coperto il BASSO è meglio (regola
// catena: NON è sempre "numero alto = verde").
export type Col = {
  key: keyof MarginiCopertiPV;
  label: string;
  altoMeglio: boolean;
};

// Ordina i PV per la colonna scelta; gli incompleti restano sempre in fondo.
//
// ANOMALIA FOTOGRAFATA: i null diventano -Infinity, quindi finiscono in coda con
// `desc` ma in TESTA con `asc`. E' l'effetto di una sola coalescenza usata per
// entrambe le direzioni. Non corretto: cambierebbe l'ordine a schermo.
export function ordinaRighe(
  righe: MarginiCopertiPV[],
  sortKey: keyof MarginiCopertiPV,
  sortDir: "asc" | "desc",
): MarginiCopertiPV[] {
  return [...righe].sort((a, b) => {
    if (a.dati_incompleti !== b.dati_incompleti) return a.dati_incompleti ? 1 : -1;
    const va = a[sortKey] as number | null;
    const vb = b[sortKey] as number | null;
    const na = va == null ? -Infinity : va;
    const nb = vb == null ? -Infinity : vb;
    return sortDir === "desc" ? nb - na : na - nb;
  });
}

// Massimo per colonna (solo PV con dati) per la heatmap di fatturato/coperti.
//
// ANOMALIA FOTOGRAFATA: il `?? 0` appiattisce null su 0. Per un massimo e'
// innocuo; su un array vuoto `Math.max(0, ...)` da' 0, che heatStyle intercetta
// con `max <= 0`. La coppia va testata insieme, non separatamente.
export function calcolaHeatMax(righe: MarginiCopertiPV[]): Record<string, number> {
  const heatMax: Record<string, number> = {};
  for (const k of HEAT) {
    heatMax[k] = Math.max(0, ...righe.map((r) => (r[k as keyof MarginiCopertiPV] as number) ?? 0));
  }
  return heatMax;
}

// Per ogni colonna, individua best/worst tra i PV con dati (esclude incompleti
// e valori null). Se c'è un solo PV con dato, niente evidenza (non c'è confronto).
export function calcolaExtremes(
  righe: MarginiCopertiPV[],
  cols: Col[],
): Record<string, { best: number | null; worst: number | null }> {
  const completi = righe.filter((r) => !r.dati_incompleti);
  const extremes: Record<string, { best: number | null; worst: number | null }> = {};
  for (const col of cols) {
    const vals = completi
      .map((r) => r[col.key] as number | null)
      .filter((v): v is number => v != null);
    if (vals.length < MIN_VALORI_CONFRONTO) {
      extremes[col.key] = { best: null, worst: null };
      continue;
    }
    const hi = Math.max(...vals);
    const lo = Math.min(...vals);
    extremes[col.key] = col.altoMeglio ? { best: hi, worst: lo } : { best: lo, worst: hi };
  }
  return extremes;
}

// Colore della cella: verde al migliore, rosso al peggiore. La guardia
// `v !== ex.worst` evita di colorare quando tutti i PV hanno lo stesso valore
// (best === worst): senza, la cella prenderebbe entrambe le classi.
//
// Il `return` su `v == null` e' difensivo e NON osservabile: calcolaExtremes
// filtra i null, quindi best/worst sono sempre numeri e `null === <numero>` e'
// gia' false. Provato per mutazione (M18): togliendolo nessun test cambia, ed e'
// equivalenza vera, non una fixture mancante. Resta perche' rende esplicito il
// contratto e regge se un domani gli extremes arrivassero da un'altra fonte.
export function cellTone(
  col: Col,
  r: MarginiCopertiPV,
  extremes: Record<string, { best: number | null; worst: number | null }>,
): string {
  if (r.dati_incompleti) return "";
  const v = r[col.key] as number | null;
  if (v == null) return "";
  const ex = extremes[col.key];
  if (ex.best == null) return "";
  if (v === ex.best && v !== ex.worst) return "text-emerald-600 dark:text-emerald-500 font-semibold";
  if (v === ex.worst && v !== ex.best) return "text-rose-600 dark:text-rose-500 font-semibold";
  return "";
}

// Best/worst per RIGA (categoria) tra i PV con dato: la cella più bassa è la
// migliore (meno materia prima per coperto = meno spreco), la più alta peggiore.
export function rigaExtremes(r: SprecoCategoriaRiga): { best: number | null; worst: number | null } {
  const vals = r.per_pv.map((c) => c.valore).filter((v): v is number => v != null);
  if (vals.length < MIN_VALORI_CONFRONTO) return { best: null, worst: null };
  return { best: Math.min(...vals), worst: Math.max(...vals) };
}

/* ─── finestra-spesa-pv.tsx: heatmap pivot, PV piu' caro, intervallo mese ─── */

// Heatmap a token di tema (dark/light-safe): intensità sfondo dalla frazione
// della cella sul massimo della pivot. Usa la primary con alpha → contrasto su
// entrambi i temi, niente colori hardcoded.
//
// ATTENZIONE: coefficienti DIVERSI da heatStyle (0.06/0.34 contro 0.05/0.30), e
// firma non-nullable. Le due heatmap restano due funzioni distinte: unificarle
// cambierebbe i colori a schermo, che e' una correzione travestita da pulizia.
export function cellStyle(v: number, max: number): Record<string, string> {
  if (max <= 0 || v <= 0) return {};
  const a = 0.06 + (v / max) * 0.34;
  return { backgroundColor: `color-mix(in oklab, var(--primary) ${Math.round(a * 100)}%, transparent)` };
}

// Massimo assoluto della pivot, per la heatmap.
export function calcolaMaxCell(rows: SpesaPivotRow[], pv: { id: string }[]): number {
  return Math.max(0, ...rows.flatMap((r) => pv.map((p) => r.per_pv[p.id] ?? 0)));
}

// PV più caro della riga: lo evidenziamo solo se almeno 2 PV hanno
// speso (altrimenti "il più caro" è ovvio e diventa rumore).
//
// ANOMALIA FOTOGRAFATA: il `>` stretto fa vincere il PRIMO a parita' di importo.
// Il tie-break e' implicito e dipende dall'ordine di `pv`, non dichiarato.
export function pvPiuCaro(row: SpesaPivotRow, pv: { id: string }[]): string | null {
  const conSpesa = pv.filter((p) => (row.per_pv[p.id] ?? 0) > 0);
  return conSpesa.length >= MIN_VALORI_CONFRONTO
    ? conSpesa.reduce((a, b) => ((row.per_pv[b.id] ?? 0) > (row.per_pv[a.id] ?? 0) ? b : a)).id
    : null;
}

// Estremi del mese per la query: primo giorno -> ultimo giorno effettivo.
// `new Date(anno, m, 0)` con m 1-based da' l'ultimo giorno del mese m (giorno 0
// del mese successivo), quindi gestisce 28/29/30/31 senza tabelle.
export function intervalloMese(anno: number, mese: number): { data_da: string; data_a: string } {
  const ultimo = new Date(anno, mese, 0).getDate(); // ultimo giorno del mese
  return {
    data_da: `${anno}-${String(mese).padStart(2, "0")}-01`,
    data_a: `${anno}-${String(mese).padStart(2, "0")}-${String(ultimo).padStart(2, "0")}`,
  };
}

// Incidenza % di un totale PV sul totale generale.
//
// ANOMALIA FOTOGRAFATA: con `grand_total` a 0 restituisce 0, non null — a
// schermo diventa "0,0%" dove il dato in realta' non esiste ("—" sarebbe onesto).
export function incidenzaPct(tot: number, grandTotal: number): number {
  return grandTotal > 0 ? (tot / grandTotal) * 100 : 0;
}

/* ─── sintesi-catena.tsx: sparkline MOL, tinta conti, anello salute ──────── */

export type PuntoMol = { mese: number; mol: number };

export type Sparkline = {
  d: string;
  ytdPct: number | null;
  su: boolean;
  stroke: string;
  meseDa: string;
  meseA: string;
  // Coordinate del punto finale (il cerchio in fondo alla linea). Restituite qui
  // invece di ricalcolare geometria nel componente: due copie della stessa
  // formula divergerebbero al primo ritocco.
  cx: number;
  cy: number;
} | null;

const MESI_ABBR = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

// Path SVG + variazione da inizio a fine anno della serie MOL del gruppo.
//
// ANOMALIA FOTOGRAFATA (la piu' notevole dell'area): con `primo <= 0` la
// variazione e' null — e `su` diventa false, quindi la linea e' ROSSA "in calo"
// anche quando il MOL sta risalendo (es. da -74.031 a -19.221). Oggi nessun
// cliente la vede: services/routers/gruppo.py:873 tiene solo i mesi con
// `netto > 0`, e con `tot_lordo <= 0` il livello e' "nessuno", che in
// sintesi-catena.tsx:318 non renderizza affatto la sparkline. Il difetto e'
// reale ma non raggiungibile: si arma se quel filtro cambia.
//
// `range = max - min || 1` protegge la divisione quando tutti i MOL sono uguali.
export function calcolaSparkline(punti: PuntoMol[], W = 240, H = 40, PAD = 4): Sparkline {
  if (punti.length < 2) return null;
  const vals = punti.map((p) => p.mol);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const n = punti.length;
  const x = (i: number) => PAD + (i * (W - 2 * PAD)) / (n - 1);
  const y = (v: number) => H - PAD - ((v - min) / range) * (H - 2 * PAD);
  const d = punti.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.mol).toFixed(1)}`).join(" ");
  const primo = punti[0].mol;
  const ultimo = punti[n - 1].mol;
  const ytdPct = primo > 0 ? ((ultimo - primo) / primo) * 100 : null;
  const su = ytdPct != null && ytdPct >= 0;
  const stroke = su ? "text-emerald-500" : "text-rose-500";
  const meseDa = MESI_ABBR[(punti[0].mese - 1) % 12] ?? "";
  const meseA = MESI_ABBR[(punti[n - 1].mese - 1) % 12] ?? "";
  return { d, ytdPct, su, stroke, meseDa, meseA, cx: x(n - 1), cy: y(ultimo) };
}

// A cascata: con dati incompleti il MOL e' falso -> card neutra (no verde/rosso).
//
// ANOMALIA FOTOGRAFATA: `livello_dati ?? "completo"` sceglie sull'assenza del
// campo l'ipotesi PIU' ottimista — un worker che lo omettesse mostrerebbe MOL e
// margini come affidabili. Il tipo GruppoKpi lo dichiara non-nullable, quindi
// TypeScript non vedrebbe mai il caso: la difesa e' solo a runtime.
export function tintConti(kpi: { mol: number; livello_dati?: string | null }): "verde" | "rosso" | "giallo" {
  const livello = kpi.livello_dati ?? "completo";
  const molPos = kpi.mol >= 0;
  return livello === "completo" ? (molPos ? "verde" : "rosso") : "giallo";
}

// Offset del cerchio SVG dell'anello salute: indice 0-100 clampato.
export function offsetAnello(indice: number, r: number): number {
  const c = 2 * Math.PI * r;
  return c - (Math.max(0, Math.min(100, indice)) / 100) * c;
}

// Riga "fatture di gruppo da collocare". Se la narrativa ha già accennato alla
// novità di ieri (apertura "sono arrivate N fatture"), qui basta il numero totale
// senza ripetere l'imperativo "assegnale/dividile" — già dato sopra.
export function messaggioFattureDaCollocare(briefing: {
  n_fatture_da_collocare?: number;
  n_fatture_arrivate_ieri?: number | null;
}): string | null {
  if ((briefing.n_fatture_da_collocare ?? 0) <= 0) return null;
  return briefing.n_fatture_arrivate_ieri
    ? briefing.n_fatture_da_collocare === 1
      ? "In tutto c'è 1 fattura di gruppo da collocare qui sotto."
      : `In tutto ci sono ${briefing.n_fatture_da_collocare} fatture di gruppo da collocare qui sotto.`
    : briefing.n_fatture_da_collocare === 1
      ? "C'è 1 fattura di gruppo da collocare qui sotto: assegnala a una sede o dividila fra i locali."
      : `Ci sono ${briefing.n_fatture_da_collocare} fatture di gruppo da collocare qui sotto: assegnale a una sede o dividile fra i locali.`;
}
