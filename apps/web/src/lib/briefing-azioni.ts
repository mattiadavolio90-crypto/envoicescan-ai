// Quale riquadro sta sotto la voce dell'assistente, nella Home desktop e in /m.
//
// "vuoto" (25/09/2026): niente card da fare, niente dati mancanti, ma il backend
// non dice tutto_ok — un arretrato aperto, un food cost sopra la soglia, un
// incasso sceso. La narrativa sopra lo dice gia'; prima qui restava il titolo
// «Da fare oggi (0)» sopra una lista vuota.
export type StatoAzioni = "verde" | "dati_mancanti" | "lista" | "vuoto";

export function statoAzioni(
  tuttoOk: boolean,
  nVisibili: number,
  nDatiMancanti: number,
): StatoAzioni {
  if (nVisibili > 0) return "lista";
  if (tuttoOk) return "verde";
  if (nDatiMancanti > 0) return "dati_mancanti";
  return "vuoto";
}
