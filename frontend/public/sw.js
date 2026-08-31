// Minimal service worker: makes the app installable and speeds up repeat
// loads of the built JS/CSS. Deliberately never caches /api/, /iclock/, or
// /media/ — attendance and employee data must always come from the network.
const CACHE = "mekawy-erp-shell-v1";

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const bypass =
    url.pathname.startsWith("/api/") ||
    url.pathname.startsWith("/iclock/") ||
    url.pathname.startsWith("/media/") ||
    url.pathname.startsWith("/admin/");
  if (bypass) return; // let the browser handle it normally, no SW caching

  // Hashed Next.js build assets: safe to cache-first, they never change content.
  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.open(CACHE).then(async (cache) => {
        const cached = await cache.match(request);
        if (cached) return cached;
        const res = await fetch(request);
        if (res.ok) cache.put(request, res.clone());
        return res;
      })
    );
    return;
  }

  // Everything else (pages): network-first, fall back to cache if offline.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) caches.open(CACHE).then((cache) => cache.put(request, res.clone()));
        return res;
      })
      .catch(() => caches.match(request))
  );
});
