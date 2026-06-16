import { redirect } from "next/navigation";

// Il Mapping Ragione Sociale è stato assorbito in Admin → Flusso dati.
// Redirect per compatibilità con vecchi link/bookmark.
export default function RagioneSocialeRedirect() {
  redirect("/admin/flusso-dati");
}
