// Chi puo' usare /api/tts. La route girava con il solo controllo che il cookie di
// sessione ESISTESSE: un valore inventato bastava a usarla come proxy verso il
// TTS di Google (audit di ottobre 2026, K26). Ora la sessione si verifica sul
// worker come per ogni altra pagina; un worker irraggiungibile non e' un logout.
export type EsitoSessione = { status: "ok" | "invalid" | "unavailable" };

export function rifiutoTts(esito: EsitoSessione): { status: number; error: string } | null {
  if (esito.status === "ok") return null;
  if (esito.status === "invalid") return { status: 401, error: "Non autenticato" };
  return { status: 503, error: "Servizio temporaneamente non raggiungibile" };
}
