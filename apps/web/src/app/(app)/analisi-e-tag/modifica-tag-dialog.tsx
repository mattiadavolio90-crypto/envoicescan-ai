"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { NativeSelect } from "@/components/ui/select";
import type { CartellaTag, CustomTag, DescrizioneDistinta, TagProdotto } from "@/lib/tag";
import { EMOJI_TAG } from "@/lib/tag";
import { campiCambiati, ordinaCartelle } from "@/lib/tag-cartelle";
import {
  type FiltroSelettore,
  blocchiModifiche, chiaviDelTag, corpoModifiche, deselezionaTutti, differenze, inverti,
  partiContatore, righeSelettore, selezionaTutti, testoEsito,
} from "@/lib/tag-selezione";

const SERVIZIO_GIU = "Il servizio non risponde, riprova fra poco";

function messaggioErrore(status: number, generico: string): string {
  if (status === 401) return "Sessione scaduta, ricarica la pagina";
  if (status === 404) return "Il tag non esiste più: ricarica la pagina";
  return generico;
}

/** Errore sul tag stesso (POST/PATCH): nome doppio, cartella sparita, worker giu'. */
function messaggioErroreTag(status: number, detail: string, conCartella: boolean): string {
  if (status === 409) return "Esiste già un tag con questo nome";
  if (status === 404 && conCartella) return "Il tag o la cartella scelta non esistono più: ricarica la pagina";
  if (status === 400 && detail) return detail;
  if (status === 502 && !detail) return SERVIZIO_GIU;
  return messaggioErrore(status, detail || "Errore nel salvataggio del tag");
}

/** 401 e 404 non passano riprovando: lo dice gia' `messaggioErrore`. */
function errorePermanente(status: number): boolean {
  return status === 401 || status === 404;
}

async function dettaglio(res: Response): Promise<string> {
  const d = await res.json().catch(() => null);
  return typeof d?.detail === "string" ? d.detail : "";
}

/* ── Riquadro unico per «Nuovo tag» (tag=null) e «Modifica tag» ── */
export function ModificaTagDialog({
  open, onOpenChange, tag, cartelle, onSaved, onProdottiCambiati,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  tag: CustomTag | null;
  cartelle: CartellaTag[];
  onSaved: (saved: CustomTag, isNew: boolean) => void;
  /** Almeno una PATCH dei prodotti e' andata a segno (anche solo in parte). */
  onProdottiCambiati: () => void;
}) {
  const [nome, setNome] = useState("");
  const [emoji, setEmoji] = useState("");
  // "" = «Senza cartella»: il valore di un <select> e' sempre una stringa.
  const [cartellaScelta, setCartellaScelta] = useState("");
  const [tavolozzaAperta, setTavolozzaAperta] = useState(false);

  const [descrizioni, setDescrizioni] = useState<DescrizioneDistinta[]>([]);
  const [prodottiTag, setProdottiTag] = useState<TagProdotto[]>([]);
  const [caricamento, setCaricamento] = useState(false);
  const [erroreCaricamento, setErroreCaricamento] = useState(false);

  const [filtro, setFiltro] = useState<FiltroSelettore>("tutti");
  const [ricerca, setRicerca] = useState("");
  const [selezionati, setSelezionati] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  // L'ultimo stato salvato dal riquadro: un tag nuovo gia' creato da un Salva i
  // cui prodotti sono falliti, o un tag esistente dopo una PATCH riuscita. Il
  // secondo Salva confronta con questo, non con la copia presa all'apertura.
  const [creato, setCreato] = useState<CustomTag | null>(null);
  // Guardia sincrona contro il doppio invio (Invio ripetuto nel campo Nome):
  // `saving` e' uno stato e arriva al secondo keydown troppo tardi.
  const inCorso = useRef(false);

  function chiudi(v: boolean) {
    if (!v && inCorso.current) return;
    onOpenChange(v);
  }

  useEffect(() => {
    if (!open) return;
    let attivo = true;
    setNome(tag?.nome ?? "");
    setEmoji(tag?.emoji ?? "");
    setCartellaScelta(
      tag?.cartella_id != null && cartelle.some(c => c.id === tag.cartella_id) ? String(tag.cartella_id) : "",
    );
    setTavolozzaAperta(false);
    setRicerca("");
    setCreato(null);
    setDescrizioni([]);
    setProdottiTag([]);
    setSelezionati(new Set());
    setFiltro("tutti");
    setErroreCaricamento(false);
    setCaricamento(true);

    const richiesteProdotti = tag
      ? fetch(`/api/tag/${tag.id}/prodotti`).then(r => {
          if (!r.ok) throw new Error();
          return r.json();
        }).then(d => (d.prodotti ?? []) as TagProdotto[])
      : Promise.resolve([] as TagProdotto[]);
    const richiestaDescrizioni = fetch("/api/tag/descrizioni").then(r => {
      if (!r.ok) throw new Error();
      return r.json();
    }).then(d => (d.descrizioni ?? []) as DescrizioneDistinta[]);

    Promise.all([richiestaDescrizioni, richiesteProdotti])
      .then(([desc, prod]) => {
        if (!attivo) return;
        setDescrizioni(desc);
        setProdottiTag(prod);
        setSelezionati(chiaviDelTag(prod));
        setFiltro(prod.length > 0 ? "nel_tag" : "tutti");
      })
      .catch(() => { if (attivo) setErroreCaricamento(true); })
      .finally(() => { if (attivo) setCaricamento(false); });

    return () => { attivo = false; };
    // `cartelle` fuori di proposito: una cartella creata o riordinata mentre il
    // riquadro e' aperto non deve azzerare le spunte gia' fatte.
  }, [open, tag]);  // eslint-disable-line react-hooks/exhaustive-deps

  const cartelleOrdinate = useMemo(() => ordinaCartelle(cartelle), [cartelle]);

  const iniziali = useMemo(() => chiaviDelTag(prodottiTag), [prodottiTag]);
  const esito = useMemo(
    () => righeSelettore(descrizioni, prodottiTag, ricerca, filtro, selezionati),
    [descrizioni, prodottiTag, ricerca, filtro, selezionati],
  );
  const tutteLeRighe = useMemo(
    () => righeSelettore(descrizioni, prodottiTag, "", "tutti").corrispondenti,
    [descrizioni, prodottiTag],
  );
  const diff = useMemo(() => differenze(iniziali, selezionati), [iniziali, selezionati]);
  const contatore = partiContatore(diff.aggiungi.length, diff.togli.length);
  const chiaviCorrispondenti = esito.corrispondenti.map(r => r.descrizione_key);

  async function salva() {
    if (inCorso.current || caricamento) return;
    const n = nome.trim();
    if (!n) { toast.error("Inserisci un nome per il tag"); return; }
    const em = emoji.trim() || null;
    const cartellaId = cartellaScelta ? Number(cartellaScelta) : null;
    // L'ultimo stato salvato, anche per un tag esistente: dopo una PATCH riuscita
    // il confronto successivo parte da quello che e' sul DB.
    const base = creato ?? tag;
    inCorso.current = true;
    setSaving(true);
    try {
      let salvato: CustomTag | null = base;
      if (!base) {
        const res = await fetch("/api/tag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ nome: n, emoji: em, colore: null }),
        });
        if (!res.ok) throw new Error(messaggioErroreTag(res.status, await dettaglio(res), false));
        const data = await res.json();
        salvato = data?.tag ?? null;
        if (!salvato) throw new Error("Errore nel salvataggio del tag");
        setCreato(salvato);
        onSaved(salvato, true);
      }
      if (!salvato) return;

      // Un tag nuovo nasce senza cartella: la cartella scelta e' una modifica
      // come le altre, e se fallisce il secondo Salva la riprova sul tag creato.
      const campi = campiCambiati(salvato, { nome: n, emoji: em, cartella_id: cartellaId }, cartelle);
      if (Object.keys(campi).length > 0) {
        const res = await fetch(`/api/tag/${salvato.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(campi),
        });
        if (!res.ok) {
          const motivo = messaggioErroreTag(res.status, await dettaglio(res), "cartella_id" in campi);
          throw new Error(!base ? `Tag creato, ma non è stato messo nella cartella: ${motivo}` : motivo);
        }
        const data = await res.json().catch(() => null);
        const aggiornato: CustomTag = { ...salvato, ...campi, ...(data?.tag ?? {}) };
        setCreato(aggiornato);
        onSaved(aggiornato, false);
        salvato = aggiornato;
      }

      let esitoProdotti = "";
      const blocchi = blocchiModifiche(corpoModifiche(diff, tutteLeRighe));
      let aggiunte = 0;
      let tolte = 0;
      for (let i = 0; i < blocchi.length; i++) {
        const res = await fetch(`/api/tag/${salvato.id}/prodotti`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(blocchi[i]),
        }).catch(() => null);
        if (res && res.status === 502) {
          const detail = await dettaglio(res);
          if (detail) {
            // Il worker ha scritto le aggiunte e non (tutte) le rimozioni: il suo
            // messaggio dice gia' cosa e' successo. Lo stato del riquadro non e'
            // piu' quello del DB: si chiude e la pagina ricarica.
            toast.error(detail);
            onProdottiCambiati();
            inCorso.current = false;
            onOpenChange(false);
            return;
          }
          // Senza `detail` il 502 e' del proxy (workerUnreachable): il worker non
          // ha ricevuto questo blocco, e il riquadro resta com'e' per riprovare.
          if (i === 0) {
            toast.error(!tag ? `Tag creato, ma i prodotti non sono stati salvati: ${SERVIZIO_GIU.toLowerCase()}` : SERVIZIO_GIU);
            return;
          }
          toast.error(`Prodotti salvati solo in parte (${testoEsito(aggiunte, tolte)}): ${SERVIZIO_GIU.toLowerCase()}. Riapri il tag per completare.`);
          inCorso.current = false;
          onOpenChange(false);
          return;
        }
        if (!res || !res.ok) {
          const motivo = res ? messaggioErrore(res.status, await dettaglio(res)) : "";
          const premessa = !tag ? "Tag creato, ma i prodotti non sono stati salvati" : "I prodotti non sono stati salvati";
          if (i > 0) {
            // Una parte e' gia' scritta: lo stato del riquadro non e' piu' quello
            // del DB. Si chiude, cosi' la pagina ricarica e la riapertura parte giusta.
            toast.error(`Prodotti salvati solo in parte (${testoEsito(aggiunte, tolte)})${motivo ? `: ${motivo}` : ""}. Riapri il tag per completare.`);
            inCorso.current = false;
            onOpenChange(false);
            return;
          }
          toast.error(
            res && errorePermanente(res.status)
              ? `${premessa}: ${motivo}`
              : `${premessa}${motivo ? `: ${motivo}` : ""}. Riprova con Salva.`,
          );
          return;
        }
        onProdottiCambiati();
        const d = await res.json().catch(() => null);
        aggiunte += typeof d?.aggiunte === "number" ? d.aggiunte : blocchi[i].aggiungi.length;
        tolte += typeof d?.tolte === "number" ? d.tolte : blocchi[i].togli.length;
      }
      if (blocchi.length > 0) esitoProdotti = testoEsito(aggiunte, tolte);

      inCorso.current = false;
      if (salvato === base && !esitoProdotti) {
        onOpenChange(false);
        return;
      }
      const titolo = tag ? "Tag aggiornato" : "Tag creato";
      toast.success(esitoProdotti ? `${titolo}: ${esitoProdotti}` : titolo);
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error && e.message ? e.message : "Errore nel salvataggio del tag");
    } finally {
      inCorso.current = false;
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={chiudi}>
      <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-5 pt-5 pb-3 border-b border-border shrink-0">
          <DialogTitle>{tag ? "Modifica tag" : "Nuovo tag"}</DialogTitle>
        </DialogHeader>

        {/* Un'unica area che scorre: con i campi fissi sopra, su un telefono in
            orizzontale (375 px di altezza) la lista restava alta 1 px. Ricerca e
            «Seleziona tutti» restano agganciati in cima mentre si scorre. */}
        <div className="min-h-0 flex-1 overflow-y-auto">
        {/* Campi del tag: emoji, nome, cartella. */}
        <div className="min-w-0 px-5 pt-4 pb-2 space-y-3">
          <div className="flex min-w-0 items-center gap-2">
            <Popover open={tavolozzaAperta} onOpenChange={setTavolozzaAperta}>
              <PopoverTrigger
                render={
                  <Button variant="outline" size="icon" aria-label={emoji ? `Emoji ${emoji}, cambia` : "Scegli un'emoji"} title="Emoji del tag">
                    <span aria-hidden>{emoji || "🏷️"}</span>
                  </Button>
                }
              />
              <PopoverContent className="w-72 p-3 space-y-2" align="start">
                <div className="grid grid-cols-7 gap-1">
                  {EMOJI_TAG.map(em => (
                    <Button
                      key={em}
                      variant={emoji === em ? "secondary" : "ghost"}
                      size="icon"
                      aria-pressed={emoji === em}
                      className={emoji === em ? "border-primary bg-primary/10" : undefined}
                      onClick={() => { setEmoji(em); setTavolozzaAperta(false); }}
                    >
                      {em}
                    </Button>
                  ))}
                </div>
                {emoji && (
                  <Button variant="ghost" size="xs" onClick={() => { setEmoji(""); setTavolozzaAperta(false); }}>
                    Nessuna emoji
                  </Button>
                )}
              </PopoverContent>
            </Popover>
            <Input
              aria-label="Nome del tag"
              placeholder="Nome del tag, es. Salmone"
              value={nome}
              maxLength={100}
              onChange={e => setNome(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && !e.repeat) salva(); }}
              autoFocus={!tag}
            />
          </div>

          <label className="flex min-w-0 items-center gap-2">
            <span className="w-16 shrink-0 text-sm font-medium">Cartella</span>
            <NativeSelect
              aria-label="Cartella del tag"
              value={cartellaScelta}
              onValueChange={setCartellaScelta}
              className="min-w-0 flex-1"
            >
              <option value="">Senza cartella</option>
              {cartelleOrdinate.map(c => (
                <option key={c.id} value={String(c.id)}>{c.nome}</option>
              ))}
            </NativeSelect>
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Prodotti</span>
            {iniziali.size > 0 && (
              <SegmentedControl
                aria-label="Quali prodotti mostrare"
                value={filtro}
                onChange={setFiltro}
                options={[
                  { value: "nel_tag", label: `Nel tag (${iniziali.size})` },
                  { value: "tutti", label: "Tutti" },
                ]}
              />
            )}
          </div>
        </div>

        <div className="sticky top-0 z-10 min-w-0 space-y-2 border-b border-border bg-popover px-5 pt-1 pb-2">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <Input
              aria-label="Cerca prodotto"
              className="pl-8"
              placeholder="Cerca prodotto…"
              value={ricerca}
              onChange={e => setRicerca(e.target.value)}
              autoFocus={!!tag}
            />
          </div>

          <div className="flex flex-wrap items-center gap-1">
            <Button
              variant="ghost"
              size="xs"
              disabled={caricamento || esito.totale === 0 || esito.spuntateCorrispondenti === esito.totale}
              onClick={() => setSelezionati(s => selezionaTutti(s, chiaviCorrispondenti))}
            >
              Seleziona tutti ({esito.totale})
            </Button>
            <span className="text-xs text-muted-foreground" aria-hidden>·</span>
            <Button
              variant="ghost"
              size="xs"
              disabled={caricamento || esito.spuntateCorrispondenti === 0}
              onClick={() => setSelezionati(s => deselezionaTutti(s, chiaviCorrispondenti))}
            >
              Deseleziona tutti
            </Button>
          </div>
        </div>

        <div>
          {caricamento ? (
            <div className="space-y-2 p-3">
              {[1, 2, 3, 4].map(i => <div key={i} className="h-9 rounded-md bg-muted animate-pulse" />)}
            </div>
          ) : erroreCaricamento ? (
            <p className="text-sm text-muted-foreground py-6 px-5 text-center">
              Non è stato possibile caricare i prodotti. Chiudi e riapri il riquadro fra un momento.
            </p>
          ) : esito.visibili.length === 0 ? (
            <p className="text-sm text-muted-foreground py-6 text-center">Nessun prodotto trovato</p>
          ) : (
            <div className="divide-y divide-border">
              {esito.visibili.map(r => {
                const sel = selezionati.has(r.descrizione_key);
                return (
                  <label
                    key={r.descrizione_key}
                    className={`flex min-w-0 cursor-pointer items-center gap-3 px-5 py-2 text-sm transition-colors ${sel ? "bg-primary/10" : "hover:bg-muted"}`}
                  >
                    <input
                      type="checkbox"
                      className="size-4 shrink-0 cursor-pointer accent-primary"
                      checked={sel}
                      onChange={() => setSelezionati(s => inverti(s, r.descrizione_key))}
                    />
                    <span className="min-w-0 flex-1 truncate font-medium" title={r.descrizione}>{r.descrizione}</span>
                    {r.occorrenze != null ? (
                      <span className="text-xs text-muted-foreground shrink-0">{r.occorrenze} occ.</span>
                    ) : (
                      <span
                        className="text-xs text-muted-foreground shrink-0"
                        title="Non compare più fra le fatture caricate: puoi toglierlo dal tag"
                      >
                        non più in fattura
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          )}
        </div>
        </div>

        {/* border-t: senza stacco dalla lista scrollabile sopra, l'ultima riga
            tagliata a meta' sembrava parte di questo testo di aiuto. */}
        {!caricamento && esito.nascoste > 0 && (
          <p className="border-t border-border px-5 pt-2 pb-2 text-xs text-muted-foreground shrink-0">
            Mostrati {esito.visibili.length} di {esito.totale} prodotti — usa la ricerca per trovare gli altri.
          </p>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-t border-border shrink-0 bg-popover">
          <p className="text-sm text-muted-foreground">
            {!contatore.aggiungi && !contatore.togli && "Nessuna modifica ai prodotti"}
            {contatore.aggiungi && <span className="text-foreground">{contatore.aggiungi}</span>}
            {contatore.aggiungi && contatore.togli && " · "}
            {contatore.togli && <span className="text-negativo">{contatore.togli}</span>}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => chiudi(false)} disabled={saving}>
              Annulla
            </Button>
            <Button onClick={salva} disabled={saving || caricamento || !nome.trim()}>
              {saving ? "Salvataggio…" : "Salva"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
