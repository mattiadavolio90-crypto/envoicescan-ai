"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Pencil, Plus, X } from "lucide-react";
import { type Sede, type Settore, PIANO_COLOR, PIANO_LABEL, SETTORE_LABEL, SETTORE_OPTIONS } from "@/lib/admin";
import { RagioneSocialeClient } from "@/components/admin/ragione-sociale";
import { chiamaAdmin, messaggioErrore, type TabProps } from "./comune";

type Modulo = {
  nome: string;
  piva: string;
  ragione: string;
  indirizzo: string;
  cap: string;
  comune: string;
  piano: string;
  tipo: Settore;
};

const VUOTO: Modulo = { nome: "", piva: "", ragione: "", indirizzo: "", cap: "", comune: "", piano: "base", tipo: "ristorazione" };

function daSede(s: Sede): Modulo {
  return {
    nome: s.nome_ristorante || "",
    piva: s.partita_iva || "",
    ragione: s.ragione_sociale || "",
    indirizzo: s.indirizzo || "",
    cap: s.cap || "",
    comune: s.comune || "",
    piano: s.piano || "base",
    tipo: s.tipo_attivita ?? "ristorazione",
  };
}

function CampiSede({ m, set, settoreBloccato, notaSettore }: {
  m: Modulo;
  set: (m: Modulo) => void;
  settoreBloccato: boolean;
  notaSettore: string | null;
}) {
  return (
    <div className="space-y-3 py-2">
      <div className="space-y-1.5">
        <Label htmlFor="s-nome">Nome sede *</Label>
        <Input id="s-nome" placeholder="Es: Trattoria Mario 2" value={m.nome} onChange={(e) => set({ ...m, nome: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="s-piva">P.IVA * (11 cifre)</Label>
        <Input id="s-piva" placeholder="12345678901" maxLength={11} value={m.piva} onChange={(e) => set({ ...m, piva: e.target.value.replace(/\D/g, "") })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="s-ragione">Ragione sociale</Label>
        <Input id="s-ragione" placeholder="Opzionale" value={m.ragione} onChange={(e) => set({ ...m, ragione: e.target.value })} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="s-indirizzo">Indirizzo</Label>
        <Input id="s-indirizzo" placeholder="Via e numero civico" value={m.indirizzo} onChange={(e) => set({ ...m, indirizzo: e.target.value })} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="s-cap">CAP</Label>
          <Input id="s-cap" placeholder="00000" maxLength={10} value={m.cap} onChange={(e) => set({ ...m, cap: e.target.value })} />
        </div>
        <div className="col-span-2 space-y-1.5">
          <Label htmlFor="s-comune">Comune</Label>
          <Input id="s-comune" placeholder="Città" value={m.comune} onChange={(e) => set({ ...m, comune: e.target.value })} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="s-piano">Piano</Label>
        <NativeSelect id="s-piano" value={m.piano} onValueChange={(v) => set({ ...m, piano: v })}>
          <option value="free">Free (chat AI esclusa)</option>
          <option value="base">Base (50 fatture)</option>
          <option value="plus">Plus (100 fatture)</option>
          <option value="pro">Pro (200 fatture)</option>
        </NativeSelect>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="s-tipo">Settore</Label>
        <NativeSelect id="s-tipo" value={m.tipo} onValueChange={(v) => set({ ...m, tipo: v as Settore })} disabled={settoreBloccato}>
          {SETTORE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </NativeSelect>
        {notaSettore && <p className="text-xs text-muted-foreground">{notaSettore}</p>}
      </div>
      <p className="text-xs text-muted-foreground">
        Indirizzo, CAP e comune servono a smistare automaticamente le fatture quando più sedi condividono la stessa P.IVA. Il piano è per sede.
      </p>
    </div>
  );
}

type Mapping = { id: string; ragione_sociale: string; ristorante_id: string; created_at: string };

// Le ragioni sociali con cui le email dei gestionali di cassa arrivano, e la
// sede a cui vanno i loro ricavi. Prima stavano in Flusso dati → Mapping ricavi.
function MittentiRicavi({ sedi }: { sedi: Sede[] }) {
  const [mappe, setMappe] = useState<Mapping[] | null>(null);
  const [errore, setErrore] = useState(false);
  useEffect(() => {
    const ids = new Set(sedi.map((s) => s.id));
    fetch("/api/admin/ragione-sociale-map")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((tutte: Mapping[]) => setMappe(tutte.filter((m) => ids.has(m.ristorante_id))))
      .catch(() => setErrore(true));
  }, [sedi]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Ricavi dai gestionali di cassa</CardTitle>
        <p className="text-xs text-muted-foreground">
          La ragione sociale con cui arrivano le email del gestionale, e la sede a cui vanno gli incassi.
        </p>
      </CardHeader>
      <CardContent>
        {errore ? (
          <p className="text-sm text-muted-foreground">Non riesco a leggere i collegamenti dal server.</p>
        ) : mappe === null ? (
          <p className="text-sm text-muted-foreground">Caricamento…</p>
        ) : (
          <RagioneSocialeClient mappingsIniziali={mappe} sedi={sedi.map((s) => ({ id: s.id, label: s.nome_ristorante }))} />
        )}
      </CardContent>
    </Card>
  );
}

export function SediTab({ c, setC }: TabProps) {
  // In v1 le sedi di un account hanno lo stesso settore (lo impone il worker):
  // con almeno una sede il settore e' deciso, e i dialog lo mostrano bloccato.
  const settoreAccount: Settore | null = c.sedi.length > 0 ? (c.sedi[0].tipo_attivita ?? "ristorazione") : null;

  const [nuova, setNuova] = useState<Modulo | null>(null);
  const [inModifica, setInModifica] = useState<{ sede: Sede; m: Modulo } | null>(null);
  const [daEliminare, setDaEliminare] = useState<Sede | null>(null);
  const [occupato, setOccupato] = useState(false);
  const [sdiInCorso, setSdiInCorso] = useState<string | null>(null);

  async function crea() {
    if (!nuova) return;
    if (!nuova.nome.trim() || !nuova.piva.trim()) { toast.error("Nome e P.IVA obbligatori"); return; }
    setOccupato(true);
    try {
      const sede: Sede = await chiamaAdmin(`/api/admin/clienti/${c.id}/sedi`, "POST", {
        nome_ristorante: nuova.nome.trim(),
        partita_iva: nuova.piva.trim(),
        ragione_sociale: nuova.ragione.trim() || undefined,
        indirizzo: nuova.indirizzo.trim() || undefined,
        cap: nuova.cap.trim() || undefined,
        comune: nuova.comune.trim() || undefined,
        piano: nuova.piano,
        tipo_attivita: settoreAccount ?? nuova.tipo,
      });
      setC((prev) => ({ ...prev, sedi: [...prev.sedi, sede], n_sedi: prev.n_sedi + 1 }));
      toast.success("Sede creata");
      setNuova(null);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setOccupato(false);
    }
  }

  async function salvaModifica() {
    if (!inModifica) return;
    const { sede, m } = inModifica;
    if (!m.nome.trim() || !m.piva.trim()) { toast.error("Nome e P.IVA obbligatori"); return; }
    setOccupato(true);
    try {
      const aggiornata: Sede = await chiamaAdmin(`/api/admin/clienti/${c.id}/sedi/${sede.id}`, "PATCH", {
        nome_ristorante: m.nome.trim(),
        partita_iva: m.piva.trim(),
        ragione_sociale: m.ragione.trim() || null,
        indirizzo: m.indirizzo.trim() || null,
        cap: m.cap.trim() || null,
        comune: m.comune.trim() || null,
        piano: m.piano,
        tipo_attivita: m.tipo,
      });
      setC((prev) => ({ ...prev, sedi: prev.sedi.map((s) => (s.id === aggiornata.id ? { ...s, ...aggiornata } : s)) }));
      toast.success("Sede aggiornata");
      setInModifica(null);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setOccupato(false);
    }
  }

  async function elimina() {
    const sede = daEliminare;
    if (!sede) return;
    setOccupato(true);
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/sedi/${sede.id}`, "DELETE");
      setC((prev) => ({ ...prev, sedi: prev.sedi.filter((s) => s.id !== sede.id), n_sedi: prev.n_sedi - 1 }));
      toast.success("Sede eliminata");
      setDaEliminare(null);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setOccupato(false);
    }
  }

  async function cambiaSdi(sede: Sede) {
    const nuovo = !sede.sdi_attivo;
    setSdiInCorso(sede.id);
    try {
      const aggiornata: Sede = await chiamaAdmin(`/api/admin/clienti/${c.id}/sedi/${sede.id}`, "PATCH", { sdi_attivo: nuovo });
      setC((prev) => ({ ...prev, sedi: prev.sedi.map((s) => (s.id === aggiornata.id ? { ...s, ...aggiornata } : s)) }));
      toast.success(nuovo ? "Ricezione SDI attivata" : "Ricezione SDI disattivata");
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setSdiInCorso(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Sedi ({c.sedi.length})</CardTitle>
          <Button size="sm" variant="outline" onClick={() => setNuova({ ...VUOTO, tipo: settoreAccount ?? "ristorazione" })}>
            <Plus className="size-4 mr-1" /> Aggiungi sede
          </Button>
        </CardHeader>
        <CardContent>
          {c.sedi.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nessuna sede configurata</p>
          ) : (
            <div className="space-y-2">
              {c.sedi.map((sede) => {
                const ubicazione = [sede.indirizzo, sede.cap, sede.comune].filter(Boolean).join(" · ");
                return (
                  <div key={sede.id} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <p className="text-sm font-medium truncate">{sede.nome_ristorante}</p>
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold shrink-0 ${PIANO_COLOR[sede.piano || "base"] || ""}`}>
                          {PIANO_LABEL[sede.piano || "base"] || sede.piano}
                        </span>
                        {sede.tipo_attivita === "retail" && (
                          <span className="rounded-full px-1.5 py-0.5 text-[10px] font-semibold shrink-0 bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">
                            {SETTORE_LABEL.retail}
                          </span>
                        )}
                        {!sede.attivo && <span className="text-[10px] font-semibold text-red-600 shrink-0">Inattiva</span>}
                      </div>
                      <p className="text-xs text-muted-foreground tabular-nums">{sede.partita_iva || "—"}</p>
                      {ubicazione ? (
                        <p className="text-xs text-muted-foreground truncate">{ubicazione}</p>
                      ) : (
                        c.sedi.length > 1 && (
                          <p className="text-xs text-amber-600 truncate">⚠ Indirizzo mancante — smistamento fatture manuale</p>
                        )
                      )}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button
                        type="button"
                        onClick={() => cambiaSdi(sede)}
                        disabled={sdiInCorso === sede.id}
                        title={sede.sdi_attivo
                          ? "Ricezione SDI automatica ATTIVA — clic per disattivare"
                          : "Ricezione SDI automatica spenta — clic per attivare (caricamento manuale)"}
                        className={`rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors disabled:opacity-50 ${
                          sede.sdi_attivo
                            ? "bg-emerald-500/15 text-emerald-700 hover:bg-emerald-500/25"
                            : "bg-muted text-muted-foreground hover:bg-border"
                        }`}
                      >
                        {sede.sdi_attivo ? "SDI attivo" : "SDI spento"}
                      </button>
                      <Button size="sm" variant="ghost" className="size-7 p-0 text-muted-foreground hover:text-foreground"
                        onClick={() => setInModifica({ sede, m: daSede(sede) })} title="Modifica sede" aria-label="Modifica sede">
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button size="sm" variant="ghost" className="size-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => setDaEliminare(sede)} title="Elimina sede" aria-label="Elimina sede">
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>

        <Dialog open={nuova !== null} onOpenChange={(o) => !o && setNuova(null)}>
          <DialogContent className="max-w-sm">
            <DialogHeader><DialogTitle>Aggiungi sede</DialogTitle></DialogHeader>
            {nuova && (
              <CampiSede
                m={settoreAccount ? { ...nuova, tipo: settoreAccount } : nuova}
                set={setNuova}
                settoreBloccato={settoreAccount !== null}
                notaSettore={settoreAccount !== null ? "Le sedi di un account hanno lo stesso settore: un ristorante e un negozio sono due account." : null}
              />
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setNuova(null)} disabled={occupato}>Annulla</Button>
              <Button onClick={crea} disabled={occupato || !nuova?.nome.trim() || !nuova?.piva.trim()}>
                {occupato ? "Creazione…" : "Crea sede"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={inModifica !== null} onOpenChange={(o) => !o && setInModifica(null)}>
          <DialogContent className="max-w-sm">
            <DialogHeader><DialogTitle>Modifica sede</DialogTitle></DialogHeader>
            {inModifica && (
              <CampiSede
                m={inModifica.m}
                set={(m) => setInModifica({ ...inModifica, m })}
                settoreBloccato={c.sedi.length > 1}
                notaSettore={c.sedi.length > 1 ? "Con più sedi il settore non si cambia da qui: le sedi di un account hanno lo stesso settore." : null}
              />
            )}
            <DialogFooter>
              <Button variant="outline" onClick={() => setInModifica(null)} disabled={occupato}>Annulla</Button>
              <Button onClick={salvaModifica} disabled={occupato || !inModifica?.m.nome.trim() || !inModifica?.m.piva.trim()}>
                {occupato ? "Salvataggio…" : "Salva modifiche"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={daEliminare !== null} onOpenChange={(o) => !o && setDaEliminare(null)}>
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle className="text-destructive">Elimina sede</DialogTitle>
              <DialogDescription>
                Stai per eliminare la sede <strong>{daEliminare?.nome_ristorante}</strong>.
                Tutte le sue fatture verranno eliminate. Azione irreversibile.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="outline" onClick={() => setDaEliminare(null)} disabled={occupato}>Annulla</Button>
              <Button variant="destructive" onClick={elimina} disabled={occupato}>
                {occupato ? "Eliminazione…" : "Elimina sede"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </Card>
      {c.sedi.length > 0 && <MittentiRicavi sedi={c.sedi} />}
    </div>
  );
}
