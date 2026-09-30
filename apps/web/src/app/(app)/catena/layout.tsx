import { requireCatena } from "@/lib/page-guard";

// Tutte le pagine di catena leggono ogni sede dell'account: un sotto-utente ci
// entra solo con la Catena (che il worker concede solo con tutte le sedi).
export default async function CatenaLayout({ children }: { children: React.ReactNode }) {
  await requireCatena();
  return children;
}
