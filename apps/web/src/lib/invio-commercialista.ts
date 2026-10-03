// Invio degli XML al commercialista: la logica pura della card admin
// (components/admin/invio-commercialista.tsx). Lo attiva solo l'admin, una riga
// per P.IVA. Decide il worker e rifiuta il DB; qui solo cosa mostrare, con quali
// parole, e quali percorsi il proxy
// (app/api/admin/clienti/[id]/invio-commercialista/[[...percorso]]) puo' inoltrare.

export type Frequenza = "settimanale" | "quindicinale" | "mensile";
export type Tono = "positivo" | "negativo" | "incerto" | "neutro";

export interface UltimoInvio {
  periodo_dal: string;
  periodo_al: string;
  n_file: number | null;
  conclusa_at: string | null;
}

export interface VocePiva {
  piva: string;
  sedi: string[];
  sdi_attivo: boolean;
  arrivate: boolean;
  config_id: string | null;
  attivo: boolean;
  sospesa_motivo: string | null;
  email: string | null;
  frequenza: Frequenza;
  attivato_il: string | null;
  attivato_da: string | null;
  ultimo_invio: UltimoInvio | null;
  prossimo_invio: string | null;
  da_chiarire: { id: string; periodo_dal: string; periodo_al: string } | null;
}

export interface StatoInvioCommercialista {
  interruttore: boolean;
  frequenze: Record<Frequenza, string>;
  pive: VocePiva[];
}

// I motivi scritti dal worker (services/invio_commercialista_service.py) e i
// codici della guardia (services/invio_commercialista_guardia.py).
const MOTIVI: Record<string, string> = {
  invio_spento: "Interruttore generale spento (INVIO_COMMERCIALISTA_ATTIVO sul queue-worker): parte solo la prova a vuoto.",
  non_piu_autorizzato: "Dopo la richiesta la configurazione è stata spenta, sospesa o ha cambiato email.",
  configurazione_cambiata_durante_l_invio: "La configurazione è cambiata mentre si preparavano i file: nessuna email è partita.",
  configurazione_assente: "La configurazione non esiste più.",
  nessuna_sede_con_sdi_attivo: "Nessuna sede di questa P.IVA ha la ricezione SDI attiva.",
  brevo_non_configurato: "Manca BREVO_API_KEY sul queue-worker.",
  brevo_esito_incerto: "Brevo non ha confermato: l'email potrebbe essere partita. Controlla i log di Brevo e chiarisci.",
  interrotto: "Il worker si è fermato a metà: nessuna email è partita.",
  interrotto_dopo_l_email: "Il worker si è fermato dopo aver tentato l'email: controlla i log di Brevo e chiarisci.",
  riga_non_piu_in_corso: "L'invio è stato chiuso da un altro processo mentre lavorava.",
  saldo_invoicetronic_esaurito: "Saldo Invoicetronic esaurito durante i download.",
  saldo_insufficiente: "Saldo Invoicetronic troppo basso per scaricare tutto senza lasciare a secco le fatture in arrivo.",
  saldo_illeggibile: "Non si è riusciti a leggere il saldo Invoicetronic.",
  contatore_email_illeggibile: "Non si è riusciti a contare le email già inviate (anti-loop).",
  troppe_email_allo_stesso_destinatario_in_24_ore: "Già 3 email a questo indirizzo nelle ultime 24 ore (anti-loop).",
  zip_oltre_il_limite_del_bucket: "Un mese supera i 50 MB: lo ZIP non entra nel bucket.",
  invoicetronic: "Invoicetronic ha risposto con un errore.",
  errore_interno: "Errore interno del worker.",
  piva_non_solo_del_cliente: "La P.IVA risulta anche su un altro account.",
  azienda_assente_su_invoicetronic: "L'azienda non c'è più su Invoicetronic.",
  azienda_diversa_su_invoicetronic: "Invoicetronic risponde con un'azienda diversa da quella collegata.",
  documento_di_un_altra_azienda: "Nell'elenco c'è un documento di un'altra azienda.",
  documento_con_altro_destinatario: "Nell'elenco c'è un documento per un'altra P.IVA.",
  azienda_con_fatture_di_un_altro_cliente: "Fatture di questa azienda risultano arrivate a un altro cliente.",
  fatture_del_cliente_su_un_altra_azienda: "Fatture di questo cliente risultano arrivate su un'altra azienda Invoicetronic.",
  elenco_senza_fatture_gia_arrivate: "L'elenco di Invoicetronic non contiene fatture che OneFlux ha già ricevuto.",
  registro_diverso_dalla_configurazione: "L'invio non corrisponde alla sua configurazione.",
  stesso_nome_contenuto_diverso: "Due file con lo stesso nome e contenuto diverso.",
  stesso_identificativo_sdi_contenuto_diverso: "Due file con lo stesso identificativo SDI e contenuto diverso.",
};

/** Il motivo di un invio in una frase. Un codice sconosciuto resta com'è: meglio
 * il codice che una frase inventata. Il dettaglio fra parentesi o dopo i due
 * punti resta in coda. */
export function testoMotivo(motivo: string | null | undefined): string {
  if (!motivo) return "";
  const brevo = /^brevo_rifiutata_http_(\d{3})$/.exec(motivo);
  if (brevo) return `Brevo ha rifiutato l'email (HTTP ${brevo[1]}): ricontrolla l'indirizzo.`;
  const m = /^([a-z_]+)(?::\s*|\s+\(|$)(.*)$/.exec(motivo);
  if (!m || !(m[1] in MOTIVI)) return motivo;
  const dettaglio = m[2].replace(/\)$/, "").trim();
  return dettaglio ? `${MOTIVI[m[1]]} (${dettaglio})` : MOTIVI[m[1]];
}

// La stessa regola del worker (e del vincolo icc_email_chk).
export function emailValida(email: string): boolean {
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim());
}

export function formattaData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, g] = iso.slice(0, 10).split("-");
  return `${g}/${m}/${a}`;
}

const GIORNI = ["domenica", "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato"];
const MESI = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

// «lunedì 5 ottobre»: calcolato sulla data, senza fuso (la data e' gia' di Roma).
export function giornoEsteso(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${GIORNI[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]} ${d} ${MESI[m - 1]}`;
}

/** Cosa si puo' fare su una riga: attivare, solo disattivare, o niente. */
export function azioneRiga(v: VocePiva): "attiva" | "disattiva" | "nessuna" {
  if (v.attivo) return "disattiva";
  return v.sdi_attivo && v.arrivate ? "attiva" : "nessuna";
}

export function rigaStato(v: VocePiva, frequenze: Record<Frequenza, string>): { testo: string; tono: Tono } {
  if (v.da_chiarire) {
    return {
      testo: "Brevo non ha confermato l'ultima email: controlla nei suoi log se è arrivata. Finché non lo dici, non parte altro.",
      tono: "incerto",
    };
  }
  if (v.attivo && v.sospesa_motivo) {
    return { testo: `Fermo per un controllo di sicurezza: ${testoMotivo(v.sospesa_motivo)} Per ripartire: Disattiva, poi Attiva.`, tono: "negativo" };
  }
  if (v.attivo && !v.sdi_attivo) {
    return { testo: `In pausa: nessuna sede di questa P.IVA riceve più via SDI.`, tono: "incerto" };
  }
  if (v.attivo && v.email) {
    const prossimo = v.prossimo_invio ? ` Prossimo invio: ${giornoEsteso(v.prossimo_invio)}.` : "";
    return { testo: `Attivo → ${v.email}, ${frequenze[v.frequenza]}.${prossimo}`, tono: "positivo" };
  }
  if (!v.arrivate) {
    return { testo: "Nessuna fattura è ancora arrivata via SDI: si potrà attivare dopo la prima.", tono: "neutro" };
  }
  return { testo: "Non attivo.", tono: "neutro" };
}

export function rigaUltimoInvio(u: UltimoInvio | null): string | null {
  if (!u) return null;
  const periodo = `dal ${formattaData(u.periodo_dal)} al ${formattaData(u.periodo_al)}`;
  const quando = u.conclusa_at ? ` il ${formattaData(u.conclusa_at)}` : "";
  const n = u.n_file ?? 0;
  if (n === 0) return `Ultimo invio${quando}: nessuna fattura arrivata ${periodo}.`;
  return `Ultimo invio${quando}: ${n} ${n === 1 ? "fattura" : "fatture"} ${periodo}.`;
}

// Chi ha attivato e quando: la traccia della richiesta del cliente.
export function rigaAttivazione(v: VocePiva): string | null {
  if (!v.attivo || !v.attivato_il) return null;
  const quando = new Date(v.attivato_il);
  const giorno = quando.toLocaleDateString("it-IT", {
    timeZone: "Europe/Rome", day: "2-digit", month: "2-digit", year: "numeric",
  });
  const ora = quando.toLocaleTimeString("it-IT", { timeZone: "Europe/Rome", hour: "2-digit", minute: "2-digit" });
  return `Attivato il ${giorno} alle ${ora}${v.attivato_da ? ` da ${v.attivato_da}` : ""}`;
}

export function etichettaPiva(v: VocePiva): string {
  return v.sedi.length ? `${v.sedi.join(", ")} · P.IVA ${v.piva}` : `P.IVA ${v.piva}`;
}

const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Il percorso del worker per una richiesta al proxy, o null se non e' uno dei
 * percorsi di questa card. Il proxy non inoltra nient'altro: niente `..`,
 * niente segmenti arbitrari, nessuna query. */
export function percorsoProxy(clienteId: string, segmenti: string[]): string | null {
  if (!ID.test(clienteId)) return null;
  const base = `/api/admin/clienti/${clienteId}/invio-commercialista`;
  if (segmenti.length === 0) return base;
  if (segmenti.length === 1 && (segmenti[0] === "attiva" || segmenti[0] === "disattiva")) {
    return `${base}/${segmenti[0]}`;
  }
  if (segmenti.length === 3 && segmenti[0] === "invii" && ID.test(segmenti[1]) && segmenti[2] === "chiarisci") {
    return `${base}/invii/${segmenti[1]}/chiarisci`;
  }
  return null;
}
