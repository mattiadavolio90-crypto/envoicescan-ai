"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { KeyRound, Lock, Mail, Send } from "lucide-react";
import { SottoUtentiCard } from "@/components/admin/sotto-utenti";
import { chiamaAdmin, messaggioErrore, type TabProps } from "./comune";

export function AccountTab({ c, setC }: TabProps) {
  const [emailDialog, setEmailDialog] = useState(false);
  const [nuovaEmail, setNuovaEmail] = useState("");
  const [pwdDialog, setPwdDialog] = useState(false);
  const [nuovaPwd, setNuovaPwd] = useState("");
  const [pwdVisibile, setPwdVisibile] = useState(false);
  const [occupato, setOccupato] = useState(false);

  async function inviaReset() {
    try {
      const data = await chiamaAdmin(`/api/admin/clienti/${c.id}/reset-password`, "POST");
      toast.success(data.email_inviata ? "Email reset inviata" : `Email NON inviata. Link: ${data.link}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function rinviaAttivazione() {
    try {
      // Il backend ritorna 502 (→ throw) se Brevo fallisce: qui l'email e' partita.
      const data = await chiamaAdmin(`/api/admin/clienti/${c.id}/rinvia-attivazione`, "POST");
      toast.success(`Email di attivazione reinviata a ${data.email}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function impostaPassword() {
    if (!nuovaPwd.trim()) return;
    setOccupato(true);
    try {
      const eraAttivo = c.attivo;
      await chiamaAdmin(`/api/admin/clienti/${c.id}/imposta-password`, "POST", { password: nuovaPwd });
      setC((prev) => ({ ...prev, attivo: true }));
      toast.success(eraAttivo ? "Password aggiornata." : "Password impostata. Account attivo.");
      setPwdDialog(false);
      setNuovaPwd("");
      setPwdVisibile(false);
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setOccupato(false);
    }
  }

  async function cambiaEmail() {
    if (!nuovaEmail.trim()) return;
    setOccupato(true);
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/email`, "PATCH", { nuova_email: nuovaEmail.trim() });
      setC((prev) => ({ ...prev, email: nuovaEmail.trim().toLowerCase() }));
      toast.success("Email aggiornata");
      setEmailDialog(false);
      setNuovaEmail("");
    } catch (e) {
      toast.error(messaggioErrore(e));
    } finally {
      setOccupato(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Accesso del titolare</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm">
            <span className="text-muted-foreground">Email di accesso: </span>
            <span className="font-medium break-all">{c.email}</span>
          </p>
          <div className="flex flex-wrap gap-2">
            {!c.attivo && (
              <Button variant="outline" size="sm" onClick={rinviaAttivazione}>
                <Send className="size-4 mr-1" /> Rinvia email di attivazione
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={inviaReset}>
              <KeyRound className="size-4 mr-1" /> Invia reset password
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setNuovaPwd(""); setPwdVisibile(false); setPwdDialog(true); }}>
              <Lock className="size-4 mr-1" /> {c.attivo ? "Imposta password" : "Crea password"}
            </Button>
            <Button variant="outline" size="sm" onClick={() => setEmailDialog(true)}>
              <Mail className="size-4 mr-1" /> Cambia email
            </Button>
          </div>
        </CardContent>
      </Card>

      <SottoUtentiCard clienteId={c.id} />

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
              <Input id="nuova-email" type="email" value={nuovaEmail} onChange={(e) => setNuovaEmail(e.target.value)} placeholder="nuova@email.it" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEmailDialog(false)} disabled={occupato}>Annulla</Button>
            <Button onClick={cambiaEmail} disabled={occupato || !nuovaEmail.trim()}>{occupato ? "Salvataggio…" : "Conferma"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={pwdDialog} onOpenChange={setPwdDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{c.attivo ? "Imposta password" : "Crea password"}</DialogTitle>
            <DialogDescription>
              Imposti tu la password per <strong>{c.email}</strong>.
              {c.attivo
                ? " Sostituisce quella attuale e chiude ogni sessione aperta del cliente."
                : " L'account viene attivato e ogni sessione aperta del cliente viene chiusa."}
              {" "}Da comunicare al cliente a voce.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-2">
            <Label htmlFor="nuova-pwd">Nuova password</Label>
            <div className="relative">
              <Input
                id="nuova-pwd"
                type={pwdVisibile ? "text" : "password"}
                value={nuovaPwd}
                onChange={(e) => setNuovaPwd(e.target.value)}
                placeholder="Almeno 10 caratteri"
                autoComplete="new-password"
              />
              <button
                type="button"
                onClick={() => setPwdVisibile((v) => !v)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-foreground"
              >
                {pwdVisibile ? "Nascondi" : "Mostra"}
              </button>
            </div>
            <p className="text-xs text-muted-foreground">
              Min. 10 caratteri con maiuscola, minuscola, numero e simbolo. No email o nome del locale.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPwdDialog(false)} disabled={occupato}>Annulla</Button>
            <Button onClick={impostaPassword} disabled={occupato || !nuovaPwd.trim()}>
              {occupato ? "Salvataggio…" : c.attivo ? "Imposta" : "Imposta e attiva"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
