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
let feedbackAttachments = [];

const feedbackAttachmentLimits = {
  count: 4,
  bytesEach: 8 * 1024 * 1024,
  bytesTotal: 12 * 1024 * 1024,
};

const elements = {
  app: document.getElementById("app"),
  title: document.getElementById("protocol-title"),
  blindBadge: document.getElementById("blind-badge"),
  saveStatus: document.getElementById("save-status"),
  reviewerChip: document.getElementById("reviewer-chip"),
  progressLabel: document.getElementById("progress-label"),
  progressBar: document.getElementById("progress-bar"),
  unitList: document.getElementById("unit-list"),
  submitReview: document.getElementById("submit-review"),
  queueBoundary: document.getElementById("queue-boundary"),
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
  sourceCaptionNote: document.getElementById("source-caption-note"),
  zoomLabel: document.getElementById("zoom-label"),
  candidateCard: document.getElementById("candidate-card"),
  candidateLabel: document.getElementById("candidate-label"),
  candidateText: document.getElementById("candidate-text"),
  candidateCorrect: document.getElementById("candidate-correct"),
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
  feedbackDropzone: document.getElementById("feedback-dropzone"),
  feedbackFileInput: document.getElementById("feedback-file-input"),
  feedbackAttachmentList: document.getElementById("feedback-attachment-list"),
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
  if (value === null || value === undefined) return "";
  return Array.isArray(value) ? value : String(value);
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
    if (field.required_unless) {
      const controlValue = row.values[field.required_unless.field];
      if (!(field.required_unless.values || []).includes(controlValue)) {
        required = true;
      }
    }
    if (
      required &&
      (
        value === null ||
        value === undefined ||
        (Array.isArray(value) ? value.length === 0 : String(value).trim() === "")
      )
    ) {
      missing.add(field.name);
    }
  }
  if (
    view.protocol.review_mode !== "candidate-review" &&
    decision &&
    decision !== "accept"
  ) {
    let rationale = row.values.notes;
    if (view.protocol.protocol_id.includes("gold-page")) {
      rationale = rationale || row.values.source_damage_or_ambiguity;
    }
    if (!rationale || !String(rationale).trim()) {
      missing.add("notes");
    }
  }
  if (view.protocol.review_mode === "candidate-review") {
    const scope = row.values.language_review_scope;
    if (
      scope === "visual-only" &&
      decision &&
      !["language-not-assessed", "uncertain", "reject"].includes(decision)
    ) {
      missing.add("decision");
    }
    if (
      ["full", "partial"].includes(scope) &&
      decision === "language-not-assessed"
    ) {
      missing.add("decision");
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
  const candidateReview = view.protocol.review_mode === "candidate-review";
  elements.progressLabel.textContent =
    `${completion.completedUnits} / ${completion.totalUnits}`;
  elements.progressBar.style.width =
    `${(completion.completedUnits / completion.totalUnits) * 100}%`;
  elements.reviewerChip.textContent =
    view.state.reviewer_ref || "Рецензент не указан";
  elements.submitReview.textContent = isFrozen()
    ? candidateReview
      ? "Ревью зафиксировано"
      : "Pass 1 зафиксирован"
    : completion.completedUnits === completion.totalUnits
      ? candidateReview
        ? "Завершить ревью"
        : "Завершить проход"
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
    strong.textContent = unit.queue_title || unit.title || unit.unit_id;
    const context = document.createElement("span");
    context.textContent = unit.queue_context || unit.context;
    copy.append(strong, context);

    const dot = document.createElement("span");
    dot.className = "unit-dot";
    dot.setAttribute("aria-hidden", "true");

    button.append(number, copy, dot);
    button.title = `Технический ID: ${unit.unit_id}`;
    button.addEventListener("click", () => navigateTo(index));
    elements.unitList.append(button);
  });
}

function isFieldRequired(field, row) {
  if (field.always_required) return true;
  if ((field.required_for || []).includes(selectedDecision(row.values))) {
    return true;
  }
  if (field.required_unless) {
    const controlValue = row.values[field.required_unless.field];
    return !(field.required_unless.values || []).includes(controlValue);
  }
  return false;
}

function isFieldVisible(field, row) {
  const decision = selectedDecision(row.values);
  if (field.visible_for && !field.visible_for.includes(decision)) {
    return false;
  }
  if (field.hidden_when) {
    const controlValue = row.values[field.hidden_when.field];
    if ((field.hidden_when.values || []).includes(controlValue)) {
      return false;
    }
  }
  return true;
}

function candidateDecisionOptions(field, row) {
  const options = field.options || [];
  if (
    view.protocol.review_mode !== "candidate-review" ||
    field.name !== "decision"
  ) {
    return options;
  }
  const scope = row.values.language_review_scope;
  if (scope === "visual-only") {
    return options.filter(([value]) =>
      ["language-not-assessed", "uncertain", "reject"].includes(value)
    );
  }
  if (["full", "partial"].includes(scope)) {
    return options.filter(([value]) => value !== "language-not-assessed");
  }
  return options;
}

function markFieldChanged(fieldName, value) {
  const normalized =
    value === "" || (Array.isArray(value) && value.length === 0) ? null : value;
  currentRow().values[fieldName] = normalized;
  if (
    view.protocol.review_mode === "candidate-review" &&
    fieldName === "language_review_scope"
  ) {
    const language = currentUnit().language;
    view.state.rows.forEach((row, index) => {
      if (view.units[index].language !== language) return;
      row.values.language_review_scope = normalized;
      if (normalized === "visual-only") {
        row.values.text_fidelity = null;
        row.values.completeness = null;
        row.values.error_types = null;
        row.values.corrected_text = null;
        if (
          row.values.decision &&
          !["language-not-assessed", "uncertain", "reject"].includes(
            row.values.decision,
          )
        ) {
          row.values.decision = null;
        }
      } else if (row.values.decision === "language-not-assessed") {
        row.values.decision = null;
      }
    });
  }
  updateProgress();
  renderQueue();
  scheduleSave();
}

function appendCharacterTools(wrapper, input, characters) {
  if (!characters || !characters.length) return;
  const toolbar = document.createElement("span");
  toolbar.className = "character-tools";
  const hint = document.createElement("span");
  hint.textContent = "Вставить:";
  toolbar.append(hint);
  for (const character of characters) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "character-button";
    button.textContent = character;
    button.title = `Вставить ${character}`;
    button.disabled = isFrozen();
    button.addEventListener("click", () => {
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      input.setRangeText(character, start, end, "end");
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
    });
    toolbar.append(button);
  }
  wrapper.append(toolbar);
}

function buildField(field, row) {
  const isButtonGroup = field.kind === "choice" || field.kind === "multi-choice";
  const wrapper = document.createElement(isButtonGroup ? "div" : "label");
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
  if (isButtonGroup) {
    const choices = document.createElement("span");
    choices.className = "choice-row";
    choices.setAttribute("role", "group");
    choices.setAttribute("aria-label", field.label);
    const selected = new Set(
      field.kind === "multi-choice" && Array.isArray(value)
        ? value
        : value
          ? [value]
          : [],
    );
    for (const [optionValue, optionLabel] of candidateDecisionOptions(field, row)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "choice-button";
      button.textContent = optionLabel;
      button.disabled = disabled;
      if (selected.has(optionValue)) button.classList.add("selected");
      button.addEventListener("click", () => {
        if (field.kind === "multi-choice") {
          if (selected.has(optionValue)) {
            selected.delete(optionValue);
            button.classList.remove("selected");
          } else {
            selected.add(optionValue);
            button.classList.add("selected");
          }
          markFieldChanged(field.name, [...selected]);
        } else {
          for (const sibling of choices.querySelectorAll(".choice-button")) {
            sibling.classList.remove("selected");
          }
          button.classList.add("selected");
          wrapper.classList.remove("missing");
          markFieldChanged(field.name, optionValue);
          if (field.name === "language_review_scope") {
            renderCandidate();
            renderForm();
          }
        }
        wrapper.classList.remove("missing");
      });
      choices.append(button);
    }
    wrapper.append(choices);
    return wrapper;
  }

  let input;
  if (field.kind === "textarea" || field.kind === "correction-textarea") {
    input = document.createElement("textarea");
    input.rows = field.rows || 4;
  } else if (field.kind === "select") {
    input = document.createElement("select");
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Выберите после просмотра";
    input.append(placeholder);
    for (const [optionValue, optionLabel] of candidateDecisionOptions(field, row)) {
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
  appendCharacterTools(wrapper, input, field.character_tools || []);
  const handleValueChange = () => {
    wrapper.classList.remove("missing");
    if (
      field.name === "decision" &&
      input.value === "corrected" &&
      !row.values.corrected_text
    ) {
      row.values.corrected_text = currentUnit().candidate_text;
    }
    markFieldChanged(field.name, input.value);
    if (field.name === "decision") {
      renderCandidate();
      renderForm();
    }
  };
  input.addEventListener(field.kind === "select" ? "change" : "input", handleValueChange);
  wrapper.append(input);
  return wrapper;
}

function renderForm() {
  const row = currentRow();
  elements.reviewForm.replaceChildren();
  for (const field of view.protocol.fields) {
    if (!isFieldVisible(field, row)) continue;
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
  const canvasStyle = window.getComputedStyle(elements.pageCanvas);
  const horizontalPadding =
    Number.parseFloat(canvasStyle.paddingLeft) +
    Number.parseFloat(canvasStyle.paddingRight);
  const fitWidth = Math.max(1, elements.pageCanvas.clientWidth - horizontalPadding);
  const targetWidth = `${Math.round(fitWidth * zoom)}px`;
  elements.sourcePage.style.width = targetWidth;
  elements.sourcePage.style.minWidth = targetWidth;
  elements.zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
}

function renderCandidate() {
  const unit = currentUnit();
  if (!view.protocol.candidate_visible || !unit.candidate_text) {
    elements.candidateCard.hidden = true;
    return;
  }
  elements.candidateCard.hidden = false;
  elements.candidateLabel.textContent =
    `${unit.candidate_label} · ${unit.candidate_position} из ${unit.candidate_count}`;
  elements.candidateText.textContent = unit.candidate_text.trimEnd();
  const scope = currentRow().values.language_review_scope;
  const correctionActive = currentRow().values.decision === "corrected";
  elements.candidateCorrect.disabled = isFrozen() || scope === "visual-only";
  elements.candidateCorrect.textContent = correctionActive
    ? "Продолжить исправление"
    : scope === "visual-only"
      ? "Языковая правка не заявлена"
      : "Исправить только ошибки";
}

function renderCurrentUnit() {
  const unit = currentUnit();
  elements.unitContext.textContent = unit.context;
  elements.unitHeading.textContent = unit.title || unit.unit_id;
  elements.unitHeading.title = `Технический ID: ${unit.unit_id}`;
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
  renderCandidate();
  renderForm();
}

function renderAll() {
  elements.title.textContent = view.protocol.short_title;
  elements.blindBadge.textContent = view.protocol.badge_label || "Blind";
  const candidateReview = view.protocol.review_mode === "candidate-review";
  elements.queueBoundary.textContent = candidateReview
    ? "Здесь сохраняется ваша оценка кандидатов. Она не превращает текст в эталон и не ранжирует методы автоматически."
    : "Здесь сохраняется только независимый калибровочный черновик.";
  elements.sourceCaptionNote.textContent = candidateReview
    ? "Страница и байты кандидата проверены машиной; качество оценивает человек."
    : "Источник проверен машиной; содержимое оценивает человек.";
  document.title = `${view.protocol.short_title} · Tree of Sophia`;
  document.body.classList.toggle("submitted", isFrozen());
  document.body.classList.toggle("candidate-review", candidateReview);
  updateProgress();
  renderQueue();
  renderCurrentUnit();
  elements.app.setAttribute("aria-busy", "false");
  if (isFrozen()) {
    setSaveStatus(
      view.protocol.review_mode === "candidate-review"
        ? "Ревью зафиксировано"
        : "Pass 1 зафиксирован",
      "saved",
    );
    showToast(
      view.protocol.review_mode === "candidate-review"
        ? "Review draft зафиксирован. Он не является gold или общим рейтингом методов."
        : "Человеческий черновик зафиксирован. Он ещё не является gold.",
      6000,
    );
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
    elements.startError.textContent = "Укажите имя или устойчивый псевдоним.";
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
    view.protocol.review_mode === "candidate-review"
      ? "Названия методов были скрыты; их OCR-тексты были показаны для оценки."
      : "Модельные ответы и признанные переводы не были показаны.",
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

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => resolve(String(reader.result)));
    reader.addEventListener("error", () => reject(new Error("Не удалось прочитать изображение.")));
    reader.readAsDataURL(file);
  });
}

function renderFeedbackAttachments() {
  elements.feedbackAttachmentList.replaceChildren();
  elements.feedbackDropzone.classList.toggle(
    "has-attachments",
    feedbackAttachments.length > 0,
  );
  feedbackAttachments.forEach((attachment, index) => {
    const item = document.createElement("article");
    item.className = "feedback-attachment";

    const preview = document.createElement("img");
    preview.src = attachment.dataUrl;
    preview.alt = `Скриншот ${index + 1}`;

    const copy = document.createElement("span");
    copy.className = "feedback-attachment-copy";
    const name = document.createElement("strong");
    name.textContent = attachment.name;
    const size = document.createElement("span");
    size.textContent = `${(attachment.bytes / (1024 * 1024)).toFixed(2)} МиБ`;
    copy.append(name, size);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "feedback-attachment-remove";
    remove.textContent = "Удалить";
    remove.addEventListener("click", () => {
      feedbackAttachments.splice(index, 1);
      renderFeedbackAttachments();
    });
    item.append(preview, copy, remove);
    elements.feedbackAttachmentList.append(item);
  });
}

function resetFeedbackAttachments() {
  feedbackAttachments = [];
  elements.feedbackFileInput.value = "";
  renderFeedbackAttachments();
}

async function addFeedbackFiles(fileList) {
  const files = [...fileList].filter((file) => file);
  if (!files.length) return;
  elements.feedbackError.textContent = "";

  if (feedbackAttachments.length + files.length > feedbackAttachmentLimits.count) {
    elements.feedbackError.textContent =
      `Можно приложить не более ${feedbackAttachmentLimits.count} изображений.`;
    return;
  }
  const supportedTypes = new Set(["image/png", "image/jpeg", "image/webp"]);
  const currentBytes = feedbackAttachments.reduce(
    (total, attachment) => total + attachment.bytes,
    0,
  );
  const incomingBytes = files.reduce((total, file) => total + file.size, 0);
  const unsupported = files.find((file) => !supportedTypes.has(file.type));
  if (unsupported) {
    elements.feedbackError.textContent =
      "Поддерживаются скриншоты PNG, JPEG и WebP.";
    return;
  }
  const oversized = files.find((file) => file.size > feedbackAttachmentLimits.bytesEach);
  if (oversized) {
    elements.feedbackError.textContent =
      "Один скриншот должен быть не больше 8 МиБ.";
    return;
  }
  if (currentBytes + incomingBytes > feedbackAttachmentLimits.bytesTotal) {
    elements.feedbackError.textContent =
      "Общий размер скриншотов должен быть не больше 12 МиБ.";
    return;
  }

  elements.feedbackSend.disabled = true;
  try {
    for (const file of files) {
      const dataUrl = await readFileAsDataUrl(file);
      const separator = dataUrl.indexOf(",");
      if (separator < 0) throw new Error("Некорректное изображение из буфера обмена.");
      feedbackAttachments.push({
        name: file.name || `screenshot-${feedbackAttachments.length + 1}.png`,
        mediaType: file.type,
        bytes: file.size,
        dataUrl,
        dataBase64: dataUrl.slice(separator + 1),
      });
    }
    renderFeedbackAttachments();
    showToast(
      feedbackAttachments.length === 1
        ? "Скриншот приложен к обратной связи."
        : `Приложено скриншотов: ${feedbackAttachments.length}.`,
    );
  } catch (error) {
    elements.feedbackError.textContent = error.message;
  } finally {
    elements.feedbackSend.disabled = false;
  }
}

function openFeedback() {
  elements.feedbackError.textContent = "";
  elements.feedbackLayer.hidden = false;
  elements.feedbackNote.focus();
}

async function sendFeedback() {
  const note = elements.feedbackNote.value.trim();
  elements.feedbackError.textContent = "";
  if (!note && feedbackAttachments.length === 0) {
    elements.feedbackError.textContent =
      "Напишите комментарий или приложите скриншот.";
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
        attachments: feedbackAttachments.map((attachment) => ({
          name: attachment.name,
          media_type: attachment.mediaType,
          data_base64: attachment.dataBase64,
        })),
      }),
    });
    elements.feedbackLayer.hidden = true;
    elements.feedbackNote.value = "";
    resetFeedbackAttachments();
    showToast(
      "Обратная связь и скриншоты сохранены отдельно от решения по источнику.",
    );
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
  document.addEventListener("fullscreenchange", () => {
    window.requestAnimationFrame(applyZoom);
  });
  window.addEventListener("resize", () => {
    window.requestAnimationFrame(applyZoom);
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
  elements.candidateCorrect.addEventListener("click", () => {
    if (currentRow().values.language_review_scope === "visual-only") {
      showToast(
        "Языковая правка отключена в режиме «Язык не читаю». Можно оценить страницу и структуру.",
        5000,
      );
      return;
    }
    if (!currentRow().values.corrected_text) {
      currentRow().values.corrected_text = currentUnit().candidate_text;
    }
    currentRow().values.decision = "corrected";
    updateProgress();
    renderQueue();
    renderCandidate();
    renderForm();
    scheduleSave();
    window.requestAnimationFrame(() => {
      elements.reviewForm
        .querySelector('[name="corrected_text"]')
        ?.focus();
    });
  });
  elements.feedbackSend.addEventListener("click", sendFeedback);
  elements.feedbackDropzone.addEventListener("click", () => {
    elements.feedbackFileInput.click();
  });
  elements.feedbackDropzone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      elements.feedbackFileInput.click();
    }
  });
  elements.feedbackFileInput.addEventListener("change", () => {
    addFeedbackFiles(elements.feedbackFileInput.files);
    elements.feedbackFileInput.value = "";
  });
  elements.feedbackLayer.addEventListener("paste", (event) => {
    const imageFiles = [...(event.clipboardData?.items || [])]
      .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
      .map((item) => item.getAsFile())
      .filter(Boolean);
    if (imageFiles.length) {
      event.preventDefault();
      addFeedbackFiles(imageFiles);
    }
  });
  for (const eventName of ["dragenter", "dragover"]) {
    elements.feedbackDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.feedbackDropzone.classList.add("drag-active");
    });
  }
  for (const eventName of ["dragleave", "drop"]) {
    elements.feedbackDropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      elements.feedbackDropzone.classList.remove("drag-active");
    });
  }
  elements.feedbackDropzone.addEventListener("drop", (event) => {
    addFeedbackFiles(event.dataTransfer?.files || []);
  });
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
