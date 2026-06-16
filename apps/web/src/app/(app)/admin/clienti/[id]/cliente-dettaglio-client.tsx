"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  LogIn, Mail, KeyRound, Trash2, Plus, X, Clock, CheckCircle, XCircle, AlertTriangle, Pencil
} from "lucide-react";
import { ClienteDettaglio, Sede, PIANO_LABEL, PIANO_COLOR, fmtDate, fmtDateTime } from "@/lib/admin";

type Props = { cliente: ClienteDettaglio };

const SIDEBAR_FLAGS: { key: string; label: string; desc: string }[] = [
  { key: "analisi_fatture", label: "Analisi Fatture", desc: "Visualizza e gestisci fatture" },
  { key: "prezzi", label: "Osservatorio", desc: "Variazioni prezzi, sconti, note di credito, score fornitori" },
  { key: "margini", label: "Ricavi e Margini", desc: "Calcolo marginalità e analisi avanzate" },
  { key: "agenda", label: "Agenda", desc: "Appuntamenti, spese extra, turni del personale" },
  { key: "workspace", label: "Strumenti", desc: "Foodcost e inventario di magazzino" },
  { key: "analisi_e_tag", label: "Analisi e Tag", desc: "Tag personalizzati e analytics" },
  { key: "scadenziario", label: "Gestione Fatture", desc: "Gestione scadenze e pagamenti" },
  { key: "blocco_anno_precedente", label: "Blocca anno precedente", desc: "Impedisce caricamento fatture dell'anno scorso" },
  { key: "blocco_mesi_precedenti", label: "Blocca mesi precedenti", desc: "Consente solo mese corrente e precedente" },
];

export function ClienteDettaglioClient({ cliente: iniziale }: Props) {
  const router = useRouter();
  const [c, setC] = useState<ClienteDettaglio>(iniziale);

  // Email dialog
  const [emailDialog, setEmailDialog] = useState(false);
  const [nuovaEmail, setNuovaEmail] = useState("");
  const [emailSaving, setEmailSaving] = useState(false);

  // Sede dialog (crea)
  const [sedeDialog, setSedeDialog] = useState(false);
  const [sNome, setSNome] = useState("");
  const [sPiva, setSPiva] = useState("");
  const [sRagione, setSRagione] = useState("");
  const [sIndirizzo, setSIndirizzo] = useState("");
  const [sCap, setSCap] = useState("");
  const [sComune, setSComune] = useState("");
  const [sPiano, setSPiano] = useState("base");
  const [sedeSaving, setSedeSaving] = useState(false);

  // Sede dialog (modifica)
  const [editSede, setEditSede] = useState<Sede | null>(null);
  const [eNome, setENome] = useState("");
  const [ePiva, setEPiva] = useState("");
  const [eRagione, setERagione] = useState("");
  const [eIndirizzo, setEIndirizzo] = useState("");
  const [eCap, setECap] = useState("");
  const [eComune, setEComune] = useState("");
  const [ePiano, setEPiano] = useState("base");
  const [editSedeSaving, setEditSedeSaving] = useState(false);

  // Modifica dati account (etichetta + gruppo). Il piano è per-SEDE, non qui.
  const [modificaDialog, setModificaDialog] = useState(false);
  const [mNome, setMNome] = useState("");
  const [mGruppo, setMGruppo] = useState("");
  const [modificaSaving, setModificaSaving] = useState(false);

  // Elimina account dialog
  const [eliminaDialog, setEliminaDialog] = useState(false);
  const [eliminaMemoria, setEliminaMemoria] = useState(false);
  const [eliminaSaving, setEliminaSaving] = useState(false);

  async function patch(url: string, method: string, body?: object) {
    const res = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Errore");
    return data;
  }

  async function toggleAttivo() {
    try {
      await patch(`/api/admin/clienti/${c.id}/account`, "PATCH", { attivo: !c.attivo });
      setC((prev) => ({ ...prev, attivo: !prev.attivo }));
      toast.success(c.attivo ? "Account disattivato" : "Account attivato");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleResetPassword() {
    try {
      const data = await patch(`/api/admin/clienti/${c.id}/reset-password`, "POST");
      toast.success(data.email_inviata ? "Email reset inviata" : `Email NON inviata. Link: ${data.link}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleCambioEmail() {
    if (!nuovaEmail.trim()) return;
    setEmailSaving(true);
    try {
      await patch(`/api/admin/clienti/${c.id}/email`, "PATCH", { nuova_email: nuovaEmail.trim() });
      setC((prev) => ({ ...prev, email: nuovaEmail.trim().toLowerCase() }));
      toast.success("Email aggiornata");
      setEmailDialog(false);
      setNuovaEmail("");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setEmailSaving(false);
    }
  }

  async function handleImpersona() {
    try {
      await patch(`/api/admin/clienti/${c.id}/impersona`, "POST");
      toast.success(`Accesso come ${c.email}`);
      router.push("/dashboard");
      router.refresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  function openModifica() {
    setMNome(c.nome_ristorante || "");
    setMGruppo(c.nome_gruppo || "");
    setModificaDialog(true);
  }

  async function handleModifica() {
    setModificaSaving(true);
    try {
      const res = await fetch(`/api/admin/clienti/${c.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome_ristorante: mNome.trim() || undefined,
          nome_gruppo: mGruppo.trim() || null,
        }),
      });
      const data = await res.json();
      if (!res.ok) { toast.error(data.detail || "Errore salvataggio"); return; }
      setC((prev) => ({
        ...prev,
        nome_ristorante: mNome.trim() || prev.nome_ristorante,
        nome_gruppo: mGruppo.trim() || null,
      }));
      toast.success("Dati aggiornati");
      setModificaDialog(false);
    } catch {
      toast.error("Errore di connessione");
    } finally {
      setModificaSaving(false);
    }
  }

  async function handleAttivaTrial() {
    try {
      const data = await patch(`/api/admin/clienti/${c.id}/trial`, "POST");
      toast.success(data.message || "Trial attivata");
      router.refresh();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleCreaSedeSubmit() {
    if (!sNome.trim() || !sPiva.trim()) { toast.error("Nome e P.IVA obbligatori"); return; }
    setSedeSaving(true);
    try {
      const sede: Sede = await patch(`/api/admin/clienti/${c.id}/sedi`, "POST", {
        nome_ristorante: sNome.trim(),
        partita_iva: sPiva.trim(),
        ragione_sociale: sRagione.trim() || undefined,
        indirizzo: sIndirizzo.trim() || undefined,
        cap: sCap.trim() || undefined,
        comune: sComune.trim() || undefined,
        piano: sPiano,
      });
      setC((prev) => ({ ...prev, sedi: [...prev.sedi, sede], n_sedi: prev.n_sedi + 1 }));
      toast.success("Sede creata");
      setSedeDialog(false);
      setSNome(""); setSPiva(""); setSRagione("");
      setSIndirizzo(""); setSCap(""); setSComune(""); setSPiano("base");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setSedeSaving(false);
    }
  }

  async function handleEliminaSede(sede: Sede) {
    if (!confirm(`Eliminare la sede "${sede.nome_ristorante}"? Tutte le sue fatture verranno eliminate.`)) return;
    try {
      await patch(`/api/admin/clienti/${c.id}/sedi/${sede.id}`, "DELETE");
      setC((prev) => ({ ...prev, sedi: prev.sedi.filter((s) => s.id !== sede.id), n_sedi: prev.n_sedi - 1 }));
      toast.success("Sede eliminata");
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  function openModificaSede(sede: Sede) {
    setEditSede(sede);
    setENome(sede.nome_ristorante || "");
    setEPiva(sede.partita_iva || "");
    setERagione(sede.ragione_sociale || "");
    setEIndirizzo(sede.indirizzo || "");
    setECap(sede.cap || "");
    setEComune(sede.comune || "");
    setEPiano(sede.piano || "base");
  }

  async function handleModificaSedeSubmit() {
    if (!editSede) return;
    if (!eNome.trim() || !ePiva.trim()) { toast.error("Nome e P.IVA obbligatori"); return; }
    setEditSedeSaving(true);
    try {
      const updated: Sede = await patch(`/api/admin/clienti/${c.id}/sedi/${editSede.id}`, "PATCH", {
        nome_ristorante: eNome.trim(),
        partita_iva: ePiva.trim(),
        ragione_sociale: eRagione.trim() || null,
        indirizzo: eIndirizzo.trim() || null,
        cap: eCap.trim() || null,
        comune: eComune.trim() || null,
        piano: ePiano,
      });
      setC((prev) => ({ ...prev, sedi: prev.sedi.map((s) => (s.id === updated.id ? updated : s)) }));
      toast.success("Sede aggiornata");
      setEditSede(null);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    } finally {
      setEditSedeSaving(false);
    }
  }

  async function handleToggleFlag(key: string, enabled: boolean) {
    try {
      await patch(`/api/admin/clienti/${c.id}/flags`, "PATCH", {
        pagine_abilitate: { [key]: enabled },
      });
      setC((prev) => ({ ...prev, pagine_abilitate: { ...prev.pagine_abilitate, [key]: enabled } }));
      toast.success(`${key} ${enabled ? "attivato" : "disattivato"}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleToggleChatAi(enabled: boolean) {
    try {
      await patch(`/api/admin/clienti/${c.id}/flags`, "PATCH", { chat_ai_enabled: enabled });
      setC((prev) => ({ ...prev, chat_ai_enabled: enabled }));
      toast.success(`Assistente AI ${enabled ? "attivato" : "disattivato"}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Errore");
    }
  }

  async function handleEliminaAccount() {
    setEliminaSaving(true);
    try {
      await fetch(`/api/admin/clienti/${c.id}?elimina_memoria=${eliminaMemoria}`, { method: "DELETE" });
      toast.success("Account eliminato");
      router.push("/admin/clienti");
      router.refresh();
    } catch {
      toast.error("Errore eliminazione");
    } finally {
      setEliminaSaving(false);
    }
  }

  const flags = c.pagine_abilitate || {};

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Colonna sinistra: dati + azioni rapide */}
      <div className="lg:col-span-1 space-y-4">
        {/* Card dati cliente */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Dati cliente</CardTitle>
            <Button variant="ghost" size="sm" onClick={openModifica}>
              <Pencil className="size-4 mr-1" /> Modifica
            </Button>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <dl className="space-y-2">
              <div>
                <dt className="text-muted-foreground text-xs">Email</dt>
                <dd className="font-medium break-all">{c.email}</dd>
              </div>
              {c.nome_gruppo && (
                <div>
                  <dt className="text-muted-foreground text-xs">Nome gruppo / catena</dt>
                  <dd className="font-medium">{c.nome_gruppo}</dd>
                </div>
              )}
              <div>
                <dt className="text-muted-foreground text-xs">Nome account</dt>
                <dd className="font-medium">{c.nome_ristorante || "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Membro dal</dt>
                <dd className="font-medium">{fmtDate(c.created_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Ultimo accesso</dt>
                <dd className="font-medium">{fmtDateTime(c.last_seen_at)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Fatture totali</dt>
                <dd className="font-medium tabular-nums">{c.n_fatture?.toLocaleString("it-IT") ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground text-xs">Stato account</dt>
                <dd>
                  {c.attivo
                    ? <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700"><CheckCircle className="size-3" /> Attivo</span>
                    : <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600"><XCircle className="size-3" /> Disattivo</span>
                  }
                </dd>
              </div>
              {c.trial?.active && (
                <div>
                  <dt className="text-muted-foreground text-xs">Trial</dt>
                  <dd className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700">
                    <Clock className="size-3" /> {c.trial.days_remaining ?? 0} giorni rimasti
                  </dd>
                </div>
              )}
            </dl>
          </CardContent>
        </Card>

        {/* Azioni rapide */}
        <Card>
          <CardHeader><CardTitle className="text-base">Azioni</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Button className="w-full justify-start" onClick={handleImpersona}>
              <LogIn className="size-4 mr-2" /> Entra come cliente
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={handleResetPassword}>
              <KeyRound className="size-4 mr-2" /> Invia reset password
            </Button>
            <Button variant="outline" className="w-full justify-start" onClick={() => setEmailDialog(true)}>
              <Mail className="size-4 mr-2" /> Cambia email
            </Button>
            <Button
              variant={c.attivo ? "outline" : "default"}
              className="w-full justify-start"
              onClick={toggleAttivo}
            >
              {c.attivo
                ? <><XCircle className="size-4 mr-2" /> Disattiva account</>
                : <><CheckCircle className="size-4 mr-2" /> Attiva account</>
              }
            </Button>
            {!c.trial?.active && (
              <Button variant="outline" className="w-full justify-start" onClick={handleAttivaTrial}>
                <Clock className="size-4 mr-2" /> Attiva trial 7 giorni
              </Button>
            )}
          </CardContent>
        </Card>

        {/* Zona pericolosa */}
        <Card className="border-destructive/40">
          <CardHeader><CardTitle className="text-base text-destructive">Zona pericolosa</CardTitle></CardHeader>
          <CardContent>
            <Button
              variant="destructive"
              className="w-full"
              onClick={() => setEliminaDialog(true)}
            >
              <Trash2 className="size-4 mr-2" /> Elimina account
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Colonna destra: feature flags + sedi */}
      <div className="lg:col-span-2 space-y-4">
        {/* Feature flags */}
        <Card>
          <CardHeader><CardTitle className="text-base">Accesso sezioni</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {SIDEBAR_FLAGS.map((f) => {
              const enabled = flags[f.key] !== false;
              return (
                <div key={f.key} className="flex items-center justify-between gap-4 py-1 border-b last:border-0">
                  <div>
                    <p className="text-sm font-medium">{f.label}</p>
                    <p className="text-xs text-muted-foreground">{f.desc}</p>
                  </div>
                  <Switch
                    checked={enabled}
                    onCheckedChange={(v: boolean) => handleToggleFlag(f.key, v)}
                  />
                </div>
              );
            })}
            <div className="flex items-center justify-between gap-4 py-1 border-b">
              <div>
                <p className="text-sm font-medium">Assistente AI (Chat)</p>
                <p className="text-xs text-muted-foreground">Chat AI nella Home del cliente</p>
              </div>
              <Switch
                checked={c.chat_ai_enabled}
                onCheckedChange={handleToggleChatAi}
              />
            </div>
            <div className="flex items-center justify-between gap-4 py-1">
              <div>
                <p className="text-sm font-medium">Suggerimenti servizi</p>
                <p className="text-xs text-muted-foreground">
                  Hint contestuali discreti che propongono i servizi giusti nelle pagine
                </p>
              </div>
              {/* Convenzione inversa: salviamo il flag solo da SPENTO
                  (trigger_servizi_off). Assente = ON di default, anche per i
                  clienti gia' esistenti. La lista pagine_abilitate lato cliente
                  porta solo le chiavi true, quindi un OFF deve essere una chiave
                  presente, non assente. Lo switch mostra l'opposto del flag-off. */}
              <Switch
                checked={flags.trigger_servizi_off !== true}
                onCheckedChange={(v: boolean) => handleToggleFlag("trigger_servizi_off", !v)}
              />
            </div>
          </CardContent>
        </Card>

        {/* Sedi */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">Sedi ({c.sedi.length})</CardTitle>
            <Button size="sm" variant="outline" onClick={() => setSedeDialog(true)}>
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
                  <div key={sede.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <p className="text-sm font-medium truncate">{sede.nome_ristorante}</p>
                        <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold shrink-0 ${PIANO_COLOR[sede.piano || "base"] || ""}`}>
                          {PIANO_LABEL[sede.piano || "base"] || sede.piano}
                        </span>
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
                      <span className={`text-xs font-medium ${sede.attivo ? "text-emerald-600" : "text-red-500"}`}>
                        {sede.attivo ? "Attiva" : "Inattiva"}
                      </span>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="size-7 p-0 text-muted-foreground hover:text-foreground"
                        onClick={() => openModificaSede(sede)}
                        title="Modifica sede"
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="size-7 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => handleEliminaSede(sede)}
                        title="Elimina sede"
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Dialog cambia email */}
      <Dialog open={emailDialog} onOpenChange={setEmailDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Cambia email</DialogTitle>
            <DialogDescription>La sessione corrente del cliente verrà invalidata.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label>Email attuale</Label>
              <p className="text-sm text-muted-foreground">{c.email}</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nuova-email">Nuova email</Label>
              <Input
                id="nuova-email"
                type="email"
                value={nuovaEmail}
                onChange={(e) => setNuovaEmail(e.target.value)}
                placeholder="nuova@email.it"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailDialog(false)} disabled={emailSaving}>Annulla</Button>
            <Button onClick={handleCambioEmail} disabled={emailSaving || !nuovaEmail.trim()}>
              {emailSaving ? "Salvataggio…" : "Conferma"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog modifica dati cliente */}
      <Dialog open={modificaDialog} onOpenChange={setModificaDialog}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Modifica dati account</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="m-nome">Nome account</Label>
              <Input id="m-nome" value={mNome} onChange={(e) => setMNome(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="m-gruppo">Nome gruppo / catena</Label>
              <Input id="m-gruppo" placeholder="Es: SUSHILAND (opzionale, per clienti multi-sede)" value={mGruppo} onChange={(e) => setMGruppo(e.target.value)} />
            </div>
            <p className="text-xs text-muted-foreground">
              P.IVA, ragione sociale e piano si gestiscono per <strong>sede</strong>, nella sezione Sedi.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setModificaDialog(false)} disabled={modificaSaving}>Annulla</Button>
            <Button onClick={handleModifica} disabled={modificaSaving}>
              {modificaSaving ? "Salvataggio…" : "Salva"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog aggiungi sede */}
      <Dialog open={sedeDialog} onOpenChange={setSedeDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Aggiungi sede</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="s-nome">Nome sede *</Label>
              <Input id="s-nome" placeholder="Es: Trattoria Mario 2" value={sNome} onChange={(e) => setSNome(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-piva">P.IVA * (11 cifre)</Label>
              <Input id="s-piva" placeholder="12345678901" maxLength={11} value={sPiva} onChange={(e) => setSPiva(e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-ragione">Ragione sociale</Label>
              <Input id="s-ragione" placeholder="Opzionale" value={sRagione} onChange={(e) => setSRagione(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-indirizzo">Indirizzo</Label>
              <Input id="s-indirizzo" placeholder="Via e numero civico" value={sIndirizzo} onChange={(e) => setSIndirizzo(e.target.value)} />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="s-cap">CAP</Label>
                <Input id="s-cap" placeholder="00000" maxLength={10} value={sCap} onChange={(e) => setSCap(e.target.value)} />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="s-comune">Comune</Label>
                <Input id="s-comune" placeholder="Città" value={sComune} onChange={(e) => setSComune(e.target.value)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="s-piano">Piano</Label>
              <Select value={sPiano} onValueChange={setSPiano}>
                <SelectTrigger id="s-piano"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="free">Free (chat AI esclusa)</SelectItem>
                  <SelectItem value="base">Base (50 fatture)</SelectItem>
                  <SelectItem value="plus">Plus (100 fatture)</SelectItem>
                  <SelectItem value="pro">Pro (200 fatture)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              Indirizzo, CAP e comune servono a smistare automaticamente le fatture quando più sedi condividono la stessa P.IVA. Il piano è per sede.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSedeDialog(false)} disabled={sedeSaving}>Annulla</Button>
            <Button onClick={handleCreaSedeSubmit} disabled={sedeSaving || !sNome.trim() || !sPiva.trim()}>
              {sedeSaving ? "Creazione…" : "Crea sede"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog modifica sede */}
      <Dialog open={editSede !== null} onOpenChange={(o) => !o && setEditSede(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Modifica sede</DialogTitle></DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="e-nome">Nome sede *</Label>
              <Input id="e-nome" value={eNome} onChange={(e) => setENome(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-piva">P.IVA * (11 cifre)</Label>
              <Input id="e-piva" maxLength={11} value={ePiva} onChange={(e) => setEPiva(e.target.value.replace(/\D/g, ""))} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-ragione">Ragione sociale</Label>
              <Input id="e-ragione" placeholder="Opzionale" value={eRagione} onChange={(e) => setERagione(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-indirizzo">Indirizzo</Label>
              <Input id="e-indirizzo" placeholder="Via e numero civico" value={eIndirizzo} onChange={(e) => setEIndirizzo(e.target.value)} />
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="e-cap">CAP</Label>
                <Input id="e-cap" placeholder="00000" maxLength={10} value={eCap} onChange={(e) => setECap(e.target.value)} />
              </div>
              <div className="col-span-2 space-y-1.5">
                <Label htmlFor="e-comune">Comune</Label>
                <Input id="e-comune" placeholder="Città" value={eComune} onChange={(e) => setEComune(e.target.value)} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="e-piano">Piano</Label>
              <Select value={ePiano} onValueChange={setEPiano}>
                <SelectTrigger id="e-piano"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="free">Free (chat AI esclusa)</SelectItem>
                  <SelectItem value="base">Base (50 fatture)</SelectItem>
                  <SelectItem value="plus">Plus (100 fatture)</SelectItem>
                  <SelectItem value="pro">Pro (200 fatture)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p className="text-xs text-muted-foreground">
              Indirizzo, CAP e comune servono a smistare automaticamente le fatture quando più sedi condividono la stessa P.IVA. Il piano è per sede.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditSede(null)} disabled={editSedeSaving}>Annulla</Button>
            <Button onClick={handleModificaSedeSubmit} disabled={editSedeSaving || !eNome.trim() || !ePiva.trim()}>
              {editSedeSaving ? "Salvataggio…" : "Salva modifiche"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog elimina account */}
      <Dialog open={eliminaDialog} onOpenChange={setEliminaDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-destructive">Elimina account</DialogTitle>
            <DialogDescription>
              Stai per eliminare definitivamente <strong>{c.email}</strong> e tutti i suoi dati. Questa azione è irreversibile.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2 space-y-3">
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive space-y-1">
              <p className="font-medium"><AlertTriangle className="inline size-4 mr-1" />Verranno eliminati:</p>
              <ul className="list-disc list-inside text-xs space-y-0.5 text-destructive/80">
                <li>Account utente</li>
                <li>Tutte le fatture e righe prodotto</li>
                <li>Upload events, ricette, ingredienti</li>
                <li>Tutti i ristoranti/sedi</li>
              </ul>
            </div>
            <div className="flex items-center gap-2">
              <Switch id="elimina-memoria" checked={eliminaMemoria} onCheckedChange={setEliminaMemoria} />
              <Label htmlFor="elimina-memoria" className="text-sm">
                Elimina anche i contributi alla memoria AI globale
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEliminaDialog(false)} disabled={eliminaSaving}>Annulla</Button>
            <Button variant="destructive" onClick={handleEliminaAccount} disabled={eliminaSaving}>
              {eliminaSaving ? "Eliminazione…" : "Sì, elimina definitivamente"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
