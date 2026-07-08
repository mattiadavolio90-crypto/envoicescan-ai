import { ImageResponse } from "next/og";

// Anteprima social DEDICATA per /demo (link condiviso su WhatsApp/mail): senza
// questo file la route erediterebbe l'og-image generica della landing, che
// parla d'altro. Generata a request-time con ImageResponse (Satori): niente
// oklch() supportato, colori in hex equivalenti al tema (--primary sky, sfondo
// notte "#05070A" della landing scrollytelling).

export const alt = "Prova ONEFLUX in un minuto — demo interattiva con dati di esempio";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const SKY = "#38bdf8";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#05070A",
          backgroundImage:
            "radial-gradient(circle at 25% 20%, rgba(56,189,248,0.20), transparent 55%), radial-gradient(circle at 80% 85%, rgba(56,189,248,0.12), transparent 50%)",
        }}
      >
        {/* Logo mark: stesso doppio anello + X a flusso di components/brand/logo.tsx */}
        <svg width="120" height="120" viewBox="0 0 100 100" fill="none">
          <circle cx="50" cy="50" r="42" stroke={SKY} strokeWidth={6} fill="none" />
          <circle cx="50" cy="50" r="31" stroke={SKY} strokeWidth={2.5} fill="none" />
          <path d="M36 36 C48 44 48 56 64 64" stroke={SKY} strokeWidth={7} strokeLinecap="round" />
          <path d="M64 36 C52 44 52 56 36 64" stroke={SKY} strokeWidth={7} strokeLinecap="round" />
        </svg>

        <div
          style={{
            marginTop: 28,
            fontSize: 30,
            fontWeight: 700,
            letterSpacing: 4,
            color: SKY,
            textTransform: "uppercase",
          }}
        >
          Demo interattiva
        </div>

        <div
          style={{
            marginTop: 18,
            fontSize: 60,
            fontWeight: 800,
            color: "#ffffff",
            textAlign: "center",
            lineHeight: 1.15,
            maxWidth: 980,
            display: "flex",
          }}
        >
          Prova ONEFLUX in 1 minuto
        </div>

        <div
          style={{
            marginTop: 20,
            fontSize: 28,
            color: "rgba(255,255,255,0.72)",
            textAlign: "center",
            maxWidth: 860,
            display: "flex",
          }}
        >
          Fatture lette da sole, avvisi sui rincari, il margine reale — con dati di esempio
        </div>
      </div>
    ),
    { ...size },
  );
}
