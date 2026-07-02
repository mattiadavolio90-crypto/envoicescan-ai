import { cache } from "react";
import { cookies } from "next/headers";

export const SESSION_COOKIE = "oneflux_session";

// Fonte unica per URL/secret/timeout del worker (auth.ts e' il modulo base che
// non dipende da altri lib; worker-config.ts re-importa da qui per evitare cicli).
export const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
export const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

// Timeout su tutte le chiamate worker: evita che il render appeso a un cold-start
// di Railway blocchi ogni pagina autenticata (getCurrentUser gira nel layout).
// Override via env per lo sviluppo locale (worker a freddo + init Supabase può
// avvicinarsi al limite); in produzione resta il default 12s se la var non è settata.
// Alzato da 8s a 12s: /api/auth/me fa una cascata di query Supabase e, sotto
// contesa sull'unica istanza Railway, un singolo colpo di lentezza superava gli 8s
// e mandava OGNI pagina alla schermata "Servizio non raggiungibile".
export const WORKER_TIMEOUT_MS = Number(process.env.WORKER_TIMEOUT_MS) || 12000;

export type SessionUser = {
  id: string;
  email: string;
  nome_ristorante: string | null;
  // Sede attiva (clienti multi-sede). Per i mono-sede coincide con nome_ristorante.
  // Il worker la valorizza sempre; resta opzionale per compatibilita' coi vecchi token.
  sede_attiva_nome?: string | null;
  sede_attiva_id?: string | null;
  // Numero di sedi attive dell'account: ≥2 = cliente catena (landing su /catena).
  // Opzionale per compatibilità coi vecchi token (default mono-sede).
  num_sedi?: number;
  pagine_abilitate: string[] | null;
  is_admin: boolean;
  tema?: "dark" | "light";
};

function workerHeaders(extra: HeadersInit = {}): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json", ...(extra as Record<string, string>) };
  if (WORKER_SECRET_KEY) {
    h["X-Worker-Key"] = WORKER_SECRET_KEY;
  }
  return h;
}

export async function loginWithCredentials(email: string, password: string): Promise<
  { ok: true; token: string; user: SessionUser } | { ok: false; status: number; error: string }
> {
  try {
    const res = await fetch(`${WORKER_URL}/api/auth/login`, {
      method: "POST",
      headers: workerHeaders(),
      body: JSON.stringify({ email, password }),
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return {
        ok: false,
        status: res.status,
        error: data.detail || data.message || "Credenziali non valide",
      };
    }

    const data = await res.json();
    return { ok: true, token: data.token, user: data.user as SessionUser };
  } catch (err) {
    console.error("[auth.login] worker fetch error:", err);
    return { ok: false, status: 503, error: "Servizio temporaneamente non raggiungibile" };
  }
}

// Esito discriminato della verifica sessione, cosi' il chiamante distingue
// "token scaduto" (-> logout + login) da "worker lento/giu'" (-> riprova, NON
// sloggare). Prima entrambi tornavano null e il layout buttava fuori l'utente
// anche per un semplice cold-start di Railway.
export type SessionResult =
  | { status: "ok"; user: SessionUser }
  | { status: "invalid" } // 401/403: sessione non valida -> vai al login
  | { status: "unavailable" }; // timeout / 5xx / rete: worker non raggiungibile

export async function verifySession(token: string): Promise<SessionResult> {
  // Un solo colpo di lentezza sul worker (contesa sull'unica istanza Railway,
  // cold-start) non deve buttare l'utente sulla schermata "non raggiungibile":
  // ritentiamo UNA volta su timeout/5xx/rete. Un 401/403 invece e' definitivo
  // (token davvero non valido) e non va ritentato.
  const attempts = 2;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      const res = await fetch(`${WORKER_URL}/api/auth/me`, {
        method: "GET",
        headers: workerHeaders({ Authorization: `Bearer ${token}` }),
        cache: "no-store",
        signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
      });
      if (res.ok) return { status: "ok", user: (await res.json()) as SessionUser };
      if (res.status === 401 || res.status === 403) return { status: "invalid" };
      // 5xx o altri: il worker c'e' ma e' in difficolta' -> non invalidare la sessione
      console.error(`[auth.me] worker error (tentativo ${attempt}/${attempts}):`, res.status);
    } catch (err) {
      // Timeout o errore di rete: worker non raggiungibile, sessione NON compromessa
      console.error(`[auth.me] worker fetch error (tentativo ${attempt}/${attempts}):`, err);
    }
  }
  return { status: "unavailable" };
}

// Compat: alcune callsite vogliono solo l'utente (o null). Mantiene il vecchio
// comportamento per chi non deve distinguere gli esiti.
export async function fetchSessionUser(token: string): Promise<SessionUser | null> {
  const r = await verifySession(token);
  return r.status === "ok" ? r.user : null;
}

export async function logoutSession(token: string): Promise<void> {
  try {
    await fetch(`${WORKER_URL}/api/auth/logout`, {
      method: "POST",
      headers: workerHeaders({ Authorization: `Bearer ${token}` }),
      cache: "no-store",
    });
  } catch (err) {
    console.error("[auth.logout] worker fetch error:", err);
  }
}

// Avvolto in cache() di React: layout (app), layout admin e le pagine che
// chiamano getCurrentUser nello stesso render colpiscono il worker UNA sola
// volta invece di ripetere /api/auth/me a ogni navigazione (era il collo di
// bottiglia per-pagina). La cache vive solo per la durata della singola request.
export const getCurrentUser = cache(async (): Promise<SessionUser | null> => {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  return fetchSessionUser(token);
});

// Variante con esito discriminato per il layout: deve distinguere "nessun
// cookie / token scaduto" (redirect al login) da "worker non raggiungibile"
// (mostra fallback, NON sloggare). Stessa cache() di getCurrentUser: una sola
// chiamata /api/auth/me per render.
export const getCurrentSession = cache(async (): Promise<SessionResult> => {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return { status: "invalid" };
  return verifySession(token);
});
