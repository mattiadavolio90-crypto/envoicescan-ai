// Formatter di dominio (valuta/data/percentuale) — FONTE UNICA.
// Prima erano duplicati in margini/periodi.ts, analisi-fatture/periodi.ts e
// scadenziario.ts, con formatEuroCompact divergente (milioni gestiti solo in uno):
// rischio di output incoerente tra pagine. Qui una sola implementazione.

export function formatEuro(v: number, decimali = 0): string {
  return v.toLocaleString("it-IT", {
    style: "currency",
    currency: "EUR",
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
  });
}

export function formatEuroCompact(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return `€ ${(v / 1_000_000).toFixed(1)}M`;
  if (abs >= 1000) return `€ ${(v / 1000).toFixed(1)}k`;
  return formatEuro(v);
}

export function formatPct(v: number, decimali = 1): string {
  if (!isFinite(v)) return "—";
  return `${v.toFixed(decimali)}%`;
}

export function formatData(iso: string | null): string {
  if (!iso) return "—";
  // Tronca a YYYY-MM-DD: con un timestamp ISO ("2026-06-05T10:30:00Z") il giorno
  // diventava "05T10:30:00Z"; con input parziale y poteva essere undefined -> crash.
  const [y, m, d] = iso.slice(0, 10).split("-");
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y.slice(2)}`;
}

// ─── Parsing dell'input numerico italiano ──────────────────────────────────

/**
 * Cosa puo' essere un numero digitato da un utente: cifre, punti, virgole, un
 * segno iniziale. Niente altro.
 *
 * Serve perche' `Number()` accetta notazioni che nessuno scrive in un campo
 * importo e che darebbero un valore silenziosamente sbagliato:
 *   `Number("0x10")` = 16, `Number("1e3")` = 1000, `Number("Infinity")` = Inf.
 * Un "Infinity" che passa la guardia `importo > 0` finirebbe in un POST.
 */
const FORMA_NUMERICA = /^[+-]?[\d.,]+$/;

/**
 * Converte in numero un importo scritto come lo scrive un italiano.
 *
 * Perche' esiste: in tutta l'app il pattern era `Number(t.replace(",", "."))`,
 * che sbaglia su due input reali e frequenti:
 *   - `"1.234,56"` (separatore delle migliaia) -> NaN, perche' resta `1.234.56`
 *   - `"1.234"` inteso come milleduecentotrentaquattro -> `1.234`, cioe'
 *     mille volte meno. Questo e' il caso pericoloso: non da' errore, da' un
 *     numero **plausibile e sbagliato**.
 *
 * Regole, nell'ordine in cui contano:
 *   1. se c'e' una virgola, e' LEI il separatore decimale e i punti sono
 *      migliaia -> si tolgono i punti, la virgola diventa punto;
 *   2. se ci sono solo punti, si guarda l'ULTIMO gruppo: esattamente 3 cifre
 *      (e almeno un punto) = migliaia all'italiana -> si tolgono i punti;
 *      altrimenti e' un decimale all'inglese e si lascia stare;
 *   3. spazi (anche unicode, da copia-incolla di Excel) e simbolo € si tolgono.
 *
 * `"1.234"` -> 1234 e `"1.23"` -> 1.23: la regola delle 3 cifre e' l'unica
 * disambiguazione possibile senza chiedere all'utente, ed e' quella che usa
 * anche Excel in locale italiano.
 *
 * Ritorna NaN su input non numerico: chi chiama decide se e' un errore da
 * mostrare (`importoValido`) o uno zero da assumere (`|| 0`).
 */
export function parseNumeroIt(testo: string | null | undefined): number {
  if (testo == null) return NaN;
  const pulito = testo
    .replace(/[\s\u00a0\u202f\u2007]/g, "")
    .replace(/€/g, "")
    .trim();
  if (!FORMA_NUMERICA.test(pulito)) return NaN;

  if (pulito.includes(",")) {
    return Number(pulito.replace(/\./g, "").replace(",", "."));
  }
  const pezzi = pulito.split(".");
  if (pezzi.length > 1 && pezzi[pezzi.length - 1].length === 3) {
    return Number(pezzi.join(""));
  }
  return Number(pulito);
}

/**
 * Come `parseNumeroIt`, ma con `0` al posto di NaN.
 *
 * Per i campi dove "vuoto" significa davvero zero — i ricavi di un giorno in
 * cui non si e' incassato, una voce di costo non compilata — e dove il vecchio
 * codice scriveva `parseFloat(x.replace(",", ".")) || 0`.
 *
 * `parseFloat` era **peggio** di `Number` su questi input: su `"1.234,56"` non
 * dava NaN ma `1.234`, quindi il `|| 0` non scattava e un fatturato di
 * 1.234,56 € entrava nel MOL come 1,23 €. Nessun errore a schermo.
 */
export function parseNumeroItOZero(testo: string | null | undefined): number {
  const n = parseNumeroIt(testo);
  return Number.isNaN(n) ? 0 : n;
}

/**
 * Come `parseNumeroIt` ma **senza la regola delle migliaia**: il punto e'
 * sempre un separatore decimale.
 *
 * Per i campi dove il separatore delle migliaia non ha senso perche' i valori
 * sono piccoli per natura — ore lavorate, percentuali, prezzi unitari. Li'
 * `"33.333"` e' trentatre virgola trecentotrentatre, non trentatremila:
 * applicare la regola delle 3 cifre darebbe un valore mille volte piu' grande.
 *
 * La virgola resta il separatore decimale italiano, quindi `"8,5"` -> 8.5.
 */
export function parseDecimaleIt(testo: string | null | undefined): number {
  if (testo == null) return NaN;
  const pulito = testo
    .replace(/[\s   ]/g, "")
    .replace(/€/g, "")
    .replace(/%/g, "")
    .trim();
  if (!FORMA_NUMERICA.test(pulito)) return NaN;
  return Number(pulito.replace(",", "."));
}

/** `parseDecimaleIt` con `0` al posto di NaN. */
export function parseDecimaleItOZero(testo: string | null | undefined): number {
  const n = parseDecimaleIt(testo);
  return Number.isNaN(n) ? 0 : n;
}
