// Service Worker Exclusivo - Shanti Studio Aluno (/aluno/)
const CACHE_NAME = 'shanti-aluno-pwa-v37';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME && (key.startsWith('shanti-aluno') || key.startsWith('shanti-pwa'))) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Ignora chamadas de API, métodos não-GET e qualquer requisição direcionada ao app de Gestão
  if (
    event.request.method !== 'GET' ||
    event.request.url.includes('/api/') ||
    event.request.url.includes('/gestao')
  ) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => networkResponse)
      .catch(() => caches.match(event.request))
  );
});
