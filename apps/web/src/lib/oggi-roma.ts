/**
 * Il giorno di oggi a Roma, come Date locale al fuso del ristoratore.
 *
 * Vercel esegue i Server Component in UTC: `new Date()` dentro una pagina server
 * e' l'istante giusto ma il GIORNO sbagliato fra mezzanotte e le 02:00 italiane.
 * Un preset come "mese in corso", calcolato li', il 1° del mese alle 00:30 mostra
 * il mese PRECEDENTE per intero (misurato il 15/09/2026: alle 00:30 del 1° ottobre
 * la pagina Margini rispondeva 2026-09-01 -> 2026-09-30).
 *
 * Il valore che torna ha anno/mese/giorno di Roma a mezzogiorno locale del
 * processo: serve solo a `getFullYear()/getMonth()/getDate()`, non e' un istante.
 * Mezzogiorno, e non mezzanotte, perche' un `new Date(y, m, d)` a mezzanotte in un
 * fuso a ovest di Roma tornerebbe indietro di un giorno al primo confronto.
 */
export function oggiARoma(adesso: Date = new Date()): Date {
  const parti = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Rome",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(adesso);

  const valore = (tipo: string) => Number(parti.find((p) => p.type === tipo)?.value);
  return new Date(valore("year"), valore("month") - 1, valore("day"), 12, 0, 0, 0);
}
