document.addEventListener("DOMContentLoaded", () => {
  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    const root = document.documentElement;
    const syncIcon = () => {
      themeToggle.textContent = root.getAttribute("data-theme") === "dark" ? "☀️" : "🌙";
    };
    syncIcon();
    themeToggle.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      localStorage.setItem("planowiec-theme", next);
      syncIcon();
    });
  }

  const toggle = document.getElementById("menu-toggle");
  const sidebar = document.getElementById("sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (window.innerWidth > 900) return;
      if (!sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove("open");
      }
    });
  }

  document.querySelectorAll(".alert").forEach((alert) => {
    setTimeout(() => {
      alert.style.transition = "opacity .3s ease";
      alert.style.opacity = "0";
      setTimeout(() => alert.remove(), 300);
    }, 4500);
  });

  registerServiceWorker();
});

// PWA: rejestrujemy Service Workera pod {PREFIX}/sw.js, NIE pod
// "/static/js/sw.js" — gdy appka stoi pod prefiksem (np. Tailscale Serve
// --set-path /planowiec), bezwzględna ścieżka bez prefiksu nigdy nie
// trafi do backendu. "/sw.js" jest osobno serwowany w app.py z nagłówkiem
// Service-Worker-Allowed, żeby scope objął cały prefiks appki. Rejestracja
// samej obecności Service Workera (nawet bez cache'owania) jest jednym z
// warunków, które przeglądarka sprawdza, zanim pokaże opcję "Zainstaluj
// aplikację" — obok manifestu, ikon i podania po HTTPS.
function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return Promise.resolve(null);
  const prefix = window.APP_URL_PREFIX || "";
  return navigator.serviceWorker
    .register(prefix + "/sw.js", { scope: prefix + "/" })
    .catch((e) => {
      console.warn("Rejestracja Service Workera nie powiodła się:", e);
      return null;
    });
}

// Prosty toast, w tym samym stylu co flashe z Flaska (.flash-container/.alert),
// żeby feedback z włączania powiadomień wyglądał tak samo jak reszta appki.
function showToast(message, category = "info") {
  const container = document.querySelector(".flash-container");
  if (!container) { alert(message); return; }
  const el = document.createElement("div");
  el.className = `alert alert-${category}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity .3s ease";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 300);
  }, 4500);
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map((c) => c.charCodeAt(0)));
}

function isIosSafari() {
  const ua = window.navigator.userAgent;
  const isIos = /iPad|iPhone|iPod/.test(ua) || (ua.includes("Mac") && "ontouchend" in document);
  const isSafari = /Safari/.test(ua) && !/CriOS|FxiOS|EdgiOS/.test(ua);
  return isIos && isSafari;
}

function isStandalonePwa() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

// Włączenie powiadomień push — wywoływane z przycisku w /profile. Prośba o
// zgodę (Notification.requestPermission) MUSI być odpowiedzią na gest
// użytkownika, inaczej przeglądarki ją blokują — dlatego to osobna funkcja,
// a nie coś odpalane automatycznie przy ładowaniu strony.
async function setupPushNotifications() {
  const prefix = window.APP_URL_PREFIX || "";
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    if (isIosSafari() && !isStandalonePwa()) {
      showToast("Na iPhone/iPad: najpierw dodaj Planowca do ekranu głównego (Udostępnij → Dodaj do ekranu początkowego), potem otwórz appkę z ikony i włącz powiadomienia.", "info");
    } else {
      showToast("Ta przeglądarka nie wspiera powiadomień push.", "warning");
    }
    return;
  }
  try {
    const reg = await registerServiceWorker();
    if (!reg) {
      showToast("Nie udało się zarejestrować Service Workera.", "danger");
      return;
    }
    await navigator.serviceWorker.ready;

    const r = await fetch(prefix + "/profile/vapid-public-key");
    const { publicKey } = await r.json();
    if (!publicKey) {
      showToast("Serwer nie ma skonfigurowanego VAPID_PUBLIC_KEY.", "danger");
      return;
    }

    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      showToast("Nie zgodziłeś się na powiadomienia — nie mogę ich włączyć.", "warning");
      return;
    }

    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    }

    const resp = await fetch(prefix + "/profile/push-subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    if (resp.ok) {
      showToast("Powiadomienia push włączone!", "success");
    } else {
      showToast("Serwer odrzucił subskrypcję push.", "danger");
    }
  } catch (e) {
    console.warn("Push setup failed:", e);
    showToast("Nie udało się włączyć powiadomień push.", "danger");
  }
}
