import { cookies } from "next/headers";
import dynamic from "next/dynamic";
import { SESSION_COOKIE } from "@/lib/auth";
import { requirePagina } from "@/lib/page-guard";
import { PageHeader } from "@/components/ui/page-header";
import type { CustomTag, TagSuggestion } from "@/lib/tag";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

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
  let suggestions: TagSuggestion[] = [];

  if (token) {
    const [tagsRes, suggestionsRes] = await Promise.all([
      fetchInitial<{ tags: CustomTag[] }>("/api/tag", token),
      fetchInitial<{ suggestions: TagSuggestion[] }>("/api/tag/suggestions", token),
    ]);
    tags = tagsRes?.tags ?? [];
    suggestions = suggestionsRes?.suggestions ?? [];
  }

  return (
    <div className="space-y-4">
      <PageHeader
        icon="tags"
        title="Analisi e Tag"
        hint="Raggruppa i prodotti come ragioni tu"
      />
      <AnalisiETagClient initialTags={tags} initialSuggestions={suggestions} />
    </div>
  );
}
