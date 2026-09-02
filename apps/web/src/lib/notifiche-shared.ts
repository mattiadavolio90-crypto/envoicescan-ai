// Il tipo vive QUI, non in notifiche.ts, e la direzione della dipendenza e'
// deliberata: notifiche.ts importa ./worker-config (path relativo) e l'harness
// pytest->node non lo risolve, quindi qualunque import da li' — anche di solo
// tipo — renderebbe questo modulo non eseguibile dai test. Le funzioni pure
// non devono dipendere da chi fa le fetch.
export type Notifica = {
  id: string;
  topic_key: string | null;
  source_type: string | null;
  severity: "info" | "warning" | "error" | "success";
  title: string;
  body: string | null;
  action_page: string | null;
  // Dati strutturati del topic (es. count righe/prezzi). Gia' restituito dal
  // worker; opzionale lato tipo perche' non tutte le callsite lo usano.
  payload?: Record<string, unknown> | null;
  // False per i segnali LIVE (fatturato/fatture/righe mancanti...): non si
  // archiviano (si chiudono da soli quando inserisci il dato). Il frontend
  // nasconde la X. Default true per compatibilita' coi vecchi payload.
  dismissible?: boolean;
  dismissed_at: string | null;
  expires_at: string | null;
  created_at: string | null;
};

// Lookup che NON attraversa Object.prototype: `MAPPA["toString"]` su un object
// literal restituisce una funzione, e una guardia `x ? ... : ...` la accetta.
// Si usa `Object.prototype.hasOwnProperty.call` e non `Object.hasOwn` perche'
// quest'ultimo e' ES2022 mentre `tsconfig.json` ha `target: ES2017`: essendo un
// metodo di libreria e non sintassi, `tsc` non lo downlevella e non lo segnala
// (`lib` include esnext), quindi finirebbe nel bundle cosi' com'e'.
function has(mappa: object, chiave: string): boolean {
  return Object.prototype.hasOwnProperty.call(mappa, chiave);
}

// --- Priorita' visiva per severity -----------------------------------------
// Ordine: error (rosso) > warning (giallo) > info (blu) > success (verde).
// Usato sia per ordinare che per i colori del bordo/badge.
export const SEVERITY_RANK: Record<Notifica["severity"], number> = {
  error: 0,
  warning: 1,
  info: 2,
  success: 3,
};

// --- Raggruppamento per origine ---------------------------------------------
// source_type reali emessi dal backend (upload_handler, anomaly_radar,
// tag_suggestion, scadenziario): mappati a categorie leggibili. Sconosciuti -> "Altro".
type Gruppo = { key: string; label: string };

const SOURCE_GROUP: Record<string, Gruppo> = {
  upload: { key: "upload", label: "Fatture caricate" },
  radar: { key: "radar", label: "Anomalie e prezzi" },
  operativa: { key: "operativa", label: "Da sistemare" },
  scadenza: { key: "scadenza", label: "Scadenze" },
  scadenziario: { key: "scadenza", label: "Scadenze" },
  agenda: { key: "agenda", label: "Agenda" },
};

const GRUPPO_ALTRO: Gruppo = { key: "altro", label: "Altro" };

// Ordine di visualizzazione dei gruppi. Agenda in coda: importanza medio/bassa.
const GRUPPO_ORDINE = ["scadenza", "upload", "radar", "operativa", "agenda", "altro"];

export function gruppoDi(n: Notifica): Gruppo {
  const st = (n.source_type ?? "").toLowerCase();
  // `has()` e non un lookup nudo: `MAPPA[k]` eredita da Object.prototype,
  // quindi source_type "toString" o "constructor" restituirebbe una funzione
  // invece del fallback. Non raggiungibile oggi (i writer usano literal
  // hardcoded), ma il costo di chiuderlo e' una riga.
  return has(SOURCE_GROUP, st) ? SOURCE_GROUP[st] : GRUPPO_ALTRO;
}

export type GruppoNotifiche = {
  key: string;
  label: string;
  notifiche: Notifica[];
};

// Raggruppa per origine e ordina i gruppi (per GRUPPO_ORDINE) e le notifiche
// interne (per priorita' severity, poi data desc — le piu' recenti prima).
export function raggruppa(notifiche: Notifica[]): GruppoNotifiche[] {
  const byKey = new Map<string, GruppoNotifiche>();
  for (const n of notifiche) {
    const g = gruppoDi(n);
    const esistente = byKey.get(g.key);
    if (esistente) esistente.notifiche.push(n);
    else byKey.set(g.key, { key: g.key, label: g.label, notifiche: [n] });
  }
  for (const g of byKey.values()) {
    g.notifiche.sort((a, b) => {
      const r = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity];
      if (r !== 0) return r;
      return (b.created_at ?? "").localeCompare(a.created_at ?? "");
    });
  }
  return [...byKey.values()].sort(
    (a, b) => GRUPPO_ORDINE.indexOf(a.key) - GRUPPO_ORDINE.indexOf(b.key),
  );
}

// --- CTA inline: action_page -> rotta Next ----------------------------------
// I nuovi action_page sono gia' path Next (es. "/prezzi"). Ma le notifiche
// storiche salvate nel DB possono avere ancora path Streamlit legacy
// ("pages/3_controllo_prezzi.py"): questa mappa li traduce. Quelle non mappabili
// NON producono un bottone (niente link rotti). Stessa logica del briefing
// lato worker (daily_briefing_service).
const LEGACY_TO_NEXT: Record<string, string> = {
  "pages/3_controllo_prezzi.py": "/prezzi",
  "pages/1_calcolo_margine.py": "/margini",
  "pages/5_notifiche_e_gestione.py": "/analisi-e-tag",
  "pages/4_analisi_personalizzata.py": "/analisi-e-tag",
  "pages/2_analisi_fatture.py": "/analisi-fatture",
  dashboard: "/dashboard",
  // Non solo path Streamlit: a DB ci sono anche NOMI di pagina. Il caso vivo e'
  // "Agenda" (topic `incasso_mancante`, 33 righe, 3 ancora VISIBILI su 2 utenti
  // una volta applicato `expires_at`): la notifica "Manca l'incasso di ieri"
  // non aveva il pulsante per arrivare all'incasso.
  //
  // Attenzione alla destinazione: NON e' /agenda. Gli incassi sono stati
  // spostati fuori dall'Agenda (desktop: Margini -> Calcolo; mobile: Movimenti,
  // ex Turni). Mandare a /agenda darebbe un pulsante che non fa fare la cosa
  // chiesta. /margini e' anche cio' che il briefing usa gia' per lo stesso
  // topic (`daily_briefing_service.py`) e cio' che scrive la versione live
  // della notifica (`fastapi_worker.py`): una sola destinazione per un topic.
  agenda: "/margini",
  "analisi margine": "/margini",
  "analisi fatture": "/analisi-fatture",
  // "Vai ai Documenti" e "Carica Fatture"/"Gestione e Pagamenti"
  // (`upload_handler.py`, percorso Streamlit) NON si mappano: /documenti non
  // esiste fra le rotte di (app)/ e gli altri due non hanno una destinazione
  // univoca. Meglio nessun pulsante di un 404 — vedi il test del fallback.
};

export function ctaDi(n: Notifica): { href: string; label: string } | null {
  const raw = (n.action_page ?? "").trim();
  if (!raw) return null;
  // Gia' rotta Next.
  if (raw.startsWith("/")) return { href: raw, label: "Vai" };
  // Vedi la nota in gruppoDi: lookup che non attraversa Object.prototype.
  const low = raw.toLowerCase();
  const mapped = has(LEGACY_TO_NEXT, raw)
    ? LEGACY_TO_NEXT[raw]
    : has(LEGACY_TO_NEXT, low)
      ? LEGACY_TO_NEXT[low]
      : undefined;
  return mapped ? { href: mapped, label: "Vai" } : null;
}

// --- Pulizia testo (markdown grezzo -> testo semplice) ----------------------
export function pulisci(testo: string): string {
  return testo
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/\*\*(.+?)\*\*/g, "$1")
    .replace(/\*(.+?)\*/g, "$1")
    .replace(/`/g, "")
    .trim();
}

// --- Filtri per severity ----------------------------------------------------
// Estratte dagli `useMemo` di `app/(app)/notifiche/notifiche-list.tsx`: erano
// pure gia' li', ma dentro un componente React l'harness pytest->node non le
// raggiunge (esegue solo moduli senza React, e solo dentro lib/).
export type Filtro = "tutte" | "error" | "warning" | "info";

export type ContiFiltro = Record<Filtro, number>;

// Notifiche ancora visibili: `dismissed` sono quelle archiviate NELLA SESSIONE
// corrente (ottimistico, prima che il worker risponda).
export function visibili(notifiche: Notifica[], dismissed: Iterable<string>): Notifica[] {
  const fuori = dismissed instanceof Set ? dismissed : new Set(dismissed);
  return notifiche.filter((n) => !fuori.has(n.id));
}

// `info` assorbe `success`: sono due severity a DB ma UNA sola voce di menu
// ("Informazioni"). Deliberato — un avviso positivo non merita una categoria
// propria. Nota: `success` non esiste ancora nei dati veri (misurato il 2/9:
// solo warning/info/error), quindi questo ramo non e' mai stato esercitato
// dalla produzione: e' congelato qui perche' nessuno lo "corregga".
export function contaPerFiltro(notifiche: Notifica[]): ContiFiltro {
  const c: ContiFiltro = { tutte: notifiche.length, error: 0, warning: 0, info: 0 };
  for (const n of notifiche) {
    if (n.severity === "error") c.error += 1;
    else if (n.severity === "warning") c.warning += 1;
    else c.info += 1;
  }
  return c;
}

// Stessa asimmetria di contaPerFiltro: se le due divergessero, il contatore
// direbbe un numero e la lista ne mostrerebbe un altro.
export function filtraPerSeverity(notifiche: Notifica[], filtro: Filtro): Notifica[] {
  if (filtro === "tutte") return notifiche;
  if (filtro === "info") {
    return notifiche.filter((n) => n.severity === "info" || n.severity === "success");
  }
  return notifiche.filter((n) => n.severity === filtro);
}

// --- CTA sul mobile ---------------------------------------------------------
// La PWA spegne le CTA che porterebbero a viste desktop (`hideCta` qui,
// `hideLinks` nella card Salute): un link a /margini su un telefono e' peggio
// di nessun link. Ma "nessuna CTA" ha lasciato scoperto il caso piu' vivo:
// `incasso_mancante` NASCE sul mobile (`m/incasso-reminder.tsx`) e la sua
// notifica arrivava li' senza modo di agire.
//
// Si mappa per TOPIC, non per path, ed e' una correzione voluta: su /margini
// desktop confluiscono almeno 6 topic (incasso_mancante, fatturato_mancante,
// costo_personale_mancante, coperti_anomalia, upload_ricavi_failed,
// buona_notizia) che sul mobile NON finiscono nello stesso posto. Mappare il
// path li avrebbe mandati tutti su /m/turni, e per due sarebbe stato sbagliato:
//   - `fatturato_mancante` e' il totale MENSILE, che su mobile e' read-only
//     ("Totale mensile inserito da desktop", `mobile-incassi.tsx`);
//   - `coperti_anomalia` punta a un tab `coperti` che sul mobile non esiste
//     (zero occorrenze di "coperti" in `(mobile)/m/`).
// Sarebbe stato di nuovo un pulsante che non fa fare la cosa chiesta.
//
// La PWA ha 6 sezioni contro le molte rotte desktop: tutto cio' che non e'
// elencato qui resta senza pulsante, come prima. Aggiungere una voce significa
// verificare che la sezione mobile esista E che ci si atterri sul tab giusto.
const TOPIC_TO_MOBILE: Record<string, string> = {
  // "Movimenti" (ex Turni), tab di default "Incassi" (`mobile-turni.tsx`):
  // e' dove l'incasso si inserisce da quando e' uscito dall'Agenda. Chiude il
  // cerchio: il segnale legge `ricavi_giornalieri` e quel tab ci scrive
  // (POST /api/ricavi/giornalieri).
  incasso_mancante: "/m/turni",
  // NON aggiungere `costo_personale_mancante` qui: sembra una dimenticanza
  // perche' /m/turni ha un tab "Turni" con inserimento mensile, ma quel dialog
  // scrive su `turni_personale` (POST /api/workspace/personale/mensile) mentre
  // il segnale legge `costo_dipendenti` dai margini mensili — e nessuna rotta
  // mobile scrive li'. Il pulsante porterebbe a una schermata che NON spegne
  // l'avviso: la stessa trappola di /agenda per gli incassi.
};

// CTA da mostrare sul mobile: `null` quando il topic non ha una destinazione
// mobile dove l'azione sia davvero eseguibile.
export function ctaMobile(n: Notifica): { href: string; label: string } | null {
  // Passa comunque da ctaDi: se la CTA desktop non esiste (action_page vuoto o
  // non mappabile) non deve esistere nemmeno quella mobile.
  const cta = ctaDi(n);
  if (!cta) return null;
  // Vedi la nota in gruppoDi.
  const topic = n.topic_key ?? "";
  const mobile = has(TOPIC_TO_MOBILE, topic) ? TOPIC_TO_MOBILE[topic] : undefined;
  return mobile ? { href: mobile, label: cta.label } : null;
}
