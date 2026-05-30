"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FileText } from "lucide-react";

interface FattureMensiliCardProps {
  label: string;
  value: string;
  fattureMese: number;
  fattureMensili: { mese: string; count: number }[];
}

function fmtMese(mese: string): string {
  const [year, month] = mese.split("-");
  const date = new Date(Number(year), Number(month) - 1, 1);
  return date.toLocaleDateString("it-IT", { month: "long", year: "numeric" });
}

export function FattureMensiliCard({ label, value, fattureMensili }: FattureMensiliCardProps) {
  const [open, setOpen] = useState(false);
  const maxCount = Math.max(...(fattureMensili.length > 0 ? fattureMensili.map((r) => r.count) : [1]), 1);

  return (
    <>
      <Card
        className="ring-1 ring-sky-500/60 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={() => setOpen(true)}
        title="Clicca per vedere il dettaglio mensile"
      >
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
          <FileText className="size-4 text-orange-500" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold tabular-nums">{value}</div>
          <p className="text-xs text-muted-foreground mt-1">clicca per storico</p>
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="size-4 text-orange-500" />
              Fatture per mese
            </DialogTitle>
          </DialogHeader>

          {fattureMensili.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              Nessun dato disponibile
            </p>
          ) : (
            <div className="space-y-2 max-h-[60vh] overflow-y-auto pr-1">
              {[...fattureMensili].reverse().map((row) => (
                <div key={row.mese} className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground w-36 shrink-0 capitalize">
                    {fmtMese(row.mese)}
                  </span>
                  <div className="flex-1 h-5 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-orange-500/70 rounded-full transition-all"
                      style={{ width: `${(row.count / maxCount) * 100}%` }}
                    />
                  </div>
                  <span className="text-sm font-bold tabular-nums w-10 text-right">
                    {row.count}
                  </span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
