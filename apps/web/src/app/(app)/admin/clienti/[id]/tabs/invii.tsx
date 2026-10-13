"use client";

import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { InvioCommercialistaCard } from "@/components/admin/invio-commercialista";
import { chiamaAdmin, messaggioErrore, type TabProps } from "./comune";

export function InviiTab({ c, setC }: TabProps) {
  async function scriviEmailSettimanale(enabled: boolean) {
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/flags`, "PATCH", { email_settimanale_abilitata: enabled });
      setC((prev) => ({ ...prev, email_settimanale_abilitata: enabled }));
      toast.success(`Email settimanale ${enabled ? "abilitata" : "disabilitata"}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function prova() {
    try {
      const data = await chiamaAdmin(`/api/admin/clienti/${c.id}/email-settimanale-prova`, "POST");
      if (data.inviata) toast.success(`Prova inviata a ${data.a}`);
      else toast.error(`Nessuna email: ${data.motivo || "il cliente non la riceverebbe"}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Email settimanale</CardTitle></CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            <p className="text-sm text-muted-foreground">
              {/* La scelta del cliente vince sempre: abilitarlo non riaccende
                  un'email che ha spento lui. */}
              {c.email_settimanale_cliente === false
                ? "Il cliente l'ha disattivata: non la riceve finché non la riaccende lui."
                : "Il lunedì mattina, il riepilogo della settimana del locale."}
            </p>
            <div className="flex shrink-0 items-center gap-3">
              <Button variant="outline" size="sm" onClick={prova}>Mandami una prova</Button>
              <Switch checked={c.email_settimanale_abilitata === true} onCheckedChange={scriviEmailSettimanale} />
            </div>
          </div>
        </CardContent>
      </Card>

      <InvioCommercialistaCard clienteId={c.id} />
    </div>
  );
}
