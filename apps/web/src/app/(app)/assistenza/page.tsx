import { PageHeader } from "@/components/ui/page-header";
import { Marketplace } from "./marketplace";

export default function AssistenzaPage() {
  return (
    <div className="space-y-6 max-w-5xl">
      <PageHeader
        icon="lifebuoy"
        title="Servizi"
        subtitle="Supporto operativo e consulenze mirate per migliorare margini, costi e presenza del tuo locale. Scegli quello che ti serve: ti ricontatto io, senza impegno."
      />

      <Marketplace />
    </div>
  );
}
