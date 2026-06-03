// Service worker ONEFLUX PWA.
// Scopo: installabilita' + cache degli asset statici immutabili, per rendere la
// navigazione tra tab robusta ai cali di rete. ONEFLUX e' un'app di analisi
// online-first: i DATI devono restare sempre freschi, quindi NON cachiamo mai
// le navigazioni HTML, le richieste RSC (?_rsc=) ne' le /api/*.
//
// IMPORTANTE — storia di questo file: un vecchio handler "fetch" network-first
// sulle NAVIGAZIONI, in modalita' standalone (WebView PWA), gestiva male i
// redirect di auth e mostrava "this page couldn't load". Per questo qui
// intercettiamo ESCLUSIVAMENTE /_next/static/* : sono file con hash nel nome
// (immutabili), quindi cache-first e' sicuro al 100%. Per ogni altra richiesta
// NON chiamiamo respondWith(): la lascia gestire nativamente al browser, come
// se il SW non ci fosse.

const CACHE = "oneflux-static-v4";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Pulisce le cache delle versioni precedenti (incluse quelle dei vecchi SW).
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Tocchiamo SOLO le GET degli asset statici di Next con hash nel nome.
  // Tutto il resto (navigazioni HTML, RSC, /api/*, POST) NON viene intercettato.
  if (req.method !== "GET") return;

  let url;
  try {
    url = new URL(req.url);
  } catch {
    return;
  }

  // Solo stesso-origine e solo /_next/static/* (chunk JS/CSS immutabili).
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith("/_next/static/")) return;

  // Cache-first: se l'asset e' gia' in cache lo serviamo subito (navigazione
  // istantanea, immune ai cali di rete); altrimenti lo scarichiamo e lo
  // mettiamo in cache per le volte successive. Essendo file con hash nel nome,
  // non diventano mai stantii.
  event.respondWith(
    caches.match(req).then((cached) => {
      if (cached) return cached;
      return fetch(req).then((res) => {
        // Mettiamo in cache solo risposte valide.
        if (res && res.ok) {
          const copia = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copia));
        }
        return res;
      });
    }),
  );
});
