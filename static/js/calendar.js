(function () {
  const root = document.getElementById("calendar-app");
  if (!root) return;

  const CONTEXT = root.dataset.context;
  const CONTEXT_ID = parseInt(root.dataset.contextId, 10);
  const CAN_EDIT = root.dataset.canEdit === "true";
  // Uwzględnia prefiks URL appki (ustawiany w templates/base.html), żeby
  // wywołania API działały poprawnie także gdy appka jest zamontowana
  // pod ścieżką inną niż "/" (np. za Tailscale Serve --set-path).
  const API_BASE = (window.APP_URL_PREFIX || "") + "/dashboard/api";

  const WEEKDAYS = ["Pon", "Wt", "Śr", "Czw", "Pt", "Sob", "Niedz"];
  const MONTHS = [
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
  ];

  let current = new Date();
  current.setDate(1);
  let types = [];
  let activeTypeIds = new Set();
  let activities = [];
  let editingActivityId = null;

  const grid = document.getElementById("calendar-grid");
  const titleEl = document.getElementById("calendar-title");
  const filtersEl = document.getElementById("type-filters");

  // ---------------------------------------------------------------------
  // API helpers
  // ---------------------------------------------------------------------
  async function apiGet(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error("Błąd pobierania danych.");
    return res.json();
  }

  async function apiSend(url, method, body) {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Wystąpił błąd.");
    return data;
  }

  // ---------------------------------------------------------------------
  // Ładowanie typów aktywności
  // ---------------------------------------------------------------------
  async function loadTypes() {
    types = await apiGet(`${API_BASE}/types?context=${CONTEXT}&id=${CONTEXT_ID}`);
    if (activeTypeIds.size === 0) {
      types.forEach((t) => activeTypeIds.add(t.id));
    }
    renderFilters();
  }

  function renderFilters() {
    filtersEl.innerHTML = "";
    types.forEach((t) => {
      const wrap = document.createElement("div");
      wrap.className = "type-filter-item";

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "type-filter" + (activeTypeIds.has(t.id) ? " active" : "");
      chip.style.background = activeTypeIds.has(t.id) ? t.color : "";
      chip.style.borderColor = activeTypeIds.has(t.id) ? t.color : "";
      chip.innerHTML = `<span class="type-dot" style="background:${activeTypeIds.has(t.id) ? "#fff" : t.color}"></span>${escapeHtml(t.name)}`;
      chip.addEventListener("click", () => {
        if (activeTypeIds.has(t.id)) activeTypeIds.delete(t.id);
        else activeTypeIds.add(t.id);
        renderFilters();
        loadActivities();
      });
      wrap.appendChild(chip);

      // Edytować może każdy typ (domyślne są globalne, zmiana widoczna dla wszystkich).
      // Usuwać można tylko własne (niedomyślne) typy.
      if (CONTEXT === "own") {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "type-filter-tool";
        editBtn.title = t.is_default ? "Edytuj typ (domyślny — zmiana widoczna dla wszystkich)" : "Edytuj typ";
        editBtn.setAttribute("aria-label", "Edytuj typ " + t.name);
        editBtn.innerHTML = "✎";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openTypeModal(t);
        });
        wrap.appendChild(editBtn);

        if (!t.is_default) {
          const delBtn = document.createElement("button");
          delBtn.type = "button";
          delBtn.className = "type-filter-tool type-filter-tool-danger";
          delBtn.title = "Usuń typ";
          delBtn.setAttribute("aria-label", "Usuń typ " + t.name);
          delBtn.innerHTML = "🗑";
          delBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            deleteType(t);
          });
          wrap.appendChild(delBtn);
        }
      }

      filtersEl.appendChild(wrap);
    });

    if (CONTEXT === "own") {
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "type-filter add-type-btn";
      addBtn.innerHTML = "+ Nowy typ";
      addBtn.addEventListener("click", () => openTypeModal(null));
      filtersEl.appendChild(addBtn);
    }
  }

  // ---------------------------------------------------------------------
  // Widok miesiąca
  // ---------------------------------------------------------------------
  function gridRange() {
    const year = current.getFullYear();
    const month = current.getMonth();
    const firstOfMonth = new Date(year, month, 1);
    const startOffset = (firstOfMonth.getDay() + 6) % 7; // poniedziałek = 0
    const gridStart = new Date(year, month, 1 - startOffset);
    const gridEnd = new Date(gridStart);
    gridEnd.setDate(gridStart.getDate() + 42);
    return { gridStart, gridEnd };
  }

  async function loadActivities() {
    const { gridStart, gridEnd } = gridRange();
    const typeParam = Array.from(activeTypeIds).join(",");
    const params = new URLSearchParams({
      context: CONTEXT,
      id: CONTEXT_ID,
      start: gridStart.toISOString(),
      end: gridEnd.toISOString(),
      types: typeParam,
    });
    activities = await apiGet(`${API_BASE}/activities?${params.toString()}`);
    renderGrid();
  }

  function renderGrid() {
    const { gridStart } = gridRange();
    titleEl.textContent = `${MONTHS[current.getMonth()]} ${current.getFullYear()}`;

    grid.innerHTML = "";
    WEEKDAYS.forEach((d) => {
      const el = document.createElement("div");
      el.className = "calendar-weekday";
      el.textContent = d;
      grid.appendChild(el);
    });

    const today = new Date();
    const cursor = new Date(gridStart);

    for (let i = 0; i < 42; i++) {
      const dayDate = new Date(cursor);
      const dayCell = document.createElement("div");
      const isOutside = dayDate.getMonth() !== current.getMonth();
      const isToday = sameDate(dayDate, today);
      dayCell.className = "calendar-day" + (isOutside ? " outside" : "") + (isToday ? " today" : "");

      const num = document.createElement("div");
      num.className = "calendar-day-num";
      num.textContent = dayDate.getDate();
      dayCell.appendChild(num);

      const eventsWrap = document.createElement("div");
      eventsWrap.className = "calendar-events";

      const dayActivities = activities.filter((a) => sameDate(new Date(a.start), dayDate));
      dayActivities.slice(0, 3).forEach((a) => {
        const chip = document.createElement("div");
        chip.className = "calendar-event-chip";
        chip.style.background = a.type ? a.type.color : "#64748b";
        chip.textContent = a.title;
        chip.title = a.title;
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          openActivityModal(a);
        });
        eventsWrap.appendChild(chip);
      });
      if (dayActivities.length > 3) {
        const more = document.createElement("div");
        more.className = "calendar-event-more";
        more.textContent = `+${dayActivities.length - 3} więcej`;
        eventsWrap.appendChild(more);
      }

      dayCell.appendChild(eventsWrap);
      dayCell.addEventListener("click", () => openDayModal(dayDate, dayActivities));
      grid.appendChild(dayCell);

      cursor.setDate(cursor.getDate() + 1);
    }
  }

  function sameDate(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Nawigacja
  // ---------------------------------------------------------------------
  document.getElementById("prev-month").addEventListener("click", () => {
    current.setMonth(current.getMonth() - 1);
    loadActivities();
  });
  document.getElementById("next-month").addEventListener("click", () => {
    current.setMonth(current.getMonth() + 1);
    loadActivities();
  });
  function goToToday() {
    current = new Date();
    current.setDate(1);
    loadActivities();
  }

  document.getElementById("today-btn").addEventListener("click", goToToday);

  // ---------------------------------------------------------------------
  // Modal: dzień (lista aktywności danego dnia)
  // ---------------------------------------------------------------------
  const dayModal = document.getElementById("day-modal");
  const dayModalTitle = document.getElementById("day-modal-title");
  const dayModalList = document.getElementById("day-modal-list");
  const dayModalAddBtn = document.getElementById("day-modal-add");
  let selectedDay = null;

  function openDayModal(date, dayActivities) {
    selectedDay = date;
    dayModalTitle.textContent = date.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });
    dayModalList.innerHTML = "";

    if (dayActivities.length === 0) {
      dayModalList.innerHTML = '<div class="empty-state"><div class="icon">📭</div>Brak aktywności tego dnia.</div>';
    } else {
      dayActivities
        .slice()
        .sort((a, b) => new Date(a.start) - new Date(b.start))
        .forEach((a) => {
          const item = document.createElement("div");
          item.className = "list-item";
          item.style.cursor = "pointer";
          const time = a.all_day
            ? "Cały dzień"
            : `${formatTime(a.start)} – ${formatTime(a.end)}`;
          item.innerHTML = `
            <span class="type-dot" style="background:${a.type ? a.type.color : "#64748b"}"></span>
            <div class="list-item-info">
              <div class="list-item-name">${escapeHtml(a.title)}</div>
              <div class="list-item-sub">${time}${a.location ? " · " + escapeHtml(a.location) : ""}</div>
            </div>`;
          item.addEventListener("click", () => openActivityModal(a));
          dayModalList.appendChild(item);
        });
    }

    dayModalAddBtn.style.display = CAN_EDIT ? "inline-flex" : "none";
    dayModal.classList.add("open");
  }

  dayModalAddBtn.addEventListener("click", () => {
    dayModal.classList.remove("open");
    openActivityModal(null, selectedDay);
  });

  function formatTime(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });
  }

  // ---------------------------------------------------------------------
  // Modal: dodawanie / edycja / podgląd aktywności
  // ---------------------------------------------------------------------
  const actModal = document.getElementById("activity-modal");
  const actForm = document.getElementById("activity-form");
  const actTitle = document.getElementById("activity-modal-title");
  const actTypeSelect = document.getElementById("activity-type");
  const actDeleteBtn = document.getElementById("activity-delete");
  const actSaveBtn = document.getElementById("activity-save");
  const actReadonlyBanner = document.getElementById("activity-readonly-banner");

  function populateTypeSelect() {
    actTypeSelect.innerHTML = "";
    types.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name;
      actTypeSelect.appendChild(opt);
    });
  }

  function toLocalInput(iso) {
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function openActivityModal(activity, presetDate) {
    populateTypeSelect();
    editingActivityId = activity ? activity.id : null;
    const readOnly = !CAN_EDIT;

    actTitle.textContent = activity ? (readOnly ? "Szczegóły aktywności" : "Edytuj aktywność") : "Nowa aktywność";
    actReadonlyBanner.style.display = readOnly ? "flex" : "none";
    actDeleteBtn.style.display = activity && !readOnly ? "inline-flex" : "none";
    actSaveBtn.style.display = readOnly ? "none" : "inline-flex";

    document.getElementById("activity-title").value = activity ? activity.title : "";
    document.getElementById("activity-description").value = activity ? activity.description : "";
    document.getElementById("activity-location").value = activity ? activity.location : "";
    document.getElementById("activity-all-day").checked = activity ? activity.all_day : false;

    let startDate = activity ? new Date(activity.start) : (presetDate ? new Date(presetDate) : new Date());
    let endDate = activity ? new Date(activity.end) : new Date(startDate.getTime() + 60 * 60 * 1000);
    if (!activity && presetDate) {
      startDate.setHours(9, 0, 0, 0);
      endDate = new Date(startDate.getTime() + 60 * 60 * 1000);
    }
    document.getElementById("activity-start").value = toLocalInput(startDate);
    document.getElementById("activity-end").value = toLocalInput(endDate);
    actTypeSelect.value = activity && activity.type ? activity.type.id : (types[0] ? types[0].id : "");

    Array.from(actForm.elements).forEach((el) => {
      if (el.type !== "button" && el.type !== "submit") el.disabled = readOnly;
    });

    actModal.classList.add("open");
  }

  const addActivityBtn = document.getElementById("add-activity-btn");
  if (addActivityBtn) {
    addActivityBtn.addEventListener("click", () => openActivityModal(null, new Date()));
  }

  actForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      context: CONTEXT,
      id: CONTEXT_ID,
      title: document.getElementById("activity-title").value,
      description: document.getElementById("activity-description").value,
      location: document.getElementById("activity-location").value,
      all_day: document.getElementById("activity-all-day").checked,
      start: document.getElementById("activity-start").value,
      end: document.getElementById("activity-end").value,
      activity_type_id: parseInt(actTypeSelect.value, 10),
    };
    try {
      if (editingActivityId) {
        await apiSend(`${API_BASE}/activities/${editingActivityId}`, "PUT", payload);
      } else {
        await apiSend(`${API_BASE}/activities`, "POST", payload);
      }
      closeModal(actModal);
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
  });

  actDeleteBtn.addEventListener("click", async () => {
    if (!editingActivityId) return;
    if (!confirm("Na pewno usunąć tę aktywność?")) return;
    try {
      await apiSend(`${API_BASE}/activities/${editingActivityId}?context=${CONTEXT}&id=${CONTEXT_ID}`, "DELETE");
      closeModal(actModal);
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
  });

  // ---------------------------------------------------------------------
  // Modal: nowy typ / edycja typu aktywności
  // ---------------------------------------------------------------------
  const typeModal = document.getElementById("type-modal");
  const typeForm = document.getElementById("type-form");
  const typeModalTitle = document.getElementById("type-modal-title");
  const typeSaveBtn = document.getElementById("type-save");
  let editingTypeId = null;

  function openTypeModal(type) {
    typeForm.reset();
    editingTypeId = type ? type.id : null;
    typeModalTitle.textContent = type ? "Edytuj typ aktywności" : "Nowy typ aktywności";
    typeSaveBtn.textContent = type ? "Zapisz zmiany" : "Dodaj typ";
    document.getElementById("type-name").value = type ? type.name : "";
    document.getElementById("type-color").value = type ? type.color : "#2563eb";
    typeModal.classList.add("open");
  }

  typeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      name: document.getElementById("type-name").value,
      color: document.getElementById("type-color").value,
    };
    try {
      if (editingTypeId) {
        await apiSend(`${API_BASE}/types/${editingTypeId}`, "PUT", payload);
      } else {
        await apiSend(`${API_BASE}/types`, "POST", payload);
      }
      closeModal(typeModal);
      await loadTypes();
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
  });

  async function deleteType(type) {
    if (!confirm(`Na pewno usunąć typ „${type.name}”?`)) return;
    try {
      await apiSend(`${API_BASE}/types/${type.id}`, "DELETE");
      activeTypeIds.delete(type.id);
      await loadTypes();
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
  }

  // ---------------------------------------------------------------------
  // Ogólne zamykanie modali
  // ---------------------------------------------------------------------
  function closeModal(modal) {
    modal.classList.remove("open");
  }

  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => closeModal(btn.closest(".modal-backdrop")));
  });
  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (e) => {
      if (e.target === backdrop) closeModal(backdrop);
    });
  });

  // ---------------------------------------------------------------------
  // Start
  // ---------------------------------------------------------------------
  (async function init() {
    await loadTypes();
    // Ładujemy widok dokładnie tak, jakby domyślnie kliknięto przycisk "Dziś",
    // żeby po wejściu w cudzy plan od razu było widać bieżący miesiąc z aktywnościami.
    goToToday();
  })();
})();
