type SedeCheck = { id: string; attiva: boolean };

const TENTATIVI = 5;
const ATTESA_MS = 300;

/**
 * Cambia la sede attiva e attende che il worker la veda davvero.
 *
 * Il worker gira su più processi (WORKER_WEB_CONCURRENCY): l'invalidazione delle cache
 * lato server tocca solo il processo che ha servito la POST. Navigare subito significa
 * far atterrare le fetch della pagina successiva su processi che risolvono ancora la
 * sede VECCHIA — testata e dati disallineati, e per i PV di catena le righe ripartite
 * assenti finché non si ricaricava a mano. Confermiamo il cambio rileggendo
 * /api/account/sedi (no-store, sempre fresco dal DB) prima di lasciar navigare.
 *
 * Ritorna true se il cambio è stato confermato entro la finestra di polling. Un false
 * NON è un errore: la POST è andata a buon fine e il DB è aggiornato, è solo la
 * propagazione ai processi worker a essere più lenta del solito — il chiamante può
 * navigare comunque, ma non deve annunciare un successo secco.
 *
 * Solleva solo se la POST stessa fallisce.
 */
export async function cambiaSedeEAttendi(ristoranteId: string): Promise<boolean> {
  const res = await fetch("/api/account/cambia-sede", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ristorante_id: ristoranteId }),
  });
  if (!res.ok) throw new Error("cambio sede fallito");

  for (let tentativo = 0; tentativo < TENTATIVI; tentativo++) {
    await new Promise((r) => setTimeout(r, ATTESA_MS));
    try {
      const check = await fetch("/api/account/sedi", { cache: "no-store" });
      const data = check.ok ? await check.json() : null;
      const attiva = (data?.sedi as SedeCheck[] | undefined)?.find((s) => s.attiva);
      if (attiva?.id === ristoranteId) return true;
    } catch {
      // riprova al prossimo giro
    }
  }
  return false;
}
