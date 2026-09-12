const CACHE_NAME = 'shanti-studio-pwa-v11';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          // Limpa todos os caches antigos imediatamente
          return caches.delete(key);
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Não interceptar chamadas de API nem requisições que não sejam GET (como envio de áudio e chat)
  if (event.request.method !== 'GET' || event.request.url.includes('/api/')) {
    return;
  }

  // Sempre buscar da rede primeiro (Network-First) para refletir o design na hora
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        return networkResponse;
      })
      .catch(() => {
        return caches.match(event.request);
      })
  );
});
