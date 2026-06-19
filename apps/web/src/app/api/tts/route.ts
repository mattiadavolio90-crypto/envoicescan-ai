import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

// TTS gratuito server-side via Google Translate (voce "Google italiano"): non
// dipende dalle voci installate sul dispositivo, quindi suona UGUALE e decente su
// ogni telefono / PWA. Niente API a pagamento. Limite: servizio non ufficiale,
// max ~200 caratteri per richiesta -> spezziamo il testo in chunk e concateniamo
// gli MP3 (i player riproducono i frame in sequenza). Richiede sessione valida per
// non esporre un proxy aperto.
//
// Cache: stesso testo -> stesso audio. Lasciamo cache HTTP lunga (il briefing del
// giorno e' stabile) cosi' un secondo ascolto non ricontatta Google.

export const runtime = "nodejs";

const MAX_CHUNK = 190; // sotto il limite ~200 char del servizio

// Spezza il testo in chunk <= MAX_CHUNK rispettando i confini di frase/parola.
function chunk(testo: string): string[] {
  const pulito = testo.replace(/\s+/g, " ").trim();
  if (pulito.length <= MAX_CHUNK) return [pulito];
  const out: string[] = [];
  // Prima per frase, poi accorpa fino al limite.
  const frasi = pulito.split(/(?<=[.!?;:])\s+/);
  let buf = "";
  for (const f of frasi) {
    if ((buf + " " + f).trim().length <= MAX_CHUNK) {
      buf = (buf + " " + f).trim();
      continue;
    }
    if (buf) out.push(buf);
    if (f.length <= MAX_CHUNK) {
      buf = f;
    } else {
      // Frase troppo lunga: spezza per parole.
      let w = "";
      for (const p of f.split(" ")) {
        if ((w + " " + p).trim().length <= MAX_CHUNK) {
          w = (w + " " + p).trim();
        } else {
          if (w) out.push(w);
          w = p;
        }
      }
      buf = w;
    }
  }
  if (buf) out.push(buf);
  return out;
}

export async function GET(request: Request) {
  const cookieStore = await cookies();
  const token = cookieStore.get(SESSION_COOKIE)?.value;
  if (!token) return NextResponse.json({ error: "Non autenticato" }, { status: 401 });

  const q = new URL(request.url).searchParams.get("q")?.trim();
  if (!q) return NextResponse.json({ error: "Testo mancante" }, { status: 400 });
  // Cap di sicurezza sulla lunghezza totale (un briefing e' breve).
  const testo = q.slice(0, 1200);

  try {
    const parti = chunk(testo);
    const buffers: Uint8Array[] = [];
    for (const parte of parti) {
      const url =
        "https://translate.google.com/translate_tts?ie=UTF-8&tl=it&client=tw-ob&q=" +
        encodeURIComponent(parte);
      const res = await fetch(url, {
        headers: {
          // Senza un User-Agent "browser" il servizio risponde 403.
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
          Referer: "https://translate.google.com/",
        },
        cache: "no-store",
      });
      if (!res.ok) {
        return NextResponse.json({ error: "TTS non disponibile" }, { status: 502 });
      }
      buffers.push(new Uint8Array(await res.arrayBuffer()));
    }

    // Concatena gli MP3 (i frame si susseguono: i player li leggono in sequenza).
    const totale = buffers.reduce((n, b) => n + b.length, 0);
    const audio = new Uint8Array(totale);
    let off = 0;
    for (const b of buffers) {
      audio.set(b, off);
      off += b.length;
    }

    return new NextResponse(audio, {
      headers: {
        "Content-Type": "audio/mpeg",
        // Il briefing del giorno e' stabile: cache lunga lato browser/CDN.
        "Cache-Control": "private, max-age=86400",
      },
    });
  } catch {
    return NextResponse.json({ error: "Errore TTS" }, { status: 500 });
  }
}
