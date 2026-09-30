import { MobileDiario } from "./mobile-diario";
import { requireTabMobile } from "@/lib/page-guard";

// Pagina interamente client-driven (fetch da useEffect): evitiamo qualsiasi
// tentativo di prerender statico.
export const dynamic = "force-dynamic";

export default async function MobileDiarioPage() {
  await requireTabMobile("/m/diario");
  return <MobileDiario />;
}
