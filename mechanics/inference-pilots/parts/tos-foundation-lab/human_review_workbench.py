#!/usr/bin/env python3
"""Serve one verified Tree of Sophia human-review pass on loopback."""

from __future__ import annotations

import base64
import binascii
import copy
import fcntl
import hashlib
import json
import math
import mimetypes
import os
import re
import secrets
import tempfile
import threading
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from human_gold_review import verify_human_gold_review_manifest
from ocr_candidate_review import verify_ocr_candidate_review_manifest
from translation_source_review import verify_translation_source_review_manifest


PART_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PART_ROOT / "workbench"
DEFAULT_HUMAN_REVIEW_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab/"
    "human-review"
)
MAX_REQUEST_BYTES = 18 * 1024 * 1024
MAX_TEXT_FIELD_CHARS = 500_000
MAX_FEEDBACK_ATTACHMENTS = 4
MAX_FEEDBACK_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_FEEDBACK_ATTACHMENT_TOTAL_BYTES = 12 * 1024 * 1024
AUTHORITY_BOUNDARY = (
    "one real-human pass draft only; workbench submission is not independent "
    "double-check, adjudication, source acceptance, gold, translation, or canon"
)
OCR_CANDIDATE_REVIEW_AUTHORITY_BOUNDARY = (
    "one real-human source-visible OCR candidate-review draft only; submission "
    "does not create source truth, gold, accepted text, a general method "
    "ranking, translation, or canon"
)
FEEDBACK_CATEGORIES = {
    "unclear-task",
    "wrong-source",
    "interface-friction",
    "technical-problem",
    "other",
}
FEEDBACK_IMAGE_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

GOLD_SOURCE_LABELS: dict[str, dict[str, str]] = {
    "ocr-antonovsky-2007": {
        "short": "Антоновский, 2007",
        "full": "Перевод П. Антоновского, 2007",
        "language": "Русский",
    },
    "ocr-mysl-1996": {
        "short": "«Мысль», 1996",
        "full": "Собрание сочинений, «Мысль», 1996",
        "language": "Русский",
    },
    "ocr-naumann-1893": {
        "short": "Naumann, 1893",
        "full": "Немецкий оригинал, C. G. Naumann, 1893",
        "language": "Немецкий",
    },
}

DIFFICULTY_LABELS = {
    "ordinary": "обычная",
    "hard": "сложная",
    "adversarial": "особо сложная",
}

STRATA_LABELS = {
    "opening-and-page-boundary": "начало или граница страницы",
    "ordinary-prose": "обычная проза",
    "bibliographic-and-rights-front-matter": "выходные данные",
    "dense-or-dialogic-prose": "плотный текст или диалог",
    "song-poetry-or-unusual-punctuation": (
        "стихотворная форма или необычная пунктуация"
    ),
    "late-work-and-ending": "поздняя часть или финал",
}

LAYOUT_POSTURE_LABELS = {
    "prose-at-page-start": "проза в начале страницы",
    "prose-at-page-end": "проза в конце страницы",
    "prose-crosses-page-boundary": "проза через границу страниц",
    "prose-after-heading": "проза после заголовка",
    "ordinary-prose": "обычная проза",
}


class HumanReviewWorkbenchError(RuntimeError):
    """Raised when a review session cannot be served without weakening its gates."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HumanReviewWorkbenchError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HumanReviewWorkbenchError(f"{path} must contain a JSON object")
    return payload


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HumanReviewWorkbenchError(f"cannot read {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise HumanReviewWorkbenchError(f"{path}:{line_number} is blank")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HumanReviewWorkbenchError(
                f"cannot read {path}:{line_number}: {exc}"
            ) from exc
        if not isinstance(row, dict):
            raise HumanReviewWorkbenchError(
                f"{path}:{line_number} must contain an object"
            )
        rows.append(row)
    return rows


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _atomic_write_json(path: Path, payload: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise HumanReviewWorkbenchError(
                "feedback attachment target is a symlink"
            )
        os.replace(temporary_path, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _detected_feedback_media_type(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (
        len(payload) >= 12
        and payload.startswith(b"RIFF")
        and payload[8:12] == b"WEBP"
    ):
        return "image/webp"
    return None


def _safe_original_filename(value: object, *, index: int, extension: str) -> str:
    if not isinstance(value, str):
        return f"screenshot-{index + 1}.{extension}"
    leaf = value.replace("\\", "/").rsplit("/", 1)[-1]
    leaf = "".join(character for character in leaf if ord(character) >= 32).strip()
    if not leaf:
        return f"screenshot-{index + 1}.{extension}"
    return leaf[:200]


def _source_group(
    manifest_unit: dict[str, Any], pages: dict[str, Any]
) -> str | None:
    declared = manifest_unit.get("group_id")
    if isinstance(declared, str) and declared in GOLD_SOURCE_LABELS:
        return declared
    current_ref = str(pages.get("current", ""))
    for group_id in GOLD_SOURCE_LABELS:
        if group_id in current_ref:
            return group_id
    return None


def _source_labels(
    manifest_unit: dict[str, Any], pages: dict[str, Any]
) -> dict[str, str]:
    group_id = _source_group(manifest_unit, pages)
    if group_id is not None:
        return GOLD_SOURCE_LABELS[group_id]
    language = str(manifest_unit.get("language", "")).lower()
    return {
        "short": "Источник",
        "full": "Источник",
        "language": "Немецкий" if language == "de" else "Русский",
    }


def _page_number_from_ref(value: object) -> int | None:
    match = re.search(r"(?:p|page-)(\d+)(?:\.[^.]+)?$", str(value))
    return int(match.group(1)) if match else None


def _human_page_label(source_short: str, value: object) -> str:
    page_number = _page_number_from_ref(value)
    if page_number is None:
        return source_short
    return f"{source_short} · PDF-страница {page_number}"


def _humanize_known(value: object, mapping: dict[str, str]) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return mapping.get(raw, raw.replace("-", " "))


GOLD_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "name": "page_and_region_resolved",
        "kind": "choice",
        "label": "Показана правильная страница целиком?",
        "help": (
            "«Да» — если центральная страница совпадает с заданием и видна "
            "полностью. «Нет» — если открыта другая страница или часть страницы "
            "обрезана."
        ),
        "options": (
            ("yes", "Да"),
            ("no", "Нет"),
            ("uncertain", "Не уверен"),
        ),
        "always_required": True,
    },
    {
        "name": "source_legibility",
        "kind": "select",
        "label": "Читаемость источника",
        "options": (
            ("legible", "Читается"),
            ("partly-legible", "Читается частично"),
            ("illegible", "Нечитаемо"),
            ("uncertain", "Не уверен"),
        ),
        "always_required": True,
    },
    {
        "name": "diplomatic_transcription",
        "kind": "textarea",
        "label": "Независимая транскрипция текста страницы",
        "help": (
            "Сохраняйте исходную орфографию, регистр и пунктуацию. Не "
            "подгоняйте текст под печатные строки: сохраняйте абзацы и только "
            "значимые разрывы."
        ),
        "rows": 16,
        "character_tools": ("«", "»", "—", "…"),
        "required_for": ("accept", "accept-with-limits"),
    },
    {
        "name": "layout_and_reading_order",
        "kind": "textarea",
        "label": "Структура и порядок чтения",
        "help": "Опишите колонки, заголовки, сноски и необычный порядок блоков.",
        "rows": 4,
        "required_for": ("accept", "accept-with-limits"),
    },
    {
        "name": "unresolved_glyphs",
        "kind": "textarea",
        "label": "Неуверенные глифы",
        "help": "Один случай на строку; укажите строку или область страницы.",
        "rows": 3,
    },
    {
        "name": "source_damage_or_ambiguity",
        "kind": "textarea",
        "label": "Повреждения и неоднозначности источника",
        "rows": 3,
    },
    {
        "name": "decision",
        "kind": "select",
        "label": "Решение по странице",
        "options": (
            ("accept", "Принять"),
            ("accept-with-limits", "Принять с ограничениями"),
            ("reject", "Отклонить"),
            ("uncertain", "Не уверен"),
            ("abstain", "Воздержаться"),
        ),
        "always_required": True,
    },
    {
        "name": "notes",
        "kind": "textarea",
        "label": "Комментарий",
        "help": "Обязателен, если страница не принята без ограничений.",
        "rows": 3,
    },
)


GERMAN_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "name": "layout_role",
        "kind": "select",
        "label": "Роль видимого фрагмента",
        "options": (
            ("heading", "Заголовок"),
            ("section-marker", "Маркер раздела"),
            ("prose", "Проза"),
            ("quotation", "Цитата"),
            ("continuation", "Продолжение"),
            ("page-furniture", "Служебный элемент страницы"),
            ("mixed", "Смешанная роль"),
            ("uncertain", "Не уверен"),
        ),
        "always_required": True,
    },
    {
        "name": "begins_on_previous_page",
        "kind": "choice",
        "label": "Целевой фрагмент начинается на предыдущей странице?",
        "options": (("yes", "Да"), ("no", "Нет"), ("uncertain", "Не уверен")),
        "always_required": True,
    },
    {
        "name": "continues_on_next_page",
        "kind": "choice",
        "label": "Целевой фрагмент продолжается на следующей странице?",
        "options": (("yes", "Да"), ("no", "Нет"), ("uncertain", "Не уверен")),
        "always_required": True,
    },
    {
        "name": "boundary_start_note",
        "kind": "text",
        "label": "Где точно начинается фрагмент?",
        "help": "Укажите видимый ориентир: строку, заголовок или первые слова.",
        "required_for": ("accept", "accept-with-limits"),
    },
    {
        "name": "boundary_end_note",
        "kind": "text",
        "label": "Где точно заканчивается фрагмент?",
        "help": "Укажите видимый ориентир или последние слова.",
        "required_for": ("accept", "accept-with-limits"),
    },
    {
        "name": "diplomatic_transcription",
        "kind": "textarea",
        "label": "Дипломатическая немецкая транскрипция",
        "help": "Сохраняйте историческую орфографию, регистр и пунктуацию.",
        "rows": 12,
        "character_tools": ("„", "“", "—", "…", "ß"),
        "required_for": ("accept", "accept-with-limits"),
    },
    {
        "name": "uncertain_glyphs",
        "kind": "textarea",
        "label": "Неуверенные глифы, пробелы и соединения",
        "help": "Один случай на строку.",
        "rows": 3,
    },
    {
        "name": "decision",
        "kind": "select",
        "label": "Решение по фрагменту",
        "options": (
            ("accept", "Принять"),
            ("accept-with-limits", "Принять с ограничениями"),
            ("reject", "Отклонить"),
            ("uncertain", "Не уверен"),
            ("defer", "Отложить"),
        ),
        "always_required": True,
    },
    {
        "name": "notes",
        "kind": "textarea",
        "label": "Комментарий",
        "help": "Обязателен, если фрагмент не принят без ограничений.",
        "rows": 3,
    },
)

OCR_CANDIDATE_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "name": "language_review_scope",
        "kind": "choice",
        "label": "Насколько вы знаете язык этой страницы?",
        "help": (
            "Ответ автоматически применяется ко всем кандидатам на этом языке. "
            "Он ограничивает только то, что будет считаться проверенным вами."
        ),
        "options": (
            ("full", "Читаю и могу проверить"),
            ("partial", "Проверю только уверенное"),
            ("visual-only", "Язык не читаю"),
        ),
        "always_required": True,
        "propagate_by": "language",
    },
    {
        "name": "page_and_region_resolved",
        "kind": "choice",
        "label": "Показана правильная страница целиком?",
        "help": (
            "«Да» — если центральная страница совпадает с кандидатом и видна "
            "полностью."
        ),
        "options": (
            ("yes", "Да"),
            ("no", "Нет"),
            ("uncertain", "Не уверен"),
        ),
        "always_required": True,
    },
    {
        "name": "source_legibility",
        "kind": "select",
        "label": "Читаемость источника",
        "options": (
            ("legible", "Читается"),
            ("partly-legible", "Читается частично"),
            ("illegible", "Нечитаемо"),
            ("uncertain", "Не уверен"),
        ),
        "always_required": True,
    },
    {
        "name": "text_fidelity",
        "kind": "select",
        "label": "Насколько точно передан видимый текст?",
        "help": "Оценивайте исходную орфографию, а не исправляйте автора или издание.",
        "options": (
            ("exact", "Точно"),
            ("minor-errors", "Есть мелкие ошибки"),
            ("major-errors", "Есть серьёзные ошибки"),
            ("unusable", "Текст непригоден"),
            ("uncertain", "Не уверен"),
        ),
        "required_unless": {
            "field": "language_review_scope",
            "values": ("visual-only",),
        },
        "hidden_when": {
            "field": "language_review_scope",
            "values": ("visual-only",),
        },
    },
    {
        "name": "completeness",
        "kind": "select",
        "label": "Полнота текста",
        "options": (
            ("complete", "Всё на месте"),
            ("minor-omissions", "Небольшие пропуски"),
            ("major-omissions", "Большие пропуски"),
            ("added-text", "Есть лишний текст"),
            ("uncertain", "Не уверен"),
        ),
        "required_unless": {
            "field": "language_review_scope",
            "values": ("visual-only",),
        },
        "hidden_when": {
            "field": "language_review_scope",
            "values": ("visual-only",),
        },
    },
    {
        "name": "structure_and_order",
        "kind": "select",
        "label": "Структура и порядок чтения",
        "options": (
            ("correct", "Верно"),
            ("minor-errors", "Есть мелкие ошибки"),
            ("major-errors", "Есть серьёзные ошибки"),
            ("unusable", "Порядок разрушен"),
            ("not-assessed", "Не могу оценить"),
        ),
        "always_required": True,
    },
    {
        "name": "error_types",
        "kind": "multi-choice",
        "label": "Что именно не так?",
        "help": "Отметьте только заметные типы ошибок; можно выбрать несколько.",
        "options": (
            ("omission", "Пропуск"),
            ("addition", "Лишний текст"),
            ("substitution", "Подмена"),
            ("spacing", "Пробелы"),
            ("punctuation", "Пунктуация"),
            ("reading-order", "Порядок чтения"),
            ("layout-furniture", "Номера и служебные элементы"),
        ),
        "hidden_when": {
            "field": "language_review_scope",
            "values": ("visual-only",),
        },
    },
    {
        "name": "decision",
        "kind": "select",
        "label": "Итог по кандидату",
        "options": (
            ("accept", "Подходит без исправлений"),
            ("accept-with-limits", "Подходит с замечаниями"),
            ("corrected", "Исправил ошибки"),
            ("reject", "Отклонить"),
            ("uncertain", "Не уверен"),
            ("language-not-assessed", "Текст на этом языке не оценивал"),
        ),
        "always_required": True,
    },
    {
        "name": "corrected_text",
        "kind": "correction-textarea",
        "label": "Исправленный кандидат",
        "help": (
            "Текст уже подставлен. Меняйте только найденные ошибки; это не "
            "перепечатывание с нуля."
        ),
        "rows": 14,
        "character_tools": ("«", "»", "—", "…", "„", "“", "ß"),
        "required_for": ("corrected",),
        "visible_for": ("corrected",),
    },
    {
        "name": "notes",
        "kind": "textarea",
        "label": "Короткое замечание",
        "help": "Можно указать конкретное место или причину неуверенности.",
        "rows": 3,
        "required_for": ("accept-with-limits", "reject", "uncertain"),
    },
)


SELECTION_INSTRUCTIONS = {
    "confirm-visible-complete-prose-unit-without-reusing-v1-text": (
        "Найдите и точно перепишите полный видимый прозаический фрагмент. "
        "Не используйте прежний автоматический кандидат."
    ),
    "identify-first-new-complete-prose-unit-using-page-triplet": (
        "Используя все три страницы, найдите первый новый полный прозаический "
        "фрагмент и зафиксируйте его точные границы."
    ),
    "identify-first-prose-unit-after-visible-heading": (
        "Найдите первый полный прозаический фрагмент после видимого заголовка."
    ),
    "resolve-cross-page-boundary-and-transcribe-complete-prose-unit": (
        "Разрешите переход между страницами и перепишите один полный "
        "прозаический фрагмент."
    ),
}


@dataclass(frozen=True)
class ReviewProtocol:
    protocol_id: str
    title: str
    short_title: str
    unit_id_key: str
    fields: tuple[dict[str, Any], ...]
    expected_unit_count: int | None
    draft_filename: str
    draft_schema_version: str
    manifest_filename: str
    template_key: str = "review_template"
    review_mode: str = "independent"
    candidate_visible: bool = False
    badge_label: str = "Независимый проход"
    blind_notice: str = (
        "Модельные ответы, прежние кандидаты и признанные переводы скрыты. "
        "Судите только по источнику."
    )
    authority_boundary: str = AUTHORITY_BOUNDARY


GOLD_PROTOCOL = ReviewProtocol(
    protocol_id="tos.human-review.gold-page-pass-1.v1",
    title="Независимая калибровочная транскрипция",
    short_title="Независимая калибровка · проход 1",
    unit_id_key="sample_id",
    fields=GOLD_FIELDS,
    expected_unit_count=15,
    draft_filename="human-gold-pass-1.draft.json",
    draft_schema_version="tos_human_gold_review_draft_v1",
    manifest_filename="human-gold-review-manifest.json",
)

GERMAN_PROTOCOL = ReviewProtocol(
    protocol_id="tos.human-review.german-source-pass-1.v1",
    title="Немецкий источник: границы и транскрипция",
    short_title="Немецкий источник · проход 1",
    unit_id_key="review_unit_id",
    fields=GERMAN_FIELDS,
    expected_unit_count=30,
    draft_filename="source-review-pass-1.draft.json",
    draft_schema_version="tos_translation_source_human_review_draft_v2",
    manifest_filename="translation-source-review-manifest.json",
)

OCR_CANDIDATE_PROTOCOL = ReviewProtocol(
    protocol_id="tos.human-review.ocr-candidate-pass-1.v1",
    title="Сверка OCR: оценка и точечное исправление",
    short_title="Сверка OCR · A/B/C",
    unit_id_key="review_unit_id",
    fields=OCR_CANDIDATE_FIELDS,
    expected_unit_count=None,
    draft_filename="ocr-candidate-review-pass-1.draft.json",
    draft_schema_version="tos_ocr_candidate_human_review_draft_v1",
    manifest_filename="ocr-candidate-review-manifest.json",
    review_mode="candidate-review",
    candidate_visible=True,
    badge_label="Методы скрыты",
    blind_notice=(
        "Название метода скрыто, но сам результат показан: сравните его с "
        "источником. Не перепечатывайте страницу с нуля."
    ),
    authority_boundary=OCR_CANDIDATE_REVIEW_AUTHORITY_BOUNDARY,
)


def _field_names(protocol: ReviewProtocol) -> set[str]:
    return {str(field["name"]) for field in protocol.fields}


def _blank_values(protocol: ReviewProtocol) -> dict[str, Any]:
    return {str(field["name"]): None for field in protocol.fields}


def _sanitize_values(
    protocol: ReviewProtocol, values: dict[str, Any]
) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for field in protocol.fields:
        name = str(field["name"])
        options = field.get("options")
        if field.get("kind") == "multi-choice":
            value = values.get(name)
            if value is None:
                sanitized[name] = None
                continue
            if not isinstance(value, list):
                raise HumanReviewWorkbenchError(f"{name} must be a list or null")
            allowed = {str(option[0]) for option in options or ()}
            if (
                len(value) > len(allowed)
                or len(value) != len(set(value))
                or any(not isinstance(item, str) or item not in allowed for item in value)
            ):
                raise HumanReviewWorkbenchError(
                    f"{name} contains an unknown or duplicate option"
                )
            sanitized[name] = list(value) or None
            continue
        value = _sanitize_string(values.get(name), field=name)
        if value is not None and options:
            allowed = {str(option[0]) for option in options}
            if value not in allowed:
                raise HumanReviewWorkbenchError(
                    f"{name} is not an allowed protocol value"
                )
        sanitized[name] = value
    return sanitized


def _sanitize_string(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HumanReviewWorkbenchError(f"{field} must be text or null")
    if len(value) > MAX_TEXT_FIELD_CHARS:
        raise HumanReviewWorkbenchError(f"{field} is too large")
    return value


def _missing_fields(
    protocol: ReviewProtocol, values: dict[str, Any]
) -> list[str]:
    decision = values.get("decision")
    missing: list[str] = []
    for field in protocol.fields:
        name = str(field["name"])
        value = values.get(name)
        required = bool(field.get("always_required"))
        required_for = tuple(field.get("required_for", ()))
        if decision in required_for:
            required = True
        required_unless = field.get("required_unless")
        if isinstance(required_unless, dict):
            control_value = values.get(str(required_unless.get("field", "")))
            excluded_values = tuple(required_unless.get("values", ()))
            if control_value not in excluded_values:
                required = True
        if required and (value is None or (isinstance(value, str) and not value.strip())):
            missing.append(name)
    if (
        protocol is not OCR_CANDIDATE_PROTOCOL
        and decision
        and decision != "accept"
    ):
        rationale = values.get("notes")
        if protocol is GOLD_PROTOCOL:
            rationale = rationale or values.get("source_damage_or_ambiguity")
        if not isinstance(rationale, str) or not rationale.strip():
            missing.append("notes")
    if protocol is OCR_CANDIDATE_PROTOCOL:
        scope = values.get("language_review_scope")
        if scope == "visual-only" and decision not in {
            None,
            "language-not-assessed",
            "uncertain",
            "reject",
        }:
            missing.append("decision")
        if scope in {"full", "partial"} and decision == "language-not-assessed":
            missing.append("decision")
    return sorted(set(missing))


class ReviewContext:
    def __init__(
        self,
        session_dir: Path,
        *,
        allowed_work_root: Path = DEFAULT_HUMAN_REVIEW_ROOT,
    ) -> None:
        self.lock = threading.RLock()
        self.session_dir = session_dir.resolve()
        self.allowed_work_root = allowed_work_root.resolve()
        if not _within(self.session_dir, self.allowed_work_root):
            raise HumanReviewWorkbenchError(
                f"session must stay under {self.allowed_work_root}"
            )
        if not self.session_dir.is_dir():
            raise HumanReviewWorkbenchError(f"session is missing: {self.session_dir}")

        self.session_path = self.session_dir / "review-session.json"
        if self.session_path.is_symlink():
            raise HumanReviewWorkbenchError("review session control file is a symlink")
        self.session = _load_json(self.session_path)
        if self.session.get("private_local_only") is not True:
            raise HumanReviewWorkbenchError("review session is not private-local-only")
        packet = self.session.get("packet")
        if not isinstance(packet, dict):
            raise HumanReviewWorkbenchError("review session has no packet")
        self.packet_root = Path(str(packet.get("root", ""))).resolve()
        if not self.packet_root.is_dir():
            raise HumanReviewWorkbenchError("declared immutable packet is missing")

        if (self.packet_root / GOLD_PROTOCOL.manifest_filename).is_file():
            self.protocol = GOLD_PROTOCOL
            self.manifest_path = self.packet_root / GOLD_PROTOCOL.manifest_filename
            self.manifest = verify_human_gold_review_manifest(self.manifest_path)
        elif (
            self.packet_root / OCR_CANDIDATE_PROTOCOL.manifest_filename
        ).is_file():
            self.protocol = OCR_CANDIDATE_PROTOCOL
            self.manifest_path = (
                self.packet_root / OCR_CANDIDATE_PROTOCOL.manifest_filename
            )
            self.manifest = verify_ocr_candidate_review_manifest(
                self.manifest_path
            )
        elif (self.packet_root / GERMAN_PROTOCOL.manifest_filename).is_file():
            self.protocol = GERMAN_PROTOCOL
            self.manifest_path = self.packet_root / GERMAN_PROTOCOL.manifest_filename
            self.manifest = verify_translation_source_review_manifest(
                self.manifest_path
            )
        else:
            raise HumanReviewWorkbenchError(
                "packet is not a supported verified human-review family"
            )

        if self.manifest.get("packet_id") != packet.get("packet_id"):
            raise HumanReviewWorkbenchError("session and packet identity disagree")
        expected_manifest_sha = packet.get("manifest_sha256")
        if expected_manifest_sha and _sha256_file(self.manifest_path) != expected_manifest_sha:
            raise HumanReviewWorkbenchError("session manifest digest drifted")

        template_record = self.manifest.get(self.protocol.template_key)
        if not isinstance(template_record, dict):
            raise HumanReviewWorkbenchError("packet has no blank review template")
        self.template_path = (
            self.packet_root / str(template_record.get("ref", ""))
        ).resolve()
        if not _within(self.template_path, self.packet_root):
            raise HumanReviewWorkbenchError("review template escaped packet")
        if _sha256_file(self.template_path) != template_record.get("sha256"):
            raise HumanReviewWorkbenchError("review template digest drifted")
        self.template_rows = _load_jsonl(self.template_path)
        expected_unit_count = self.protocol.expected_unit_count
        if expected_unit_count is None:
            expected_unit_count = self.manifest.get("unit_count")
        if (
            not isinstance(expected_unit_count, int)
            or expected_unit_count < 1
            or len(self.template_rows) != expected_unit_count
        ):
            raise HumanReviewWorkbenchError("review template unit count drifted")

        self.units = self._build_units()
        self.unit_ids = [str(unit["unit_id"]) for unit in self.units]
        if len(self.unit_ids) != len(set(self.unit_ids)):
            raise HumanReviewWorkbenchError("review unit IDs are not unique")
        self.page_assets: dict[tuple[int, str], Path] = {}
        for index, row in enumerate(self.template_rows):
            pages = row.get("source_pages")
            if not isinstance(pages, dict):
                raise HumanReviewWorkbenchError(f"unit {index} has no source pages")
            for role in ("previous", "current", "next"):
                asset = (self.packet_root / str(pages.get(role, ""))).resolve()
                if not _within(asset, self.packet_root) or not asset.is_file():
                    raise HumanReviewWorkbenchError(
                        f"unit {index} has invalid {role} page"
                    )
                self.page_assets[(index, role)] = asset

        self.autosave_path = self.session_dir / "human-review-workbench.pass-1.autosave.json"
        self.feedback_path = self.session_dir / "human-review-workbench.feedback.jsonl"
        self.feedback_assets_dir = (
            self.session_dir / "human-review-workbench.feedback-assets"
        )
        self.receipt_path = (
            self.session_dir / "human-review-workbench.pass-1.freeze-receipt.json"
        )
        self.draft_path = self.session_dir / self.protocol.draft_filename
        self.session_lock_path = self.session_dir / ".human-review-workbench.lock"
        for path in (
            self.autosave_path,
            self.feedback_path,
            self.feedback_assets_dir,
            self.receipt_path,
            self.draft_path,
            self.session_lock_path,
        ):
            if path.is_symlink():
                raise HumanReviewWorkbenchError(
                    f"mutable review output is a symlink: {path.name}"
                )
        if self.feedback_assets_dir.exists() and not self.feedback_assets_dir.is_dir():
            raise HumanReviewWorkbenchError(
                "feedback attachment route is not a directory"
            )
        self.state = self._load_or_initialize_state()

    def _build_units(self) -> list[dict[str, Any]]:
        manifest_units = self.manifest.get("units")
        if not isinstance(manifest_units, list):
            raise HumanReviewWorkbenchError("packet manifest has no units")
        manifest_by_id = {
            str(row.get(self.protocol.unit_id_key)): row
            for row in manifest_units
            if isinstance(row, dict)
        }
        plan_by_id: dict[str, dict[str, Any]] = {}
        if self.protocol is GERMAN_PROTOCOL:
            plan_path = Path(str(self.manifest.get("review_plan_ref", ""))).resolve()
            plan = _load_json(plan_path)
            plan_by_id = {
                str(row.get("review_unit_id")): row
                for row in plan.get("units", [])
                if isinstance(row, dict)
            }

        units: list[dict[str, Any]] = []
        for index, template in enumerate(self.template_rows):
            unit_id = str(template.get(self.protocol.unit_id_key, ""))
            manifest_unit = manifest_by_id.get(unit_id)
            if not unit_id or not isinstance(manifest_unit, dict):
                raise HumanReviewWorkbenchError(
                    f"template unit {index} does not resolve in manifest"
                )
            pages = template["source_pages"]
            if self.protocol is GOLD_PROTOCOL:
                source = _source_labels(manifest_unit, pages)
                pdf_page = manifest_unit.get("pdf_page", "?")
                title = f"{source['short']} · PDF-страница {pdf_page}"
                context_parts = [
                    source["language"],
                    f"PDF-страница {pdf_page}",
                    _humanize_known(
                        manifest_unit.get("difficulty"), DIFFICULTY_LABELS
                    ),
                ]
                instruction = (
                    "Перепишите всю текущую страницу по видимому источнику. "
                    "Соседние страницы даны только для контекста."
                )
                strata = manifest_unit.get("strata")
                if isinstance(strata, list) and strata:
                    context_parts.append(
                        " / ".join(
                            _humanize_known(item, STRATA_LABELS)
                            for item in strata
                        )
                    )
                context = " · ".join(part for part in context_parts if part)
                language = str(manifest_unit.get("language", "")).lower() or "ru"
                extra: dict[str, Any] = {}
            elif self.protocol is OCR_CANDIDATE_PROTOCOL:
                source = _source_labels(manifest_unit, pages)
                pdf_page = manifest_unit.get("pdf_page", "?")
                title = f"{source['short']} · PDF-страница {pdf_page}"
                candidate_label = str(
                    manifest_unit.get("candidate_label", "Кандидат")
                )
                queue_title = f"Страница {pdf_page} · {candidate_label}"
                context_parts = [
                    source["language"],
                    candidate_label,
                    _humanize_known(
                        manifest_unit.get("difficulty"), DIFFICULTY_LABELS
                    ),
                ]
                strata = manifest_unit.get("strata")
                if isinstance(strata, list) and strata:
                    context_parts.append(
                        " / ".join(
                            _humanize_known(item, STRATA_LABELS)
                            for item in strata
                        )
                    )
                context = " · ".join(part for part in context_parts if part)
                queue_context = " · ".join(
                    part
                    for part in (
                        source["short"],
                        source["language"],
                        _humanize_known(
                            manifest_unit.get("difficulty"), DIFFICULTY_LABELS
                        ),
                    )
                    if part
                )
                instruction = (
                    "Прочитайте страницу и сверяйте с показанным OCR-текстом. "
                    "Оцените его по критериям; исправляйте только найденные "
                    "ошибки."
                )
                candidate_path = (
                    self.packet_root
                    / str(manifest_unit.get("candidate_ref", ""))
                ).resolve()
                if (
                    not _within(candidate_path, self.packet_root)
                    or not candidate_path.is_file()
                    or candidate_path.is_symlink()
                    or _sha256_file(candidate_path)
                    != manifest_unit.get("candidate_sha256")
                    or candidate_path.stat().st_size
                    != manifest_unit.get("candidate_bytes")
                ):
                    raise HumanReviewWorkbenchError(
                        f"{unit_id}: candidate text drifted"
                    )
                candidate_text = candidate_path.read_text(encoding="utf-8")
                if len(candidate_text) > MAX_TEXT_FIELD_CHARS:
                    raise HumanReviewWorkbenchError(
                        f"{unit_id}: candidate text is too large"
                    )
                language = (
                    str(manifest_unit.get("language", "")).lower() or "und"
                )
                extra = {
                    "queue_title": queue_title,
                    "queue_context": queue_context,
                    "candidate_label": candidate_label,
                    "candidate_position": int(
                        manifest_unit.get("candidate_position", 1)
                    ),
                    "candidate_count": int(
                        manifest_unit.get("candidate_count_for_source", 1)
                    ),
                    "candidate_text": candidate_text,
                    "candidate_sha256": manifest_unit["candidate_sha256"],
                }
            else:
                source = GOLD_SOURCE_LABELS["ocr-naumann-1893"]
                plan_unit = plan_by_id.get(unit_id, {})
                visual = plan_unit.get("visual_context", {})
                current_pdf_page = visual.get("current_pdf_page", "?")
                title = f"{source['short']} · PDF-страница {current_pdf_page}"
                context = (
                    f"{source['language']} · PDF-страница {current_pdf_page}"
                )
                layout_posture = _humanize_known(
                    plan_unit.get("layout_posture"), LAYOUT_POSTURE_LABELS
                )
                if layout_posture:
                    context += f" · {layout_posture}"
                instruction_key = str(plan_unit.get("selection_instruction", ""))
                instruction = SELECTION_INSTRUCTIONS.get(
                    instruction_key,
                    "Определите один полный видимый прозаический фрагмент и "
                    "зафиксируйте его точные границы.",
                )
                language = "de"
                extra = {}
            units.append(
                {
                    "index": index,
                    "unit_id": unit_id,
                    "title": title,
                    "context": context,
                    "instruction": instruction,
                    "language": language,
                    "page_labels": {
                        role: _human_page_label(source["short"], pages[role])
                        for role in ("previous", "current", "next")
                    },
                    **extra,
                }
            )
        return units

    def _new_state(self) -> dict[str, Any]:
        return {
            "schema_version": "tos_human_review_workbench_state_v1",
            "protocol_id": self.protocol.protocol_id,
            "packet_id": self.manifest["packet_id"],
            "packet_manifest_sha256": _sha256_file(self.manifest_path),
            "template_sha256": _sha256_file(self.template_path),
            "session_id": self.session.get("session_id"),
            "pass_number": 1,
            "status": "ready",
            "reviewer_ref": None,
            "started_at_utc": None,
            "updated_at_utc": _utc_now(),
            "submitted_at_utc": None,
            "active_unit_index": 0,
            "revision": 0,
            "rows": [
                {
                    "unit_id": unit_id,
                    "values": _blank_values(self.protocol),
                    "active_seconds": 0.0,
                }
                for unit_id in self.unit_ids
            ],
            "authority_boundary": self.protocol.authority_boundary,
        }

    def _load_or_initialize_state(self) -> dict[str, Any]:
        if self.autosave_path.is_file():
            state = _load_json(self.autosave_path)
            self._validate_saved_state(state)
            receipt_exists = self.receipt_path.is_file()
            draft_exists = self.draft_path.is_file()
            if receipt_exists != draft_exists:
                raise HumanReviewWorkbenchError(
                    "review freeze is partial; draft and receipt must coexist"
                )
            if receipt_exists and draft_exists:
                self._validate_frozen_artifacts(state)
                state["status"] = "submitted-and-frozen"
            elif state.get("status") == "submitted-and-frozen":
                raise HumanReviewWorkbenchError(
                    "autosave claims submission without frozen artifacts"
                )
            return state
        if self.receipt_path.exists() or self.draft_path.exists():
            raise HumanReviewWorkbenchError(
                "draft or receipt exists without a matching workbench autosave"
            )
        return self._new_state()

    def _validate_saved_state(self, state: dict[str, Any]) -> None:
        expected = {
            "schema_version": "tos_human_review_workbench_state_v1",
            "protocol_id": self.protocol.protocol_id,
            "packet_id": self.manifest["packet_id"],
            "packet_manifest_sha256": _sha256_file(self.manifest_path),
            "template_sha256": _sha256_file(self.template_path),
            "session_id": self.session.get("session_id"),
            "pass_number": 1,
            "authority_boundary": self.protocol.authority_boundary,
        }
        for key, value in expected.items():
            if state.get(key) != value:
                raise HumanReviewWorkbenchError(f"autosave drifted at {key}")
        if state.get("status") not in {"in-progress", "submitted-and-frozen"}:
            raise HumanReviewWorkbenchError("autosave status is invalid")
        revision = state.get("revision")
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
        ):
            raise HumanReviewWorkbenchError("autosave revision is invalid")
        active_index = state.get("active_unit_index")
        if (
            not isinstance(active_index, int)
            or isinstance(active_index, bool)
            or not 0 <= active_index < len(self.units)
        ):
            raise HumanReviewWorkbenchError("autosave active unit is invalid")
        reviewer_ref = state.get("reviewer_ref")
        if (
            not isinstance(reviewer_ref, str)
            or not reviewer_ref.strip()
            or len(reviewer_ref) > 200
        ):
            raise HumanReviewWorkbenchError("autosave reviewer identity is invalid")
        rows = state.get("rows")
        if not isinstance(rows, list) or len(rows) != len(self.unit_ids):
            raise HumanReviewWorkbenchError("autosave unit order drifted")
        allowed_fields = _field_names(self.protocol)
        for index, row in enumerate(rows):
            if not isinstance(row, dict) or row.get("unit_id") != self.unit_ids[index]:
                raise HumanReviewWorkbenchError("autosave unit order drifted")
            values = row.get("values")
            if not isinstance(values, dict) or set(values) != allowed_fields:
                raise HumanReviewWorkbenchError(
                    f"autosave row {index} fields drifted"
                )
            if _sanitize_values(self.protocol, values) != values:
                raise HumanReviewWorkbenchError(
                    f"autosave row {index} values drifted"
                )
            active_seconds = row.get("active_seconds")
            if (
                not isinstance(active_seconds, (int, float))
                or isinstance(active_seconds, bool)
                or not math.isfinite(float(active_seconds))
                or active_seconds < 0
                or active_seconds > 7 * 24 * 60 * 60
            ):
                raise HumanReviewWorkbenchError(
                    f"autosave row {index} active_seconds drifted"
                )

    def _validate_frozen_artifacts(self, state: dict[str, Any]) -> None:
        receipt = _load_json(self.receipt_path)
        draft = _load_json(self.draft_path)
        draft_sha = _sha256_file(self.draft_path)
        if receipt.get("draft_sha256") != draft_sha:
            raise HumanReviewWorkbenchError("frozen review draft digest drifted")
        expected_receipt = {
            "schema_version": "tos_human_review_workbench_freeze_receipt_v1",
            "status": "pass-1-draft-frozen",
            "protocol_id": self.protocol.protocol_id,
            "packet_id": self.manifest["packet_id"],
            "session_id": self.session.get("session_id"),
            "packet_manifest_sha256": _sha256_file(self.manifest_path),
            "reviewer_ref": state["reviewer_ref"],
            "performed_by_real_human": True,
            "unit_count": len(self.units),
            "draft_ref": self.draft_path.name,
            "draft_sha256": draft_sha,
            "authority_boundary": self.protocol.authority_boundary,
        }
        for key, value in expected_receipt.items():
            if receipt.get(key) != value:
                raise HumanReviewWorkbenchError(
                    f"frozen review receipt drifted at {key}"
                )
        submitted_at = receipt.get("submitted_at_utc")
        expected_draft = {
            "schema_version": self.protocol.draft_schema_version,
            "packet_id": self.manifest["packet_id"],
            "pass_number": 1,
            "performed_by_real_human": True,
            "reviewer_ref": state["reviewer_ref"],
            "exported_at_utc": submitted_at,
            "rows": self._draft_rows(state),
            "authority_boundary": self.protocol.authority_boundary,
        }
        if self.protocol is GERMAN_PROTOCOL:
            expected_draft["source_acceptance"] = None
        if draft != expected_draft:
            raise HumanReviewWorkbenchError(
                "frozen review draft no longer matches autosave and receipt"
            )

    def public_session(self) -> dict[str, Any]:
        with self.lock:
            completed = [
                not _missing_fields(self.protocol, row["values"])
                for row in self.state["rows"]
            ]
            return {
                "schema_version": "tos_human_review_workbench_view_v1",
                "protocol": {
                    "protocol_id": self.protocol.protocol_id,
                    "title": self.protocol.title,
                    "short_title": self.protocol.short_title,
                    "pass_number": 1,
                    "fields": list(self.protocol.fields),
                    "blind": True,
                    "review_mode": self.protocol.review_mode,
                    "candidate_visible": self.protocol.candidate_visible,
                    "badge_label": self.protocol.badge_label,
                    "blind_notice": self.protocol.blind_notice,
                },
                "packet": {
                    "packet_id": self.manifest["packet_id"],
                    "unit_count": len(self.units),
                },
                "units": copy.deepcopy(self.units),
                "state": copy.deepcopy(self.state),
                "completion": {
                    "completed_units": sum(completed),
                    "total_units": len(completed),
                    "per_unit": completed,
                },
                "authority_boundary": self.protocol.authority_boundary,
            }

    def page_asset(self, index: int, role: str) -> Path:
        asset = self.page_assets.get((index, role))
        if asset is None:
            raise HumanReviewWorkbenchError("unknown source page")
        return asset

    def autosave(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] == "submitted-and-frozen":
                raise HumanReviewWorkbenchError("submitted review is frozen")
            if payload.get("revision") != self.state["revision"]:
                raise HumanReviewWorkbenchError("autosave revision conflict")
            reviewer_ref = _sanitize_string(
                payload.get("reviewer_ref"), field="reviewer_ref"
            )
            if reviewer_ref is None or not reviewer_ref.strip():
                raise HumanReviewWorkbenchError("reviewer_ref is required")
            if len(reviewer_ref) > 200:
                raise HumanReviewWorkbenchError("reviewer_ref is too long")
            existing_reviewer = self.state.get("reviewer_ref")
            if existing_reviewer and reviewer_ref.strip() != existing_reviewer:
                raise HumanReviewWorkbenchError(
                    "reviewer_ref cannot change after the pass begins"
                )
            active_index = payload.get("active_unit_index")
            if (
                not isinstance(active_index, int)
                or isinstance(active_index, bool)
                or not 0 <= active_index < len(self.units)
            ):
                raise HumanReviewWorkbenchError("active unit index is invalid")
            incoming_rows = payload.get("rows")
            if not isinstance(incoming_rows, list) or len(incoming_rows) != len(
                self.units
            ):
                raise HumanReviewWorkbenchError("autosave rows are incomplete")
            allowed_fields = _field_names(self.protocol)
            sanitized_rows: list[dict[str, Any]] = []
            for index, incoming in enumerate(incoming_rows):
                if not isinstance(incoming, dict):
                    raise HumanReviewWorkbenchError(f"row {index} is invalid")
                if incoming.get("unit_id") != self.unit_ids[index]:
                    raise HumanReviewWorkbenchError("autosave unit order changed")
                values = incoming.get("values")
                if not isinstance(values, dict) or set(values) != allowed_fields:
                    raise HumanReviewWorkbenchError(
                        f"row {index} fields do not match protocol"
                    )
                sanitized_values = _sanitize_values(self.protocol, values)
                active_seconds = incoming.get("active_seconds", 0)
                if (
                    not isinstance(active_seconds, (int, float))
                    or isinstance(active_seconds, bool)
                    or not math.isfinite(float(active_seconds))
                    or active_seconds < 0
                    or active_seconds > 7 * 24 * 60 * 60
                ):
                    raise HumanReviewWorkbenchError(
                        f"row {index} active_seconds is invalid"
                    )
                previous_active_seconds = self.state["rows"][index].get(
                    "active_seconds", 0
                )
                if float(active_seconds) < float(previous_active_seconds):
                    raise HumanReviewWorkbenchError(
                        f"row {index} active_seconds cannot move backwards"
                    )
                sanitized_rows.append(
                    {
                        "unit_id": self.unit_ids[index],
                        "values": sanitized_values,
                        "active_seconds": round(float(active_seconds), 3),
                    }
                )
            now = _utc_now()
            self.state.update(
                {
                    "status": "in-progress",
                    "reviewer_ref": reviewer_ref.strip(),
                    "started_at_utc": self.state.get("started_at_utc") or now,
                    "updated_at_utc": now,
                    "active_unit_index": active_index,
                    "revision": int(self.state["revision"]) + 1,
                    "rows": sanitized_rows,
                }
            )
            _atomic_write_json(self.autosave_path, self.state)
            return self.public_session()

    def _decode_feedback_attachments(
        self, payload: dict[str, Any]
    ) -> list[tuple[bytes, str, str]]:
        raw_attachments = payload.get("attachments", [])
        if raw_attachments is None:
            return []
        if not isinstance(raw_attachments, list):
            raise HumanReviewWorkbenchError(
                "feedback attachments must be a list"
            )
        if len(raw_attachments) > MAX_FEEDBACK_ATTACHMENTS:
            raise HumanReviewWorkbenchError(
                f"feedback accepts at most {MAX_FEEDBACK_ATTACHMENTS} images"
            )

        decoded: list[tuple[bytes, str, str]] = []
        total_bytes = 0
        for index, item in enumerate(raw_attachments):
            if not isinstance(item, dict):
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} is invalid"
                )
            media_type = item.get("media_type")
            encoded = item.get("data_base64")
            if media_type not in FEEDBACK_IMAGE_EXTENSIONS:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} has an unsupported image type"
                )
            if not isinstance(encoded, str) or not encoded:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} has no image data"
                )
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} is not valid base64"
                ) from exc
            if not image_bytes:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} is empty"
                )
            if len(image_bytes) > MAX_FEEDBACK_ATTACHMENT_BYTES:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} exceeds 8 MiB"
                )
            detected_media_type = _detected_feedback_media_type(image_bytes)
            if detected_media_type != media_type:
                raise HumanReviewWorkbenchError(
                    f"feedback attachment {index + 1} content does not match its image type"
                )
            total_bytes += len(image_bytes)
            if total_bytes > MAX_FEEDBACK_ATTACHMENT_TOTAL_BYTES:
                raise HumanReviewWorkbenchError(
                    "feedback attachments exceed 12 MiB in total"
                )
            extension = FEEDBACK_IMAGE_EXTENSIONS[media_type]
            original_name = _safe_original_filename(
                item.get("name"), index=index, extension=extension
            )
            decoded.append((image_bytes, media_type, original_name))
        return decoded

    def _store_feedback_attachments(
        self, decoded: list[tuple[bytes, str, str]]
    ) -> list[dict[str, Any]]:
        if not decoded:
            return []
        if self.feedback_assets_dir.is_symlink():
            raise HumanReviewWorkbenchError(
                "feedback attachment route is a symlink"
            )
        self.feedback_assets_dir.mkdir(mode=0o700, exist_ok=True)
        if (
            self.feedback_assets_dir.is_symlink()
            or not self.feedback_assets_dir.is_dir()
            or not _within(
                self.feedback_assets_dir.resolve(), self.session_dir
            )
        ):
            raise HumanReviewWorkbenchError(
                "feedback attachment route escaped the review session"
            )
        os.chmod(self.feedback_assets_dir, 0o700)

        stored: list[dict[str, Any]] = []
        for image_bytes, media_type, original_name in decoded:
            digest = hashlib.sha256(image_bytes).hexdigest()
            extension = FEEDBACK_IMAGE_EXTENSIONS[media_type]
            asset_path = self.feedback_assets_dir / f"sha256-{digest}.{extension}"
            if asset_path.is_symlink():
                raise HumanReviewWorkbenchError(
                    "feedback attachment target is a symlink"
                )
            if asset_path.exists():
                if (
                    not asset_path.is_file()
                    or _sha256_file(asset_path) != digest
                ):
                    raise HumanReviewWorkbenchError(
                        "feedback attachment content-address collision"
                    )
                os.chmod(asset_path, 0o600)
            else:
                _atomic_write_bytes(asset_path, image_bytes)
            stored.append(
                {
                    "attachment_id": f"sha256:{digest}",
                    "ref": asset_path.relative_to(self.session_dir).as_posix(),
                    "sha256": digest,
                    "bytes": len(image_bytes),
                    "media_type": media_type,
                    "original_name": original_name,
                }
            )
        return stored

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            category = _sanitize_string(payload.get("category"), field="category")
            note = _sanitize_string(payload.get("note"), field="note")
            unit_id = _sanitize_string(payload.get("unit_id"), field="unit_id")
            decoded_attachments = self._decode_feedback_attachments(payload)
            if not category:
                raise HumanReviewWorkbenchError("feedback category is required")
            if category not in FEEDBACK_CATEGORIES:
                raise HumanReviewWorkbenchError("feedback category is unknown")
            if note is not None and len(note) > 10_000:
                raise HumanReviewWorkbenchError("feedback note is too long")
            if unit_id is not None and unit_id not in self.unit_ids:
                raise HumanReviewWorkbenchError("feedback unit is unknown")
            if (note is None or not note.strip()) and not decoded_attachments:
                raise HumanReviewWorkbenchError(
                    "feedback note or screenshot is required"
                )
            attachments = self._store_feedback_attachments(decoded_attachments)
            record = {
                "schema_version": "tos_human_review_workbench_feedback_v2",
                "protocol_id": self.protocol.protocol_id,
                "packet_id": self.manifest["packet_id"],
                "session_id": self.session.get("session_id"),
                "unit_id": unit_id,
                "category": category,
                "note": note.strip() if note else "",
                "attachments": attachments,
                "recorded_at_utc": _utc_now(),
                "authority_boundary": (
                    "reviewer feedback about task or interface; not a source "
                    "acceptance decision"
                ),
            }
            _append_jsonl(self.feedback_path, record)
            return {
                "recorded": True,
                "attachment_count": len(attachments),
                "recorded_at_utc": record["recorded_at_utc"],
            }

    def _draft_rows(
        self, state: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        manifest_units = {
            str(unit.get(self.protocol.unit_id_key)): unit
            for unit in self.manifest.get("units", [])
            if isinstance(unit, dict)
        }
        for row in (state or self.state)["rows"]:
            values = row["values"]
            if self.protocol is GOLD_PROTOCOL:
                rows.append(
                    {
                        "sample_id": row["unit_id"],
                        "source_visible": True,
                        "source_file_digest_verified": True,
                        "page_and_region_resolved": values[
                            "page_and_region_resolved"
                        ],
                        "source_legibility": values["source_legibility"],
                        "diplomatic_transcription": values[
                            "diplomatic_transcription"
                        ],
                        "layout_and_reading_order": values[
                            "layout_and_reading_order"
                        ],
                        "unresolved_glyphs": _split_lines(
                            values.get("unresolved_glyphs")
                        ),
                        "source_damage_or_ambiguity": values[
                            "source_damage_or_ambiguity"
                        ],
                        "decision": values["decision"],
                        "elapsed_minutes": round(
                            float(row["active_seconds"]) / 60.0, 1
                        ),
                        "notes": _split_lines(values.get("notes")),
                    }
                )
            elif self.protocol is OCR_CANDIDATE_PROTOCOL:
                unit = manifest_units[row["unit_id"]]
                rows.append(
                    {
                        "review_unit_id": row["unit_id"],
                        "source_sample_id": unit["source_sample_id"],
                        "visual_sample_id": unit["visual_sample_id"],
                        "source_anchor_ref": unit["source_anchor_ref"],
                        "language": unit["language"],
                        "candidate_label": unit["candidate_label"],
                        "candidate_sha256": unit["candidate_sha256"],
                        "source_visible": True,
                        "source_page_digest_verified": True,
                        "language_review_scope": values[
                            "language_review_scope"
                        ],
                        "page_and_region_resolved": values[
                            "page_and_region_resolved"
                        ],
                        "source_legibility": values["source_legibility"],
                        "text_fidelity": values["text_fidelity"],
                        "completeness": values["completeness"],
                        "structure_and_order": values["structure_and_order"],
                        "error_types": list(values.get("error_types") or []),
                        "corrected_text": values["corrected_text"],
                        "decision": values["decision"],
                        "notes": values["notes"],
                        "elapsed_minutes": round(
                            float(row["active_seconds"]) / 60.0, 1
                        ),
                    }
                )
            else:
                rows.append(
                    {
                        "review_unit_id": row["unit_id"],
                        "layout_role": values["layout_role"],
                        "begins_on_previous_page": _choice_to_bool(
                            values["begins_on_previous_page"]
                        ),
                        "continues_on_next_page": _choice_to_bool(
                            values["continues_on_next_page"]
                        ),
                        "boundary_start_note": values["boundary_start_note"],
                        "boundary_end_note": values["boundary_end_note"],
                        "diplomatic_transcription": values[
                            "diplomatic_transcription"
                        ],
                        "uncertain_glyphs": values["uncertain_glyphs"],
                        "decision": values["decision"],
                        "notes": values["notes"],
                    }
                )
        return rows

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] == "submitted-and-frozen":
                return self.public_session()
            if payload.get("revision") != self.state["revision"]:
                raise HumanReviewWorkbenchError("submission revision conflict")
            if payload.get("performed_by_real_human") is not True:
                raise HumanReviewWorkbenchError("real-human attestation is required")
            incomplete = [
                {
                    "unit_id": row["unit_id"],
                    "missing_fields": _missing_fields(
                        self.protocol, row["values"]
                    ),
                }
                for row in self.state["rows"]
                if _missing_fields(self.protocol, row["values"])
            ]
            if incomplete:
                raise HumanReviewWorkbenchError(
                    "submission has incomplete units: "
                    + ", ".join(
                        f"{item['unit_id']}[{','.join(item['missing_fields'])}]"
                        for item in incomplete[:8]
                    )
                )
            reviewer_ref = self.state.get("reviewer_ref")
            if not isinstance(reviewer_ref, str) or not reviewer_ref:
                raise HumanReviewWorkbenchError("reviewer identity is missing")
            submitted_at = _utc_now()
            draft: dict[str, Any] = {
                "schema_version": self.protocol.draft_schema_version,
                "packet_id": self.manifest["packet_id"],
                "pass_number": 1,
                "performed_by_real_human": True,
                "reviewer_ref": reviewer_ref,
                "exported_at_utc": submitted_at,
                "rows": self._draft_rows(),
                "authority_boundary": self.protocol.authority_boundary,
            }
            if self.protocol is GERMAN_PROTOCOL:
                draft["source_acceptance"] = None
            _atomic_write_json(self.draft_path, draft, mode=0o400)
            draft_sha = _sha256_file(self.draft_path)
            receipt = {
                "schema_version": "tos_human_review_workbench_freeze_receipt_v1",
                "status": "pass-1-draft-frozen",
                "protocol_id": self.protocol.protocol_id,
                "packet_id": self.manifest["packet_id"],
                "session_id": self.session.get("session_id"),
                "packet_manifest_sha256": _sha256_file(self.manifest_path),
                "reviewer_ref": reviewer_ref,
                "performed_by_real_human": True,
                "submitted_at_utc": submitted_at,
                "unit_count": len(self.units),
                "draft_ref": self.draft_path.name,
                "draft_sha256": draft_sha,
                "authority_boundary": self.protocol.authority_boundary,
            }
            _atomic_write_json(self.receipt_path, receipt)
            self.state.update(
                {
                    "status": "submitted-and-frozen",
                    "submitted_at_utc": submitted_at,
                    "updated_at_utc": submitted_at,
                    "revision": int(self.state["revision"]) + 1,
                }
            )
            _atomic_write_json(self.autosave_path, self.state)
            return self.public_session()


def _split_lines(value: object) -> list[str]:
    if not isinstance(value, str):
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def _choice_to_bool(value: object) -> bool | None:
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


class WorkbenchApplication:
    def __init__(self, context: ReviewContext, token: str) -> None:
        self.context = context
        self.token = token

    def index_html(self) -> bytes:
        template = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        return template.replace("__WORKBENCH_TOKEN__", self.token).encode("utf-8")

    def static_asset(self, name: str) -> tuple[bytes, str]:
        if name not in {"app.css", "app.js"}:
            raise HumanReviewWorkbenchError("unknown static asset")
        path = STATIC_ROOT / name
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return path.read_bytes(), media_type


class ReviewWorkbenchServer(ThreadingHTTPServer):
    """Threaded loopback server that owns one exclusive mutable-session lock."""

    session_lock_fd: int | None = None

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            if self.session_lock_fd is not None:
                try:
                    fcntl.flock(self.session_lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(self.session_lock_fd)
                    self.session_lock_fd = None


def _acquire_session_lock(context: ReviewContext) -> int:
    lock_path = context.session_lock_path
    try:
        descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
    except OSError as exc:
        raise HumanReviewWorkbenchError(
            "cannot create the private human-review session lock"
        ) from exc
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise HumanReviewWorkbenchError(
            "this human-review session is already open in another workbench"
        ) from exc
    return descriptor


def _host_allowed(value: str) -> bool:
    host = value.rsplit(":", 1)[0].strip("[]").lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _handler_for(application: WorkbenchApplication) -> type[BaseHTTPRequestHandler]:
    class WorkbenchHandler(BaseHTTPRequestHandler):
        server_version = "ToSReviewWorkbench/1"

        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; "
                "style-src 'self'; script-src 'self'; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )

        def _send_bytes(
            self, status: int, payload: bytes, media_type: str
        ) -> None:
            self.send_response(status)
            self._security_headers()
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(
                payload, ensure_ascii=False, allow_nan=False
            ).encode("utf-8")
            self._send_bytes(status, body, "application/json; charset=utf-8")

        def _reject(self, status: int, message: str) -> None:
            self._send_json(status, {"ok": False, "error": message})

        def _valid_host(self) -> bool:
            return _host_allowed(self.headers.get("Host", ""))

        def _query_token_valid(self, parsed: Any) -> bool:
            supplied = parse_qs(parsed.query).get("token", [""])[0]
            return secrets.compare_digest(supplied, application.token)

        def _api_token_valid(self) -> bool:
            supplied = self.headers.get("X-ToS-Review-Token", "")
            return secrets.compare_digest(supplied, application.token)

        def _origin_valid(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            parsed = urlparse(origin)
            return parsed.scheme == "http" and _host_allowed(parsed.netloc)

        def _read_payload(self) -> dict[str, Any]:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise HumanReviewWorkbenchError("invalid content length") from exc
            if length <= 0 or length > MAX_REQUEST_BYTES:
                raise HumanReviewWorkbenchError("request size is invalid")
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HumanReviewWorkbenchError("request is not valid JSON") from exc
            if not isinstance(payload, dict):
                raise HumanReviewWorkbenchError("request body must be an object")
            return payload

        def do_GET(self) -> None:  # noqa: N802
            if not self._valid_host():
                self._reject(HTTPStatus.BAD_REQUEST, "unexpected Host")
                return
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(
                    HTTPStatus.OK,
                    {"status": "ok", "exposure": "loopback-only"},
                )
                return
            if parsed.path == "/":
                if not self._query_token_valid(parsed):
                    self._reject(HTTPStatus.FORBIDDEN, "invalid review token")
                    return
                self._send_bytes(
                    HTTPStatus.OK,
                    application.index_html(),
                    "text/html; charset=utf-8",
                )
                return
            if parsed.path in {"/app.css", "/app.js"}:
                name = parsed.path.removeprefix("/")
                body, media_type = application.static_asset(name)
                self._send_bytes(HTTPStatus.OK, body, media_type)
                return
            if parsed.path == "/api/session":
                if not self._api_token_valid():
                    self._reject(HTTPStatus.FORBIDDEN, "invalid review token")
                    return
                self._send_json(HTTPStatus.OK, application.context.public_session())
                return
            if parsed.path.startswith("/api/page/"):
                if not self._query_token_valid(parsed):
                    self._reject(HTTPStatus.FORBIDDEN, "invalid review token")
                    return
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 4:
                    self._reject(HTTPStatus.NOT_FOUND, "unknown page")
                    return
                try:
                    index = int(parts[2])
                    asset = application.context.page_asset(index, parts[3])
                except (ValueError, HumanReviewWorkbenchError) as exc:
                    self._reject(HTTPStatus.NOT_FOUND, str(exc))
                    return
                self._send_bytes(HTTPStatus.OK, asset.read_bytes(), "image/png")
                return
            self._reject(HTTPStatus.NOT_FOUND, "unknown route")

        def do_POST(self) -> None:  # noqa: N802
            if not self._valid_host() or not self._origin_valid():
                self._reject(HTTPStatus.BAD_REQUEST, "invalid loopback request")
                return
            if not self._api_token_valid():
                self._reject(HTTPStatus.FORBIDDEN, "invalid review token")
                return
            parsed = urlparse(self.path)
            try:
                payload = self._read_payload()
                if parsed.path == "/api/autosave":
                    response = application.context.autosave(payload)
                elif parsed.path == "/api/feedback":
                    response = application.context.record_feedback(payload)
                elif parsed.path == "/api/submit":
                    response = application.context.submit(payload)
                else:
                    self._reject(HTTPStatus.NOT_FOUND, "unknown route")
                    return
            except HumanReviewWorkbenchError as exc:
                status = (
                    HTTPStatus.CONFLICT
                    if "revision conflict" in str(exc)
                    else HTTPStatus.UNPROCESSABLE_ENTITY
                )
                self._reject(status, str(exc))
                return
            except OSError:
                self._reject(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "human-review session storage operation failed",
                )
                return
            self._send_json(HTTPStatus.OK, response)

    return WorkbenchHandler


def create_human_review_workbench_server(
    session_dir: Path,
    *,
    port: int = 0,
    allowed_work_root: Path = DEFAULT_HUMAN_REVIEW_ROOT,
) -> tuple[ThreadingHTTPServer, str, ReviewContext]:
    if not STATIC_ROOT.is_dir():
        raise HumanReviewWorkbenchError(f"workbench assets are missing: {STATIC_ROOT}")
    context = ReviewContext(session_dir, allowed_work_root=allowed_work_root)
    token = secrets.token_urlsafe(32)
    application = WorkbenchApplication(context, token)
    lock_fd = _acquire_session_lock(context)
    try:
        server = ReviewWorkbenchServer(
            ("127.0.0.1", port), _handler_for(application)
        )
    except Exception:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
        raise
    server.session_lock_fd = lock_fd
    server.daemon_threads = True
    actual_port = int(server.server_address[1])
    url = f"http://127.0.0.1:{actual_port}/?token={token}"
    return server, url, context


def serve_human_review_workbench(
    session_dir: Path,
    *,
    port: int = 0,
    open_browser: bool = False,
    allowed_work_root: Path = DEFAULT_HUMAN_REVIEW_ROOT,
) -> None:
    server, url, context = create_human_review_workbench_server(
        session_dir, port=port, allowed_work_root=allowed_work_root
    )
    print(
        json.dumps(
            {
                "schema_version": "tos_human_review_workbench_start_v1",
                "status": context.state["status"],
                "protocol_id": context.protocol.protocol_id,
                "session_id": context.session.get("session_id"),
                "unit_count": len(context.units),
                "url": url,
                "exposure": "127.0.0.1-only",
                "autosave_ref": context.autosave_path.as_posix(),
                "draft_ref": context.draft_path.as_posix(),
                "authority_boundary": context.protocol.authority_boundary,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    if open_browser:
        webbrowser.open(url, new=2)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
