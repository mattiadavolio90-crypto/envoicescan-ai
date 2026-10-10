import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { fetchBriefing, fetchConfig } from "@/lib/home";
import { vistaCatena, vistaSede } from "@/lib/home-chat";
import { getCurrentUser } from "@/lib/auth";
import { haCatena } from "@/lib/sotto-utente";
import { requireTabMobile } from "@/lib/page-guard";
import { MobileChat } from "./mobile-chat";

export default async function MobileChatPage() {
  await requireTabMobile("/m/chat");
  // Stessa regola della bottom nav: chat solo se abilitata e piano con limite.
  // Guard anche qui per chi arriva via URL diretto a tab nascosta.
  // Config, briefing e utente si leggono insieme: in fila la pagina aspettava
  // piu' giri. Il briefing serve solo nel locale; in catena si scarta.
  const [config, briefing, utente, cookieStore] = await Promise.all([
    fetchConfig(),
    fetchBriefing(),
    getCurrentUser(),
    cookies(),
  ]);
  const chatEnabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
  if (!chatEnabled) redirect("/m/briefing");

  // In catena (stessa regola di /m/briefing) la chat parla del gruppo, come
  // l'intestazione che dice «Tutti i punti vendita»; nel locale, di quel locale
  // e le domande nascono dal briefing di oggi (fase F). Briefing assente = le
  // domande fisse di sempre.
  const inChain = !!utente && haCatena(utente) && cookieStore.get("oneflux_view")?.value !== "pv";

  return (
    <MobileChat
      vista={inChain ? vistaCatena() : vistaSede(utente?.sede_attiva_id)}
      temi={inChain ? undefined : briefing?.temi}
      settore={utente?.tipo_attivita}
      limiteGiorno={config?.chat_limite_giorno ?? 0}
      domandeOggiIniziali={config?.chat_domande_oggi ?? 0}
      lettoAlle={Date.now()}
    />
  );
}
