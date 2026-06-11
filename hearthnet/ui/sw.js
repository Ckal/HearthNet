/**
 * HearthNet Service Worker
 * 
 * Enables offline-first functionality and caching for PWA.
 * Installed via manifest.json
 */

const CACHE_NAME = 'hearthnet-v0.1.0';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/styles.css',
];

/**
 * Install event: Pre-cache static assets
 */
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Caching static assets');
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('[Service Worker] Some assets failed to cache:', err);
        // Don't fail on cache errors (some assets may not exist)
      });
    })
  );
  self.skipWaiting();
});

/**
 * Activate event: Clean up old caches
 */
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

/**
 * Fetch event: Cache-first strategy for static assets, network-first for API calls
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // API calls: Network-first (always try server)
  if (url.pathname.startsWith('/api/') || 
      url.pathname.startsWith('/bus/') ||
      url.pathname.startsWith('/trace/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Cache successful responses
          if (response.status === 200) {
            const cache = caches.open(CACHE_NAME);
            cache.then((c) => c.put(request, response.clone()));
          }
          return response;
        })
        .catch(() => {
          // Fallback to cache if offline
          return caches.match(request).then((cached) => {
            if (cached) {
              console.log('[Service Worker] Serving from cache (offline):', request.url);
              return cached;
            }
            // Return offline page or error
            return new Response('Offline - API unavailable', {
              status: 503,
              statusText: 'Service Unavailable',
            });
          });
        })
    );
    return;
  }

  // Static assets: Cache-first
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request).then((response) => {
        if (response.status === 200) {
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, response.clone());
          });
        }
        return response;
      });
    })
  );
});

/**
 * Background sync: Queue API calls when offline
 */
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-messages') {
    event.waitUntil(
      // Implement message queue sync here
      Promise.resolve()
    );
  }
});

/**
 * Push notifications
 */
self.addEventListener('push', (event) => {
  const options = {
    body: event.data?.text() || 'New notification from HearthNet',
    icon: '/static/icon-192.png',
    badge: '/static/icon-96.png',
    tag: 'hearthnet-notification',
    requireInteraction: false,
  };

  event.waitUntil(
    self.registration.showNotification('HearthNet', options)
  );
});

console.log('[Service Worker] Loaded and ready');
