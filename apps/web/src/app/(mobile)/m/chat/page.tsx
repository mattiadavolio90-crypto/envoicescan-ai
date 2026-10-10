import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { fetchBriefing, fetchConfig } from "@/lib/home";
import { fetchGruppoChatConfig } from "@/lib/gruppo";
import { chatCatenaAttiva } from "@/lib/catena-confronti";
import { vistaCatena, vistaSede } from "@/lib/home-chat";
import { getCurrentUser } from "@/lib/auth";
import { haCatena } from "@/lib/sotto-utente";
import { requireTabMobile } from "@/lib/page-guard";
import { MobileChat } from "./mobile-chat";

export default async function MobileChatPage() {
  await requireTabMobile("/m/chat");
  // Config, briefing e utente si leggono insieme: in fila la pagina aspettava
  // piu' giri. Il briefing serve solo nel locale; in catena si scarta.
  const [config, briefing, utente, cookieStore] = await Promise.all([
    fetchConfig(),
    fetchBriefing(),
    getCurrentUser(),
    cookies(),
  ]);

  // In catena (stessa regola di /m/briefing) la chat parla del gruppo, come
  // l'intestazione che dice «Tutti i punti vendita», e vale la regola della Home
  // di catena: pool AI del gruppo e interruttore di gruppo (`chatCatenaAttiva`).
  // Nel locale, di quel locale, con le domande del briefing di oggi (fase F).
  const inChain = !!utente && haCatena(utente) && cookieStore.get("oneflux_view")?.value !== "pv";
  const gruppo = inChain ? await fetchGruppoChatConfig() : null;
  const chatEnabled = inChain
    ? chatCatenaAttiva(gruppo)
    : (config?.chat_ai_enabled ?? true) && (config?.chat_limite_giorno ?? 0) > 0;
  if (!chatEnabled) redirect("/m/briefing");

  return (
    <MobileChat
      vista={inChain ? vistaCatena() : vistaSede(utente?.sede_attiva_id)}
      temi={inChain ? undefined : briefing?.temi}
      settore={utente?.tipo_attivita}
      limiteGiorno={(inChain ? gruppo?.limite_giorno : config?.chat_limite_giorno) ?? 0}
      domandeOggiIniziali={(inChain ? gruppo?.domande_oggi : config?.chat_domande_oggi) ?? 0}
      lettoAlle={Date.now()}
    />
  );
}
