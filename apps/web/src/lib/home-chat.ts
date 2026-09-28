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
// backend vince quando c'e'; il 504 no, perche' li' il messaggio del gateway
// non e' scritto per un ristoratore.
export function messaggioRisposta(
  status: number,
  data: { reply?: string; error?: string },
): string {
  if (data.reply) return data.reply;
  if (status === 429) return data.error || "Hai raggiunto il limite di domande per oggi. Il contatore si azzera a mezzanotte.";
  if (status === 403) return data.error || "La chat non è disponibile nel tuo piano attuale.";
  if (status === 504) return "L'assistente ha impiegato troppo tempo. Riprova.";
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

/* ─── Una conversazione sola, con la vista in cui e' stato scritto ogni messaggio ─ */

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

// Dove si trova il cliente quando scrive: una sede precisa o la vista catena.
// `chiave` distingue le sedi fra loro (due locali non sono la stessa vista);
// `frase` e' la riga che la conversazione mostra quando si cambia.
export type Vista = { chiave: string; contesto: "sede" | "catena"; frase: string };

export function vistaSede(id: string | null | undefined, nome: string | null | undefined): Vista {
  const n = (nome ?? "").trim();
  return {
    chiave: `sede:${(id ?? "").trim()}`,
    contesto: "sede",
    frase: n ? `Ora sei in ${n}` : "Ora sei nel tuo locale",
  };
}

export function vistaCatena(nomeGruppo: string | null | undefined): Vista {
  const n = (nomeGruppo ?? "").trim();
  return {
    chiave: "catena",
    contesto: "catena",
    frase: n ? `Ora sei nella vista catena del gruppo ${n}` : "Ora sei nella vista catena",
  };
}

// Una voce della conversazione: un messaggio, o la riga «Ora sei in…».
export type VoceChat = {
  role: "user" | "assistant" | "vista";
  content: string;
  vista: string;
};

// Oltre, le voci piu' vecchie si lasciano cadere: la conversazione vive nel
// browser fino alla fase 5, e sessionStorage ha un limite.
export const MAX_VOCI_SALVATE = 200;

// Stesso contratto di parseStorico: contenuto fuori dal nostro controllo, mai
// un throw. Una voce senza vista (formato del vecchio pulsante flottante) si
// scarta: non sapremmo a quale locale apparteneva.
export function parseConversazione(raw: string | null): VoceChat[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (v): v is VoceChat =>
        !!v &&
        (v.role === "user" || v.role === "assistant" || v.role === "vista") &&
        typeof v.content === "string" &&
        typeof v.vista === "string" &&
        v.vista !== "",
    );
  } catch {
    return [];
  }
}

export function daSalvare(voci: VoceChat[]): VoceChat[] {
  return voci.slice(-MAX_VOCI_SALVATE);
}

// Il cliente e' arrivato in `vista`: se la conversazione era altrove, compare la
// riga «Ora sei in…». In una conversazione vuota niente riga (non c'e' niente da
// cui distinguersi); due cambi di fila non lasciano due righe; tornare dove si
// era prima di un cambio senza aver scritto niente la toglie.
export function entraInVista(voci: VoceChat[], vista: Vista): VoceChat[] {
  if (!voci.some((v) => v.role !== "vista")) return voci;
  const ultima = voci[voci.length - 1];
  if (ultima.vista === vista.chiave) return voci;
  const base = ultima.role === "vista" ? voci.slice(0, -1) : voci;
  if (base.length === 0 || base[base.length - 1].vista === vista.chiave) return base;
  return [...base, { role: "vista", content: vista.frase, vista: vista.chiave }];
}

// Cosa si manda a /api/chat: solo i messaggi scritti in QUESTA vista. Prima la
// catena e il punto vendita condividevano la stessa chiave di sessionStorage e
// lo stesso storico, e al backend arrivavano domande fatte su un altro locale
// come contesto di questa. Le righe «Ora sei in…» non si mandano mai.
export function codaPerVista(voci: VoceChat[], vista: Vista): Msg[] {
  return codaDaInviare(
    voci
      .filter((v): v is VoceChat & { role: "user" | "assistant" } => v.role !== "vista" && v.vista === vista.chiave)
      .map((v) => ({ role: v.role, content: v.content })),
  );
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

// La risposta va subito dopo la sua domanda, non in fondo: se nel frattempo il
// cliente ha cambiato sede, in fondo c'e' gia' la riga «Ora sei in…», e una
// risposta sotto quella riga sembrerebbe detta sul locale nuovo. Una domanda
// alla volta (il campo e' bloccato mentre si aspetta), quindi e' l'ultima
// domanda di quella vista.
export function conRisposta(voci: VoceChat[], vistaChiave: string, testo: string): VoceChat[] {
  let i = voci.length - 1;
  while (i >= 0 && !(voci[i].role === "user" && voci[i].vista === vistaChiave)) i--;
  const risposta: VoceChat = { role: "assistant", content: testo, vista: vistaChiave };
  if (i < 0) return [...voci, risposta];
  return [...voci.slice(0, i + 1), risposta, ...voci.slice(i + 1)];
}

export function testoAttesa(passo: number): string {
  if (passo <= 0) return "Sto cercando...";
  if (passo === 1) return "Sto leggendo le tue fatture...";
  return "Ci sono quasi, un attimo...";
}

export function testoContatore(rimanenti: number): string {
  if (rimanenti <= 0) return "Limite di oggi raggiunto — si azzera a mezzanotte";
  return `Ti restano ${rimanenti} ${rimanenti === 1 ? "domanda" : "domande"} oggi`;
}
