import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { logoutSession, SESSION_COOKIE } from "@/lib/auth";
import { IMPERSONATE_COOKIE, IMPERSONATE_BACKUP_COOKIE } from "@/app/api/admin/_worker";

export const runtime = "nodejs";

export async function POST() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;

  if (token) {
    await logoutSession(token);
  }

  const res = NextResponse.json({ ok: true });
  const clear = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 0,
  };
  res.cookies.set(SESSION_COOKIE, "", clear);
  // Il logout deve azzerare anche lo stato di impersonazione: altrimenti i
  // cookie sopravvivono al login successivo e il banner "Stai vedendo l'app
  // come ..." resta attivo anche sul proprio account.
  res.cookies.set(IMPERSONATE_COOKIE, "", clear);
  res.cookies.set(IMPERSONATE_BACKUP_COOKIE, "", clear);

  return res;
}
