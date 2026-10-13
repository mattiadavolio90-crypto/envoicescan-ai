"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { ChevronDown } from "lucide-react";
import { TAB_SEZIONI, tabOffKey, type SezioneConTab } from "@/lib/tab-flags";
import { INTERRUTTORI_CATENA, tabOffKeyCatena } from "@/lib/catena-schede";
import { RicaricheAiCliente } from "../ricariche-ai";
import { chiamaAdmin, messaggioErrore, type TabProps } from "./comune";

// `defaultOn` = stato mostrato quando la chiave non e' ancora a DB, e deve
// combaciare con il default del BACKEND che applica il flag. Non e' uniforme:
// upload_policy.py usa `cfg.get(BLOCCO_ANNO_KEY, True)` ma
// `cfg.get(BLOCCO_MESI_KEY, False)`. Con un fail-open uniforme il pannello
// mostrava acceso un blocco mesi che nessuno applicava — l'admin credeva di aver
// ristretto i caricamenti e non era vero. Se cambi un default qui, cambia il
// backend (o viceversa): tests/test_upload_policy.py presidia l'asimmetria.
//
// `sezione` collega la voce alle sue tab in TAB_SEZIONI (@/lib/tab-flags), che
// restano l'unica fonte: qui non si duplicano.
type Voce = { key: string; label: string; desc: string; defaultOn: boolean; sezione?: SezioneConTab };

const SEZIONI: Voce[] = [
  { key: "analisi_fatture", label: "Analisi Fatture", desc: "Visualizza e gestisci fatture", defaultOn: true, sezione: "analisi_fatture" },
  { key: "prezzi", label: "Osservatorio", desc: "Variazioni prezzi, sconti, note di credito, score fornitori", defaultOn: true, sezione: "prezzi" },
  { key: "margini", label: "Ricavi e Margini", desc: "Calcolo marginalità e analisi avanzate", defaultOn: true, sezione: "margini" },
  { key: "agenda", label: "Agenda", desc: "Appuntamenti, spese extra, turni del personale", defaultOn: true, sezione: "agenda" },
  { key: "workspace", label: "Strumenti", desc: "Foodcost e inventario di magazzino", defaultOn: true, sezione: "workspace" },
  { key: "analisi_e_tag", label: "Analisi e Tag", desc: "Tag personalizzati e analytics", defaultOn: true },
  { key: "scadenziario", label: "Gestione Fatture", desc: "Gestione scadenze e pagamenti", defaultOn: true, sezione: "scadenziario" },
];

const REGOLE_CARICAMENTO: Voce[] = [
  { key: "blocco_anno_precedente", label: "Blocca anno precedente", desc: "Impedisce il caricamento delle fatture dell'anno scorso", defaultOn: true },
  { key: "blocco_mesi_precedenti", label: "Blocca mesi precedenti", desc: "Consente solo mese corrente e precedente", defaultOn: false },
];

function Riga({ titolo, desc, children }: { titolo: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div className="min-w-0">
        <p className="text-sm font-medium">{titolo}</p>
        {desc && <p className="text-xs text-muted-foreground">{desc}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-3">{children}</div>
    </div>
  );
}

function Personalizza({ aperta, onToggle, spente, totale }: { aperta: boolean; onToggle: () => void; spente: number; totale: number }) {
  return (
    <button type="button" onClick={onToggle} className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <ChevronDown className={`size-3.5 transition-transform ${aperta ? "rotate-180" : ""}`} />
      Personalizza schede
      <span className={spente > 0 ? "font-medium text-amber-700" : ""}>
        ({spente > 0 ? `${spente} spente su ${totale}` : `tutte ${totale} accese`})
      </span>
    </button>
  );
}

export function FunzioniTab({ c, setC }: TabProps) {
  const flags = c.pagine_abilitate || {};
  const [aperte, setAperte] = useState<Record<string, boolean>>({});
  const apri = (k: string) => setAperte((p) => ({ ...p, [k]: !p[k] }));

  // `etichetta` e `acceso` esistono perche' per i flag a convenzione inversa
  // (tab, trigger servizi) il valore scritto e' l'OPPOSTO di cio' che l'admin ha
  // acceso: un toast che leggesse `enabled` direbbe "attivato" quando spegni, e
  // mostrerebbe la chiave grezza (`tab_off_analisi_fatture_categorie`).
  async function scriviFlag(key: string, enabled: boolean, etichetta: string, acceso?: boolean) {
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/flags`, "PATCH", { pagine_abilitate: { [key]: enabled } });
      setC((prev) => ({ ...prev, pagine_abilitate: { ...prev.pagine_abilitate, [key]: enabled } }));
      toast.success(`${etichetta} ${(acceso ?? enabled) ? "attivato" : "disattivato"}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  async function scriviChatAi(enabled: boolean) {
    try {
      await chiamaAdmin(`/api/admin/clienti/${c.id}/flags`, "PATCH", { chat_ai_enabled: enabled });
      setC((prev) => ({ ...prev, chat_ai_enabled: enabled }));
      toast.success(`Assistente AI ${enabled ? "attivato" : "disattivato"}`);
    } catch (e) {
      toast.error(messaggioErrore(e));
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Sezioni dell&apos;app</CardTitle></CardHeader>
        <CardContent className="divide-y">
          {SEZIONI.map((f) => {
            // `??` e non `!== false`: quest'ultimo tratta "assente" e true allo
            // stesso modo, e rende impossibile esprimere un default spento.
            const enabled = flags[f.key] ?? f.defaultOn;
            const tabs = f.sezione ? TAB_SEZIONI[f.sezione] : [];
            // Convenzione inversa: chiave presente = tab SPENTA.
            const spente = tabs.filter((t) => flags[tabOffKey(f.sezione as SezioneConTab, t.key)] === true).length;
            return (
              <div key={f.key} className="py-1">
                <Riga titolo={f.label} desc={f.desc}>
                  <Switch checked={enabled} onCheckedChange={(v: boolean) => scriviFlag(f.key, v, f.label)} />
                </Riga>
                {/* Tab figlie: solo a sezione accesa (spegnerla le rende
                    irraggiungibili comunque). I flag restano a DB e si
                    riapplicano se la sezione viene riaccesa. */}
                {enabled && tabs.length > 0 && (
                  <div className="pb-2">
                    <Personalizza aperta={!!aperte[f.key]} onToggle={() => apri(f.key)} spente={spente} totale={tabs.length} />
                    {aperte[f.key] && (
                      <div className="ml-1 pl-3 border-l space-y-1.5">
                        {tabs.map((t) => {
                          const chiave = tabOffKey(f.sezione as SezioneConTab, t.key);
                          const tabOn = flags[chiave] !== true;
                          return (
                            <div key={t.key} className="flex items-center justify-between gap-4">
                              <p className="text-xs text-muted-foreground">{t.label}</p>
                              <Switch
                                checked={tabOn}
                                onCheckedChange={(v: boolean) => scriviFlag(chiave, !v, `${f.label} › ${t.label}`, v)}
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
          {/* Catena (fase H3, 09/10/2026): non ha un interruttore di pagina,
              solo le schede, e le colonne dei coperti per chi non li
              registra. Solo per gli account con almeno due sedi: con una
              sola la vista di catena non esiste. Convenzione inversa, come
              le tab del PV: chiave presente = spenta. */}
          {c.sedi.length > 1 && (() => {
            const voci = INTERRUTTORI_CATENA.flatMap((g) => g.voci.map((v) => ({ g, v, chiave: tabOffKeyCatena(v.key) })));
            const spente = voci.filter((x) => flags[x.chiave] === true).length;
            return (
              <div className="py-1">
                <Riga titolo="Vista catena" desc="Schede della vista di gruppo" >{null}</Riga>
                <div className="pb-2">
                  <Personalizza aperta={!!aperte.catena} onToggle={() => apri("catena")} spente={spente} totale={voci.length} />
                  {aperte.catena && (
                    <div className="ml-1 pl-3 border-l space-y-1.5">
                      {voci.map(({ g, v, chiave }) => (
                        <div key={chiave} className="flex items-center justify-between gap-4">
                          <p className="text-xs text-muted-foreground">{g.pagina} › {v.label}</p>
                          <Switch
                            checked={flags[chiave] !== true}
                            onCheckedChange={(on: boolean) => scriviFlag(chiave, !on, `Catena › ${g.pagina} › ${v.label}`, on)}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })()}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Assistente AI</CardTitle></CardHeader>
        <CardContent className="divide-y">
          <Riga titolo="Chat AI" desc="La chat nella Home del cliente">
            <Switch checked={c.chat_ai_enabled} onCheckedChange={scriviChatAi} />
          </Riga>
          <div className="pt-3"><RicaricheAiCliente clienteId={c.id} /></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Altro</CardTitle></CardHeader>
        <CardContent className="divide-y">
          {/* Convenzione inversa: salviamo il flag solo da SPENTO
              (trigger_servizi_off). Assente = ON di default, anche per i
              clienti gia' esistenti. La lista pagine_abilitate lato cliente
              porta solo le chiavi true, quindi un OFF deve essere una chiave
              presente, non assente. Lo switch mostra l'opposto del flag-off. */}
          <Riga titolo="Suggerimenti servizi" desc="Hint discreti che propongono i servizi giusti nelle pagine">
            <Switch
              checked={flags.trigger_servizi_off !== true}
              onCheckedChange={(v: boolean) => scriviFlag("trigger_servizi_off", !v, "Suggerimenti servizi", v)}
            />
          </Riga>
          {REGOLE_CARICAMENTO.map((f) => (
            <Riga key={f.key} titolo={f.label} desc={f.desc}>
              <Switch checked={flags[f.key] ?? f.defaultOn} onCheckedChange={(v: boolean) => scriviFlag(f.key, v, f.label)} />
            </Riga>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
