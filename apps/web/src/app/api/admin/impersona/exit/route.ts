import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { IMPERSONATE_COOKIE, IMPERSONATE_BACKUP_COOKIE } from "../../_worker";

export const runtime = "nodejs";

export async function POST() {
  const store = await cookies();
  const backupToken = store.get(IMPERSONATE_BACKUP_COOKIE)?.value;

  if (backupToken) {
    const cookieOpts = { httpOnly: true, path: "/", sameSite: "lax" as const, secure: process.env.NODE_ENV === "production", maxAge: 60 * 60 * 24 * 30 };
    store.set(SESSION_COOKIE, backupToken, cookieOpts);
  }

  store.delete(IMPERSONATE_BACKUP_COOKIE);
  store.delete(IMPERSONATE_COOKIE);

  return NextResponse.json({ ok: true });
}
