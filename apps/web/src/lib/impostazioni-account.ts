// Logica della pagina Impostazioni → account. Estratta dai .tsx perche' l'unica
// rete sul frontend (`npx tsc --noEmit`) controlla i tipi e non esegue niente:
// soglie e macchine a stati restavano non provate.

export type LivelloUso = "critico" | "attenzione" | "ok";

export type StatoUsageBar = {
  pct: number;
  livello: LivelloUso;
  mostraAvviso: boolean;
};

// Il livello e' la decisione, la classe CSS e' la resa: se questa funzione
// tornasse "bg-red-500" un redesign farebbe fallire dei test di logica.
export function statoUsageBar(usate: number, limite: number): StatoUsageBar {
  const pct = limite > 0 ? Math.min(100, Math.round((usate / limite) * 100)) : 0;
  const livello: LivelloUso = pct >= 90 ? "critico" : pct >= 70 ? "attenzione" : "ok";
  // Avviso e colore derivano dallo STESSO pct: nel .tsx erano due confronti
  // `>= 90` separati, che una modifica futura poteva disallineare.
  return { pct, livello, mostraAvviso: livello === "critico" };
}

export type StatoChatAi =
  | { modo: "nascosto" }
  | { modo: "non_incluso" }
  | { modo: "barra"; usate: number; limite: number; label: string; nota: string; avviso: string; ricarica: number };

// Crediti AI (fase J, 10/10/2026): la barra e' quella del MESE, il vincolo
// vero. Il giorno resta solo se il worker non manda il mese (versione vecchia).
const CHAT_LABEL_GRUPPO = "Crediti AI del gruppo (questo mese)";
const CHAT_LABEL_SEDE = "Crediti AI (questo mese)";
const CHAT_NOTA_POOL =
  "Condivisi tra tutti i punti vendita e la modalità catena. Si rinnovano il 1° di ogni mese.";
const CHAT_NOTA_SEDE = "Si rinnovano il 1° di ogni mese.";
const CHAT_LABEL_GRUPPO_GIORNO = "Crediti AI del gruppo (oggi)";
const CHAT_LABEL_SEDE_GIORNO = "Crediti AI (oggi)";
const CHAT_NOTA_GIORNO = "Il contatore si azzera ogni giorno a mezzanotte.";

export type DatiChatAi = {
  chat_limite_giorno?: number | null;
  chat_limite_mese?: number | null;
  chat_crediti_oggi?: number | null;
  chat_crediti_mese?: number | null;
  chat_crediti_ricarica?: number | null;
  chat_pool?: boolean | null;
};

// Tre esiti che nel .tsx erano due condizioni annidate dentro il JSX: assente
// (il piano non espone il dato), incluso con quota, non incluso nel piano.
export function statoChatAi(d: DatiChatAi): StatoChatAi {
  const limiteGiorno = d.chat_limite_giorno;
  if (limiteGiorno == null) return { modo: "nascosto" };
  if (!(limiteGiorno > 0)) return { modo: "non_incluso" };
  const ricarica = Math.max(0, d.chat_crediti_ricarica ?? 0);
  const limiteMese = d.chat_limite_mese ?? 0;
  if (limiteMese > 0) {
    return {
      modo: "barra",
      usate: d.chat_crediti_mese ?? 0,
      limite: limiteMese,
      label: d.chat_pool ? CHAT_LABEL_GRUPPO : CHAT_LABEL_SEDE,
      nota: d.chat_pool ? CHAT_NOTA_POOL : CHAT_NOTA_SEDE,
      avviso: "Hai quasi esaurito i crediti del mese.",
      ricarica,
    };
  }
  return {
    modo: "barra",
    usate: d.chat_crediti_oggi ?? 0,
    limite: limiteGiorno,
    label: d.chat_pool ? CHAT_LABEL_GRUPPO_GIORNO : CHAT_LABEL_SEDE_GIORNO,
    nota: CHAT_NOTA_GIORNO,
    avviso: "Hai quasi esaurito i crediti di oggi.",
    ricarica,
  };
}

// Le due conferme distruttive NON hanno la stessa regola, ed e' deliberato:
// il worker rivalida con la stessa asimmetria (services/routers/account.py:284
// case-sensitive su SVUOTA, :405 case-insensitive su ELIMINA). Uniformarle qui
// le disallineerebbe dal backend.
export function confermaSvuotamentoValida(testo: string | null | undefined): boolean {
  return (testo ?? "").trim() === "SVUOTA";
}

export function confermaEliminazioneValida(testo: string | null | undefined): boolean {
  return (testo ?? "").trim().toUpperCase() === "ELIMINA";
}

// La scheda «Email settimanale» nelle Impostazioni: solo se l'admin l'ha
// abilitata per questo cliente (Mattia, 25/09/2026: la accende lui, cliente per
// cliente) e mai a un admin, escluso dai destinatari. Fuori da questi casi
// l'interruttore prometterebbe un'email che non parte. Assente = non abilitata.
export function mostraEmailSettimanale(data: {
  is_admin?: boolean | null;
  email_settimanale_abilitata?: boolean | null;
}): boolean {
  return data.is_admin !== true && data.email_settimanale_abilitata === true;
}
