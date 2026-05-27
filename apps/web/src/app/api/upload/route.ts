import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";

const WORKER_URL = process.env.WORKER_URL ?? "https://worker-production-a552.up.railway.app";
const WORKER_SECRET_KEY = process.env.WORKER_SECRET_KEY ?? "";

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Non autenticato" }, { status: 401 });
  }

  let formData: FormData;
  try {
    formData = await req.formData();
  } catch {
    return NextResponse.json({ error: "Body non valido" }, { status: 400 });
  }

  const file = formData.get("file");
  if (!file || !(file instanceof File)) {
    return NextResponse.json({ error: "File mancante" }, { status: 400 });
  }

  // Inolta file al worker
  const workerForm = new FormData();
  workerForm.append("file", file);

  try {
    const res = await fetch(`${WORKER_URL}/api/upload/invoice`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(WORKER_SECRET_KEY ? { "X-Worker-Key": WORKER_SECRET_KEY } : {}),
      },
      body: workerForm,
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      return NextResponse.json(
        { error: data.detail ?? data.error ?? "Errore worker" },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err) {
    console.error("[upload] worker fetch error:", err);
    return NextResponse.json({ error: "Servizio non raggiungibile" }, { status: 503 });
  }
}
