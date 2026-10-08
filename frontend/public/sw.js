/* XiloScan — service worker (shell offline + instalável). Sem libs. */
const CACHE = 'xiloscan-shell-v1';
const SHELL = [
  '/', '/index.html', '/manifest.webmanifest',
  '/icon.svg', '/icon-192.png', '/icon-512.png', '/apple-touch-icon.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (e) => {
  const { request } = e;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);

  // nunca intercepta outra origem (API no Railway/ngrok) nem chamadas /api ou /static
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/static')) return;

  // HTML: network-first (pega atualizações), cai no cache quando offline
  if (request.mode === 'navigate') {
    e.respondWith(
      fetch(request)
        .then((r) => { const cp = r.clone(); caches.open(CACHE).then((c) => c.put('/', cp)); return r; })
        .catch(() => caches.match('/').then((r) => r || caches.match('/index.html'))),
    );
    return;
  }

  // demais assets (JS/CSS/ícones com hash): cache-first
  e.respondWith(
    caches.match(request).then((cached) => cached || fetch(request).then((r) => {
      if (r.ok) { const cp = r.clone(); caches.open(CACHE).then((c) => c.put(request, cp)); }
      return r;
    })),
  );
});
