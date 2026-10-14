"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { AlertTriangle, ArrowRightLeft, Check, CheckCircle, ChevronDown, RefreshCw, Search, Trash2 } from "lucide-react";
import { CATEGORIE_TUTTE } from "@/lib/admin";
import { formatEuro } from "@/lib/format";
import {
  DA_CLASSIFICARE, esitoClassifica, filtra, leggiDaSistemare, puoConfermare, riepilogo, rigaSotto, toglieGruppo,
  type DatiDaSistemare, type GruppoDaSistemare,
} from "@/lib/admin-categorie";

async function chiama(url: string, method: string, body?: object) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const d = await res.json().catch(() => ({}));
  if (!res.ok || d?.ok === false) throw new Error(d.detail || d.error || "Errore");
  return d;
}

type Esito = { chiave: string; scritte: number; chieste: number; logId: number | null };

// ─── Da sistemare ────────────────────────────────────────────────────────────
function DaSistemare() {
  const [dati, setDati] = useState<DatiDaSistemare | null>(null);
  const [errore, setErrore] = useState(false);
  const [caricamento, setCaricamento] = useState(true);
  const [cliente, setCliente] = useState("tutti");
  const [testo, setTesto] = useState("");
  const [scelti, setScelti] = useState<Set<string>>(new Set());
  const [occupato, setOccupato] = useState(false);
  const [daCambiare, setDaCambiare] = useState<GruppoDaSistemare[] | null>(null);
  const [categoriaNuova, setCategoriaNuova] = useState("");
  const [confermaBlocco, setConfermaBlocco] = useState(false);

  const carica = useCallback(async () => {
    setCaricamento(true);
    try {
      const res = await fetch("/api/admin/categorie/da-sistemare", { cache: "no-store" });
      const letto = leggiDaSistemare(await res.json().catch(() => null));
      if (!res.ok || !letto) { setErrore(true); return; }
      setDati(letto);
      setErrore(false);
      setScelti(new Set());
    } catch {
      setErrore(true);
    } finally {
      setCaricamento(false);
    }
  }, []);

  useEffect(() => { carica(); }, [carica]);

  const visibili = useMemo(() => (dati ? filtra(dati.gruppi, cliente, testo) : []), [dati, cliente, testo]);
  const sceltiVisibili = visibili.filter((g) => scelti.has(g.chiave));
  const confermabili = sceltiVisibili.filter(puoConfermare);
  const totali = riepilogo(visibili);

  async function annulla(logIds: number[]) {
    try {
      for (const id of logIds) await chiama("/api/admin/qualita-ai/audit/annulla", "POST", { log_id: id });
      toast.success("Annullato");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
    carica();
  }

  // Una chiamata per gruppo: la memoria globale si salva per descrizione.
  async function salva(gruppi: GruppoDaSistemare[], categoria: string | null) {
    setOccupato(true);
    const esiti: Esito[] = [];
    let errori = 0;
    for (const g of gruppi) {
      try {
        const d = await chiama("/api/admin/qualita-ai/coda/classifica", "POST", {
          ids: g.ids, categoria: categoria ?? g.categoria, salva_memoria: true,
        });
        esiti.push({ chiave: g.chiave, scritte: d.righe_aggiornate ?? 0, chieste: g.ids.length, logId: d.log_id ?? null });
      } catch (e) {
        errori++;
        if (gruppi.length === 1) toast.error(e instanceof Error ? e.message : "Errore");
      }
    }
    setOccupato(false);
    setScelti(new Set());
    if (esiti.length === 0) return;

    const scritte = esiti.reduce((s, e) => s + e.scritte, 0);
    const chieste = esiti.reduce((s, e) => s + e.chieste, 0);
    const logIds = esiti.map((e) => e.logId).filter((i): i is number => i !== null);
    toast.success(
      esitoClassifica(scritte, chieste) + (errori ? ` · ${errori} non salvat${errori === 1 ? "o" : "i"}` : ""),
      logIds.length ? { action: { label: "Annulla", onClick: () => annulla(logIds) } } : undefined,
    );
    if (esiti.every((e) => toglieGruppo(e.scritte, e.chieste)) && !errori) {
      const via = new Set(esiti.map((e) => e.chiave));
      setDati((prima) => prima && { ...prima, gruppi: prima.gruppi.filter((g) => !via.has(g.chiave)) });
    } else {
      carica();
    }
  }

  function apriCambia(gruppi: GruppoDaSistemare[]) {
    const unico = gruppi.length === 1 ? gruppi[0] : null;
    setCategoriaNuova(unico ? (unico.suggerita ?? (unico.categoria !== DA_CLASSIFICARE ? unico.categoria : "")) : "");
    setDaCambiare(gruppi);
  }

  function seleziona(chiave: string) {
    setScelti((prima) => {
      const dopo = new Set(prima);
      if (dopo.has(chiave)) dopo.delete(chiave); else dopo.add(chiave);
      return dopo;
    });
  }

  if (errore && !dati) {
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-incerto/40 bg-incerto/10 p-4 text-sm">
        <span className="flex items-center gap-2"><AlertTriangle className="size-4 text-incerto" /> Non riesco a leggere le righe da sistemare.</span>
        <Button size="sm" variant="outline" onClick={carica} disabled={caricamento}><RefreshCw className="size-4 mr-1" /> Riprova</Button>
      </div>
    );
  }
  if (!dati) return <p className="text-sm text-muted-foreground">Caricamento…</p>;

  const tutti = visibili.length > 0 && sceltiVisibili.length === visibili.length;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Da sistemare</h2>
          <p className="text-sm text-muted-foreground">
            {totali.gruppi} prodott{totali.gruppi === 1 ? "o" : "i"} · {totali.righe} righe · {formatEuro(totali.euro)}. Ogni scelta vale per tutti i clienti.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Cerca prodotto o fornitore" className="w-56 pl-8" value={testo} onChange={(e) => setTesto(e.target.value)} />
          </div>
          <NativeSelect value={cliente} onValueChange={setCliente} className="w-44" aria-label="Cliente">
            <option value="tutti">Tutti i clienti</option>
            {dati.clienti.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </NativeSelect>
          <Button variant="ghost" size="sm" onClick={carica} disabled={caricamento}>
            <RefreshCw className={`size-4 mr-1 ${caricamento ? "animate-spin" : ""}`} /> Aggiorna
          </Button>
        </div>
      </div>

      {sceltiVisibili.length > 0 && (
        <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-2 text-sm shadow-sm">
          <span className="px-1 font-medium">{sceltiVisibili.length} selezionat{sceltiVisibili.length === 1 ? "o" : "i"}</span>
          <Button size="sm" disabled={occupato || confermabili.length === 0} onClick={() => setConfermaBlocco(true)}>
            <Check className="size-4 mr-1" /> Giuste ({confermabili.length})
          </Button>
          <Button size="sm" variant="outline" disabled={occupato} onClick={() => apriCambia(sceltiVisibili)}>Cambia categoria…</Button>
          <Button size="sm" variant="ghost" onClick={() => setScelti(new Set())}>Deseleziona</Button>
        </div>
      )}

      {visibili.length === 0 ? (
        <div className="flex items-center gap-2 rounded-md border border-positivo/30 bg-positivo/10 p-4 text-sm">
          <CheckCircle className="size-4 text-positivo" />
          {dati.gruppi.length === 0 ? "Tutto a posto: nessuna categoria da sistemare." : "Nessun prodotto con questo filtro."}
        </div>
      ) : (
        <div className="rounded-lg border">
          <label className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            <input type="checkbox" checked={tutti} onChange={() => setScelti(tutti ? new Set() : new Set(visibili.map((g) => g.chiave)))} />
            Seleziona tutti
          </label>
          <ul className="divide-y">
            {visibili.map((g) => {
              const misto = g.categorie.length > 1;
              return (
                <li key={g.chiave} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center">
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    <input type="checkbox" className="mt-1" checked={scelti.has(g.chiave)} onChange={() => seleziona(g.chiave)} aria-label={`Seleziona ${g.descrizione}`} />
                    <div className="min-w-0 space-y-1">
                      <p className="truncate text-sm font-medium" title={g.descrizione}>{g.descrizione}</p>
                      <p className="truncate text-xs text-muted-foreground" title={rigaSotto(g)}>{rigaSotto(g)}</p>
                      <div className="flex flex-wrap items-center gap-1.5 text-xs">
                        {misto ? (
                          <span className="rounded-full bg-incerto/10 px-2 py-0.5 font-medium text-incerto" title={g.categorie.join(", ")}>
                            {g.categorie.length} categorie diverse
                          </span>
                        ) : (
                          <span className={`rounded-full px-2 py-0.5 font-medium ${g.categoria === DA_CLASSIFICARE ? "bg-negativo/10 text-negativo" : "bg-muted"}`}>
                            {g.categoria === DA_CLASSIFICARE ? "Da classificare" : g.categoria}
                          </span>
                        )}
                        {g.suggerita && <span className="text-muted-foreground">suggerita: <b className="font-medium text-foreground">{g.suggerita}</b></span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 pl-7 sm:pl-0">
                    <span className="w-20 text-right text-sm tabular-nums">{formatEuro(g.euro)}</span>
                    {g.suggerita ? (
                      <Button size="sm" variant="outline" disabled={occupato} onClick={() => salva([g], g.suggerita)}>Usa suggerita</Button>
                    ) : puoConfermare(g) ? (
                      <Button size="sm" variant="outline" disabled={occupato} onClick={() => salva([g], null)}><Check className="size-4 mr-1" /> Giusta</Button>
                    ) : null}
                    <Button size="sm" variant="ghost" disabled={occupato} onClick={() => apriCambia([g])}>Cambia</Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <Dialog open={daCambiare !== null} onOpenChange={(o) => { if (!o) setDaCambiare(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Scegli la categoria</DialogTitle>
            <DialogDescription className="break-words">
              {daCambiare?.length === 1
                ? `${daCambiare[0].descrizione} · ${rigaSotto(daCambiare[0])}`
                : `${daCambiare?.length ?? 0} prodotti selezionati`}
            </DialogDescription>
          </DialogHeader>
          <NativeSelect value={categoriaNuova} onValueChange={setCategoriaNuova} placeholder="Seleziona la categoria…">
            {CATEGORIE_TUTTE.map((c) => <option key={c} value={c}>{c}</option>)}
          </NativeSelect>
          <p className="text-xs text-muted-foreground">Vale per tutti i clienti: finisce nella memoria globale.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDaCambiare(null)}>Annulla</Button>
            <Button disabled={!categoriaNuova || occupato} onClick={() => {
              const gruppi = daCambiare ?? [];
              setDaCambiare(null);
              salva(gruppi, categoriaNuova);
            }}>Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confermaBlocco}
        titolo={`Confermare la categoria di ${confermabili.length} prodott${confermabili.length === 1 ? "o" : "i"}?`}
        messaggio="Ognuno tiene la categoria che ha, e la scelta vale per tutti i clienti. Quelli da classificare o con categorie diverse restano in lista."
        confermaLabel="Conferma"
        onConferma={() => salva(confermabili, null)}
        onClose={() => setConfermaBlocco(false)}
      />
    </section>
  );
}

// ─── Conflitti ───────────────────────────────────────────────────────────────
type Conflitto = { local_id: string; descrizione: string; categoria_locale: string; categoria_globale: string; nome_cliente: string; volte_locale: number };

function Conflitti() {
  const [righe, setRighe] = useState<Conflitto[] | null>(null);
  const [aperto, setAperto] = useState(false);
  const [occupato, setOccupato] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/admin/qualita-ai/conflitti", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setRighe(Array.isArray(d) ? d : null))
      .catch(() => setRighe(null));
  }, []);

  async function risolvi(c: Conflitto, azione: "promuovi" | "ignora") {
    setOccupato(c.local_id);
    try {
      await chiama("/api/admin/qualita-ai/conflitti/risolvi", "POST", { local_id: c.local_id, azione });
      toast.success(azione === "promuovi" ? "Ora vale per tutti i clienti" : "Resta solo per questo cliente");
      setRighe((prima) => prima && prima.filter((x) => x.local_id !== c.local_id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setOccupato(null);
    }
  }

  if (!righe || righe.length === 0) return null;

  return (
    <section className="rounded-lg border">
      <button type="button" onClick={() => setAperto((a) => !a)} aria-expanded={aperto}
        className="flex w-full items-center justify-between gap-3 p-3 text-left">
        <span className="flex items-center gap-2">
          <ArrowRightLeft className="size-4 text-incerto" />
          <span>
            <span className="text-sm font-semibold">Conflitti con la memoria globale ({righe.length})</span>
            <span className="block text-xs text-muted-foreground">Un cliente ha scelto una categoria diversa da quella che vale per tutti.</span>
          </span>
        </span>
        <ChevronDown className={`size-4 shrink-0 transition-transform ${aperto ? "rotate-180" : ""}`} />
      </button>
      {aperto && (
        <ul className="max-h-[28rem] divide-y overflow-y-auto border-t">
          {righe.map((c) => (
            <li key={c.local_id} className="flex flex-col gap-2 p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <p className="truncate font-medium" title={c.descrizione}>{c.descrizione}</p>
                <p className="text-xs text-muted-foreground">
                  {c.nome_cliente}: <b className="font-medium text-foreground">{c.categoria_locale}</b> · per tutti: {c.categoria_globale}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                <Button size="sm" variant="outline" disabled={occupato === c.local_id} onClick={() => risolvi(c, "promuovi")}>Vale per tutti</Button>
                <Button size="sm" variant="ghost" disabled={occupato === c.local_id} onClick={() => risolvi(c, "ignora")}>Solo sua</Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

// ─── Memoria globale: si cerca, non si sfoglia ───────────────────────────────
type VoceMemoria = { id: string; descrizione: string; categoria: string; volte_visto: number };

function Memoria() {
  const [testo, setTesto] = useState("");
  const [voci, setVoci] = useState<VoceMemoria[] | null>(null);
  const [modifica, setModifica] = useState<VoceMemoria | null>(null);
  const [categoria, setCategoria] = useState("");
  const [daEliminare, setDaEliminare] = useState<VoceMemoria | null>(null);

  useEffect(() => {
    const cerca = testo.trim();
    if (cerca.length < 2) { setVoci(null); return; }
    const t = setTimeout(async () => {
      try {
        const qs = new URLSearchParams({ stato: "tutti", page: "1", per_page: "50", search: cerca });
        const res = await fetch(`/api/admin/qualita-ai/memoria?${qs}`, { cache: "no-store" });
        const d = await res.json().catch(() => ({}));
        setVoci(res.ok && Array.isArray(d.rows) ? d.rows : []);
      } catch {
        setVoci([]);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [testo]);

  async function salva() {
    if (!modifica || !categoria) return;
    const voce = modifica;
    setModifica(null);
    try {
      const d = await chiama(`/api/admin/qualita-ai/memoria/${voce.id}`, "PATCH", { categoria });
      const n = typeof d.righe_propagate === "number" ? d.righe_propagate : null;
      toast.success(n ? `Categoria aggiornata, ${n} righe corrette` : "Categoria aggiornata");
      setVoci((prima) => prima && prima.map((v) => (v.id === voce.id ? { ...v, categoria } : v)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function elimina(voce: VoceMemoria) {
    try {
      await chiama(`/api/admin/qualita-ai/memoria/${voce.id}`, "DELETE");
      toast.success("Voce eliminata");
      setVoci((prima) => prima && prima.filter((v) => v.id !== voce.id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  return (
    <section className="space-y-2 rounded-lg border p-3">
      <div>
        <h2 className="text-sm font-semibold">Memoria globale</h2>
        <p className="text-xs text-muted-foreground">Le categorie che valgono per tutti i clienti. Cerca un prodotto per correggerne una sbagliata.</p>
      </div>
      <div className="relative max-w-sm">
        <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input placeholder="Cerca nella memoria…" className="pl-8" value={testo} onChange={(e) => setTesto(e.target.value)} />
      </div>
      {voci && voci.length === 0 && <p className="text-sm text-muted-foreground">Nessuna voce trovata.</p>}
      {voci && voci.length > 0 && (
        <ul className="divide-y rounded-md border">
          {voci.map((v) => (
            <li key={v.id} className="flex items-center justify-between gap-2 px-3 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate" title={v.descrizione}>{v.descrizione}</p>
                <p className="text-xs text-muted-foreground">{v.categoria} · vista {v.volte_visto} volt{v.volte_visto === 1 ? "a" : "e"}</p>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button size="sm" variant="ghost" onClick={() => { setModifica(v); setCategoria(v.categoria); }}>Modifica</Button>
                <Button size="sm" variant="ghost" className="text-destructive" aria-label="Elimina" onClick={() => setDaEliminare(v)}><Trash2 className="size-4" /></Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Dialog open={modifica !== null} onOpenChange={(o) => { if (!o) setModifica(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Modifica categoria</DialogTitle>
            <DialogDescription className="break-words">{modifica?.descrizione}</DialogDescription>
          </DialogHeader>
          <NativeSelect value={categoria} onValueChange={setCategoria}>
            {CATEGORIE_TUTTE.map((c) => <option key={c} value={c}>{c}</option>)}
          </NativeSelect>
          <p className="text-xs text-muted-foreground">Corregge anche le righe già caricate dai clienti, tranne quelle che hanno scelto a mano.</p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModifica(null)}>Annulla</Button>
            <Button onClick={salva} disabled={!categoria}>Salva</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare questa voce dalla memoria globale?"
        messaggio={daEliminare ? `«${daEliminare.descrizione}» non avrà più una categoria valida per tutti.` : ""}
        confermaLabel="Elimina"
        onConferma={() => { if (daEliminare) elimina(daEliminare); }}
        onClose={() => setDaEliminare(null)}
      />
    </section>
  );
}

export function CategorieClient() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Categorie</h1>
      <DaSistemare />
      <Conflitti />
      <Memoria />
    </div>
  );
}
