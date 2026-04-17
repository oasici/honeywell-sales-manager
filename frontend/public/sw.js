// Service Worker — network-first, no aggressive caching
// Prevents stale chunk issues after deployments

const CACHE_NAME = 'hsm-v2';

self.addEventListener('install', () => {
  // Immediately activate — don't wait for old tabs to close
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  // Clear ALL old caches on activation
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Network-first for navigation (always get fresh index.html)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html'))
    );
    return;
  }
  // Network-first for all other requests (no caching)
  event.respondWith(fetch(event.request));
});
