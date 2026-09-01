// Chat della Home — logica pura estratta da chat-widget.tsx.

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
  if (status === 429) return data.error || "Hai raggiunto il limite di domande per oggi. Riprova domani.";
  if (status === 403) return data.error || "La chat non è disponibile nel tuo piano attuale.";
  if (status === 504) return "L'assistente ha impiegato troppo tempo. Riprova.";
  return data.error || "Si è verificato un errore. Riprova.";
}

// Il contatore segue la verita' del backend quando la manda. Il 429 e' il caso
// in cui spesso non la manda: li' la quota e' esaurita per definizione.
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
