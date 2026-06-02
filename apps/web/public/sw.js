// Service worker minimale ONEFLUX PWA.
// Scopo: rendere l'app installabile (requisito PWA) e dare un fallback offline
// gentile. NON facciamo precaching/offline aggressivo: ONEFLUX e' un'app di
// analisi, i dati devono essere sempre freschi (network-first), mai stale.

const CACHE = "oneflux-shell-v2";
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll([OFFLINE_URL])),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

// Solo per le navigazioni: lasciamo passare la richiesta in rete col redirect
// gestito dal browser ("manual" romperebbe i redirect di auth/proxy mostrando
// una pagina vuota o errore). Interveniamo SOLO se la rete e' davvero giu',
// servendo la pagina di cortesia offline. Tutto il resto (asset, /api/*) non
// viene intercettato.
self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  if (request.mode !== "navigate") return;

  event.respondWith(
    fetch(request).catch(() =>
      caches.match(OFFLINE_URL).then((r) => r ?? new Response("Offline", { status: 503 })),
    ),
  );
});
