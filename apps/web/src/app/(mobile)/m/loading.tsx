import { LogoSpinner } from "@/components/brand/logo-spinner";

// Loading mobile: stesso spinner di brand pulsante del desktop, mostrato durante
// il caricamento delle pagine /m (cambio tab, refresh).
export default function Loading() {
  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center">
      <LogoSpinner size={48} glow label="Caricamento..." />
    </div>
  );
}
