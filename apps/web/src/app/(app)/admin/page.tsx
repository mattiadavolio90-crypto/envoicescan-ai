import { cookies } from "next/headers";
import { SESSION_COOKIE } from "@/lib/auth";
import { OggiClient } from "./oggi-client";
import { datiOggi } from "./oggi-dati";

// La pagina di apertura dell'admin: cosa c'e' da fare oggi (riordino del
// 13/10/2026). L'accesso admin lo controlla admin/layout.tsx.
export default async function AdminOggiPage() {
  const store = await cookies();
  return <OggiClient iniziale={await datiOggi(store.get(SESSION_COOKIE)?.value ?? "")} />;
}
