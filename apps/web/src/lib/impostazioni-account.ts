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
  | { modo: "barra"; usate: number; limite: number; label: string; nota: string };

const CHAT_LABEL_GRUPPO = "Domande all'assistente AI del gruppo (oggi)";
const CHAT_LABEL_SEDE = "Domande all'assistente AI (oggi)";
const CHAT_NOTA_POOL =
  "Pool condiviso tra tutti i punti vendita e la modalità catena. Si azzera ogni giorno a mezzanotte.";
const CHAT_NOTA_SEDE = "Il contatore si azzera ogni giorno a mezzanotte.";

// Tre esiti che nel .tsx erano due condizioni annidate dentro il JSX: assente
// (il piano non espone il dato), incluso con quota, non incluso nel piano.
export function statoChatAi(
  limite: number | null | undefined,
  usate: number | null | undefined,
  pool: boolean | null | undefined,
): StatoChatAi {
  if (limite == null) return { modo: "nascosto" };
  if (!(limite > 0)) return { modo: "non_incluso" };
  return {
    modo: "barra",
    usate: usate ?? 0,
    limite,
    label: pool ? CHAT_LABEL_GRUPPO : CHAT_LABEL_SEDE,
    nota: pool ? CHAT_NOTA_POOL : CHAT_NOTA_SEDE,
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
