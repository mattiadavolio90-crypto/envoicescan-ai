// L'avatar dell'assistente in Home (fase L, decisioni di Mattia del 15/10/2026): non un
// viso ma un flusso astratto, tre nastri di fili che si attorcigliano su se stessi mentre
// scorrono, con fili di luce che salgono. Qui la logica pura, provata da
// tests/test_avatar_flusso_frontend.py; il disegno sta in components/home/disegno-flusso.ts.

export type ModoAvatar = "riposo" | "ascolta" | "pensa" | "parla";

/** La voce vince su tutto: se legge il briefing mentre aspetta una risposta, parla. */
export function modoAvatar(s: { parla: boolean; pensa: boolean; ascolta: boolean }): ModoAvatar {
  if (s.parla) return "parla";
  if (s.pensa) return "pensa";
  if (s.ascolta) return "ascolta";
  return "riposo";
}

export const TESTO_MODO: Record<ModoAvatar, string> = {
  riposo: "Pronto",
  ascolta: "Ti ascolto",
  pensa: "Sto pensando…",
  parla: "Sto leggendo il briefing",
};

/** Avvicina `attuale` a `obiettivo` in modo esponenziale, indipendente dal frame rate. */
export function avvicina(attuale: number, obiettivo: number, k: number, dt: number): number {
  return attuale + (obiettivo - attuale) * (1 - Math.exp(-k * dt));
}

/** Livello della voce smorzato: sale svelto e scende piano, perché il flusso non tremi. */
export function livelloVoce(attuale: number, obiettivo: number, dt: number): number {
  return avvicina(attuale, obiettivo, obiettivo > attuale ? 18 : 6, dt);
}

/**
 * Il ritmo di una voce che legge, in [0,1]: sillabe svelte dentro un respiro lento.
 * Simulato di proposito (decisione del 15/10): leggere l'audio vero con Web Audio
 * farebbe passare il suono di «Ascolta» da un altro canale, e se il contesto audio non
 * parte la lettura resta muta.
 */
export function voceSimulata(t: number): number {
  const sillaba = 0.5 + 0.5 * Math.sin(t * 10.5 + 2.2 * Math.sin(t * 2.7));
  const respiro = 0.6 + 0.4 * Math.sin(t * 1.3);
  return Math.min(1, 0.15 + 0.7 * sillaba * respiro);
}

/** Generatore pseudo-casuale deterministico (Park-Miller): stesso seme, stesso flusso. */
export function generatore(seme: number): () => number {
  let s = Math.max(1, Math.floor(seme) % 2147483647);
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
}

export type Nastro = { fase: number; larg: number; dy: number };
export const NASTRI: readonly Nastro[] = [
  { fase: 0, larg: 1, dy: 0.02 },
  { fase: 2.1, larg: 0.75, dy: -0.03 },
  { fase: 4.2, larg: 0.55, dy: 0.04 },
];
/** Quanti giri fa un nastro su se stesso da un capo all'altro. */
export const GIRI = 1.15;

/** Quanto pesa ogni modo, da 0 a 1 (le transizioni sono graduali). */
export type Pesi = { ascolta: number; pensa: number; parla: number };

/** Ampiezza dell'onda: respira lenta a riposo, si apre quando ascolta. */
export function ampiezza(p: Pesi, t: number): number {
  return (1 + 0.45 * p.ascolta + 0.2 * p.pensa + 0.15 * p.parla) * (0.85 + 0.15 * Math.sin(t * 0.55));
}

/** Velocità di scorrimento e di rotazione su se stessi: svelte quando pensa. */
export function velocita(p: Pesi): { fase: number; giro: number } {
  return {
    fase: 1 + 0.35 * p.ascolta + 1.4 * p.pensa + 0.5 * p.parla,
    giro: 0.55 + 0.3 * p.ascolta + 1.8 * p.pensa + 0.6 * p.parla,
  };
}

/** Quanti fili di luce nascono al secondo. */
export function nascitaFili(p: Pesi, voce: number): number {
  return 13 + 9 * p.ascolta + 16 * p.pensa + 24 * voce;
}

export type Spinta = {
  fase: number;
  amp: number;
  voce: number;
  pensa: number;
  /** Dove sta il cursore lungo il nastro (0-1), quanto è vicino (0-1), sopra (+1) o sotto (-1). */
  uc: number;
  vicino: number;
  verso: number;
};

/** Altezza della linea centrale di un nastro nel punto u (0-1), in unità del disegno. */
export function centroNastro(u: number, t: number, q: Spinta, n: Nastro): number {
  const f = q.fase;
  let y =
    0.11 * Math.sin(u * 5.2 + f * 0.4 + n.fase * 0.7) +
    0.035 * Math.sin(u * 11 - f * 0.6 + n.fase) +
    n.dy * Math.sin(u * 7 + f * 0.5);
  y *= q.amp;
  y += q.voce * 0.035 * Math.sin(u * 30 - t * 13) * Math.sin(u * Math.PI);
  y += q.pensa * 0.008 * Math.sin(u * 40 + t * 10);
  y += q.vicino * q.verso * 0.06 * Math.exp(-((u - q.uc) ** 2) / 0.01);
  return y;
}

/**
 * Dove il nastro si mostra di taglio (angolo di 90° + k·180°): lì i fili si stringono e
 * si accende un nodo di luce. Solo dentro (0,06 – 0,94): ai capi il nastro sfuma.
 */
export function nodiDiTaglio(giro: number, faseNastro: number): number[] {
  const nodi: number[] = [];
  const g = ((giro % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  for (let k = -3; k <= 5; k++) {
    const u = (Math.PI / 2 + k * Math.PI - g - faseNastro) / (2 * Math.PI * GIRI);
    if (u >= 0.06 && u <= 0.94) nodi.push(u);
  }
  return nodi.sort((a, b) => a - b);
}

export type Frase = { inizio: number; fine: number; testo: string };

/** Il testo diviso in frasi; un punto fra due cifre («2.340 €») non chiude la frase. */
export function frasi(testo: string): Frase[] {
  const out: Frase[] = [];
  const re = /[\s\S]*?[.!?](?=\s|$)\s*/g;
  let m: RegExpExecArray | null;
  let fine = 0;
  while ((m = re.exec(testo)) && m[0].length) {
    out.push({ inizio: m.index, fine: m.index + m[0].length, testo: m[0] });
    fine = m.index + m[0].length;
  }
  if (fine < testo.length) out.push({ inizio: fine, fine: testo.length, testo: testo.slice(fine) });
  return out;
}

/** Indice della frase che contiene il carattere, -1 se fuori dal testo. */
export function fraseAl(elenco: readonly Frase[], carattere: number): number {
  if (carattere < 0) return -1;
  return elenco.findIndex((f) => carattere >= f.inizio && carattere < f.fine);
}

/**
 * A che carattere della narrativa è arrivata la lettura, data la frazione letta di tutto il
 * testo d'«Ascolta» (che può avere il saluto davanti e un avviso dietro). -1 se la lettura è
 * ancora sul saluto o il testo non contiene la narrativa.
 */
export function carattereNarrativa(testoAscolta: string, narrativa: string, frazione: number): number {
  const inizio = testoAscolta.indexOf(narrativa);
  if (inizio < 0 || !narrativa) return -1;
  const c = Math.floor(Math.min(1, Math.max(0, frazione)) * testoAscolta.length) - inizio;
  return c >= 0 && c < narrativa.length ? c : -1;
}

/** Caratteri al secondo della voce di «Ascolta» (Google a 1,25x): per stimare dove legge
 *  quando la durata dell'audio non è nota. */
export const CARATTERI_AL_SECONDO = 15;

/** Il giorno di Roma, «AAAA-MM-GG»: il benvenuto si mostra una volta al giorno. */
export function giornoDiRoma(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome" }).format(d);
}

export function chiaveBenvenuto(giorno: string): string {
  return `oneflux:benvenuto:${giorno}`;
}

/** Il benvenuto parte se oggi non è ancora stato visto e il sistema non chiede meno animazioni. */
export function mostraBenvenuto(s: { gia_visto: boolean; meno_animazioni: boolean }): boolean {
  return !s.gia_visto && !s.meno_animazioni;
}

/** Dove sta la linea del flusso, in frazione dell'altezza: più in basso nella colonna alta,
 *  così i fili di luce la riempiono. */
export type VarianteAvatar = "colonna" | "fascia" | "palco";
export const BASE_FLUSSO: Record<VarianteAvatar, number> = { colonna: 0.64, fascia: 0.6, palco: 0.6 };

export type Palette = {
  composizione: "source-over" | "lighter";
  alfa: number;
  /** Fili lontano, a metà, vicino. */
  piani: readonly [string, string, string];
  /** Inizio di un «rgba(r,g,b,» da chiudere con l'opacità. */
  luce: string;
  punta: string;
  nodo: string;
  alone: string;
  /** Opacità massima dei nodi di luce e delle luci sfocate di fondo. */
  forzaNodo: number;
  forzaAlone: number;
};

/** In chiaro inchiostro blu sul bianco; in scuro luce sommata ma bassa («troppo
 *  fluorescente» la prima versione). */
export const PALETTE: Record<"chiaro" | "scuro", Palette> = {
  chiaro: {
    composizione: "source-over",
    alfa: 0.95,
    piani: ["rgb(120,178,214)", "rgb(25,125,188)", "rgb(3,78,126)"],
    luce: "rgba(18,118,180,",
    punta: "rgb(3,90,140)",
    nodo: "rgba(14,140,210,",
    alone: "rgba(14,165,233,",
    forzaNodo: 0.35,
    forzaAlone: 0.16,
  },
  scuro: {
    composizione: "lighter",
    alfa: 0.72,
    piani: ["rgb(36,88,134)", "rgb(60,146,204)", "rgb(140,205,240)"],
    luce: "rgba(70,160,220,",
    punta: "rgb(205,238,255)",
    nodo: "rgba(170,225,255,",
    alone: "rgba(56,189,248,",
    forzaNodo: 0.45,
    forzaAlone: 0.22,
  },
};

/** «rgba(r,g,b,» + opacità limitata a [0,1] con tre decimali. */
export function conOpacita(inizio: string, a: number): string {
  return `${inizio}${Math.min(1, Math.max(0, a)).toFixed(3)})`;
}
