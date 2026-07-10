"use client";

import { MessageCircle, RotateCcw } from "lucide-react";
import { Logo, Wordmark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  DEMO_RINCARI_TROVATI,
  DEMO_WHATSAPP_MESSAGE,
  DEMO_WHATSAPP_NUMBER,
} from "@/lib/demo-steps";

// Schermata di CONVERSIONE. Diretta, poche righe prima del bottone (il
// disclaimer "dati di esempio" è già stato detto in copertina, qui non si
// ripete). Impianto (audit CRO 10/07):
//   1. Titolo = offerta esplicita ("prova ONEFLUX"), non una domanda.
//   2. Bottino della demo ANNUALIZZATO (220 €/mese → 2.640 €/anno: per il
//      target è una cifra che si sente) + gap di curiosità sui suoi numeri.
//   3. Il BOTTONE porta l'OFFERTA ("prova gratuita — 7 giorni"), non il
//      meccanismo ("invia su WhatsApp"): prima l'offerta era visibile solo
//      dentro il messaggio precompilato, cioè dopo il click.
//   4. Sotto il bottone: cosa succede dopo il click (niente da configurare,
//      briefing domattina) + risk reversal completo (senza carta, si disdice
//      con un messaggio — confermato da Mattia 10/07).
//   5. Riga prezzo col frame ROI: 39 €/mese contro i 220 €/mese appena visti
//      — aritmetica che il prospect ha verificato coi suoi occhi. Link ai
//      piani per chi vuole il dettaglio prima di scrivere.
export function DemoClosing({ onRestart }: { onRestart: () => void }) {
  const waHref = `https://wa.me/${DEMO_WHATSAPP_NUMBER}?text=${encodeURIComponent(
    DEMO_WHATSAPP_MESSAGE,
  )}`;
  const rincariAnnui = (DEMO_RINCARI_TROVATI * 12).toLocaleString("it-IT");

  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-gradient-to-br from-sky-500/10 via-background to-background px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="flex items-center justify-center gap-2.5">
          <Logo variant="icon" size={36} glow />
          <Wordmark className="text-2xl" />
        </div>

        {/* Titolo = offerta diretta, non domanda */}
        <h1 className="mt-8 text-2xl font-bold leading-snug tracking-tight sm:text-3xl">
          Prova ONEFLUX sul tuo locale
        </h1>

        {/* Incassa la demo: bottino mensile + annualizzato, poi il gap di
            curiosità sui SUOI numeri */}
        <p className="mt-3 text-base text-muted-foreground">
          In un minuto ho trovato{" "}
          <span className="font-semibold text-foreground">
            {DEMO_RINCARI_TROVATI} € al mese di rincari
          </span>{" "}
          — {rincariAnnui} € l&apos;anno, su dati di esempio. Nelle tue fatture
          vere nessuno li cerca.
        </p>

        {/* CTA unica dominante: il bottone porta l'offerta */}
        <div className="mt-6 flex flex-col items-center gap-3">
          <a href={waHref} target="_blank" rel="noopener noreferrer" className="w-full max-w-sm">
            <Button size="lg" className="h-12 w-full gap-2 bg-emerald-600 text-base text-white shadow-lg shadow-emerald-600/30 hover:bg-emerald-700">
              <MessageCircle className="size-5" />
              Attiva la prova gratuita — 7 giorni
            </Button>
          </a>
          {/* Cosa succede dopo il click + risk reversal, niente scadenze finte */}
          <p className="max-w-sm text-sm text-muted-foreground">
            Si apre WhatsApp col messaggio già pronto: lo mandi e attiviamo noi
            — tu non configuri niente
          </p>
          <p className="-mt-1.5 max-w-sm text-sm text-muted-foreground">
            Domani mattina hai il primo briefing · senza carta · si disdice con
            un messaggio
          </p>
          {/* Frame ROI sul prezzo: risponde a "quanto costa?" nel momento
              della decisione, legandolo al bottino appena visto */}
          <p className="mt-3 max-w-sm text-sm text-foreground/85">
            Piani da 39 € al mese, tutto incluso — solo i rincari di questa
            demo ne valgono cinque.{" "}
            <a
              href="/#piani"
              className="font-medium text-primary underline-offset-2 hover:underline"
            >
              Guarda i piani
            </a>
          </p>
          <button
            onClick={onRestart}
            className="mt-2 inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <RotateCcw className="size-4" />
            Rivedi il tour
          </button>
        </div>

        <p className="mt-10 text-xs text-muted-foreground/70">
          Dati di esempio. RECOMASYSTEM Srl — P.IVA 12993240154
        </p>
      </div>
    </div>
  );
}
