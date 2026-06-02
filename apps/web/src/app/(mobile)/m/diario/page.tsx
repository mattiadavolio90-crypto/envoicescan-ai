import { MobileDiario } from "./mobile-diario";

// Pagina interamente client-driven (fetch da useEffect): evitiamo qualsiasi
// tentativo di prerender statico.
export const dynamic = "force-dynamic";

export default function MobileDiarioPage() {
  return <MobileDiario />;
}
