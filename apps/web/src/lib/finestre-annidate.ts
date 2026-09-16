/**
 * Due finestre che si alternano, senza lasciare stato appeso.
 *
 * In Catena "Margini e coperti" ha un bottone "Categorie" che apre una seconda
 * finestra. Fino al 16/09/2026 la seconda era renderizzata DENTRO il Dialog
 * della prima: due modali impilate, e la X della seconda chiudeva solo quella in
 * cima. Portandola fuori la prima si nasconde mentre la seconda e' aperta — ma
 * il componente resta MONTATO anche a finestre chiuse (`sintesi-catena.tsx:583`
 * lo rende sempre, passando `open` come prop), quindi il flag della seconda
 * sopravvive alla chiusura se nessuno lo azzera.
 *
 * Il difetto che ne nasce e' silenzioso: chiusa la coppia con la seconda ancora
 * segnata come aperta, al rientro `apriPrincipale` resta false e l'utente si
 * ritrova davanti la finestra SECONDARIA, non quella che ha chiesto.
 *
 * Sta in `lib/` e non nel .tsx perche' e' logica di stato, non rendering: qui i
 * test la raggiungono (nel componente no, il progetto non ha runner npm).
 */

export type StatoFinestre = {
  /** La finestra principale e' richiesta dal chiamante. */
  aperta: boolean;
  /** La finestra secondaria e' stata aperta da dentro la principale. */
  secondariaAperta: boolean;
};

/**
 * Se mostrare la finestra PRINCIPALE: aperta, e non coperta dalla secondaria.
 * Una alla volta — e' tutto il punto della correzione.
 */
export function mostraPrincipale(s: StatoFinestre): boolean {
  return s.aperta && !s.secondariaAperta;
}

/**
 * Se mostrare la finestra SECONDARIA.
 *
 * La condizione `aperta` non e' ridondante: e' la guardia contro il flag
 * sopravvissuto. Senza, una secondaria rimasta segnata aperta ricomparirebbe da
 * sola alla riapertura della principale.
 */
export function mostraSecondaria(s: StatoFinestre): boolean {
  return s.aperta && s.secondariaAperta;
}
