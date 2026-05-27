import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";

// Espone il session token al browser per upload diretti al worker.
// Necessario per superare il limit body di 4.5MB delle Vercel API routes.
// Il token e gia presente nel cookie HTTP-only; lo restituiamo al client che
// lo usera come Authorization Bearer verso il worker (CORS-protected).
export async function GET() {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  return NextResponse.json({ token, worker_url: WORKER_URL });
}
