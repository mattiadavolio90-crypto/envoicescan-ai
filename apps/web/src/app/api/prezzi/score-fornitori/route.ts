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
  const data_da = searchParams.get("data_da");
  const data_a = searchParams.get("data_a");
  const soglia = searchParams.get("soglia") ?? "5";
  if (!data_da || !data_a)
    return NextResponse.json({ error: "Missing params" }, { status: 400 });

  try {
    const qs = new URLSearchParams({ data_da, data_a, soglia });
    const res = await fetch(`${WORKER_URL}/api/prezzi/score-fornitori?${qs}`, {
      headers: workerHeaders(token),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
