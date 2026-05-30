import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { WORKER_URL, getToken, workerHeaders, unauthorized, workerUnreachable, IMPERSONATE_COOKIE, IMPERSONATE_BACKUP_COOKIE } from "../../../_worker";
import { SESSION_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";
type Ctx = { params: Promise<{ id: string }> };

export async function POST(_req: NextRequest, { params }: Ctx) {
  const store = await cookies();
  const adminToken = store.get(SESSION_COOKIE)?.value;
  if (!adminToken) return unauthorized();
  const { id } = await params;
  try {
    const res = await fetch(`${WORKER_URL}/api/admin/impersona/${id}`, {
      method: "POST",
      headers: workerHeaders(adminToken),
      cache: "no-store",
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      const data = await res.json();
      return NextResponse.json(data, { status: res.status });
    }
    const { target_token, target_email, target_nome } = await res.json();

    const cookieOpts = { httpOnly: true, path: "/", sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", maxAge: 60 * 60 * 8 };

    store.set(IMPERSONATE_BACKUP_COOKIE, adminToken, cookieOpts);
    store.set(SESSION_COOKIE, target_token, cookieOpts);
    store.set(IMPERSONATE_COOKIE, target_email, { ...cookieOpts, httpOnly: false });

    return NextResponse.json({ ok: true, target_email, target_nome });
  } catch {
    return workerUnreachable();
  }
}
