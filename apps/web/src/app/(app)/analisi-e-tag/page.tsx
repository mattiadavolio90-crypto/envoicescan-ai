import { cookies } from "next/headers";
import dynamic from "next/dynamic";
import { SESSION_COOKIE } from "@/lib/auth";
import { requirePagina } from "@/lib/page-guard";
import { PageHeader } from "@/components/ui/page-header";
import type { CartellaTag, CustomTag, TagSuggestion } from "@/lib/tag";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";
import { esitoLista } from "@/lib/esito-caricamento";

// dynamic(): il client importa recharts, usata solo per i grafici di questa
// pagina, cosi' il chunk resta separato dal bundle condiviso.
// Niente ssr:false: in un Server Component non e' consentito da Next.
const AnalisiETagClient = dynamic(() => import("./analisi-e-tag-client").then((m) => m.AnalisiETagClient), {
  loading: () => <div className="h-40 animate-pulse rounded-lg bg-muted/40" />,
});

async function fetchInitial<T>(path: string, token: string): Promise<T | null> {
  try {
    const h: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
    const res = await fetch(`${WORKER_URL}${path}`, {
      headers: h,
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}

export default async function AnalisiETagPage() {
  await requirePagina("analisi_e_tag");
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;

  let tags: CustomTag[] = [];
  let cartelle: CartellaTag[] = [];
  let suggestions: TagSuggestion[] = [];
  // Senza token non c'e' stata nessuna chiamata: non e' un guasto del worker.
  let caricamentoFallito = false;

  if (token) {
    const [tagsRes, suggestionsRes] = await Promise.all([
      fetchInitial<{ tags: CustomTag[]; cartelle?: CartellaTag[] }>("/api/tag", token),
      fetchInitial<{ suggestions: TagSuggestion[] }>("/api/tag/suggestions", token),
    ]);
    const esitoTag = esitoLista<CustomTag>(tagsRes, "tags");
    tags = esitoTag.righe;
    caricamentoFallito = esitoTag.stato === "non_disponibile";
    // Stessa risposta dei tag: se quella e' fallita il guasto e' gia' segnalato.
    cartelle = esitoLista<CartellaTag>(tagsRes, "cartelle").righe;
    suggestions = esitoLista<TagSuggestion>(suggestionsRes, "suggestions").righe;
  }

  return (
    <div className="space-y-4">
      <PageHeader
        icon="tags"
        title="Analisi e Tag"
        hint="Raggruppa i prodotti come ragioni tu"
      />
      <AnalisiETagClient
        initialTags={tags}
        initialCartelle={cartelle}
        initialSuggestions={suggestions}
        caricamentoFallito={caricamentoFallito}
      />
    </div>
  );
}
