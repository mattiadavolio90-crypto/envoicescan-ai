import { Marketplace } from "./marketplace";

export default function AssistenzaPage() {
  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Servizi</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Servizi pensati per il tuo locale. Scegli quello che ti serve: ti
          ricontatto io, senza impegno.
        </p>
      </div>

      <Marketplace />
    </div>
  );
}
