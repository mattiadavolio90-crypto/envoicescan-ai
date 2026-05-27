"use client";

import { type PivotRow } from "@/lib/fatture";

type Props = {
  rows: PivotRow[];
  mesi: string[];
  dimensioneLabel: string;
};

function formatEur(v: number): string {
  return v.toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
}

function formatMese(key: string): string {
  const [y, m] = key.split("-");
  const mesi = ["", "Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
  return `${mesi[parseInt(m)]} ${y}`;
}

export function PivotTable({ rows, mesi, dimensioneLabel }: Props) {
  if (rows.length === 0) {
    return (
      <div className="text-center py-16 text-muted-foreground text-sm">
        Nessun dato disponibile per il periodo selezionato.
      </div>
    );
  }

  const maxTotale = Math.max(...rows.map((r) => r.totale), 1);

  return (
    <div className="rounded-lg border overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50">
            <th className="text-left px-4 py-2.5 font-medium text-xs text-muted-foreground w-48 min-w-48">
              {dimensioneLabel}
            </th>
            {mesi.map((m) => (
              <th key={m} className="text-right px-3 py-2.5 font-medium text-xs text-muted-foreground whitespace-nowrap min-w-24">
                {formatMese(m)}
              </th>
            ))}
            <th className="text-right px-4 py-2.5 font-medium text-xs text-muted-foreground whitespace-nowrap min-w-28">
              Totale
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const pct = Math.round((row.totale / maxTotale) * 100);
            return (
              <tr key={row.dimensione} className={idx % 2 === 0 ? "bg-background" : "bg-muted/20"}>
                <td className="px-4 py-2 font-medium text-xs max-w-48 truncate" title={row.dimensione}>
                  {row.dimensione}
                </td>
                {mesi.map((m) => (
                  <td key={m} className="text-right px-3 py-2 text-xs tabular-nums text-muted-foreground">
                    {row.mesi[m] ? formatEur(row.mesi[m]) : "—"}
                  </td>
                ))}
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2 justify-end">
                    <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="text-xs font-semibold tabular-nums">{formatEur(row.totale)}</span>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr className="border-t bg-muted/50 font-semibold">
            <td className="px-4 py-2.5 text-xs">Totale</td>
            {mesi.map((m) => {
              const sum = rows.reduce((acc, r) => acc + (r.mesi[m] ?? 0), 0);
              return (
                <td key={m} className="text-right px-3 py-2.5 text-xs tabular-nums">
                  {sum > 0 ? formatEur(sum) : "—"}
                </td>
              );
            })}
            <td className="text-right px-4 py-2.5 text-xs tabular-nums">
              {formatEur(rows.reduce((acc, r) => acc + r.totale, 0))}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
