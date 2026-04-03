// Service worker for Chapter Tracker PWA.
// Strategy: network-first for navigation and static assets, skipping /api/* calls.
// Falls back to cache so the shell loads offline.

const CACHE = 'chapter-tracker-v1'
const PRECACHE_URLS = ['/', '/index.html']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  // Only intercept GET requests
  if (event.request.method !== 'GET') return

  const url = new URL(event.request.url)

  // Let API calls go through without caching — always want live data
  if (url.pathname.startsWith('/api')) return

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        // Cache successful responses for the app shell
        if (response.ok) {
          const clone = response.clone()
          caches.open(CACHE).then((cache) => cache.put(event.request, clone))
        }
        return response
      })
      .catch(() => caches.match(event.request))
  )
})
