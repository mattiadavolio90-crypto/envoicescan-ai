import { redirect } from "next/navigation";

// Landing in lavorazione: la root non deve mostrarla.
// Manda all'app: se non loggato il layout (app) reindirizza a /login.
export default function Home() {
  redirect("/dashboard");
}
