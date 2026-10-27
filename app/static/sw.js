// Minimal service worker: makes Sightline installable and shows the app shell offline.
// Never caches /api, /approve or /link: shopping and checkout always need the live server.
const CACHE = 'sightline-shell-v1';
const SHELL = ['/', '/static/style.css', '/static/app.js', '/static/manifest.webmanifest', '/static/icon-192.png'];
self.addEventListener('install', (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))));
self.addEventListener('activate', (e) => e.waitUntil(
  caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))));
self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || !SHELL.includes(url.pathname)) return;  // network only
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));    // network first, shell from cache offline
});
