// Scheda cliente → «Sotto-utenti» (pannello Admin). Qui solo la logica pura:
// le regole vere le applica il worker (services/routers/sotto_utenti_admin.py),
// questa le anticipa per non far premere un pulsante che risponderebbe 400.

export type StatoSottoUtente = "attivo" | "in_attesa" | "disattivato";

export type SottoUtente = {
  id: string;
  email: string;
  nome: string | null;
  stato: StatoSottoUtente;
  pagine: string[];
  sedi: string[];
  last_login: string | null;
  created_at: string | null;
};

export type SedeAssegnabile = { id: string; nome: string | null };

export type ElencoSottoUtenti = {
  sotto_utenti: SottoUtente[];
  sedi: SedeAssegnabile[];
  pagine_assegnabili: string[];
};

export type Selezione = { pagine: string[]; sedi: string[] };

export const PAGINA_CATENA = "catena";

// I nomi e l'ordine della barra laterale (components/nav/app-sidebar.tsx): un
// test li confronta, cosi' il pannello non chiama una pagina in un altro modo.
// Home = la Home completa e l'assistente AI.
export const ETICHETTA_PAGINA: Record<string, string> = {
  home: "Home (con assistente AI)",
  analisi_fatture: "Analisi Fatture",
  margini: "Ricavi e Margini",
  analisi_e_tag: "Analisi e Tag",
  prezzi: "Osservatorio",
  scadenziario: "Gestione Fatture",
  agenda: "Agenda e Personale",
  workspace: "Strumenti",
  catena: "Catena (tutte le sedi)",
};

export const ETICHETTA_STATO: Record<StatoSottoUtente, string> = {
  attivo: "Attivo",
  in_attesa: "In attesa di attivazione",
  disattivato: "Disattivato",
};

const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function pagineInOrdine(assegnabili: string[]): string[] {
  const note = Object.keys(ETICHETTA_PAGINA).filter((p) => assegnabili.includes(p));
  return [...note, ...assegnabili.filter((p) => !(p in ETICHETTA_PAGINA)).sort()];
}

/** La Catena si puo' spuntare solo con tutte le sedi spuntate. */
export function catenaDisponibile(sediScelte: string[], sediTutte: SedeAssegnabile[]): boolean {
  return sediTutte.length > 0 && sediTutte.every((s) => sediScelte.includes(s.id));
}

/** Spunta o toglie una voce. Togliere una sede a chi ha la Catena toglie anche la Catena. */
export function alterna(sel: Selezione, tipo: "pagine" | "sedi", voce: string, sediTutte: SedeAssegnabile[]): Selezione {
  const lista = sel[tipo];
  const nuova = lista.includes(voce) ? lista.filter((v) => v !== voce) : [...lista, voce];
  const prossima = { ...sel, [tipo]: nuova };
  if (!catenaDisponibile(prossima.sedi, sediTutte)) {
    prossima.pagine = prossima.pagine.filter((p) => p !== PAGINA_CATENA);
  }
  return prossima;
}

/** La selezione da cui parte «Modifica»: solo pagine e sedi che si possono ancora dare.
 *  Se al cliente e' stata spenta una pagina, il sotto-utente la perde al salvataggio
 *  invece di restare bloccato (il worker rifiuterebbe la pagina che non c'e' piu'). */
export function selezioneIniziale(su: Pick<SottoUtente, "pagine" | "sedi">, assegnabili: string[], sediTutte: SedeAssegnabile[]): Selezione {
  const sedi = su.sedi.filter((s) => sediTutte.some((t) => t.id === s));
  const pagine = su.pagine.filter((p) => assegnabili.includes(p) && (p !== PAGINA_CATENA || catenaDisponibile(sedi, sediTutte)));
  return { pagine, sedi };
}

/** Cosa manca per poter salvare; null se si puo'. */
export function erroreSelezione(sel: Selezione, email?: string): string | null {
  if (email !== undefined && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())) return "Email non valida";
  if (sel.pagine.length === 0) return "Scegli almeno una pagina";
  if (sel.sedi.length === 0) return "Scegli almeno una sede";
  return null;
}

/** Il percorso del worker per il proxy, o null: niente id inventati verso il worker. */
export function percorsoProxy(clienteId: string, segmenti: string[]): string | null {
  if (!ID.test(clienteId)) return null;
  const base = `/api/admin/clienti/${clienteId}/sotto-utenti`;
  if (segmenti.length === 0) return base;
  const [su, ...resto] = segmenti;
  if (!ID.test(su)) return null;
  if (resto.length === 0) return `${base}/${su}`;
  if (resto.length === 1 && resto[0] === "invia-link") return `${base}/${su}/invia-link`;
  return null;
}
