// Service worker minimale ONEFLUX PWA.
// Scopo: rendere l'app installabile (requisito PWA). ONEFLUX e' un'app di
// analisi online-first: i dati devono essere sempre freschi, niente offline
// aggressivo.
//
// IMPORTANTE: NON intercettiamo le navigazioni. Un handler "fetch" network-first
// sulle navigazioni, in modalita' standalone (WebView PWA), gestiva male i
// redirect di auth/proxy e mostrava "this page couldn't load" su alcune pagine
// (es. /m/impostazioni). Lasciando che sia il WebView a gestire le navigazioni
// nativamente il problema sparisce e l'app resta installabile.

const CACHE = "oneflux-shell-v3";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  // Pulisce eventuali cache delle versioni precedenti (incluso l'offline.html
  // del vecchio handler di navigazione).
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

// Nessun handler "fetch": tutte le richieste (navigazioni, asset, /api/*) vanno
// in rete normalmente, gestite dal browser. Il SW esiste solo per installabilita'.
