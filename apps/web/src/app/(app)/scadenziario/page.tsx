import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { requirePagina } from "@/lib/page-guard";
import { PageHeader } from "@/components/ui/page-header";
import { ScadenziarioClient } from "./scadenziario-client";
import type { Documento } from "@/lib/scadenziario";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { esitoLista } from "@/lib/esito-caricamento";

// `null` = non sono riuscito a chiedere (non-2xx, timeout, rete), che NON e'
// "zero scadenze": vedi lib/esito-caricamento.ts.
async function fetchDocumenti(token: string): Promise<{ documenti: Documento[] } | null> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    const res = await fetch(`${WORKER_URL}/api/scadenziario`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return (await res.json()) as { documenti: Documento[] };
  } catch {
    return null;
  }
}

async function triggerNotifica(token: string): Promise<void> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  try {
    await fetch(`${WORKER_URL}/api/scadenziario/notifica`, {
      method: "POST",
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
  } catch {
    // best-effort
  }
}

export default async function ScadenziarioPage() {
  await requirePagina("scadenziario");
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value ?? "";

  // Senza token la chiamata parte comunque e il worker risponde 401 -> `null`,
  // come prima di questo fix: l'assenza di sessione la gestisce il layout, e
  // non e' il caso che questa pagina deve distinguere.
  const [risposta] = await Promise.all([
    fetchDocumenti(token),
    token ? triggerNotifica(token) : Promise.resolve(),
  ]);
  const esito = esitoLista<Documento>(risposta, "documenti");

  return (
    <div className="space-y-5">
      <PageHeader
        icon="calendar"
        title="Gestione Fatture"
        hint="Scadenze e pagamenti sotto controllo"
      />
      <ScadenziarioClient
        initialDocumenti={esito.righe}
        caricamentoFallito={esito.stato === "non_disponibile"}
      />
    </div>
  );
}
