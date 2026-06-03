/** @type {import('next').NextConfig} */
const nextConfig = {
  // Riduce il codice trascinato dagli import barrel di librerie pesanti:
  // recharts (grafici) e lucide-react (icone) sono i principali nel bundle.
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
};

export default nextConfig;
