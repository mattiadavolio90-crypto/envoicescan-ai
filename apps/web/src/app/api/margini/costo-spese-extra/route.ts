import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const anno = req.nextUrl.searchParams.get("anno") ?? "";
  const mese = req.nextUrl.searchParams.get("mese") ?? "";
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(
      `${WORKER_URL}/api/margini/costo-spese-extra?anno=${anno}&mese=${mese}`,
      { headers: h, cache: "no-store" },
    );
    return NextResponse.json(await res.json(), { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
