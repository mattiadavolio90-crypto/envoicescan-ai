import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY, WORKER_TIMEOUT_MS } from "@/lib/worker-config";

// Proxy generico per gli endpoint tag di catena (/api/gruppo/tag/...). Un solo
// handler per CRUD + associazioni + analisi: inoltra GET/POST/DELETE al worker
// con Bearer + X-Worker-Key. Sola lettura/scrittura tag di gruppo, gated dalla
// UI multi-sede.

function workerHeaders(token: string, json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
  if (WORKER_SECRET_KEY) h["X-Worker-Key"] = WORKER_SECRET_KEY;
  return h;
}

async function proxy(req: NextRequest, path: string[], method: "GET" | "POST" | "DELETE") {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const sub = path.map(encodeURIComponent).join("/");
  const qs = req.nextUrl.search;
  const url = `${WORKER_URL}/api/gruppo/tag/${sub}${qs}`;

  const hasBody = method === "POST";
  let body: string | undefined;
  if (hasBody) {
    body = await req.text();
  }

  try {
    const res = await fetch(url, {
      method,
      headers: workerHeaders(token, hasBody),
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(WORKER_TIMEOUT_MS),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}

type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, { params }: Ctx) {
  return proxy(req, (await params).path, "GET");
}
export async function POST(req: NextRequest, { params }: Ctx) {
  return proxy(req, (await params).path, "POST");
}
export async function DELETE(req: NextRequest, { params }: Ctx) {
  return proxy(req, (await params).path, "DELETE");
}
