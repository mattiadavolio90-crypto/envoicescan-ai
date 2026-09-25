// Quale azione offrire su una fattura in coda che non ha ancora un cliente
// (Admin → Flusso dati, «P.IVA non riconosciute»).
//
// - failed / dead: il download o la lettura sono falliti (saldo Invoicetronic
//   esaurito, 404, timeout). «Riprova» la rimette in coda: il worker riscarica
//   l'XML e decide il cliente come il webhook (services/routing_coda.py).
//   «Assegna a…» qui non servirebbe: aggiorna solo le righe unknown_tenant.
// - unknown_tenant: la P.IVA e' letta ma non e' di nessuna sede. Serve sapere
//   di chi e': «Assegna a…».
export type AzioneOrfana = "riprova" | "assegna" | null;

export function azioneFatturaOrfana(status: string | null | undefined): AzioneOrfana {
  if (status === "failed" || status === "dead") return "riprova";
  if (status === "unknown_tenant") return "assegna";
  return null;
}
