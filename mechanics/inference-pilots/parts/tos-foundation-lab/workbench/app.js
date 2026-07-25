"use strict";

const token = document.querySelector('meta[name="tos-review-token"]').content;
const apiHeaders = {
  "Content-Type": "application/json",
  "X-ToS-Review-Token": token,
};

let view = null;
let activePageRole = "current";
let zoom = 1;
let saveTimer = null;
let saveInFlight = false;
let saveAgain = false;
let toastTimer = null;
let lastInteractionAt = Date.now();

const elements = {
  app: document.getElementById("app"),
  title: document.getElementById("protocol-title"),
  saveStatus: document.getElementById("save-status"),
  reviewerChip: document.getElementById("reviewer-chip"),
  progressLabel: document.getElementById("progress-label"),
  progressBar: document.getElementById("progress-bar"),
  unitList: document.getElementById("unit-list"),
  submitReview: document.getElementById("submit-review"),
  unitContext: document.getElementById("unit-context"),
  unitHeading: document.getElementById("unit-heading"),
  unitInstruction: document.getElementById("unit-instruction"),
  blindNotice: document.getElementById("blind-notice"),
  reviewForm: document.getElementById("review-form"),
  sourcePanel: document.getElementById("source-panel"),
  judgmentPanel: document.getElementById("judgment-panel"),
  pageTabs: document.getElementById("page-tabs"),
  pageViewer: document.getElementById("page-viewer"),
  pageCanvas: document.getElementById("page-canvas"),
  sourcePage: document.getElementById("source-page"),
  pageLabel: document.getElementById("page-label"),
  zoomLabel: document.getElementById("zoom-label"),
  previousUnit: document.getElementById("previous-unit"),
  nextUnit: document.getElementById("next-unit"),
  unitPosition: document.getElementById("unit-position"),
  startLayer: document.getElementById("start-layer"),
  startDescription: document.getElementById("start-description"),
  reviewerInput: document.getElementById("reviewer-ref-input"),
  startReview: document.getElementById("start-review"),
  startError: document.getElementById("start-error"),
  feedbackLayer: document.getElementById("feedback-layer"),
  feedbackOpen: document.getElementById("feedback-open"),
  feedbackCategory: document.getElementById("feedback-category"),
  feedbackNote: document.getElementById("feedback-note"),
  feedbackError: document.getElementById("feedback-error"),
  feedbackSend: document.getElementById("feedback-send"),
  submitLayer: document.getElementById("submit-layer"),
  submitSummary: document.getElementById("submit-summary"),
  humanAttestation: document.getElementById("human-attestation"),
  submitError: document.getElementById("submit-error"),
  submitConfirm: document.getElementById("submit-confirm"),
  toast: document.getElementById("toast"),
};

async function request(path, options = {}) {
  const response = await fetch(path, {
    cache: "no-store",
    ...options,
    headers: { ...apiHeaders, ...(options.headers || {}) },
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function fieldValue(row, fieldName) {
  const value = row.values[fieldName];
  return value === null || value === undefined ? "" : String(value);
}

function selectedDecision(values) {
  return values.decision || "";
}

function missingFields(row) {
  const decision = selectedDecision(row.values);
  const missing = new Set();
  for (const field of view.protocol.fields) {
    const value = row.values[field.name];
    let required = Boolean(field.always_required);
    if ((field.required_for || []).includes(decision)) {
      required = true;
    }
    if (required && (value === null || String(value).trim() === "")) {
      missing.add(field.name);
    }
  }
  if (decision && decision !== "accept") {
    let rationale = row.values.notes;
    if (view.protocol.protocol_id.includes("gold-page")) {
      rationale = rationale || row.values.source_damage_or_ambiguity;
    }
    if (!rationale || !String(rationale).trim()) {
      missing.add("notes");
    }
  }
  return [...missing];
}

function localCompletion() {
  const perUnit = view.state.rows.map((row) => missingFields(row).length === 0);
  return {
    perUnit,
    completedUnits: perUnit.filter(Boolean).length,
    totalUnits: perUnit.length,
  };
}

function currentIndex() {
  return view.state.active_unit_index;
}

function currentUnit() {
  return view.units[currentIndex()];
}

function currentRow() {
  return view.state.rows[currentIndex()];
}

function isFrozen() {
  return view.state.status === "submitted-and-frozen";
}

function showToast(message, duration = 3000) {
  clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => {
    elements.toast.hidden = true;
  }, duration);
}

function setSaveStatus(message, tone = "normal") {
  elements.saveStatus.textContent = message;
  elements.saveStatus.style.color =
    tone === "error" ? "var(--danger)" : tone === "saved" ? "var(--green)" : "";
}

function updateProgress() {
  const completion = localCompletion();
  elements.progressLabel.textContent =
    `${completion.completedUnits} / ${completion.totalUnits}`;
  elements.progressBar.style.width =
    `${(completion.completedUnits / completion.totalUnits) * 100}%`;
  elements.reviewerChip.textContent =
    view.state.reviewer_ref || "Рецензент не указан";
  elements.submitReview.textContent = isFrozen()
    ? "Pass 1 зафиксирован"
    : completion.completedUnits === completion.totalUnits
      ? "Завершить проход"
      : `Завершить · осталось ${completion.totalUnits - completion.completedUnits}`;
  elements.submitReview.disabled = isFrozen();
}

function renderQueue() {
  const completion = localCompletion();
  elements.unitList.replaceChildren();
  view.units.forEach((unit, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "unit-button";
    if (index === currentIndex()) button.classList.add("active");
    if (completion.perUnit[index]) button.classList.add("complete");
    button.dataset.index = String(index);

    const number = document.createElement("span");
    number.className = "unit-number";
    number.textContent = String(index + 1).padStart(2, "0");

    const copy = document.createElement("span");
    copy.className = "unit-copy";
    const strong = document.createElement("strong");
    strong.textContent = unit.unit_id;
    const context = document.createElement("span");
    context.textContent = unit.context;
    copy.append(strong, context);

    const dot = document.createElement("span");
    dot.className = "unit-dot";
    dot.setAttribute("aria-hidden", "true");

    button.append(number, copy, dot);
    button.addEventListener("click", () => navigateTo(index));
    elements.unitList.append(button);
  });
}

function isFieldRequired(field, row) {
  if (field.always_required) return true;
  return (field.required_for || []).includes(selectedDecision(row.values));
}

function markFieldChanged(fieldName, value) {
  currentRow().values[fieldName] = value === "" ? null : value;
  updateProgress();
  renderQueue();
  scheduleSave();
}

function buildField(field, row) {
  const wrapper = document.createElement("label");
  wrapper.className = "field";
  wrapper.dataset.field = field.name;
  if (missingFields(row).includes(field.name)) {
    wrapper.classList.add("missing");
  }

  const label = document.createElement("span");
  label.className = "field-label";
  if (isFieldRequired(field, row)) label.classList.add("required");
  label.textContent = field.label;
  wrapper.append(label);

  if (field.help) {
    const help = document.createElement("span");
    help.className = "field-help";
    help.textContent = field.help;
    wrapper.append(help);
  }

  const value = fieldValue(row, field.name);
  const disabled = isFrozen();
  if (field.kind === "choice") {
    const choices = document.createElement("span");
    choices.className = "choice-row";
    for (const [optionValue, optionLabel] of field.options || []) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "choice-button";
      button.textContent = optionLabel;
      button.disabled = disabled;
      if (value === optionValue) button.classList.add("selected");
      button.addEventListener("click", () => {
        for (const sibling of choices.querySelectorAll(".choice-button")) {
          sibling.classList.remove("selected");
        }
        button.classList.add("selected");
        wrapper.classList.remove("missing");
        markFieldChanged(field.name, optionValue);
      });
      choices.append(button);
    }
    wrapper.append(choices);
    return wrapper;
  }

  let input;
  if (field.kind === "textarea") {
    input = document.createElement("textarea");
    input.rows = field.rows || 4;
  } else if (field.kind === "select") {
    input = document.createElement("select");
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Выберите после просмотра";
    input.append(placeholder);
    for (const [optionValue, optionLabel] of field.options || []) {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = optionLabel;
      input.append(option);
    }
  } else {
    input = document.createElement("input");
    input.type = "text";
  }
  input.name = field.name;
  input.value = value;
  input.disabled = disabled;
  input.addEventListener("input", () => {
    wrapper.classList.remove("missing");
    markFieldChanged(field.name, input.value);
    if (field.name === "decision") {
      renderForm();
    }
  });
  input.addEventListener("change", () => {
    wrapper.classList.remove("missing");
    markFieldChanged(field.name, input.value);
    if (field.name === "decision") {
      renderForm();
    }
  });
  wrapper.append(input);
  return wrapper;
}

function renderForm() {
  const row = currentRow();
  elements.reviewForm.replaceChildren();
  for (const field of view.protocol.fields) {
    elements.reviewForm.append(buildField(field, row));
  }
}

function pageUrl(role) {
  return `/api/page/${currentIndex()}/${role}?token=${encodeURIComponent(token)}`;
}

function showPage(role) {
  activePageRole = role;
  elements.sourcePage.src = pageUrl(role);
  elements.sourcePage.alt =
    role === "current"
      ? "Текущая страница источника"
      : role === "previous"
        ? "Предыдущая страница источника"
        : "Следующая страница источника";
  elements.pageLabel.textContent = currentUnit().page_labels[role];
  for (const tab of elements.pageTabs.querySelectorAll("button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.role === role));
  }
  elements.pageCanvas.scrollTo({ top: 0, left: 0 });
}

function applyZoom() {
  elements.sourcePage.style.width = `${Math.round(zoom * 100)}%`;
  elements.zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
}

function renderCurrentUnit() {
  const unit = currentUnit();
  elements.unitContext.textContent = unit.context;
  elements.unitHeading.textContent = unit.unit_id;
  elements.unitInstruction.textContent = unit.instruction;
  elements.blindNotice.textContent = view.protocol.blind_notice;
  elements.unitPosition.textContent =
    `Единица ${currentIndex() + 1} из ${view.units.length}`;
  elements.previousUnit.disabled = currentIndex() === 0;
  elements.nextUnit.disabled = currentIndex() === view.units.length - 1;
  elements.nextUnit.textContent =
    currentIndex() === view.units.length - 1 ? "К завершению →" : "Далее →";
  zoom = 1;
  activePageRole = "current";
  showPage("current");
  applyZoom();
  elements.judgmentPanel.scrollTo({ top: 0, left: 0 });
  renderForm();
}

function renderAll() {
  elements.title.textContent = view.protocol.short_title;
  document.title = `${view.protocol.short_title} · Tree of Sophia`;
  document.body.classList.toggle("submitted", isFrozen());
  updateProgress();
  renderQueue();
  renderCurrentUnit();
  elements.app.setAttribute("aria-busy", "false");
  if (isFrozen()) {
    setSaveStatus("Pass 1 зафиксирован", "saved");
    showToast("Человеческий черновик зафиксирован. Он ещё не является gold.", 6000);
  } else if (view.state.status === "in-progress") {
    setSaveStatus("Сохранено", "saved");
  } else {
    setSaveStatus("Готово");
  }
}

async function navigateTo(index) {
  if (index < 0 || index >= view.units.length || index === currentIndex()) return;
  const saved = await flushSave();
  if (!saved) {
    showToast("Переход остановлен: сначала нужно сохранить текущую работу.", 5000);
    return;
  }
  view.state.active_unit_index = index;
  renderQueue();
  renderCurrentUnit();
  if (window.matchMedia("(max-width: 860px)").matches) {
    elements.sourcePanel.scrollIntoView({ block: "start" });
  }
  scheduleSave(0);
}

function scheduleSave(delay = 650) {
  if (!view || isFrozen() || !view.state.reviewer_ref) return;
  saveAgain = true;
  clearTimeout(saveTimer);
  setSaveStatus("Есть несохранённые изменения");
  saveTimer = window.setTimeout(() => flushSave(), delay);
}

async function flushSave() {
  clearTimeout(saveTimer);
  if (!view || isFrozen() || !view.state.reviewer_ref) return true;
  if (saveInFlight) {
    saveAgain = true;
    while (saveInFlight) {
      await new Promise((resolve) => window.setTimeout(resolve, 25));
    }
    return flushSave();
  }
  if (!saveAgain) return true;
  saveAgain = false;
  saveInFlight = true;
  let succeeded = false;
  setSaveStatus("Сохранение…");
  const payload = {
    revision: view.state.revision,
    reviewer_ref: view.state.reviewer_ref,
    active_unit_index: view.state.active_unit_index,
    rows: view.state.rows,
  };
  try {
    const response = await request("/api/autosave", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    view.state = response.state;
    view.completion = response.completion;
    updateProgress();
    setSaveStatus("Сохранено", "saved");
    succeeded = true;
  } catch (error) {
    if (error.status === 409) {
      setSaveStatus("Обновляю состояние…");
      view = await request("/api/session");
      renderAll();
      showToast(
        "Сессия изменилась в другой вкладке. Загружена сохранённая версия; несохранённые изменения этой вкладки не применены.",
        8000,
      );
    } else {
      saveAgain = true;
      setSaveStatus("Не удалось сохранить", "error");
      showToast(`Автосохранение не выполнено: ${error.message}`, 6000);
    }
  } finally {
    saveInFlight = false;
    if (saveAgain) {
      scheduleSave(150);
    }
  }
  return succeeded;
}

async function startReview() {
  const reviewerRef = elements.reviewerInput.value.trim();
  elements.startError.textContent = "";
  if (!reviewerRef) {
    elements.startError.textContent = "Укажите reviewer reference.";
    elements.reviewerInput.focus();
    return;
  }
  view.state.reviewer_ref = reviewerRef;
  saveAgain = true;
  elements.startReview.disabled = true;
  try {
    const saved = await flushSave();
    if (!saved) {
      elements.startError.textContent =
        "Не удалось зафиксировать начало прохода. Проверьте сообщение автосохранения.";
      return;
    }
    elements.startLayer.hidden = true;
    renderAll();
  } catch (error) {
    elements.startError.textContent = error.message;
  } finally {
    elements.startReview.disabled = false;
  }
}

function firstIncompleteIndex() {
  return localCompletion().perUnit.findIndex((complete) => !complete);
}

async function openSubmit() {
  const saved = await flushSave();
  if (!saved) return;
  const completion = localCompletion();
  if (completion.completedUnits !== completion.totalUnits) {
    const index = firstIncompleteIndex();
    if (index >= 0) {
      await navigateTo(index);
      const missing = missingFields(currentRow());
      renderForm();
      showToast(`Заполните обязательные поля: ${missing.join(", ")}`, 5000);
    }
    return;
  }
  elements.submitSummary.replaceChildren();
  const lines = [
    `Рецензент: ${view.state.reviewer_ref}`,
    `Проверено единиц: ${completion.totalUnits}`,
    "Модельные ответы и признанные переводы не были показаны.",
  ];
  for (const line of lines) {
    const item = document.createElement("span");
    item.textContent = line;
    elements.submitSummary.append(item);
  }
  elements.humanAttestation.checked = false;
  elements.submitError.textContent = "";
  elements.submitLayer.hidden = false;
}

async function confirmSubmit() {
  elements.submitError.textContent = "";
  if (!elements.humanAttestation.checked) {
    elements.submitError.textContent =
      "Для фиксации требуется явное подтверждение реального человека.";
    return;
  }
  elements.submitConfirm.disabled = true;
  try {
    const saved = await flushSave();
    if (!saved) {
      elements.submitError.textContent =
        "Сначала необходимо сохранить последние изменения.";
      return;
    }
    const response = await request("/api/submit", {
      method: "POST",
      body: JSON.stringify({
        revision: view.state.revision,
        performed_by_real_human: true,
      }),
    });
    view = response;
    elements.submitLayer.hidden = true;
    renderAll();
  } catch (error) {
    elements.submitError.textContent = error.message;
  } finally {
    elements.submitConfirm.disabled = false;
  }
}

function openFeedback() {
  elements.feedbackError.textContent = "";
  elements.feedbackNote.value = "";
  elements.feedbackLayer.hidden = false;
  elements.feedbackNote.focus();
}

async function sendFeedback() {
  const note = elements.feedbackNote.value.trim();
  elements.feedbackError.textContent = "";
  if (!note) {
    elements.feedbackError.textContent = "Опишите проблему или неудобство.";
    return;
  }
  elements.feedbackSend.disabled = true;
  try {
    await request("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        category: elements.feedbackCategory.value,
        note,
        unit_id: currentUnit().unit_id,
      }),
    });
    elements.feedbackLayer.hidden = true;
    showToast("Обратная связь сохранена отдельно от решения по источнику.");
  } catch (error) {
    elements.feedbackError.textContent = error.message;
  } finally {
    elements.feedbackSend.disabled = false;
  }
}

function closeModal(name) {
  if (name === "feedback") elements.feedbackLayer.hidden = true;
  if (name === "submit") elements.submitLayer.hidden = true;
}

function bindEvents() {
  elements.pageTabs.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-role]");
    if (button) showPage(button.dataset.role);
  });
  document.getElementById("zoom-in").addEventListener("click", () => {
    zoom = Math.min(3, zoom + 0.2);
    applyZoom();
  });
  document.getElementById("zoom-out").addEventListener("click", () => {
    zoom = Math.max(0.4, zoom - 0.2);
    applyZoom();
  });
  document.getElementById("zoom-fit").addEventListener("click", () => {
    zoom = 1;
    applyZoom();
    elements.pageCanvas.scrollTo({ top: 0, left: 0, behavior: "smooth" });
  });
  document.getElementById("viewer-fullscreen").addEventListener("click", async () => {
    if (!document.fullscreenElement) {
      await elements.pageViewer.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  });
  elements.previousUnit.addEventListener("click", () => navigateTo(currentIndex() - 1));
  elements.nextUnit.addEventListener("click", () => {
    if (currentIndex() === view.units.length - 1) {
      openSubmit();
    } else {
      navigateTo(currentIndex() + 1);
    }
  });
  elements.startReview.addEventListener("click", startReview);
  elements.reviewerInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") startReview();
  });
  elements.submitReview.addEventListener("click", openSubmit);
  elements.submitConfirm.addEventListener("click", confirmSubmit);
  elements.feedbackOpen.addEventListener("click", openFeedback);
  elements.feedbackSend.addEventListener("click", sendFeedback);
  document.querySelectorAll("[data-close]").forEach((button) => {
    button.addEventListener("click", () => closeModal(button.dataset.close));
  });
  for (const eventName of ["keydown", "pointerdown", "wheel", "input"]) {
    document.addEventListener(eventName, () => {
      lastInteractionAt = Date.now();
    }, { passive: true });
  }
  window.addEventListener("focus", () => {
    lastInteractionAt = Date.now();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      saveAgain = true;
      flushSave();
    }
    if (event.altKey && event.key === "ArrowRight") {
      event.preventDefault();
      navigateTo(Math.min(view.units.length - 1, currentIndex() + 1));
    }
    if (event.altKey && event.key === "ArrowLeft") {
      event.preventDefault();
      navigateTo(Math.max(0, currentIndex() - 1));
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && saveAgain) {
      flushSave();
    }
  });
}

function startActiveTimeObservation() {
  window.setInterval(() => {
    if (
      !view ||
      isFrozen() ||
      !view.state.reviewer_ref ||
      document.hidden ||
      !document.hasFocus() ||
      Date.now() - lastInteractionAt > 10 * 60_000
    ) {
      return;
    }
    currentRow().active_seconds = Number(currentRow().active_seconds || 0) + 1;
    if (Math.round(currentRow().active_seconds) % 10 === 0) {
      scheduleSave(0);
    }
  }, 1000);
}

async function boot() {
  bindEvents();
  try {
    view = await request("/api/session");
    elements.startDescription.textContent =
      `${view.protocol.title}. Подготовлено ${view.packet.unit_count} единиц.`;
    if (!view.state.reviewer_ref && !isFrozen()) {
      elements.startLayer.hidden = false;
    } else {
      elements.reviewerInput.value = view.state.reviewer_ref || "";
    }
    renderAll();
    startActiveTimeObservation();
  } catch (error) {
    elements.saveStatus.textContent = "Workbench недоступен";
    elements.saveStatus.style.color = "var(--danger)";
    showToast(`Не удалось открыть review session: ${error.message}`, 10_000);
  }
}

boot();
