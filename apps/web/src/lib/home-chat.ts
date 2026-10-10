
// Chat dell'assistente — logica pura. Dal 28/9/2026 la conversazione vive nel
// riquadro del briefing della Home (components/home/conversazione-assistente.tsx),
// non piu' nel pulsante flottante; lo stato sta in AssistenteProvider.

export type Msg = { role: "user" | "assistant"; content: string };

// Il backend accetta al massimo 20 messaggi (ChatRequest.max_length). Inviamo
// solo la coda piu' recente: senza questo, dopo ~20 scambi ogni invio falliva
// con 422 e l'utente vedeva un errore generico, senza piu' poter chattare.
// La UI conserva comunque l'intera conversazione a schermo.
export const MAX_STORICO_INVIATO = 16;

// Lo storico vive in sessionStorage, quindi il contenuto e' fuori dal nostro
// controllo: puo' essere assente, non-JSON, un JSON che non e' un array, o un
// array con voci malformate. Ognuno di questi casi deve dare [] e mai un
// throw, o la chat non si apre piu' e l'utente non ha modo di ripulirla.
export function parseStorico(raw: string | null): Msg[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is Msg =>
        !!m && (m.role === "user" || m.role === "assistant") && typeof m.content === "string",
    );
  } catch {
    return [];
  }
}

export function codaDaInviare(messaggi: Msg[]): Msg[] {
  return messaggi.slice(-MAX_STORICO_INVIATO);
}

export function domandeRimanenti(limiteGiorno: number, domandeOggi: number): number {
  return Math.max(0, limiteGiorno - domandeOggi);
}

// Cosa legge l'utente quando la chiamata non porta una risposta. `error` del
// backend vince sui 4xx, scritti per il cliente; sui 5xx no: li' arrivano il
// testo del gateway, «Internal Server Error» o un motivo tecnico come
// «OPENAI_API_KEY non configurata», mostrato cosi' in chat il 29/9.
export const MESSAGGIO_NON_DISPONIBILE = "L'assistente non è disponibile in questo momento. Riprova tra poco.";

export function messaggioRisposta(
  status: number,
  data: { reply?: string; error?: string },
): string {
  if (data.reply) return data.reply;
  if (status === 429) return data.error || "Hai raggiunto il limite di domande per oggi. Il contatore si azzera a mezzanotte.";
  if (status === 403) return data.error || "La chat non è disponibile nel tuo piano attuale.";
  if (status === 504) return "L'assistente ha impiegato troppo tempo. Riprova.";
  if (status >= 500) return MESSAGGIO_NON_DISPONIBILE;
  return data.error || "Si è verificato un errore. Riprova.";
}

// Quale delle due quote ha fermato il cliente. Il backend distingue i due casi
// nel messaggio (la RPC ritorna -1 per il giorno, -2 per il mese) e qui serve
// saperlo per non dire la cosa sbagliata: segnare il GIORNO come esaurito su un
// 429 MENSILE fa concludere al cliente «riprovo domani», e domani sara' fermo di
// nuovo. Si riconosce dal testo perche' e' l'unico segnale che arriva al client:
// il campo `error` lo scrive il backend, non l'utente.
export type QuotaEsaurita = "giorno" | "mese" | null;

export function quotaEsaurita(
  status: number,
  data: { error?: string },
): QuotaEsaurita {
  if (status !== 429) return null;
  return (data.error ?? "").includes("questo mese") ? "mese" : "giorno";
}

// Il contatore segue la verita' del backend quando la manda. Il 429 e' il caso
// in cui spesso non la manda: li' la quota e' esaurita per definizione.
//
// ATTENZIONE: su un 429 MENSILE questo porta il contatore del giorno al suo
// massimo, il che e' vero (il cliente non puo' piu' chattare) ma incompleto —
// chi mostra il contatore deve usare `quotaEsaurita` per dire QUALE quota e'
// finita, o il cliente legge «riprova domani» da una barra che parla del giorno.
// Dal 28/9/2026 la usa il provider dell'assistente, via `statoDomande`.
export function contatoreAggiornato(
  status: number,
  data: { domande_oggi?: number },
  limiteGiorno: number,
  attuale: number,
): number {
  if (typeof data.domande_oggi === "number") return data.domande_oggi;
  if (status === 429) return limiteGiorno;
  return attuale;
}

/* ─── Una conversazione per vista: ogni locale la sua, e la catena la sua ─── */
//
// Mattia, 29/9: una conversazione unica che continuava cambiando locale, sotto
// un briefing che nel frattempo era cambiato, era «molto confusionaria» — e il
// modello riceveva comunque solo i messaggi del locale aperto (codaPerVista).
// Ora a schermo c'e' esattamente cio' che l'assistente ricorda: i messaggi di
// questa vista. Quelli delle altre restano salvati e si ritrovano tornandoci.

// Domande proposte nel riquadro, per vista. Guidano chi non sa cosa chiedere.
export const SUGGERIMENTI_SEDE = [
  "Qual è il mio food cost?",
  "Cosa devo pagare?",
  "Com'è andato il MOL?",
  "Chi è il mio fornitore più caro?",
] as const;

export const SUGGERIMENTI_CATENA = [
  "Quale punto vendita ha il margine peggiore?",
  "Dove si spende di più in pesce?",
  "Cosa c'è da vedere nella catena?",
  "Chi ha lo scontrino medio più alto?",
] as const;

// I negozi non hanno food cost, pesce ne' coperti (regola 7: la deviazione
// scatta sul settore, i ristoranti restano con le liste di sopra).
export const SUGGERIMENTI_SEDE_RETAIL = [
  "Qual è il mio costo merce?",
  "Cosa devo pagare?",
  "Com'è andato il MOL?",
  "Chi è il mio fornitore più caro?",
] as const;

export const SUGGERIMENTI_CATENA_RETAIL = [
  "Quale punto vendita ha il margine peggiore?",
  "Dove si spende di più?",
  "Cosa c'è da vedere nella catena?",
  "Quale punto vendita incassa di più?",
] as const;

export function suggerimentiPer(
  contesto: "sede" | "catena",
  settore: string | null | undefined,
): readonly string[] {
  const retail = settore === "retail";
  if (contesto === "catena") return retail ? SUGGERIMENTI_CATENA_RETAIL : SUGGERIMENTI_CATENA;
  return retail ? SUGGERIMENTI_SEDE_RETAIL : SUGGERIMENTI_SEDE;
}

// Le domande proposte nascono da cio' che il briefing ha appena detto (fase F,
// 8/10/2026; Mattia, screen 8: «le domande sotto non sono coerenti con il
// contesto del briefing»). `temi` arriva dal worker nell'ordine del briefing;
// ogni domanda deve avere uno strumento dell'assistente che la sappia
// rispondere. `registra` = la vista sa confermare le cifre dettate (card
// «Conferma»): la Home e `/m` si' (dalla fase I), una vista che non mostra le
// card non deve proporre «Voglio inserire…». I posti liberi si riempiono con le domande fisse. Rincari e
// ribassi li risponde `avvisi_prezzi` (strumenti delle pagine, fase F).
export const DOMANDE_PER_TEMA: Record<string, string> = {
  "buona_notizia:mol_mese": "Come si è chiuso il mese scorso?",
  "buona_notizia:perdita_in_calo": "Come si è chiuso il mese scorso?",
  "buona_notizia:incasso_ieri": "Com'è andato l'incasso del mese finora?",
  "buona_notizia:fatture_arrivate": "Cosa ho comprato negli ultimi giorni?",
  andamento_incasso: "Com'è andato l'incasso del mese finora?",
  mese_chiuso: "Quali categorie hanno pesato di più il mese scorso?",
  food_cost_alto: "Quali categorie pesano di più sul food cost?",
  price_alert: "Quali prodotti sono rincarati di più?",
  prezzo_sceso: "Quali prezzi sono scesi di recente?",
  scadenza_superata: "Cosa devo pagare?",
  scadenza_imminente: "Cosa devo pagare?",
  coperti_anomalia: "Come vanno i coperti questo mese?",
  appuntamento_imminente: "Che appuntamenti ho oggi?",
};

export const DOMANDE_PER_REGISTRARE: Record<string, string> = {
  fatturato_mancante: "Voglio inserire il fatturato del mese scorso",
  costo_personale_mancante: "Voglio inserire il costo del personale",
  incasso_mancante: "Voglio inserire l'incasso di ieri",
};

export const MAX_DOMANDE_PROPOSTE = 4;

export function domandeDalBriefing(
  temi: readonly string[] | null | undefined,
  settore: string | null | undefined,
  opzioni: { registra: boolean },
): string[] {
  const out: string[] = [];
  const aggiungi = (d: string | undefined) => {
    if (d && !out.includes(d) && out.length < MAX_DOMANDE_PROPOSTE) out.push(d);
  };
  for (const t of temi ?? []) {
    aggiungi(DOMANDE_PER_TEMA[t] ?? (opzioni.registra ? DOMANDE_PER_REGISTRARE[t] : undefined));
  }
  for (const d of suggerimentiPer("sede", settore)) aggiungi(d);
  return out;
}

// Dove si trova il cliente quando scrive: una sede precisa o la vista catena.
// `chiave` distingue le sedi fra loro (due locali non sono la stessa vista).
export type Vista = { chiave: string; contesto: "sede" | "catena" };

export function vistaSede(id: string | null | undefined): Vista {
  return { chiave: `sede:${(id ?? "").trim()}`, contesto: "sede" };
}

export function vistaCatena(): Vista {
  return { chiave: "catena", contesto: "catena" };
}

// Un messaggio della conversazione, con la vista in cui e' stato scritto. Una
// risposta dell'assistente puo' portare le card delle cifre dettate (fase 3).
export type VoceChat = {
  role: "user" | "assistant";
  content: string;
  vista: string;
  card?: CardCifra[];
};

// Oltre, le voci piu' vecchie si lasciano cadere: la conversazione vive nel
// browser fino alla fase 5, e sessionStorage ha un limite.
export const MAX_VOCI_SALVATE = 200;

// Stesso contratto di parseStorico: contenuto fuori dal nostro controllo, mai
// un throw. Una voce senza vista (formato del vecchio pulsante flottante) si
// scarta: non sapremmo a quale locale apparteneva. Cosi' anche le righe «Ora
// sei in…» salvate prima del 29/9 (role "vista").
export function parseConversazione(raw: string | null): VoceChat[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (v): v is VoceChat =>
          !!v &&
          (v.role === "user" || v.role === "assistant") &&
          typeof v.content === "string" &&
          typeof v.vista === "string" &&
          v.vista !== "",
      )
      .map((v) => {
        const voce: VoceChat = { role: v.role, content: v.content, vista: v.vista };
        const card = v.role === "assistant" ? cardSalvate(v.card) : [];
        if (card.length) voce.card = card;
        return voce;
      });
  } catch {
    return [];
  }
}

export function daSalvare(voci: VoceChat[]): VoceChat[] {
  return voci.slice(-MAX_VOCI_SALVATE);
}

// Cosa si vede sotto il briefing: i soli messaggi di questa vista.
export function vociDellaVista(voci: VoceChat[], vistaChiave: string): VoceChat[] {
  return voci.filter((v) => v.vista === vistaChiave);
}

// «Nuova conversazione» ricomincia quella di questa vista: le conversazioni
// degli altri locali restano dove sono.
export function senzaVista(voci: VoceChat[], vistaChiave: string): VoceChat[] {
  return voci.filter((v) => v.vista !== vistaChiave);
}

// Cosa si manda a /api/chat: solo i messaggi scritti in QUESTA vista. Prima la
// catena e il punto vendita condividevano la stessa chiave di sessionStorage e
// lo stesso storico, e al backend arrivavano domande fatte su un altro locale
// come contesto di questa.
//
// Una sede senza id (il worker lo lascia vuoto se la risoluzione della sede
// fallisce) darebbe la stessa chiave a tutti i locali: li' si manda solo la
// domanda appena scritta, mai lo storico.
export function codaPerVista(voci: VoceChat[], vista: Vista): Msg[] {
  const della = voci
    .filter((v) => v.vista === vista.chiave)
    .map((v) => ({ role: v.role, content: v.content }));
  return codaDaInviare(vista.chiave.endsWith(":") ? della.slice(-1) : della);
}

// Il corpo di POST /api/chat. `mobile` solo sul telefono: il worker lo usa per dire
// dove si trova Score Fornitori (che sul telefono non c'e'); dal desktop il corpo
// resta quello di prima.
export function corpoRichiestaChat(
  voci: VoceChat[],
  vista: Vista,
  mobile = false,
): { messages: Msg[]; contesto: "sede" | "catena"; card_conferma: true; mobile?: true } {
  return {
    messages: codaPerVista(voci, vista),
    contesto: vista.contesto,
    // Questo client mostra le card con Conferma: il worker puo' offrire
    // all'assistente gli strumenti che le preparano.
    card_conferma: true,
    ...(mobile ? { mobile: true as const } : {}),
  };
}

// Le domande proposte si vedono finche' in questa vista non si e' scritto niente.
export function mostraSuggerimenti(voci: VoceChat[], vista: Vista): boolean {
  return !voci.some((v) => v.role === "user" && v.vista === vista.chiave);
}

// La chiave di sessionStorage e' per utente: sessionStorage sopravvive al logout
// nella stessa scheda, e con una chiave fissa chi entra dopo leggeva la
// conversazione di chi era uscito.
export function chiaveConversazione(utenteId: string): string {
  return `oneflux:assistente:${utenteId}`;
}

// La chiave del vecchio pulsante flottante, condivisa fra catena e PV: si
// cancella al primo caricamento.
export const CHIAVE_VECCHIA = "oneflux:chat-messages";

// La risposta va subito dopo la sua domanda, nella sua vista: se nel frattempo
// il cliente ha cambiato locale e scritto li', la risposta resta nella
// conversazione del locale dove e' partita la domanda. Una domanda alla volta
// (il campo e' bloccato mentre si aspetta), quindi e' l'ultima domanda di
// quella vista.
export function conRisposta(
  voci: VoceChat[],
  vistaChiave: string,
  testo: string,
  card: CardCifra[] = [],
): VoceChat[] {
  let i = voci.length - 1;
  while (i >= 0 && !(voci[i].role === "user" && voci[i].vista === vistaChiave)) i--;
  const risposta: VoceChat = { role: "assistant", content: testo, vista: vistaChiave };
  if (card.length) risposta.card = card;
  if (i < 0) return [...voci, risposta];
  return [...voci.slice(0, i + 1), risposta, ...voci.slice(i + 1)];
}

export function testoAttesa(passo: number): string {
  if (passo <= 0) return "Sto cercando...";
  if (passo === 1) return "Sto leggendo le tue fatture...";
  return "Ci sono quasi, un attimo...";
}

export function testoContatore(rimanenti: number, finita: QuotaEsaurita = null): string {
  // Il 429 mensile non si azzera a mezzanotte: dirlo farebbe riprovare domani.
  if (finita === "mese") return "Limite del mese raggiunto — riparte il mese prossimo";
  if (rimanenti <= 0) return "Limite di oggi raggiunto — si azzera a mezzanotte";
  return `Ti restano ${rimanenti} ${rimanenti === 1 ? "domanda" : "domande"} oggi`;
}

/* ─── Il contatore delle domande di oggi ─────────────────────────────────── */

// Il backend conta UNA quota per account, spesa fra la catena e tutti i punti
// vendita. Le due fonti del numero sono la pagina (il config letto dal server a
// ogni render) e l'ultima risposta di /api/chat: vince la piu' recente. Con una
// mappa per vista, e il provider che non si rimonta mai, un conteggio vecchio
// vinceva sul server — tornando in catena dopo domande nel PV, o il mattino
// dopo con la scheda aperta, quando la casella restava bloccata (revisore, 28/9).
export type Conteggio = { valore: number; alle: number; finita?: QuotaEsaurita };

export function statoDomande(
  limiteGiorno: number,
  server: Conteggio,
  risposta: Conteggio | null,
): { usate: number; rimanenti: number; esaurite: boolean; testo: string } {
  const recente = risposta && risposta.alle > server.alle ? risposta : server;
  const finita = recente.finita ?? null;
  const usate = recente.valore;
  const rimanenti = finita ? 0 : domandeRimanenti(limiteGiorno, usate);
  return { usate, rimanenti, esaurite: rimanenti <= 0, testo: testoContatore(rimanenti, finita) };
}

/* ─── Le cifre dettate: la card con Conferma (fase 3) ────────────────────── */
//
// L'assistente PROPONE (il worker restituisce `proposte` accanto a `reply`), il
// cliente preme Conferma, e solo allora POST /api/assistente/registra scrive.
// La proposta e' gia' il corpo di quella chiamata: il client la rimanda com'e',
// senza ricalcolare niente. Il numero sulla card e' il controllo umano.

export type TipoCifra = "incasso_giorno" | "personale_mese" | "fatturato_mese" | "spesa_extra";

export type PropostaCifra = {
  tipo: TipoCifra;
  ristorante_id: string;
  sede_nome?: string | null;
  data?: string | null;
  anno?: number | null;
  mese?: number | null;
  fatturato_iva10: number;
  altri_ricavi_noiva: number;
  fatturato_iva22: number;
  /** Personale (fase D): le voci dettate, le sole che si scrivono; null = non
   *  dettata. `restano`: le voci gia' registrate che non si toccano. */
  costo_dipendenti?: number | null;
  costo_personale_extra?: number | null;
  costo_personale_chiamata?: number | null;
  restano?: Record<string, number> | null;
  /** Cio' che la card mostra come «risulta …»; null = nessun valore. */
  precedente?: Record<string, number> | null;
  /** Spesa extra (fase D): `importo` com'e' stato pagato, IVA compresa (5/10).
   *  `id_proposta` diventa l'id della spesa: la Conferma ripetuta non la raddoppia. */
  categoria?: string | null;
  descrizione?: string | null;
  importo?: number | null;
  id_proposta?: string | null;
  doppione?: boolean;
};

/** attesa: Conferma e Annulla; invio: la Conferma e' partita; cambiata: nel
 *  frattempo il valore e' cambiato, si chiede una conferma nuova; errore: la
 *  Conferma e' stata rifiutata e non si puo' ripetere. */
export type StatoCard = "attesa" | "invio" | "registrata" | "annullata" | "cambiata" | "errore";

export type CardCifra = { id: string; proposta: PropostaCifra; stato: StatoCard; messaggio?: string };

const TIPI_CIFRA: readonly string[] = ["incasso_giorno", "personale_mese", "fatturato_mese", "spesa_extra"];
const STATI_CARD: readonly string[] = ["attesa", "invio", "registrata", "annullata", "cambiata", "errore"];

function importo(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x) && x >= 0;
}

function intero(x: unknown): x is number {
  return typeof x === "number" && Number.isInteger(x);
}

function valoriValidi(x: unknown): x is Record<string, number> {
  return !!x && typeof x === "object" && !Array.isArray(x) && Object.values(x).every(importo);
}

const VOCI_PERSONALE = ["costo_dipendenti", "costo_personale_extra", "costo_personale_chiamata"] as const;
type VocePersonale = (typeof VOCI_PERSONALE)[number];
const NOME_VOCE: Record<VocePersonale, string> = {
  costo_dipendenti: "Lordo", costo_personale_extra: "Ore extra", costo_personale_chiamata: "Chiamata",
};

// Le voci del personale dettate, nell'ordine di Margini.
function vociDettate(p: Pick<PropostaCifra, VocePersonale>): [VocePersonale, number][] {
  return VOCI_PERSONALE.filter((k) => p[k] != null).map((k) => [k, p[k] as number]);
}

// Arriva dal worker o da sessionStorage: in entrambi i casi si controlla prima
// di mostrarla, perche' Conferma la rimanda al server cosi' com'e'.
export function propostaValida(x: unknown): x is PropostaCifra {
  if (!x || typeof x !== "object") return false;
  const p = x as Record<string, unknown>;
  if (typeof p.tipo !== "string" || !TIPI_CIFRA.includes(p.tipo)) return false;
  if (typeof p.ristorante_id !== "string" || !p.ristorante_id) return false;
  if (!importo(p.fatturato_iva10) || !importo(p.altri_ricavi_noiva) || !importo(p.fatturato_iva22)) return false;
  if (p.precedente != null && !valoriValidi(p.precedente)) return false;
  if (p.sede_nome != null && typeof p.sede_nome !== "string") return false;
  for (const k of VOCI_PERSONALE) if (p[k] != null && !importo(p[k])) return false;
  if (p.restano != null && !valoriValidi(p.restano)) return false;
  if (p.tipo === "spesa_extra") return spesaValida(p);
  if (p.tipo === "incasso_giorno") {
    return typeof p.data === "string" && /^\d{4}-\d{2}-\d{2}$/.test(p.data) && totaleIncasso(p as PropostaCifra) > 0;
  }
  if (!intero(p.anno) || !intero(p.mese) || p.mese < 1 || p.mese > 12) return false;
  if (p.tipo === "personale_mese") return vociDettate(p as PropostaCifra).some(([, v]) => v > 0);
  return totaleIncasso(p as PropostaCifra) > 0;
}

function testoPieno(x: unknown): x is string {
  return typeof x === "string" && x.trim().length > 0;
}

function spesaValida(p: Record<string, unknown>): boolean {
  if (typeof p.data !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(p.data)) return false;
  if (!testoPieno(p.categoria) || !testoPieno(p.descrizione) || !testoPieno(p.id_proposta)) return false;
  if (!importo(p.importo) || p.importo <= 0) return false;
  return p.doppione === undefined || typeof p.doppione === "boolean";
}

// Le card di una risposta di /api/chat. `ora` rende gli id unici fra risposte.
export function cardDaProposte(proposte: unknown, ora: number): CardCifra[] {
  if (!Array.isArray(proposte)) return [];
  return proposte.filter(propostaValida).map((proposta, i) => ({ id: `${ora}-${i}`, proposta, stato: "attesa" }));
}

// Da sessionStorage: una card rimasta «invio» (pagina ricaricata mentre la
// Conferma viaggiava) torna in attesa. Ripeterla e' innocuo: se la cifra e' gia'
// scritta, il server risponde 409 col valore attuale uguale al dettato, ed
// `esitoConferma` lo legge come registrata.
function cardSalvate(x: unknown): CardCifra[] {
  if (!Array.isArray(x)) return [];
  return x
    .filter(
      (c): c is CardCifra =>
        !!c &&
        typeof c.id === "string" &&
        typeof c.stato === "string" &&
        STATI_CARD.includes(c.stato) &&
        (c.messaggio === undefined || typeof c.messaggio === "string") &&
        propostaValida(c.proposta),
    )
    .map((c) => {
      const card: CardCifra = { id: c.id, proposta: c.proposta, stato: c.stato === "invio" ? "attesa" : c.stato };
      if (c.messaggio !== undefined) card.messaggio = c.messaggio;
      return card;
    });
}

export function totaleIncasso(p: Pick<PropostaCifra, "fatturato_iva10" | "altri_ricavi_noiva" | "fatturato_iva22">): number {
  return Math.round((p.fatturato_iva10 + p.altri_ricavi_noiva + p.fatturato_iva22) * 100) / 100;
}

// Il corpo di POST /api/assistente/registra: la proposta senza i campi che
// servono solo a scrivere la card.
// Solo i campi di RegistraRequest: la proposta puo' venire da sessionStorage.
const CAMPI_CONFERMA = [
  "tipo", "ristorante_id", "data", "anno", "mese",
  "fatturato_iva10", "altri_ricavi_noiva", "fatturato_iva22",
  "costo_dipendenti", "costo_personale_extra", "costo_personale_chiamata", "precedente",
  "categoria", "descrizione", "importo", "id_proposta",
] as const;

// Il personale dichiara sempre le tre voci (null = non dettata): il server
// rifiuta la Conferma che non le ha, cioe' quella del client di prima.
export function corpoConferma(p: PropostaCifra): Record<string, unknown> {
  const corpo = Object.fromEntries(CAMPI_CONFERMA.filter((k) => k in p).map((k) => [k, p[k]]));
  if (p.tipo === "personale_mese") for (const k of VOCI_PERSONALE) corpo[k] = p[k] ?? null;
  return corpo;
}

// I campi che la Conferma scrive, come il server li confronta (al centesimo).
function giaCosi(p: PropostaCifra, attuale: Record<string, number>): boolean {
  // Una spesa si aggiunge: non c'e' un valore registrato con cui confrontarla.
  if (p.tipo === "spesa_extra") return false;
  const dettati: Record<string, number> =
    p.tipo === "personale_mese"
      ? Object.fromEntries(vociDettate(p))
      : { fatturato_iva10: p.fatturato_iva10, altri_ricavi_noiva: p.altri_ricavi_noiva, fatturato_iva22: p.fatturato_iva22 };
  return Object.entries(dettati).every(([k, v]) => Math.abs(v - (attuale[k] ?? 0)) < 0.005);
}

export function confermabile(c: CardCifra): boolean {
  return c.stato === "attesa" || c.stato === "cambiata";
}

// Sulla card il punto delle migliaia sempre: l'italiano di Intl non lo mette
// sotto i 10.000 («1800,00 €»), e accanto al «1.800» detto dal cliente sembra
// un'altra cifra.
function euro(v: number): string {
  return v.toLocaleString("it-IT", {
    style: "currency", currency: "EUR", minimumFractionDigits: 2, maximumFractionDigits: 2, useGrouping: "always",
  });
}

const MESI = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

function giornoInChiaro(iso: string, annoCorrente: number): string {
  const [a, m, g] = iso.split("-").map(Number);
  const d = new Date(Date.UTC(a, m - 1, g));
  const settimana = d.toLocaleDateString("it-IT", { weekday: "long", timeZone: "UTC" });
  return `${settimana} ${g} ${MESI[m - 1]}${a !== annoCorrente ? ` ${a}` : ""}`;
}

export type TestoCard = { titolo: string; sede: string | null; righe: [string, string][]; totale: string | null; nota: string | null };

// Cosa dice la card: cosa, dove, quando, gli importi in chiaro e il valore che
// sostituisce. `annoCorrente` (di Roma) toglie l'anno dai giorni di quest'anno.
export function testoCard(p: PropostaCifra, annoCorrente: number): TestoCard {
  const sede = p.sede_nome?.trim() || null;
  if (p.tipo === "spesa_extra") return testoSpesa(p, sede, annoCorrente);
  const quando =
    p.tipo === "incasso_giorno" ? giornoInChiaro(p.data ?? "", annoCorrente) : `${MESI[(p.mese ?? 1) - 1]} ${p.anno}`;
  if (p.tipo === "personale_mese") return testoPersonale(p, sede, quando);
  const righe: [string, string][] = [
    ["Al 10%", euro(p.fatturato_iva10)],
    ["Senza IVA", euro(p.altri_ricavi_noiva)],
  ];
  if (p.fatturato_iva22 > 0) righe.push(["Al 22%", euro(p.fatturato_iva22)]);
  const prima = p.precedente
    ? totaleIncasso({
        fatturato_iva10: p.precedente.fatturato_iva10 ?? 0,
        altri_ricavi_noiva: p.precedente.altri_ricavi_noiva ?? 0,
        fatturato_iva22: p.precedente.fatturato_iva22 ?? 0,
      })
    : null;
  return {
    titolo: p.tipo === "incasso_giorno" ? `Incasso di ${quando}` : `Fatturato di ${quando}`,
    sede,
    righe,
    totale: euro(totaleIncasso(p)),
    nota: prima != null ? `Risulta già ${euro(prima)}: lo sostituisco.` : null,
  };
}

// Le sole voci dettate: le altre restano come sono e la card le nomina.
function testoPersonale(p: PropostaCifra, sede: string | null, quando: string): TestoCard {
  const dettate = vociDettate(p);
  const unaSola = dettate.length === 1;
  const prima = dettate
    .map(([k]) => [k, p.precedente?.[k] ?? 0] as const)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => (unaSola ? euro(v) : `${NOME_VOCE[k].toLowerCase()} ${euro(v)}`));
  const restano = VOCI_PERSONALE.filter((k) => (p.restano?.[k] ?? 0) > 0).map(
    (k) => `${euro(p.restano?.[k] ?? 0)} di ${NOME_VOCE[k].toLowerCase()}`,
  );
  return {
    titolo: `Costo del personale di ${quando}`,
    sede,
    righe: dettate.map(([k, v]) => [NOME_VOCE[k], euro(v)]),
    totale: unaSola ? null : euro(Math.round(dettate.reduce((s, [, v]) => s + v, 0) * 100) / 100),
    nota: [
      prima.length ? `Risulta già ${prima.join(" e ")}: ${prima.length === 1 ? "lo" : "li"} sostituisco.` : null,
      restano.length ? `Più ${restano.join(" e ")} già registrati, che restano.` : null,
    ].filter(Boolean).join(" ") || null,
  };
}

function testoSpesa(p: PropostaCifra, sede: string | null, annoCorrente: number): TestoCard {
  const righe: [string, string][] = [
    ["Voce", p.descrizione ?? ""],
    ["Categoria", p.categoria ?? ""],
    ["Importo", euro(p.importo ?? 0)],
  ];
  return {
    titolo: `Spesa extra di ${giornoInChiaro(p.data ?? "", annoCorrente)}`,
    sede,
    righe,
    totale: null,
    nota: p.doppione ? "C'è già una spesa uguale in questo giorno: confermando ne aggiungi un'altra." : null,
  };
}

// Dopo la Conferma di una spesa: dove la trova e come entra nel MOL (fase B:
// solo con «Recupera», come quelle scritte a mano).
export const MESSAGGIO_SPESA_REGISTRATA =
  "Registrata nelle Spese dell'Agenda. Nel MOL entra quando in Margini premi «Recupera dal tab Spese».";

// Com'e' andata la Conferma. Il 409 «valore_cambiato» porta il valore di adesso:
// diventa il nuovo «risulta …» e si chiede una conferma nuova, mai in automatico.
export function esitoConferma(status: number, data: unknown, card: CardCifra): CardCifra {
  const detail = data && typeof data === "object" ? (data as { detail?: unknown }).detail : undefined;
  if (status >= 200 && status < 300) {
    const messaggio = card.proposta.tipo === "spesa_extra" ? MESSAGGIO_SPESA_REGISTRATA : "Registrato.";
    return { ...card, stato: "registrata", messaggio };
  }
  if (status === 409 && detail && typeof detail === "object") {
    const { motivo, attuale } = detail as { motivo?: unknown; attuale?: unknown };
    if (motivo === "valore_cambiato" && (attuale == null || valoriValidi(attuale))) {
      // La stessa Conferma ripetuta (pagina ricaricata, risposta persa): il
      // valore «cambiato» e' proprio quello dettato.
      if (attuale && giaCosi(card.proposta, attuale as Record<string, number>)) {
        return { ...card, stato: "registrata", messaggio: "Registrato." };
      }
      const precedente = (attuale as Record<string, number> | null | undefined) ?? null;
      return {
        ...card,
        proposta: { ...card.proposta, precedente },
        stato: "cambiata",
        messaggio: precedente
          ? "Nel frattempo il valore è cambiato (lo vedi qui sopra). Se vuoi sostituirlo, premi di nuovo Conferma."
          : "Nel frattempo il valore registrato è stato tolto. Se vuoi registrare questa cifra, premi di nuovo Conferma.",
      };
    }
    if (motivo === "mese_a_totale") {
      return { ...card, stato: "errore", messaggio: "Questo mese è tenuto come totale del mese: il singolo giorno non si registra. Puoi dettarmi il nuovo totale del mese." };
    }
    if (motivo === "mese_con_giorni") {
      return { ...card, stato: "errore", messaggio: "Questo mese ha già gli incassi giorno per giorno: il fatturato del mese è la loro somma. Puoi dettarmi l'incasso di un giorno." };
    }
  }
  if (status === 400 && typeof detail === "string" && detail) {
    return { ...card, stato: "errore", messaggio: `Non registrato. ${detail}.` };
  }
  if (status === 404) return { ...card, stato: "errore", messaggio: "Non registrato: questo locale non è più disponibile." };
  if (status === 403) return { ...card, stato: "errore", messaggio: "Non registrato: non hai il permesso di registrare questa cifra." };
  if (status === 401) return { ...card, stato: "attesa", messaggio: "La sessione è scaduta: rientra e premi di nuovo Conferma." };
  return { ...card, stato: "attesa", messaggio: "Non sono riuscito a registrarla. Riprova tra poco." };
}

export function conCard(voci: VoceChat[], id: string, f: (c: CardCifra) => CardCifra): VoceChat[] {
  return voci.map((v) =>
    v.card?.some((c) => c.id === id) ? { ...v, card: v.card.map((c) => (c.id === id ? f(c) : c)) } : v,
  );
}

export function trovaCard(voci: VoceChat[], id: string): CardCifra | null {
  for (const v of voci) for (const c of v.card ?? []) if (c.id === id) return c;
  return null;
}
