import type { MetadataRoute } from "next";

// /robots.txt generato da Next. La landing pubblica e le pagine legali sono
// indicizzabili; le aree applicative private (richiedono login: non hanno valore
// SEO e non devono finire nell'indice) sono escluse. Sitemap dichiarata in fondo.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/login", "/dashboard", "/admin", "/m", "/api"],
    },
    sitemap: "https://oneflux.it/sitemap.xml",
    host: "https://oneflux.it",
  };
}
