import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

function workerHeaders(token: string): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const prodotto = searchParams.get("prodotto");
  const fornitore = searchParams.get("fornitore") ?? "";
  const data_da = searchParams.get("data_da");
  const data_a = searchParams.get("data_a");
  if (!prodotto)
    return NextResponse.json({ error: "Missing param: prodotto" }, { status: 400 });

  try {
    const qs = new URLSearchParams({ prodotto, fornitore });
    if (data_da) qs.set("data_da", data_da);
    if (data_a) qs.set("data_a", data_a);
    const res = await fetch(`${WORKER_URL}/api/prezzi/storico-prodotto?${qs}`, {
      headers: workerHeaders(token),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
