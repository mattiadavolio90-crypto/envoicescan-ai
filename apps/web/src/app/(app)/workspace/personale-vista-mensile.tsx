"use client";

import { Plus } from "lucide-react";
import {
  type Turno,
  type Dipendente,
  type TipoGiorno,
  TIPO_GIORNO_LABEL,
  fmtOra,
  fmtOreDisplay,
  calcolaOreTotali,
  orarioTurno,
} from "./personale-tab";

interface VistaMensileGridProps {
  meseBase: string; // YYYY-MM
  turni: Turno[];
  dipendenti: Dipendente[];
  nomePerId: Record<string, string>;
  oggi: string; // ISO
  onNuovoTurno: (dipendenteId: string, data: string) => void;
  onModificaTurno: (turno: Turno) => void;
  onModificaStatoGiorno: (turno: Turno) => void;
}

const TIPO_GIORNO_SIGLA: Record<Exclude<TipoGiorno, "turno">, string> = {
  riposo: "R",
  ferie: "F",
  malattia: "M",
};

const TIPO_GIORNO_CELL_CLASS: Record<Exclude<TipoGiorno, "turno">, string> = {
  riposo: "bg-slate-500/10 text-slate-600 dark:text-slate-400",
  ferie: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  malattia: "bg-red-500/10 text-red-600 dark:text-red-400",
};

function giorniDelMese(meseBase: string): string[] {
  const [ay, am] = meseBase.split("-").map(Number);
  const n = new Date(ay, am, 0).getDate();
  return Array.from({ length: n }, (_, i) => `${meseBase}-${String(i + 1).padStart(2, "0")}`);
}

function dowBreve(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return ["Do", "Lu", "Ma", "Me", "Gi", "Ve", "Sa"][d.getDay()];
}

function isWeekend(iso: string): boolean {
  const d = new Date(iso + "T00:00:00").getDay();
  return d === 0 || d === 6;
}

export function VistaMensileGrid({
  meseBase,
  turni,
  dipendenti,
  nomePerId,
  oggi,
  onNuovoTurno,
  onModificaTurno,
  onModificaStatoGiorno,
}: VistaMensileGridProps) {
  const giorni = giorniDelMese(meseBase);
  // Il backend (ws_personale_list) filtra già .eq("attivo", True): nessun filtro client-side da fare qui.
  const dipendentiAttivi = dipendenti;

  // Pivot dipendente×giorno: per ogni cella al più una riga (turno o stato-giorno).
  // Se più righe insistono sullo stesso giorno/dipendente si mostra la prima e le
  // altre restano raggiungibili solo dalla vista settimana (caso raro, non gestito qui).
  const cellaPerDipGiorno = new Map<string, Turno>();
  for (const t of turni) {
    if (t.mensile) continue; // le righe mensili aggregate non hanno una data-giorno da piazzare in griglia
    const key = `${t.dipendente_id}|${t.data_turno}`;
    if (!cellaPerDipGiorno.has(key)) cellaPerDipGiorno.set(key, t);
  }

  if (dipendentiAttivi.length === 0) {
    return (
      <div className="py-12 text-center text-sm text-muted-foreground">
        Nessun dipendente attivo. Aggiungine uno da &ldquo;Aggiungi turno&rdquo;.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border overflow-auto">
      <table className="border-collapse text-xs w-full">
        <thead>
          <tr className="sticky top-0 z-10 bg-card">
            <th className="sticky left-0 z-20 bg-card text-left font-semibold px-3 py-2 border-b border-r border-border min-w-[140px]">
              Dipendente
            </th>
            {giorni.map(iso => {
              const giorno = iso.split("-")[2];
              const weekend = isWeekend(iso);
              const isOggi = iso === oggi;
              return (
                <th
                  key={iso}
                  className={`px-1.5 py-2 border-b border-border font-medium min-w-[38px] ${
                    weekend ? "bg-muted/40" : ""
                  } ${isOggi ? "bg-primary/10" : ""}`}
                >
                  <div className="flex flex-col items-center leading-tight">
                    <span className="text-[9px] opacity-60">{dowBreve(iso)}</span>
                    <span className={isOggi ? "text-primary font-bold" : ""}>{giorno}</span>
                  </div>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {dipendentiAttivi.map(dip => (
            <tr key={dip.id} className="group/row">
              <td className="sticky left-0 z-10 bg-card group-hover/row:bg-muted/30 text-left px-3 py-1.5 border-r border-b border-border font-medium truncate max-w-[140px]">
                {nomePerId[dip.id] ?? dip.nome}
              </td>
              {giorni.map(iso => {
                const t = cellaPerDipGiorno.get(`${dip.id}|${iso}`);
                const weekend = isWeekend(iso);
                const isOggi = iso === oggi;
                const tipoGiorno = t?.tipo_giorno ?? "turno";
                const statoNonTurno = t && tipoGiorno !== "turno";

                let contenuto: React.ReactNode = null;
                if (statoNonTurno) {
                  contenuto = (
                    <span
                      className={`inline-flex items-center justify-center size-5 rounded text-[10px] font-semibold ${TIPO_GIORNO_CELL_CLASS[tipoGiorno as Exclude<TipoGiorno, "turno">]}`}
                      title={TIPO_GIORNO_LABEL[tipoGiorno as TipoGiorno]}
                    >
                      {TIPO_GIORNO_SIGLA[tipoGiorno as Exclude<TipoGiorno, "turno">]}
                    </span>
                  );
                } else if (t) {
                  const ore = calcolaOreTotali(t);
                  contenuto = (
                    <span className="flex flex-col items-center leading-tight tabular-nums" title={orarioTurno(t)}>
                      <span className="text-[10px]">{fmtOra(t.ora_inizio)}</span>
                      <span className="text-[9px] opacity-60">{fmtOreDisplay(ore)}</span>
                    </span>
                  );
                }

                return (
                  <td
                    key={iso}
                    onClick={() => {
                      if (t) {
                        if (statoNonTurno) onModificaStatoGiorno(t);
                        else onModificaTurno(t);
                      } else {
                        onNuovoTurno(dip.id, iso);
                      }
                    }}
                    className={`px-1 py-1.5 border-b border-border text-center cursor-pointer hover:bg-primary/10 ${
                      weekend ? "bg-muted/40" : ""
                    } ${isOggi ? "bg-primary/5" : ""}`}
                  >
                    {contenuto ?? (
                      <span className="flex items-center justify-center size-5 mx-auto rounded text-muted-foreground/0 hover:text-muted-foreground/60">
                        <Plus className="size-3" />
                      </span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="px-3 py-2 text-[11px] text-muted-foreground border-t border-border">
        Click su una cella per aggiungere o modificare il turno. R = riposo, F = ferie, M = malattia.
        Per impostare riposo/ferie/malattia su una cella vuota usa &ldquo;Riposo/ferie/malattia&rdquo; nella toolbar.
      </p>
    </div>
  );
}
