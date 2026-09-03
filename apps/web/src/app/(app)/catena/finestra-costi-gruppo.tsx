"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, CopyPlus, FileText, PencilLine, ChevronDown, AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  datiCostoValidi,
  esitoCorrezioneCategoria,
  frammentoConteggioCosti,
  frammentoNonCorreggibili,
  mostraAvvisoDaClassificare,
  parseImportoManuale,
} from "@/lib/catena-costi-gruppo";
import { NativeSelect } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownCategoria } from "@/components/fatture/dropdown-categoria";
import { CATEGORIE_TUTTE } from "@/lib/admin";
import { formatEuro as euro } from "@/lib/format";
import { MESI_LUNGHI as MESI } from "@/lib/mesi";
import { daScegliereCategoria } from "@/lib/categorie-spesa";

type Quota = {
  ristorante_id: string;
  sede: string;
  quota_perc: number;
  quota_importo: number;
};

type DettaglioCategoria = {
  categoria: string;
  importo: number;
};

type RigaDocumento = {
  id: number;
  descrizione: string | null;
  categoria: string | null;
  totale_riga: number;
  needs_review: boolean;
};

type Costo = {
  id: string;
  origine: "fattura" | "manuale";
  file_origine: string | null;
  fornitore: string | null;
  descrizione: string;
  importo_totale: number;
  tipo: "generale" | "fb";
  regola: "equa" | "percentuali";
  // Una entry per SEDE (il backend aggrega le porzioni per-categoria).
  quote: Quota[];
  dettaglio_categorie: DettaglioCategoria[];
  // Righe reali del documento di struttura: qui si corregge la categoria.
  righe: RigaDocumento[];
};

type CostiComuniRes = {
  anno: number;
  mese: number;
  costi: Costo[];
  totale: number;
  // Quanto, di questo totale, sta pesando sul secchio spese del MOL solo perche'
  // non e' ancora classificato. A differenza delle righe fattura normali (escluse
  // dal MOL) una quota "Da Classificare" viene contata: la riga d'origine e' gia'
  // esclusa come ripartita_su_gruppo, quindi la quota e' l'unico posto in cui quel
  // costo esiste. Vedi 20260724220000_riparto_quote_per_categoria.sql.
  da_classificare_importo?: number;
  da_classificare_costi?: number;
  // Quanti di quei costi NON sono sistemabili da qui: le quote si correggono agendo
  // sulle righe del documento, quindi un costo che non ne ha lascia l'utente senza
  // azioni. In quel caso l'avviso cambia testo invece di dare un'istruzione che non
  // puo' funzionare.
  da_classificare_non_correggibili?: number;
};

export function FinestraCostiGruppo({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const annoCorrente = new Date().getFullYear();
  const meseCorrente = new Date().getMonth() + 1;
  const [mese, setMese] = useState<number>(meseCorrente);
  const [data, setData] = useState<CostiComuniRes | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [daEliminare, setDaEliminare] = useState<Costo | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const reqRef = useRef(0);

  const carica = useCallback(() => {
    const my = ++reqRef.current;
    setLoading(true);
    setLoadError(false);
    fetch(`/api/gruppo/costi-comuni?anno=${annoCorrente}&mese=${mese}`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((j) => {
        if (my === reqRef.current) setData(j);
      })
      .catch(() => {
        if (my === reqRef.current) {
          setLoadError(true);
          toast.error("Errore nel caricamento dei costi di gruppo");
        }
      })
      .finally(() => {
        if (my === reqRef.current) setLoading(false);
      });
  }, [annoCorrente, mese]);

  useEffect(() => {
    if (!open) return;
    carica();
  }, [open, carica]);

  async function elimina(c: Costo) {
    if (busy) return;
    setBusy(c.id);
    try {
      const res = await fetch(`/api/riparto/${c.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      toast.success("Ripartizione rimossa");
      carica();
    } catch {
      toast.error("Impossibile rimuovere la ripartizione");
    } finally {
      setBusy(null);
    }
  }

  async function duplica(c: Costo) {
    if (busy) return;
    setBusy(c.id);
    try {
      const res = await fetch(`/api/riparto/${c.id}/duplica`, { method: "POST" });
      if (!res.ok) throw new Error();
      toast.success("Duplicato sul mese successivo");
      carica();
    } catch {
      toast.error("Impossibile duplicare");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] flex-col gap-0 w-[min(96vw,56rem)] max-w-none overflow-hidden p-0 sm:max-w-none">
        <DialogHeader className="shrink-0 border-b px-5 py-4">
          <DialogTitle className="flex flex-wrap items-center justify-between gap-3 text-base">
            <span>Costi di gruppo</span>
            <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <NativeSelect
                value={String(mese)}
                onValueChange={(v) => setMese(Number(v))}
                className="h-8 w-40 text-xs"
              >
                {MESI.slice(0, meseCorrente).map((m, i) => (
                  <option key={i + 1} value={String(i + 1)}>
                    {m} {annoCorrente}
                  </option>
                ))}
              </NativeSelect>
              <Button size="sm" variant="outline" onClick={() => setAddOpen(true)}>
                <Plus className="size-3.5" />
                Aggiungi costo
              </Button>
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-3">
          <p className="mb-3 text-xs text-muted-foreground">
            Costi di struttura intestati alla sede legale, divisi fra i punti vendita. La quota di
            ogni sede entra nel suo MOL; nell&apos;analisi fatture il documento resta intero.
          </p>

          {loading && !data ? (
            <div className="py-16 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : loadError && !data ? (
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <AlertTriangle className="size-7 text-rose-500" />
              <p className="text-sm text-muted-foreground">
                Non è stato possibile caricare i dati.
              </p>
              <Button size="sm" variant="outline" onClick={carica} disabled={loading}>
                Riprova
              </Button>
            </div>
          ) : !data || data.costi.length === 0 ? (
            <div className="py-16 text-center text-sm text-muted-foreground">
              Nessun costo di gruppo in {MESI[mese - 1]}. Ripartisci una fattura dal suo dettaglio, o
              aggiungi un costo manuale (es. stipendi ufficio).
            </div>
          ) : (
            <ul className="space-y-3">
              {data.costi.map((c) => (
                <li key={c.id} className="rounded-lg border bg-card p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      {c.origine === "fattura" ? (
                        <FileText className="size-3.5 text-muted-foreground" />
                      ) : (
                        <PencilLine className="size-3.5 text-muted-foreground" />
                      )}
                      {c.descrizione}
                      <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[0.65rem] font-normal text-muted-foreground">
                        {c.tipo === "fb" ? "F&B" : "spese generali"}
                      </span>
                    </span>
                    <span className="font-semibold tabular-nums">{euro(c.importo_totale)}</span>
                  </div>

                  <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {c.quote.map((q) => (
                      <span key={q.ristorante_id}>
                        {q.sede}{" "}
                        <span className="font-medium text-foreground tabular-nums">{euro(q.quota_importo)}</span>{" "}
                        ({q.quota_perc.toLocaleString("it-IT", { maximumFractionDigits: 1 })}%)
                      </span>
                    ))}
                    <span className="text-muted-foreground/70">
                      {c.regola === "equa" ? "parti uguali" : "percentuali"}
                    </span>
                  </div>

                  <DettagliCosto costo={c} onCorretto={carica} />

                  <div className="mt-2 flex gap-2">
                    {c.origine === "manuale" && (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => duplica(c)}
                        className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs transition-colors hover:bg-accent disabled:opacity-50"
                      >
                        <CopyPlus className="size-3.5" />
                        Duplica sul mese dopo
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={busy !== null}
                      onClick={() => setDaEliminare(c)}
                      className="inline-flex items-center gap-1 rounded border px-2 py-1 text-xs text-destructive transition-colors hover:bg-destructive/10 disabled:opacity-50"
                    >
                      <Trash2 className="size-3.5" />
                      {c.origine === "fattura" ? "Rimuovi ripartizione" : "Elimina"}
                    </button>
                  </div>
                </li>
              ))}
              <li className="flex items-center justify-between border-t pt-3 text-sm font-semibold">
                <span>Totale costi di gruppo</span>
                <span className="tabular-nums">{euro(data.totale)}</span>
              </li>
            </ul>
          )}

          {mostraAvvisoDaClassificare(data?.da_classificare_importo) && (
            <div className="mt-3 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <p>
                <strong className="tabular-nums">{euro(data!.da_classificare_importo!)}</strong>{" "}
                di quote non sono ancora classificate
                {frammentoConteggioCosti(data!.da_classificare_costi)}
                . Finché restano così pesano tra le <em>Spese Generali</em>{" "}
                del MOL,
                anche se in parte sono Food &amp; Beverage. Assegna la categoria dalle
                righe del documento qui sopra per collocarle nel secchio giusto.
                {frammentoNonCorreggibili(
                  data!.da_classificare_non_correggibili,
                  data!.da_classificare_costi,
                ) && (
                  <>
                    {" "}
                    <strong>
                      {frammentoNonCorreggibili(
                        data!.da_classificare_non_correggibili,
                        data!.da_classificare_costi,
                      )}
                    </strong>{" "}
                    da cui correggerli: la fattura d&apos;origine non è più presente,
                    quindi vanno rifatti eliminando e ricreando il costo di gruppo.
                  </>
                )}
              </p>
            </div>
          )}
        </div>

        <AggiungiCostoDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          anno={annoCorrente}
          mese={mese}
          onDone={() => {
            setAddOpen(false);
            carica();
          }}
        />

        <ConfirmDialog
          open={daEliminare !== null}
          titolo={daEliminare?.origine === "fattura" ? "Rimuovere la ripartizione?" : "Eliminare questo costo di gruppo?"}
          messaggio={daEliminare?.origine === "fattura" ? "Il costo tornerà intero sulla sede intestataria." : undefined}
          confermaLabel={daEliminare?.origine === "fattura" ? "Rimuovi" : "Elimina"}
          onConferma={() => { if (daEliminare) elimina(daEliminare); }}
          onClose={() => setDaEliminare(null)}
        />
      </DialogContent>
    </Dialog>
  );
}

// Dialog per aggiungere una voce di costo di gruppo manuale (senza fattura).
function AggiungiCostoDialog({
  open,
  onOpenChange,
  anno,
  mese,
  onDone,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  anno: number;
  mese: number;
  onDone: () => void;
}) {
  const [descrizione, setDescrizione] = useState("");
  const [importo, setImporto] = useState("");
  const [categoria, setCategoria] = useState("");
  const [saving, setSaving] = useState(false);

  async function salva() {
    const imp = parseImportoManuale(importo);
    if (!datiCostoValidi(descrizione, imp, categoria)) {
      toast.error("Inserisci descrizione, importo e categoria");
      return;
    }
    setSaving(true);
    try {
      const res = await fetch("/api/riparto/manuale", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          descrizione: descrizione.trim(),
          importo_totale: imp,
          categoria,
          anno,
          mese,
          regola: "equa",
        }),
      });
      if (!res.ok) throw new Error();
      toast.success("Costo di gruppo aggiunto (parti uguali)");
      setDescrizione("");
      setImporto("");
      setCategoria("");
      onDone();
    } catch {
      toast.error("Impossibile aggiungere il costo");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Aggiungi costo di gruppo</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs font-medium">Descrizione</label>
            <input
              value={descrizione}
              onChange={(e) => setDescrizione(e.target.value)}
              placeholder="Es. Utenze sede centrale"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            />
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Importo (€)</label>
              <input
                value={importo}
                onChange={(e) => setImporto(e.target.value)}
                inputMode="decimal"
                placeholder="2000"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm tabular-nums"
              />
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium">Categoria</label>
              <div className="flex h-[38px] items-center rounded-md border bg-background px-3">
                <DropdownCategoria
                  value={categoria}
                  categorie={CATEGORIE_TUTTE}
                  onSelect={setCategoria}
                  daScegliere={!categoria}
                />
              </div>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            Diviso in parti uguali fra i punti vendita. Potrai modificarlo dalla lista.
          </p>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={saving}>
              Annulla
            </Button>
            <Button size="sm" onClick={salva} disabled={saving}>
              {saving ? "Salvataggio…" : "Aggiungi"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// Dettaglio di un costo di gruppo: le porzioni per categoria e le righe reali del
// documento di struttura, entrambe chiuse di default (il default resta pulito).
// Le righe sono l'unico posto dove una categoria sbagliata su un costo di gruppo si
// può correggere insieme al tab Articoli: vivono sulla sede tecnica, che non è
// selezionabile dallo switcher sedi.
function DettagliCosto({
  costo,
  onCorretto,
}: {
  costo: Costo;
  onCorretto: () => void;
}) {
  const [apriRighe, setApriRighe] = useState(false);
  const [salvando, setSalvando] = useState<number | null>(null);

  const daVerificare = costo.righe.filter((r) =>
    daScegliereCategoria(r.needs_review, r.categoria),
  ).length;

  async function correggi(riga: RigaDocumento, categoria: string) {
    if (!costo.file_origine || !riga.descrizione) return;
    setSalvando(riga.id);
    try {
      const res = await fetch("/api/riparto/riga-categoria", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_origine: costo.file_origine,
          descrizione: riga.descrizione,
          nuova_categoria: categoria,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        // La categoria è scritta, ma il ricalcolo quote è fallito: dirlo, altrimenti
        // il MOL resta disallineato in silenzio fino alla prossima scrittura.
        const esito = esitoCorrezioneCategoria(data);
        toast[esito.tipo](esito.messaggio);
        onCorretto();
      } else {
        toast.error(data.detail ?? data.error ?? "Errore aggiornamento");
      }
    } catch {
      toast.error("Errore di rete");
    } finally {
      setSalvando(null);
    }
  }

  if (!costo.righe.length) return null;

  return (
    <div className="mt-2 space-y-1.5 text-xs">
      {costo.righe.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setApriRighe((v) => !v)}
            className="inline-flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown
              className={`size-3 transition-transform ${apriRighe ? "" : "-rotate-90"}`}
            />
            righe del documento ({costo.righe.length})
            {daVerificare > 0 && (
              <span className="ml-1 rounded-full bg-rose-100 px-1.5 py-0.5 text-[0.65rem] font-semibold text-rose-700 dark:bg-rose-900/40 dark:text-rose-300">
                {daVerificare} da verificare
              </span>
            )}
          </button>
          {apriRighe && (
            <ul className="mt-1 space-y-1 pl-4">
              {costo.righe.map((r) => {
                const daScegliere = daScegliereCategoria(r.needs_review, r.categoria);
                return (
                  <li
                    key={r.id}
                    className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-dashed py-1 last:border-0"
                  >
                    <span className="min-w-0 flex-1 truncate" title={r.descrizione ?? ""}>
                      {r.descrizione || <em className="text-muted-foreground">senza descrizione</em>}
                    </span>
                    <DropdownCategoria
                      value={r.categoria ?? ""}
                      categorie={CATEGORIE_TUTTE}
                      onSelect={(c) => correggi(r, c)}
                      saving={salvando === r.id}
                      daScegliere={daScegliere}
                      compact
                    />
                    <span className="tabular-nums text-muted-foreground">
                      {euro(r.totale_riga)}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
