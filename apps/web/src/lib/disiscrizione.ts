// Parametri della disiscrizione dall'email settimanale (u = id utente, t =
// token firmato dal worker). Arrivano dalla query (List-Unsubscribe e pagina)
// o dal corpo JSON; la query vince, perche' e' quella che il worker ha firmato
// dentro il link. Logica pura, provata con node in
// tests/test_disiscrizione_frontend.py.
export type ParametriDisiscrizione = { u: string; t: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TOKEN = /^[0-9a-f]{64}$/i;

function pulisci(v: unknown): string {
  return typeof v === "string" ? v.trim() : "";
}

export function parametriDisiscrizione(
  query: { get(nome: string): string | null } | null,
  corpo: unknown,
): ParametriDisiscrizione | null {
  const daCorpo = (corpo && typeof corpo === "object" ? corpo : {}) as Record<string, unknown>;
  const u = pulisci(query?.get("u")) || pulisci(daCorpo.u);
  const t = pulisci(query?.get("t")) || pulisci(daCorpo.t);
  if (!UUID.test(u) || !TOKEN.test(t)) return null;
  return { u, t };
}
