import Link from "next/link";
import { Check, ArrowRight } from "lucide-react";
import { type Salute } from "@/lib/home";
import { vociCompletezza } from "@/lib/home-kpi";
import { CardHome, RiepilogoCompletezza } from "@/components/home/card-home";

// Soglie dell'indice decise lato backend (verde >=80, giallo 50-79, rosso <50):
// qui solo il disegno.
//
// hideLinks: su mobile (PWA) niente «Vai» che porterebbe fuori dalla Home verso
// la vista desktop.
export function SaluteCard({ salute, hideLinks = false }: { salute: Salute; hideLinks?: boolean }) {
  const { daSistemare, aPosto } = vociCompletezza(salute.voci);
  // Con tutte le voci spente dal configuratore non c'e' niente da dire: «tutte a
  // posto» sarebbe vero a vuoto.
  const nota =
    salute.voci.length === 0
      ? undefined
      : daSistemare.length === 0
      ? "Tutte le voci sono a posto"
      : `${daSistemare.length} ${daSistemare.length === 1 ? "voce" : "voci"} su ${salute.voci.length} da sistemare`;

  return (
    <CardHome titolo="Completezza dati" meta={<span className="capitalize">{salute.mese_label}</span>}>
      <RiepilogoCompletezza indice={salute.indice} colore={salute.colore} nota={nota} />

      {daSistemare.length > 0 && (
        <ul className="divide-y divide-border">
          {daSistemare.map((v) => (
            <li key={v.key} className="flex items-start gap-2.5 py-2 text-sm first:pt-0">
              <span className="mt-1.5 size-2 shrink-0 rounded-full bg-incerto" />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="font-medium">{v.label}</span>
                <span className="text-xs text-muted-foreground">{v.dettaglio}</span>
                {/* L'effetto sui numeri, quando c'e'. Ambra come il pallino. */}
                {v.conseguenza && <span className="text-xs text-incerto">{v.conseguenza}</span>}
              </div>
              {!hideLinks && v.cta_page && (
                <Link
                  href={v.cta_page}
                  title="Vai alla pagina"
                  className="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-primary-text hover:underline"
                >
                  Vai
                  <ArrowRight className="size-3.5" />
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Le voci a posto in una riga sola: il loro dettaglio resta nel title. */}
      {aPosto.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1 font-medium text-positivo">
            <Check className="size-3.5" />A posto:
          </span>
          {aPosto.map((v) => (
            <span key={v.key} title={v.dettaglio}>
              {v.label}
            </span>
          ))}
        </p>
      )}
    </CardHome>
  );
}
