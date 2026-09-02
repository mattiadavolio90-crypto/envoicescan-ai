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
  return SOURCE_GROUP[st] ?? GRUPPO_ALTRO;
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
  // Non solo path Streamlit: a DB ci sono anche NOMI di pagina. "Agenda" era il
  // caso vivo — 33 righe (topic `incasso_mancante`), 11 attive su 3 clienti,
  // ancora scritte l'1/9/2026 — e senza mappa la notifica "Manca l'incasso di
  // ieri" diceva di andare in Agenda SENZA il pulsante per arrivarci. La
  // sorgente e' corretta (`routers/scadenziario.py` scrive "/agenda" come gia'
  // faceva `fastapi_worker.py`), ma le righe gia' a DB passano solo di qui.
  // Le altre due sono solo storiche: nessun codice le emette piu'.
  agenda: "/agenda",
  "analisi margine": "/margini",
  "analisi fatture": "/analisi-fatture",
  // "Vai ai Documenti" (1 riga, 13/5/2026) NON si mappa: la rotta /documenti
  // non esiste. Meglio nessun pulsante di un 404 — vedi il test del fallback.
};

export function ctaDi(n: Notifica): { href: string; label: string } | null {
  const raw = (n.action_page ?? "").trim();
  if (!raw) return null;
  // Gia' rotta Next.
  if (raw.startsWith("/")) return { href: raw, label: "Vai" };
  const mapped = LEGACY_TO_NEXT[raw] ?? LEGACY_TO_NEXT[raw.toLowerCase()];
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
