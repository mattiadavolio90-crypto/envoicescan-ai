import { redirect } from "next/navigation";
import { fetchBriefing, fetchConfig } from "@/lib/home";
import { domandeDalBriefing } from "@/lib/home-chat";
import { getCurrentUser } from "@/lib/auth";
import { requireTabMobile } from "@/lib/page-guard";
import { MobileChat } from "./mobile-chat";

export default async function MobileChatPage() {
  await requireTabMobile("/m/chat");
  // Stessa regola della bottom nav: chat solo se abilitata e piano con limite.
  // Guard anche qui per chi arriva via URL diretto a tab nascosta.
  const config = await fetchConfig();
  const chatEnabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
  if (!chatEnabled) redirect("/m/briefing");

  // Le domande proposte dal briefing di oggi, come in Home (fase F). Il
  // telefono non ha ancora la «Conferma» delle cifre (fase I): niente domande
  // per registrare. Briefing assente = le domande fisse di sempre.
  const [briefing, utente] = await Promise.all([fetchBriefing(), getCurrentUser()]);
  const suggerimenti = domandeDalBriefing(briefing?.temi, utente?.tipo_attivita, { registra: false });

  return <MobileChat suggerimenti={suggerimenti} />;
}
