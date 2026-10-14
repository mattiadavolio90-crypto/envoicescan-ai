/**
 * Quali righe d'acquisto aprono l'anteprima della fattura.
 *
 * Una quota ripartita dal gruppo (`ripartita_su_gruppo`, id negativo sintetico)
 * porta il `file_origine` della fattura della sede capofila: l'anteprima la
 * cerca sulla sede di sessione e si aprirebbe vuota. Senza `file_origine` non
 * c'e' niente da aprire.
 */
export function rigaApribile(r: { id: number; file_origine?: string | null; ripartita_su_gruppo?: boolean }): boolean {
  return Boolean(r.file_origine) && r.ripartita_su_gruppo !== true && r.id >= 0;
}
