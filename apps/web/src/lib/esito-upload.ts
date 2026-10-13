/**
 * Esito di UN file nella finestra «Carica fatture», dalla risposta del worker.
 *
 * Scartata (arancio) e non caricata (rossa) dicono al cliente due cose opposte:
 * «non devi fare niente» contro «c'e' un problema». Un doppione e' sempre
 * scartato. `duplicate_document` (stesso fornitore+numero+data sotto un altro
 * nome, es. `X (1).xml`) usciva in rosso col codice grezzo, contato «non
 * caricata», ritentato a ogni click e con l'avviso di chiusura: il cliente
 * pensava a un guasto. Il worker ora lo manda come `ALREADY_LOADED:`; il ramo
 * qui resta per le risposte di un worker non ancora ridispiegato.
 */

export type StatoUpload = "success" | "error" | "skipped" | "queued";

export type MotivoScarto = "ALREADY_LOADED" | "PIVA_NESSUNA_SEDE" | "GIA_IN_CODA";

export type EsitoUpload = {
  status: StatoUpload;
  error?: string;
  skip_motivo?: MotivoScarto;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function classificaEsitoUpload(ok: boolean, httpStatus: number, data: any): EsitoUpload {
  const d = data ?? {};
  if (!ok) {
    return { status: "error", error: String(d.detail ?? d.error ?? `HTTP ${httpStatus}`) };
  }
  const errStr = String(d.error ?? "");

  // Multi-sede AMBIGUO: la P.IVA e' del cliente ma l'indirizzo non distingue la
  // sede. Il worker la mette in coda 'da_assegnare' con success=true.
  // queue_created=false = era gia' in coda (stesso hash): un doppione, non una
  // nuova. Si controlla PRIMA di success, che sul ramo ambiguo e' sempre true.
  const ambiguo = d.success === true && d.routing_status === "ambiguo";
  if (ambiguo && d.queue_created !== false) return { status: "queued" };
  if (ambiguo) return { status: "skipped", skip_motivo: "GIA_IN_CODA" };

  if (errStr.startsWith("ALREADY_LOADED:") || errStr === "duplicate_document") {
    return { status: "skipped", skip_motivo: "ALREADY_LOADED" };
  }
  if (errStr === "PIVA_NESSUNA_SEDE") return { status: "skipped", skip_motivo: "PIVA_NESSUNA_SEDE" };

  if (d.success) return { status: "success" };
  return { status: "error", error: d.error ?? undefined };
}
