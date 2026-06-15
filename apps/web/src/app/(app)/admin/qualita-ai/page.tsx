import { redirect } from "next/navigation";

// La pagina "Qualità AI" è stata unificata nello strumento unico "Categorie".
// Manteniamo il redirect per non rompere vecchi link/bookmark.
export default function QualitaAiRedirect() {
  redirect("/admin/categorie");
}
