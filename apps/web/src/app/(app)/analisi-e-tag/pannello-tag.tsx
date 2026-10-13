"use client";

import { useId, useMemo, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";
import {
  ChevronDown, ChevronRight, Folder, GripVertical, MoreHorizontal, Pencil, Plus, Star, Tag as TagIcon, Trash2,
} from "lucide-react";
import { toast } from "sonner";
import {
  DndContext, DragOverlay, KeyboardSensor, MouseSensor, TouchSensor,
  closestCenter, pointerWithin, rectIntersection, useDraggable, useDroppable, useSensor, useSensors,
  type Announcements, type CollisionDetection, type DragEndEvent, type DragStartEvent, type UniqueIdentifier,
} from "@dnd-kit/core";
import {
  SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import type { CartellaTag, CustomTag } from "@/lib/tag";
import {
  type RigaCartella, type VistaTag,
  alternaChiusa, applicaOrdine, cartellaDaIdRiga, idRiga, idTagTrascinabile, messaggioErroreCartella,
  nomeCartellaGiaUsato, ordinaCartelle, raggruppa, riordina, soloPreferiti, spostaTag, stessoOrdine, tagDaIdTrascinabile,
} from "@/lib/tag-cartelle";

const JSON_HEADERS = { "Content-Type": "application/json" };

// I due tasti che creano qualcosa sono gemelli (Mattia, 13/10): stessa forma,
// l'icona di cio' che nasce a sinistra e il «+» a destra.
const CLASSE_CREA =
  "w-full justify-start gap-2 border-primary/40 bg-primary/5 font-semibold text-primary-text hover:border-primary hover:bg-primary/10 hover:text-primary-text";

async function dettaglio(res: Response): Promise<string> {
  const d = await res.json().catch(() => null);
  return typeof d?.detail === "string" ? d.detail : "";
}

type Trascinato = { tipo: "tag"; tag: CustomTag } | { tipo: "cartella"; cartella: CartellaTag };

/* ── Riga di un tag ── */
function RigaTag({ tag, attivo, onClick }: { tag: CustomTag; attivo: boolean; onClick?: () => void }) {
  return (
    <Button
      variant="ghost"
      aria-current={attivo ? "true" : undefined}
      onClick={onClick}
      className={cn(
        "w-full justify-start gap-2 px-2.5",
        attivo && "bg-primary/10 font-semibold text-primary-text hover:bg-primary/10 hover:text-primary-text",
      )}
    >
      {tag.emoji
        ? <span aria-hidden className="w-4 shrink-0 text-center">{tag.emoji}</span>
        : <TagIcon aria-hidden className="text-muted-foreground" />}
      <span className="min-w-0 flex-1 truncate text-left" title={tag.nome}>{tag.nome}</span>
      {tag.preferito && <Star aria-label="preferito" className="fill-incerto text-incerto" />}
    </Button>
  );
}

// Il trascinamento della riga parte solo col puntatore e col dito: Invio e
// Spazio devono continuare a selezionare il tag. Da tastiera la cartella di un
// tag si cambia dal campo «Cartella» di «Modifica tag».
function RigaTagTrascinabile({ tag, attivo, onClick }: { tag: CustomTag; attivo: boolean; onClick: () => void }) {
  const { setNodeRef, listeners, isDragging } = useDraggable({
    id: idTagTrascinabile(tag.id),
    data: { tipo: "tag" },
  });
  const soloPuntatore = Object.fromEntries(
    Object.entries(listeners ?? {}).filter(([evento]) => evento !== "onKeyDown"),
  );
  return (
    <div ref={setNodeRef} {...soloPuntatore} className={cn("touch-manipulation", isDragging && "opacity-40")}>
      <RigaTag tag={tag} attivo={attivo} onClick={onClick} />
    </div>
  );
}

function TagDellaRiga({
  riga, selectedTagId, onSeleziona,
}: {
  riga: RigaCartella;
  selectedTagId: number | null;
  onSeleziona: (id: number) => void;
}) {
  return (
    <>
      {riga.tags.map(t => (
        <RigaTagTrascinabile key={t.id} tag={t} attivo={t.id === selectedTagId} onClick={() => onSeleziona(t.id)} />
      ))}
    </>
  );
}

/* ── Una cartella: ordinabile con la maniglia, bersaglio per i tag ── */
function CartellaOrdinabile({
  riga, cartella, chiusa, onAlterna, evidenzia, selectedTagId, onSeleziona, onRinomina, onElimina,
}: {
  riga: RigaCartella;
  cartella: CartellaTag;
  chiusa: boolean;
  onAlterna: () => void;
  evidenzia: boolean;
  selectedTagId: number | null;
  onSeleziona: (id: number) => void;
  onRinomina: () => void;
  onElimina: () => void;
}) {
  const {
    attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging, isOver,
  } = useSortable({ id: idRiga(cartella.id), data: { tipo: "cartella" } });
  const sopra = isOver && evidenzia;
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={cn(
        "rounded-lg border p-1",
        isDragging ? "relative z-10 border-primary bg-card opacity-80 shadow-md"
          : sopra ? "border-primary bg-primary/5" : "border-transparent",
      )}
    >
      <div className="group/cartella flex min-w-0 items-center gap-0.5">
        {/* Maniglia e menu restano visibili anche senza passaggio del mouse: col
            dito non c'e' hover, e un comando invisibile non si trova. */}
        <Button
          ref={setActivatorNodeRef}
          variant="ghost"
          size="icon-xs"
          className="cursor-grab touch-none text-muted-foreground opacity-50 group-hover/cartella:opacity-100 focus-visible:opacity-100"
          aria-label={`Trascina per riordinare la cartella ${cartella.nome}`}
          title="Trascina per riordinare"
          {...attributes}
          {...listeners}
        >
          <GripVertical />
        </Button>
        <Button
          variant="ghost"
          size="icon-xs"
          className="text-muted-foreground aria-expanded:bg-transparent aria-expanded:text-muted-foreground hover:aria-expanded:bg-muted"
          aria-expanded={!chiusa}
          aria-label={chiusa ? `Apri la cartella ${cartella.nome}` : `Chiudi la cartella ${cartella.nome}`}
          onClick={onAlterna}
        >
          {chiusa ? <ChevronRight /> : <ChevronDown />}
        </Button>
        <Folder className="ml-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="ml-1.5 min-w-0 truncate text-xs font-semibold uppercase tracking-wide" title={cartella.nome}>
          {cartella.nome}
        </span>
        <span className="ml-1.5 shrink-0 text-xs tabular-nums text-muted-foreground">
          <span aria-hidden>{riga.tags.length}</span>
          <span className="sr-only">{riga.tags.length === 1 ? "1 tag" : `${riga.tags.length} tag`}</span>
        </span>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                size="icon-xs"
                className="ml-auto text-muted-foreground opacity-60 group-hover/cartella:opacity-100 focus-visible:opacity-100"
                aria-label={`Azioni sulla cartella ${cartella.nome}`}
                title="Rinomina o elimina la cartella"
              >
                <MoreHorizontal />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={onRinomina}>
              <Pencil />
              Rinomina
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onClick={onElimina}>
              <Trash2 />
              Elimina
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {!chiusa && (
        <div className="mt-0.5 space-y-0.5 pl-6">
          {riga.tags.length === 0
            ? <p className="rounded-md border border-dashed px-2.5 py-1.5 text-xs italic text-muted-foreground">Trascina qui un tag</p>
            : <TagDellaRiga riga={riga} selectedTagId={selectedTagId} onSeleziona={onSeleziona} />}
        </div>
      )}
    </div>
  );
}

/* ── «Senza cartella»: bersaglio per togliere un tag dalla sua cartella ── */
function GruppoSenzaCartella({
  riga, conEtichetta, attiva, evidenzia, selectedTagId, onSeleziona,
}: {
  riga: RigaCartella;
  conEtichetta: boolean;
  attiva: boolean;
  evidenzia: boolean;
  selectedTagId: number | null;
  onSeleziona: (id: number) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: idRiga(null), disabled: !attiva });
  const sopra = isOver && evidenzia;
  return (
    <div
      ref={setNodeRef}
      className={cn(
        "rounded-lg border p-1",
        sopra ? "border-primary bg-primary/5" : attiva && riga.tags.length === 0 ? "border-dashed border-border" : "border-transparent",
      )}
    >
      {conEtichetta && <p className="px-1.5 pb-1 pt-0.5 text-xs italic text-muted-foreground">Senza cartella</p>}
      <div className={cn("space-y-0.5", conEtichetta && "pl-6")}>
        {riga.tags.length === 0
          ? <p className="px-2.5 py-1.5 text-xs italic text-muted-foreground">Lascia qui per togliere il tag dalla cartella</p>
          : <TagDellaRiga riga={riga} selectedTagId={selectedTagId} onSeleziona={onSeleziona} />}
      </div>
    </div>
  );
}

/* ── Nome della cartella: «Nuova cartella» e «Rinomina» ── */
function DialogNomeCartella({
  stato, onChiudi, onSalva,
}: {
  stato: { open: boolean; cartella: CartellaTag | null };
  onChiudi: () => void;
  /** Ritorna il messaggio d'errore da mostrare, o null se e' andata. */
  onSalva: (nome: string, cartella: CartellaTag | null) => Promise<string | null>;
}) {
  const [nome, setNome] = useState("");
  const [errore, setErrore] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [aperturaVista, setAperturaVista] = useState<{ open: boolean; cartella: CartellaTag | null } | null>(null);

  if (stato !== aperturaVista) {
    setAperturaVista(stato);
    if (stato.open) {
      setNome(stato.cartella?.nome ?? "");
      setErrore("");
    }
  }

  async function conferma() {
    if (salvando) return;
    const n = nome.trim();
    if (!n) { setErrore("Il nome della cartella non può essere vuoto"); return; }
    if (stato.cartella && n === stato.cartella.nome) { onChiudi(); return; }
    setSalvando(true);
    try {
      const msg = await onSalva(n, stato.cartella);
      if (msg) setErrore(msg);
      else onChiudi();
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Dialog open={stato.open} onOpenChange={v => { if (!v && !salvando) onChiudi(); }}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>{stato.cartella ? "Rinomina cartella" : "Nuova cartella"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-1.5">
          <Input
            aria-label="Nome della cartella"
            placeholder="Nome della cartella, es. Pesce"
            value={nome}
            maxLength={60}
            autoFocus
            aria-invalid={errore ? true : undefined}
            onChange={e => { setNome(e.target.value); setErrore(""); }}
            onKeyDown={e => { if (e.key === "Enter" && !e.repeat) conferma(); }}
          />
          {errore && <p className="text-xs text-destructive" role="alert">{errore}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onChiudi} disabled={salvando}>Annulla</Button>
          <Button onClick={conferma} disabled={salvando || !nome.trim()}>
            {salvando ? "Salvataggio…" : stato.cartella ? "Rinomina" : "Crea cartella"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ══════════════════════════════════════════════════════════ PANNELLO */
// Il riquadro «I tuoi tag» (Fase 3, 13/10/2026): una scheda con bordo e titolo,
// non una fascia a tutta altezza, perche' accanto c'e' gia' il menu dell'app.
export function PannelloTag({
  tags, cartelle, setTags, setCartelle, vista, onVista, chiuse, onChiuse,
  selectedTagId, onSelezionaTag, onNuovoTag, onRicarica, info, suggerimenti,
}: {
  tags: CustomTag[];
  cartelle: CartellaTag[];
  setTags: Dispatch<SetStateAction<CustomTag[]>>;
  setCartelle: Dispatch<SetStateAction<CartellaTag[]>>;
  vista: VistaTag;
  onVista: (v: VistaTag) => void;
  chiuse: number[];
  onChiuse: (chiuse: number[]) => void;
  selectedTagId: number | null;
  onSelezionaTag: (id: number) => void;
  onNuovoTag: () => void;
  /** Rilegge tag e cartelle dal worker: dopo un conflitto lo stato locale non e' piu' affidabile. */
  onRicarica: () => void;
  /** Accanto al titolo (InfoPopover). */
  info?: ReactNode;
  /** In fondo al riquadro, sotto i tasti che creano (Suggerimenti). */
  suggerimenti?: ReactNode;
}) {
  const dndId = useId();
  const [trascinato, setTrascinato] = useState<Trascinato | null>(null);
  const [dialogNome, setDialogNome] = useState<{ open: boolean; cartella: CartellaTag | null }>({ open: false, cartella: null });
  const [daEliminare, setDaEliminare] = useState<CartellaTag | null>(null);
  // Un PUT /ordine alla volta: due riordini in volo insieme si intreccerebbero
  // sul worker, che scrive una cartella per volta.
  const codaRiordini = useRef<Promise<void>>(Promise.resolve());

  const trascinaTag = trascinato?.tipo === "tag";
  const righe = useMemo(
    () => raggruppa(tags, cartelle, { mostraSenzaCartella: trascinaTag }),
    [tags, cartelle, trascinaTag],
  );
  const preferiti = useMemo(() => soloPreferiti(tags), [tags]);
  const idsOrdinati = useMemo(() => ordinaCartelle(cartelle).map(c => c.id), [cartelle]);
  const chiuseSet = useMemo(() => new Set(chiuse), [chiuse]);

  const sensori = useSensors(
    // MouseSensor e non PointerSensor: il secondo scatta anche col dito dopo 6 px
    // e un trascinamento partirebbe da ogni scorrimento della pagina iniziato su
    // una riga. Col dito decide TouchSensor, dopo una pressione prolungata.
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const collisione: CollisionDetection = args => {
    if (args.active.data.current?.tipo === "tag") {
      const sotto = pointerWithin(args);
      return sotto.length > 0 ? sotto : rectIntersection(args);
    }
    return closestCenter({
      ...args,
      droppableContainers: args.droppableContainers.filter(c => typeof cartellaDaIdRiga(c.id) === "number"),
    });
  };

  function nomeDi(id: UniqueIdentifier): string {
    const tagId = tagDaIdTrascinabile(id);
    if (tagId !== undefined) return `il tag ${tags.find(t => t.id === tagId)?.nome ?? ""}`;
    const cartellaId = cartellaDaIdRiga(id);
    if (cartellaId === null) return "Senza cartella";
    return `la cartella ${cartelle.find(c => c.id === cartellaId)?.nome ?? ""}`;
  }

  const annunci: Announcements = {
    onDragStart: ({ active }) => `Hai preso ${nomeDi(active.id)}.`,
    onDragOver: ({ active, over }) =>
      over ? `${nomeDi(active.id)} è sopra ${nomeDi(over.id)}.` : `${nomeDi(active.id)} non è sopra nessuna cartella.`,
    onDragEnd: ({ active, over }) =>
      over ? `${nomeDi(active.id)} lasciato su ${nomeDi(over.id)}.` : `${nomeDi(active.id)} lasciato dov'era.`,
    onDragCancel: ({ active }) => `Spostamento di ${nomeDi(active.id)} annullato.`,
  };

  function inizioTrascinamento(e: DragStartEvent) {
    const tagId = tagDaIdTrascinabile(e.active.id);
    const tag = tagId !== undefined ? tags.find(t => t.id === tagId) : undefined;
    if (tag) { setTrascinato({ tipo: "tag", tag }); return; }
    const cartellaId = cartellaDaIdRiga(e.active.id);
    const cartella = typeof cartellaId === "number" ? cartelle.find(c => c.id === cartellaId) : undefined;
    setTrascinato(cartella ? { tipo: "cartella", cartella } : null);
  }

  function fineTrascinamento(e: DragEndEvent) {
    setTrascinato(null);
    const { active, over } = e;
    if (!over) return;
    const tagId = tagDaIdTrascinabile(active.id);
    if (tagId !== undefined) {
      const destinazione = cartellaDaIdRiga(over.id);
      if (destinazione !== undefined) spostaInCartella(tagId, destinazione);
      return;
    }
    const da = cartellaDaIdRiga(active.id);
    const a = cartellaDaIdRiga(over.id);
    if (typeof da === "number" && typeof a === "number" && da !== a) riordinaCartelle(da, a);
  }

  async function spostaInCartella(tagId: number, destinazione: number | null) {
    const tag = tags.find(t => t.id === tagId);
    if (!tag) return;
    const nota = tag.cartella_id != null && cartelle.some(c => c.id === tag.cartella_id);
    const attuale = nota ? (tag.cartella_id as number) : null;
    if (attuale === destinazione) return;
    setTags(ts => spostaTag(ts, tagId, destinazione));
    try {
      const res = await fetch(`/api/tag/${tagId}`, {
        method: "PATCH",
        headers: JSON_HEADERS,
        body: JSON.stringify({ cartella_id: destinazione }),
      });
      if (res.ok) return;
      if (res.status === 404) {
        toast.error("Il tag o la cartella non esistono più: ho ricaricato l'elenco");
        onRicarica();
        return;
      }
      throw new Error(messaggioErroreCartella(res.status, await dettaglio(res)));
    } catch (e) {
      // Indietro solo se nessun altro spostamento ha gia' cambiato il tag nel frattempo.
      setTags(ts => ts.map(t => (t.id === tagId && t.cartella_id === destinazione ? { ...t, cartella_id: attuale } : t)));
      toast.error(`Non sono riuscito a spostare il tag${e instanceof Error && e.message ? `: ${e.message}` : ""}`);
    }
  }

  function riordinaCartelle(da: number, a: number) {
    const precedenti = idsOrdinati;
    const nuovi = riordina(precedenti, da, a);
    setCartelle(cs => applicaOrdine(cs, nuovi));
    codaRiordini.current = codaRiordini.current.then(() => salvaOrdine(nuovi, precedenti));
  }

  async function salvaOrdine(nuovi: number[], precedenti: number[]) {
    try {
      const res = await fetch("/api/tag/cartelle/ordine", {
        method: "PUT",
        headers: JSON_HEADERS,
        body: JSON.stringify({ ids: nuovi }),
      });
      if (res.ok) return;
      const detail = await dettaglio(res);
      if (res.status === 409 || res.status === 404) {
        toast.error("Le cartelle erano cambiate nel frattempo: ho ricaricato l'elenco");
        onRicarica();
        return;
      }
      if (res.status === 502 && detail) {
        // Il worker ha scritto solo una parte dell'ordine: a video si mostra
        // quello che c'e' davvero sul DB, non quello di prima.
        toast.error(detail);
        onRicarica();
        return;
      }
      throw new Error(messaggioErroreCartella(res.status, detail));
    } catch (e) {
      // Indietro solo se a video c'e' ancora l'ordine di questo tentativo.
      setCartelle(cs => (stessoOrdine(cs, nuovi) ? applicaOrdine(cs, precedenti) : cs));
      toast.error(`Non sono riuscito a riordinare le cartelle${e instanceof Error && e.message ? `: ${e.message}` : ""}`);
    }
  }

  async function salvaNome(nome: string, cartella: CartellaTag | null): Promise<string | null> {
    if (nomeCartellaGiaUsato(cartelle, nome, cartella?.id)) return messaggioErroreCartella(409, "");
    try {
      const res = cartella
        ? await fetch(`/api/tag/cartelle/${cartella.id}`, { method: "PUT", headers: JSON_HEADERS, body: JSON.stringify({ nome }) })
        : await fetch("/api/tag/cartelle", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ nome }) });
      if (!res.ok) {
        if (res.status === 404) onRicarica();
        return messaggioErroreCartella(res.status, await dettaglio(res));
      }
      const d = await res.json().catch(() => null);
      const salvata: CartellaTag | null = d?.cartella ?? null;
      if (!salvata) {
        onRicarica();
        return null;
      }
      setCartelle(cs => (cartella ? cs.map(c => (c.id === salvata.id ? salvata : c)) : [...cs, salvata]));
      // Dalla vista Preferiti la cartella nuova non si vedrebbe: si mostra «Tutte».
      if (!cartella && vista === "preferiti") onVista("tutte");
      toast.success(cartella ? "Cartella rinominata" : "Cartella creata");
      return null;
    } catch {
      return "Il servizio non risponde, riprova fra poco";
    }
  }

  async function elimina(cartella: CartellaTag) {
    const dentro = tags.filter(t => t.cartella_id === cartella.id).map(t => t.id);
    setCartelle(cs => cs.filter(c => c.id !== cartella.id));
    setTags(ts => ts.map(t => (t.cartella_id === cartella.id ? { ...t, cartella_id: null } : t)));
    try {
      const res = await fetch(`/api/tag/cartelle/${cartella.id}`, { method: "DELETE" });
      if (res.ok || res.status === 404) {
        toast.success("Cartella eliminata: i suoi tag sono in Senza cartella");
        return;
      }
      throw new Error(messaggioErroreCartella(res.status, await dettaglio(res)));
    } catch (e) {
      setCartelle(cs => (cs.some(c => c.id === cartella.id) ? cs : [...cs, cartella]));
      setTags(ts => ts.map(t => (dentro.includes(t.id) && t.cartella_id == null ? { ...t, cartella_id: cartella.id } : t)));
      toast.error(`Non sono riuscito a eliminare la cartella${e instanceof Error && e.message ? `: ${e.message}` : ""}`);
    }
  }

  const ciSonoCartelle = cartelle.length > 0;

  return (
    <section aria-label="I tuoi tag" className="min-w-0 overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b px-4 py-3.5">
        <h2 className="flex items-center gap-1.5 text-base font-semibold">
          I tuoi tag
          {info}
        </h2>
        {tags.length > 0 && (
          <SegmentedControl
            aria-label="Quali tag mostrare"
            value={vista}
            onChange={onVista}
            options={[
              {
                value: "preferiti",
                label: <><Star className={vista === "preferiti" ? "fill-current" : "fill-incerto text-incerto"} /> Preferiti</>,
              },
              { value: "tutte", label: "Tutte" },
            ]}
          />
        )}
      </div>

      {/* Impilato sopra l'analisi (sotto i 1280 px) la lista ha un tetto, cosi'
          non spinge i numeri del tag fuori dallo schermo; a due colonne no. */}
      <div className="max-h-80 overflow-y-auto p-3 xl:max-h-none">
        {tags.length === 0 && cartelle.length === 0 ? (
          <p className="px-1.5 py-2 text-sm text-muted-foreground">Ancora nessun tag: crea il primo qui sotto.</p>
        ) : vista === "preferiti" && tags.length > 0 ? (
          <div className="space-y-0.5">
            {preferiti.length === 0 ? (
              <p className="px-1.5 py-2 text-sm text-muted-foreground">Nessun preferito: apri un tag e tocca la ☆</p>
            ) : (
              preferiti.map(t => (
                <RigaTag key={t.id} tag={t} attivo={t.id === selectedTagId} onClick={() => onSelezionaTag(t.id)} />
              ))
            )}
          </div>
        ) : (
          <DndContext
            id={dndId}
            sensors={sensori}
            collisionDetection={collisione}
            accessibility={{
              announcements: annunci,
              screenReaderInstructions: {
                draggable:
                  "Per riordinare una cartella premi Spazio o Invio sulla maniglia, spostala con le frecce e premi di nuovo Spazio o Invio per lasciarla. Esc annulla.",
              },
            }}
            onDragStart={inizioTrascinamento}
            onDragEnd={fineTrascinamento}
            onDragCancel={() => setTrascinato(null)}
          >
            <SortableContext items={idsOrdinati.map(id => idRiga(id))} strategy={verticalListSortingStrategy}>
              <div className="space-y-1.5">
                {righe.map(riga => {
                  const c = riga.cartella;
                  return c ? (
                    <CartellaOrdinabile
                      key={c.id}
                      riga={riga}
                      cartella={c}
                      chiusa={chiuseSet.has(c.id)}
                      onAlterna={() => onChiuse(alternaChiusa(chiuse, c.id))}
                      evidenzia={trascinaTag}
                      selectedTagId={selectedTagId}
                      onSeleziona={onSelezionaTag}
                      onRinomina={() => setDialogNome({ open: true, cartella: c })}
                      onElimina={() => setDaEliminare(c)}
                    />
                  ) : (
                    <GruppoSenzaCartella
                      key="senza"
                      riga={riga}
                      conEtichetta={ciSonoCartelle}
                      attiva={trascinaTag}
                      evidenzia={trascinaTag}
                      selectedTagId={selectedTagId}
                      onSeleziona={onSelezionaTag}
                    />
                  );
                })}
              </div>
            </SortableContext>
            <DragOverlay dropAnimation={null}>
              {trascinato?.tipo === "tag" ? (
                <div className="w-60 rounded-lg border bg-card shadow-md">
                  <RigaTag tag={trascinato.tag} attivo />
                </div>
              ) : null}
            </DragOverlay>
          </DndContext>
        )}
      </div>

      <div className="@container space-y-2 border-t bg-muted/40 p-3">
        {/* Affiancati solo se ci stanno interi: nel riquadro stretto «Nuova
            cartella» si troncava. */}
        <div className="grid grid-cols-1 gap-2 @sm:grid-cols-2">
          <Button variant="outline" className={CLASSE_CREA} onClick={onNuovoTag}>
            <TagIcon />
            <span className="flex-1 text-left">Nuovo tag</span>
            <Plus className="text-primary" aria-hidden />
          </Button>
          <Button variant="outline" className={CLASSE_CREA} onClick={() => setDialogNome({ open: true, cartella: null })}>
            <Folder />
            <span className="flex-1 text-left">Nuova cartella</span>
            <Plus className="text-primary" aria-hidden />
          </Button>
        </div>
        {suggerimenti}
      </div>

      <DialogNomeCartella
        stato={dialogNome}
        onChiudi={() => setDialogNome(d => ({ ...d, open: false }))}
        onSalva={salvaNome}
      />
      <ConfirmDialog
        open={daEliminare !== null}
        titolo={`Eliminare la cartella «${daEliminare?.nome ?? ""}»?`}
        messaggio="I tag della cartella restano e finiscono in Senza cartella."
        confermaLabel="Elimina cartella"
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </section>
  );
}
