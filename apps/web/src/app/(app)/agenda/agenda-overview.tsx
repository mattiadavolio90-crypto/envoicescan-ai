"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, CalendarDays, Wallet, Users, Receipt, ArrowUpRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";

// ─── Fonti aggregate ────────────────────────────────────────────────────────

type Fonte = "appuntamento" | "spesa" | "turno" | "scadenza";

interface VoceAgenda {
  id: string;
  fonte: Fonte;
  data: string;            // YYYY-MM-DD
  titolo: string;
  dettaglio?: string;      // riga secondaria
  ora?: string;            // HH:MM se rilevante
  importo?: number;        // per spese/scadenze
}

const FONTI: Record<Fonte, { label: string; dot: string; chip: string; icon: typeof CalendarDays; href: string }> = {
  appuntamento: { label: "Appuntamenti", dot: "bg-sky-500",    chip: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",       icon: CalendarDays, href: "/agenda?layer=appuntamenti" },
  spesa:        { label: "Spese",        dot: "bg-orange-500", chip: "bg-orange-100 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200", icon: Wallet,       href: "/agenda?layer=spese" },
  turno:        { label: "Personale",    dot: "bg-violet-500", chip: "bg-violet-100 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200", icon: Users,        href: "/agenda?layer=personale" },
  scadenza:     { label: "Scadenze",     dot: "bg-red-500",    chip: "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200",       icon: Receipt,      href: "/scadenziario" },
};

// ─── Utilità date ─────────────────────────────────────────────────────────────

const MESI = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno","Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"];
const GIORNI_BREVI = ["L","M","M","G","V","S","D"];

function meseISO(anno: number, mese: number) {
  return `${anno}-${String(mese + 1).padStart(2, "0")}`;
}
function primoGiornoMese(anno: number, mese: number): number {
  const d = new Date(anno, mese, 1).getDay();
  return d === 0 ? 6 : d - 1;
}
function giorniNelMese(anno: number, mese: number) {
  return new Date(anno, mese + 1, 0).getDate();
}
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function fmtOra(t: string | null | undefined) {
  return t ? t.slice(0, 5) : "";
}
function fmtEuro(v: number) {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(v);
}

// ─── Tipi grezzi degli endpoint riusati ────────────────────────────────────────

interface EventoRaw { id: string; data_evento: string; titolo: string; ora_inizio?: string | null; ora_fine?: string | null; descrizione?: string | null; }
interface SpesaRaw { id: string; data_spesa: string; tipo: "fb" | "generale"; importo: number; descrizione: string; }
interface TurnoRaw { id: string; nome: string; data_turno: string; ora_inizio: string; ora_fine: string; }
interface ScadenzaRaw { id: string; fornitore: string; totale_documento: number; scadenza_effettiva: string | null; pagata: boolean; is_nota_credito?: boolean; numero_documento: string | null; }

// ─── Vista aggregata "Tutto" ───────────────────────────────────────────────────

export function AgendaOverview() {
  const today = todayISO();
  const now = new Date();
  const [anno, setAnno] = useState(now.getFullYear());
  const [mese, setMese] = useState(now.getMonth());
  const [giornoSel, setGiornoSel] = useState<string>(today);
  const [voci, setVoci] = useState<VoceAgenda[]>([]);
  const [loading, setLoading] = useState(false);
  // filtri fonte attivi
  const [fontiAttive, setFontiAttive] = useState<Set<Fonte>>(new Set(["appuntamento", "spesa", "turno", "scadenza"]));

  const da = `${meseISO(anno, mese)}-01`;
  const fine = `${meseISO(anno, mese)}-${String(giorniNelMese(anno, mese)).padStart(2, "0")}`;

  const load = useCallback(async (a: number, m: number) => {
    setLoading(true);
    const mISO = meseISO(a, m);
    const d0 = `${mISO}-01`;
    const dN = `${mISO}-${String(giorniNelMese(a, m)).padStart(2, "0")}`;
    try {
      const [evRes, spRes, tuRes, scRes] = await Promise.allSettled([
        fetch(`/api/workspace/diario?mese=${mISO}`).then(r => r.json()),
        fetch(`/api/workspace/spese?da=${d0}&a=${dN}`).then(r => r.json()),
        fetch(`/api/workspace/personale?da=${d0}&a=${dN}`).then(r => r.json()),
        fetch(`/api/scadenziario`).then(r => r.json()),
      ]);

      const out: VoceAgenda[] = [];

      if (evRes.status === "fulfilled") {
        for (const e of (evRes.value?.eventi ?? []) as EventoRaw[]) {
          out.push({
            id: `ev-${e.id}`, fonte: "appuntamento", data: e.data_evento,
            titolo: e.titolo,
            dettaglio: e.descrizione ?? undefined,
            ora: fmtOra(e.ora_inizio) || undefined,
          });
        }
      }
      if (spRes.status === "fulfilled") {
        for (const s of (spRes.value?.voci ?? []) as SpesaRaw[]) {
          out.push({
            id: `sp-${s.id}`, fonte: "spesa", data: s.data_spesa,
            titolo: s.descrizione,
            dettaglio: s.tipo === "fb" ? "Costo F&B" : "Spesa generale",
            importo: s.importo,
          });
        }
      }
      if (tuRes.status === "fulfilled") {
        for (const t of (tuRes.value?.turni ?? []) as TurnoRaw[]) {
          out.push({
            id: `tu-${t.id}`, fonte: "turno", data: t.data_turno,
            titolo: t.nome,
            dettaglio: `${fmtOra(t.ora_inizio)}–${fmtOra(t.ora_fine)}`,
            ora: fmtOra(t.ora_inizio) || undefined,
          });
        }
      }
      if (scRes.status === "fulfilled") {
        for (const doc of (scRes.value?.documenti ?? []) as ScadenzaRaw[]) {
          // Solo scadenze del mese in vista, non pagate, non note di credito
          if (doc.pagata || doc.is_nota_credito || !doc.scadenza_effettiva) continue;
          if (doc.scadenza_effettiva < d0 || doc.scadenza_effettiva > dN) continue;
          out.push({
            id: `sc-${doc.id}`, fonte: "scadenza", data: doc.scadenza_effettiva.slice(0, 10),
            titolo: doc.fornitore,
            dettaglio: doc.numero_documento ? `Fattura n. ${doc.numero_documento}` : "Fattura da pagare",
            importo: doc.totale_documento,
          });
        }
      }
      setVoci(out);
    } catch {
      toast.error("Errore caricamento agenda");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(anno, mese); }, [anno, mese, load]);

  function mesePrecedente() {
    if (mese === 0) { setAnno(a => a - 1); setMese(11); } else setMese(m => m - 1);
  }
  function meseSuccessivo() {
    if (mese === 11) { setAnno(a => a + 1); setMese(0); } else setMese(m => m + 1);
  }
  function toggleFonte(f: Fonte) {
    setFontiAttive(prev => {
      const next = new Set(prev);
      if (next.has(f)) next.delete(f); else next.add(f);
      return next;
    });
  }

  const vociVisibili = useMemo(() => voci.filter(v => fontiAttive.has(v.fonte)), [voci, fontiAttive]);

  const perGiorno = useMemo(() => {
    const map: Record<string, VoceAgenda[]> = {};
    for (const v of vociVisibili) (map[v.data] ??= []).push(v);
    return map;
  }, [vociVisibili]);

  const vociGiorno = (perGiorno[giornoSel] ?? []).slice().sort((a, b) =>
    (a.ora ?? "99:99").localeCompare(b.ora ?? "99:99")
  );

  const celle: (number | null)[] = [
    ...Array(primoGiornoMese(anno, mese)).fill(null),
    ...Array.from({ length: giorniNelMese(anno, mese) }, (_, i) => i + 1),
  ];

  const fmtGiornoLabel = (iso: string) => {
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("it-IT", { weekday: "long", day: "numeric", month: "long" });
  };

  return (
    <div className="space-y-4">
      {/* Filtri fonte */}
      <div className="flex flex-wrap items-center gap-2">
        {(Object.keys(FONTI) as Fonte[]).map(f => {
          const info = FONTI[f];
          const attiva = fontiAttive.has(f);
          const Icon = info.icon;
          return (
            <button
              key={f}
              onClick={() => toggleFonte(f)}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                attiva ? `${info.chip} border-transparent` : "border-border text-muted-foreground hover:text-foreground opacity-60"
              }`}
            >
              <Icon className="size-3.5" />
              {info.label}
            </button>
          );
        })}
        <Link
          href="/agenda?layer=appuntamenti"
          className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Gestisci appuntamenti <ArrowUpRight className="size-3" />
        </Link>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-4 items-start">
        {/* Calendario */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-3">
              <button onClick={mesePrecedente} className="p-1 rounded hover:bg-muted">
                <ChevronLeft className="size-4" />
              </button>
              <span className="text-sm font-semibold">{MESI[mese]} {anno}</span>
              <button onClick={meseSuccessivo} className="p-1 rounded hover:bg-muted">
                <ChevronRight className="size-4" />
              </button>
            </div>

            <div className="grid grid-cols-7 mb-1">
              {GIORNI_BREVI.map((g, i) => (
                <div key={i} className="text-center text-[10px] font-medium text-muted-foreground py-1">{g}</div>
              ))}
            </div>
            <div className="grid grid-cols-7 gap-1">
              {celle.map((giorno, i) => {
                if (!giorno) return <div key={`pad-${i}`} />;
                const iso = `${meseISO(anno, mese)}-${String(giorno).padStart(2, "0")}`;
                const isOggi = iso === today;
                const isSel = iso === giornoSel;
                const items = perGiorno[iso] ?? [];
                const fontiGiorno = Array.from(new Set(items.map(v => v.fonte)));
                return (
                  <button
                    key={iso}
                    onClick={() => setGiornoSel(iso)}
                    className={`flex flex-col items-center justify-start rounded-lg py-1.5 min-h-[44px] text-sm transition-colors ${
                      isSel ? "bg-primary text-primary-foreground font-semibold"
                      : isOggi ? "ring-1 ring-primary font-semibold"
                      : "hover:bg-muted"
                    }`}
                  >
                    <span>{giorno}</span>
                    {fontiGiorno.length > 0 && (
                      <div className="flex gap-0.5 mt-1">
                        {fontiGiorno.slice(0, 4).map(f => (
                          <span key={f} className={`size-1.5 rounded-full ${FONTI[f].dot} ${isSel ? "opacity-90" : ""}`} />
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Pannello giorno */}
        <div className="space-y-2">
          <h2 className="text-sm font-semibold capitalize">{fmtGiornoLabel(giornoSel)}</h2>
          {loading ? (
            <div className="py-10 text-center text-sm text-muted-foreground">Caricamento…</div>
          ) : vociGiorno.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">Niente in programma.</div>
          ) : (
            <div className="space-y-1.5">
              {vociGiorno.map(v => {
                const info = FONTI[v.fonte];
                return (
                  <Link
                    key={v.id}
                    href={info.href}
                    className="flex items-start gap-2.5 rounded-lg border border-border p-2.5 hover:bg-muted/40 transition-colors group"
                  >
                    <span className={`mt-1 size-2.5 rounded-full shrink-0 ${info.dot}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-sm truncate">{v.titolo}</span>
                        {v.ora && <span className="text-xs text-muted-foreground shrink-0">{v.ora}</span>}
                      </div>
                      {v.dettaglio && <p className="text-xs text-muted-foreground truncate">{v.dettaglio}</p>}
                    </div>
                    {v.importo != null && (
                      <span className={`text-sm font-semibold tabular-nums shrink-0 ${v.fonte === "scadenza" ? "text-red-600 dark:text-red-400" : ""}`}>
                        {fmtEuro(v.importo)}
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
