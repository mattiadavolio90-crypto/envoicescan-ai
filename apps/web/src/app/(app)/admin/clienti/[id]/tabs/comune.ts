import type { Dispatch, SetStateAction } from "react";
import type { ClienteDettaglio } from "@/lib/admin";

export type TabProps = {
  c: ClienteDettaglio;
  setC: Dispatch<SetStateAction<ClienteDettaglio>>;
};

/** Chiamata alle route /api/admin: il dettaglio dell'errore del worker diventa
 *  il messaggio dell'eccezione, che le tab mostrano nel toast. */
export async function chiamaAdmin(url: string, method: string, body?: object) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Errore");
  return data;
}

export function messaggioErrore(e: unknown): string {
  return e instanceof Error ? e.message : "Errore";
}
