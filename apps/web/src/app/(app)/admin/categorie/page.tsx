import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { CategorieClient } from "./categorie-client";

export default async function CategoriePage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");
  return <CategorieClient />;
}
