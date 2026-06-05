/** @type {import('next').NextConfig} */
const nextConfig = {
  // Riduce il codice trascinato dagli import barrel di librerie pesanti:
  // recharts (grafici) e lucide-react (icone) sono i principali nel bundle.
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
  // Security header: l'app non definiva nulla -> niente protezione clickjacking
  // ne' Referrer-Policy. CSP omessa di proposito (richiede test dedicati per non
  // rompere recharts/inline styles); aggiunti i tre header a basso rischio.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
