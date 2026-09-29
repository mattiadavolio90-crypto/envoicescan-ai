"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  CHIAVE_VECCHIA,
  chiaveConversazione,
  codaPerVista,
  conRisposta,
  contatoreAggiornato,
  quotaEsaurita,
  type Conteggio,
  daSalvare,
  messaggioRisposta,
  parseConversazione,
  senzaVista,
  type Vista,
  type VoceChat,
} from "@/lib/home-chat";

// Le conversazioni con l'assistente, una per locale e una per la catena, per
// scheda del browser (28/9/2026; una per vista dal 29/9).
//
// Sta nel layout di (app) e non nella Home perche' deve sopravvivere al cambio
// di pagina e di sede: una domanda partita dalla Home arriva anche se nel
// frattempo il cliente e' andato altrove, e tornando la trova. La Home mostra
// quella della vista aperta, dentro il riquadro del briefing. Fino alla fase 5 vive in
// sessionStorage: resta finche' la scheda e' aperta, non passa al server.

type Quota = { limiteGiorno: number; domandeOggi: number };

type StatoAssistente = {
  pronta: boolean;
  voci: VoceChat[];
  /** Chiave della vista che aspetta una risposta, null se nessuna. */
  inCorso: string | null;
  /** 0, 1, 2: il messaggio d'attesa avanza col tempo. */
  attesa: number;
  /** Domande di oggi come le ha contate il backend nell'ultima risposta (una
   *  quota per account), col momento in cui e' arrivata. */
  domande: Conteggio | null;
  invia: (testo: string, vista: Vista, quota: Quota) => Promise<void>;
  /** Ricomincia la conversazione di questa vista; le altre restano. */
  nuova: (vistaChiave: string) => void;
};

const Contesto = createContext<StatoAssistente | null>(null);

export function useAssistente(): StatoAssistente {
  const c = useContext(Contesto);
  if (!c) throw new Error("useAssistente fuori da AssistenteProvider");
  return c;
}

export function AssistenteProvider({ utenteId, children }: { utenteId: string; children: React.ReactNode }) {
  const chiave = chiaveConversazione(utenteId);
  const [voci, setVoci] = useState<VoceChat[]>([]);
  const vociRef = useRef<VoceChat[]>([]);
  const [pronta, setPronta] = useState(false);
  const [inCorso, setInCorso] = useState<string | null>(null);
  const [attesa, setAttesa] = useState(0);
  const [domande, setDomande] = useState<Conteggio | null>(null);

  const aggiorna = useCallback((f: (v: VoceChat[]) => VoceChat[]) => {
    vociRef.current = f(vociRef.current);
    setVoci(vociRef.current);
  }, []);

  // sessionStorage non esiste in SSR: si legge dopo il mount.
  useEffect(() => {
    let salvate: VoceChat[] = [];
    try {
      salvate = parseConversazione(sessionStorage.getItem(chiave));
      sessionStorage.removeItem(CHIAVE_VECCHIA);
    } catch {
      /* Safari privato, storage disabilitato: si parte vuoti */
    }
    vociRef.current = salvate;
    setVoci(salvate);
    setPronta(true);
  }, [chiave]);

  useEffect(() => {
    if (!pronta) return;
    try {
      if (voci.length) sessionStorage.setItem(chiave, JSON.stringify(daSalvare(voci)));
      else sessionStorage.removeItem(chiave);
    } catch {
      /* quota piena: la conversazione resta a schermo, solo senza salvataggio */
    }
  }, [voci, pronta, chiave]);

  // L'assistente puo' metterci diversi secondi (legge le fatture, fa piu' giri):
  // un testo fermo sembra un blocco, uno che avanza dice che sta lavorando.
  useEffect(() => {
    if (!inCorso) {
      setAttesa(0);
      return;
    }
    const t1 = setTimeout(() => setAttesa(1), 2500);
    const t2 = setTimeout(() => setAttesa(2), 6000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [inCorso]);

  const inCorsoRef = useRef(false);
  const invia = useCallback(
    async (testo: string, vista: Vista, quota: Quota) => {
      const t = testo.trim();
      if (!t || inCorsoRef.current) return;
      inCorsoRef.current = true;
      aggiorna((v) => [...v, { role: "user", content: t, vista: vista.chiave }]);
      setInCorso(vista.chiave);
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ messages: codaPerVista(vociRef.current, vista), contesto: vista.contesto }),
        });
        const data = (await res.json()) as { reply?: string; error?: string; domande_oggi?: number };
        setDomande({
          valore: contatoreAggiornato(res.status, data, quota.limiteGiorno, quota.domandeOggi),
          alle: Date.now(),
          finita: quotaEsaurita(res.status, data),
        });
        aggiorna((v) => conRisposta(v, vista.chiave, messaggioRisposta(res.status, data)));
      } catch {
        aggiorna((v) => conRisposta(v, vista.chiave, "Errore di connessione. Controlla la rete e riprova."));
      } finally {
        inCorsoRef.current = false;
        setInCorso(null);
      }
    },
    [aggiorna],
  );

  const nuova = useCallback((vistaChiave: string) => aggiorna((v) => senzaVista(v, vistaChiave)), [aggiorna]);

  return (
    <Contesto.Provider value={{ pronta, voci, inCorso, attesa, domande, invia, nuova }}>
      {children}
    </Contesto.Provider>
  );
}
