const CACHE_NAME = 'md5-scribe-v6'
const APP_SHELL = ['./index.html', './favicon.svg']

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)))
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)),
    )),
  )
  self.clients.claim()
})

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok && response.headers.get('content-type')?.includes('text/html')) {
            caches.open(CACHE_NAME).then((cache) => cache.put('./index.html', response.clone()))
          }
          return response
        })
        .catch(() => caches.match('./index.html')),
    )
    return
  }

  event.respondWith(
    fetch(event.request)
      .then(async (response) => {
        const contentType = response.headers.get('content-type') || ''
        const isAsset = contentType.includes('javascript') || contentType.includes('css') || contentType.startsWith('image/')
        if (response.ok && isAsset && new URL(event.request.url).origin === self.location.origin) {
          const cache = await caches.open(CACHE_NAME)
          cache.put(event.request, response.clone())
        }
        return response
      })
      .catch(() => caches.match(event.request)),
  )
})
