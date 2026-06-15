import { NextRequest, NextResponse } from "next/server";
import { loginWithCredentials, SESSION_COOKIE } from "@/lib/auth";
import { IMPERSONATE_COOKIE, IMPERSONATE_BACKUP_COOKIE } from "@/app/api/admin/_worker";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  let payload: { email?: string; password?: string };
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: "Body non valido" }, { status: 400 });
  }

  const email = (payload.email ?? "").trim().toLowerCase();
  const password = payload.password ?? "";

  if (!email || !password) {
    return NextResponse.json({ error: "Email e password sono obbligatori" }, { status: 400 });
  }

  const result = await loginWithCredentials(email, password);

  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  const res = NextResponse.json({ user: result.user });
  res.cookies.set(SESSION_COOKIE, result.token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  // Un login pulito non deve mai ereditare uno stato di impersonazione
  // residuo: azzeriamo i cookie per recuperare anche le sessioni rimaste
  // bloccate prima di questa fix.
  const clear = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge: 0,
  };
  res.cookies.set(IMPERSONATE_COOKIE, "", clear);
  res.cookies.set(IMPERSONATE_BACKUP_COOKIE, "", clear);

  return res;
}
