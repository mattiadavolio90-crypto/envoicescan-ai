"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { CopyButton } from "@/components/ui/copy-button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { fmtDateTime } from "@/lib/admin";
import {
  type ElencoSottoUtenti, type Selezione, type SottoUtente, type StatoSottoUtente,
  ETICHETTA_PAGINA, ETICHETTA_STATO, PAGINA_CATENA,
  alterna, catenaDisponibile, erroreSelezione, pagineInOrdine, selezioneIniziale,
} from "@/lib/sotto-utenti-admin";

const CLASSE_STATO: Record<StatoSottoUtente, string> = {
  attivo: "text-positivo",
  in_attesa: "text-incerto",
  disattivato: "text-muted-foreground",
};

type Modulo = { id: string | null; email: string; nome: string; sel: Selezione };

async function leggi(res: Response) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || "Errore");
  return data;
}

// Scheda cliente → «Sotto-utenti»: accessi in piu' allo stesso account, ognuno
// con le sue pagine e le sue sedi. Li crea solo l'admin; il sotto-utente riceve
// un link (24 ore) e la password la sceglie lui.
export function SottoUtentiCard({ clienteId }: { clienteId: string }) {
  const base = `/api/admin/clienti/${clienteId}/sotto-utenti`;
  const [dati, setDati] = useState<ElencoSottoUtenti | null>(null);
  const [errore, setErrore] = useState<string | null>(null);
  const [occupato, setOccupato] = useState(false);
  const [modulo, setModulo] = useState<Modulo | null>(null);
  const [daEliminare, setDaEliminare] = useState<SottoUtente | null>(null);
  const [linkManuale, setLinkManuale] = useState<string | null>(null);

  const carica = useCallback(async () => {
    try {
      setDati(await leggi(await fetch(base, { cache: "no-store" })));
      setErrore(null);
    } catch (e) {
      setErrore(e instanceof Error ? e.message : "Errore");
    }
  }, [base]);

  useEffect(() => {
    carica();
  }, [carica]);

  async function chiama(path: string, metodo: "POST" | "PATCH" | "DELETE", body?: object, ok?: string) {
    setOccupato(true);
    try {
      const data = await leggi(await fetch(`${base}${path}`, {
        method: metodo,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      }));
      if (data.link_attivazione) {
        setLinkManuale(data.link_attivazione);
        toast.warning("Email non partita: copia il link e mandalo tu");
      } else if (ok) {
        toast.success(ok);
      }
      await carica();
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Errore");
      return false;
    } finally {
      setOccupato(false);
    }
  }

  async function salva() {
    if (!modulo) return;
    const corpo = { nome: modulo.nome, pagine: modulo.sel.pagine, sedi: modulo.sel.sedi };
    const fatto = modulo.id
      ? await chiama(`/${modulo.id}`, "PATCH", corpo, "Sotto-utente aggiornato")
      : await chiama("", "POST", { ...corpo, email: modulo.email }, "Sotto-utente creato: gli abbiamo mandato il link");
    if (fatto) setModulo(null);
  }

  const sedi = dati?.sedi ?? [];
  const nomeSede = (id: string) => sedi.find((s) => s.id === id)?.nome ?? "sede non più attiva";
  const pagine = pagineInOrdine(dati?.pagine_assegnabili ?? []);
  const erroreModulo = modulo ? erroreSelezione(modulo.sel, modulo.id ? undefined : modulo.email) : null;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Sotto-utenti ({dati?.sotto_utenti.length ?? 0})</CardTitle>
        <Button
          size="sm"
          disabled={!dati || sedi.length === 0}
          onClick={() => setModulo({ id: null, email: "", nome: "", sel: { pagine: [], sedi: sedi.length === 1 ? [sedi[0].id] : [] } })}
        >
          Nuovo sotto-utente
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {errore && <p className="text-negativo">{errore}</p>}
        {dati && sedi.length === 0 && (
          <p className="text-muted-foreground">Il cliente non ha sedi attive: aggiungine una prima di creare sotto-utenti.</p>
        )}
        {dati && dati.sotto_utenti.length === 0 && sedi.length > 0 && (
          <p className="text-muted-foreground">
            Nessun sotto-utente. Ognuno ha la sua email e password, e vede solo le pagine e le sedi che scegli qui.
          </p>
        )}
        {dati?.sotto_utenti.map((su) => (
          <div key={su.id} className="rounded-md border p-3 space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="min-w-0">
                <p className="font-medium break-all">{su.nome ? `${su.nome} — ${su.email}` : su.email}</p>
                <p className={`text-xs ${CLASSE_STATO[su.stato]}`}>
                  {ETICHETTA_STATO[su.stato]}
                  {su.last_login ? ` · ultimo accesso ${fmtDateTime(su.last_login)}` : ""}
                </p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Pagine: {su.pagine.map((p) => ETICHETTA_PAGINA[p] ?? p).join(", ") || "nessuna"}
            </p>
            <p className="text-xs text-muted-foreground">Sedi: {su.sedi.map(nomeSede).join(", ") || "nessuna"}</p>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm" variant="outline" disabled={occupato}
                onClick={() => setModulo({ id: su.id, email: su.email, nome: su.nome ?? "", sel: selezioneIniziale(su, dati?.pagine_assegnabili ?? [], sedi) })}
              >
                Modifica
              </Button>
              {su.stato !== "disattivato" && (
                <Button
                  size="sm" variant="outline" disabled={occupato}
                  onClick={() => chiama(`/${su.id}/invia-link`, "POST", undefined,
                    su.stato === "in_attesa" ? "Link di attivazione rimandato" : "Link per la nuova password mandato")}
                >
                  {su.stato === "in_attesa" ? "Rimanda attivazione" : "Link nuova password"}
                </Button>
              )}
              <Button
                size="sm" variant="outline" disabled={occupato}
                onClick={() => chiama(`/${su.id}`, "PATCH", { attivo: su.stato === "disattivato" },
                  su.stato === "disattivato" ? "Sotto-utente riattivato" : "Sotto-utente disattivato: è uscito da tutte le sessioni")}
              >
                {su.stato === "disattivato" ? "Riattiva" : "Disattiva"}
              </Button>
              <Button size="sm" variant="outline" className="text-destructive" disabled={occupato} onClick={() => setDaEliminare(su)}>
                Elimina
              </Button>
            </div>
          </div>
        ))}
        {linkManuale && (
          <div className="rounded-md border p-3 space-y-2">
            <p className="text-xs">L&apos;email non è partita. Manda tu questo link (vale 24 ore):</p>
            <div className="flex items-center gap-2">
              <code className="text-xs break-all">{linkManuale}</code>
              <CopyButton testo={linkManuale} />
            </div>
            <Button size="sm" variant="ghost" onClick={() => setLinkManuale(null)}>Chiudi</Button>
          </div>
        )}
      </CardContent>

      <Dialog open={modulo !== null} onOpenChange={(o) => { if (!o) setModulo(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{modulo?.id ? "Modifica sotto-utente" : "Nuovo sotto-utente"}</DialogTitle>
            <DialogDescription>
              {modulo?.id
                ? modulo.email
                : "Riceverà un'email con il link per scegliere la password (vale 24 ore)."}
            </DialogDescription>
          </DialogHeader>
          {modulo && (
            <div className="space-y-4 text-sm">
              {!modulo.id && (
                <div className="space-y-1">
                  <Label htmlFor="su-email">Email</Label>
                  <Input id="su-email" type="email" value={modulo.email}
                    onChange={(e) => setModulo({ ...modulo, email: e.target.value })} />
                </div>
              )}
              <div className="space-y-1">
                <Label htmlFor="su-nome">Nome (facoltativo)</Label>
                <Input id="su-nome" value={modulo.nome} placeholder="es. Responsabile sala"
                  onChange={(e) => setModulo({ ...modulo, nome: e.target.value })} />
              </div>
              <fieldset className="space-y-1">
                <legend className="font-medium">Pagine</legend>
                {pagine.map((p) => {
                  const bloccata = p === PAGINA_CATENA && !catenaDisponibile(modulo.sel.sedi, sedi);
                  return (
                    <label key={p} className={`flex items-center gap-2 ${bloccata ? "text-muted-foreground" : ""}`}>
                      <input type="checkbox" className="rounded" disabled={bloccata}
                        checked={modulo.sel.pagine.includes(p)}
                        onChange={() => setModulo({ ...modulo, sel: alterna(modulo.sel, "pagine", p, sedi) })} />
                      {ETICHETTA_PAGINA[p] ?? p}
                      {bloccata && <span className="text-xs">— serve spuntare tutte le sedi</span>}
                    </label>
                  );
                })}
              </fieldset>
              <fieldset className="space-y-1">
                <legend className="font-medium">Sedi</legend>
                {sedi.map((s) => (
                  <label key={s.id} className="flex items-center gap-2">
                    <input type="checkbox" className="rounded"
                      checked={modulo.sel.sedi.includes(s.id)}
                      onChange={() => setModulo({ ...modulo, sel: alterna(modulo.sel, "sedi", s.id, sedi) })} />
                    {s.nome ?? s.id}
                  </label>
                ))}
              </fieldset>
              {erroreModulo && <p className="text-xs text-muted-foreground">{erroreModulo}</p>}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setModulo(null)}>Annulla</Button>
            <Button disabled={occupato || erroreModulo !== null} onClick={salva}>
              {modulo?.id ? "Salva" : "Crea e manda il link"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={daEliminare !== null}
        titolo="Eliminare il sotto-utente?"
        messaggio={daEliminare ? `${daEliminare.email} non potrà più entrare. I dati che ha inserito restano del cliente.` : undefined}
        confermaLabel="Elimina"
        onConferma={async () => {
          if (daEliminare) await chiama(`/${daEliminare.id}`, "DELETE", undefined, "Sotto-utente eliminato");
          setDaEliminare(null);
        }}
        onClose={() => setDaEliminare(null)}
      />
    </Card>
  );
}
