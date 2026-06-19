"use client";

import { useEffect, useRef, useState } from "react";
import { Volume2, Square } from "lucide-react";
import { cn } from "@/lib/utils";

// Pulsante "ascolta": legge il testo con la Web Speech API del browser
// (speechSynthesis). Gratis, offline, voce di sistema. La qualità dipende dalle
// voci installate: scegliamo la MIGLIORE voce italiana disponibile (le voci
// "naturali"/cloud di Google e Microsoft suonano molto meglio di quelle locali
// robotiche). Importante: su Chrome getVoices() è ASINCRONO — alla prima chiamata
// può tornare [] e senza una voce italiana il browser legge l'italiano con la voce
// inglese di default (il vero motivo per cui "fa schifo"). Qui aspettiamo l'evento
// voiceschanged e teniamo le voci in stato.
export function AscoltaButton({ testo, className }: { testo: string; className?: string }) {
  const [supportato, setSupportato] = useState(false);
  const [parla, setParla] = useState(false);
  const voceRef = useRef<SpeechSynthesisVoice | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    setSupportato(true);
    const synth = window.speechSynthesis;

    // Sceglie la migliore voce italiana: preferisce le voci "naturali"/online
    // (nomi noti di alta qualità), poi una qualunque it-IT, poi una it-*.
    function scegliVoce() {
      const voci = synth.getVoices().filter((v) => v.lang?.toLowerCase().startsWith("it"));
      if (voci.length === 0) return;
      const preferite = [
        "Google italiano",
        "Microsoft Elsa",
        "Microsoft Cosimo",
        "Alice", // macOS/iOS, voce italiana di buona qualità
        "Federica",
        "Luca",
      ];
      const perNome =
        voci.find((v) => preferite.some((p) => v.name.includes(p))) ||
        voci.find((v) => /natural|online|enhanced|premium/i.test(v.name)) ||
        voci.find((v) => v.lang === "it-IT") ||
        voci[0];
      voceRef.current = perNome ?? null;
    }

    scegliVoce();
    synth.addEventListener("voiceschanged", scegliVoce);
    return () => {
      synth.removeEventListener("voiceschanged", scegliVoce);
      try {
        synth.cancel();
      } catch {
        /* no-op */
      }
    };
  }, []);

  if (!supportato || !testo.trim()) return null;

  function toggle() {
    const synth = window.speechSynthesis;
    if (parla) {
      synth.cancel();
      setParla(false);
      return;
    }
    synth.cancel(); // azzera eventuali code precedenti
    const u = new SpeechSynthesisUtterance(testo);
    u.lang = "it-IT";
    u.rate = 1; // velocità naturale
    u.pitch = 1;
    if (voceRef.current) u.voice = voceRef.current;
    u.onend = () => setParla(false);
    u.onerror = () => setParla(false);
    setParla(true);
    synth.speak(u);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={parla ? "Ferma la lettura" : "Ascolta il briefing"}
      title={parla ? "Ferma" : "Ascolta"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background/60 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent",
        className,
      )}
    >
      {parla ? <Square className="size-3.5" /> : <Volume2 className="size-3.5" />}
      {parla ? "Ferma" : "Ascolta"}
    </button>
  );
}
