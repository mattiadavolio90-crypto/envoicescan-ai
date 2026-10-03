// Invio delle fatture al commercialista attivato dal cliente: la logica pura della
// scheda in Impostazioni (app/(app)/impostazioni/fatture-commercialista-card.tsx).
// Decide il worker e rifiuta il DB; qui solo quando mostrarla e con quali parole.

export type Frequenza = "settimanale" | "quindicinale" | "mensile";
export type Tono = "positivo" | "incerto" | "neutro";

export interface UltimoInvio {
  periodo_dal: string;
  periodo_al: string;
  n_file: number | null;
  conclusa_at: string | null;
}

export interface VocePiva {
  piva: string;
  sedi: string[];
  attivo: boolean;
  sospeso: boolean;
  email: string | null;
  frequenza: Frequenza;
  attivato_il: string | null;
  recupero_dal: string | null;
  ultimo_invio: UltimoInvio | null;
  prossimo_invio: string | null;
}

export interface StatoFattureCommercialista {
  disponibile: boolean;
  /** Un admin che impersona il cliente: l'autorizzazione non e' sua da dare. */
  impersonazione: boolean;
  oggi: string;
  frequenze: Record<Frequenza, string>;
  testo_autorizzazione: string;
  pive: VocePiva[];
}

// Solo il titolare (un admin non ha un commercialista, un sotto-utente non
// sceglie per l'account, un admin che impersona non autorizza al posto del
// cliente), solo a servizio acceso (altrimenti la scheda prometterebbe un invio
// che non parte) e solo se c'e' una P.IVA che riceve via SDI.
export function mostraFattureCommercialista(
  stato: StatoFattureCommercialista | null | undefined,
  account: { is_admin?: boolean | null; sotto_utente?: boolean | null },
): boolean {
  return (
    !!stato &&
    stato.disponibile === true &&
    stato.impersonazione !== true &&
    account.is_admin !== true &&
    account.sotto_utente !== true &&
    stato.pive.length > 0
  );
}

// La stessa regola del worker (e del vincolo icc_email_chk).
export function emailValida(email: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
}

// Il testo che il cliente autorizza, compilato come lo salvera' il worker.
export function testoAutorizzazione(
  modello: string,
  email: string,
  frequenza: string,
  piva: string,
): string {
  const destinatario = email.trim().toLowerCase() || "l'indirizzo indicato";
  return modello
    .replace("{email}", destinatario)
    .replace("{frequenza}", frequenza)
    .replace("{piva}", piva);
}

function ddmmyyyy(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const MESI = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

// «lunedì 5 ottobre»: calcolato sulla data, senza fuso (la data e' gia' di Roma).
export function giornoEsteso(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const giorno = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return `${GIORNI[giorno]} ${d} ${MESI[m - 1]}`;
}

export function rigaStato(
  voce: VocePiva,
  frequenze: Record<Frequenza, string>,
): { testo: string; tono: Tono } {
  if (voce.sospeso) {
    return { testo: "In verifica da parte di OneFlux: l'invio è fermo, ti contatteremo noi.", tono: "incerto" };
  }
  if (!voce.attivo || !voce.email) {
    return { testo: "Non attivo.", tono: "neutro" };
  }
  const prossimo = voce.prossimo_invio ? ` Prossimo invio: ${giornoEsteso(voce.prossimo_invio)}.` : "";
  return {
    testo: `Attivo: ${voce.email} riceve le fatture ${frequenze[voce.frequenza]}.${prossimo}`,
    tono: "positivo",
  };
}

export function rigaUltimoInvio(ultimo: UltimoInvio | null): string | null {
  if (!ultimo) return null;
  const periodo = `dal ${ddmmyyyy(ultimo.periodo_dal)} al ${ddmmyyyy(ultimo.periodo_al)}`;
  const quando = ultimo.conclusa_at ? ` il ${ddmmyyyy(ultimo.conclusa_at)}` : "";
  const n = ultimo.n_file ?? 0;
  if (n === 0) return `Ultimo invio${quando}: nessuna fattura arrivata ${periodo}.`;
  return `Ultimo invio${quando}: ${n} ${n === 1 ? "fattura" : "fatture"} ${periodo}.`;
}

export function etichettaRecupero(voce: VocePiva): string | null {
  if (!voce.recupero_dal) return null;
  const dal = ddmmyyyy(voce.recupero_dal);
  return voce.ultimo_invio
    ? `Invia anche le fatture arrivate mentre era disattivato (dal ${dal})`
    : `Invia anche le fatture già ricevute (dal ${dal})`;
}

export function etichettaPiva(voce: VocePiva): string {
  return voce.sedi.length ? `${voce.sedi.join(", ")} · P.IVA ${voce.piva}` : `P.IVA ${voce.piva}`;
}
