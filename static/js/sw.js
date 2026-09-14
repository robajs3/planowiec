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

// ---- Push notifications ----
// Ścieżki liczymy z self.registration.scope (a nie hardkodujemy "/..."),
// bo ten plik nie przechodzi przez Jinja i nie zna window.APP_URL_PREFIX —
// patrz komentarz wyżej.
function scopeUrl(path) {
  return new URL(path, self.registration.scope).href;
}

self.addEventListener("push", function (event) {
  let data = { title: "Planowiec", body: "Masz nowe powiadomienie.", link: self.registration.scope };
  try {
    const parsed = event.data.json();
    data = { ...data, ...parsed };
  } catch {
    try { data.body = event.data.text(); } catch {}
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: scopeUrl("static/img/icon-192.png"),
      badge: scopeUrl("static/img/icon-72.png"),
      data: { link: data.link || self.registration.scope },
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  const link = event.notification.data?.link || self.registration.scope;
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url === link && "focus" in client) return client.focus();
      }
      if (clients.openWindow) return clients.openWindow(link);
    })
  );
});
