#!/usr/bin/env python3
"""Inspect and resource-gate Tree of Sophia foundation laboratory experiments."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import Draft202012Validator, FormatChecker


PART_ROOT = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(PART_ROOT) not in sys.path:
    sys.path.insert(0, str(PART_ROOT))

from native_structure import NativeStructureError, execute_native_structure
from lexical_retrieval import LexicalRetrievalError, execute_lexical_retrieval
from canonical_graph import CanonicalGraphError, execute_canonical_graph
from semantic_retrieval import SemanticRetrievalError, execute_semantic_retrieval
from granite_retrieval import GraniteRetrievalError, execute_granite_retrieval
from neo4j_graph import Neo4jGraphError, execute_neo4j_graph
from oxigraph_graph import OxigraphGraphError, execute_oxigraph_graph
from ocr_render import (
    DEFAULT_SHARED_ROOT,
    OcrRenderError,
    materialize_ocr_render,
    verify_render_manifest,
)
from human_gold_review import (
    DEFAULT_SHARED_ROOT as DEFAULT_HUMAN_GOLD_ROOT,
    MANIFEST_SCHEMA_PATH as HUMAN_GOLD_MANIFEST_SCHEMA_PATH,
    RECORD_SCHEMA_PATH as HUMAN_GOLD_RECORD_SCHEMA_PATH,
    inspect_human_gold_readiness,
    materialize_human_gold_review,
    verify_human_gold_review_manifest,
)
from ocr_candidate_review import (
    DEFAULT_HUMAN_REVIEW_ROOT as DEFAULT_CANDIDATE_REVIEW_ROOT,
    DEFAULT_SHARED_ROOT as DEFAULT_OCR_CANDIDATE_REVIEW_ROOT,
    MANIFEST_SCHEMA_PATH as OCR_CANDIDATE_REVIEW_SCHEMA_PATH,
    OcrCandidateReviewError,
    initialize_ocr_candidate_review_session,
    materialize_ocr_candidate_review,
    verify_ocr_candidate_review_manifest,
)
from human_review_workbench import (
    HumanReviewWorkbenchError,
    serve_human_review_workbench,
    synchronize_human_review_session_control,
)
from ocr_candidate_analysis import (
    OcrCandidateAnalysisError,
    analyze_frozen_ocr_candidate_review,
)
from translation_source import (
    DEFAULT_SHARED_ROOT as DEFAULT_TRANSLATION_SOURCE_ROOT,
    TranslationSourceError,
    materialize_translation_source,
    verify_translation_source_inspection,
    verify_translation_source_manifest,
)
from translation_source_review import (
    TranslationSourceReviewError,
    materialize_translation_source_review,
    verify_translation_source_review_manifest,
)
from translation_lab_readiness import (
    HUMAN_REVIEW_SCHEMA_PATH,
    READINESS_SCHEMA_PATH,
    inspect_translation_lab_readiness,
)
from runtime_manifest import RuntimeManifestError, verify_runtime_manifest
from tesseract_ocr import (
    TesseractOcrError,
    compare_tesseract_runs,
    execute_tesseract_ocr,
)
from kraken_party_ocr import (
    KrakenPartyOcrError,
    compare_kraken_party_runs,
    execute_kraken_party_ocr,
)
from paddle_ocr import (
    PaddleOcrError,
    compare_paddle_ocr_runs,
    execute_paddle_ocr,
)
from tesseract_runtime import (
    DEFAULT_RUNTIME_ROOT as DEFAULT_TESSERACT_RUNTIME_ROOT,
    TesseractRuntimeError,
    build_tesseract_runtime,
)
from kraken_party_runtime import (
    DEFAULT_RUNTIME_ROOT as DEFAULT_KRAKEN_PARTY_RUNTIME_ROOT,
    KrakenPartyRuntimeError,
    build_kraken_party_runtime,
    freeze_kraken_party_acquisition,
)
from paddle_ocr_runtime import (
    DEFAULT_RUNTIME_ROOT as DEFAULT_PADDLE_OCR_RUNTIME_ROOT,
    PaddleOcrRuntimeError,
    build_paddle_ocr_runtime,
    freeze_paddle_ocr_acquisition,
)
from structure_runtime import (
    DOC_RUNTIME_ROOT,
    PADDLE_RUNTIME_ROOT,
    StructureRuntimeError,
    build_docling_runtime,
    build_paddle_vl_runtime,
    freeze_docling_acquisition,
    freeze_paddle_vl_acquisition,
)
from paddle_vl_structure import (
    PaddleVlStructureError,
    execute_paddle_vl_structure,
)
from docling_structure import DoclingStructureError, execute_docling_structure


SUITE_PATH = PART_ROOT / "examples" / "tos-foundation-suite.v1.json"
SUITE_SCHEMA_PATH = PART_ROOT / "schemas" / "experiment-suite.schema.json"
RUN_SCHEMA_PATH = PART_ROOT / "schemas" / "run-receipt.schema.json"
REVIEW_SCHEMA_PATH = PART_ROOT / "schemas" / "manual-review-receipt.schema.json"
MODEL_INSPECTION_SCHEMA_PATH = PART_ROOT / "schemas" / "source-visible-model-inspection.schema.json"
OCR_RENDER_SCHEMA_PATH = PART_ROOT / "schemas" / "ocr-render-manifest.schema.json"
TRANSLATION_SOURCE_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "translation-source-manifest.schema.json"
)
TRANSLATION_SOURCE_INSPECTION_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "translation-source-model-inspection.schema.json"
)
TRANSLATION_SOURCE_REVIEW_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "translation-source-review-manifest.schema.json"
)
RUNTIME_MANIFEST_SCHEMA_PATH = PART_ROOT / "schemas" / "runtime-manifest.schema.json"
STRUCTURE_VLM_SELECTION_PATH = (
    PART_ROOT / "examples" / "tos-structure-vlm-selection.v1.json"
)
STRUCTURE_VLM_SELECTION_SCHEMA_PATH = (
    PART_ROOT / "schemas" / "structure-vlm-selection.schema.json"
)

RUN_ID_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
VERSION_ARGUMENTS = {
    "curl": ("--version",),
    "docling": ("--version",),
    "java": ("-version",),
    "jq": ("--version",),
    "kraken": ("--version",),
    "ocrmypdf": ("--version",),
    "party": ("--version",),
    "paddleocr": ("--version",),
    "pdfinfo": ("-v",),
    "pdftotext": ("-v",),
    "python": ("--version",),
    "sqlite3": ("--version",),
    "tesseract": ("--version",),
}


class LaboratoryError(RuntimeError):
    pass


def canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LaboratoryError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LaboratoryError(f"{path} must contain a JSON object")
    return payload


def load_suite() -> dict[str, Any]:
    return load_json(SUITE_PATH)


def schema_issues(payload: object, schema_path: Path) -> list[str]:
    schema = load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path)):
        location = "".join(f"[{part!r}]" for part in error.absolute_path) or "<root>"
        issues.append(f"{location}: {error.message}")
    return issues


def semantic_suite_issues(suite: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    experiments = suite.get("experiments")
    if not isinstance(experiments, list):
        return ["experiments must be an array"]

    seen_experiments: set[str] = set()
    for index, experiment in enumerate(experiments):
        if not isinstance(experiment, dict):
            issues.append(f"experiments[{index}] must be an object")
            continue
        experiment_id = experiment.get("experiment_id")
        location = str(experiment_id or f"experiments[{index}]")
        if not isinstance(experiment_id, str):
            continue
        if experiment_id in seen_experiments:
            issues.append(f"{location}: duplicate experiment_id")
        seen_experiments.add(experiment_id)

        variants = experiment.get("variants", [])
        labels = [variant.get("label") for variant in variants if isinstance(variant, dict)]
        if sorted(labels) != ["A", "B", "C"]:
            issues.append(f"{location}: variants must contain exactly A, B, and C")
        for variant in variants:
            if not isinstance(variant, dict):
                continue
            label = variant.get("label")
            human_required = variant.get("human_input_required")
            status = variant.get("install_status")
            if status == "human-input" and human_required is not True:
                issues.append(f"{location}/{label}: human-input status requires human_input_required=true")
            if status == "reference-only" and human_required:
                issues.append(f"{location}/{label}: reference-only cannot claim human execution")
            if variant.get("network_required") and not experiment.get("rights_gate", {}).get("network_allowed"):
                issues.append(f"{location}/{label}: network-required variant conflicts with rights gate")

        metric_ids = [metric.get("metric_id") for metric in experiment.get("metrics", []) if isinstance(metric, dict)]
        if len(metric_ids) != len(set(metric_ids)):
            issues.append(f"{location}: metric IDs must be unique")
        dimensions = {
            metric.get("dimension")
            for metric in experiment.get("metrics", [])
            if isinstance(metric, dict)
        }
        for required in ("quality", "speed", "machine-cost", "human-cost", "traceability"):
            if required not in dimensions:
                issues.append(f"{location}: metrics omit {required}")

    return issues


def validate_suite() -> list[str]:
    suite = load_suite()
    issues = schema_issues(suite, SUITE_SCHEMA_PATH)
    issues.extend(semantic_suite_issues(suite))
    selection = load_json(STRUCTURE_VLM_SELECTION_PATH)
    issues.extend(
        f"{STRUCTURE_VLM_SELECTION_PATH.relative_to(REPO_ROOT)}: {issue}"
        for issue in schema_issues(selection, STRUCTURE_VLM_SELECTION_SCHEMA_PATH)
    )
    selected_ids = [
        row.get("sample_id")
        for row in selection.get("samples", [])
        if isinstance(row, dict)
    ]
    if len(selected_ids) != len(set(selected_ids)):
        issues.append("structure VLM selection sample IDs must be unique")
    for group_id in (
        "ocr-antonovsky-2007",
        "ocr-mysl-1996",
        "ocr-naumann-1893",
    ):
        group_rows = [
            row
            for row in selection.get("samples", [])
            if isinstance(row, dict) and row.get("group_id") == group_id
        ]
        for lane in ("hard", "random"):
            lane_count = sum(row.get("lane") == lane for row in group_rows)
            if lane_count != 2:
                issues.append(
                    f"structure VLM selection requires exactly two {lane} rows for {group_id}"
                )
    seed = selection.get("selection_law", {}).get("random_seed")
    if isinstance(seed, str):
        for row in selection.get("samples", []):
            if not isinstance(row, dict) or row.get("lane") != "random":
                continue
            expected = hashlib.sha256(
                f"{seed}|{row.get('group_id')}|{row.get('sample_id')}".encode("utf-8")
            ).hexdigest()
            if row.get("selection_score") != expected:
                issues.append(
                    f"structure VLM random score drift for {row.get('sample_id')}"
                )
    for schema_path in (
        RUN_SCHEMA_PATH,
        REVIEW_SCHEMA_PATH,
        MODEL_INSPECTION_SCHEMA_PATH,
        OCR_RENDER_SCHEMA_PATH,
        HUMAN_GOLD_MANIFEST_SCHEMA_PATH,
        HUMAN_GOLD_RECORD_SCHEMA_PATH,
        OCR_CANDIDATE_REVIEW_SCHEMA_PATH,
        TRANSLATION_SOURCE_SCHEMA_PATH,
        TRANSLATION_SOURCE_INSPECTION_SCHEMA_PATH,
        TRANSLATION_SOURCE_REVIEW_SCHEMA_PATH,
        HUMAN_REVIEW_SCHEMA_PATH,
        READINESS_SCHEMA_PATH,
        RUNTIME_MANIFEST_SCHEMA_PATH,
        STRUCTURE_VLM_SELECTION_SCHEMA_PATH,
    ):
        try:
            Draft202012Validator.check_schema(load_json(schema_path))
        except Exception as exc:  # jsonschema exposes several schema error subclasses
            issues.append(f"{schema_path.relative_to(REPO_ROOT)}: invalid schema: {exc}")
    return issues


def find_experiment(suite: dict[str, Any], experiment_id: str) -> dict[str, Any]:
    for experiment in suite.get("experiments", []):
        if isinstance(experiment, dict) and experiment.get("experiment_id") == experiment_id:
            return experiment
    available = ", ".join(
        str(experiment.get("experiment_id"))
        for experiment in suite.get("experiments", [])
        if isinstance(experiment, dict)
    )
    raise LaboratoryError(f"unknown experiment {experiment_id!r}; available: {available}")


def find_variant(experiment: dict[str, Any], label: str) -> dict[str, Any]:
    for variant in experiment.get("variants", []):
        if isinstance(variant, dict) and variant.get("label") == label:
            return variant
    raise LaboratoryError(f"experiment {experiment.get('experiment_id')} has no variant {label}")


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            value = int(parts[0])
        except ValueError:
            continue
        if len(parts) > 1 and parts[1].lower() == "kb":
            value *= 1024
        values[key] = value
    return values


def _run_abyss_machine_json(
    arguments: tuple[str, ...],
    *,
    timeout: int = 45,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = shutil.which("abyss-machine")
    if command is None:
        return {
            "command_available": False,
            "returncode": None,
            "allowed": False,
            "reason": "abyss-machine command is unavailable",
            "payload": {},
        }
    try:
        completed = runner(
            (command, *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command_available": True,
            "returncode": None,
            "allowed": False,
            "reason": f"abyss-machine command failed to execute: {exc}",
            "payload": {},
        }
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    allowed_values = {payload.get("decision"), payload.get("status"), payload.get("result")}
    explicit_allowed = payload.get("allowed")
    allowed = bool(
        completed.returncode == 0
        and (
            explicit_allowed is True
            or any(value in {"allow", "allowed", "pass", "ready", "ok"} for value in allowed_values)
        )
    )
    return {
        "command_available": True,
        "returncode": completed.returncode,
        "allowed": allowed,
        "decision": payload.get("decision"),
        "status": payload.get("status"),
        "reason": payload.get("reason") or payload.get("summary") or completed.stderr.strip()[:500] or None,
        "payload": payload,
    }


def _owner_temperature_c(thermal_owner: dict[str, Any]) -> float | None:
    cooling = thermal_owner.get("cooling_status", {})
    payload = cooling.get("payload", {}) if isinstance(cooling, dict) else {}
    temperature = payload.get("temperature", {}) if isinstance(payload, dict) else {}
    summary = temperature.get("summary", {}) if isinstance(temperature, dict) else {}
    value = summary.get("temperature_c_max") if isinstance(summary, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def collect_thermal_owner(resource_gates: dict[str, Any]) -> dict[str, Any]:
    workload_class = str(resource_gates["thermal_workload_class"])
    workload_kind = str(resource_gates["thermal_workload_kind"])
    cooling = _run_abyss_machine_json(("cooling", "status", "--json"))
    resource_plan = _run_abyss_machine_json(
        (
            "resource",
            "plan",
            "--class",
            workload_class,
            "--kind",
            workload_kind,
            "--json",
        )
    )
    return {
        "owner": "abyss-machine",
        "workload_class": workload_class,
        "workload_kind": workload_kind,
        "cooling_status": cooling,
        "resource_plan": resource_plan,
        "temperature_c_max": _owner_temperature_c({"cooling_status": cooling}),
        "authority_boundary": "host thermal and resource admission; not experiment quality or promotion",
    }


def _command_version(
    command: str, path: str, environment: dict[str, str] | None = None
) -> str | None:
    arguments = VERSION_ARGUMENTS.get(command)
    if arguments is None:
        return None
    try:
        completed = subprocess.run(
            (path, *arguments),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if not combined:
        return None
    return combined.splitlines()[0][:240]


def _service_names_from_podman_records(records: object) -> list[str]:
    """Return both container identities and Compose service identities."""

    if not isinstance(records, list):
        return []
    services: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        names = record.get("Names", [])
        if isinstance(names, str):
            services.add(names)
        elif isinstance(names, list):
            services.update(name for name in names if isinstance(name, str) and name)
        labels = record.get("Labels", {})
        if not isinstance(labels, dict):
            continue
        for key in ("com.docker.compose.service", "io.podman.compose.service"):
            service = labels.get(key)
            if isinstance(service, str) and service:
                services.add(service)
    return sorted(services)


def _running_services() -> list[str]:
    podman = shutil.which("podman")
    if podman is None:
        return []
    try:
        completed = subprocess.run(
            (podman, "ps", "--format", "json"),
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    try:
        records = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    return _service_names_from_podman_records(records)


def _lspci_text() -> str:
    command = shutil.which("lspci")
    if command is None:
        return ""
    try:
        completed = subprocess.run(
            (command,), check=False, capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout


def _openvino_devices() -> list[str]:
    try:
        from openvino import Core  # type: ignore

        return sorted(str(device) for device in Core().available_devices)
    except Exception:
        return []


def collect_host_facts(
    required_commands: list[str],
    resource_gates: dict[str, Any],
    *,
    command_overrides: dict[str, str] | None = None,
    command_environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    memory = _read_meminfo()
    disk = os.statvfs("/srv")
    thermal_owner = collect_thermal_owner(resource_gates)
    commands: dict[str, dict[str, str | None]] = {}
    overrides = command_overrides or {}
    environment = os.environ.copy()
    if command_environment:
        environment.update(command_environment)
    for command in sorted(set(required_commands)):
        path = overrides.get(command) or shutil.which(command)
        commands[command] = {
            "path": path,
            "version": _command_version(command, path, environment) if path else None,
        }
    pci = _lspci_text().lower()
    vulkan = shutil.which("vulkaninfo") is not None
    openvino_devices = _openvino_devices()
    return {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "host": platform.node(),
        "os": platform.platform(),
        "kernel": platform.release(),
        "cpu_model": next(
            (
                line.partition(":")[2].strip()
                for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines()
                if line.lower().startswith("model name")
            ),
            platform.processor() or "unknown",
        ),
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": memory.get("MemTotal"),
        "memory_available_bytes": memory.get("MemAvailable"),
        "swap_total_bytes": memory.get("SwapTotal"),
        "swap_free_bytes": memory.get("SwapFree"),
        "load_1m": os.getloadavg()[0],
        "srv_total_bytes": disk.f_blocks * disk.f_frsize,
        "srv_free_bytes": disk.f_bavail * disk.f_frsize,
        "srv_used_ratio": 1.0 - (disk.f_bavail / disk.f_blocks),
        "thermal_owner": thermal_owner,
        "devices": {
            "CPU": True,
            "GPU": any(token in pci for token in ("vga compatible", "3d controller", "display controller")),
            "NPU": "processing accelerators" in pci or "neural" in pci,
            "Vulkan": vulkan,
            "openvino": openvino_devices,
        },
        "commands": commands,
        "running_services": _running_services(),
    }


def run_storage_preflight(
    target: str,
    byte_count: int,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    command = shutil.which("abyss-machine")
    if command is None:
        return {
            "command_available": False,
            "returncode": None,
            "allowed": False,
            "reason": "abyss-machine command is unavailable",
        }
    try:
        completed = runner(
            (
                command,
                "storage",
                "write-preflight",
                "--kind",
                "artifact",
                "--bytes",
                str(byte_count),
                "--target",
                target,
                "--json",
            ),
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "command_available": True,
            "returncode": None,
            "allowed": False,
            "reason": f"storage preflight failed to execute: {exc}",
        }
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    allowed_values = {
        payload.get("decision"),
        payload.get("status"),
        payload.get("result"),
    }
    explicit_allowed = payload.get("allowed")
    allowed = bool(
        completed.returncode == 0
        and (
            explicit_allowed is True
            or any(value in {"allow", "allowed", "pass", "ready", "ok"} for value in allowed_values)
        )
    )
    return {
        "command_available": True,
        "returncode": completed.returncode,
        "allowed": allowed,
        "decision": payload.get("decision"),
        "status": payload.get("status"),
        "reason": payload.get("reason") or payload.get("summary") or completed.stderr.strip()[:500] or None,
        "target": target,
        "bytes": byte_count,
    }


def evaluate_preflight(
    experiment: dict[str, Any],
    variant: dict[str, Any],
    host_facts: dict[str, Any],
    storage_preflight: dict[str, Any],
    runtime_admission: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    gates = experiment["resource_gates"]
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, observed: object, required: object, *, severity: str = "block") -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "observed": observed,
                "required": required,
                "severity": severity,
            }
        )

    free_bytes = host_facts.get("srv_free_bytes")
    check(
        "srv-free-bytes",
        isinstance(free_bytes, int) and free_bytes >= gates["minimum_srv_free_bytes"],
        free_bytes,
        f">={gates['minimum_srv_free_bytes']}",
    )
    available_memory = host_facts.get("memory_available_bytes")
    check(
        "available-memory",
        isinstance(available_memory, int) and available_memory >= gates["minimum_available_memory_bytes"],
        available_memory,
        f">={gates['minimum_available_memory_bytes']}",
    )
    load = host_facts.get("load_1m")
    check(
        "load-1m",
        isinstance(load, (int, float)) and load <= gates["maximum_load_1m"],
        load,
        f"<={gates['maximum_load_1m']}",
    )
    thermal_owner = host_facts.get("thermal_owner", {})
    if not isinstance(thermal_owner, dict):
        thermal_owner = {}
    cooling = thermal_owner.get("cooling_status", {})
    resource_plan = thermal_owner.get("resource_plan", {})
    check(
        "thermal-owner-route",
        thermal_owner.get("owner") == gates["thermal_owner"]
        and thermal_owner.get("workload_class") == gates["thermal_workload_class"]
        and thermal_owner.get("workload_kind") == gates["thermal_workload_kind"],
        {
            "owner": thermal_owner.get("owner"),
            "workload_class": thermal_owner.get("workload_class"),
            "workload_kind": thermal_owner.get("workload_kind"),
        },
        {
            "owner": gates["thermal_owner"],
            "workload_class": gates["thermal_workload_class"],
            "workload_kind": gates["thermal_workload_kind"],
        },
    )
    cooling_available = bool(
        isinstance(cooling, dict)
        and cooling.get("command_available")
        and cooling.get("returncode") == 0
    )
    temperature = thermal_owner.get("temperature_c_max")
    if temperature is None:
        check(
            "thermal-owner-telemetry",
            not gates["temperature_telemetry_required"],
            None,
            "fresh abyss-machine cooling status",
            severity="block" if gates["temperature_telemetry_required"] else "warn",
        )
    else:
        check(
            "thermal-owner-telemetry",
            cooling_available,
            temperature,
            "fresh abyss-machine cooling status",
        )
        payload = cooling.get("payload", {}) if isinstance(cooling, dict) else {}
        owner_temperature = payload.get("temperature", {}) if isinstance(payload, dict) else {}
        episode = owner_temperature.get("episode", {}) if isinstance(owner_temperature, dict) else {}
        thresholds = episode.get("thresholds", {}) if isinstance(episode, dict) else {}
        watch_c = thresholds.get("watch_c") if isinstance(thresholds, dict) else None
        critical_c = thresholds.get("critical_c") if isinstance(thresholds, dict) else None
        if isinstance(watch_c, (int, float)):
            check(
                "thermal-watch-band",
                float(temperature) <= float(watch_c),
                {"temperature_c": temperature, "episode": episode.get("band")},
                f"<={watch_c}C or owner-routed observation",
                severity="warn",
            )
        if isinstance(critical_c, (int, float)):
            check(
                "thermal-critical-band",
                float(temperature) < float(critical_c),
                temperature,
                f"<{critical_c}C",
            )
    check(
        "thermal-owner-admission",
        bool(isinstance(resource_plan, dict) and resource_plan.get("allowed") is True),
        {
            "command_available": resource_plan.get("command_available")
            if isinstance(resource_plan, dict)
            else False,
            "returncode": resource_plan.get("returncode")
            if isinstance(resource_plan, dict)
            else None,
            "allowed": resource_plan.get("allowed") if isinstance(resource_plan, dict) else False,
            "decision": resource_plan.get("decision") if isinstance(resource_plan, dict) else None,
            "reason": resource_plan.get("reason") if isinstance(resource_plan, dict) else None,
        },
        (
            "abyss-machine resource plan allow for "
            f"{gates['thermal_workload_class']}/{gates['thermal_workload_kind']}"
        ),
    )

    commands = host_facts.get("commands", {})
    for command in variant["required_commands"]:
        available = bool(isinstance(commands, dict) and commands.get(command, {}).get("path"))
        check(f"command:{command}", available, commands.get(command) if isinstance(commands, dict) else None, "available")
    services = set(host_facts.get("running_services", []))
    for service in variant["required_services"]:
        check(f"service:{service}", service in services, service in services, "running")
    devices = host_facts.get("devices", {})
    for device in variant["required_devices"]:
        if device == "none":
            continue
        available = False
        if isinstance(devices, dict):
            if device in {"CPU", "GPU", "NPU", "Vulkan"}:
                available = bool(devices.get(device))
        check(f"device:{device}", available, available, "available")

    license_ok = variant["license_status"] in {"verified-for-bounded-research", "not-applicable"}
    check("license", license_ok, variant["license_status"], "verified or not-applicable")
    install_status = variant["install_status"]
    runtime_verified = bool(runtime_admission and runtime_admission.get("verified") is True)
    if install_status == "requires-setup":
        check(
            "runtime-admission",
            runtime_verified,
            runtime_admission or {"verified": False, "reason": "no runtime manifest supplied"},
            "verified exact isolated runtime manifest",
        )
    check(
        "candidate-installation",
        install_status not in {"requires-setup", "reference-only"}
        or (install_status == "requires-setup" and runtime_verified),
        {"install_status": install_status, "runtime_verified": runtime_verified},
        "available, human-input, or verified isolated runtime",
    )
    check(
        "network-rights",
        not variant["network_required"] or experiment["rights_gate"]["network_allowed"],
        variant["network_required"],
        experiment["rights_gate"]["network_allowed"],
    )
    check(
        "storage-owner-preflight",
        storage_preflight.get("allowed") is True,
        storage_preflight,
        "abyss-machine allow",
    )

    blocking_failures = [item for item in checks if not item["passed"] and item["severity"] == "block"]
    if blocking_failures:
        return "blocked", checks
    if variant["human_input_required"]:
        return "awaiting-human-input", checks
    return "ready", checks


def build_preflight_receipt(
    suite: dict[str, Any],
    experiment: dict[str, Any],
    variant: dict[str, Any],
    *,
    host_facts: dict[str, Any] | None = None,
    storage_preflight: dict[str, Any] | None = None,
    runtime_manifest_path: Path | None = None,
    runtime_admission: dict[str, Any] | None = None,
) -> dict[str, Any]:
    admission = runtime_admission
    if admission is None and runtime_manifest_path is not None:
        try:
            runtime = verify_runtime_manifest(
                runtime_manifest_path,
                experiment_id=str(experiment["experiment_id"]),
                variant=str(variant["label"]),
                required_commands=list(variant["required_commands"]),
            )
        except RuntimeManifestError as exc:
            admission = {
                "verified": False,
                "manifest_ref": runtime_manifest_path.resolve().as_posix(),
                "reason": str(exc),
            }
        else:
            admission = {
                "verified": True,
                "manifest_ref": runtime_manifest_path.resolve().as_posix(),
                "manifest_sha256": sha256_file(runtime_manifest_path.resolve()),
                "runtime_id": runtime["runtime_id"],
                "runtime_root": runtime["runtime_root"],
                "artifact_set_sha256": runtime["artifact_set_sha256"],
                "commands": runtime["commands"],
                "environment": runtime["environment"],
                "authority_boundary": "runtime readiness only; no contestant quality verdict",
            }
    overrides = admission.get("commands", {}) if admission and admission.get("verified") else {}
    command_environment = (
        admission.get("environment", {}) if admission and admission.get("verified") else {}
    )
    facts = host_facts or collect_host_facts(
        list(variant["required_commands"]),
        experiment["resource_gates"],
        command_overrides=overrides if isinstance(overrides, dict) else {},
        command_environment=command_environment if isinstance(command_environment, dict) else {},
    )
    expected_bytes = int(variant["expected_download_bytes"]) + int(variant["estimated_output_bytes"])
    storage = storage_preflight or run_storage_preflight(
        suite["artifact_roots"]["durable"], expected_bytes
    )
    decision, checks = evaluate_preflight(experiment, variant, facts, storage, admission)
    return {
        "schema_version": "tos_foundation_lab_preflight_v1",
        "suite_id": suite["suite_id"],
        "suite_sha256": sha256_json(suite),
        "experiment_id": experiment["experiment_id"],
        "experiment_sha256": sha256_json(experiment),
        "variant": variant["label"],
        "captured_at_utc": facts["captured_at_utc"],
        "decision": decision,
        "host_facts": facts,
        "runtime_admission": admission,
        "storage_preflight": storage,
        "checks": checks,
        "authority_boundary": "execution readiness only; no content-quality, rights-clearance, or promotion verdict",
    }


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_run(
    suite: dict[str, Any],
    experiment: dict[str, Any],
    variant: dict[str, Any],
    preflight: dict[str, Any],
    run_id: str,
    output_root: Path,
) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise LaboratoryError("run-id must use lowercase letters, digits, dot, underscore, and hyphen")
    if preflight.get("experiment_id") != experiment["experiment_id"] or preflight.get("variant") != variant["label"]:
        raise LaboratoryError("preflight experiment/variant does not match requested run")
    if preflight.get("experiment_sha256") != sha256_json(experiment):
        raise LaboratoryError("preflight was captured for a different experiment revision")
    if preflight.get("decision") not in {"ready", "awaiting-human-input"}:
        raise LaboratoryError("blocked preflight cannot materialize a run")

    durable_root = Path(suite["artifact_roots"]["durable"])
    if not _within(output_root, durable_root):
        raise LaboratoryError(f"output root must stay under {durable_root}")
    run_root = output_root / experiment["experiment_id"] / run_id / f"variant-{variant['label']}"
    if run_root.exists():
        raise LaboratoryError(f"run path already exists: {run_root}")

    for relative in (
        "inputs",
        "raw-output",
        "metrics",
        "manual-review",
        "receipts",
    ):
        (run_root / relative).mkdir(parents=True, exist_ok=False)
    write_json(run_root / "experiment.spec.json", experiment)
    write_json(run_root / "receipts" / "preflight.json", preflight)
    (run_root / "manual-review" / "error-ledger.jsonl").write_text("", encoding="utf-8")
    (run_root / "manual-review" / "README.md").write_text(
        "# Manual review\n\nUse the committed MANUAL_REVIEW_PROTOCOL.md and preserve source-visible, blind-labeled receipts here.\n",
        encoding="utf-8",
    )
    status = "awaiting-human-input" if variant["human_input_required"] else "prepared"
    run_receipt = {
        "schema_version": "tos_foundation_lab_run_receipt_v1",
        "run_id": run_id,
        "experiment_id": experiment["experiment_id"],
        "variant": variant["label"],
        "experiment_spec_sha256": sha256_json(experiment),
        "status": status,
        "started_at_utc": None,
        "finished_at_utc": None,
        "preflight_ref": "receipts/preflight.json",
        "source_refs": experiment["source_refs"],
        "sample_ids": [],
        "method_revision": {
            "implementation": variant["implementation"],
            "version": "unresolved-before-execution",
            "runtime": variant["runtime"],
            "model": variant["model"],
            "artifact_digest": None,
        },
        "invocation_ref": None,
        "artifact_refs": [],
        "metric_refs": [],
        "manual_review_refs": [],
        "model_inspection_refs": [],
        "errors": [],
        "retention_decision": "pending",
        "authority_boundary": "runtime evidence only; no source, translation, semantic, rights, or canon promotion without Tree of Sophia human review",
    }
    issues = schema_issues(run_receipt, RUN_SCHEMA_PATH)
    if issues:
        raise LaboratoryError("generated run receipt is invalid: " + "; ".join(issues))
    write_json(run_root / "run.receipt.json", run_receipt)
    return run_root


def verify_run(run_root: Path) -> list[str]:
    issues: list[str] = []
    for relative in (
        "experiment.spec.json",
        "run.receipt.json",
        "receipts/preflight.json",
        "manual-review/error-ledger.jsonl",
    ):
        if not (run_root / relative).is_file():
            issues.append(f"missing {relative}")
    if issues:
        return issues
    receipt = load_json(run_root / "run.receipt.json")
    issues.extend(schema_issues(receipt, RUN_SCHEMA_PATH))
    experiment = load_json(run_root / "experiment.spec.json")
    if receipt.get("experiment_spec_sha256") != sha256_json(experiment):
        issues.append("run receipt experiment_spec_sha256 does not match experiment.spec.json")
    for ref in (
        receipt.get("artifact_refs", [])
        + receipt.get("metric_refs", [])
        + receipt.get("manual_review_refs", [])
        + receipt.get("model_inspection_refs", [])
    ):
        if isinstance(ref, str) and not (run_root / ref).is_file():
            issues.append(f"receipt reference is missing: {ref}")
    for ref in receipt.get("manual_review_refs", []):
        if isinstance(ref, str) and (run_root / ref).is_file():
            review = load_json(run_root / ref)
            issues.extend(f"{ref}: {issue}" for issue in schema_issues(review, REVIEW_SCHEMA_PATH))
    for ref in receipt.get("model_inspection_refs", []):
        if isinstance(ref, str) and (run_root / ref).is_file():
            inspection = load_json(run_root / ref)
            issues.extend(
                f"{ref}: {issue}"
                for issue in schema_issues(inspection, MODEL_INSPECTION_SCHEMA_PATH)
            )
    promoted_status = receipt.get("status") in {"completed", "completed-with-warnings"}
    if promoted_status and not receipt.get("manual_review_refs"):
        issues.append("completed run has no manual_review_refs")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate", help="validate schemas and the frozen experiment suite")

    inspect_parser = subparsers.add_parser("inspect", help="print one frozen experiment")
    inspect_parser.add_argument("--experiment", required=True)

    preflight_parser = subparsers.add_parser("preflight", help="capture current execution readiness")
    preflight_parser.add_argument("--experiment", required=True)
    preflight_parser.add_argument("--variant", choices=("A", "B", "C"), required=True)
    preflight_parser.add_argument("--output", type=Path)
    preflight_parser.add_argument("--runtime-manifest", type=Path)

    prepare_parser = subparsers.add_parser("prepare", help="materialize an isolated run packet after preflight")
    prepare_parser.add_argument("--experiment", required=True)
    prepare_parser.add_argument("--variant", choices=("A", "B", "C"), required=True)
    prepare_parser.add_argument("--preflight", type=Path, required=True)
    prepare_parser.add_argument("--run-id", required=True)
    prepare_parser.add_argument("--output-root", type=Path)

    verify_parser = subparsers.add_parser("verify-run", help="validate a materialized run packet")
    verify_parser.add_argument("run_root", type=Path)

    render_parser = subparsers.add_parser(
        "materialize-ocr-render",
        help="render and freeze the shared OCR A/B/C visual packet",
    )
    render_parser.add_argument("--tree-repo-root", type=Path, required=True)
    render_parser.add_argument("--sample-plan", type=Path, required=True)
    render_parser.add_argument("--render-id", required=True)
    render_parser.add_argument("--shared-root", type=Path, default=DEFAULT_SHARED_ROOT)
    render_parser.add_argument("--pdftoppm", type=Path, default=Path("/usr/bin/pdftoppm"))
    render_parser.add_argument("--tree-local-manifest", type=Path)

    verify_render_parser = subparsers.add_parser(
        "verify-ocr-render",
        help="verify schema, PNG headers, and fixity of a frozen OCR render packet",
    )
    verify_render_parser.add_argument("manifest", type=Path)

    human_gold_parser = subparsers.add_parser(
        "materialize-human-gold-review",
        help="render blind page triplets and blank interfaces for the 15-page human gold set",
    )
    human_gold_parser.add_argument("--tree-repo-root", type=Path, required=True)
    human_gold_parser.add_argument("--gold-status", type=Path, required=True)
    human_gold_parser.add_argument("--visual-plan", type=Path, required=True)
    human_gold_parser.add_argument("--render-manifest", type=Path, required=True)
    human_gold_parser.add_argument("--packet-id", required=True)
    human_gold_parser.add_argument(
        "--shared-root", type=Path, default=DEFAULT_HUMAN_GOLD_ROOT
    )
    human_gold_parser.add_argument(
        "--pdftoppm", type=Path, default=Path("/usr/bin/pdftoppm")
    )
    human_gold_parser.add_argument(
        "--pdfinfo", type=Path, default=Path("/usr/bin/pdfinfo")
    )

    verify_human_gold_parser = subparsers.add_parser(
        "verify-human-gold-review",
        help="verify the 15-page blind review packet and its blank human stop line",
    )
    verify_human_gold_parser.add_argument("manifest", type=Path)

    gate_human_gold_parser = subparsers.add_parser(
        "gate-human-gold-review",
        help="keep OCR and structure quality claims blocked until 15 pages have two human passes",
    )
    gate_human_gold_parser.add_argument("--manifest", type=Path, required=True)
    gate_human_gold_parser.add_argument("--human-review-output", type=Path)

    ocr_candidate_review_parser = subparsers.add_parser(
        "materialize-ocr-candidate-review",
        help=(
            "freeze method-blind visible OCR candidates beside verified source "
            "triplets"
        ),
    )
    ocr_candidate_review_parser.add_argument(
        "--human-gold-manifest", type=Path, required=True
    )
    ocr_candidate_review_parser.add_argument(
        "--candidate-run",
        type=Path,
        action="append",
        required=True,
        help="repeat once for each frozen OCR run",
    )
    ocr_candidate_review_parser.add_argument(
        "--language",
        action="append",
        help="repeat to select source languages; defaults to ru",
    )
    ocr_candidate_review_parser.add_argument("--packet-id", required=True)
    ocr_candidate_review_parser.add_argument(
        "--shared-root",
        type=Path,
        default=DEFAULT_OCR_CANDIDATE_REVIEW_ROOT,
    )

    verify_ocr_candidate_review_parser = subparsers.add_parser(
        "verify-ocr-candidate-review",
        help="verify candidate bytes, source pages, blindness map, and stop line",
    )
    verify_ocr_candidate_review_parser.add_argument("manifest", type=Path)

    initialize_ocr_candidate_session_parser = subparsers.add_parser(
        "initialize-ocr-candidate-review-session",
        help="create a private mutable Workbench session for a verified packet",
    )
    initialize_ocr_candidate_session_parser.add_argument(
        "--manifest", type=Path, required=True
    )
    initialize_ocr_candidate_session_parser.add_argument(
        "--session-id", required=True
    )
    initialize_ocr_candidate_session_parser.add_argument(
        "--review-root",
        type=Path,
        default=DEFAULT_CANDIDATE_REVIEW_ROOT,
    )

    human_review_workbench_parser = subparsers.add_parser(
        "human-review-workbench",
        help="open one verified private pass-1 session in the loopback human workbench",
    )
    human_review_workbench_parser.add_argument(
        "--session-dir", type=Path, required=True
    )
    human_review_workbench_parser.add_argument(
        "--port", type=int, default=0, help="loopback port; 0 selects a free port"
    )
    human_review_workbench_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="ask the desktop to open the tokenized loopback URL",
    )
    synchronize_review_control_parser = subparsers.add_parser(
        "sync-human-review-session-control",
        help="repair mutable review-session status from validated review artifacts",
    )
    synchronize_review_control_parser.add_argument(
        "--session-dir", type=Path, required=True
    )
    analyze_ocr_candidate_review_parser = subparsers.add_parser(
        "analyze-ocr-candidate-review",
        help=(
            "join one frozen candidate pass to its restricted A/B/C map in a "
            "private post-reveal report"
        ),
    )
    analyze_ocr_candidate_review_parser.add_argument(
        "--session-dir", type=Path, required=True
    )

    translation_source_parser = subparsers.add_parser(
        "materialize-translation-source",
        help="freeze the German source-review packet before any translation lane",
    )
    translation_source_parser.add_argument("--tree-repo-root", type=Path, required=True)
    translation_source_parser.add_argument("--sample-plan", type=Path, required=True)
    translation_source_parser.add_argument("--anchors", type=Path, required=True)
    translation_source_parser.add_argument("--packet-id", required=True)
    translation_source_parser.add_argument("--visual-item-ref", required=True)
    translation_source_parser.add_argument("--visual-file-ref", required=True)
    translation_source_parser.add_argument("--visual-file-sha256", required=True)
    translation_source_parser.add_argument(
        "--shared-root", type=Path, default=DEFAULT_TRANSLATION_SOURCE_ROOT
    )
    translation_source_parser.add_argument(
        "--pdfinfo", type=Path, default=Path("/usr/bin/pdfinfo")
    )

    verify_translation_source_parser = subparsers.add_parser(
        "verify-translation-source",
        help="verify the source packet without accepting its automated German text",
    )
    verify_translation_source_parser.add_argument("manifest", type=Path)

    verify_translation_inspection_parser = subparsers.add_parser(
        "verify-translation-source-inspection",
        help="verify an advisory exhaustive selector inspection against its source packet",
    )
    verify_translation_inspection_parser.add_argument("inspection", type=Path)
    verify_translation_inspection_parser.add_argument("--manifest", type=Path, required=True)

    translation_review_parser = subparsers.add_parser(
        "materialize-translation-source-review",
        help="render blind page triplets and blank interfaces for real human source review",
    )
    translation_review_parser.add_argument("--tree-repo-root", type=Path, required=True)
    translation_review_parser.add_argument("--review-plan", type=Path, required=True)
    translation_review_parser.add_argument("--packet-id", required=True)
    translation_review_parser.add_argument(
        "--shared-root", type=Path, default=DEFAULT_TRANSLATION_SOURCE_ROOT
    )
    translation_review_parser.add_argument(
        "--pdftoppm", type=Path, default=Path("/usr/bin/pdftoppm")
    )
    translation_review_parser.add_argument(
        "--pdfinfo", type=Path, default=Path("/usr/bin/pdfinfo")
    )

    verify_translation_review_parser = subparsers.add_parser(
        "verify-translation-source-review",
        help="verify page renders, blank interfaces, and the human-review stop line",
    )
    verify_translation_review_parser.add_argument("manifest", type=Path)

    translation_readiness_parser = subparsers.add_parser(
        "gate-translation-lab",
        help="verify source-review evidence and keep draft lanes blocked until independent pre-draft evidence",
    )
    translation_readiness_parser.add_argument("--tree-repo-root", type=Path, required=True)
    translation_readiness_parser.add_argument("--laboratory-plan", type=Path, required=True)
    translation_readiness_parser.add_argument("--reference-register", type=Path, required=True)
    translation_readiness_parser.add_argument(
        "--source-review-manifest", type=Path, required=True
    )
    translation_readiness_parser.add_argument("--human-review-output", type=Path)

    runtime_parser = subparsers.add_parser(
        "materialize-tesseract-runtime",
        help="build OCR A's exact isolated runtime from an already cached five-RPM lock",
    )
    runtime_parser.add_argument("--rpm-cache", type=Path, required=True)
    runtime_parser.add_argument(
        "--runtime-root", type=Path, default=DEFAULT_TESSERACT_RUNTIME_ROOT
    )
    runtime_parser.add_argument("--owner-receipt", type=Path, action="append", default=[])

    freeze_party_parser = subparsers.add_parser(
        "freeze-kraken-party-acquisition",
        help="verify OCR B's cached source/model/wheels and emit the complete hash lock",
    )
    freeze_party_parser.add_argument("--wheel-cache", type=Path, required=True)
    freeze_party_parser.add_argument("--party-source", type=Path, required=True)
    freeze_party_parser.add_argument("--model", type=Path, required=True)
    freeze_party_parser.add_argument("--zenodo-record", type=Path, required=True)
    freeze_party_parser.add_argument("--output", type=Path, required=True)
    freeze_party_parser.add_argument("--owner-receipt", type=Path, action="append", default=[])

    party_runtime_parser = subparsers.add_parser(
        "materialize-kraken-party-runtime",
        help="build OCR B's exact offline Python 3.12 runtime from a frozen acquisition",
    )
    party_runtime_parser.add_argument("--acquisition-receipt", type=Path, required=True)
    party_runtime_parser.add_argument(
        "--runtime-root", type=Path, default=DEFAULT_KRAKEN_PARTY_RUNTIME_ROOT
    )
    party_runtime_parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3.12"))
    party_runtime_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    freeze_paddle_parser = subparsers.add_parser(
        "freeze-paddle-ocr-acquisition",
        help="verify OCR C's cached wheels/models and emit the complete hash lock",
    )
    freeze_paddle_parser.add_argument("--wheel-cache", type=Path, required=True)
    freeze_paddle_parser.add_argument("--model-cache", type=Path, required=True)
    freeze_paddle_parser.add_argument("--output", type=Path, required=True)
    freeze_paddle_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    paddle_runtime_parser = subparsers.add_parser(
        "materialize-paddle-ocr-runtime",
        help="build OCR C's exact offline Python 3.12 runtime from a frozen acquisition",
    )
    paddle_runtime_parser.add_argument("--acquisition-receipt", type=Path, required=True)
    paddle_runtime_parser.add_argument(
        "--runtime-root", type=Path, default=DEFAULT_PADDLE_OCR_RUNTIME_ROOT
    )
    paddle_runtime_parser.add_argument("--python", type=Path, default=Path("/usr/bin/python3.12"))
    paddle_runtime_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    freeze_docling_structure_parser = subparsers.add_parser(
        "freeze-docling-structure-acquisition",
        help="verify Structure B's cached wheel/model closure and emit its exact lock",
    )
    freeze_docling_structure_parser.add_argument("--wheel-cache", type=Path, required=True)
    freeze_docling_structure_parser.add_argument("--model-dir", type=Path, required=True)
    freeze_docling_structure_parser.add_argument("--output", type=Path, required=True)
    freeze_docling_structure_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    docling_structure_runtime_parser = subparsers.add_parser(
        "materialize-docling-structure-runtime",
        help="build Structure B's exact offline Docling/Heron/Tesseract runtime",
    )
    docling_structure_runtime_parser.add_argument(
        "--acquisition-receipt", type=Path, required=True
    )
    docling_structure_runtime_parser.add_argument(
        "--runtime-root", type=Path, default=DOC_RUNTIME_ROOT
    )
    docling_structure_runtime_parser.add_argument(
        "--python", type=Path, default=Path("/usr/bin/python3.12")
    )
    docling_structure_runtime_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    freeze_paddle_structure_parser = subparsers.add_parser(
        "freeze-paddle-vl-structure-acquisition",
        help="verify Structure C's OCR-extra wheels, base runtime, and pinned models",
    )
    freeze_paddle_structure_parser.add_argument("--wheel-cache", type=Path, required=True)
    freeze_paddle_structure_parser.add_argument("--vl-model-dir", type=Path, required=True)
    freeze_paddle_structure_parser.add_argument(
        "--layout-model-dir", type=Path, required=True
    )
    freeze_paddle_structure_parser.add_argument("--output", type=Path, required=True)
    freeze_paddle_structure_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    paddle_structure_runtime_parser = subparsers.add_parser(
        "materialize-paddle-vl-structure-runtime",
        help="build Structure C's exact CPU runtime from the verified OCR base and VLM models",
    )
    paddle_structure_runtime_parser.add_argument(
        "--acquisition-receipt", type=Path, required=True
    )
    paddle_structure_runtime_parser.add_argument(
        "--runtime-root", type=Path, default=PADDLE_RUNTIME_ROOT
    )
    paddle_structure_runtime_parser.add_argument(
        "--owner-receipt", type=Path, action="append", default=[]
    )

    tesseract_parser = subparsers.add_parser(
        "execute-tesseract-ocr",
        help="execute prepared OCR A over the shared frozen visual packet",
    )
    tesseract_parser.add_argument("run_root", type=Path)
    tesseract_parser.add_argument("--sample-plan", type=Path, required=True)
    tesseract_parser.add_argument("--render-manifest", type=Path, required=True)
    tesseract_parser.add_argument("--runtime-manifest", type=Path, required=True)

    compare_tesseract_parser = subparsers.add_parser(
        "compare-tesseract-ocr",
        help="compare two OCR A runs for mechanically identical output bytes",
    )
    compare_tesseract_parser.add_argument("first_run_root", type=Path)
    compare_tesseract_parser.add_argument("second_run_root", type=Path)

    kraken_party_parser = subparsers.add_parser(
        "execute-kraken-party-ocr",
        help="execute prepared OCR B over the shared frozen visual packet",
    )
    kraken_party_parser.add_argument("run_root", type=Path)
    kraken_party_parser.add_argument("--sample-plan", type=Path, required=True)
    kraken_party_parser.add_argument("--render-manifest", type=Path, required=True)
    kraken_party_parser.add_argument("--runtime-manifest", type=Path, required=True)

    compare_kraken_party_parser = subparsers.add_parser(
        "compare-kraken-party-ocr",
        help="compare two OCR B runs with canonical and raw-byte identities separated",
    )
    compare_kraken_party_parser.add_argument("first_run_root", type=Path)
    compare_kraken_party_parser.add_argument("second_run_root", type=Path)

    paddle_ocr_parser = subparsers.add_parser(
        "execute-paddle-ocr",
        help="execute prepared OCR C over the shared frozen visual packet",
    )
    paddle_ocr_parser.add_argument("run_root", type=Path)
    paddle_ocr_parser.add_argument("--sample-plan", type=Path, required=True)
    paddle_ocr_parser.add_argument("--render-manifest", type=Path, required=True)
    paddle_ocr_parser.add_argument("--runtime-manifest", type=Path, required=True)
    paddle_ocr_parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="execute only this frozen render sample; repeat for a bounded subset",
    )

    compare_paddle_ocr_parser = subparsers.add_parser(
        "compare-paddle-ocr",
        help="compare two OCR C runs with semantic and raw-byte identities separated",
    )
    compare_paddle_ocr_parser.add_argument("first_run_root", type=Path)
    compare_paddle_ocr_parser.add_argument("second_run_root", type=Path)

    structure_parser = subparsers.add_parser(
        "execute-native-structure",
        help="execute prepared Structure A over the frozen ToS sample",
    )
    structure_parser.add_argument("run_root", type=Path)
    structure_parser.add_argument("--tree-repo-root", type=Path, required=True)
    structure_parser.add_argument("--sample-plan", type=Path, required=True)

    docling_structure_parser = subparsers.add_parser(
        "execute-docling-structure",
        help="execute prepared Structure B through the exact offline Docling runtime",
    )
    docling_structure_parser.add_argument("run_root", type=Path)
    docling_structure_parser.add_argument("--tree-repo-root", type=Path, required=True)
    docling_structure_parser.add_argument("--sample-plan", type=Path, required=True)
    docling_structure_parser.add_argument("--runtime-manifest", type=Path, required=True)
    docling_structure_parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="execute only this already frozen sample as a diagnostic; repeat if needed",
    )

    paddle_vl_structure_parser = subparsers.add_parser(
        "execute-paddle-vl-structure",
        help="execute prepared Structure C over the output-blind frozen visual selection",
    )
    paddle_vl_structure_parser.add_argument("run_root", type=Path)
    paddle_vl_structure_parser.add_argument("--visual-plan", type=Path, required=True)
    paddle_vl_structure_parser.add_argument("--render-manifest", type=Path, required=True)
    paddle_vl_structure_parser.add_argument("--selection", type=Path, required=True)
    paddle_vl_structure_parser.add_argument("--runtime-manifest", type=Path, required=True)
    paddle_vl_structure_parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="execute only this already frozen sample as a diagnostic; repeat if needed",
    )

    retrieval_parser = subparsers.add_parser(
        "execute-lexical-retrieval",
        help="execute prepared Retrieval A over one preserved structure run",
    )
    retrieval_parser.add_argument("run_root", type=Path)
    retrieval_parser.add_argument("--structure-run-root", type=Path, required=True)
    retrieval_parser.add_argument("--query-plan", type=Path, required=True)
    retrieval_parser.add_argument("--query-content", type=Path, required=True)

    semantic_retrieval_parser = subparsers.add_parser(
        "execute-semantic-retrieval",
        help="execute prepared Retrieval B through resident OVMS/Qdrant/Qwen3 services",
    )
    semantic_retrieval_parser.add_argument("run_root", type=Path)
    semantic_retrieval_parser.add_argument("--structure-run-root", type=Path, required=True)
    semantic_retrieval_parser.add_argument("--query-plan", type=Path, required=True)
    semantic_retrieval_parser.add_argument("--query-content", type=Path, required=True)
    semantic_retrieval_parser.add_argument("--collection", required=True)

    granite_retrieval_parser = subparsers.add_parser(
        "execute-granite-retrieval",
        help="execute prepared Retrieval C through the pinned Granite R2 OpenVINO runtime",
    )
    granite_retrieval_parser.add_argument("run_root", type=Path)
    granite_retrieval_parser.add_argument("--structure-run-root", type=Path, required=True)
    granite_retrieval_parser.add_argument("--query-plan", type=Path, required=True)
    granite_retrieval_parser.add_argument("--query-content", type=Path, required=True)
    granite_retrieval_parser.add_argument("--runtime-python", type=Path, required=True)
    granite_retrieval_parser.add_argument("--runtime-manifest", type=Path, required=True)
    granite_retrieval_parser.add_argument("--model-snapshot", type=Path, required=True)

    graph_parser = subparsers.add_parser(
        "execute-canonical-graph",
        help="execute prepared Graph A over one frozen ToS claim and query set",
    )
    graph_parser.add_argument("run_root", type=Path)
    graph_parser.add_argument("--tree-repo-root", type=Path, required=True)
    graph_parser.add_argument("--claim-set", type=Path, required=True)
    graph_parser.add_argument("--query-plan", type=Path, required=True)

    neo4j_graph_parser = subparsers.add_parser(
        "execute-neo4j-graph",
        help="execute prepared Graph B in an isolated resident Neo4j namespace",
    )
    neo4j_graph_parser.add_argument("run_root", type=Path)
    neo4j_graph_parser.add_argument("--tree-repo-root", type=Path, required=True)
    neo4j_graph_parser.add_argument("--claim-set", type=Path, required=True)
    neo4j_graph_parser.add_argument("--query-plan", type=Path, required=True)
    neo4j_graph_parser.add_argument("--lab-run", required=True)

    oxigraph_graph_parser = subparsers.add_parser(
        "execute-oxigraph-graph",
        help="execute prepared Graph C in an isolated run-local Oxigraph store",
    )
    oxigraph_graph_parser.add_argument("run_root", type=Path)
    oxigraph_graph_parser.add_argument("--tree-repo-root", type=Path, required=True)
    oxigraph_graph_parser.add_argument("--claim-set", type=Path, required=True)
    oxigraph_graph_parser.add_argument("--query-plan", type=Path, required=True)
    oxigraph_graph_parser.add_argument("--runtime-python", type=Path, required=True)
    oxigraph_graph_parser.add_argument("--runtime-manifest", type=Path, required=True)
    oxigraph_graph_parser.add_argument("--lab-run", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            issues = validate_suite()
            if issues:
                for issue in issues:
                    print(f"[error] {issue}", file=sys.stderr)
                return 1
            print("[ok] validated Tree of Sophia foundation laboratory suite and schemas")
            print("[boundary] schema validity is not source, translation, semantic, rights, or review truth")
            return 0

        if args.command == "materialize-ocr-render":
            manifest = materialize_ocr_render(
                args.tree_repo_root,
                args.sample_plan,
                args.render_id,
                shared_root=args.shared_root,
                pdftoppm=args.pdftoppm,
                tree_local_manifest=args.tree_local_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] frozen pixels are not OCR or source-text truth")
            return 0

        if args.command == "verify-ocr-render":
            manifest = verify_render_manifest(args.manifest)
            print(
                f"[ok] verified {manifest['sample_count']} frozen OCR pages "
                f"({manifest['render_set_sha256']})"
            )
            print("[boundary] render fixity is not OCR quality")
            return 0

        if args.command == "materialize-human-gold-review":
            manifest = materialize_human_gold_review(
                args.tree_repo_root,
                args.gold_status,
                args.visual_plan,
                args.render_manifest,
                args.packet_id,
                shared_root=args.shared_root,
                pdftoppm=args.pdftoppm,
                pdfinfo=args.pdfinfo,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print(
                "[boundary] source triplets and blank forms are not human "
                "transcription, OCR quality, structure quality, or gold"
            )
            return 0

        if args.command == "verify-human-gold-review":
            manifest = verify_human_gold_review_manifest(args.manifest)
            print(
                f"[ok] verified {len(manifest['units'])} blind gold candidates and "
                f"{manifest['context_render']['unique_page_count']} context pages"
            )
            print(
                "[boundary] packet fixity is not human review or content correctness"
            )
            return 0

        if args.command == "gate-human-gold-review":
            readiness = inspect_human_gold_readiness(
                args.manifest, args.human_review_output
            )
            print(json.dumps(readiness, ensure_ascii=False, indent=2))
            print(
                "[boundary] readiness verifies declared evidence shape only; it "
                "cannot inspect or attest transcription correctness"
            )
            return 0 if readiness["decision"] == (
                "ready-for-manual-metric-adjudication"
            ) else 2

        if args.command == "materialize-ocr-candidate-review":
            manifest = materialize_ocr_candidate_review(
                args.human_gold_manifest,
                args.candidate_run,
                args.packet_id,
                languages=tuple(args.language or ("ru",)),
                shared_root=args.shared_root,
                invocation=[
                    sys.argv[0],
                    *(argv if argv is not None else sys.argv[1:]),
                ],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print(
                "[boundary] visible candidates and packet fixity are not source "
                "truth, gold, acceptance, or a general method ranking"
            )
            return 0

        if args.command == "verify-ocr-candidate-review":
            manifest = verify_ocr_candidate_review_manifest(args.manifest)
            print(
                f"[ok] verified {manifest['unit_count']} method-blind candidate "
                f"units over {manifest['source_count']} source pages"
            )
            print(
                "[boundary] packet verification does not evaluate candidate "
                "content or create human review"
            )
            return 0

        if args.command == "initialize-ocr-candidate-review-session":
            session_dir = initialize_ocr_candidate_review_session(
                args.manifest,
                args.session_id,
                review_root=args.review_root,
            )
            print(session_dir)
            print(
                "[boundary] an initialized session contains no human judgment"
            )
            return 0

        if args.command == "human-review-workbench":
            serve_human_review_workbench(
                args.session_dir,
                port=args.port,
                open_browser=args.open_browser,
            )
            return 0

        if args.command == "sync-human-review-session-control":
            result = synchronize_human_review_session_control(
                args.session_dir
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "analyze-ocr-candidate-review":
            result = analyze_frozen_ocr_candidate_review(args.session_dir)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "materialize-translation-source":
            manifest = materialize_translation_source(
                args.tree_repo_root,
                args.sample_plan,
                args.anchors,
                args.packet_id,
                args.visual_item_ref,
                args.visual_file_ref,
                args.visual_file_sha256,
                shared_root=args.shared_root,
                pdfinfo=args.pdfinfo,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print(
                "[boundary] source packet awaits real source-visible human review; "
                "all translation lanes remain unstarted"
            )
            return 0

        if args.command == "verify-translation-source":
            manifest = verify_translation_source_manifest(args.manifest)
            print(
                f"[ok] verified {manifest['fragment_count']} pre-translation source candidates "
                f"({manifest['candidate_set_sha256']})"
            )
            print("[boundary] fixity is not accepted German transcription or translation quality")
            return 0

        if args.command == "verify-translation-source-inspection":
            inspection = verify_translation_source_inspection(
                args.inspection, args.manifest
            )
            counts = inspection["summary"]["decision_counts"]
            print(
                "[ok] verified exhaustive advisory inspection of "
                f"{inspection['summary']['record_count']} candidates: "
                f"{counts['accept_with_limits']} limited, {counts['reject']} rejected, "
                f"{counts['uncertain']} uncertain"
            )
            print(
                "[boundary] selector rejection is model-advisory; German source acceptance "
                "still requires a real human source-visible pass"
            )
            return 0

        if args.command == "materialize-translation-source-review":
            manifest = materialize_translation_source_review(
                args.tree_repo_root,
                args.review_plan,
                args.packet_id,
                shared_root=args.shared_root,
                pdftoppm=args.pdftoppm,
                pdfinfo=args.pdfinfo,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print(
                "[boundary] interfaces and templates are blank; only a real human "
                "source-visible pass may create review evidence"
            )
            return 0

        if args.command == "verify-translation-source-review":
            manifest = verify_translation_source_review_manifest(args.manifest)
            print(
                f"[ok] verified {len(manifest['units'])} blind review units and "
                f"{manifest['render']['unique_page_count']} source-page renders"
            )
            print(
                "[boundary] interface fixity is not human review, accepted German, or translation"
            )
            return 0

        if args.command == "gate-translation-lab":
            readiness = inspect_translation_lab_readiness(
                args.tree_repo_root,
                args.laboratory_plan,
                args.source_review_manifest,
                args.human_review_output,
                reference_register_path=args.reference_register,
            )
            print(json.dumps(readiness, ensure_ascii=False, indent=2))
            print(
                "[boundary] readiness checks declared source-review evidence and independent pre-draft lane order; "
                "it is not human identity, transcription, translation, etymology, or semantic truth"
            )
            return 0 if readiness["decision"] == (
                "ready-for-independent-source-grounded-pre-draft-analysis"
            ) else 2

        if args.command == "materialize-tesseract-runtime":
            manifest = build_tesseract_runtime(
                args.rpm_cache,
                runtime_root=args.runtime_root,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] runtime fixity is not OCR quality")
            return 0

        if args.command == "freeze-kraken-party-acquisition":
            receipt = freeze_kraken_party_acquisition(
                args.wheel_cache,
                args.party_source,
                args.model,
                args.zenodo_record,
                args.output,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            print("[boundary] acquisition fixity is not OCR quality")
            return 0

        if args.command == "materialize-kraken-party-runtime":
            manifest = build_kraken_party_runtime(
                args.acquisition_receipt,
                runtime_root=args.runtime_root,
                python_command=args.python,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] runtime fixity is not OCR quality")
            return 0

        if args.command == "freeze-paddle-ocr-acquisition":
            receipt = freeze_paddle_ocr_acquisition(
                args.wheel_cache,
                args.model_cache,
                args.output,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            print("[boundary] acquisition fixity is not OCR quality")
            return 0

        if args.command == "materialize-paddle-ocr-runtime":
            manifest = build_paddle_ocr_runtime(
                args.acquisition_receipt,
                runtime_root=args.runtime_root,
                python_command=args.python,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] runtime fixity and synthetic smoke are not OCR quality")
            return 0

        if args.command == "freeze-docling-structure-acquisition":
            receipt = freeze_docling_acquisition(
                args.wheel_cache,
                args.model_dir,
                args.output,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            print("[boundary] acquisition fixity is not structure quality")
            return 0

        if args.command == "materialize-docling-structure-runtime":
            manifest = build_docling_runtime(
                args.acquisition_receipt,
                runtime_root=args.runtime_root,
                python_command=args.python,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] runtime fixity and import smoke are not structure quality")
            return 0

        if args.command == "freeze-paddle-vl-structure-acquisition":
            receipt = freeze_paddle_vl_acquisition(
                args.wheel_cache,
                args.vl_model_dir,
                args.layout_model_dir,
                args.output,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
            print("[boundary] acquisition fixity is not structure quality")
            return 0

        if args.command == "materialize-paddle-vl-structure-runtime":
            manifest = build_paddle_vl_runtime(
                args.acquisition_receipt,
                runtime_root=args.runtime_root,
                owner_receipt_refs=args.owner_receipt,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            print(json.dumps(manifest, ensure_ascii=False, indent=2))
            print("[boundary] runtime fixity and import smoke are not structure quality")
            return 0

        if args.command == "execute-tesseract-ocr":
            metrics = execute_tesseract_ocr(
                args.run_root,
                args.sample_plan,
                args.render_manifest,
                args.runtime_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] OCR A remains blocked from quality claims until real human gold and review")
            return 0

        if args.command == "compare-tesseract-ocr":
            comparison = compare_tesseract_runs(args.first_run_root, args.second_run_root)
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
            print("[boundary] repeatability is not OCR accuracy")
            return 0 if comparison["mechanically_identical"] else 2

        if args.command == "execute-kraken-party-ocr":
            metrics = execute_kraken_party_ocr(
                args.run_root,
                args.sample_plan,
                args.render_manifest,
                args.runtime_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] OCR B remains blocked from quality claims until real human gold and review")
            return 0

        if args.command == "compare-kraken-party-ocr":
            comparison = compare_kraken_party_runs(args.first_run_root, args.second_run_root)
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
            print("[boundary] canonical repeatability and raw byte identity are not OCR accuracy")
            return 0 if comparison["mechanically_identical"] else 2

        if args.command == "execute-paddle-ocr":
            metrics = execute_paddle_ocr(
                args.run_root,
                args.sample_plan,
                args.render_manifest,
                args.runtime_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
                selected_sample_ids=args.sample_ids,
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] OCR C remains blocked from quality claims until real human gold and review")
            return 0

        if args.command == "compare-paddle-ocr":
            comparison = compare_paddle_ocr_runs(args.first_run_root, args.second_run_root)
            print(json.dumps(comparison, ensure_ascii=False, indent=2))
            print("[boundary] canonical repeatability and raw byte identity are not OCR accuracy")
            return 0 if comparison["mechanically_identical"] else 2

        if args.command == "execute-native-structure":
            metrics = execute_native_structure(
                args.run_root,
                args.tree_repo_root,
                args.sample_plan,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] native extraction is awaiting source-visible manual review")
            return 0

        if args.command == "execute-docling-structure":
            metrics = execute_docling_structure(
                args.run_root,
                args.tree_repo_root,
                args.sample_plan,
                args.runtime_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
                selected_sample_ids=args.sample_ids,
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] Structure B remains blocked from quality claims until real human review")
            return 0

        if args.command == "execute-paddle-vl-structure":
            metrics = execute_paddle_vl_structure(
                args.run_root,
                args.visual_plan,
                args.render_manifest,
                args.selection,
                args.runtime_manifest,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
                selected_sample_ids=args.sample_ids,
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] Structure C remains blocked from quality claims until real human review")
            return 0

        if args.command == "execute-lexical-retrieval":
            metrics = execute_lexical_retrieval(
                args.run_root,
                args.structure_run_root,
                args.query_plan,
                args.query_content,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] lexical rankings are awaiting source-visible human relevance review")
            return 0

        if args.command == "execute-semantic-retrieval":
            metrics = execute_semantic_retrieval(
                args.run_root,
                args.structure_run_root,
                args.query_plan,
                args.query_content,
                collection=args.collection,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] semantic and reranked outputs await source-visible human relevance review")
            return 0

        if args.command == "execute-granite-retrieval":
            metrics = execute_granite_retrieval(
                args.run_root,
                args.structure_run_root,
                args.query_plan,
                args.query_content,
                args.runtime_python,
                args.runtime_manifest,
                args.model_snapshot,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] Granite rankings await source-visible human relevance review")
            return 0

        if args.command == "execute-canonical-graph":
            metrics = execute_canonical_graph(
                args.run_root,
                args.tree_repo_root,
                args.claim_set,
                args.query_plan,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] canonical claim queries are awaiting source-visible human graph review")
            return 0

        if args.command == "execute-neo4j-graph":
            metrics = execute_neo4j_graph(
                args.run_root,
                args.tree_repo_root,
                args.claim_set,
                args.query_plan,
                lab_run=args.lab_run,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] Neo4j projection remains unreviewed and Tree of Sophia remains canonical")
            return 0

        if args.command == "execute-oxigraph-graph":
            metrics = execute_oxigraph_graph(
                args.run_root,
                args.tree_repo_root,
                args.claim_set,
                args.query_plan,
                args.runtime_python,
                args.runtime_manifest,
                lab_run=args.lab_run,
                invocation=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            )
            issues = verify_run(args.run_root)
            if issues:
                raise LaboratoryError("executed run packet is invalid: " + "; ".join(issues))
            print(json.dumps(metrics, ensure_ascii=False, indent=2))
            print("[boundary] Oxigraph projection remains unreviewed and Tree of Sophia remains canonical")
            return 0

        suite = load_suite()
        experiment = find_experiment(suite, args.experiment) if hasattr(args, "experiment") else None

        if args.command == "inspect":
            print(json.dumps(experiment, ensure_ascii=False, indent=2))
            return 0

        if args.command == "preflight":
            assert experiment is not None
            variant = find_variant(experiment, args.variant)
            receipt = build_preflight_receipt(
                suite,
                experiment,
                variant,
                runtime_manifest_path=args.runtime_manifest,
            )
            rendered_receipt = json.dumps(receipt, ensure_ascii=False, indent=2)
            if args.output:
                if receipt["storage_preflight"].get("allowed") is not True:
                    print(rendered_receipt)
                    raise LaboratoryError("storage owner denied the write; blocked receipt remains on stdout only")
                write_json(args.output, receipt)
            print(rendered_receipt)
            return 0 if receipt["decision"] in {"ready", "awaiting-human-input"} else 2

        if args.command == "prepare":
            assert experiment is not None
            variant = find_variant(experiment, args.variant)
            preflight = load_json(args.preflight)
            output_root = args.output_root or Path(suite["artifact_roots"]["durable"])
            run_root = prepare_run(suite, experiment, variant, preflight, args.run_id, output_root)
            print(run_root)
            return 0

        if args.command == "verify-run":
            issues = verify_run(args.run_root)
            if issues:
                for issue in issues:
                    print(f"[error] {issue}", file=sys.stderr)
                return 1
            print(f"[ok] verified run packet {args.run_root}")
            print("[boundary] packet completeness is not content acceptance")
            return 0
    except (
        LaboratoryError,
        OcrCandidateReviewError,
        NativeStructureError,
        LexicalRetrievalError,
        SemanticRetrievalError,
        GraniteRetrievalError,
        CanonicalGraphError,
        Neo4jGraphError,
        OxigraphGraphError,
        OcrRenderError,
        TranslationSourceError,
        RuntimeManifestError,
        TesseractOcrError,
        KrakenPartyOcrError,
        PaddleOcrError,
        TesseractRuntimeError,
        KrakenPartyRuntimeError,
        PaddleOcrRuntimeError,
        StructureRuntimeError,
        DoclingStructureError,
        PaddleVlStructureError,
        HumanReviewWorkbenchError,
        OcrCandidateAnalysisError,
    ) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
