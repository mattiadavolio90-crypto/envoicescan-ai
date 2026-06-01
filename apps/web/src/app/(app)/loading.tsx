import { LogoSpinner } from "@/components/brand/logo-spinner";

export default function Loading() {
  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center">
      <LogoSpinner size={48} glow label="Caricamento..." />
    </div>
  );
}
