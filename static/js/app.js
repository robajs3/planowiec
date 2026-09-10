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
  if (!("serviceWorker" in navigator)) return;
  const prefix = window.APP_URL_PREFIX || "";
  navigator.serviceWorker
    .register(prefix + "/sw.js", { scope: prefix + "/" })
    .catch((e) => console.warn("Rejestracja Service Workera nie powiodła się:", e));
}
