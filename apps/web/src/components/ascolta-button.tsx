"use client";

import { useEffect, useRef, useState } from "react";
import { Volume2, Square, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

// Pulsante "ascolta": legge il briefing con una voce gratuita ma DECENTE e UGUALE
// su ogni dispositivo. Strategia:
//  1) TTS server-side via /api/tts (voce "Google italiano"): non dipende dalle voci
//     installate sul telefono -> qualita' costante anche da PWA mobile.
//  2) Fallback: Web Speech del browser (voce di sistema) se l'endpoint non risponde,
//     cosi' il pulsante non resta mai muto.
export function AscoltaButton({ testo, className }: { testo: string; className?: string }) {
  const [stato, setStato] = useState<"idle" | "loading" | "playing">("idle");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // Stop completo (audio HTML + eventuale Web Speech) alla smontatura.
  useEffect(() => {
    return () => {
      audioRef.current?.pause();
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* no-op */
      }
    };
  }, []);

  if (!testo.trim()) return null;

  function stop() {
    audioRef.current?.pause();
    if (audioRef.current) audioRef.current.currentTime = 0;
    try {
      window.speechSynthesis?.cancel();
    } catch {
      /* no-op */
    }
    setStato("idle");
  }

  // Fallback voce di sistema (qualita' variabile, ma meglio di niente).
  function fallbackWebSpeech() {
    try {
      const synth = window.speechSynthesis;
      if (!synth) {
        setStato("idle");
        return;
      }
      synth.cancel();
      const u = new SpeechSynthesisUtterance(testo);
      u.lang = "it-IT";
      u.rate = 1.15; // un filo piu' svelto della voce di sistema di default
      const it = synth.getVoices().find((v) => v.lang?.toLowerCase().startsWith("it"));
      if (it) u.voice = it;
      u.onend = () => setStato("idle");
      u.onerror = () => setStato("idle");
      setStato("playing");
      synth.speak(u);
    } catch {
      setStato("idle");
    }
  }

  async function play() {
    setStato("loading");
    try {
      const audio = new Audio(`/api/tts?q=${encodeURIComponent(testo)}`);
      audioRef.current = audio;
      // La voce Google Translate legge lenta: acceleriamo del 25%. preservesPitch
      // mantiene il tono naturale (niente effetto "Paperino"). Va impostato anche
      // a 'playing' perche' alcuni browser lo resettano al caricamento.
      audio.preservesPitch = true;
      audio.playbackRate = 1.25;
      audio.onended = () => setStato("idle");
      audio.onerror = () => fallbackWebSpeech();
      audio.onplaying = () => {
        audio.playbackRate = 1.25;
        setStato("playing");
      };
      await audio.play();
    } catch {
      // play() rifiutato o rete KO -> voce di sistema.
      fallbackWebSpeech();
    }
  }

  function toggle() {
    if (stato === "idle") void play();
    else stop();
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={stato === "loading"}
      aria-label={stato !== "idle" ? "Ferma la lettura" : "Ascolta il briefing"}
      title={stato !== "idle" ? "Ferma" : "Ascolta"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background/60 px-3 py-1 text-xs font-medium text-primary transition-colors hover:bg-accent disabled:opacity-60",
        className,
      )}
    >
      {stato === "loading" ? (
        <Loader2 className="size-3.5 animate-spin" />
      ) : stato === "playing" ? (
        <Square className="size-3.5" />
      ) : (
        <Volume2 className="size-3.5" />
      )}
      {stato === "playing" ? "Ferma" : stato === "loading" ? "…" : "Ascolta"}
    </button>
  );
}
