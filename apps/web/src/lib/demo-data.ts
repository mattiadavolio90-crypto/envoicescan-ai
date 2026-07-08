// Dataset UNICO e coerente del Demo Tour ("Marea", ristorante di pesce).
//
// È tutto finto e hardcoded: nessuna query, nessuna chiamata worker, nessun
// dato cliente. Serve solo a far vedere l'app "viva" a un prospect in 60-90s.
//
// ANTI-DRIFT: ogni struttura è tipizzata contro i tipi REALI dell'app
// (Briefing, HomeKpi, VariazionePrezzo, ArticoloAggregato, …). Se un domani
// quei tipi cambiano forma, questo file smette di compilare e ce ne accorgiamo
// subito — invece di lasciare la demo che mostra una UI diversa dal prodotto.

import type {
  Briefing,
  AssistantConfig,
  HomeKpi,
  Salute,
} from "@/lib/home";
import type { VariazionePrezzo } from "@/lib/prezzi";
import type { ArticoloAggregato } from "@/lib/fatture";
import { CATEGORIA_ICONS } from "@/app/(app)/analisi-fatture/periodi";

// Anti-drift categorie: usiamo SOLO le categorie che esistono davvero nell'app
// (chiavi della mappa icone reale). Scrivere una categoria inventata qui ora
// rompe il typecheck invece di mostrarle con l'icona-segnaposto 🏷️.
type CategoriaReale = keyof typeof CATEGORIA_ICONS;
const cat = (c: CategoriaReale): string => c;

export const DEMO_RISTORANTE = "Marea";
export const DEMO_REFERENTE = "Luca";

// ── HOME · Briefing dell'assistente ─────────────────────────────────────────
export const demoBriefing: Briefing = {
  saluto: `Buongiorno ${DEMO_REFERENTE}, ecco il quadro di Marea`,
  data: "2026-05-18",
  narrativa:
    "Questo mese il pesce ti è costato l'11% in più: il salmone di Ittica Marina è salito del 16%. " +
    "Il food cost è al 31% (+2 punti) e il margine è sceso al 21%. " +
    "Ti ho preparato due cose da guardare oggi.",
  severity_max: "warning",
  tutto_ok: false,
  dati_mancanti: [],
  azioni: [
    {
      id: "demo-prezzi",
      topic_key: "price_alert",
      severity: "warning",
      testo:
        "Il salmone di Ittica Marina è passato da 18,90 € a 21,90 €/kg (+16%). Con i tuoi volumi sono circa +148 €/mese.",
      cta_label: "Vedi i prezzi",
      cta_page: "/prezzi",
    },
    {
      id: "demo-margini",
      topic_key: "mol_basso",
      severity: "info",
      // NIENTE piatti/distinte base/magazzino: evocano lavoro manuale e
      // spaventano. Solo dati che ONEFLUX calcola da solo dalle fatture.
      testo:
        "Il margine di maggio è al 21%, tre punti meno di aprile: a pesare è soprattutto il food cost.",
      cta_label: "Guarda i margini",
      cta_page: "/margini",
    },
  ],
  generated_at: null,
};

// ── HOME · Configurazione assistente ────────────────────────────────────────
// Lista avvisi COMPLETA come il pannello reale del punto vendita: la demo deve
// mostrare lo stesso configuratore che avrà il cliente, non una versione ridotta.
export const demoConfig: AssistantConfig = {
  nome_referente: DEMO_REFERENTE,
  topics: [
    {
      key: "price_alert",
      label: "Alert prezzi",
      enabled: true,
      bloccato: false,
      descrizione: "Ti avviso quando un fornitore alza i prezzi oltre la soglia.",
    },
    {
      key: "mol_basso",
      label: "Margine sotto la soglia",
      enabled: true,
      bloccato: false,
      descrizione: "Ti avviso se il margine del mese scende troppo.",
    },
    {
      key: "fatture_mancanti",
      label: "Fatture mancanti",
      enabled: true,
      bloccato: false,
      descrizione: "Ti avviso se un fornitore abituale non ti ha ancora fatturato.",
    },
    {
      key: "uncategorized_rows",
      label: "Righe da controllare",
      enabled: true,
      bloccato: false,
      descrizione: "Ti avviso se ci sono prodotti che non riesco a classificare con certezza.",
    },
    {
      key: "incasso_mancante",
      label: "Incassi mancanti",
      enabled: true,
      bloccato: false,
      descrizione: "Ti avviso se manca l'incasso di un giorno di apertura.",
    },
    {
      key: "costo_personale_mancante",
      label: "Costo personale mancante",
      enabled: true,
      bloccato: false,
      descrizione: "Ti ricordo di inserire il costo del personale del mese.",
    },
    {
      key: "appuntamento_imminente",
      label: "Appuntamenti in agenda",
      enabled: false,
      bloccato: false,
      descrizione: "Ti ricordo scadenze e appuntamenti presi in Agenda.",
    },
    {
      key: "upload_falliti",
      label: "Caricamenti falliti",
      enabled: true,
      bloccato: true,
      descrizione: "Problemi tecnici da non perdere: sempre attivi.",
    },
  ],
  chat_ai_enabled: true,
  chat_limite_giorno: 15,
  chat_domande_oggi: 0,
  price_alert_threshold: 5,
  alert_prezzi_solo_preferiti: false,
  giorni_chiusura_settimanali: 1,
};

// ── HOME · KPI / conti del mese ─────────────────────────────────────────────
// I numeri QUADRANO: 62.400 − 19.344 (food 31%) − 18.700 − 11.256 = 13.100 (21%).
// Maggio si confronta con l'aprile della tabella Margini (60.000 / MOL 14.400):
// stessi dati ovunque, il prospect può verificare e i conti tornano.
export const demoKpi: HomeKpi = {
  periodo_label: "Maggio 2026",
  is_mese_in_corso: true,
  fatturato: 62400,
  food_cost_pct: 31,
  costo_personale: 18700,
  spese_generali: 11256,
  mol: 13100,
  has_data: true,
  confronto_label: "vs aprile",
  fatturato_delta_pct: 4,
  food_cost_delta_pp: 2,
  personale_delta_pct: 4,
  spese_delta_pct: 10,
  mol_delta_pct: -9,
  costi_mancanti: false,
  mol_mensile: [
    { mese: 1, mol: 14200 },
    { mese: 2, mol: 13800 },
    { mese: 3, mol: 15100 },
    { mese: 4, mol: 14400 },
    { mese: 5, mol: 13100 },
  ],
  mol_mensile_anno: 2026,
};

// ── HOME · Salute della gestione ────────────────────────────────────────────
export const demoSalute: Salute = {
  indice: 78,
  colore: "giallo",
  mese_label: "Maggio 2026",
  voci: [
    {
      key: "fatture",
      label: "Fatture del mese registrate",
      ok: true,
      dettaglio: "24 fatture caricate e categorizzate",
      cta_page: null,
    },
    {
      key: "ricavi",
      label: "Incassi aggiornati",
      ok: true,
      dettaglio: "Ricavi importati fino a ieri",
      cta_page: null,
    },
    {
      key: "food_cost",
      label: "Food cost sotto controllo",
      ok: false,
      dettaglio: "31% questo mese (obiettivo 29%)",
      cta_page: "/prezzi",
    },
    {
      key: "margine",
      label: "Margine in linea",
      ok: false,
      dettaglio: "21% (−3 punti rispetto ad aprile)",
      cta_page: "/margini",
    },
  ],
};

// ── HOME · Chat AI (scambio dimostrativo pre-caricato) ──────────────────────
export type DemoChatMsg = { role: "user" | "assistant"; content: string };

export const demoChatSuggerimenti = [
  "Qual è il mio food cost?",
  "Conviene cambiare fornitore per il salmone?",
  "Com'è andato il MOL?",
];

// DUE scambi "da consulente": prima il confronto fornitori con consiglio,
// poi l'assistente che LAVORA per te (prepara il messaggio di trattativa,
// coerente con la bozza trattativa reale dello Score Fornitori).
export const demoChatScambio: DemoChatMsg[] = [
  { role: "user", content: "Conviene cambiare fornitore per il salmone?" },
  {
    role: "assistant",
    content:
      "Ti conviene prima trattare: Ittica Marina ha portato il salmone a 21,90 €/kg (+16%), " +
      "mentre Pesca Blu sul pesce fresco è stabile intorno ai 19,50 €. " +
      "Sugli 82 kg che compri ogni mese la differenza vale circa 197 €. " +
      "E da Ittica Marina compri oltre 6.000 € al mese: hai peso per chiedere un prezzo migliore — o per cambiare.",
  },
  { role: "user", content: "Preparami un messaggio per trattare con Ittica Marina." },
  {
    role: "assistant",
    content:
      "Eccolo, puoi incollarlo su WhatsApp: «Buongiorno, ho visto che il salmone è passato da 18,90 a " +
      "21,90 €/kg negli ultimi ordini. Compriamo da voi oltre 6.000 € al mese: vorrei rivedere il prezzo " +
      "del salmone o valutare un listino dedicato. Possiamo sentirci?»",
  },
];

// ── ANALISI FATTURE · articoli aggregati ────────────────────────────────────
// COERENZA card ↔ tabella: le card KPI dicono esattamente ciò che la tabella
// mostra. 21 prodotti, 81 acquisti (righe), e i totali quadrano con la colonna
// Maggio dei Margini: F&B = 17.344, Spese generali = 8.256 → 25.600 €.
function art(a: {
  d: string;
  c: CategoriaReale;
  f: string;
  altri?: string[];
  data: string;
  q: number;
  um: string | null;
  pm: number | null;
  trend: number | null;
  tot: number;
  n: number;
}): ArticoloAggregato {
  return {
    descrizione: a.d,
    categoria: a.c,
    fornitore_principale: a.f,
    altri_fornitori: a.altri ?? [],
    ultimo_acquisto: a.data,
    quantita_totale: a.q,
    unita_misura: a.um,
    prezzo_unit_medio: a.pm,
    prezzo_unit_trend_pct: a.trend,
    totale_speso: a.tot,
    num_acquisti: a.n,
    righe_ids: [],
    needs_review: false,
    is_nuovo: false,
  };
}

// Ordinati per totale speso decrescente (default della tabella reale).
export const demoArticoli: ArticoloAggregato[] = [
  art({ d: "Pescato del giorno misto", c: "PESCE", f: "Ittica Marina", data: "2026-05-13", q: 160, um: "kg", pm: 20, trend: 6, tot: 3200, n: 4 }),
  art({ d: "Energia elettrica", c: "UTENZE E LOCALI", f: "Enel Energia", data: "2026-05-03", q: 0, um: null, pm: null, trend: null, tot: 2980, n: 2 }),
  art({ d: "Verdure di stagione", c: "VERDURE", f: "Ortofrutta Levante", data: "2026-05-15", q: 428, um: "kg", pm: 5, trend: 0, tot: 2140, n: 12 }),
  art({ d: "Materiale di consumo sala", c: "MATERIALE DI CONSUMO", f: "General Food", data: "2026-05-10", q: 0, um: null, pm: null, trend: null, tot: 1756, n: 3 }),
  art({ d: "Salmone fresco Norvegia", c: "PESCE", f: "Ittica Marina", altri: ["Pesca Blu"], data: "2026-05-14", q: 82, um: "kg", pm: 20.4, trend: 16, tot: 1673, n: 6 }),
  art({ d: "Consulenza commercialista", c: "SERVIZI E CONSULENZE", f: "Studio Ferri", data: "2026-05-01", q: 0, um: null, pm: null, trend: null, tot: 1500, n: 1 }),
  art({ d: "Branzino fresco", c: "PESCE", f: "Pesca Blu", data: "2026-05-13", q: 100, um: "kg", pm: 14.8, trend: 2, tot: 1480, n: 5 }),
  art({ d: "Dispensa e conserve", c: "SCATOLAME E CONSERVE", f: "General Food", data: "2026-05-07", q: 87, um: "pz", pm: 17, trend: 0, tot: 1479, n: 2 }),
  art({ d: "Gas cucina", c: "UTENZE E LOCALI", f: "Meridiana Gas", data: "2026-05-02", q: 0, um: null, pm: null, trend: null, tot: 1240, n: 1 }),
  art({ d: "Latticini e burro", c: "LATTICINI", f: "Caseificio Val d'Oro", data: "2026-05-12", q: 97, um: "kg", pm: 12, trend: 4, tot: 1164, n: 5 }),
  art({ d: "Calamari freschi", c: "PESCE", f: "Ittica Marina", data: "2026-05-11", q: 32, um: "kg", pm: 30, trend: 5, tot: 960, n: 4 }),
  art({ d: "Acqua minerale", c: "ACQUA", f: "General Food", data: "2026-05-09", q: 1160, um: "bt", pm: 0.7, trend: 0, tot: 812, n: 3 }),
  art({ d: "Lavanderia tovagliato", c: "SERVIZI E CONSULENZE", f: "Lavanderia Splendor", data: "2026-05-12", q: 0, um: null, pm: null, trend: null, tot: 780, n: 4 }),
  art({ d: "Gamberi rossi di Mazara", c: "PESCE", f: "Pesca Blu", data: "2026-05-10", q: 18, um: "kg", pm: 38.5, trend: 3, tot: 693, n: 3 }),
  art({ d: "Caffè miscela bar", c: "CAFFE E THE", f: "Torrefazione Aroma", data: "2026-05-05", q: 30, um: "kg", pm: 23, trend: 2, tot: 690, n: 2 }),
  art({ d: "Cozze e vongole", c: "PESCE", f: "Pesca Blu", data: "2026-05-14", q: 190, um: "kg", pm: 3.6, trend: 1, tot: 684, n: 6 }),
  art({ d: "Pane e lievitati", c: "PRODOTTI DA FORNO", f: "Forno San Marco", data: "2026-05-15", q: 212, um: "kg", pm: 3, trend: 0, tot: 636, n: 8 }),
  art({ d: "Prosecco DOC Extra Dry", c: "VINI", f: "Cantine del Piave", data: "2026-05-08", q: 96, um: "bt", pm: 6.4, trend: 9, tot: 614, n: 2 }),
  art({ d: "Ricciola fresca", c: "PESCE", f: "Ittica Marina", data: "2026-05-12", q: 34, um: "kg", pm: 16.2, trend: -8, tot: 551, n: 4 }),
  art({ d: "Vermentino di Sardegna", c: "VINI", f: "Cantine del Piave", data: "2026-05-06", q: 60, um: "bt", pm: 5.9, trend: 7, tot: 354, n: 2 }),
  art({ d: "Olio EVO frantoio", c: "OLIO E CONDIMENTI", f: "Terre di Puglia", data: "2026-05-04", q: 24, um: "lt", pm: 8.9, trend: 0, tot: 214, n: 2 }),
];

// KPI di testata Analisi Fatture: ESATTAMENTE la somma della tabella sopra.
// 21 prodotti · 81 acquisti · 25.600 € (= colonna Maggio dei Margini).
export const demoAnalisiKpi = {
  totale: 25600,
  num_righe: 81,
  num_prodotti: 21,
  num_fatture: 24,
  periodo_label: "Maggio 2026",
};

// ── PREZZI · variazioni (il cuore dello step Osservatorio) ──────────────────
export const demoVariazioni: VariazionePrezzo[] = [
  {
    prodotto: "Salmone fresco Norvegia",
    categoria: cat("PESCE"),
    fornitore: "Ittica Marina",
    storico: "18,90 € → 19,50 € → 21,90 €",
    media: 20.1,
    penultimo: 19.5,
    ultimo: 21.9,
    aumento_perc: 16,
    data: "2026-05-14",
    n_fattura: "FT/2026/512",
    trend: "su",
    impatto_stimato: 148,
    delta_euro: 3.0,
    preferito: true,
  },
  {
    prodotto: "Prosecco DOC Extra Dry",
    categoria: cat("VINI"),
    fornitore: "Cantine del Piave",
    storico: "5,90 € → 6,10 € → 6,40 €",
    media: 6.13,
    penultimo: 6.1,
    ultimo: 6.4,
    aumento_perc: 9,
    data: "2026-05-08",
    n_fattura: "FT/2026/498",
    trend: "su",
    impatto_stimato: 48,
    delta_euro: 0.5,
    preferito: false,
  },
  {
    prodotto: "Vermentino di Sardegna",
    categoria: cat("VINI"),
    fornitore: "Cantine del Piave",
    storico: "5,50 € → 5,70 € → 5,90 €",
    media: 5.7,
    penultimo: 5.7,
    ultimo: 5.9,
    aumento_perc: 7,
    data: "2026-05-06",
    n_fattura: "FT/2026/498",
    trend: "su",
    impatto_stimato: 24,
    delta_euro: 0.4,
    preferito: false,
  },
  {
    prodotto: "Ricciola fresca",
    categoria: cat("PESCE"),
    fornitore: "Ittica Marina",
    storico: "17,60 € → 16,90 € → 16,20 €",
    media: 16.9,
    penultimo: 16.9,
    ultimo: 16.2,
    aumento_perc: -8,
    data: "2026-05-12",
    n_fattura: "FT/2026/512",
    trend: "giu",
    impatto_stimato: -47,
    delta_euro: -1.4,
    preferito: false,
  },
];

// KPI di sintesi del tab Variazioni (calcolati "a mano" per coerenza col brief).
export const demoPrezziKpi = {
  rincaro_medio: 10.7,
  n_rincari: 3,
  risparmio_medio: -8,
  n_risparmi: 1,
  scostamento_medio: 6,
  impatto_stimato: 173,
};

// ── MARGINI · conto economico (voci della tabella reale, mesi in colonna) ────
// DUE mesi (Aprile + Maggio) + Totale, come la tabella trasposta reale. Il
// confronto del briefing ("food cost +2 punti, margine −3") è VERIFICABILE qui:
// aprile 29%/24%, maggio 31%/21%. Ogni colonna quadra al centesimo
// (netto − F&B − spese − personale = MOL).
export type DemoMeseMargini = {
  label: string;
  fatturato_iva10: number;
  fatturato_iva22: number;
  altri_ricavi_noiva: number;
  fatturato_netto: number;
  costi_fb_auto: number;
  altri_costi_fb: number;
  costi_fb_totali: number;
  primo_margine: number;
  costi_spese_auto: number;
  altri_costi_spese: number;
  costi_spese_totali: number;
  costo_dipendenti: number;
  costo_personale_extra: number;
  costi_personale: number;
  totale_costi: number;
  mol: number;
};

// Aprile: 60.000 − 17.400 (29%) − 10.200 − 18.000 = 14.400 (MOL 24%)
export const demoMarginiApr: DemoMeseMargini = {
  label: "Apr 26",
  fatturato_iva10: 54000,
  fatturato_iva22: 5000,
  altri_ricavi_noiva: 1000,
  fatturato_netto: 60000,
  costi_fb_auto: 15400,
  altri_costi_fb: 2000,
  costi_fb_totali: 17400,
  primo_margine: 42600,
  costi_spese_auto: 7200,
  altri_costi_spese: 3000,
  costi_spese_totali: 10200,
  costo_dipendenti: 16000,
  costo_personale_extra: 2000,
  costi_personale: 18000,
  totale_costi: 45600,
  mol: 14400,
};

// Maggio: 62.400 − 19.344 (31%) − 11.256 − 18.700 = 13.100 (MOL 21%)
export const demoMarginiMag: DemoMeseMargini = {
  label: "Mag 26",
  fatturato_iva10: 56000,
  fatturato_iva22: 5400,
  altri_ricavi_noiva: 1000,
  fatturato_netto: 62400,
  costi_fb_auto: 17344,
  altri_costi_fb: 2000,
  costi_fb_totali: 19344,
  primo_margine: 43056,
  costi_spese_auto: 8256,
  altri_costi_spese: 3000,
  costi_spese_totali: 11256,
  costo_dipendenti: 16700,
  costo_personale_extra: 2000,
  costi_personale: 18700,
  totale_costi: 49300,
  mol: 13100,
};

// Totale periodo = somma campo per campo dei due mesi.
export const demoMarginiTot: DemoMeseMargini = {
  label: "Totale",
  fatturato_iva10: 110000,
  fatturato_iva22: 10400,
  altri_ricavi_noiva: 2000,
  fatturato_netto: 122400,
  costi_fb_auto: 32744,
  altri_costi_fb: 4000,
  costi_fb_totali: 36744,
  primo_margine: 85656,
  costi_spese_auto: 15456,
  altri_costi_spese: 6000,
  costi_spese_totali: 21456,
  costo_dipendenti: 32700,
  costo_personale_extra: 4000,
  costi_personale: 36700,
  totale_costi: 94900,
  mol: 27500,
};

// Percentuali del PERIODO per i gauge dell'Analisi visiva (sul totale Apr+Mag).
export const demoMarginiPeriodo = {
  range_label: "01/04/26 → 31/05/26",
  food_cost_perc: 30,
  primo_margine_perc: 70,
  spese_gen_perc: 18,
  personale_perc: 30,
  mol_perc: 22,
};

// Commenti dei gauge (come i "commenti" del worker: emoji + testo breve).
export const demoMarginiCommenti = {
  food_cost: { emoji: "⚠️", testo: "Il rincaro del pesce ha spinto il food cost dal 29% di aprile al 31% di maggio." },
  primo_margine: { emoji: "✅", testo: "Buon primo margine: 7 euro su 10 restano dopo le materie prime." },
  costi_gestione: { emoji: "✅", testo: "Spese di gestione sotto controllo nel periodo." },
  mol: { emoji: "🟡", testo: "MOL di maggio al 21%, tre punti sotto aprile: tieni d'occhio il food cost." },
};
