import { fetchBriefing, fetchSalute, fetchKpi } from "@/lib/home";
import { SaluteCard } from "@/app/(app)/dashboard/salute-card";
import { KpiBlock } from "@/app/(app)/dashboard/kpi-block";
import { MobileBriefing } from "./mobile-briefing";

export default async function MobileBriefingPage() {
  const [briefing, salute, kpi] = await Promise.all([
    fetchBriefing(),
    fetchSalute(),
    fetchKpi(),
  ]);

  return (
    <div className="space-y-5">
      {briefing ? (
        <MobileBriefing briefing={briefing} />
      ) : (
        <div className="py-10 text-center text-sm text-muted-foreground">
          Impossibile caricare il briefing. Riprova più tardi.
        </div>
      )}

      {/* Stessa Home del desktop, impilata verticale: i due componenti sono
          gia' responsive (server component puri), li riusiamo senza duplicare. */}
      {kpi && <KpiBlock kpi={kpi} />}
      {salute && <SaluteCard salute={salute} />}
    </div>
  );
}
