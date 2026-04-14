// Service Worker for POS PWA
const CACHE_NAME = 'pos-cache-v1';
const urlsToCache = [
  '/pos/',
  '/dashboard/',
  '/cafe_tables/',
  '/static/img/pwa-icon-192.png',
  '/static/img/pwa-icon-512.png',
];

// Install
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      console.log('[SW] Caching app shell');
      return cache.addAll(urlsToCache).catch(err => {
        console.log('[SW] Cache addAll failed (pages require auth):', err);
      });
    })
  );
  self.skipWaiting();
});

// Activate - cleanup old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(names => {
      return Promise.all(
        names.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Fetch - Network first, fall back to cache
self.addEventListener('fetch', event => {
  // Skip non-GET and API requests 
  if (event.request.method !== 'GET') return;
  if (event.request.url.includes('/api/')) return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses for static assets
        if (response.ok && (
          event.request.url.includes('/static/') ||
          event.request.url.includes('/media/')
        )) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // Offline fallback
        return caches.match(event.request);
      })
  );
});
