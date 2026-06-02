import { fetchBriefing } from "@/lib/home";
import { MobileBriefing } from "./mobile-briefing";

export default async function MobileBriefingPage() {
  const briefing = await fetchBriefing();

  if (!briefing) {
    return (
      <div className="py-20 text-center text-sm text-muted-foreground">
        Impossibile caricare il briefing. Riprova più tardi.
      </div>
    );
  }

  return <MobileBriefing briefing={briefing} />;
}
