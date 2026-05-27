import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

function headers(token: string, json = false): Record<string, string> {
  const h: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (json) h["Content-Type"] = "application/json";
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
  if (!data_da || !data_a)
    return NextResponse.json({ error: "Missing params: data_da, data_a" }, { status: 400 });

  try {
    const qs = new URLSearchParams({ data_da, data_a });
    const res = await fetch(`${WORKER_URL}/api/ricavi/giornalieri?${qs}`, {
      headers: headers(token),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  try {
    const res = await fetch(`${WORKER_URL}/api/ricavi/giornalieri`, {
      method: "POST",
      headers: headers(token, true),
      body: JSON.stringify(body),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}

export async function DELETE(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { searchParams } = new URL(req.url);
  const data = searchParams.get("data");
  if (!data) return NextResponse.json({ error: "Missing param: data" }, { status: 400 });

  try {
    const qs = new URLSearchParams({ data });
    const res = await fetch(`${WORKER_URL}/api/ricavi/giornalieri?${qs}`, {
      method: "DELETE",
      headers: headers(token),
    });
    const respData = await res.json();
    return NextResponse.json(respData, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker unreachable" }, { status: 502 });
  }
}
