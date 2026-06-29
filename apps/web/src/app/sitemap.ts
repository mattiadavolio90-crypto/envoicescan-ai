import type { MetadataRoute } from "next";

// /sitemap.xml generato da Next. Solo le route PUBBLICHE reali (verificate: "/",
// "/privacy", "/termini"). Le aree applicative sono dietro login e fuori dalla
// sitemap. Quando nascerà l'hub contenuti (/risorse), i nuovi articoli si
// aggiungono qui — è il segnale primario con cui Google scopre le pagine.
const BASE = "https://oneflux.it";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: BASE,
      changeFrequency: "weekly",
      priority: 1,
    },
    {
      url: `${BASE}/privacy`,
      changeFrequency: "yearly",
      priority: 0.3,
    },
    {
      url: `${BASE}/termini`,
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];
}
