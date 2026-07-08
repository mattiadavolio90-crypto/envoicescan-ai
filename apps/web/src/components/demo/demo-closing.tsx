"use client";

import { MessageCircle, RotateCcw } from "lucide-react";
import { Logo, Wordmark } from "@/components/brand/logo";
import { Button } from "@/components/ui/button";
import {
  DEMO_RINCARI_TROVATI,
  DEMO_WHATSAPP_MESSAGE,
  DEMO_WHATSAPP_NUMBER,
} from "@/lib/demo-steps";

// Schermata di CONVERSIONE. Impianto "incassa la demo":
//   1. Il disclaimer "dati di esempio" RIBALTATO in aggancio: Marea è finta,
//      le fatture del prospect no — e i suoi rincari veri nessuno li cerca.
//   2. Il bottino della demo (220 €/mese, stesso numero del contatore in barra)
//      come prova concreta di cosa fa il prodotto in 60 secondi.
//   3. Il messaggio WhatsApp GIÀ SCRITTO in una bolla, firmato dall'assistente
//      ("come faccio coi fornitori"): richiama il momento più forte della demo
//      (il messaggio di trattativa) e azzera lo sforzo del click.
//   4. Sprone ONESTO = vicinanza della ricompensa, non scadenze finte:
//      "domani mattina hai il primo briefing sul tuo locale".
export function DemoClosing({ onRestart }: { onRestart: () => void }) {
  const waHref = `https://wa.me/${DEMO_WHATSAPP_NUMBER}?text=${encodeURIComponent(
    DEMO_WHATSAPP_MESSAGE,
  )}`;

  return (
    <div className="flex min-h-svh flex-col items-center justify-center bg-gradient-to-br from-sky-500/10 via-background to-background px-6 py-12">
      <div className="w-full max-w-md text-center">
        <div className="flex items-center justify-center gap-2.5">
          <Logo variant="icon" size={36} glow />
          <Wordmark className="text-2xl" />
        </div>

        {/* Il disclaimer diventa l'aggancio */}
        <h1 className="mt-8 text-2xl font-bold leading-snug tracking-tight sm:text-3xl">
          Marea è una demo.
          <br />
          Il tuo locale no.
        </h1>

        {/* Incassa la demo: il bottino + il gap di curiosità sui SUOI numeri */}
        <p className="mt-3 text-base text-muted-foreground">
          Il tuo locale e le tue fatture sono reali. In un minuto ho trovato{" "}
          <span className="font-semibold text-foreground">
            {DEMO_RINCARI_TROVATI} € al mese di rincari
          </span>{" "}
          — su un ristorante finto. Nelle tue fatture ce ne sono di veri, e oggi
          nessuno li sta cercando.
        </p>

        {/* Il messaggio già pronto: richiama la trattativa vista in chat */}
        <div className="mt-8 rounded-2xl border border-border bg-card px-4 py-3 text-left shadow-sm">
          <p className="text-xs font-medium text-muted-foreground">
            Il messaggio te l&apos;ho già scritto io — come faccio coi fornitori.
            Tu devi solo premere invia:
          </p>
          <p className="mt-2 rounded-xl bg-emerald-500/10 px-3 py-2 text-sm leading-snug">
            {DEMO_WHATSAPP_MESSAGE}
          </p>
        </div>

        {/* CTA unica dominante */}
        <div className="mt-5 flex flex-col items-center gap-3">
          <a href={waHref} target="_blank" rel="noopener noreferrer" className="w-full max-w-sm">
            <Button size="lg" className="h-12 w-full gap-2 bg-emerald-600 text-base text-white shadow-lg shadow-emerald-600/30 hover:bg-emerald-700">
              <MessageCircle className="size-5" />
              Invia su WhatsApp
            </Button>
          </a>
          {/* Sprone onesto: ricompensa a 12 ore, non countdown */}
          <p className="max-w-sm text-sm text-muted-foreground">
            Ti risponde chi ha costruito ONEFLUX: ti apre l&apos;account e{" "}
            <span className="font-medium text-foreground">
              domani mattina hai il primo briefing sul tuo locale
            </span>
            .
          </p>
          <p className="text-xs text-muted-foreground">
            7 giorni gratis · senza carta · risposta in poche ore
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
          Dati di esempio. Recoma System S.r.l. — P.IVA IT09599210961
        </p>
      </div>
    </div>
  );
}
