// Invio degli XML al commercialista: la logica pura della scheda admin
// (components/admin/invio-commercialista.tsx). Decide il worker e rifiuta il DB;
// qui solo cosa mostrare, con quali parole, e quali percorsi il proxy
// (app/api/admin/clienti/[id]/invio-commercialista/[[...percorso]]) puo' inoltrare.

export type StatoInvio =
  | "richiesto" | "in_corso" | "inviato" | "errore" | "bloccato" | "prova_ok" | "esito_incerto";
export type TipoInvio = "primo" | "ordinario" | "reinvio" | "prova";
export type Frequenza = "settimanale" | "quindicinale" | "mensile";
export type Tono = "positivo" | "negativo" | "incerto" | "neutro";

export interface Invio {
  id: string;
  tipo: TipoInvio;
  stato: StatoInvio;
  periodo_dal: string;
  periodo_al: string;
  richiesto_da: "notturno" | "admin";
  n_file: number | null;
  byte_totali: number | null;
  destinatario: string | null;
  motivo: string | null;
  creata_at: string;
  conclusa_at: string | null;
  email_tentata_at: string | null;
  link_scade_il: string | null;
  file_rimossi_at: string | null;
}

export interface Configurazione {
  id: string;
  piva: string;
  invoicetronic_company_id: number | null;
  invoicetronic_nome: string | null;
  email_destinatario: string | null;
  frequenza: Frequenza;
  data_partenza: string | null;
  attivo: boolean;
  consenso_ricevuto: boolean;
  consenso_data: string | null;
  consenso_email: string | null;
  sospesa_at: string | null;
  sospesa_motivo: string | null;
  aggiornata_at: string;
  sede_sdi_attiva: boolean;
  ultimo_giorno_inviato: string | null;
  invii: Invio[];
}

export interface StatoInvioCommercialista {
  oggi: string;
  limite_due_anni: string;
  piva_disponibili: string[];
  configurazioni: Configurazione[];
}

export const DUE_ANNI =
  "Invoicetronic conserva le fatture ricevute per 2 anni. Per periodi precedenti usa il Cassetto fiscale dell'Agenzia delle Entrate.";

export const ETICHETTA_STATO: Record<StatoInvio, string> = {
  richiesto: "In coda",
  in_corso: "In corso",
  inviato: "Inviato",
  errore: "Non riuscito",
  bloccato: "Bloccato",
  prova_ok: "Prova riuscita",
  esito_incerto: "Esito incerto",
};

export const TONO_STATO: Record<StatoInvio, Tono> = {
  richiesto: "neutro",
  in_corso: "neutro",
  inviato: "positivo",
  errore: "negativo",
  bloccato: "negativo",
  prova_ok: "positivo",
  esito_incerto: "incerto",
};

export const ETICHETTA_TIPO: Record<TipoInvio, string> = {
  primo: "Primo invio",
  ordinario: "Invio",
  reinvio: "Reinvio",
  prova: "Prova a vuoto",
};

export const ETICHETTA_FREQUENZA: Record<Frequenza, string> = {
  settimanale: "Settimanale (il lunedì)",
  quindicinale: "Quindicinale (l'1 e il 16)",
  mensile: "Mensile (l'1)",
};

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

/** Cosa manca perché il DB lasci accendere la configurazione (icc_attivabile_chk). */
export function requisitiMancanti(c: Configurazione): string[] {
  const mancano: string[] = [];
  if (c.invoicetronic_company_id == null) mancano.push("collegamento a Invoicetronic");
  if (!c.email_destinatario) mancano.push("email del commercialista");
  if (!c.consenso_ricevuto || !c.email_destinatario || c.consenso_email !== c.email_destinatario) {
    mancano.push("consenso per questa email");
  }
  if (!c.data_partenza) mancano.push("data di partenza");
  return mancano;
}

export function statoConfigurazione(c: Configurazione): { testo: string; tono: Tono } {
  if (c.sospesa_at) {
    return { testo: `Sospesa dalla guardia: ${testoMotivo(c.sospesa_motivo)}`, tono: "negativo" };
  }
  if (c.invii.some((i) => i.stato === "esito_incerto")) {
    return { testo: "Esito incerto da chiarire: nessun altro invio finché non lo chiudi", tono: "incerto" };
  }
  if (!c.attivo) {
    const mancano = requisitiMancanti(c);
    return { testo: mancano.length ? `Spenta — manca: ${mancano.join(", ")}` : "Spenta", tono: "neutro" };
  }
  if (!c.sede_sdi_attiva) return { testo: "In pausa: nessuna sede con SDI attivo", tono: "incerto" };
  if (!c.ultimo_giorno_inviato) return { testo: "Attiva — il primo invio si lancia a mano", tono: "incerto" };
  return { testo: `Attiva — inviato fino al ${formattaData(c.ultimo_giorno_inviato)}`, tono: "positivo" };
}

export function spostaGiorni(iso: string, giorni: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + giorni);
  return d.toISOString().slice(0, 10);
}

/** Come `oggi - interval '2 years'` di Postgres: il 29/02 diventa il 28/02. */
export function limiteDueAnni(oggi: string): string {
  const anno = Number(oggi.slice(0, 4)) - 2;
  const meseGiorno = oggi.slice(5) === "02-29" ? "02-28" : oggi.slice(5);
  return `${String(anno).padStart(4, "0")}-${meseGiorno}`;
}

/** Lo stesso controllo del worker su un periodo scelto dall'admin (prova, reinvio). */
export function erroreDelPeriodo(dal: string, al: string, oggi: string): string | null {
  if (!dal || !al) return "Indica il periodo.";
  if (dal > al) return "La data di inizio viene dopo quella di fine.";
  if (al >= oggi) return "Il periodo deve finire al più tardi ieri.";
  if (dal < limiteDueAnni(oggi)) return DUE_ANNI;
  return null;
}

/** Il periodo che «Invia ora» chiederà: dalla data di partenza finché non c'è un
 * primo invio riuscito, poi dal giorno dopo l'ultimo inviato. Fino a ieri. */
export function periodoInviaOra(
  c: Pick<Configurazione, "data_partenza" | "ultimo_giorno_inviato">,
  oggi: string,
): { tipo: "primo" | "ordinario"; dal: string; al: string } | null {
  const limite = limiteDueAnni(oggi);
  const al = spostaGiorni(oggi, -1);
  let tipo: "primo" | "ordinario";
  let dal: string;
  if (c.ultimo_giorno_inviato) {
    tipo = "ordinario";
    dal = spostaGiorni(c.ultimo_giorno_inviato, 1);
  } else if (c.data_partenza) {
    tipo = "primo";
    dal = c.data_partenza;
  } else {
    return null;
  }
  if (dal < limite) dal = limite;
  return dal > al ? null : { tipo, dal, al };
}

export function formattaData(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [a, m, g] = iso.slice(0, 10).split("-");
  return `${g}/${m}/${a}`;
}

export function formattaByte(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} byte`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
}

const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Il percorso del worker per una richiesta al proxy, o null se non e' uno dei
 * percorsi di questa scheda. Il proxy non inoltra nient'altro: niente `..`,
 * niente segmenti arbitrari, e della query solo la P.IVA a 11 cifre. */
export function percorsoProxy(clienteId: string, segmenti: string[], query: URLSearchParams): string | null {
  if (!ID.test(clienteId)) return null;
  const base = `/api/admin/clienti/${clienteId}/invio-commercialista`;
  if (segmenti.length === 0) return base;
  if (segmenti.length === 1 && segmenti[0] === "azienda") {
    const piva = query.get("piva") ?? "";
    return /^\d{11}$/.test(piva) ? `${base}/azienda?piva=${piva}` : null;
  }
  const [config, ...resto] = segmenti;
  if (!ID.test(config)) return null;
  if (resto.length === 0) return `${base}/${config}`;
  if (resto[0] !== "invii") return null;
  if (resto.length === 1) return `${base}/${config}/invii`;
  if (resto.length === 3 && ID.test(resto[1]) && (resto[2] === "chiarisci" || resto[2] === "annulla")) {
    return `${base}/${config}/invii/${resto[1]}/${resto[2]}`;
  }
  return null;
}
