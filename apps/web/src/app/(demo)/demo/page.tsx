import { DemoShell } from "./demo-shell";

// Pagina statica: nessun dato dal server, tutto il tour vive client-side con i
// dati finti di lib/demo-data.ts. Il server component esiste solo per montare
// la shell (un client component) e restare una route App Router normale.
export default function DemoPage() {
  return <DemoShell />;
}
