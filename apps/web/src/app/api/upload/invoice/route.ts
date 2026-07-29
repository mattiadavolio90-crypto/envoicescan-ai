import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";
import { WORKER_URL, WORKER_SECRET_KEY } from "@/lib/worker-config";

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const formData = await req.formData();

  const MAX_BYTES = 200 * 1024 * 1024; // allineato a MAX_UPLOAD_TOTAL_MB (config/constants.py)
  let totalBytes = 0;
  for (const value of formData.values()) {
    if (value instanceof Blob) totalBytes += value.size;
  }
  if (totalBytes > MAX_BYTES) {
    return NextResponse.json(
      { error: `File troppo grande (max ${MAX_BYTES / 1024 / 1024} MB)` },
      { status: 413 },
    );
  }

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (WORKER_SECRET_KEY) headers["X-Worker-Key"] = WORKER_SECRET_KEY;

  try {
    const res = await fetch(`${WORKER_URL}/api/upload/invoice`, {
      method: "POST",
      headers,
      body: formData,
      signal: AbortSignal.timeout(30000),
    });
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json({ error: "Worker non raggiungibile" }, { status: 502 });
  }
}
