export type Documento = {
  id: string;
  file_origine: string;
  fornitore: string;
  piva_fornitore?: string | null;
  tipo_documento: string;
  is_nota_credito?: boolean;
  totale_documento: number;
  totale_incoerente?: boolean;
  data_documento: string | null;
  numero_documento: string | null;
  scadenza_effettiva: string | null;
  scadenza_source: string | null;
  pagata: boolean;
  data_pagamento: string | null;
  pagata_at: string | null;
  stato_scadenza: string;
  is_nuovo?: boolean;
  // Presenti SOLO in modalità catena (endpoint /api/gruppo/scadenziario):
  // assenti in mono-sede, coerente con get_documenti_scadenziario lato worker.
  ristorante_id?: string;
  sede_nome?: string;
};

// Sede di catena: elenco esposto da /api/gruppo/scadenziario, usato per il
// filtro Sede e la colonna per riga. La sede tecnica ("Costi comuni di
// gruppo") appare qui con is_sede_tecnica=true.
export type SedeCatena = {
  id: string;
  nome_ristorante: string;
  is_sede_tecnica: boolean;
};

export type RegolaPagamento = {
  id: string;
  piva_fornitore: string;
  modalita: string;
  giorni_pagamento: number;
  data_riferimento: string;
  attiva: boolean;
  note: string | null;
  created_at: string | null;
};

export type ScadenzarioKpi = {
  scadute_count: number;
  scadute_totale: number;
  settimana_count: number;
  settimana_totale: number;
  da_pagare_count: number;
  da_pagare_totale: number;
  pagate_mese_count: number;
  pagate_mese_totale: number;
};

export const MODALITA_LABELS: Record<string, string> = {
  rid: "Automatico / RID — già pagato",
  "30gg": "30 giorni dalla data fattura",
  "60gg": "60 giorni dalla data fattura",
  "90gg": "90 giorni dalla data fattura",
  "30gg_fm": "Fine mese successivo",
  "60gg_fm": "Fine del 2° mese successivo",
  "90gg_fm": "Fine del 3° mese successivo",
};

/**
 * Parsa una data "YYYY-MM-DD" come data LOCALE a mezzanotte.
 * `new Date("YYYY-MM-DD")` la interpreterebbe come mezzanotte UTC, che in Italia
 * (UTC+1/+2) sposta confronti e bucket di un giorno. Qui evitiamo l'ambiguità.
 */
export function parseLocalDate(iso: string | null): Date | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) {
    const d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/**
 * Data odierna nel formato che il worker usa per pagata_at: "YYYY-MM-DD" in ora
 * LOCALE. `new Date().toISOString()` darebbe l'istante UTC — a ovest di Greenwich
 * la sera del 31 diventa gia' il 1° del mese dopo, e la riga aggiornata in modo
 * ottimistico saltava di mese finche' non si ricaricava.
 */
export function todayLocalIso(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

export function computeKpi(documenti: Documento[]): ScadenzarioKpi {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const in7 = new Date(today);
  in7.setDate(in7.getDate() + 7);

  const primoMese = new Date(today.getFullYear(), today.getMonth(), 1);

  let scadute_count = 0, scadute_totale = 0;
  let settimana_count = 0, settimana_totale = 0;
  let da_pagare_count = 0, da_pagare_totale = 0;
  let pagate_mese_count = 0, pagate_mese_totale = 0;

  for (const doc of documenti) {
    if (doc.is_nota_credito) continue; // le NC non sono debiti da pagare
    const totale = doc.totale_documento || 0;

    if (doc.pagata) {
      // parseLocalDate, non new Date(): il worker manda pagata_at come data nuda
      // "YYYY-MM-DD" (_to_date_iso in documenti_service.py), che new Date()
      // leggerebbe a mezzanotte UTC. In un fuso a ovest di Greenwich quella
      // mezzanotte cade il giorno prima in locale e un pagamento del 1° del mese
      // finiva fuori dal KPI "Pagate (mese)".
      const pagata_at = parseLocalDate(doc.pagata_at);
      if (pagata_at && pagata_at >= primoMese) {
        pagate_mese_count++;
        pagate_mese_totale += totale;
      }
      continue;
    }

    da_pagare_count++;
    da_pagare_totale += totale;

    const scad = parseLocalDate(doc.scadenza_effettiva);
    if (!scad) continue;

    if (scad < today) {
      scadute_count++;
      scadute_totale += totale;
    } else if (scad <= in7) {
      settimana_count++;
      settimana_totale += totale;
    }
  }

  return {
    scadute_count, scadute_totale,
    settimana_count, settimana_totale,
    da_pagare_count, da_pagare_totale,
    pagate_mese_count, pagate_mese_totale,
  };
}

export function bucketizeDocumenti(documenti: Documento[]) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const in7 = new Date(today);
  in7.setDate(in7.getDate() + 7);
  const in30 = new Date(today);
  in30.setDate(in30.getDate() + 30);

  const scadute: Documento[] = [];
  const settimana: Documento[] = [];
  const mese: Documento[] = [];
  const oltre: Documento[] = [];
  const senzaScadenza: Documento[] = [];
  const pagate: Documento[] = [];
  const noteCredito: Documento[] = [];

  for (const doc of documenti) {
    // Le note di credito non sono obbligazioni di pagamento: niente bucket di
    // scadenza, vanno in una sezione informativa separata.
    if (doc.is_nota_credito) {
      noteCredito.push(doc);
      continue;
    }
    if (doc.pagata) {
      pagate.push(doc);
      continue;
    }
    const scad = parseLocalDate(doc.scadenza_effettiva);
    if (!scad) {
      senzaScadenza.push(doc);
      continue;
    }
    if (scad < today) scadute.push(doc);
    else if (scad <= in7) settimana.push(doc);
    else if (scad <= in30) mese.push(doc);
    else oltre.push(doc);
  }

  return { scadute, settimana, mese, oltre, senzaScadenza, pagate, noteCredito };
}

// ── Cash-flow: esposizione futura aggregata ──────────────────────────────────
//
// Estratta da `scadenziario-client.tsx` il 31/08/2026. Viveva dentro il
// componente, dove nessuna tecnica di test la raggiungeva (stessa ragione, e
// stessa strada, di `poolSaturo`/F7 in `lib/tag-candidati.ts`).
//
// Confini: `scadute` e' STRETTO (`s < today`), le altre fasce sono INCLUSIVE
// (`s <= inN`). Un documento che scade oggi e' "Entro 7gg", non "Scadute".
// Esclude pagate e note di credito: una NC non e' un debito.

export type CashFascia = { label: string; totale: number; count: number; tone: string };

export function buildCashFlow(documenti: Documento[]): CashFascia[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = (n: number) => { const x = new Date(today); x.setDate(x.getDate() + n); return x; };
  const in7 = d(7), in30 = d(30), in60 = d(60), in90 = d(90);

  const fasce: CashFascia[] = [
    { label: "Scadute", totale: 0, count: 0, tone: "bg-rose-500" },
    { label: "Entro 7gg", totale: 0, count: 0, tone: "bg-orange-500" },
    { label: "8–30gg", totale: 0, count: 0, tone: "bg-amber-500" },
    { label: "31–60gg", totale: 0, count: 0, tone: "bg-sky-500" },
    { label: "61–90gg", totale: 0, count: 0, tone: "bg-indigo-500" },
    { label: "Oltre 90gg", totale: 0, count: 0, tone: "bg-slate-400" },
  ];

  for (const doc of documenti) {
    if (doc.pagata || doc.is_nota_credito) continue;
    const s = parseLocalDate(doc.scadenza_effettiva);
    if (!s) continue; // le senza scadenza hanno già il loro alert dedicato
    const t = doc.totale_documento || 0;
    let i: number;
    if (s < today) i = 0;
    else if (s <= in7) i = 1;
    else if (s <= in30) i = 2;
    else if (s <= in60) i = 3;
    else if (s <= in90) i = 4;
    else i = 5;
    fasce[i].totale += t;
    fasce[i].count += 1;
  }
  return fasce;
}

// ── Filtri, ordinamento, stato: la logica che decide cosa il cliente VEDE ────
//
// Estratta da `scadenziario-client.tsx` il 31/08/2026, stessa strada di
// `buildCashFlow` (sopra) e di `poolSaturo`/F7 in `lib/tag-candidati.ts`.
// Viveva dentro il componente: 2.210 righe che nessun test raggiungeva, mentre
// decidevano quali fatture comparivano in lista e quali numeri il cliente
// leggeva. Un difetto qui non si vede — la lista e' solo piu' corta.
//
// **I confini NON sono simmetrici, ed e' voluto.** Il chip "Questo mese"
// (finestra CUMULATIVA `oggi..+30gg`, include la settimana) e la sezione
// "Questo mese" di `bucketizeDocumenti` (fascia `+8gg..+30gg`, la esclude) si
// chiamano con le stesse parole e sono insiemi diversi. Chi li allinea "per
// coerenza" cambia cio' che il cliente vede: vedi
// `tests/test_scadenziario_filtri_frontend.py::test_chip_mese_e_cumulativo_non_e_il_bucket_mese`.

export type Periodo = "tutti" | "scadute" | "settimana" | "mese" | "personalizzato";
export type Ordine = "scadenza" | "importo" | "fornitore";
export type StatoDocumento =
  | "Nota di credito" | "Pagata" | "Scaduta" | "Senza scadenza" | "Da pagare";
export type FornitoreEntry = { key: string; label: string };
export type ConfiniPeriodo = { today: Date; in7: Date; in30: Date };
export type TotaleSede = { count: number; totale: number };

export type FiltriScadenziario = {
  periodo: Periodo;
  // Lista, non Set: un Set non sopravvive a JSON.stringify (dà {}) e i test lo
  // passano serializzato. Il client converte con [...filtroFornitori].
  fornitori?: readonly string[] | null;
  soloNuove?: boolean;
  dataDa?: string;
  dataA?: string;
};

export function confiniPeriodo(now: Date = new Date()): ConfiniPeriodo {
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const in7 = new Date(today);
  in7.setDate(in7.getDate() + 7);
  const in30 = new Date(today);
  in30.setDate(in30.getDate() + 30);
  return { today, in7, in30 };
}

// Chiave di raggruppamento fornitore: P.IVA se nota, altrimenti nome (fatture
// senza fatture_documenti collegata, es. pre-esistenti al join).
export function fornitoreKey(d: Documento): string {
  return d.piva_fornitore || d.fornitore;
}

// Ordina i documenti di un bucket secondo il criterio scelto. Le fatture senza
// scadenza finiscono in fondo quando si ordina per scadenza.
export function ordinaDocumenti(docs: Documento[], ordine: Ordine): Documento[] {
  const arr = [...docs];
  if (ordine === "importo") {
    arr.sort((a, b) => (b.totale_documento || 0) - (a.totale_documento || 0));
  } else if (ordine === "fornitore") {
    arr.sort((a, b) => (a.fornitore || "").localeCompare(b.fornitore || "", "it"));
  } else {
    arr.sort((a, b) => {
      const da = parseLocalDate(a.scadenza_effettiva)?.getTime() ?? Infinity;
      const db = parseLocalDate(b.scadenza_effettiva)?.getTime() ?? Infinity;
      return da - db;
    });
  }
  return arr;
}

/**
 * Voci del filtro fornitore: una per chiave (P.IVA, fallback nome), etichettata
 * col nome piu' frequente per quella chiave — la stessa P.IVA con ragione
 * sociale scritta in modo diverso non deve apparire come voci multiple.
 *
 * A parita' di conteggio vince il nome incontrato per PRIMO: `Map` itera in
 * ordine di inserimento e `Array.prototype.sort` e' stabile per spec (ES2019).
 * E' deterministico, non fortuna.
 */
export function elencaFornitori(documenti: Documento[]): FornitoreEntry[] {
  const counts = new Map<string, Map<string, number>>();
  for (const d of documenti) {
    const key = fornitoreKey(d);
    if (!key) continue;
    const nomi = counts.get(key) ?? new Map<string, number>();
    nomi.set(d.fornitore, (nomi.get(d.fornitore) ?? 0) + 1);
    counts.set(key, nomi);
  }
  const entries: FornitoreEntry[] = [...counts.entries()].map(([key, nomi]) => {
    const label = [...nomi.entries()].sort((a, b) => b[1] - a[1])[0][0];
    return { key, label };
  });
  return entries.sort((a, b) => a.label.localeCompare(b.label, "it"));
}

/**
 * Stato mostrato nel CSV scaricato e nel bordo della riga. Ordine di precedenza
 * IDENTICO a `bucketizeDocumenti` (NC → pagata → senza scadenza → scaduta), cosi'
 * il CSV non puo' divergere da cio' che si vede a video.
 */
export function statoDocumento(d: Documento, today?: Date): StatoDocumento {
  if (d.is_nota_credito) return "Nota di credito";
  if (d.pagata) return "Pagata";
  const limite = today ?? confiniPeriodo().today;
  const s = parseLocalDate(d.scadenza_effettiva);
  if (!s) return "Senza scadenza";
  if (s < limite) return "Scaduta";
  return "Da pagare";
}

/**
 * Filtri comuni: periodo + fornitori + is_nuovo. NON include il filtro sede —
 * il KPI per-sede deve riflettere gli altri filtri attivi ma non quello di sede,
 * altrimenti sarebbe sempre un'unica barra.
 */
export function matchDocumento(
  d: Documento,
  filtri: FiltriScadenziario,
  confini: ConfiniPeriodo = confiniPeriodo(),
): boolean {
  const { periodo, fornitori, soloNuove, dataDa = "", dataA = "" } = filtri;

  if (fornitori && fornitori.length > 0 && !fornitori.includes(fornitoreKey(d))) return false;
  if (soloNuove && !d.is_nuovo) return false;

  // Filtro periodo (solo su non pagate con scadenza, tranne "tutti").
  // parseLocalDate interpreta "YYYY-MM-DD" a mezzanotte LOCALE: con new Date()
  // grezzo era mezzanotte UTC e in Italia il confronto con today (locale)
  // sbagliava di un giorno sulle scadenze esattamente a mezzanotte.
  if (periodo !== "tutti") {
    if (d.pagata) return false;
    const { today, in7, in30 } = confini;
    const s = parseLocalDate(d.scadenza_effettiva);
    if (periodo === "scadute") {
      if (!s) return false;
      return s < today;
    }
    if (periodo === "settimana") {
      if (!s) return false;
      return s >= today && s <= in7;
    }
    if (periodo === "mese") {
      if (!s) return false;
      // CUMULATIVO: include anche la settimana. Non e' il bucket "mese".
      return s >= today && s <= in30;
    }
    if (periodo === "personalizzato") {
      if (!s) return dataDa === "" && dataA === "";
      const da = parseLocalDate(dataDa);
      const a = parseLocalDate(dataA);
      if (da && s < da) return false;
      if (a && s > a) return false;
    }
  }

  return true;
}

/** `matchDocumento` su tutta la lista, piu' un predicato extra (es. la sede). */
export function filtraDocumenti(
  documenti: Documento[],
  filtri: FiltriScadenziario,
  extra?: (d: Documento) => boolean,
  confini: ConfiniPeriodo = confiniPeriodo(),
): Documento[] {
  return documenti.filter(
    d => (!extra || extra(d)) && matchDocumento(d, filtri, confini),
  );
}

/**
 * Aggrega i DEBITI (non pagate, non note di credito) per ristorante_id,
 * applicando i filtri comuni ma NON quello di sede.
 */
export function aggregaPerSede(
  documenti: Documento[],
  filtri: FiltriScadenziario,
  confini: ConfiniPeriodo = confiniPeriodo(),
): Map<string, TotaleSede> {
  const perSede = new Map<string, TotaleSede>();
  for (const d of documenti) {
    if (!d.ristorante_id || !matchDocumento(d, filtri, confini)) continue;
    if (d.is_nota_credito || d.pagata) continue;
    const acc = perSede.get(d.ristorante_id) ?? { count: 0, totale: 0 };
    acc.count += 1;
    acc.totale += d.totale_documento || 0;
    perSede.set(d.ristorante_id, acc);
  }
  return perSede;
}

// formatEuro centralizzato in lib/format.ts (era equivalente). formatDate resta
// qui: usa un formato diverso ("15 gen 2026") specifico dello scadenziario.
export { formatEuro } from "@/lib/format";

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
  } catch {
    return iso;
  }
}
