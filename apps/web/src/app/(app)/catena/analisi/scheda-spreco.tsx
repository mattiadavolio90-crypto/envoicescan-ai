"use client";

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Sprout } from "lucide-react";
import { cn } from "@/lib/utils";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";
import { formatEuro } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/select";
import { type SprecoCategorie } from "@/lib/gruppo";
import { rigaExtremes } from "@/lib/catena-confronti";
import { AREA_TABELLA, PannelloScheda } from "@/components/ui/pannello-scheda";

// Scheda «Spreco» (Mattia, 12/10/2026). Prima stava in fondo a «Margini e
// coperti» col periodo di quella tabella; da scheda ha il suo selettore. La
// pagina non la mostra a chi ha i coperti spenti (`schedeAnalisiCatena`).
export function SchedaSpreco() {
  const [periodo, setPeriodo] = useState<string>("anno");
  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  return (
    <SezioneSprecoCategorie
      mese={periodo !== "anno" ? Number(periodo) : null}
      azioni={
        <NativeSelect value={periodo} onValueChange={setPeriodo} className="h-8 w-48 text-xs">
          <option value="anno">Anno in corso ({annoCorrente})</option>
          {MESI.slice(0, meseCorrente).map((m, i) => (
            <option key={i + 1} value={String(i + 1)}>{m} {annoCorrente}</option>
          ))}
        </NativeSelect>
      }
    />
  );
}

// ─── Spreco (€MP/coperto) per categoria, confronto fra PV ───────────────────

// `formatEuro(v, 2)` con la guardia sul null: "—" e non "0,00 €" quando il dato
// non c'e'. Le due copie di questa funzione divergevano (una con il separatore
// delle migliaia, l'altra senza): unificate il 3/9 su decisione dell'owner.
function euro2(n: number | null): string {
  return n == null ? "—" : formatEuro(n, 2);
}

function SezioneSprecoCategorie({ mese, azioni }: { mese: number | null; azioni: ReactNode }) {
  const [data, setData] = useState<SprecoCategorie | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const reqRef = useRef(0);

  // Su errore NON si azzera `data`: un refetch fallito (cambio mese) deve lasciare
  // a schermo i dati precedenti, non sostituirli con "nessun dato".
  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    const qs = mese ? `?mese=${mese}` : "";
    fetch(`/api/gruppo/spreco-categorie${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => { if (my === reqRef.current) setData(j); })
      // Niente toast: la sezione si carica da sola con la scheda, e l'errore
      // lo dice gia' il riquadro «Non è stato possibile caricare i dati».
      .catch(() => { if (my === reqRef.current) setLoadError(true); })
      .finally(() => { if (my === reqRef.current) setLoading(false); });
  }, [mese]);

  useEffect(() => {
    carica();
  }, [carica]);

  return (
    <PannelloScheda
      azioni={azioni}
      titolo={
        <>
          <Sprout className="size-4 text-positivo" />
          Spreco per categoria · confronto punti vendita
          {data?.periodo_label && (
            <span className="text-xs font-normal text-muted-foreground">— {data.periodo_label}</span>
          )}
        </>
      }
    >
      {loading && !data ? (
        <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
      ) : loadError && !data ? (
        <div className="flex flex-col items-center gap-3 py-16 text-center">
          <AlertTriangle className="size-7 text-negativo" />
          <p className="text-sm text-muted-foreground">
            Non è stato possibile caricare i dati.
          </p>
          <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
            Riprova
          </Button>
        </div>
      ) : !data || data.righe.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          Nessun dato: servono coperti e fatture F&amp;B classificate nel periodo.
        </div>
      ) : (
        <>
          {/* Un ricaricamento fallito (cambio mese) lascia i dati di prima: si
              dice quali sono, o sembrerebbero quelli del periodo scelto. */}
          {loadError && (
            <p className="mb-3 flex flex-wrap items-center gap-2 rounded-md border border-negativo/30 px-3 py-2 text-xs text-negativo">
              <AlertTriangle className="size-3.5 shrink-0" />
              Aggiornamento non riuscito: restano i dati di {data.periodo_label}.
              <Button size="sm" variant="outline" className="h-6 text-xs" onClick={carica} disabled={loading}>
                Riprova
              </Button>
            </p>
          )}
          <div className={AREA_TABELLA}>
            <table className="w-full border-separate border-spacing-0 text-sm">
              <thead className="sticky top-0 z-30 bg-card shadow-[0_1px_0_0_var(--color-border)]">
                <tr>
                  <th className="sticky left-0 z-40 bg-card px-3 py-2 text-left font-semibold">
                    Categoria
                  </th>
                  {data.pv.map((p) => (
                    <th
                      key={p.ristorante_id}
                      className="max-w-[10rem] px-3 py-2 text-right font-semibold"
                      title={p.nome}
                    >
                      <span className="block truncate" title={p.nome}>{p.nome}</span>
                    </th>
                  ))}
                  <th className="px-3 py-2 text-right font-bold text-positivo">
                    Media gruppo
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.righe.map((r) => {
                  const ex = rigaExtremes(r);
                  return (
                    <tr key={r.categoria} className="border-t transition-colors hover:bg-muted/30">
                      <td className="sticky left-0 z-10 max-w-[16rem] bg-card px-3 py-2 font-medium">
                        <span className="block truncate" title={r.categoria}>{r.categoria}</span>
                      </td>
                      {r.per_pv.map((c) => {
                        const v = c.valore;
                        const tone =
                          v == null || ex.best == null
                            ? ""
                            : v === ex.best && v !== ex.worst
                              ? "text-positivo font-semibold"
                              : v === ex.worst && v !== ex.best
                                ? "text-negativo font-semibold"
                                : "";
                        return (
                          <td key={c.ristorante_id} className={cn("px-3 py-2 text-right tabular-nums", tone)}>
                            {euro2(v)}
                          </td>
                        );
                      })}
                      <td className="px-3 py-2 text-right font-bold tabular-nums text-positivo">
                        {euro2(r.media_gruppo)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Quanto costa in <span className="font-medium">materie prime per coperto</span> ogni
            categoria, a confronto tra i punti vendita. Per categoria:{" "}
            <span className="font-medium">spesa F&amp;B ÷ coperti</span> dei soli mesi con fatture
            caricate. <span className="text-positivo">verde</span> = il PV
            più efficiente sulla categoria, <span className="text-negativo">rosso</span>{" "}
            = il più caro. Rivendita esclusa (merce comprata per rivenderla). «—» = nessun dato per quel PV.
          </p>
        </>
      )}
    </PannelloScheda>
  );
}
