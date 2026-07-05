import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SESSION_COOKIE, accettaPrivacy } from "@/lib/auth";

export const runtime = "nodejs";

export async function POST() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ ok: false }, { status: 401 });
  }

  const ok = await accettaPrivacy(token);
  if (!ok) {
    return NextResponse.json({ ok: false }, { status: 502 });
  }
  return NextResponse.json({ ok: true });
}
