import { ImpostazioniClient } from "./impostazioni-client";

// Pagina client-driven: i dati account si caricano dopo il mount (vedi
// impostazioni-client). Evitiamo SSR bloccante verso il worker, che causava
// "this page couldn't load" nel WebView della PWA quando la chiamata era lenta.
export const dynamic = "force-dynamic";

export default function MobileImpostazioniPage() {
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold tracking-tight">Account</h1>
      <ImpostazioniClient />
    </div>
  );
}
