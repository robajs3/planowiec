(function () {
  const root = document.getElementById("calendar-app");
  if (!root) return;

  const CONTEXT = root.dataset.context;
  const CONTEXT_ID = parseInt(root.dataset.contextId, 10);
  const CAN_EDIT = root.dataset.canEdit === "true";
  const CAN_COMMENT = root.dataset.canComment === "true";
  const CURRENT_USER_ID = parseInt(root.dataset.userId, 10);
  // "Wyczyść dzień" ma sens tylko tam, gdzie mamy jeden, jednoznaczny,
  // edytowalny plan (własny, plan grupy z rolą admin/editor, albo cudzy plan
  // udostępniony z rolą "editor") — nie w zagregowanym widoku "Wszystkie plany".
  const CLEAR_DAY_ENABLED = CONTEXT === "own" || ((CONTEXT === "group" || CONTEXT === "friend") && CAN_EDIT);
  // Znaczniki dnia (legenda) — podgląd dostępny wszędzie poza zagregowanym
  // "Wszystkie plany" (tam nie ma jednego planu do oznaczania); zarządzanie
  // znacznikami i przypisywanie ich do dni wymaga tych samych warunków co
  // "Wyczyść dzień" (jeden, jednoznaczny, edytowalny plan).
  const DAY_MARKERS_VIEW_ENABLED = CONTEXT !== "all";
  const DAY_MARKERS_EDIT_ENABLED = CLEAR_DAY_ENABLED;
  // Uwzględnia prefiks URL appki (ustawiany w templates/base.html), żeby
  // wywołania API działały poprawnie także gdy appka jest zamontowana
  // pod ścieżką inną niż "/" (np. za Tailscale Serve --set-path).
  const API_BASE = (window.APP_URL_PREFIX || "") + "/dashboard/api";

  // Drag & drop (kopiowanie dnia / powtarzającej się aktywności między dniami)
  // włączamy tylko tam, gdzie mamy jednoznaczny, edytowalny kontekst — czyli
  // własny plan lub plan grupy, w której mamy rolę admin/editor. W widoku
  // zagregowanym "Wszystkie plany" (mieszanka źródeł o różnych uprawnieniach)
  // oraz w podglądzie cudzego planu drag&drop jest wyłączony.
  const DRAG_ENABLED = CONTEXT === "own" || (CONTEXT === "group" && CAN_EDIT);

  const SOURCE_ICON = { own: "", friend: "👁", group: "🧩" };

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
  let dayMarkers = [];
  let dayMarkerAssignments = new Map(); // "YYYY-MM-DD" -> {marker_id, name, color}
  let activeMarkerIds = null; // null = wszystkie widoczne (jeszcze nie tykane); Set() = filtr aktywny
  let markMode = false; // tryb "Oznacz dni": klik w dzień otwiera wybór znacznika zamiast listy aktywności

  // Efektywny kontekst edycji aktualnie otwartej aktywności w modalu — w widoku
  // "all" różni się on od globalnego CONTEXT/CONTEXT_ID w zależności od tego,
  // z czyjego planu pochodzi dana aktywność (zob. activity.source).
  let editCtx = { context: CONTEXT, id: CONTEXT_ID, canEdit: CAN_EDIT };

  const grid = document.getElementById("calendar-grid");
  const titleEl = document.getElementById("calendar-title");
  const filtersEl = document.getElementById("type-filters");
  const legendEl = document.getElementById("source-legend");

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
  // Ładowanie typów aktywności / kategorii
  // ---------------------------------------------------------------------
  async function loadTypes() {
    types = await apiGet(`${API_BASE}/types?context=${CONTEXT}&id=${CONTEXT_ID}`);
    if (activeTypeIds.size === 0) {
      types.forEach((t) => activeTypeIds.add(t.id));
    }
    renderFilters();
  }

  // Czy w bieżącym, globalnym kontekście strony wolno zarządzać kategoriami
  // (dodawać/edytować/usuwać)? Tak w prywatnym planie oraz w planie grupy,
  // gdy mamy rolę admin/editor. Nie w podglądzie cudzego planu ani w
  // zagregowanym widoku "Wszystkie plany" (tam kategorie są tylko filtrem).
  const CAN_MANAGE_TYPES = CONTEXT === "own" || (CONTEXT === "group" && CAN_EDIT);

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

      if (CAN_MANAGE_TYPES) {
        const editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "type-filter-tool";
        editBtn.title = t.is_default ? "Edytuj kategorię" : "Edytuj typ";
        editBtn.setAttribute("aria-label", "Edytuj typ " + t.name);
        editBtn.innerHTML = "✎";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          openTypeModal(t);
        });
        wrap.appendChild(editBtn);

        // W prywatnym planie nie da się usunąć globalnych domyślnych typów.
        // W planie grupy admin/editor może usunąć DOWOLNĄ kategorię grupy,
        // łącznie z tymi domyślnymi (to niezależna kopia tej grupy).
        const canDeleteThis = CONTEXT === "group" ? true : !t.is_default;
        if (canDeleteThis) {
          const delBtn = document.createElement("button");
          delBtn.type = "button";
          delBtn.className = "type-filter-tool type-filter-tool-danger";
          delBtn.title = "Usuń";
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

    if (CAN_MANAGE_TYPES) {
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "type-filter add-type-btn";
      addBtn.innerHTML = CONTEXT === "group" ? "+ Nowa kategoria" : "+ Nowy typ";
      addBtn.addEventListener("click", () => openTypeModal(null));
      filtersEl.appendChild(addBtn);
    }
  }

  // ---------------------------------------------------------------------
  // Legenda źródeł (tylko widok "Wszystkie plany")
  // ---------------------------------------------------------------------
  function renderLegend() {
    if (!legendEl) return;
    if (CONTEXT !== "all") {
      legendEl.style.display = "none";
      return;
    }
    legendEl.style.display = "flex";
    legendEl.innerHTML = `
      <span><span class="dot own"></span>Twoje aktywności</span>
      <span><span class="dot friend"></span>👁 Znajomi</span>
      <span><span class="dot group"></span>🧩 Grupy</span>
    `;
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

  function toDateKey(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
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
    const jobs = [apiGet(`${API_BASE}/activities?${params.toString()}`)];
    if (DAY_MARKERS_VIEW_ENABLED) {
      const dmParams = new URLSearchParams({
        context: CONTEXT, id: CONTEXT_ID,
        start: toDateKey(gridStart), end: toDateKey(gridEnd),
      });
      jobs.push(apiGet(`${API_BASE}/day-markers/assignments?${dmParams.toString()}`));
    }
    const [activityResults, assignmentResults] = await Promise.all(jobs);
    activities = activityResults;
    if (DAY_MARKERS_VIEW_ENABLED) {
      dayMarkerAssignments = new Map((assignmentResults || []).map((a) => [a.date, a]));
    }
    renderGrid();
  }

  function renderGrid() {
    const { gridStart } = gridRange();
    titleEl.textContent = `${MONTHS[current.getMonth()]} ${current.getFullYear()}`;
    renderLegend();

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

      // ---- Kolorowa ramka dnia wg przypisanego "znacznika dnia" (legenda) ----
      // Całkowicie niezależne od aktywności/typów — patrz #day-markers-bar.
      const marker = dayMarkerAssignments.get(toDateKey(dayDate));
      const markerVisible = marker && (!activeMarkerIds || activeMarkerIds.has(marker.marker_id));
      if (markerVisible) {
        dayCell.style.borderColor = marker.color;
        dayCell.style.borderWidth = "3px";
        dayCell.classList.add("day-marked");
        dayCell.title = marker.name;
      }

      dayActivities.slice(0, 3).forEach((a) => {
        const chip = document.createElement("div");
        const srcKind = a.source ? a.source.kind : null;
        chip.className = "calendar-event-chip" + (srcKind ? ` source-${srcKind}` : "");
        chip.style.background = a.type ? a.type.color : "#64748b";
        const icon = srcKind ? SOURCE_ICON[srcKind] : "";
        chip.textContent = (icon ? icon + " " : "") + a.title;
        chip.title = a.source ? `${a.title} — ${a.source.label}` : a.title;
        chip.addEventListener("click", (e) => {
          e.stopPropagation();
          openActivityModal(a);
        });

        const chipCanEdit = a.source ? a.source.can_edit : CAN_EDIT;
        if (DRAG_ENABLED && chipCanEdit) {
          chip.classList.add("draggable-chip");
          chip.draggable = true;
          chip.addEventListener("dragstart", (e) => {
            e.stopPropagation();
            e.dataTransfer.effectAllowed = "copy";
            e.dataTransfer.setData("application/json", JSON.stringify({ kind: "activity", id: a.id }));
          });
        }

        eventsWrap.appendChild(chip);
      });
      if (dayActivities.length > 3) {
        const more = document.createElement("div");
        more.className = "calendar-event-more";
        more.textContent = `+${dayActivities.length - 3} więcej`;
        eventsWrap.appendChild(more);
      }

      dayCell.appendChild(eventsWrap);
      dayCell.addEventListener("click", () => {
        if (markMode) {
          openDayMarkerPicker(dayDate);
        } else {
          openDayModal(dayDate, dayActivities);
        }
      });

      // ---- Drag & drop: przeciąganie całego dnia (kopiowanie) ----
      const dayHasEditableActivities = dayActivities.some((a) => (a.source ? a.source.can_edit : CAN_EDIT));
      if (DRAG_ENABLED) {
        dayCell.addEventListener("dragover", (e) => {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
          dayCell.classList.add("drag-over");
        });
        dayCell.addEventListener("dragleave", () => dayCell.classList.remove("drag-over"));
        dayCell.addEventListener("drop", (e) => {
          e.preventDefault();
          dayCell.classList.remove("drag-over");
          let payload;
          try {
            payload = JSON.parse(e.dataTransfer.getData("application/json"));
          } catch (err) {
            return;
          }
          handleDrop(payload, dayDate);
        });

        if (dayHasEditableActivities) {
          dayCell.classList.add("drag-enabled");
          dayCell.draggable = true;
          dayCell.addEventListener("dragstart", (e) => {
            e.dataTransfer.effectAllowed = "copy";
            e.dataTransfer.setData("application/json", JSON.stringify({ kind: "day", date: dayDate.toISOString() }));
            dayCell.classList.add("day-dragging");
          });
          dayCell.addEventListener("dragend", () => dayCell.classList.remove("day-dragging"));
        }
      }

      grid.appendChild(dayCell);

      cursor.setDate(cursor.getDate() + 1);
    }
  }

  function sameDate(a, b) {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  }

  // ---------------------------------------------------------------------
  // Znaczniki dnia (legenda) — całkowicie osobny system od typów aktywności.
  // ---------------------------------------------------------------------
  const dayMarkersBar = document.getElementById("day-markers-bar");
  const dayMarkersModal = document.getElementById("day-markers-modal");
  const dayMarkersListEl = document.getElementById("day-markers-list");
  const dayMarkerForm = document.getElementById("day-marker-form");
  const dayMarkerPickerModal = document.getElementById("day-marker-picker-modal");
  const dayMarkerPickerTitle = document.getElementById("day-marker-picker-title");
  const dayMarkerPickerList = document.getElementById("day-marker-picker-list");
  const dayMarkerPickerClearBtn = document.getElementById("day-marker-picker-clear");
  let pickerDay = null;

  async function loadDayMarkers() {
    if (!DAY_MARKERS_VIEW_ENABLED) return;
    dayMarkers = await apiGet(`${API_BASE}/day-markers?context=${CONTEXT}&id=${CONTEXT_ID}`);
    renderDayMarkersBar();
  }

  function renderDayMarkersBar() {
    if (!DAY_MARKERS_VIEW_ENABLED) {
      dayMarkersBar.style.display = "none";
      return;
    }
    dayMarkersBar.style.display = "flex";
    dayMarkersBar.innerHTML = "";

    dayMarkers.forEach((m) => {
      const active = !activeMarkerIds || activeMarkerIds.has(m.id);
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "type-filter" + (active ? " active" : "");
      chip.style.background = active ? m.color : "";
      chip.style.borderColor = active ? m.color : "";
      chip.title = active ? "Kliknij, aby ukryć podświetlenie tego znacznika w kalendarzu" : "Kliknij, aby pokazać podświetlenie tego znacznika w kalendarzu";
      chip.innerHTML = `<span style="width:10px; height:10px; border-radius:50%; background:${active ? "#fff" : m.color}; display:inline-block;"></span>${escapeHtml(m.name)}`;
      chip.addEventListener("click", () => {
        // pierwsze kliknięcie: zamień "wszystko widoczne" na jawny zbiór
        // wszystkich znaczników MINUS ten kliknięty
        if (!activeMarkerIds) {
          activeMarkerIds = new Set(dayMarkers.map((x) => x.id));
        }
        if (activeMarkerIds.has(m.id)) activeMarkerIds.delete(m.id);
        else activeMarkerIds.add(m.id);
        renderDayMarkersBar();
        renderGrid();
      });
      dayMarkersBar.appendChild(chip);
    });

    if (DAY_MARKERS_EDIT_ENABLED) {
      const manageBtn = document.createElement("button");
      manageBtn.type = "button";
      manageBtn.className = "btn btn-outline btn-sm";
      manageBtn.textContent = "🏷 Znaczniki dnia";
      manageBtn.addEventListener("click", () => {
        renderDayMarkersManageList();
        dayMarkersModal.classList.add("open");
      });
      dayMarkersBar.appendChild(manageBtn);

      const toggleBtn = document.createElement("button");
      toggleBtn.type = "button";
      toggleBtn.className = "btn btn-sm " + (markMode ? "btn-primary" : "btn-outline");
      toggleBtn.textContent = markMode ? "🎨 Tryb oznaczania: WŁĄCZONY" : "🎨 Oznacz dni";
      toggleBtn.title = "Po włączeniu, kliknięcie dnia w kalendarzu pozwala przypisać mu znacznik zamiast otwierać listę aktywności.";
      toggleBtn.addEventListener("click", () => {
        markMode = !markMode;
        renderDayMarkersBar();
        renderGrid();
      });
      dayMarkersBar.appendChild(toggleBtn);
    } else if (dayMarkers.length === 0) {
      dayMarkersBar.style.display = "none";
    }
  }

  function renderDayMarkersManageList() {
    dayMarkersListEl.innerHTML = "";
    if (!dayMarkers.length) {
      dayMarkersListEl.innerHTML = '<div class="list-item-sub">Brak znaczników — dodaj pierwszy poniżej.</div>';
      return;
    }
    dayMarkers.forEach((m) => {
      const row = document.createElement("div");
      row.className = "list-item";
      row.innerHTML = `
        <span class="type-dot" style="background:${m.color}"></span>
        <div class="list-item-info"><div class="list-item-name">${escapeHtml(m.name)}</div></div>
        <button type="button" class="type-filter-tool type-filter-tool-danger" title="Usuń znacznik">🗑</button>`;
      row.querySelector("button").addEventListener("click", async () => {
        if (!confirm(`Usunąć znacznik „${m.name}”? Zniknie też ze wszystkich oznaczonych nim dni.`)) return;
        try {
          await apiSend(`${API_BASE}/day-markers/${m.id}?context=${CONTEXT}&id=${CONTEXT_ID}`, "DELETE");
          await loadDayMarkers();
          renderDayMarkersManageList();
          loadActivities();
        } catch (err) {
          alert(err.message);
        }
      });
      dayMarkersListEl.appendChild(row);
    });
  }

  if (dayMarkerForm) {
    dayMarkerForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("day-marker-name").value;
      const color = document.getElementById("day-marker-color").value;
      try {
        await apiSend(`${API_BASE}/day-markers?context=${CONTEXT}&id=${CONTEXT_ID}`, "POST", { name, color });
        dayMarkerForm.reset();
        document.getElementById("day-marker-color").value = "#ef4444";
        await loadDayMarkers();
        renderDayMarkersManageList();
      } catch (err) {
        alert(err.message);
      }
    });
  }

  function openDayMarkerPicker(date) {
    pickerDay = date;
    dayMarkerPickerTitle.textContent = "Oznacz: " + date.toLocaleDateString("pl-PL", { weekday: "long", day: "numeric", month: "long" });
    dayMarkerPickerList.innerHTML = "";
    if (!dayMarkers.length) {
      dayMarkerPickerList.innerHTML = '<div class="list-item-sub">Nie masz jeszcze żadnych znaczników. Dodaj je w „🏷 Znaczniki dnia”.</div>';
    }
    dayMarkers.forEach((m) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-item";
      btn.style.cssText = "width:100%; text-align:left; cursor:pointer; border:1px solid var(--border); background:var(--bg-card);";
      btn.innerHTML = `<span class="type-dot" style="background:${m.color}"></span><div class="list-item-info"><div class="list-item-name">${escapeHtml(m.name)}</div></div>`;
      btn.addEventListener("click", async () => {
        try {
          await apiSend(`${API_BASE}/day-markers/assign?context=${CONTEXT}&id=${CONTEXT_ID}`, "POST", {
            date: toDateKey(pickerDay), marker_id: m.id,
          });
          closeModal(dayMarkerPickerModal);
          loadActivities();
        } catch (err) {
          alert(err.message);
        }
      });
      dayMarkerPickerList.appendChild(btn);
    });
    dayMarkerPickerModal.classList.add("open");
  }

  if (dayMarkerPickerClearBtn) {
    dayMarkerPickerClearBtn.addEventListener("click", async () => {
      if (!pickerDay) return;
      try {
        await apiSend(`${API_BASE}/day-markers/assign?context=${CONTEXT}&id=${CONTEXT_ID}`, "POST", {
          date: toDateKey(pickerDay), marker_id: null,
        });
        closeModal(dayMarkerPickerModal);
        loadActivities();
      } catch (err) {
        alert(err.message);
      }
    });
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Drag & drop: logika kopiowania
  // ---------------------------------------------------------------------
  function combineDateTime(targetDate, originalDate) {
    const d = new Date(targetDate);
    d.setHours(originalDate.getHours(), originalDate.getMinutes(), originalDate.getSeconds(), 0);
    return d;
  }

  function formatLocal(d) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  async function copyActivity(a, targetDate) {
    const originalStart = new Date(a.start);
    const originalEnd = new Date(a.end);
    if (sameDate(originalStart, targetDate)) return; // bez sensu kopiować na ten sam dzień
    const durationMs = originalEnd.getTime() - originalStart.getTime();
    const newStart = combineDateTime(targetDate, originalStart);
    const newEnd = new Date(newStart.getTime() + durationMs);

    const payload = {
      context: CONTEXT,
      id: CONTEXT_ID,
      title: a.title,
      description: a.description,
      location: a.location,
      all_day: a.all_day,
      start: formatLocal(newStart),
      end: formatLocal(newEnd),
      activity_type_id: a.type ? a.type.id : null,
    };
    await apiSend(`${API_BASE}/activities`, "POST", payload);
  }

  async function handleDrop(payload, targetDate) {
    try {
      if (payload.kind === "activity") {
        const a = activities.find((x) => x.id === payload.id);
        if (!a) return;
        await copyActivity(a, targetDate);
      } else if (payload.kind === "day") {
        const sourceDate = new Date(payload.date);
        if (sameDate(sourceDate, targetDate)) return;
        const dayActivities = activities.filter((a) => sameDate(new Date(a.start), sourceDate));
        for (const a of dayActivities) {
          const chipCanEdit = a.source ? a.source.can_edit : CAN_EDIT;
          if (chipCanEdit) await copyActivity(a, targetDate);
        }
      }
      await loadActivities();
    } catch (err) {
      alert(err.message);
    }
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
  const dayModalClearBtn = document.getElementById("day-modal-clear");
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
          const srcIcon = a.source ? SOURCE_ICON[a.source.kind] : "";
          const srcLabel = a.source ? ` · ${escapeHtml(a.source.label)}` : "";
          const commentBadge = a.comment_count ? ` · 💬 ${a.comment_count}` : "";
          item.innerHTML = `
            <span class="type-dot" style="background:${a.type ? a.type.color : "#64748b"}"></span>
            <div class="list-item-info">
              <div class="list-item-name">${srcIcon ? srcIcon + " " : ""}${escapeHtml(a.title)}${a.recurrence_id ? " 🔁" : ""}</div>
              <div class="list-item-sub">${time}${a.location ? " · " + escapeHtml(a.location) : ""}${srcLabel}${commentBadge}</div>
            </div>`;
          item.addEventListener("click", () => openActivityModal(a));
          dayModalList.appendChild(item);
        });
    }

    dayModalAddBtn.style.display = CAN_EDIT ? "inline-flex" : "none";
    dayModalClearBtn.style.display = (CLEAR_DAY_ENABLED && dayActivities.length > 0) ? "inline-flex" : "none";
    dayModal.classList.add("open");
  }

  dayModalAddBtn.addEventListener("click", () => {
    dayModal.classList.remove("open");
    openActivityModal(null, selectedDay);
  });

  dayModalClearBtn.addEventListener("click", async () => {
    if (!selectedDay) return;
    if (!confirm("Na pewno usunąć WSZYSTKIE aktywności tego dnia? Tej operacji nie można cofnąć.")) return;
    try {
      await apiSend(`${API_BASE}/activities/clear-day`, "POST", {
        context: CONTEXT === "all" ? "own" : CONTEXT,
        id: CONTEXT_ID,
        date: formatLocal(selectedDay),
      });
      closeModal(dayModal);
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
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
  const actRecurrenceGroup = document.getElementById("activity-recurrence-group");
  const actRecurrenceSelect = document.getElementById("activity-recurrence");
  const actRecurrenceUntilRow = document.getElementById("activity-recurrence-until-row");
  const actRecurrenceUntil = document.getElementById("activity-recurrence-until");
  const actRecurrenceCount = document.getElementById("activity-recurrence-count");
  const actCommentsSection = document.getElementById("activity-comments-section");
  const actCommentsList = document.getElementById("activity-comments-list");
  const actCommentFormRow = document.getElementById("activity-comment-form-row");
  const actCommentInput = document.getElementById("activity-comment-input");
  const actCommentSendBtn = document.getElementById("activity-comment-send");

  let editingActivity = null; // pełny obiekt aktualnie edytowanej/przeglądanej aktywności

  function populateTypeSelect(ctxKind, ctxId) {
    actTypeSelect.innerHTML = "";
    // W widoku "Wszystkie plany" typy są zbiorem z wielu źródeł — przy
    // dodawaniu/edycji pokazujemy tylko te pasujące do faktycznego planu,
    // do którego trafi aktywność (własny/grupowy), żeby nie mieszać kategorii.
    const relevant = CONTEXT === "all"
      ? types.filter((t) => (ctxKind === "group" ? t.group_id === ctxId : !t.group_id))
      : types;
    (relevant.length ? relevant : types).forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t.id;
      opt.textContent = t.name;
      actTypeSelect.appendChild(opt);
    });
  }

  function toLocalInput(iso) {
    return formatLocal(new Date(iso));
  }

  actRecurrenceSelect.addEventListener("change", () => {
    actRecurrenceUntilRow.style.display = actRecurrenceSelect.value === "none" ? "none" : "flex";
  });

  // ---- Komentarze ----
  function renderComments(comments, canComment) {
    actCommentsList.innerHTML = "";
    if (!comments.length) {
      actCommentsList.innerHTML = '<div class="list-item-sub">Brak komentarzy.</div>';
    } else {
      comments.forEach((c) => {
        const row = document.createElement("div");
        row.style.cssText = "display:flex; gap:8px; align-items:flex-start;";
        const initials = c.author ? c.author.initials : "?";
        const color = c.author ? c.author.avatar_color : "#64748b";
        const when = new Date(c.created_at).toLocaleString("pl-PL", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        const canDelete = CURRENT_USER_ID === (c.author ? c.author.id : null) || CURRENT_USER_ID === editingActivity.ownerId;
        row.innerHTML = `
          <div class="avatar" style="background:${color}; width:26px; height:26px; font-size:.65rem; flex-shrink:0;">${initials}</div>
          <div style="flex:1; min-width:0;">
            <div style="font-size:.78rem;"><strong>${escapeHtml(c.author ? c.author.name : "Ktoś")}</strong> <span class="list-item-sub">· ${when}</span></div>
            <div style="font-size:.85rem; word-break:break-word;">${escapeHtml(c.content)}</div>
          </div>
          ${canDelete ? `<button type="button" class="type-filter-tool type-filter-tool-danger" title="Usuń komentarz" style="flex-shrink:0;">🗑</button>` : ""}`;
        if (canDelete) {
          row.querySelector("button").addEventListener("click", async () => {
            if (!confirm("Usunąć ten komentarz?")) return;
            try {
              await apiSend(`${API_BASE}/comments/${c.id}`, "DELETE");
              loadComments();
            } catch (err) {
              alert(err.message);
            }
          });
        }
        actCommentsList.appendChild(row);
      });
    }
    actCommentFormRow.style.display = canComment ? "flex" : "none";
  }

  async function loadComments() {
    if (!editingActivity) return;
    try {
      const comments = await apiGet(`${API_BASE}/activities/${editingActivity.id}/comments`);
      renderComments(comments, editCtx.canComment);
    } catch (err) {
      actCommentsList.innerHTML = '<div class="list-item-sub">Nie udało się wczytać komentarzy.</div>';
    }
  }

  actCommentSendBtn.addEventListener("click", async () => {
    const content = actCommentInput.value.trim();
    if (!content || !editingActivity) return;
    try {
      await apiSend(`${API_BASE}/activities/${editingActivity.id}/comments`, "POST", { content });
      actCommentInput.value = "";
      loadComments();
    } catch (err) {
      alert(err.message);
    }
  });
  actCommentInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      actCommentSendBtn.click();
    }
  });

  function openActivityModal(activity, presetDate) {
    editingActivityId = activity ? activity.id : null;
    editingActivity = activity
      ? { id: activity.id, recurrenceId: activity.recurrence_id, ownerId: activity.owner ? activity.owner.id : null }
      : null;

    if (activity && activity.source) {
      editCtx = {
        context: activity.source.kind, id: activity.source.id,
        canEdit: activity.source.can_edit, canComment: !!activity.source.can_comment,
      };
    } else if (activity) {
      editCtx = { context: CONTEXT, id: CONTEXT_ID, canEdit: CAN_EDIT, canComment: CAN_COMMENT };
    } else {
      // Nowa aktywność: w widoku zagregowanym zawsze trafia do własnego planu.
      editCtx = { context: CONTEXT === "all" ? "own" : CONTEXT, id: CONTEXT_ID, canEdit: CAN_EDIT, canComment: CAN_COMMENT };
    }

    populateTypeSelect(editCtx.context, editCtx.id);
    const readOnly = !editCtx.canEdit;

    actTitle.textContent = activity ? (readOnly ? "Szczegóły aktywności" : "Edytuj aktywność") : "Nowa aktywność";
    actReadonlyBanner.style.display = readOnly ? "flex" : "none";
    actDeleteBtn.style.display = activity && !readOnly ? "inline-flex" : "none";
    actDeleteBtn.textContent = activity && activity.recurrence_id ? "Usuń…" : "Usuń";
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
    actTypeSelect.value = activity && activity.type ? activity.type.id : (actTypeSelect.options[0] ? actTypeSelect.options[0].value : "");

    // Cykliczność ustawiamy tylko przy TWORZENIU nowej aktywności — edycja
    // pojedynczego, już istniejącego wystąpienia serii nie zmienia reguły cyklu.
    actRecurrenceSelect.value = "none";
    actRecurrenceUntil.value = "";
    actRecurrenceCount.value = "";
    actRecurrenceUntilRow.style.display = "none";
    actRecurrenceGroup.style.display = (!activity && !readOnly) ? "block" : "none";

    Array.from(actForm.elements).forEach((el) => {
      if (el.type !== "button" && el.type !== "submit") el.disabled = readOnly;
    });
    // Cykliczność dotyczy tylko tworzenia nowej aktywności — niezależnie od
    // stanu ustawionego przez powyższą pętlę, wymuszamy właściwy stan pól.
    actRecurrenceSelect.disabled = readOnly || !!activity;
    actRecurrenceUntil.disabled = readOnly || !!activity;
    actRecurrenceCount.disabled = readOnly || !!activity;

    // Komentowanie ma własne uprawnienie (canComment), niezależne od canEdit —
    // np. znajomy z rolą "commenter" nie może edytować planu, ale może pisać
    // komentarze, więc pole komentarza NIE powinno dziedziczyć stanu `readOnly`.
    const canWriteComment = !!(activity && editCtx.canComment);
    actCommentInput.disabled = !canWriteComment;
    actCommentSendBtn.disabled = !canWriteComment;

    // Komentarze: dostępne tylko dla już istniejących aktywności, gdy mamy
    // do nich w ogóle dostęp (czyli zawsze, skoro w ogóle je widzimy).
    if (activity) {
      actCommentsSection.style.display = "block";
      actCommentsList.innerHTML = '<div class="list-item-sub">Wczytywanie…</div>';
      loadComments();
    } else {
      actCommentsSection.style.display = "none";
    }

    actModal.classList.add("open");
  }

  const addActivityBtn = document.getElementById("add-activity-btn");
  if (addActivityBtn) {
    addActivityBtn.addEventListener("click", () => openActivityModal(null, new Date()));
  }

  actForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      context: editCtx.context,
      id: editCtx.id,
      title: document.getElementById("activity-title").value,
      description: document.getElementById("activity-description").value,
      location: document.getElementById("activity-location").value,
      all_day: document.getElementById("activity-all-day").checked,
      start: document.getElementById("activity-start").value,
      end: document.getElementById("activity-end").value,
      activity_type_id: parseInt(actTypeSelect.value, 10),
    };
    if (!editingActivityId && actRecurrenceSelect.value !== "none") {
      payload.recurrence = actRecurrenceSelect.value;
      if (actRecurrenceUntil.value) payload.recurrence_until = actRecurrenceUntil.value;
      if (actRecurrenceCount.value) payload.recurrence_count = parseInt(actRecurrenceCount.value, 10);
      if (!actRecurrenceUntil.value && !actRecurrenceCount.value) {
        alert("Podaj datę zakończenia cyklu albo liczbę powtórzeń.");
        return;
      }
    }
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
    let scope = "single";
    if (editingActivity && editingActivity.recurrenceId) {
      if (!confirm("Ta aktywność jest częścią cyklu. Usunąć tylko ten dzień? (Anuluj, żeby zamiast tego usunąć całą serię)")) {
        if (!confirm("Usunąć całą serię tego wydarzenia cyklicznego?")) return;
        scope = "series";
      }
    } else if (!confirm("Na pewno usunąć tę aktywność?")) {
      return;
    }
    try {
      await apiSend(`${API_BASE}/activities/${editingActivityId}?context=${editCtx.context}&id=${editCtx.id}&scope=${scope}`, "DELETE");
      closeModal(actModal);
      loadActivities();
    } catch (err) {
      alert(err.message);
    }
  });

  // ---------------------------------------------------------------------
  // Modal: nowy typ / edycja typu aktywności (lub kategorii grupy)
  // ---------------------------------------------------------------------
  const typeModal = document.getElementById("type-modal");
  const typeForm = document.getElementById("type-form");
  const typeModalTitle = document.getElementById("type-modal-title");
  const typeSaveBtn = document.getElementById("type-save");
  let editingTypeId = null;

  function openTypeModal(type) {
    typeForm.reset();
    editingTypeId = type ? type.id : null;
    const label = CONTEXT === "group" ? "kategorię" : "typ aktywności";
    typeModalTitle.textContent = type ? `Edytuj ${label}` : `Nowa ${label}`;
    typeSaveBtn.textContent = type ? "Zapisz zmiany" : "Dodaj";
    document.getElementById("type-name").value = type ? type.name : "";
    document.getElementById("type-color").value = type ? type.color : "#2563eb";
    typeModal.classList.add("open");
  }

  typeForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      context: CONTEXT,
      id: CONTEXT_ID,
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
    if (!confirm(`Na pewno usunąć „${type.name}”?`)) return;
    try {
      await apiSend(`${API_BASE}/types/${type.id}?context=${CONTEXT}&id=${CONTEXT_ID}`, "DELETE");
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
    await Promise.all([loadTypes(), loadDayMarkers()]);
    // Ładujemy widok dokładnie tak, jakby domyślnie kliknięto przycisk "Dziś",
    // żeby po wejściu w cudzy plan od razu było widać bieżący miesiąc z aktywnościami.
    goToToday();
  })();
})();
