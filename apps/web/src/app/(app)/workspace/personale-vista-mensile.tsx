"use client";

import { Plus } from "lucide-react";
import {
  type Turno,
  type Dipendente,
  type TipoGiorno,
  TIPO_GIORNO_LABEL,
  TIPO_GIORNO_BADGE,
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
  settimanaZoom: number | null; // indice in settimaneDelMese(meseBase), null = mese intero
  onZoomSettimana: (indice: number | null) => void;
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

// Altezza della riga-settimana: il valore è ripetuto nel `top-[...]` della riga
// giorni sotto, che deve restare incollata esattamente sotto la prima.
const H_RIGA_SETTIMANA = 29;

export function giorniDelMese(meseBase: string): string[] {
  const [ay, am] = meseBase.split("-").map(Number);
  const n = new Date(ay, am, 0).getDate();
  return Array.from({ length: n }, (_, i) => `${meseBase}-${String(i + 1).padStart(2, "0")}`);
}

export interface SettimanaMese {
  giorni: string[];
  label: string;
}

// Settimane lun→dom intersecate col mese: i gruppi ai bordi sono parziali, non si
// sconfina nel mese adiacente (i turni caricati sono solo quelli di questo mese).
export function settimaneDelMese(meseBase: string): SettimanaMese[] {
  const gruppi: string[][] = [];
  for (const iso of giorniDelMese(meseBase)) {
    const dow = new Date(iso + "T00:00:00").getDay();
    if (dow === 1 || gruppi.length === 0) gruppi.push([iso]);
    else gruppi[gruppi.length - 1].push(iso);
  }
  return gruppi.map(giorni => {
    const primo = Number(giorni[0].split("-")[2]);
    const ultimo = Number(giorni[giorni.length - 1].split("-")[2]);
    return { giorni, label: primo === ultimo ? `${primo}` : `${primo}–${ultimo}` };
  });
}

function dowBreve(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return ["Do", "Lu", "Ma", "Me", "Gi", "Ve", "Sa"][d.getDay()];
}

function dowEsteso(iso: string): string {
  const d = new Date(iso + "T00:00:00");
  return ["Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"][d.getDay()];
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
  settimanaZoom,
  onZoomSettimana,
  onNuovoTurno,
  onModificaTurno,
  onModificaStatoGiorno,
}: VistaMensileGridProps) {
  const settimane = settimaneDelMese(meseBase);
  const zoom = settimanaZoom != null ? settimane[settimanaZoom] ?? null : null;
  const isZoom = zoom != null;
  const giorni = zoom?.giorni ?? giorniDelMese(meseBase);
  const gruppiVisibili = zoom ? [{ sett: zoom, idx: settimanaZoom as number }] : settimane.map((sett, idx) => ({ sett, idx }));

  // Il backend (ws_personale_list) filtra già .eq("attivo", True): nessun filtro client-side da fare qui.
  const dipendentiAttivi = dipendenti;

  // Pivot dipendente×giorno sull'intero mese: lo zoom filtra solo le colonne
  // rese, così cambiare zoom non ricostruisce la mappa.
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

  const thGiornoCls = isZoom ? "px-2 min-w-[92px]" : "px-1.5 min-w-[38px]";
  const primoDiSettimana = new Set(settimane.map(s => s.giorni[0]));

  return (
    <div className="rounded-lg border border-border overflow-auto">
      <table className="border-collapse text-xs w-full">
        <thead>
          <tr
            className="sticky top-0 z-10 bg-card"
            style={{ height: H_RIGA_SETTIMANA }}
          >
            <th
              rowSpan={2}
              className="sticky left-0 z-20 bg-card text-left font-semibold px-3 py-2 border-b border-r border-border min-w-[140px]"
            >
              Dipendente
            </th>
            {gruppiVisibili.map(({ sett, idx }) => (
              <th
                key={sett.giorni[0]}
                colSpan={sett.giorni.length}
                className={`border-b border-l border-border p-0 font-medium ${isZoom ? "bg-primary/10" : ""}`}
              >
                <button
                  onClick={() => onZoomSettimana(isZoom ? null : idx)}
                  title={isZoom ? "Torna a tutto il mese" : "Vedi questa settimana in dettaglio"}
                  className="w-full px-2 py-1 text-[11px] cursor-pointer select-none hover:bg-primary/10 transition-colors"
                >
                  {sett.label}
                </button>
              </th>
            ))}
          </tr>
          <tr
            className="sticky z-10 bg-card"
            style={{ top: H_RIGA_SETTIMANA }}
          >
            {giorni.map(iso => {
              const giorno = iso.split("-")[2];
              const weekend = isWeekend(iso);
              const isOggi = iso === oggi;
              return (
                <th
                  key={iso}
                  className={`py-2 border-b border-border font-medium ${thGiornoCls} ${
                    primoDiSettimana.has(iso) ? "border-l" : ""
                  } ${weekend ? "bg-muted/40" : ""} ${isOggi ? "bg-primary/10" : ""}`}
                >
                  <div className="flex flex-col items-center leading-tight">
                    <span className={isZoom ? "text-[11px] opacity-70" : "text-[9px] opacity-60"}>
                      {isZoom ? dowEsteso(iso) : dowBreve(iso)}
                    </span>
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
                  const tipo = tipoGiorno as Exclude<TipoGiorno, "turno">;
                  contenuto = isZoom ? (
                    <span className={`inline-block px-2 py-0.5 rounded-md text-[11px] font-medium ${TIPO_GIORNO_BADGE[tipo]}`}>
                      {TIPO_GIORNO_LABEL[tipoGiorno as TipoGiorno]}
                    </span>
                  ) : (
                    <span
                      className={`inline-flex items-center justify-center size-5 rounded text-[10px] font-semibold ${TIPO_GIORNO_CELL_CLASS[tipo]}`}
                      title={TIPO_GIORNO_LABEL[tipoGiorno as TipoGiorno]}
                    >
                      {TIPO_GIORNO_SIGLA[tipo]}
                    </span>
                  );
                } else if (t) {
                  const ore = calcolaOreTotali(t);
                  contenuto = (
                    <span className="flex flex-col items-center leading-tight tabular-nums" title={orarioTurno(t)}>
                      <span className={isZoom ? "text-[11px]" : "text-[10px]"}>
                        {isZoom ? orarioTurno(t) : fmtOra(t.ora_inizio)}
                      </span>
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
                      primoDiSettimana.has(iso) ? "border-l" : ""
                    } ${weekend ? "bg-muted/40" : ""} ${isOggi ? "bg-primary/5" : ""}`}
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
        Click su una cella per aggiungere o modificare il turno.{" "}
        {isZoom ? (
          <>Premi Esc o &ldquo;Tutto il mese&rdquo; per tornare alla vista mensile.</>
        ) : (
          <>Click sul numero di una settimana per vederla in dettaglio. R = riposo, F = ferie, M = malattia.</>
        )}{" "}
        Per impostare riposo/ferie/malattia su una cella vuota usa &ldquo;Riposo/ferie/malattia&rdquo; nella toolbar.
      </p>
    </div>
  );
}
