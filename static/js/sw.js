// Planowiec Service Worker
//
// Rejestrowany pod {PREFIX}/sw.js (patrz app.js), żeby scope obejmował
// całą appkę nawet gdy jest wystawiona pod prefiksem (np. Tailscale Serve
// --set-path /planowiec). Ten plik jest zwykłym statycznym JS-em i NIE
// przechodzi przez Jinja, więc nie ma dostępu do window.APP_URL_PREFIX —
// jeśli kiedyś trzeba będzie tu dodać cache'owanie plików, ścieżki należy
// budować z self.registration.scope, a nie hardkodować "/static/...".

// Minimalny fetch handler — samo jego istnienie (nawet bez własnego
// cache'owania) jest wymagane przez Chrome/Android, żeby uznać stronę za
// instalowalną jako PWA. Nie cache'ujemy niczego na własną rękę, żeby nie
// serwować nieaktualnych danych kalendarza.
self.addEventListener("fetch", function (event) {
  // no-op: przepuszczamy request bez zmian
});

self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});
