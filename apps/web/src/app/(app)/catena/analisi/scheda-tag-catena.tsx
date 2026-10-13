"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Building2, Download, Pencil, Plus, Star, Tags, Trash2, Truck } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { formatEuro, formatEuro as euro, formatPct } from "@/lib/format";
import { MESI_LUNGHI as MESI_LABEL } from "@/lib/mesi";
import type { CartellaTag } from "@/lib/tag";
import {
  type VistaTag,
  leggiStatoComodo, primoTagMostrato, raggruppa, scriviStatoComodo, soloPreferiti,
} from "@/lib/tag-cartelle";
import { etichettaProdotti } from "@/lib/tag-selezione";
import { sorgenteCatena } from "@/lib/tag-sorgenti";
import {
  altezzaBarraTrend,
  analisiVuota,
  classePrezzo,
  estremiPrezzo,
  larghezzaBarra,
  massimoSpesa,
  nomeFileExport,
  righeExportFornitori,
  righeExportPv,
  soloUnPvConSpesa,
} from "@/lib/catena-tag";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { InfoPopover } from "@/components/ui/info-popover";
import { NativeSelect } from "@/components/ui/select";
import { PannelloTag } from "@/components/tag/pannello-tag";
import { ModificaTagDialog } from "@/components/tag/modifica-tag-dialog";
import type { GruppoTag, GruppoTagAnalisi } from "@/lib/gruppo";

// `formatEuro(v, 2)` con la guardia sul null: "—" e non "0,00 €" quando il dato
// non c'e'. Le due copie di questa funzione divergevano (una con il separatore
// delle migliaia, l'altra senza): unificate il 3/9 su decisione dell'owner.
function euro2(n: number | null): string {
  return n == null ? "—" : formatEuro(n, 2);
}
function num(n: number): string {
  return n.toLocaleString("it-IT", { maximumFractionDigits: 1 });
}
function pct(n: number): string {
  return formatPct(n);
}

// Vista e cartelle chiuse, per browser. Chiave diversa dalla sede: gli id delle
// cartelle di catena e di sede vengono da sequenze diverse.
const CHIAVE_STATO_COMODO = "oneflux:catena-tag:barra";

function leggiStorage(): string | null {
  try {
    return window.localStorage.getItem(CHIAVE_STATO_COMODO);
  } catch {
    return null;
  }
}

function scriviStorage(valore: string) {
  try {
    window.localStorage.setItem(CHIAVE_STATO_COMODO, valore);
  } catch {
    // Finestra privata o storage bloccato: la lista funziona lo stesso.
  }
}

function primoDaMostrare(tags: GruppoTag[], cartelle: CartellaTag[], vista: VistaTag, chiuse: number[]) {
  return primoTagMostrato(vista, raggruppa(tags, cartelle), soloPreferiti(tags), chiuse);
}

// Stessi posti dei cinque numeri della pagina «Analisi e Tag»: nessuna riga a
// meta', larghezze del riquadro e non dello schermo.
const KPI_POSTI = [
  "col-span-2 @lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-2 @3xl:col-span-1",
  "@lg:col-span-3 @3xl:col-span-1",
  "@lg:col-span-3 @3xl:col-span-1",
] as const;

function KpiCard({ label, value, principale, className }: {
  label: string; value: string; principale?: boolean; className?: string;
}) {
  return (
    <div className={cn(
      "flex min-w-0 flex-col gap-1 rounded-lg border bg-card px-4 pb-2.5 pt-3",
      principale ? "border-primary/40" : "border-border",
      className,
    )}>
      <p className="text-[11px] font-medium uppercase leading-tight tracking-wider text-muted-foreground">{label}</p>
      <p className="truncate text-xl font-bold tracking-tight tabular-nums" title={value}>{value}</p>
    </div>
  );
}

// Tag di catena = scheda di «Analisi catena». Raggruppa lo stesso prodotto su
// tutti i punti vendita e confronta la spesa per sede. Dal 13/10/2026 ha
// l'impianto di «Analisi e Tag» (Mattia: «replichiamo anche in catena allo
// stesso modo»): a sinistra la lista con cartelle e stella, a destra il tag
// scelto con l'analisi per punto vendita, che prima stava in una finestra.
export function SchedaTagCatena() {
  const [tags, setTags] = useState<GruppoTag[]>([]);
  const [cartelle, setCartelle] = useState<CartellaTag[]>([]);
  const [caricamento, setCaricamento] = useState(true);
  const [guasto, setGuasto] = useState(false);
  const [selectedTagId, setSelectedTagId] = useState<number | null>(null);
  const [vista, setVista] = useState<VistaTag>("tutte");
  const [chiuse, setChiuse] = useState<number[]>([]);
  const [comodoLetto, setComodoLetto] = useState(false);
  const [periodo, setPeriodo] = useState<string>("anno");

  const [dialogTag, setDialogTag] = useState<{ open: boolean; tag: GruppoTag | null }>({ open: false, tag: null });
  // Si ricarica solo se il riquadro ha cambiato qualcosa: chiuderlo con Annulla
  // non deve rifare lista e analisi.
  const dialogHaModificato = useRef(false);
  const [chiusureDialog, setChiusureDialog] = useState(0);
  const [confermaElimina, setConfermaElimina] = useState(false);
  // Guardia sincrona: un doppio clic su «Elimina tag» manderebbe due DELETE.
  const eliminando = useRef(false);

  const carica = useCallback(async (): Promise<{ tags: GruppoTag[]; cartelle: CartellaTag[] } | null> => {
    try {
      const res = await fetch("/api/gruppo/tag", { cache: "no-store" });
      if (!res.ok) throw new Error();
      const j = await res.json();
      const nuovi: GruppoTag[] = j.tags ?? [];
      const nuoveCartelle: CartellaTag[] = Array.isArray(j.cartelle) ? j.cartelle : [];
      setTags(nuovi);
      setCartelle(nuoveCartelle);
      setGuasto(false);
      return { tags: nuovi, cartelle: nuoveCartelle };
    } catch {
      setGuasto(true);
      toast.error("Errore nel caricamento dei tag di catena");
      return null;
    } finally {
      setCaricamento(false);
    }
  }, []);

  const ricarica = useCallback(() => { void carica(); }, [carica]);

  // Montaggio: vista ricordata, poi il primo tag mostrato.
  useEffect(() => {
    const stato = leggiStatoComodo(leggiStorage());
    setVista(stato.vista);
    setChiuse(stato.chiuse);
    setComodoLetto(true);
    carica().then(dati => {
      if (dati) setSelectedTagId(primoDaMostrare(dati.tags, dati.cartelle, stato.vista, stato.chiuse));
    });
  }, [carica]);

  useEffect(() => {
    if (comodoLetto) scriviStorage(scriviStatoComodo({ vista, chiuse }));
  }, [comodoLetto, vista, chiuse]);

  // Dopo un salvataggio nel riquadro: il numero di prodotti viene dalla lista.
  useEffect(() => {
    if (chiusureDialog > 0) void carica();
  }, [chiusureDialog, carica]);

  async function alternaPreferito(tag: GruppoTag) {
    const nuovo = !tag.preferito;
    setTags(prev => prev.map(t => (t.id === tag.id ? { ...t, preferito: nuovo } : t)));
    try {
      const res = await fetch(`/api/gruppo/tag/${tag.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preferito: nuovo }),
      });
      if (!res.ok) throw new Error();
    } catch {
      // Indietro solo se nessun altro clic ha gia' cambiato la stella nel frattempo.
      setTags(prev => prev.map(t => (t.id === tag.id && t.preferito === nuovo ? { ...t, preferito: !nuovo } : t)));
      toast.error("Non sono riuscito ad aggiornare i preferiti");
    }
  }

  async function eliminaTag(tagId: number) {
    if (eliminando.current) return;
    eliminando.current = true;
    try {
      const res = await fetch(`/api/gruppo/tag/${tagId}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Tag eliminato");
      const restanti = tags.filter(t => t.id !== tagId);
      setTags(restanti);
      if (selectedTagId === tagId) setSelectedTagId(primoDaMostrare(restanti, cartelle, vista, chiuse));
    } catch {
      toast.error("Impossibile eliminare il tag");
    } finally {
      eliminando.current = false;
    }
  }

  const selectedTag = tags.find(t => t.id === selectedTagId) ?? null;

  return (
    <div className="grid items-start gap-6 xl:grid-cols-[17rem_minmax(0,1fr)]">
      <PannelloTag
        sorgente={sorgenteCatena}
        tags={tags}
        cartelle={cartelle}
        setTags={setTags}
        setCartelle={setCartelle}
        vista={vista}
        onVista={setVista}
        chiuse={chiuse}
        onChiuse={setChiuse}
        selectedTagId={selectedTagId}
        onSelezionaTag={setSelectedTagId}
        onNuovoTag={() => setDialogTag({ open: true, tag: null })}
        onRicarica={ricarica}
        info={
          <InfoPopover title="Come funzionano i tag di catena">
            <p className="text-muted-foreground">
              Un tag di catena raggruppa <strong className="text-foreground">lo stesso prodotto su tutti i punti
              vendita</strong> e confronta la spesa sede per sede. È separato dai tag del singolo locale.
            </p>
            <div className="space-y-1.5 text-muted-foreground">
              <p><strong className="text-foreground">Crea un tag</strong> con <em>Nuovo tag</em> e spunta i prodotti: la ricerca guarda le fatture di tutti i punti vendita. Per cambiarlo usa <em>Modifica tag</em>.</p>
              <p><strong className="text-foreground">Cartelle e preferiti</strong> servono solo a tenere in ordine la lista: trascina un tag in una cartella e segna con la ☆ quelli che usi di più. Non cambiano nessuna analisi.</p>
            </div>
          </InfoPopover>
        }
      />

      <div className="min-w-0 space-y-5">
        {!caricamento && tags.length === 0 && (
          <div className="rounded-xl border border-dashed border-border bg-card py-16 text-center">
            <Tags className="mx-auto mb-3 size-10 text-muted-foreground" />
            {guasto ? (
              <>
                <p className="text-sm font-medium">Tag di catena non disponibili in questo momento</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Non è stato possibile caricarli. Ricarica la pagina fra un momento: i tuoi tag non sono stati persi.
                </p>
              </>
            ) : (
              <>
                <p className="text-sm font-medium">Nessun tag di catena</p>
                <p className="mb-4 mt-1 text-xs text-muted-foreground">
                  Creane uno per confrontare un prodotto fra i punti vendita.
                </p>
                <Button onClick={() => setDialogTag({ open: true, tag: null })}>
                  <Plus />
                  Crea il primo tag
                </Button>
              </>
            )}
          </div>
        )}

        {caricamento && <div className="h-96 animate-pulse rounded-xl border bg-muted/40" />}

        {/* Ci sono tag ma nessuno e' scelto (cartelle chiuse, nessun preferito). */}
        {!caricamento && tags.length > 0 && !selectedTag && (
          <div className="rounded-xl border border-dashed border-border bg-card py-16 text-center">
            <Tags className="mx-auto mb-3 size-10 text-muted-foreground" />
            <p className="text-sm font-medium">Scegli un tag dalla lista</p>
            <p className="mt-1 text-xs text-muted-foreground">Vedrai la spesa di ogni punto vendita, i fornitori e l&apos;andamento.</p>
          </div>
        )}

        {selectedTag && (
          <section aria-label={`Tag ${selectedTag.nome}`} className="@container overflow-hidden rounded-xl border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 px-5 pb-3 pt-4">
              <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1">
                {selectedTag.emoji && <span className="text-2xl leading-none" aria-hidden>{selectedTag.emoji}</span>}
                <h2 className="min-w-0 truncate text-xl font-semibold tracking-tight" title={selectedTag.nome}>{selectedTag.nome}</h2>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-pressed={!!selectedTag.preferito}
                  aria-label={selectedTag.preferito ? "Togli dai preferiti" : "Aggiungi ai preferiti"}
                  title={selectedTag.preferito ? "Togli dai preferiti" : "Aggiungi ai preferiti"}
                  onClick={() => alternaPreferito(selectedTag)}
                >
                  <Star className={selectedTag.preferito ? "fill-incerto text-incerto" : "text-muted-foreground"} />
                </Button>
                <Button
                  variant="link"
                  size="sm"
                  className="px-1 text-muted-foreground underline decoration-border underline-offset-4 hover:text-foreground"
                  onClick={() => setDialogTag({ open: true, tag: selectedTag })}
                >
                  {etichettaProdotti(selectedTag.n_prodotti ?? 0)}
                </Button>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="outline" onClick={() => setDialogTag({ open: true, tag: selectedTag })}>
                  <Pencil />
                  Modifica tag
                </Button>
                <Button
                  variant="outline"
                  size="icon"
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Elimina tag"
                  title="Elimina tag"
                  onClick={() => setConfermaElimina(true)}
                >
                  <Trash2 />
                </Button>
              </div>
            </div>

            <AnalisiPerPuntoVendita
              key={`${selectedTag.id}:${chiusureDialog}`}
              tag={selectedTag}
              periodo={periodo}
              onPeriodo={setPeriodo}
            />
          </section>
        )}
      </div>

      <ConfirmDialog
        open={confermaElimina && selectedTag !== null}
        titolo={`Eliminare il tag «${selectedTag?.nome ?? ""}»?`}
        messaggio="Si cancellano il tag e la sua lista di prodotti. Le fatture e le altre analisi non cambiano."
        confermaLabel="Elimina tag"
        onConferma={() => { if (selectedTag) eliminaTag(selectedTag.id); }}
        onClose={() => setConfermaElimina(false)}
      />
      <ModificaTagDialog
        sorgente={sorgenteCatena}
        open={dialogTag.open}
        onOpenChange={v => {
          setDialogTag(d => ({ ...d, open: v }));
          if (v) dialogHaModificato.current = false;
          else if (dialogHaModificato.current) {
            dialogHaModificato.current = false;
            setChiusureDialog(n => n + 1);
          }
        }}
        onProdottiCambiati={() => { dialogHaModificato.current = true; }}
        tag={dialogTag.tag}
        cartelle={cartelle}
        onSaved={(saved, isNew) => {
          dialogHaModificato.current = true;
          if (isNew) {
            setTags(prev => [...prev, { ...saved, n_prodotti: 0 }]);
            setSelectedTagId(saved.id);
          } else {
            setTags(prev => prev.map(t => (t.id === saved.id ? { ...t, ...saved } : t)));
          }
        }}
      />
    </div>
  );
}

/* ── Periodo e analisi del tag scelto, per punto vendita ── */
function AnalisiPerPuntoVendita({
  tag, periodo, onPeriodo,
}: {
  tag: GruppoTag;
  periodo: string;
  onPeriodo: (p: string) => void;
}) {
  const [data, setData] = useState<GruppoTagAnalisi | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const reqRef = useRef(0);

  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;

  // `r.ok ? r.json() : null` faceva arrivare i 5xx nel ramo di successo come
  // data=null, bypassando il catch: l'errore diventava "nessuna spesa nel periodo".
  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    const qs = periodo !== "anno" ? `?mese=${periodo}` : "";
    fetch(`/api/gruppo/tag/${tag.id}/analisi${qs}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => { if (my === reqRef.current) setData(j); })
      .catch(() => { if (my === reqRef.current) setLoadError(true); })
      .finally(() => { if (my === reqRef.current) setLoading(false); });
  }, [tag.id, periodo]);

  useEffect(() => {
    carica();
  }, [carica]);

  const maxPv = data ? massimoSpesa(data.per_pv) : 0;
  const maxForn = data ? massimoSpesa(data.fornitori) : 0;
  const maxTrend = data ? massimoSpesa(data.trend) : 0;
  // Prezzo medio: evidenzia chi paga meno (verde) e di più (rosso), se ≥2 PV con dato.
  const { minPrezzo, maxPrezzo } = estremiPrezzo(data?.per_pv);

  async function exportXls() {
    if (!data) return;
    try {
      const XLSX = await import("xlsx");
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(righeExportPv(data.per_pv)), "Per punto vendita");
      XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(righeExportFornitori(data.fornitori)), "Fornitori");
      XLSX.writeFile(wb, nomeFileExport(data.nome, data.periodo_label));
    } catch {
      toast.error("Errore nell'export");
    }
  }

  const vuoto = analisiVuota(data);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 pb-4">
        <label className="flex items-center gap-2 text-sm">
          <span className="font-medium">Periodo</span>
          <NativeSelect value={periodo} onValueChange={onPeriodo} aria-label="Periodo dell'analisi" className="w-52">
            <option value="anno">Anno in corso ({annoCorrente})</option>
            {MESI_LABEL.slice(0, meseCorrente).map((m, i) => (
              <option key={i + 1} value={String(i + 1)}>{m} {annoCorrente}</option>
            ))}
          </NativeSelect>
        </label>
        <Button variant="outline" size="sm" onClick={exportXls} disabled={vuoto || loading}>
          <Download />
          Esporta
        </Button>
      </div>

      <div className="space-y-6 p-5">
        {loading && !data ? (
          <div className="grid grid-cols-2 gap-3 @lg:grid-cols-6 @3xl:grid-cols-5">
            {KPI_POSTI.map((posto, i) => <div key={i} className={cn("h-20 animate-pulse rounded-lg border bg-card", posto)} />)}
          </div>
        ) : loadError && !data ? (
          <div className="flex flex-col items-center gap-3 py-12 text-center">
            <p className="text-sm text-muted-foreground">Non è stato possibile caricare i dati.</p>
            <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
              Riprova
            </Button>
          </div>
        ) : vuoto ? (
          <div className="rounded-lg border border-dashed border-border py-10 text-center">
            <p className="text-sm text-muted-foreground">Nessuna spesa nel periodo per questo tag.</p>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-3 @lg:grid-cols-6 @3xl:grid-cols-5">
              <KpiCard className={KPI_POSTI[0]} principale label="Spesa totale" value={euro(data!.spesa_totale)} />
              <KpiCard className={KPI_POSTI[1]} label="Quantità" value={num(data!.quantita_totale)} />
              <KpiCard className={KPI_POSTI[2]} label="Prezzo medio" value={euro2(data!.prezzo_medio)} />
              <KpiCard className={KPI_POSTI[3]} label="Fornitori" value={String(data!.n_fornitori)} />
              <KpiCard className={KPI_POSTI[4]} label="Voci in fattura" value={String(data!.per_pv.reduce((s, p) => s + p.n_righe, 0))} />
            </div>

            <section className="space-y-3 border-t pt-5" aria-label="Per punto vendita">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <Building2 className="size-4 text-muted-foreground" aria-hidden />
                Per punto vendita
              </h3>
              <ul className="space-y-2">
                {data!.per_pv.map((p) => (
                  <li key={p.ristorante_id} className="rounded-lg border px-4 py-3">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium" title={p.nome}>{p.nome}</span>
                      <span className="text-sm font-semibold tabular-nums">{euro(p.spesa)}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary"
                        style={{ width: larghezzaBarra(p.spesa, maxPv) }} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      <span>{pct(p.incidenza_pct)} del gruppo</span>
                      <span aria-hidden>·</span>
                      <span>
                        prezzo medio{" "}
                        <span className={cn(
                          "font-medium tabular-nums",
                          classePrezzo(p.prezzo_medio, minPrezzo, maxPrezzo),
                        )}>{euro2(p.prezzo_medio)}</span>
                      </span>
                      <span aria-hidden>·</span>
                      <span>{p.n_righe} righe · {p.n_fornitori} forn.</span>
                    </div>
                  </li>
                ))}
              </ul>
              {/* Se un solo PV ha spesa, le descrizioni del tag sono di quella
                  sede: il confronto fra PV si abilita aggiungendo le varianti
                  delle altre. */}
              {soloUnPvConSpesa(data!.per_pv) && (
                <p className="rounded-md border border-primary/30 bg-accent px-3 py-2 text-xs text-primary-text">
                  Solo un punto vendita ha spesa: aggiungi al tag anche le descrizioni «{tag.nome}» delle
                  altre sedi (da «Modifica tag») per confrontare i prezzi tra i punti vendita.
                </p>
              )}
            </section>

            {data!.fornitori.length > 0 && (
              <section className="space-y-3 border-t pt-5" aria-label="Fornitori">
                <h3 className="text-sm font-semibold">Fornitori (tutto il gruppo)</h3>
                <ul className="space-y-1.5">
                  {data!.fornitori.map((f) => (
                    <li key={f.nome} className="rounded-lg border px-3 py-2">
                      <div className="flex items-baseline justify-between gap-2 text-sm">
                        <span className="flex min-w-0 items-center gap-1.5">
                          <Truck className="size-3.5 shrink-0 text-muted-foreground/60" />
                          <span className="truncate font-medium" title={f.nome}>{f.nome}</span>
                        </span>
                        <span className="shrink-0 tabular-nums">{euro(f.spesa)} · {pct(f.incidenza_pct)}</span>
                      </div>
                      <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary/70"
                          style={{ width: larghezzaBarra(f.spesa, maxForn) }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Andamento mensile (solo se più di un mese nel periodo) */}
            {data!.trend.length > 1 && (
              <section className="space-y-3 border-t pt-5" aria-label="Andamento mensile">
                <h3 className="text-sm font-semibold">Andamento mensile</h3>
                <div className="flex items-end gap-1.5">
                  {data!.trend.map((t) => (
                    <div key={`${t.anno}-${t.mese}`} className="flex flex-1 flex-col items-center gap-1">
                      <div className="flex h-24 w-full items-end">
                        <div className="w-full rounded-t bg-primary/70" title={euro(t.spesa)}
                          style={{ height: altezzaBarraTrend(t.spesa, maxTrend) }} />
                      </div>
                      <span className="text-[10px] text-muted-foreground">{MESI_LABEL[t.mese - 1].slice(0, 3)}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </>
  );
}
