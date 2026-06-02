import { PageHeader } from "@/components/ui/page-header";
import { Marketplace } from "./marketplace";

export default function AssistenzaPage() {
  return (
    <div className="space-y-6 max-w-5xl">
      <PageHeader
        icon="lifebuoy"
        title="Servizi"
        hint="Servizi pensati per il tuo locale. Scegli quello che ti serve: ti ricontatto io, senza impegno."
      />

      <Marketplace />
    </div>
  );
}
