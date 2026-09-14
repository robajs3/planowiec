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

// Sprawdza (bez pytania o zgodę) czy w tej przeglądarce da się w ogóle
// korzystać z powiadomień push i w jakim są stanie. Używane m.in. przy
// otwieraniu formularza aktywności, żeby dobrać treść podpowiedzi i to,
// czy checkbox "Powiadom przed aktywnością" ma być klikalny.
function getPushSupportState() {
  if (!("Notification" in window) || !("serviceWorker" in navigator) || !("PushManager" in window)) {
    return "unsupported";
  }
  return Notification.permission; // "granted" | "denied" | "default"
}

// Włączenie powiadomień push. Wywoływane zarówno z przycisku w /profile,
// jak i automatycznie po zaznaczeniu "Powiadom przed aktywnością" w
// formularzu wydarzenia. Prośba o zgodę (Notification.requestPermission)
// MUSI być odpowiedzią na gest użytkownika (klik), inaczej przeglądarki ją
// blokują — dlatego wywołujemy to z handlera "change"/"click", a nie
// automatycznie przy ładowaniu strony.
//
// Zwraca true, jeśli po zakończeniu użytkownik ma aktywną, zapisaną na
// serwerze subskrypcję push — false w każdym innym przypadku (brak wsparcia,
// odmowa, błąd). Wywołujący kod (np. checkbox w kalendarzu) na tej podstawie
// decyduje, czy zostawić opcję powiadomień włączoną, czy ją zablokować.
async function setupPushNotifications() {
  const prefix = window.APP_URL_PREFIX || "";
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    if (isIosSafari() && !isStandalonePwa()) {
      showToast("Na iPhone/iPad: najpierw dodaj Planowca do ekranu głównego (Udostępnij → Dodaj do ekranu początkowego), potem otwórz appkę z ikony i włącz powiadomienia.", "info");
    } else {
      showToast("Ta przeglądarka nie wspiera powiadomień push.", "warning");
    }
    return false;
  }

  // Gdy przeglądarka ma już zapamiętaną odmowę, Notification.requestPermission()
  // i tak od razu zwróci "denied" bez pokazania okna — ale komunikat "nie
  // zgodziłeś się" byłby mylący (użytkownik nic teraz nie kliknął). Dajemy
  // od razu jasną informację, co zrobić, żeby to odblokować.
  if (Notification.permission === "denied") {
    showToast("Powiadomienia są zablokowane w przeglądarce dla tej strony. Odblokuj je w ustawieniach witryny (ikona 🔒/ⓘ obok adresu) i spróbuj ponownie.", "warning");
    return false;
  }

  try {
    const reg = await registerServiceWorker();
    if (!reg) {
      showToast("Nie udało się zarejestrować Service Workera.", "danger");
      return false;
    }
    await navigator.serviceWorker.ready;

    const r = await fetch(prefix + "/notifications/vapid-public-key");
    const { publicKey } = await r.json();
    if (!publicKey) {
      showToast("Serwer nie ma skonfigurowanego VAPID_PUBLIC_KEY.", "danger");
      return false;
    }

    const perm = await Notification.requestPermission();
    if (perm !== "granted") {
      showToast("Nie zgodziłeś się na powiadomienia — nie mogę ich włączyć.", "warning");
      return false;
    }

    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
    }

    const resp = await fetch(prefix + "/notifications/push-subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub),
    });
    if (resp.ok) {
      showToast("Powiadomienia push włączone!", "success");
      return true;
    }
    showToast("Serwer odrzucił subskrypcję push.", "danger");
    return false;
  } catch (e) {
    console.warn("Push setup failed:", e);
    showToast("Nie udało się włączyć powiadomień push.", "danger");
    return false;
  }
}

// Masowe włączanie przypomnień — przycisk "🔔 Włącz dla wszystkich
// aktywności" w /profile. Jeśli user nie ma jeszcze aktywnej zgody/subskrypcji
// push, najpierw ją zakładamy (kliknięcie przycisku samo jest wystarczającym
// gestem użytkownika, więc przeglądarka pozwoli pokazać dialog o zgodę) —
// bez tego ustawienie przypomnień na aktywnościach byłoby bez sensu, bo
// scheduler i tak nie miałby dokąd wysłać powiadomienia.
async function enableNotifyForAllActivities() {
  const select = document.getElementById("notify-all-minutes");
  const btn = document.getElementById("notify-all-btn");
  if (!select || !btn) return;
  const minutes = parseInt(select.value, 10);

  if (getPushSupportState() !== "granted") {
    const ok = await setupPushNotifications();
    if (!ok) return;
  }

  const prefix = window.APP_URL_PREFIX || "";
  btn.disabled = true;
  const prevText = btn.textContent;
  btn.textContent = "Włączam…";
  try {
    const resp = await fetch(prefix + "/dashboard/api/activities/notify-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ minutes }),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      showToast(`Włączono przypomnienia dla ${data.updated} nadchodzących aktywności.`, "success");
    } else {
      showToast(data.error || "Nie udało się włączyć powiadomień dla wszystkich aktywności.", "danger");
    }
  } catch (e) {
    console.warn("notify-all failed:", e);
    showToast("Nie udało się połączyć z serwerem.", "danger");
  } finally {
    btn.disabled = false;
    btn.textContent = prevText;
  }
}
