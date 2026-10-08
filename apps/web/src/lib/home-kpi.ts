// Decisioni della Home (dashboard) — logica pura, zero React.
//
// Sta qui e non nei .tsx per un motivo pratico: l'harness pytest->node esegue
// solo i moduli di lib/. Dentro un componente questa logica non e' raggiungibile
// da nessun test, e la Home ne ha gia' pagato il prezzo (vedi statoBlocchi).
//
// Per la stessa ragione questo file NON importa da lib/home.ts, nemmeno i tipi:
// home.ts importa "./worker" con path relativo, che l'harness non risolve
// (riscrive solo l'alias @/). Un import di solo tipo basta a rendere il modulo
// non eseguibile — e' successo scrivendo questi test. Le forme che servono
// sono dichiarate qui, strutturali.

/* ─── kpi-block.tsx: la tinta del delta di una voce ──────────────────────── */

// null = grigio (nessun giudizio), true = verde, false = rosso.
export type Tinta = boolean | null;

export type Direzione = "su" | "giu" | "piatto";

// Tabella di verita' a 4 ingressi, prima annegata nel corpo di <Trend>.
//
// `sopprimi`: la voce vale 0 nel mese corrente (tipicamente dato non ancora
// caricato). Il confronto con un mese pieno darebbe un crollo fuorviante
// ("-100%"): meglio "—" che una bugia.
//
// `neutro`: mostra la freccia ma MAI in verde. Serve sul MOL quando il valore
// corrente e' negativo: salire da -5.000 a -1.188 e' "meno peggio", non una
// vittoria, e festeggiarlo in verde sarebbe una falsa celebrazione della
// perdita (decisione Mattia 19/06).
//
// Attenzione: `neutro` riguarda il DELTA rispetto al mese scorso, non la
// direzione della curva annuale — quella la decide calcolaSparkline, che dal
// fix dell'1/9 colora di verde un MOL negativo in risalita. Non e' una
// contraddizione: li' la domanda e' "sta migliorando?", qui e' "e' un buon
// risultato?". Un MOL in perdita che risale sta migliorando ma non e' buono.
export function tintaTrend(opts: {
  delta: number | null;
  buonoSeSu: boolean;
  sopprimi?: boolean;
  neutro?: boolean;
}): { mostra: boolean; tinta: Tinta; direzione: Direzione } {
  const { delta, buonoSeSu, sopprimi = false, neutro = false } = opts;
  if (sopprimi || delta == null) {
    return { mostra: false, tinta: null, direzione: "piatto" };
  }
  const su = delta > 0;
  const piatto = delta === 0;
  const direzione: Direzione = piatto ? "piatto" : su ? "su" : "giu";
  const tinta: Tinta = neutro || piatto ? null : su === buonoSeSu;
  return { mostra: true, tinta, direzione };
}

/* ─── kpi-block.tsx: i mesi di ferie ─────────────────────────────────────── */

// Un mese con l'incasso molto sotto i vicini (ferie, chiusura) non si giudica
// e non fa da confronto: il worker azzera le variazioni e dice quale dei due
// mesi e' fuori norma. L'8/10/2026 la Home di OVERTIME mostrava settembre
// «fatturato +428%» e «food cost -65 punti» in verde contro un agosto chiuso.
export function testoConfronto(kpi: {
  confronto_label?: string | null;
  confronto_escluso?: string | null;
}): string | null {
  if (kpi.confronto_escluso) {
    return `nessun confronto con ${kpi.confronto_escluso}: incasso fuori dal solito`;
  }
  return kpi.confronto_label ?? null;
}

// `merce` arriva da costoMerceLabel gia' minuscola: "food cost" o "costo merce".
export function avvisoIncassoFuoriNorma(
  kpi: { incasso_fuori_norma?: boolean; periodo_label: string },
  merce: string,
): string | null {
  if (kpi.incasso_fuori_norma !== true) return null;
  return (
    `Nel mese di ${kpi.periodo_label.toLowerCase()} l'incasso è stato molto più basso del solito ` +
    `(ferie o incasso non completo): il ${merce} e il margine di questo mese non sono un allarme.`
  );
}

/* ─── page.tsx: quale blocco mostrare ────────────────────────────────────── */

export type StatoBlocchi = "worker-giu" | "vuoto" | "dati";

// Tre stati distinti, e la distinzione e' gia' costata una regressione:
//
//   - worker giu' (nessuna delle due risposte): e' un cold-start o un timeout,
//     va mostrato il retry. Mostrare "Nessuna fattura" a un cliente che ha dati
//     veri e' il modo peggiore di sbagliare.
//   - vuoto: risposta arrivata, ma senza dati di margine per il periodo.
//   - dati: tutto normale.
//
// Il punto delicato e' che "vuoto" NON dipende da salute: un cliente nuovo puo'
// avere un indice di salute (calcolato su altre componenti) e zero margini allo
// stesso tempo. Prima la condizione richiedeva anche `!salute`, quindi con
// salute presente il messaggio non compariva mai e restava un buco silenzioso.
export function statoBlocchi(
  kpi: { has_data: boolean } | null | undefined,
  salute: unknown | null | undefined,
): StatoBlocchi {
  if (!salute && !kpi) return "worker-giu";
  if (kpi?.has_data === false) return "vuoto";
  return "dati";
}

// La chat c'e' solo se abilitata E con quota > 0 (i piani free hanno 0).
// I default sono ottimisti (`?? true`) di proposito: una config che non arriva
// non deve spegnere la chat a chi l'ha pagata. Il limite invece parte da 0 —
// sull'altro default il verso e' opposto, perche' regalare quota non si fa.
export function chatVisibile(
  config: { chat_ai_enabled?: boolean | null; chat_limite_giorno?: number | null } | null | undefined,
): boolean {
  return (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
}

/* ─── salute-card.tsx: quali voci della completezza si aprono ────────────── */

// La card della completezza era alta mezza pagina perche' ogni voce, anche
// quelle a posto, aveva la sua riga con dettaglio (Mattia, 28/9: «enormi»).
// Ora si aprono solo le voci da sistemare; quelle a posto stanno in una riga
// sola coi nomi. L'ordine del backend si conserva in entrambe le liste.
export function vociCompletezza<V extends { ok: boolean }>(
  voci: readonly V[] | null | undefined,
): { daSistemare: V[]; aPosto: V[] } {
  const tutte = voci ?? [];
  return {
    daSistemare: tutte.filter((v) => !v.ok),
    aPosto: tutte.filter((v) => v.ok),
  };
}
