import { redirect } from "next/navigation";
import { fetchConfig } from "@/lib/home";
import { MobileChat } from "./mobile-chat";

export default async function MobileChatPage() {
  // Stessa regola della bottom nav: chat solo se abilitata e piano con limite.
  // Guard anche qui per chi arriva via URL diretto a tab nascosta.
  const config = await fetchConfig();
  const chatEnabled = (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
  if (!chatEnabled) redirect("/m/briefing");

  return <MobileChat />;
}
