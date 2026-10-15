"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { DisegnoFlusso } from "@/components/home/disegno-flusso";
import { useAssistenteOpzionale } from "@/components/home/assistente-provider";
import { BASE_FLUSSO, chiaveBenvenuto, giornoDiRoma, mostraBenvenuto, type VarianteAvatar } from "@/lib/avatar-flusso";
import { cn } from "@/lib/utils";

// Il benvenuto dell'assistente (fase L, decisioni di Mattia): una volta al giorno, sulla Home,
// i punti arrivano da ogni parte e formano il flusso, compare il saluto, poi il flusso vola
// al suo posto accanto al briefing. Si salta con un clic o con Esc; niente voce; lo sfondo
// segue il tema. Senza storage del browser non parte: meglio niente che ogni volta.

const DURATA_FORMA = 3; // secondi prima del volo
// Le finestre che chiedono qualcosa (il consenso privacy al primo accesso, ogni Dialog
// dell'app) hanno la precedenza. Non l'avviso cookie: e' un banner, non blocca.
const FINESTRA_APERTA = '[data-slot="dialog-content"], [data-slot="alert-dialog-content"], [role="alertdialog"]';
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

export function BenvenutoAssistente({ saluto, sottotitolo = "Ecco cosa conta oggi." }: { saluto: string; sottotitolo?: string }) {
  const [attivo, setAttivo] = useState(false);
  const [testo, setTesto] = useState(false);
  const [vola, setVola] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const palcoRef = useRef<HTMLDivElement>(null);
  const saltaRef = useRef<() => void>(() => {});
  // Solo nell'app vera, dopo il login: il Demo Tour pubblico usa lo stesso riquadro ma non ha
  // AssistenteProvider. Li' il benvenuto coprirebbe la barra del tour e consumerebbe quello del
  // giorno a un cliente che apre la demo dallo stesso browser (Mattia, 15/10).
  const nellApp = useAssistenteOpzionale() !== null;

  useEffect(() => {
    if (!nellApp) return;
    // Si decide dopo due frame: una finestra che si apre insieme alla pagina (il consenso
    // privacy) monta il suo contenuto un paio di commit dopo. Se c'e', niente benvenuto e
    // niente chiave scritta: ripartira' alla prossima Home.
    let annullato = false;
    let id = requestAnimationFrame(() => {
      id = requestAnimationFrame(() => {
        if (!annullato) decidi();
      });
    });
    return () => {
      annullato = true;
      cancelAnimationFrame(id);
    };
  }, [nellApp]);

  function decidi() {
    if (document.querySelector(FINESTRA_APERTA)) return;
    let giaVisto = true;
    try {
      const chiave = chiaveBenvenuto(giornoDiRoma(new Date()));
      giaVisto = window.localStorage.getItem(chiave) !== null;
      if (!giaVisto) window.localStorage.setItem(chiave, "1");
    } catch {
      giaVisto = true;
    }
    const menoAnimazioni = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (mostraBenvenuto({ gia_visto: giaVisto, meno_animazioni: menoAnimazioni })) setAttivo(true);
  }

  useEffect(() => {
    if (!attivo) return;
    const canvas = canvasRef.current, palco = palcoRef.current;
    if (!canvas || !palco) return;
    let disegno: DisegnoFlusso;
    try {
      disegno = new DisegnoFlusso(canvas, "palco", 23);
    } catch {
      setAttivo(false);
      return;
    }
    disegno.assemble = 0;
    disegno.cresce = 0;
    const t0 = performance.now();
    let ultimo = t0, id = 0, partito = false, chiudi = 0, scritto = false;

    const parti = (durata: number) => {
      if (partito) return;
      partito = true;
      setTesto(true);
      setVola(true);
      // Arriva sul flusso visibile della Home (colonna da computer, fascia sul telefono);
      // se non c'è, il benvenuto sfuma e basta.
      const arrivi = Array.from(document.querySelectorAll<HTMLElement>("[data-avatar-arrivo]"));
      const arrivo = arrivi.find((el) => el.getBoundingClientRect().width > 2);
      const a = palco.getBoundingClientRect();
      if (arrivo) {
        const b = arrivo.getBoundingClientRect();
        const variante = (arrivo.dataset.avatarArrivo as VarianteAvatar) ?? "colonna";
        const sc = b.width / a.width;
        const dy = b.top + b.height * BASE_FLUSSO[variante] - a.top - a.height * BASE_FLUSSO.palco * sc;
        palco.style.transition = `transform ${durata}s cubic-bezier(.22,.8,.18,1), opacity ${durata * 0.4}s ease ${durata * 0.6}s`;
        palco.style.transform = `translate(${b.left - a.left}px, ${dy}px) scale(${sc})`;
      } else {
        palco.style.transition = `opacity ${durata}s ease`;
      }
      palco.style.opacity = "0";
      chiudi = window.setTimeout(() => setAttivo(false), durata * 1000 + 60);
    };
    saltaRef.current = () => {
      disegno.assemble = 1;
      disegno.cresce = 1;
      parti(0.55);
    };

    const ciclo = (ora: number) => {
      id = requestAnimationFrame(ciclo);
      const dt = Math.min(0.05, (ora - ultimo) / 1000);
      ultimo = ora;
      const e = (ora - t0) / 1000;
      // Una finestra aperta a meta' benvenuto: si fa da parte subito.
      if (!partito && document.querySelector(FINESTRA_APERTA)) saltaRef.current();
      if (!partito) {
        disegno.assemble = Math.min(1, e / 1.5);
        disegno.cresce = clamp((e - 1.35) / 0.45, 0, 1);
        if (e > 1.1 && !scritto) {
          scritto = true;
          setTesto(true);
        }
        if (e >= DURATA_FORMA) parti(0.95);
      }
      disegno.disegna({
        t: ora / 1000,
        dt,
        modo: "riposo",
        voce: 0,
        mx: 0,
        my: 0,
        puntatore: null,
        scuro: document.documentElement.classList.contains("dark"),
        fermo: false,
      });
    };
    id = requestAnimationFrame(ciclo);
    const tasto = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") saltaRef.current();
    };
    window.addEventListener("keydown", tasto);
    return () => {
      cancelAnimationFrame(id);
      window.clearTimeout(chiudi);
      window.removeEventListener("keydown", tasto);
    };
  }, [attivo]);

  if (!attivo) return null;
  return createPortal(
    <div
      role="presentation"
      onClick={() => saltaRef.current()}
      className={cn("fixed inset-0 z-[100] grid cursor-pointer place-items-center", vola && "pointer-events-none")}
    >
      <div
        className={cn("absolute inset-0 transition-opacity duration-900 ease-out", vola && "opacity-0")}
        style={{
          background:
            "radial-gradient(80% 70% at 50% 40%, color-mix(in oklab, var(--primary) 12%, var(--background)), var(--background) 70%)",
        }}
      />
      <div className="relative flex flex-col items-center px-4">
        <div ref={palcoRef} className="relative aspect-[1.6] w-[min(88vw,640px)] origin-top-left">
          <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 block h-full w-full" />
        </div>
        <div className={cn("text-center transition-opacity duration-300", vola && "opacity-0")}>
          <h2 className="text-3xl font-bold tracking-tight sm:text-4xl" aria-label={saluto}>
            {Array.from(saluto).map((c, i) => (
              <span
                key={i}
                aria-hidden="true"
                className={cn(
                  "inline-block whitespace-pre transition-all duration-500",
                  testo ? "translate-y-0 opacity-100 blur-none" : "translate-y-2 opacity-0 blur-sm",
                )}
                style={{ transitionDelay: `${i * 28}ms` }}
              >
                {c}
              </span>
            ))}
          </h2>
          <p className={cn("mt-2 text-muted-foreground transition-opacity delay-500 duration-700", testo ? "opacity-100" : "opacity-0")}>
            {sottotitolo}
          </p>
        </div>
      </div>
      <p className={cn("absolute bottom-6 text-xs text-muted-foreground transition-opacity", vola && "opacity-0")}>
        Clic o Esc per saltare
      </p>
    </div>,
    document.body,
  );
}
