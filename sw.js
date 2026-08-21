// Service worker de rescate.
//
// index.html dejo de registrar ningun service worker el 8 de mayo de 2026, pero
// quitar el <script> de registro NO desinstala los que ya estaban activos: los
// navegadores que visitaron la web entre el 20 y el 28 de abril, o el 7 y el 8 de
// mayo, quedaron con 'pinplan-v4' sirviendo index.html desde cache (cache-first),
// es decir, viendo una version congelada de la web para siempre.
//
// Este fichero se limita a deshacer eso: borra las caches, se desregistra y
// recarga las pestanas abiertas para que reciban la version publicada.
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.map(k => caches.delete(k)));
    await self.registration.unregister();
    const clients = await self.clients.matchAll({ type: 'window' });
    clients.forEach(c => c.navigate(c.url));
  })());
});

// Mientras siga vivo, nunca servir desde cache: siempre la red.
self.addEventListener('fetch', e => e.respondWith(fetch(e.request)));
