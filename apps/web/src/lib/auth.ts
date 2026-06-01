import { cache } from "react";
import { cookies } from "next/headers";

export const SESSION_COOKIE = "oneflux_session";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export type SessionUser = {
  id: string;
  email: string;
  nome_ristorante: string | null;
  pagine_abilitate: string[] | null;
  is_admin: boolean;
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

export async function fetchSessionUser(token: string): Promise<SessionUser | null> {
  try {
    const res = await fetch(`${WORKER_URL}/api/auth/me`, {
      method: "GET",
      headers: workerHeaders({ Authorization: `Bearer ${token}` }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as SessionUser;
  } catch (err) {
    console.error("[auth.me] worker fetch error:", err);
    return null;
  }
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
