// Minimal service worker — just enough for PWA install eligibility (Chrome/
// Android requires a registered SW with a fetch handler). API calls always
// go straight to the network (never cached, always want fresh AI answers);
// everything else falls back to cache only if the network is unavailable,
// so the app shell still opens with no connection.
const CACHE = 'ledger-shell-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/api/')) return; // never intercept AI calls

  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
