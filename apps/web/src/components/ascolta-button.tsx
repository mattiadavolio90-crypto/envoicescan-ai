"use client";

import { useEffect, useState } from "react";
import { Volume2, Square } from "lucide-react";
import { cn } from "@/lib/utils";

// Pulsante "ascolta": legge il testo con la Web Speech API del browser
// (speechSynthesis). Gratis, offline, voce di sistema italiana se disponibile.
// Best-effort: se il browser non la supporta, il pulsante non compare.
export function AscoltaButton({ testo, className }: { testo: string; className?: string }) {
  const [supportato, setSupportato] = useState(false);
  const [parla, setParla] = useState(false);

  useEffect(() => {
    setSupportato(typeof window !== "undefined" && "speechSynthesis" in window);
    // Alla smontatura ferma sempre la lettura (cambio pagina mentre parla).
    return () => {
      try {
        window.speechSynthesis?.cancel();
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
    const itVoice = synth.getVoices().find((v) => v.lang?.startsWith("it"));
    if (itVoice) u.voice = itVoice;
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
