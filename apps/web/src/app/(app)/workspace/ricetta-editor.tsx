"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Plus, Trash2, Search } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import {
  CATEGORIE_RICETTE, FC_BADGE_CLASS, fmtEuro, fmtPct,
  type RicettaDettaglio, type RigaRicetta, type Ingrediente, type IngredientiResponse,
} from "@/lib/foodcost";

const UM_LIST = ["G", "KG", "ML", "CL", "LT", "PZ"];
const IVA = 0.10;

interface Props {
  open: boolean;
  ricetta?: RicettaDettaglio | null;
  onClose: () => void;
  onSaved: () => void;
}

interface RigaUI extends RigaRicetta {
  _key: number;
  costo: number;
}

let _keyCounter = 0;
function newKey() { return ++_keyCounter; }

function initRiga(r: RigaRicetta): RigaUI {
  return { ...r, _key: newKey(), costo: r.costo ?? 0 };
}

export function RicettaEditor({ open, ricetta, onClose, onSaved }: Props) {
  const isNew = !ricetta;

  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState<string>("ANTIPASTI");
  const [prezzoVendita, setPrezzoVendita] = useState("");
  const [righe, setRighe] = useState<RigaUI[]>([]);
  const [fcTotale, setFcTotale] = useState(0);
  const [saving, setSaving] = useState(false);

  // selettore ingredienti
  const [ingredienti, setIngredienti] = useState<IngredientiResponse | null>(null);
  const [searchIng, setSearchIng] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // calcolo live debounced
  const calcTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    if (isNew) {
      setNome(""); setCategoria("ANTIPASTI"); setPrezzoVendita(""); setRighe([]); setFcTotale(0);
    } else if (ricetta) {
      setNome(ricetta.nome);
      setCategoria(ricetta.categoria);
      setPrezzoVendita(ricetta.prezzo_vendita_ivainc ? String(ricetta.prezzo_vendita_ivainc) : "");
      setRighe((ricetta.righe ?? []).map(initRiga));
      setFcTotale(ricetta.foodcost_totale);
    }
    setSearchIng("");
    loadIngredienti();
  }, [open, ricetta?.id]);

  async function loadIngredienti() {
    try {
      const res = await fetch("/api/workspace/foodcost/ingredienti");
      const data: IngredientiResponse = await res.json();
      setIngredienti(data);
    } catch {
      toast.error("Errore caricamento ingredienti");
    }
  }

  // Ingredienti filtrati per ricerca
  const tuttiIngredienti: Ingrediente[] = ingredienti
    ? [...ingredienti.articoli, ...ingredienti.manuali, ...ingredienti.semilavorati]
    : [];

  const filtrati = searchIng.trim()
    ? tuttiIngredienti.filter(i => i.nome.toLowerCase().includes(searchIng.toLowerCase()))
    : tuttiIngredienti;

  function labelIngrediente(ing: Ingrediente): string {
    if (ing.tipo === "articolo") {
      const gram = ing.grammatura_str ? ` · ${ing.grammatura_str}` : "";
      return `${ing.nome}  €${ing.prezzo_unitario.toFixed(2)}/${ing.um}${gram}`;
    }
    if (ing.tipo === "manuale") return `${ing.nome}  €${ing.prezzo_unitario.toFixed(2)}/${ing.um} · manuale`;
    return `${ing.nome}  €${ing.foodcost_ricetta.toFixed(2)} · semilavorato`;
  }

  function aggiungiIngrediente(ing: Ingrediente) {
    const riga: RigaUI = {
      _key: newKey(),
      nome: ing.nome,
      tipo: ing.tipo,
      quantita: 0,
      um: ing.tipo === "semilavorato" ? "PZ" : (ing.tipo === "articolo" ? (ing.um === "KG" || ing.um === "LT" ? (ing.um === "KG" ? "G" : "ML") : ing.um) : ing.um),
      um_db: ing.tipo !== "semilavorato" ? ing.um : undefined,
      prezzo_unitario: ing.tipo !== "semilavorato" ? ing.prezzo_unitario : undefined,
      grammatura_confezione: ing.tipo === "articolo" ? ing.grammatura_confezione : undefined,
      grammatura_um: ing.tipo === "articolo" ? ing.grammatura_um : undefined,
      foodcost_ricetta: ing.tipo === "semilavorato" ? ing.foodcost_ricetta : undefined,
      costo: 0,
    };
    const nuove = [...righe, riga];
    setRighe(nuove);
    setDropdownOpen(false);
    setSearchIng("");
    triggerCalcolo(nuove);
  }

  function aggiornaRiga(key: number, campo: Partial<RigaUI>) {
    const nuove = righe.map(r => r._key === key ? { ...r, ...campo } : r);
    setRighe(nuove);
    triggerCalcolo(nuove);
  }

  function rimuoviRiga(key: number) {
    const nuove = righe.filter(r => r._key !== key);
    setRighe(nuove);
    triggerCalcolo(nuove);
  }

  const triggerCalcolo = useCallback((righeCorrente: RigaUI[]) => {
    if (calcTimer.current) clearTimeout(calcTimer.current);
    calcTimer.current = setTimeout(() => calcolaLive(righeCorrente), 300);
  }, []);

  async function calcolaLive(righeCorrente: RigaUI[]) {
    if (!righeCorrente.length) { setFcTotale(0); return; }
    try {
      const payload = righeCorrente.map(r => ({
        tipo: r.tipo,
        prezzo_unitario: r.prezzo_unitario ?? 0,
        um_db: r.um_db ?? r.um,
        quantita: r.quantita,
        um: r.um,
        grammatura_confezione: r.grammatura_confezione ?? null,
        grammatura_um: r.grammatura_um ?? null,
        prezzo_override: r.prezzo_override ?? null,
        foodcost_ricetta: r.foodcost_ricetta ?? null,
      }));
      const res = await fetch("/api/workspace/foodcost/calcola", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ righe: payload }),
      });
      const data = await res.json();
      setFcTotale(data.foodcost_totale ?? 0);
      setRighe(prev => prev.map((r, i) => ({ ...r, costo: data.costi_righe?.[i] ?? 0 })));
    } catch {
      // calcolo live silente — non blocca il salvataggio
    }
  }

  async function handleSalva() {
    if (!nome.trim()) { toast.error("Inserisci il nome della ricetta"); return; }
    setSaving(true);
    try {
      const payload = {
        nome: nome.trim(),
        categoria,
        prezzo_vendita_ivainc: prezzoVendita ? parseFloat(prezzoVendita) : null,
        righe: righe.map(({ _key, costo, ...r }) => r),
      };
      const url = isNew
        ? "/api/workspace/foodcost/ricette"
        : `/api/workspace/foodcost/ricette/${ricetta!.id}`;
      const method = isNew ? "POST" : "PATCH";
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error();
      toast.success(isNew ? "Ricetta salvata" : "Ricetta aggiornata");
      onSaved();
      onClose();
    } catch {
      toast.error("Errore salvataggio");
    } finally {
      setSaving(false);
    }
  }

  const prezzo = prezzoVendita ? parseFloat(prezzoVendita) : null;
  const prezzoNetto = prezzo ? prezzo / (1 + IVA) : null;
  const margine = prezzoNetto !== null ? prezzoNetto - fcTotale : null;
  const incidenza = (prezzoNetto && prezzoNetto > 0) ? (fcTotale / prezzoNetto) * 100 : null;
  const colore = incidenza === null ? "grigio" : incidenza <= 30 ? "verde" : incidenza <= 40 ? "ambra" : "rosso";

  // chiudi dropdown cliccando fuori
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Classe comune per i <select> nativi — focus ring blu coerente con Input
  const selectCls = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500";
  const selectSmCls = "h-8 w-full rounded-md border border-input bg-background px-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500";

  return (
    <Dialog open={open} onOpenChange={o => { if (!o) onClose(); }}>
      <DialogContent className="w-full sm:max-w-4xl gap-5 max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isNew ? "Nuova ricetta" : `Modifica — ${ricetta?.nome}`}</DialogTitle>
        </DialogHeader>

        {/* Riga 1: Nome ricetta — full width */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium">Nome ricetta *</Label>
          <Input
            placeholder="es. Pizza Margherita, Besciamella, Ragù bolognese…"
            value={nome}
            onChange={e => setNome(e.target.value)}
            className="h-10 focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          />
        </div>

        {/* Riga 2: Categoria + Prezzo vendita — stessa altezza label */}
        <div className="grid grid-cols-2 gap-5">
          <div className="space-y-1.5">
            <Label className="text-sm font-medium whitespace-nowrap">Categoria</Label>
            <select
              value={categoria}
              onChange={e => setCategoria(e.target.value)}
              className={selectCls}
            >
              {CATEGORIE_RICETTE.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-sm font-medium whitespace-nowrap">Prezzo di vendita (IVA 10% inclusa)</Label>
            <Input
              type="number"
              placeholder="0.00"
              min="0"
              step="0.50"
              value={prezzoVendita}
              onChange={e => setPrezzoVendita(e.target.value)}
              className="h-10 focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
        </div>

        {categoria === "SEMILAVORATI" && (
          <p className="text-xs text-sky-600 dark:text-sky-400 -mt-2">
            I semilavorati possono essere usati come ingredienti in altre ricette.
          </p>
        )}

        {/* Selettore ingrediente */}
        <div className="space-y-1.5">
          <Label className="text-sm font-medium">Aggiungi ingrediente</Label>
          <div className="relative" ref={dropdownRef}>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
              <Input
                className="h-10 pl-9 focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                placeholder="Cerca tra le fatture, ingredienti manuali o semilavorati…"
                value={searchIng}
                onChange={e => { setSearchIng(e.target.value); setDropdownOpen(true); }}
                onFocus={() => setDropdownOpen(true)}
              />
            </div>
            {dropdownOpen && (
              <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-lg max-h-56 overflow-y-auto">
                {filtrati.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-muted-foreground">Nessun risultato</p>
                ) : (
                  filtrati.slice(0, 80).map((ing, idx) => (
                    <button
                      key={`${ing.tipo}-${ing.nome}-${idx}`}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center gap-2"
                      onClick={() => aggiungiIngrediente(ing)}
                    >
                      <span className="shrink-0 text-xs">
                        {ing.tipo === "articolo" ? "🟢" : ing.tipo === "manuale" ? "📝" : "🥘"}
                      </span>
                      <span className="truncate">{labelIngrediente(ing)}</span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
        </div>

        {/* Tabella ingredienti */}
        {righe.length > 0 && (
          <div className="rounded-md border border-border overflow-x-hidden">
            <table className="w-full text-sm table-fixed">
              <colgroup>
                <col className="w-[35%]" />
                <col className="w-[15%]" />
                <col className="w-[14%]" />
                <col className="w-[18%]" />
                <col className="w-[12%]" />
                <col className="w-[6%]" />
              </colgroup>
              <thead className="bg-muted/50">
                <tr>
                  <th className="text-left px-3 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Ingrediente</th>
                  <th className="text-center px-2 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Quantità</th>
                  <th className="text-center px-2 py-2.5 font-medium text-muted-foreground whitespace-nowrap">UM</th>
                  <th className="text-center px-2 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Gram. conf.</th>
                  <th className="text-right px-2 py-2.5 font-medium text-muted-foreground whitespace-nowrap">Costo</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {righe.map(r => (
                  <tr key={r._key}>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="text-xs shrink-0">
                          {r.tipo === "articolo" ? "🟢" : r.tipo === "manuale" ? "📝" : "🥘"}
                        </span>
                        <span className="truncate" title={r.nome}>{r.nome}</span>
                      </div>
                    </td>
                    <td className="px-2 py-2">
                      <Input
                        type="number"
                        min="0"
                        step="1"
                        value={r.quantita || ""}
                        onChange={e => aggiornaRiga(r._key, { quantita: parseFloat(e.target.value) || 0 })}
                        className="h-8 text-right text-sm w-full focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                      />
                    </td>
                    <td className="px-2 py-2">
                      <select
                        value={r.um}
                        onChange={e => aggiornaRiga(r._key, { um: e.target.value })}
                        className={selectSmCls}
                        disabled={r.tipo === "semilavorato"}
                      >
                        {UM_LIST.map(u => <option key={u} value={u}>{u}</option>)}
                      </select>
                    </td>
                    <td className="px-2 py-2">
                      {r.tipo === "articolo" ? (
                        <Input
                          type="number"
                          min="0"
                          placeholder={r.grammatura_confezione ? String(r.grammatura_confezione) : "—"}
                          value={r.grammatura_confezione ?? ""}
                          onChange={e => aggiornaRiga(r._key, { grammatura_confezione: parseFloat(e.target.value) || null })}
                          className="h-8 text-right text-sm w-full focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                          title="Grammatura confezione in g/ml"
                        />
                      ) : (
                        <span className="text-muted-foreground text-center block">—</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right font-medium">
                      {r.costo > 0 ? fmtEuro(r.costo) : <span className="text-muted-foreground">—</span>}
                    </td>
                    <td className="px-1 py-1.5 text-center">
                      <Button size="icon" variant="ghost" className="size-7 text-muted-foreground hover:text-destructive"
                        onClick={() => rimuoviRiga(r._key)}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {righe.length === 0 && (
          <div className="rounded-md border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            Cerca e aggiungi ingredienti dalla barra sopra.
          </div>
        )}

        {/* Totali */}
        <div className={`flex flex-wrap items-center gap-4 rounded-lg border px-4 py-3 ${FC_BADGE_CLASS[colore]}`}>
          <span className="text-sm">Foodcost: <strong>{fmtEuro(fcTotale)}</strong></span>
          {margine !== null && <span className="text-sm">Margine: <strong>{fmtEuro(margine)}</strong></span>}
          {incidenza !== null && <span className="text-sm">Incidenza FC: <strong>{fmtPct(incidenza)}</strong></span>}
          {incidenza === null && fcTotale > 0 && (
            <span className="text-xs ml-auto">Imposta il prezzo di vendita per vedere margine e incidenza%</span>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>Annulla</Button>
          <Button onClick={handleSalva} disabled={saving}>
            {saving ? "Salvataggio…" : isNew ? "Crea ricetta" : "Salva modifiche"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
