"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { AscoltaButton, type StatoAscolta } from "@/components/ascolta-button";
import { AvatarFlusso } from "@/components/home/avatar-flusso";
import { BenvenutoAssistente } from "@/components/home/benvenuto-assistente";
import { useAssistenteOpzionale } from "@/components/home/assistente-provider";
import { ConversazioneAltezzaFissa } from "@/components/home/pannello-conversazione";
import {
  TESTO_MODO,
  carattereNarrativa,
  fraseAl,
  frasi,
  frazioneLetta,
  modoAvatar,
} from "@/lib/avatar-flusso";
import { cn } from "@/lib/utils";

// Il riquadro dell'assistente, uguale nella Home del punto vendita e in quella
// della catena (Mattia, 28/9: una Home sola, cambiano solo i dati). Fino ad
// allora erano due copie divergenti: misure, titolo e typewriter diversi.
//
// Fase L (15/10/2026): da computer il flusso dell'assistente sta dentro il riquadro,
// a sinistra, e il riquadro ha altezza fissa (la conversazione scorre dentro); sotto
// lo schermo largo una fascia in cima. Il flusso ascolta quando scrivi nella chat,
// pensa mentre aspetti la risposta, parla con «Ascolta» (e la frase letta si evidenzia).

// Effetto typewriter (spegnibile in 1 riga): solo al primo load del giorno,
// max ~600ms. Dietro flag perche' deve restare sobrio e veloce.
const TYPEWRITER_ENABLED = true;

function useTypewriter(text: string, enabled: boolean) {
  const [shown, setShown] = useState(enabled ? "" : text);
  useEffect(() => {
    if (!enabled) {
      setShown(text);
      return;
    }
    let i = 0;
    setShown("");
    // durata totale ~ costante indipendente dalla lunghezza
    const step = Math.max(8, Math.min(28, Math.round(600 / Math.max(text.length, 1))));
    const id = setInterval(() => {
      i += 1;
      setShown(text.slice(0, i));
      if (i >= text.length) clearInterval(id);
    }, step);
    return () => clearInterval(id);
  }, [text, enabled]);
  return shown;
}

export function RiquadroAssistente({
  etichetta,
  saluto,
  narrativa,
  testoAscolta,
  chiaveGiorno,
  children,
}: {
  etichetta: string;
  saluto: string;
  narrativa: string;
  testoAscolta: string;
  /** Chiave del giorno per animare la narrativa solo la prima volta. Assente =
   * niente animazione. */
  chiaveGiorno?: string | null;
  children?: React.ReactNode;
}) {
  const [animate, setAnimate] = useState(false);
  const decided = useRef(false);
  useEffect(() => {
    if (decided.current) return;
    decided.current = true;
    if (!TYPEWRITER_ENABLED || !chiaveGiorno) return;
    try {
      const key = `oneflux:briefing-seen:${chiaveGiorno}`;
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, "1");
        setAnimate(true);
      }
    } catch {
      /* sessionStorage non disponibile: nessuna animazione */
    }
  }, [chiaveGiorno]);

  const mostrata = useTypewriter(narrativa, animate);

  // Opzionale: il riquadro gira anche nel Demo Tour pubblico, senza AssistenteProvider.
  const inCorso = useAssistenteOpzionale()?.inCorso ?? null;
  const [ascolta, setAscolta] = useState(false);
  const [parla, setParla] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const inizioRef = useRef(0);
  const modo = modoAvatar({ parla, pensa: inCorso !== null, ascolta });

  const suStato = useCallback((stato: StatoAscolta, audio: HTMLAudioElement | null) => {
    if (stato === "playing") {
      audioRef.current = audio;
      inizioRef.current = performance.now();
      setParla(true);
    } else if (stato === "idle") {
      audioRef.current = null;
      setParla(false);
    }
  }, []);

  // A che frase e' arrivata la lettura: dall'audio, se ne conosce la durata;
  // altrimenti (voce di sistema) stimata dal tempo trascorso.
  const elenco = useMemo(() => frasi(narrativa), [narrativa]);
  const [letta, setLetta] = useState(-1);
  useEffect(() => {
    if (!parla) {
      setLetta(-1);
      return;
    }
    let id = 0;
    const segui = () => {
      id = requestAnimationFrame(segui);
      const frazione = frazioneLetta(audioRef.current, (performance.now() - inizioRef.current) / 1000, testoAscolta.length);
      const n = fraseAl(elenco, carattereNarrativa(testoAscolta, narrativa, frazione));
      setLetta((prima) => (prima === n ? prima : n));
    };
    id = requestAnimationFrame(segui);
    return () => cancelAnimationFrame(id);
  }, [parla, elenco, testoAscolta, narrativa]);

  const scritta = mostrata.length >= narrativa.length;

  // Da computer la narrativa puo' scorrere dentro il riquadro: la frase letta va tenuta in vista.
  const narrativaRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    const p = narrativaRef.current;
    const frase = letta >= 0 ? (p?.children[letta] as HTMLElement | undefined) : undefined;
    if (!p || !frase || p.scrollHeight <= p.clientHeight) return;
    const sopra = frase.offsetTop < p.scrollTop;
    const sotto = frase.offsetTop + frase.offsetHeight > p.scrollTop + p.clientHeight;
    if (sopra || sotto) p.scrollTo({ top: Math.max(0, frase.offsetTop - 8), behavior: "smooth" });
  }, [letta]);

  return (
    <>
      <BenvenutoAssistente saluto={saluto} />
      {/* Una card sola (Mattia, 15/10): il flusso a sinistra fa parte del riquadro. Da computer
          l'altezza e' fissa e la conversazione scorre dentro, invece di allungare la pagina. */}
      <div className={cn("relative isolate overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-primary/[0.04] to-background lg:grid lg:min-h-[480px] lg:grid-cols-[minmax(240px,30%)_minmax(0,1fr)]", children && "lg:h-[min(640px,calc(100vh-7rem))]")}>
        {/* Gli aloni stanno SOTTO il contenuto (-z-10 dentro isolate): sopra sbiadivano
            «Ascolta» e la fine delle prime righe. */}
        <div className="pointer-events-none absolute -right-16 -top-16 -z-10 size-56 rounded-full bg-accent blur-3xl" />
        <div className="pointer-events-none absolute -bottom-20 left-1/3 -z-10 size-52 rounded-full bg-primary/10 blur-3xl" />
        <div className="relative hidden lg:block">
          <AvatarFlusso modo={modo} variante="colonna" className="absolute inset-0" />
          <div className="absolute inset-x-0 bottom-0 flex flex-col items-center gap-1 pb-4 text-center">
            <span className="text-sm font-semibold">{etichetta}</span>
            <span className="flex items-center gap-2 text-xs text-muted-foreground" aria-live="polite">
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  modo === "ascolta" ? "bg-positivo" : "bg-primary",
                  (modo === "pensa" || modo === "parla") && "animate-pulse",
                )}
              />
              {TESTO_MODO[modo]}
            </span>
          </div>
        </div>
        <div className="flex min-h-0 min-w-0 flex-col p-5 sm:p-6 lg:pl-2">
          <div className="relative -mx-5 -mt-5 mb-2 h-28 sm:-mx-6 sm:-mt-6 lg:hidden">
            <AvatarFlusso modo={modo} variante="fascia" className="absolute inset-0" />
          </div>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs font-medium text-primary/80 lg:hidden">
              <Sparkles className="size-4" />
              <span>{etichetta}</span>
            </div>
            <AscoltaButton testo={testoAscolta} onStato={suStato} className="ml-auto" />
          </div>
          <h1 className="mt-2 text-xl font-bold tracking-tight sm:text-2xl">{saluto}</h1>
          <p
            ref={narrativaRef}
            className={cn("relative mt-3 max-w-none shrink-0 whitespace-pre-line text-base leading-relaxed text-foreground/90", children && "lg:max-h-[45%] lg:overflow-y-auto")}
          >
            {parla && scritta
              ? elenco.map((f, i) => (
                  <span
                    key={i}
                    className={cn("rounded transition-colors duration-300", i === letta && "bg-primary/15 text-foreground")}
                  >
                    {f.testo}
                  </span>
                ))
              : mostrata}
            {animate && mostrata.length < narrativa.length && (
              <span className="ml-0.5 inline-block h-5 w-0.5 animate-pulse bg-primary align-middle" />
            )}
          </p>
          <ConversazioneAltezzaFissa.Provider value={true}>
            <div
              className="flex min-h-0 flex-1 flex-col"
              onFocusCapture={(e) => {
                if (e.target instanceof HTMLTextAreaElement || e.target instanceof HTMLInputElement) setAscolta(true);
              }}
              onBlurCapture={() => setAscolta(false)}
            >
              {children}
            </div>
          </ConversazioneAltezzaFissa.Provider>
        </div>
      </div>
    </>
  );
}
