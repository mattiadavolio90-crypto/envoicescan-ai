"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { parametriDisiscrizione } from "@/lib/disiscrizione";

// La pagina del link «Non voglio più riceverla» dell'email settimanale.
// Non disiscrive all'apertura: i filtri antispam aprono i link delle email, e
// una pagina che agisce da sola disiscriverebbe chiunque la riceva. Serve il
// bottone, cioè un POST.
export function DisiscrizioneClient() {
  const query = useSearchParams();
  const parametri = parametriDisiscrizione(query, null);
  const [stato, setStato] = useState<"attesa" | "invio" | "fatto" | "errore">("attesa");

  async function conferma() {
    if (!parametri) return;
    setStato("invio");
    try {
      const res = await fetch("/api/email/disiscrizione", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parametri),
      });
      setStato(res.ok ? "fatto" : "errore");
    } catch {
      setStato("errore");
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 py-8 text-center">
      <h1 className="text-2xl font-bold text-foreground">Email settimanale</h1>
      {!parametri ? (
        <p className="text-sm text-muted-foreground">
          Questo link non è valido. Puoi spegnere l&apos;email settimanale dalle Impostazioni di
          ONEFLUX.
        </p>
      ) : stato === "fatto" ? (
        <p className="text-sm text-muted-foreground">
          Fatto: non riceverai più l&apos;email settimanale. Se cambi idea, la riaccendi dalle
          Impostazioni.
        </p>
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            Vuoi smettere di ricevere l&apos;email del lunedì con il riepilogo della settimana del
            tuo locale?
          </p>
          <Button onClick={conferma} disabled={stato === "invio"}>
            {stato === "invio" ? "Un momento…" : "Non voglio più riceverla"}
          </Button>
          {stato === "errore" && (
            <p className="text-sm text-negativo">
              Non è stato possibile completare la richiesta. Riprova, oppure spegnila dalle
              Impostazioni.
            </p>
          )}
        </>
      )}
      <p className="text-xs text-muted-foreground">
        <Link href="/login" className="text-primary-text hover:underline">
          Accedi a ONEFLUX
        </Link>
      </p>
    </div>
  );
}
