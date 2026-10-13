import { getCurrentSession } from "@/lib/auth";
import { ImpostazioniClient } from "./impostazioni-client";

// Pagina client-driven: i dati account si caricano dopo il mount (vedi
// impostazioni-client). Evitiamo SSR bloccante verso il worker, che causava
// "this page couldn't load" nel WebView della PWA quando la chiamata era lenta.
export const dynamic = "force-dynamic";

export default async function MobileImpostazioniPage() {
  // Con piu' sedi i ricavi senza IVA si eliminano solo dalla catena sul desktop,
  // dove si scelgono le sedi: su /m il riquadro non compare.
  // getCurrentSession e' la stessa cache() del layout: nessuna /api/auth/me in piu'.
  const session = await getCurrentSession();
  const numSedi = session.status === "ok" ? (session.user.num_sedi ?? null) : null;
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold tracking-tight">Account</h1>
      <ImpostazioniClient numSedi={numSedi} />
    </div>
  );
}
