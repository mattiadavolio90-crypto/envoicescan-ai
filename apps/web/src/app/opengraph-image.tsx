// Anteprima social 1200×630 generata staticamente da Next (ImageResponse). È ciò
// che appare quando un link a oneflux.it viene condiviso (WhatsApp, LinkedIn, X).
// Branding reale: nero profondo #05070A, blu OneFlux #29B6F6, mark a doppio anello
// + X di flusso (gli stessi valori del Logo SVG dell'app, riprodotti inline perché
// ImageResponse non può importare componenti "use client" né usare currentColor).
import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "ONEFLUX — Il braccio destro del tuo ristorante";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const BLU = "#29B6F6";

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
          background:
            "radial-gradient(circle at 50% 38%, #0A1622 0%, #05070A 70%)",
          color: "#E6F2F8",
          fontFamily: "sans-serif",
          padding: "0 90px",
          textAlign: "center",
        }}
      >
        {/* Mark: doppio anello (O) + X a tratti curvi (flusso) — stessi valori del Logo */}
        <svg width="120" height="120" viewBox="0 0 100 100" fill="none">
          <circle cx="50" cy="50" r="42" stroke={BLU} strokeWidth="6" />
          <circle cx="50" cy="50" r="31" stroke={BLU} strokeWidth="2.5" />
          <path
            d="M36 36 C48 44 48 56 64 64"
            stroke={BLU}
            strokeWidth="7"
            strokeLinecap="round"
          />
          <path
            d="M64 36 C52 44 52 56 36 64"
            stroke={BLU}
            strokeWidth="7"
            strokeLinecap="round"
          />
        </svg>

        <div
          style={{
            marginTop: 40,
            fontSize: 68,
            fontWeight: 800,
            letterSpacing: "-0.02em",
            lineHeight: 1.08,
          }}
        >
          Il braccio destro del tuo ristorante
        </div>

        <div
          style={{
            marginTop: 26,
            fontSize: 32,
            color: "#9FB3C0",
            maxWidth: 920,
            lineHeight: 1.3,
          }}
        >
          Food cost, marginalità e fatture sotto controllo. Te lo dice prima che
          tu lo chieda.
        </div>

        <div
          style={{
            marginTop: 52,
            fontSize: 26,
            fontWeight: 700,
            color: BLU,
            letterSpacing: "0.04em",
          }}
        >
          oneflux.it · 7 giorni gratis
        </div>
      </div>
    ),
    { ...size },
  );
}
