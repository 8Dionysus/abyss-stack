#!/usr/bin/env python3
"""Execute frozen OCR B with Kraken segmentation and the Party v4 recognizer."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import resource
import signal
import shutil
import statistics
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ocr_render import OcrRenderError, validate_visual_plan, verify_render_manifest
from runtime_manifest import RuntimeManifestError, verify_runtime_manifest


LANGUAGE_MAP = {"de": "deu", "ru": "rus"}
EXPECTED_RUNTIME_ID = "kraken-7.0.2-party-c2589b1"
EXPECTED_KRAKEN_VERSION = "kraken, version 7.0.2"
EXPECTED_PARTY_VERSION = "party_offline_cli.py, version 0.0.0.post492+gc2589b1"
EXPECTED_PARTY_MODEL_SHA256 = (
    "d6f3c2273687a79dd4852c4cfe63ec4c9e75a2a148fe02a8b787ab6afec236aa"
)
EXPECTED_PARTY_MODEL_BYTES = 518_329_816
EXPECTED_BASELINE_MODEL_SHA256 = (
    "77a638a83c9e535620827a09e410ed36391e9e8e8126d5796a0f15b978186056"
)
EXPECTED_BASELINE_MODEL_BYTES = 5_047_020
PARTY_MODEL_RELATIVE_PATH = "models/model.safetensors"
BASELINE_MODEL_RELATIVE_PATH = (
    "venv/lib/python3.12/site-packages/kraken/blla.mlmodel"
)
VOLATILE_ALTO_ATTRIBUTES = {"ID", "REF", "TAGREFS"}
MAX_GENERATED_TOKENS = 384
DECODER_SATURATION_CHARACTER_THRESHOLD = 300
DECODER_SATURATION_LINE_LIMIT = 2


class KrakenPartyOcrError(RuntimeError):
    """Raised when OCR B cannot preserve the frozen experiment law."""


class KrakenPartyOcrStop(KrakenPartyOcrError):
    """Raised when OCR B must stop while preserving partial evidence."""


def _stop_on_sigterm(signum: int, _frame: object) -> None:
    try:
        signal_name = signal.Signals(signum).name
    except ValueError:
        signal_name = str(signum)
    raise KrakenPartyOcrStop(f"external stop signal received: {signal_name}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KrakenPartyOcrError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KrakenPartyOcrError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _existing_runtime_artifact_refs(run_root: Path) -> list[str]:
    refs: list[str] = []
    for relative_root in ("raw-output", "metrics"):
        root = run_root / relative_root
        if root.is_dir():
            refs.extend(_relative(run_root, path) for path in root.rglob("*") if path.is_file())
    invocation = run_root / "receipts/kraken-party-ocr-invocation.json"
    if invocation.is_file():
        refs.append(_relative(run_root, invocation))
    return sorted(set(refs))


def _partial_sample_ids(run_root: Path, completed_sample_ids: list[str]) -> list[str]:
    raw_root = run_root / "raw-output"
    if not raw_root.is_dir():
        return []
    completed = set(completed_sample_ids)
    return sorted(
        path.name
        for path in raw_root.iterdir()
        if path.is_dir()
        and path.name not in completed
        and any(child.is_file() for child in path.rglob("*"))
    )


def _finalize_aborted_receipt(
    run_root: Path,
    receipt_path: Path,
    receipt: dict[str, Any],
    samples: list[dict[str, Any]],
    artifact_refs: list[str],
    *,
    status: str,
    error: str,
) -> None:
    if status not in {"failed", "stopped"}:
        raise ValueError(f"unsupported aborted status: {status}")
    completed_sample_ids = [str(sample["sample_id"]) for sample in samples]
    partial_sample_ids = _partial_sample_ids(run_root, completed_sample_ids)
    errors = [error]
    if partial_sample_ids:
        errors.append("partial-output-sample-ids: " + ", ".join(partial_sample_ids))
    receipt["status"] = status
    receipt["finished_at_utc"] = _utc_now()
    receipt["sample_ids"] = completed_sample_ids
    receipt["artifact_refs"] = sorted(
        set(artifact_refs + _existing_runtime_artifact_refs(run_root))
    )
    receipt["errors"] = errors
    _write_json(receipt_path, receipt)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _relative(run_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_root.resolve()).as_posix()
    except ValueError as exc:
        raise KrakenPartyOcrError(f"artifact escapes run root: {path}") from exc


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1]


def _parse_alto(path: Path) -> ET.Element:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise KrakenPartyOcrError(f"cannot parse ALTO {path}: {exc}") from exc
    if _local_name(root.tag) != "alto":
        raise KrakenPartyOcrError(f"unexpected ALTO root in {path}: {_local_name(root.tag)}")
    return root


def _canonical_element(element: ET.Element) -> dict[str, Any]:
    attributes = {
        _local_name(key): value
        for key, value in sorted(element.attrib.items())
        if _local_name(key) not in VOLATILE_ALTO_ATTRIBUTES
    }
    payload: dict[str, Any] = {
        "tag": _local_name(element.tag),
        "attributes": attributes,
        "children": [_canonical_element(child) for child in list(element)],
    }
    text = (element.text or "").strip()
    if text:
        payload["text"] = text
    return payload


def _ordered_lines(root: ET.Element) -> tuple[list[ET.Element], str]:
    layout_lines = [element for element in root.iter() if _local_name(element.tag) == "TextLine"]
    by_id = {element.attrib.get("ID"): element for element in layout_lines if element.attrib.get("ID")}
    referenced: list[ET.Element] = []
    seen: set[int] = set()
    for element in root.iter():
        if _local_name(element.tag) != "ElementRef":
            continue
        line = by_id.get(element.attrib.get("REF"))
        if line is not None and id(line) not in seen:
            referenced.append(line)
            seen.add(id(line))
    if not referenced:
        return layout_lines, "layout-document-order"
    missing = [line for line in layout_lines if id(line) not in seen]
    if missing:
        return referenced + missing, "alto-reading-order-plus-layout-fallback"
    return referenced, "alto-reading-order"


def _line_text(line: ET.Element) -> str:
    pieces: list[str] = []
    for child in list(line):
        kind = _local_name(child.tag)
        if kind == "String":
            content = child.attrib.get("CONTENT", "")
            if content:
                pieces.append(content)
        elif kind == "SP" and pieces and pieces[-1] != " ":
            pieces.append(" ")
    return "".join(pieces).strip()


def _alto_diagnostics(path: Path) -> dict[str, Any]:
    root = _parse_alto(path)
    lines, order_mode = _ordered_lines(root)
    texts = [_line_text(line) for line in lines]
    language_counts: dict[str, int] = {}
    word_confidences: list[float] = []
    string_count = 0
    for line in lines:
        language = line.attrib.get("LANG")
        if language:
            language_counts[language] = language_counts.get(language, 0) + 1
        for element in line.iter():
            if _local_name(element.tag) != "String":
                continue
            string_count += 1
            try:
                confidence = float(element.attrib.get("WC", ""))
            except ValueError:
                continue
            word_confidences.append(confidence)
    layout = next((element for element in root.iter() if _local_name(element.tag) == "Layout"), None)
    if layout is None:
        raise KrakenPartyOcrError(f"ALTO has no Layout: {path}")
    layout_lines = [element for element in layout.iter() if _local_name(element.tag) == "TextLine"]
    line_positions = {
        element.attrib.get("ID"): index
        for index, element in enumerate(layout_lines)
        if element.attrib.get("ID")
    }
    reading_order_positions: list[int] = []
    for element in root.iter():
        if _local_name(element.tag) != "ElementRef":
            continue
        position = line_positions.get(element.attrib.get("REF"))
        if position is not None:
            reading_order_positions.append(position)
    canonical_payload = {
        "layout": _canonical_element(layout),
        "reading_order_positions": reading_order_positions,
    }
    diplomatic_text = "\n".join(texts) + ("\n" if texts else "")
    line_character_counts = [len(text) for text in texts]
    return {
        "line_count": len(lines),
        "nonempty_line_count": sum(bool(text) for text in texts),
        "string_count": string_count,
        "recognized_characters": len(diplomatic_text),
        "recognized_non_whitespace_characters": len("".join(diplomatic_text.split())),
        "max_line_characters": max(line_character_counts, default=0),
        "decoder_saturation_line_count": sum(
            count >= DECODER_SATURATION_CHARACTER_THRESHOLD for count in line_character_counts
        ),
        "language_counts": language_counts,
        "reading_order_mode": order_mode,
        "mean_word_confidence": statistics.fmean(word_confidences)
        if word_confidences
        else None,
        "median_word_confidence": statistics.median(word_confidences)
        if word_confidences
        else None,
        "confidence_boundary": "engine confidence is not source-visible accuracy",
        "diplomatic_text": diplomatic_text,
        "canonical_sha256": _canonical_sha256(canonical_payload),
    }


def _decoder_saturation_guard(diagnostics: dict[str, Any]) -> dict[str, Any]:
    saturated_lines = int(diagnostics.get("decoder_saturation_line_count", 0))
    return {
        "character_threshold": DECODER_SATURATION_CHARACTER_THRESHOLD,
        "line_limit": DECODER_SATURATION_LINE_LIMIT,
        "observed_saturated_lines": saturated_lines,
        "max_line_characters": int(diagnostics.get("max_line_characters", 0)),
        "triggered": saturated_lines >= DECODER_SATURATION_LINE_LIMIT,
        "boundary": (
            "mechanical near-decoder-cap guard only; it does not determine source-visible accuracy"
        ),
    }


def _file_record(run_root: Path, path: Path, *, canonical_sha256: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "ref": _relative(run_root, path),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }
    if canonical_sha256 is not None:
        record["canonical_sha256"] = canonical_sha256
    return record


def _write_step_logs(run_root: Path, prefix: Path, stdout: bytes, stderr: bytes) -> dict[str, Any]:
    stdout_path = prefix.with_suffix(".stdout.txt")
    stderr_path = prefix.with_suffix(".stderr.txt")
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {
        "stdout": _file_record(run_root, stdout_path),
        "stderr": _file_record(run_root, stderr_path),
    }


def _run_step(
    run_root: Path,
    prefix: Path,
    arguments: list[str],
    environment: dict[str, str],
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            timeout=timeout_seconds,
            env=environment,
        )
        returncode: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = None
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
    elapsed = time.perf_counter() - started
    logs = _write_step_logs(run_root, prefix, stdout, stderr)
    return {
        "argv": arguments,
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "elapsed_seconds": elapsed,
        "stdout": logs["stdout"],
        "stderr": logs["stderr"],
        "stdout_line_count": len(stdout.decode("utf-8", errors="replace").splitlines()),
        "stderr_line_count": len(stderr.decode("utf-8", errors="replace").splitlines()),
    }


def _require_step(step_name: str, step: dict[str, Any]) -> None:
    if step["returncode"] == 0 and step["timed_out"] is False:
        return
    raise KrakenPartyOcrError(
        f"{step_name} failed: returncode={step['returncode']} timed_out={step['timed_out']} "
        f"stderr={step['stderr']['ref']}"
    )


def _version(command: Path, expected: str, environment: dict[str, str]) -> str:
    completed = subprocess.run(
        (command.as_posix(), "--version"),
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
        env=environment,
    )
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    first = combined.splitlines()[0] if combined else ""
    if completed.returncode != 0 or first != expected:
        raise KrakenPartyOcrError(f"unexpected runtime identity for {command}: {combined[:400]}")
    return first


def _runtime_artifact(runtime: dict[str, Any], relative_path: str) -> dict[str, Any]:
    for artifact in runtime.get("artifacts", []):
        if artifact.get("relative_path") == relative_path:
            return artifact
    raise KrakenPartyOcrError(f"runtime manifest omits {relative_path}")


def _verify_runtime_identity(
    runtime_manifest_path: Path,
) -> tuple[dict[str, Any], Path, Path]:
    try:
        runtime = verify_runtime_manifest(
            runtime_manifest_path,
            experiment_id="tos-ocr-foundation-v1",
            variant="B",
            required_commands=["kraken", "party"],
        )
    except RuntimeManifestError as exc:
        raise KrakenPartyOcrError(str(exc)) from exc
    if runtime.get("runtime_id") != EXPECTED_RUNTIME_ID:
        raise KrakenPartyOcrError(f"unexpected OCR B runtime_id: {runtime.get('runtime_id')}")
    runtime_root = runtime_manifest_path.resolve().parent
    model = runtime_root / PARTY_MODEL_RELATIVE_PATH
    baseline = runtime_root / BASELINE_MODEL_RELATIVE_PATH
    expected = (
        (
            PARTY_MODEL_RELATIVE_PATH,
            model,
            EXPECTED_PARTY_MODEL_SHA256,
            EXPECTED_PARTY_MODEL_BYTES,
        ),
        (
            BASELINE_MODEL_RELATIVE_PATH,
            baseline,
            EXPECTED_BASELINE_MODEL_SHA256,
            EXPECTED_BASELINE_MODEL_BYTES,
        ),
    )
    for relative_path, path, digest, size in expected:
        artifact = _runtime_artifact(runtime, relative_path)
        if (
            not path.is_file()
            or path.stat().st_size != size
            or _sha256_file(path) != digest
            or artifact.get("sha256") != digest
            or artifact.get("bytes") != size
        ):
            raise KrakenPartyOcrError(f"runtime artifact drift: {relative_path}")
    return runtime, model, baseline


def _verify_prepared_run(
    run_root: Path, runtime_manifest_path: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    receipt = _load_json(run_root / "run.receipt.json")
    experiment = _load_json(run_root / "experiment.spec.json")
    preflight = _load_json(run_root / "receipts/preflight.json")
    if receipt.get("experiment_id") != "tos-ocr-foundation-v1" or receipt.get("variant") != "B":
        raise KrakenPartyOcrError("Kraken/Party runner requires prepared OCR B")
    if receipt.get("status") != "prepared" or preflight.get("decision") != "ready":
        raise KrakenPartyOcrError("run must be prepared from a ready preflight")
    if experiment.get("family") != "ocr":
        raise KrakenPartyOcrError("experiment specification is not OCR")
    admission = preflight.get("runtime_admission")
    if not isinstance(admission, dict) or admission.get("verified") is not True:
        raise KrakenPartyOcrError("preflight does not contain a verified isolated runtime")
    if Path(str(admission.get("manifest_ref"))).resolve() != runtime_manifest_path.resolve():
        raise KrakenPartyOcrError("runtime manifest differs from the preflighted manifest")
    if _sha256_file(runtime_manifest_path.resolve()) != admission.get("manifest_sha256"):
        raise KrakenPartyOcrError("runtime manifest digest drift after preflight")
    return receipt, experiment, preflight


def _semantic_output_set_digest(samples: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": sample["sample_id"],
                "render_sha256": sample["render_sha256"],
                "raw_segmentation": sample["outputs"]["raw_segmentation"]["canonical_sha256"],
                "conditioned_segmentation": sample["outputs"]["conditioned_segmentation"][
                    "canonical_sha256"
                ],
                "recognized_alto": sample["outputs"]["recognized_alto"]["canonical_sha256"],
                "diplomatic_text": sample["outputs"]["diplomatic_text"]["sha256"],
            }
            for sample in samples
        ]
    )


def _raw_output_set_digest(samples: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "sample_id": sample["sample_id"],
                "outputs": {
                    name: {"sha256": output["sha256"], "bytes": output["bytes"]}
                    for name, output in sorted(sample["outputs"].items())
                },
            }
            for sample in samples
        ]
    )


def execute_kraken_party_ocr(
    run_root: Path,
    sample_plan_path: Path,
    render_manifest_path: Path,
    runtime_manifest_path: Path,
    *,
    invocation: list[str],
) -> dict[str, Any]:
    """Run OCR B and leave content quality awaiting real manual review."""

    run_root = run_root.resolve()
    sample_plan_path = sample_plan_path.resolve()
    render_manifest_path = render_manifest_path.resolve()
    runtime_manifest_path = runtime_manifest_path.resolve()
    receipt_path = run_root / "run.receipt.json"
    receipt, experiment, _preflight = _verify_prepared_run(run_root, runtime_manifest_path)
    plan = _load_json(sample_plan_path)
    plan_issues = validate_visual_plan(plan)
    if plan_issues:
        raise KrakenPartyOcrError("invalid frozen visual plan: " + "; ".join(plan_issues))
    try:
        render_manifest = verify_render_manifest(render_manifest_path)
    except OcrRenderError as exc:
        raise KrakenPartyOcrError(str(exc)) from exc
    if render_manifest.get("sample_plan_sha256") != _sha256_file(sample_plan_path):
        raise KrakenPartyOcrError("render packet was built from a different visual plan")
    if render_manifest.get("reference_witness_state") != "sealed-not-consulted":
        raise KrakenPartyOcrError("reference witness seal is not intact")
    runtime, model_path, baseline_path = _verify_runtime_identity(runtime_manifest_path)

    kraken_command = Path(runtime["commands"]["kraken"])
    party_command = Path(runtime["commands"]["party"])
    environment = os.environ.copy()
    environment.update({str(key): str(value) for key, value in runtime["environment"].items()})
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "4",
            "OPENBLAS_NUM_THREADS": "4",
            "NUMEXPR_NUM_THREADS": "4",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    kraken_version = _version(kraken_command, EXPECTED_KRAKEN_VERSION, environment)
    party_version = _version(party_command, EXPECTED_PARTY_VERSION, environment)
    render_root = Path(render_manifest["artifact_root"])
    renders = render_manifest["renders"]

    started_at = _utc_now()
    wall_started = time.perf_counter()
    artifact_refs: list[str] = list(receipt.get("artifact_refs", []))
    variant = next(row for row in experiment["variants"] if row["label"] == "B")
    invocation_path = run_root / "receipts/kraken-party-ocr-invocation.json"
    _write_json(
        invocation_path,
        {
            "captured_at_utc": started_at,
            "argv": invocation,
            "python": platform.python_version(),
            "kraken": kraken_version,
            "party": party_version,
            "runner_sha256": _sha256_file(Path(__file__)),
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "render_manifest_sha256": _sha256_file(render_manifest_path),
            "render_set_sha256": render_manifest["render_set_sha256"],
            "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
            "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
            "party_model_sha256": EXPECTED_PARTY_MODEL_SHA256,
            "baseline_model_sha256": EXPECTED_BASELINE_MODEL_SHA256,
            "rights_posture": "restricted-source-derived-text-private-runtime-only",
            "reference_witness_state": "sealed-not-consulted",
        },
    )
    artifact_refs.append(_relative(run_root, invocation_path))
    receipt["status"] = "running"
    receipt["started_at_utc"] = started_at
    receipt["method_revision"] = {
        "implementation": variant["implementation"],
        "version": f"{kraken_version}; {party_version}; decoder-saturation-stop-guard-v1",
        "runtime": runtime["runtime_id"],
        "model": f"Party base v4 sha256:{EXPECTED_PARTY_MODEL_SHA256}",
        "artifact_digest": runtime["artifact_set_sha256"],
    }
    receipt["invocation_ref"] = _relative(run_root, invocation_path)
    receipt["artifact_refs"] = sorted(set(artifact_refs))
    _write_json(receipt_path, receipt)

    samples: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    previous_sigterm_handler = signal.signal(signal.SIGTERM, _stop_on_sigterm)
    try:
        for render in renders:
            sample_id = str(render["sample_id"])
            party_language = LANGUAGE_MAP.get(str(render["language"]))
            if party_language is None:
                raise KrakenPartyOcrError(f"unsupported OCR language for {sample_id}")
            image_path = render_root / str(render["png_ref"])
            if _sha256_file(image_path) != render["png_sha256"]:
                raise KrakenPartyOcrError(f"render drift immediately before OCR: {sample_id}")
            sample_root = run_root / "raw-output" / sample_id
            sample_root.mkdir(parents=True, exist_ok=False)

            raw_segmentation = sample_root / "segmentation.raw.alto.xml"
            conditioned_segmentation = sample_root / "segmentation.language.alto.xml"
            recognized_alto = sample_root / "recognition.alto.xml"
            diplomatic_text = sample_root / "recognition.txt"

            segmentation_step = _run_step(
                run_root,
                sample_root / "segmentation",
                [
                    kraken_command.as_posix(),
                    "--threads",
                    "4",
                    "-d",
                    "cpu",
                    "-r",
                    "-a",
                    "-i",
                    image_path.as_posix(),
                    raw_segmentation.as_posix(),
                    "segment",
                    "-bl",
                    "-d",
                    "horizontal-lr",
                ],
                environment,
                timeout_seconds=600,
            )
            for stream in ("stdout", "stderr"):
                artifact_refs.append(segmentation_step[stream]["ref"])
            _require_step(f"Kraken segmentation for {sample_id}", segmentation_step)
            raw_diagnostics = _alto_diagnostics(raw_segmentation)

            shutil.copyfile(raw_segmentation, conditioned_segmentation)
            conditioning_step = _run_step(
                run_root,
                sample_root / "language-conditioning",
                [
                    party_command.as_posix(),
                    "set-lang",
                    party_language,
                    conditioned_segmentation.as_posix(),
                ],
                environment,
                timeout_seconds=120,
            )
            for stream in ("stdout", "stderr"):
                artifact_refs.append(conditioning_step[stream]["ref"])
            _require_step(f"Party language conditioning for {sample_id}", conditioning_step)
            conditioned_diagnostics = _alto_diagnostics(conditioned_segmentation)
            if conditioned_diagnostics["line_count"] != raw_diagnostics["line_count"]:
                raise KrakenPartyOcrError(f"language conditioning changed line count: {sample_id}")
            if conditioned_diagnostics["language_counts"].get(party_language, 0) != raw_diagnostics[
                "line_count"
            ]:
                raise KrakenPartyOcrError(f"language conditioning did not cover every line: {sample_id}")

            recognition_step = _run_step(
                run_root,
                sample_root / "recognition",
                [
                    party_command.as_posix(),
                    "-d",
                    "cpu",
                    "--precision",
                    "32-true",
                    "--workers",
                    "0",
                    "--threads",
                    "4",
                    "--seed",
                    "42",
                    "--deterministic",
                    "ocr",
                    "-l",
                    model_path.as_posix(),
                    "-a",
                    "-i",
                    conditioned_segmentation.as_posix(),
                    recognized_alto.as_posix(),
                    "-B",
                    "1",
                    "--max-generated-tokens",
                    str(MAX_GENERATED_TOKENS),
                    "--add-lang-token",
                    "--raise-on-error",
                ],
                environment,
                timeout_seconds=1800,
            )
            for stream in ("stdout", "stderr"):
                artifact_refs.append(recognition_step[stream]["ref"])
            _require_step(f"Party recognition for {sample_id}", recognition_step)
            recognized_diagnostics = _alto_diagnostics(recognized_alto)
            diplomatic_text.write_text(recognized_diagnostics.pop("diplomatic_text"), encoding="utf-8")
            saturation_guard = _decoder_saturation_guard(recognized_diagnostics)
            recognized_diagnostics["decoder_saturation_guard"] = saturation_guard

            if raw_diagnostics["line_count"] == 0:
                warnings.append({"sample_id": sample_id, "warning": "segmentation-produced-zero-lines"})
            if recognized_diagnostics["line_count"] != raw_diagnostics["line_count"]:
                warnings.append({"sample_id": sample_id, "warning": "recognized-line-count-drift"})
            if recognized_diagnostics["recognized_non_whitespace_characters"] == 0:
                warnings.append({"sample_id": sample_id, "warning": "empty-recognized-text"})
            recognized_language_lines = recognized_diagnostics["language_counts"].get(
                party_language, 0
            )
            if recognized_language_lines != conditioned_diagnostics["line_count"]:
                warnings.append(
                    {
                        "sample_id": sample_id,
                        "warning": "recognized-alto-did-not-preserve-line-language-metadata",
                    }
                )
            for name, step in (
                ("segmentation", segmentation_step),
                ("language-conditioning", conditioning_step),
                ("recognition", recognition_step),
            ):
                if step["stderr"]["bytes"]:
                    warnings.append({"sample_id": sample_id, "warning": f"{name}-stderr-nonempty"})

            outputs = {
                "raw_segmentation": _file_record(
                    run_root,
                    raw_segmentation,
                    canonical_sha256=raw_diagnostics["canonical_sha256"],
                ),
                "conditioned_segmentation": _file_record(
                    run_root,
                    conditioned_segmentation,
                    canonical_sha256=conditioned_diagnostics["canonical_sha256"],
                ),
                "recognized_alto": _file_record(
                    run_root,
                    recognized_alto,
                    canonical_sha256=recognized_diagnostics["canonical_sha256"],
                ),
                "diplomatic_text": _file_record(run_root, diplomatic_text),
            }
            for output in outputs.values():
                artifact_refs.append(output["ref"])
            metadata = {
                "sample_id": sample_id,
                "source_anchor_ref": render["anchor_ref"],
                "item_ref": render["item_ref"],
                "file_ref": render["file_ref"],
                "page": render["page"],
                "language": render["language"],
                "party_language": party_language,
                "difficulty": render["difficulty"],
                "gold_candidate": render["gold_candidate"],
                "render_ref": render["png_ref"],
                "render_sha256": render["png_sha256"],
                "outputs": outputs,
                "steps": {
                    "segmentation": segmentation_step,
                    "language_conditioning": conditioning_step,
                    "recognition": recognition_step,
                },
                "diagnostics": {
                    "raw_segmentation": raw_diagnostics,
                    "conditioned_segmentation": conditioned_diagnostics,
                    "recognized_alto": recognized_diagnostics,
                    "language_conditioning_verified_before_recognition": True,
                    "recognized_language_line_count": recognized_language_lines,
                    "language_metadata_boundary": (
                        "recognizer output may omit TextLine LANG; the separately retained conditioned "
                        "ALTO proves the decoder input"
                    ),
                },
                "content_status": "unreviewed-ocr-draft",
                "authority_boundary": "engine output only; not source text or accepted transcription",
            }
            metadata_path = sample_root / "sample.json"
            _write_json(metadata_path, metadata)
            artifact_refs.append(_relative(run_root, metadata_path))
            samples.append(metadata)
            receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
            receipt["artifact_refs"] = sorted(set(artifact_refs))
            _write_json(receipt_path, receipt)
            if saturation_guard["triggered"]:
                raise KrakenPartyOcrStop(
                    "decoder saturation guard triggered after "
                    f"{sample_id}: {saturation_guard['observed_saturated_lines']} lines reached "
                    f"at least {saturation_guard['character_threshold']} characters; "
                    "manual inspection and a revised method hypothesis are required"
                )

        output_manifest = {
            "schema_version": "tos_kraken_party_ocr_output_manifest_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "B",
            "run_id": receipt["run_id"],
            "sample_plan_sha256": _sha256_file(sample_plan_path),
            "render_manifest_ref": render_manifest_path.as_posix(),
            "render_manifest_sha256": _sha256_file(render_manifest_path),
            "render_id": render_manifest["render_id"],
            "render_set_sha256": render_manifest["render_set_sha256"],
            "runtime_manifest_ref": runtime_manifest_path.as_posix(),
            "runtime_manifest_sha256": _sha256_file(runtime_manifest_path),
            "runtime_artifact_set_sha256": runtime["artifact_set_sha256"],
            "kraken_version": kraken_version,
            "party_version": party_version,
            "party_model": {
                "ref": model_path.as_posix(),
                "sha256": EXPECTED_PARTY_MODEL_SHA256,
                "bytes": EXPECTED_PARTY_MODEL_BYTES,
                "doi": "10.5281/zenodo.20642057",
            },
            "baseline_model": {
                "ref": baseline_path.as_posix(),
                "sha256": EXPECTED_BASELINE_MODEL_SHA256,
                "bytes": EXPECTED_BASELINE_MODEL_BYTES,
            },
            "configuration": {
                "device": "cpu",
                "precision": "32-true",
                "workers": 0,
                "threads": 4,
                "seed": 42,
                "deterministic": True,
                "batch_size": 1,
                "max_generated_tokens": MAX_GENERATED_TOKENS,
                "decoder_saturation_guard": {
                    "character_threshold": DECODER_SATURATION_CHARACTER_THRESHOLD,
                    "line_limit": DECODER_SATURATION_LINE_LIMIT,
                },
                "add_language_token": True,
                "baseline_direction": "horizontal-lr",
                "language_map": LANGUAGE_MAP,
                "preprocessing": "none-outside-the-frozen-render",
                "network": "offline-enforced-by-runtime-wrapper",
            },
            "known_upstream_serialization_nondeterminism": (
                "Kraken emits UUID-bearing ALTO IDs; raw byte digests are retained while repeatability "
                "uses a canonical Layout and reading-order digest that excludes ID, REF, and TAGREFS"
            ),
            "reference_witness_state": "sealed-not-consulted",
            "samples": samples,
            "semantic_output_set_sha256": _semantic_output_set_digest(samples),
            "raw_output_set_sha256": _raw_output_set_digest(samples),
            "quality_status": "blocked-until-double-checked-human-gold",
            "authority_boundary": "reproducible OCR candidate evidence only; no source-text or winner verdict",
        }
        output_manifest_path = run_root / "raw-output/kraken-party-ocr-output-manifest.json"
        _write_json(output_manifest_path, output_manifest)
        artifact_refs.append(_relative(run_root, output_manifest_path))

        warnings_path = run_root / "raw-output/warnings.json"
        _write_json(warnings_path, {"warnings": warnings})
        artifact_refs.append(_relative(run_root, warnings_path))
        elapsed = time.perf_counter() - wall_started
        child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        artifact_bytes = sum(
            path.stat().st_size
            for path in run_root.rglob("*")
            if path.is_file() and path != receipt_path
        )
        metrics = {
            "schema_version": "tos_kraken_party_ocr_metrics_v1",
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "B",
            "sample_count": len(samples),
            "source_count": len({sample["item_ref"] for sample in samples}),
            "wall_seconds": elapsed,
            "pages_per_minute": len(samples) * 60 / elapsed if elapsed else None,
            "step_seconds": {
                "segmentation": sum(sample["steps"]["segmentation"]["elapsed_seconds"] for sample in samples),
                "language_conditioning": sum(
                    sample["steps"]["language_conditioning"]["elapsed_seconds"] for sample in samples
                ),
                "recognition": sum(sample["steps"]["recognition"]["elapsed_seconds"] for sample in samples),
            },
            "child_peak_rss_bytes": child_usage.ru_maxrss * 1024,
            "child_peak_rss_boundary": "maximum observed child RSS on Linux, not aggregate memory",
            "child_user_cpu_seconds": child_usage.ru_utime,
            "child_system_cpu_seconds": child_usage.ru_stime,
            "artifact_bytes": artifact_bytes,
            "empty_text_count": sum(
                sample["diagnostics"]["recognized_alto"]["recognized_non_whitespace_characters"] == 0
                for sample in samples
            ),
            "warning_count": len(warnings),
            "conditioned_line_count": sum(
                sample["diagnostics"]["conditioned_segmentation"]["line_count"]
                for sample in samples
            ),
            "recognized_language_metadata_line_count": sum(
                sample["diagnostics"]["recognized_language_line_count"] for sample in samples
            ),
            "quality": {
                "cer": None,
                "wer": None,
                "reading_order_error": None,
                "status": "blocked-until-double-checked-human-gold",
            },
            "human_cost": {
                "correction_time_seconds": None,
                "status": "not-measured-no-human-pass",
            },
            "traceability": {
                "mechanical_anchor_resolution": len(samples) / len(renders) if renders else None,
                "content_acceptance": "not-reviewed",
            },
            "authority_boundary": "mechanics, speed, resource, and engine diagnostics only; no OCR quality verdict",
        }
        metrics_path = run_root / "metrics/kraken-party-ocr-summary.json"
        _write_json(metrics_path, metrics)

        receipt["status"] = "awaiting-manual-review"
        receipt["finished_at_utc"] = _utc_now()
        receipt["sample_ids"] = [sample["sample_id"] for sample in samples]
        receipt["artifact_refs"] = sorted(set(artifact_refs))
        receipt["metric_refs"] = [_relative(run_root, metrics_path)]
        receipt["manual_review_refs"] = []
        receipt["errors"] = []
        _write_json(receipt_path, receipt)
        return metrics
    except (KrakenPartyOcrStop, KeyboardInterrupt) as exc:
        reason = str(exc) or "operator keyboard interrupt"
        _finalize_aborted_receipt(
            run_root,
            receipt_path,
            receipt,
            samples,
            artifact_refs,
            status="stopped",
            error=f"stopped: {reason}",
        )
        raise KrakenPartyOcrError(f"OCR B stopped: {reason}") from exc
    except Exception as exc:
        _finalize_aborted_receipt(
            run_root,
            receipt_path,
            receipt,
            samples,
            artifact_refs,
            status="failed",
            error=str(exc),
        )
        if isinstance(exc, KrakenPartyOcrError):
            raise
        raise KrakenPartyOcrError(str(exc)) from exc
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm_handler)


def compare_kraken_party_runs(first_run_root: Path, second_run_root: Path) -> dict[str, Any]:
    """Compare canonical OCR output and expose raw UUID-bearing byte drift separately."""

    manifest_name = "raw-output/kraken-party-ocr-output-manifest.json"
    first = _load_json(first_run_root.resolve() / manifest_name)
    second = _load_json(second_run_root.resolve() / manifest_name)
    common_fields = (
        "sample_plan_sha256",
        "render_set_sha256",
        "runtime_artifact_set_sha256",
        "kraken_version",
        "party_version",
        "party_model",
        "baseline_model",
        "configuration",
    )
    method_differences = [field for field in common_fields if first.get(field) != second.get(field)]
    first_samples = {row["sample_id"]: row for row in first.get("samples", [])}
    second_samples = {row["sample_id"]: row for row in second.get("samples", [])}
    semantic_differences: list[dict[str, Any]] = []
    raw_byte_differences: list[dict[str, Any]] = []
    for sample_id in sorted(set(first_samples) | set(second_samples)):
        left = first_samples.get(sample_id)
        right = second_samples.get(sample_id)
        if left is None or right is None:
            semantic_differences.append({"sample_id": sample_id, "difference": "missing-sample"})
            raw_byte_differences.append({"sample_id": sample_id, "difference": "missing-sample"})
            continue
        for output_name in sorted(set(left["outputs"]) | set(right["outputs"])):
            left_output = left["outputs"].get(output_name)
            right_output = right["outputs"].get(output_name)
            if left_output is None or right_output is None:
                semantic_differences.append(
                    {"sample_id": sample_id, "difference": "missing-output", "output": output_name}
                )
                raw_byte_differences.append(
                    {"sample_id": sample_id, "difference": "missing-output", "output": output_name}
                )
                continue
            semantic_key = "canonical_sha256" if "canonical_sha256" in left_output else "sha256"
            if left_output.get(semantic_key) != right_output.get(semantic_key):
                semantic_differences.append(
                    {
                        "sample_id": sample_id,
                        "difference": "canonical-output-digest",
                        "output": output_name,
                    }
                )
            if (left_output.get("sha256"), left_output.get("bytes")) != (
                right_output.get("sha256"),
                right_output.get("bytes"),
            ):
                raw_byte_differences.append(
                    {"sample_id": sample_id, "difference": "raw-byte-digest", "output": output_name}
                )
    semantic_set_equal = first.get("semantic_output_set_sha256") == second.get(
        "semantic_output_set_sha256"
    )
    raw_set_equal = first.get("raw_output_set_sha256") == second.get("raw_output_set_sha256")
    mechanically_identical = not method_differences and not semantic_differences and semantic_set_equal
    return {
        "schema_version": "tos_kraken_party_ocr_repeat_comparison_v1",
        "first_run_id": first.get("run_id"),
        "second_run_id": second.get("run_id"),
        "method_differences": method_differences,
        "semantic_differences": semantic_differences,
        "raw_byte_differences": raw_byte_differences,
        "semantic_output_set_sha256_equal": semantic_set_equal,
        "raw_output_set_sha256_equal": raw_set_equal,
        "mechanically_identical": mechanically_identical,
        "raw_byte_identical": not raw_byte_differences and raw_set_equal,
        "nondeterminism_boundary": (
            "mechanically_identical uses canonical ALTO Layout and reading order plus exact plain text; "
            "raw UUID-bearing XML differences remain visible and are never reported as byte-identical"
        ),
        "authority_boundary": "repeatability only; no OCR accuracy or source-text verdict",
    }
