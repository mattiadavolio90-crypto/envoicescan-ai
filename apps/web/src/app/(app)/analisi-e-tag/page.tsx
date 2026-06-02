import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { PageHeader } from "@/components/ui/page-header";
import type { CustomTag, TagSuggestion } from "@/lib/tag";
import { AnalisiETagClient } from "./analisi-e-tag-client";

const WORKER_URL =
  process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

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
