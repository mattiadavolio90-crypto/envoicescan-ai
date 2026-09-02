// Piani abbonamento — FONTE UNICA per area cliente e area admin.
// Prima erano due mappe divergenti: impostazioni/account-client.tsx conosceva
// solo base/plus/pro in Title Case, admin.ts free/base/plus/pro in MAIUSCOLO.
// Il backend (config/constants.py PIANO_LIMITI_FATTURE_MESE) conosce "free" e
// il menu admin lo offre: assegnarlo a una sede faceva mostrare al cliente la
// stringa grezza "free", perche' il fallback rende la chiave cosi' com'e'.

export type Piano = {
  label: string;       // resa cliente
  labelAdmin: string;  // resa admin (storicamente MAIUSCOLA)
  prezzo: string;
  limiteFatture: number;
};

export const PIANI: Record<string, Piano> = {
  // "free" non ha un prezzo da esporre: la dicitura spiega perche' manca la cifra.
  free: { label: "Free", labelAdmin: "FREE", prezzo: "Piano di prova", limiteFatture: 50 },
  base: { label: "Base", labelAdmin: "BASE", prezzo: "€39/mese + IVA", limiteFatture: 50 },
  plus: { label: "Plus", labelAdmin: "PLUS", prezzo: "€59/mese + IVA", limiteFatture: 100 },
  pro:  { label: "Pro",  labelAdmin: "PRO",  prezzo: "€79/mese + IVA", limiteFatture: 200 },
};

// Il piano arriva da JSON non validato e, lato admin, letto dal DB senza
// normalizzare: "Base" o " base " mancherebbero il match e cadrebbero nel
// fallback, mostrando la chiave grezza.
function normalizza(piano: string | null | undefined): string {
  return (piano ?? "").toLowerCase().trim();
}

export function etichettaPiano(piano: string | null | undefined): string {
  return PIANI[normalizza(piano)]?.label ?? piano ?? "";
}

export function etichettaPianoAdmin(piano: string | null | undefined): string {
  return PIANI[normalizza(piano)]?.labelAdmin ?? piano ?? "";
}

export function prezzoPiano(piano: string | null | undefined): string {
  return PIANI[normalizza(piano)]?.prezzo ?? "";
}
