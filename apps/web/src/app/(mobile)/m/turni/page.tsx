import { MobileTurni } from "./mobile-turni";
import { getCurrentUser } from "@/lib/auth";

// Pagina interamente client-driven (fetch da useEffect): evitiamo qualsiasi
// tentativo di prerender statico.
export const dynamic = "force-dynamic";

export default async function MobileTurniPage() {
  // Il settore arriva dalla sessione lato server. Serve qui perche' le
  // etichette dei costi sono diverse per un negozio, e /m e' un frontend
  // separato che va allineato a mano. Costa un /api/auth/me per render:
  // getCurrentUser e' in cache(), ma il layout usa getCurrentSession, che e'
  // una entry diversa sopra un verifySession non memoizzato.
  const user = await getCurrentUser();
  return <MobileTurni settore={user?.tipo_attivita} />;
}
