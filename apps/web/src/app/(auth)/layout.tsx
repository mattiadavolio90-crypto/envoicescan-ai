import type { Metadata } from "next";

// Login/recupero password: la tab mostra il brand, non il claim commerciale
// del root (che resta alla landing pubblica "/").
export const metadata: Metadata = {
  // absolute: bypassa il template "%s · ONEFLUX" del root, che senza darebbe
  // "ONEFLUX · ONEFLUX". Il template va ridichiarato: absolute lo azzera per le
  // pagine figlie, che altrimenti perderebbero il suffisso di brand in silenzio.
  title: { absolute: "ONEFLUX", template: "%s · ONEFLUX" },
};

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      {children}
    </div>
  );
}
