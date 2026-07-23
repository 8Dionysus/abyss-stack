#!/usr/bin/env python3
"""Freeze and build OCR C's exact offline PaddleOCR CPU runtime.

Network acquisition is deliberately outside this module. The freezer accepts
one already downloaded wheel closure and three official BOS inference-model
archives, inventories every byte, and writes a hash-complete acquisition lock.
The builder installs only that lock into a host-managed Python 3.12 runtime and
extracts only regular model files into the runtime closure.
"""

from __future__ import annotations

import email
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from runtime_manifest import (
    MANIFEST_NAME,
    RUNTIME_OWNER_ROOT,
    RuntimeManifestError,
    artifact_set_sha256,
    inventory_runtime,
    verify_runtime_manifest,
)


PADDLEOCR_VERSION = "3.7.0"
PADDLEX_VERSION = "3.7.2"
PADDLEPADDLE_VERSION = "3.3.1"
PADDLEOCR_WHEEL_SHA256 = "c0f0a81ad4112727f30c6fcf986ac0ef6a120d31ee0991a01fae0357ee32d338"
PADDLEX_WHEEL_SHA256 = "f1678bf650bbaccfd8f0d4e49d0ae631b4685c829fdae6e802ccd90d4fcb9a7f"
PADDLEPADDLE_WHEEL_SHA256 = (
    "9016fc497213e1101261684321fbb31ef5960019ef39cb07ded27bc70e2a9858"
)
RUNTIME_ID = "paddleocr-3.7.0-paddlex-3.7.2-paddle-3.3.1-cpu"
RUNTIME_AUTHORITY_BOUNDARY = (
    "runtime identity and fixity only; no software quality, source-text, or promotion verdict"
)
DEFAULT_RUNTIME_ROOT = RUNTIME_OWNER_ROOT / RUNTIME_ID
DEFAULT_RUNTIME_CACHE = (
    Path("/srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab")
    / RUNTIME_ID
    / "runtime-cache"
)
MODEL_SOURCES = {
    "PP-OCRv5_server_det": {
        "filename": "PP-OCRv5_server_det_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
            "official_inference_model/paddle3.0.0/PP-OCRv5_server_det_infer.tar"
        ),
        "role": "shared-text-detector",
    },
    "latin_PP-OCRv5_mobile_rec": {
        "filename": "latin_PP-OCRv5_mobile_rec_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
            "official_inference_model/paddle3.0.0/latin_PP-OCRv5_mobile_rec_infer.tar"
        ),
        "role": "german-latin-recognizer",
    },
    "eslav_PP-OCRv5_mobile_rec": {
        "filename": "eslav_PP-OCRv5_mobile_rec_infer.tar",
        "url": (
            "https://paddle-model-ecology.bj.bcebos.com/paddlex/"
            "official_inference_model/paddle3.0.0/eslav_PP-OCRv5_mobile_rec_infer.tar"
        ),
        "role": "russian-east-slavic-recognizer",
    },
}
REQUIRED_DISTRIBUTIONS = {
    "paddleocr": PADDLEOCR_VERSION,
    "paddlex": PADDLEX_VERSION,
    "paddlepaddle": PADDLEPADDLE_VERSION,
}
PRINCIPAL_WHEEL_SHA256 = {
    "paddleocr": PADDLEOCR_WHEEL_SHA256,
    "paddlex": PADDLEX_WHEEL_SHA256,
    "paddlepaddle": PADDLEPADDLE_WHEEL_SHA256,
}


class PaddleOcrRuntimeError(RuntimeError):
    """Raised when OCR C acquisition or runtime closure is not exact."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaddleOcrRuntimeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PaddleOcrRuntimeError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_stream(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _run(
    arguments: tuple[str, ...],
    *,
    environment: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        arguments,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        raise PaddleOcrRuntimeError(
            f"command failed ({completed.returncode}): {' '.join(arguments)}: {detail[:1200]}"
        )
    return completed


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata_text(value: object | None) -> str | None:
    """Normalize email metadata values before they cross the JSON boundary."""

    return None if value is None else str(value)


def _wheel_metadata(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_names = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise PaddleOcrRuntimeError(
                    f"wheel {path.name} has {len(metadata_names)} METADATA files"
                )
            metadata_name = metadata_names[0]
            message = email.message_from_bytes(archive.read(metadata_name))
            dist_info_root = metadata_name.rsplit("/", 1)[0]
            license_files = []
            for member in sorted(archive.namelist()):
                if not member.startswith(f"{dist_info_root}/licenses/") or member.endswith("/"):
                    continue
                data = archive.read(member)
                license_files.append(
                    {
                        "member": member,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
    except (OSError, zipfile.BadZipFile) as exc:
        raise PaddleOcrRuntimeError(f"cannot inspect wheel {path}: {exc}") from exc
    name = _metadata_text(message.get("Name"))
    version = _metadata_text(message.get("Version"))
    if not name or not version:
        raise PaddleOcrRuntimeError(f"wheel {path.name} omits Name or Version")
    return {
        "distribution": _normalize_distribution(name),
        "declared_name": name,
        "version": version,
        "filename": path.name,
        "path": path.resolve().as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "license_expression": _metadata_text(message.get("License-Expression")),
        "license": _metadata_text(message.get("License")),
        "license_classifiers": [
            str(value)
            for value in message.get_all("Classifier", [])
            if str(value).startswith("License ::")
        ],
        "license_files": license_files,
        "requires_python": _metadata_text(message.get("Requires-Python")),
        "requires_dist": [str(value) for value in message.get_all("Requires-Dist", [])],
    }


def _inspect_wheels(wheel_cache: Path) -> list[dict[str, Any]]:
    wheel_cache = wheel_cache.resolve()
    wheels = [_wheel_metadata(path) for path in sorted(wheel_cache.glob("*.whl"))]
    if not wheels:
        raise PaddleOcrRuntimeError(f"wheel cache is empty: {wheel_cache}")
    by_distribution: dict[str, dict[str, Any]] = {}
    for wheel in wheels:
        distribution = wheel["distribution"]
        if distribution in by_distribution:
            raise PaddleOcrRuntimeError(f"wheel lock has duplicate distribution {distribution}")
        by_distribution[distribution] = wheel
    for distribution, version in REQUIRED_DISTRIBUTIONS.items():
        wheel = by_distribution.get(distribution)
        if wheel is None or wheel["version"] != version:
            raise PaddleOcrRuntimeError(
                f"wheel lock requires {distribution}=={version}, observed {wheel and wheel['version']}"
            )
        if wheel["sha256"] != PRINCIPAL_WHEEL_SHA256[distribution]:
            raise PaddleOcrRuntimeError(f"principal wheel digest drift: {distribution}")
    for distribution in REQUIRED_DISTRIBUTIONS:
        wheel = by_distribution[distribution]
        license_text = " ".join(
            str(value)
            for value in (
                wheel.get("license_expression"),
                wheel.get("license"),
                *wheel.get("license_classifiers", []),
            )
            if value
        ).lower()
        if "apache" not in license_text and not wheel.get("license_files"):
            raise PaddleOcrRuntimeError(
                f"principal wheel does not expose Apache license evidence: {distribution}"
            )
    return wheels


def _safe_tar_member_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise PaddleOcrRuntimeError(f"unsafe model archive member: {name}")
    return path


def _tar_inventory(path: Path) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    try:
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                member_path = _safe_tar_member_name(member.name)
                if member.isdir():
                    continue
                if not member.isfile():
                    raise PaddleOcrRuntimeError(
                        f"model archive contains non-regular member: {member.name}"
                    )
                stream = archive.extractfile(member)
                if stream is None:
                    raise PaddleOcrRuntimeError(f"cannot read model member: {member.name}")
                with stream:
                    digest = _sha256_stream(stream)
                inventory.append(
                    {
                        "path": member_path.as_posix(),
                        "bytes": member.size,
                        "sha256": digest,
                    }
                )
    except (OSError, tarfile.TarError) as exc:
        raise PaddleOcrRuntimeError(f"cannot inspect model archive {path}: {exc}") from exc
    suffixes = {PurePosixPath(row["path"]).suffix for row in inventory}
    if ".json" not in suffixes or ".pdiparams" not in suffixes or ".yml" not in suffixes:
        raise PaddleOcrRuntimeError(
            f"model archive lacks static-graph JSON, pdiparams, or YAML: {path.name}"
        )
    return inventory


def _inspect_models(model_cache: Path) -> list[dict[str, Any]]:
    model_cache = model_cache.resolve()
    models = []
    for model_name, source in MODEL_SOURCES.items():
        path = model_cache / str(source["filename"])
        if not path.is_file():
            raise PaddleOcrRuntimeError(f"model archive is missing: {path}")
        members = _tar_inventory(path)
        models.append(
            {
                "model_name": model_name,
                "role": source["role"],
                "source_url": source["url"],
                "path": path.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
                "members": members,
                "member_set_sha256": _canonical_sha256(members),
                "license_posture": "official PaddleOCR/PaddleX Apache-2.0 model family",
            }
        )
    return models


def _wheel_set_sha256(wheels: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "distribution": row["distribution"],
                "version": row["version"],
                "filename": row["filename"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
            for row in sorted(wheels, key=lambda item: item["distribution"])
        ]
    )


def _model_set_sha256(models: list[dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "model_name": row["model_name"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "member_set_sha256": row["member_set_sha256"],
            }
            for row in sorted(models, key=lambda item: item["model_name"])
        ]
    )


def freeze_paddle_ocr_acquisition(
    wheel_cache: Path,
    model_cache: Path,
    output_path: Path,
    *,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    """Freeze a complete local PaddleOCR acquisition packet without network."""

    output_path = output_path.resolve()
    wheels = _inspect_wheels(wheel_cache)
    models = _inspect_models(model_cache)
    lock_path = output_path.with_name("requirements.lock.txt")
    lock_lines = [
        f"{row['distribution']}=={row['version']} --hash=sha256:{row['sha256']}"
        for row in sorted(wheels, key=lambda item: item["distribution"])
    ]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("\n".join(lock_lines) + "\n", encoding="utf-8")
    receipts = [path.resolve().as_posix() for path in (owner_receipt_refs or [])]
    for ref in receipts:
        if not Path(ref).is_file():
            raise PaddleOcrRuntimeError(f"owner receipt is missing: {ref}")
    receipt = {
        "schema_version": "tos_paddle_ocr_acquisition_v1",
        "captured_at_utc": _utc_now(),
        "network_performed_by_freezer": False,
        "wheel_cache": wheel_cache.resolve().as_posix(),
        "wheels": wheels,
        "wheel_count": len(wheels),
        "wheel_set_sha256": _wheel_set_sha256(wheels),
        "model_cache": model_cache.resolve().as_posix(),
        "models": models,
        "model_set_sha256": _model_set_sha256(models),
        "requirements_lock_ref": lock_path.as_posix(),
        "requirements_lock_sha256": _sha256_file(lock_path),
        "owner_receipt_refs": receipts,
        "invocation": invocation,
        "rights_posture": (
            "official PaddleOCR/PaddleX Apache-2.0 software and model-family sources; "
            "bounded private research only"
        ),
        "authority_boundary": (
            "software/model acquisition identity only; no OCR quality or source-text verdict"
        ),
    }
    _write_json(output_path, receipt)
    return verify_paddle_ocr_acquisition(output_path)


def verify_paddle_ocr_acquisition(receipt_path: Path) -> dict[str, Any]:
    """Recheck every mutable external byte named by an acquisition receipt."""

    receipt_path = receipt_path.resolve()
    receipt = _load_json(receipt_path)
    if receipt.get("schema_version") != "tos_paddle_ocr_acquisition_v1":
        raise PaddleOcrRuntimeError("unexpected PaddleOCR acquisition schema")
    wheels = _inspect_wheels(Path(receipt["wheel_cache"]))
    if wheels != receipt.get("wheels") or _wheel_set_sha256(wheels) != receipt.get(
        "wheel_set_sha256"
    ):
        raise PaddleOcrRuntimeError("PaddleOCR wheel-set receipt drift")
    models = _inspect_models(Path(receipt["model_cache"]))
    if models != receipt.get("models") or _model_set_sha256(models) != receipt.get(
        "model_set_sha256"
    ):
        raise PaddleOcrRuntimeError("PaddleOCR model-set receipt drift")
    lock_path = Path(receipt["requirements_lock_ref"])
    if not lock_path.is_file() or _sha256_file(lock_path) != receipt.get(
        "requirements_lock_sha256"
    ):
        raise PaddleOcrRuntimeError("PaddleOCR requirements lock drift")
    for ref in receipt.get("owner_receipt_refs", []):
        if not Path(ref).is_file():
            raise PaddleOcrRuntimeError(f"owner receipt is missing: {ref}")
    return receipt


def _runtime_environment(runtime_root: Path) -> dict[str, str]:
    return {
        "PATH": f"{runtime_root / 'bin'}:{runtime_root / 'venv/bin'}:/usr/bin",
        "VIRTUAL_ENV": (runtime_root / "venv").as_posix(),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PADDLE_PDX_MODEL_SOURCE": "BOS",
        "PADDLE_HOME": (DEFAULT_RUNTIME_CACHE / "paddle").as_posix(),
        "PADDLE_PDX_CACHE_HOME": (DEFAULT_RUNTIME_CACHE / "paddlex").as_posix(),
        "HF_HOME": (DEFAULT_RUNTIME_CACHE / "huggingface").as_posix(),
        "XDG_CACHE_HOME": (DEFAULT_RUNTIME_CACHE / "xdg-cache").as_posix(),
        "XDG_DATA_HOME": (DEFAULT_RUNTIME_CACHE / "xdg-data").as_posix(),
    }


def _wrapper_text(command: str) -> str:
    target = (
        '"$runtime_root/venv/bin/paddleocr"'
        if command == "paddleocr"
        else '"$runtime_root/venv/bin/python"'
    )
    return f'''#!/usr/bin/bash
set -euo pipefail
runtime_root="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd -P)"
export VIRTUAL_ENV="$runtime_root/venv"
export PATH="$runtime_root/bin:$runtime_root/venv/bin:/usr/bin"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PADDLE_PDX_MODEL_SOURCE=BOS
export PADDLE_HOME="{DEFAULT_RUNTIME_CACHE}/paddle"
export PADDLE_PDX_CACHE_HOME="{DEFAULT_RUNTIME_CACHE}/paddlex"
export HF_HOME="{DEFAULT_RUNTIME_CACHE}/huggingface"
export XDG_CACHE_HOME="{DEFAULT_RUNTIME_CACHE}/xdg-cache"
export XDG_DATA_HOME="{DEFAULT_RUNTIME_CACHE}/xdg-data"
exec {target} "$@"
'''


def _strip_archive_root(members: list[dict[str, Any]]) -> int:
    first_parts = {PurePosixPath(row["path"]).parts[0] for row in members}
    return 1 if len(first_parts) == 1 else 0


def _extract_model(model: dict[str, Any], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    expected = {row["path"]: row for row in model["members"]}
    strip_count = _strip_archive_root(model["members"])
    observed_targets: set[str] = set()
    with tarfile.open(model["path"], "r:*") as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            source_name = _safe_tar_member_name(member.name).as_posix()
            source_record = expected.get(source_name)
            if source_record is None or not member.isfile():
                raise PaddleOcrRuntimeError(f"model member drift while extracting: {member.name}")
            parts = PurePosixPath(source_name).parts[strip_count:]
            if not parts:
                raise PaddleOcrRuntimeError(f"model member has no extraction target: {member.name}")
            relative = PurePosixPath(*parts)
            output = target.joinpath(*relative.parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise PaddleOcrRuntimeError(f"cannot extract model member: {member.name}")
            with stream, output.open("wb") as destination:
                shutil.copyfileobj(stream, destination)
            if output.stat().st_size != source_record["bytes"] or _sha256_file(output) != source_record[
                "sha256"
            ]:
                raise PaddleOcrRuntimeError(f"extracted model member failed fixity: {member.name}")
            observed_targets.add(relative.as_posix())
    if len(observed_targets) != len(expected):
        raise PaddleOcrRuntimeError(f"model extraction count drift: {model['model_name']}")


def _installed_versions(runtime_root: Path, environment: dict[str, str]) -> dict[str, str]:
    code = (
        "import importlib.metadata,json;"
        f"names={sorted(REQUIRED_DISTRIBUTIONS)!r};"
        "print(json.dumps({n:importlib.metadata.version(n) for n in names},sort_keys=True))"
    )
    completed = _run(
        ((runtime_root / "venv/bin/python").as_posix(), "-c", code),
        environment=environment,
        timeout=60,
    )
    versions = json.loads(completed.stdout)
    if versions != dict(sorted(REQUIRED_DISTRIBUTIONS.items())):
        raise PaddleOcrRuntimeError(f"installed principal versions drift: {versions}")
    return versions


def _model_smoke_text(runtime_root: Path) -> str:
    detector = (runtime_root / "models/PP-OCRv5_server_det").as_posix()
    recognizers = {
        name: (runtime_root / "models" / name).as_posix()
        for name in ("latin_PP-OCRv5_mobile_rec", "eslav_PP-OCRv5_mobile_rec")
    }
    return f'''#!/usr/bin/env python3
from __future__ import annotations

import gc
import json
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from paddleocr import PaddleOCR

detector = {detector!r}
recognizers = {recognizers!r}
with tempfile.TemporaryDirectory() as temporary:
    image_path = Path(temporary) / "synthetic.png"
    image = Image.new("RGB", (640, 160), "white")
    ImageDraw.Draw(image).text((24, 56), "TEST 123", fill="black")
    image.save(image_path)
    results = []
    for model_name, model_dir in recognizers.items():
        pipeline = PaddleOCR(
            ocr_version="PP-OCRv5",
            text_detection_model_name="PP-OCRv5_server_det",
            text_detection_model_dir=detector,
            text_recognition_model_name=model_name,
            text_recognition_model_dir=model_dir,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device="cpu",
            engine="paddle_static",
            enable_mkldnn=False,
            cpu_threads=max(1, int(os.environ.get("OMP_NUM_THREADS", "1"))),
        )
        output = list(pipeline.predict(image_path.as_posix()))
        results.append({{"model_name": model_name, "result_count": len(output)}})
        del pipeline
        gc.collect()
print(json.dumps(results, sort_keys=True))
'''


def build_paddle_ocr_runtime(
    acquisition_receipt_path: Path,
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    python_command: Path = Path("/usr/bin/python3.12"),
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    """Build OCR C's runtime offline from the frozen wheel/model packet."""

    runtime_root = runtime_root.resolve()
    if runtime_root != DEFAULT_RUNTIME_ROOT.resolve() or not runtime_root.is_relative_to(
        RUNTIME_OWNER_ROOT.resolve()
    ):
        raise PaddleOcrRuntimeError(f"runtime root must be exactly {DEFAULT_RUNTIME_ROOT}")
    if runtime_root.exists():
        raise PaddleOcrRuntimeError(f"runtime root already exists: {runtime_root}")
    acquisition = verify_paddle_ocr_acquisition(acquisition_receipt_path)
    runtime_root.mkdir(parents=True, exist_ok=False)
    failure_path = runtime_root / "build-failure.json"
    try:
        environment = os.environ.copy()
        environment.update(
            {
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "PIP_CACHE_DIR": (DEFAULT_RUNTIME_CACHE / "pip").as_posix(),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
        )
        _run(
            (
                python_command.resolve().as_posix(),
                "-m",
                "venv",
                "--copies",
                (runtime_root / "venv").as_posix(),
            ),
            environment=environment,
            timeout=180,
        )
        install = _run(
            (
                (runtime_root / "venv/bin/python").as_posix(),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-cache-dir",
                "--no-compile",
                "--require-hashes",
                "--find-links",
                acquisition["wheel_cache"],
                "--requirement",
                acquisition["requirements_lock_ref"],
            ),
            environment=environment,
            timeout=1800,
        )
        check = _run(
            ((runtime_root / "venv/bin/python").as_posix(), "-m", "pip", "check"),
            environment=environment,
            timeout=120,
        )

        models_root = runtime_root / "models"
        models_root.mkdir()
        for model in acquisition["models"]:
            _extract_model(model, models_root / model["model_name"])

        wrapper_root = runtime_root / "bin"
        wrapper_root.mkdir()
        for command in ("paddleocr", "python"):
            wrapper = wrapper_root / command
            wrapper.write_text(_wrapper_text(command), encoding="utf-8")
            wrapper.chmod(0o755)

        receipt_root = runtime_root / "receipts"
        receipt_root.mkdir()
        acquisition_target = receipt_root / "acquisition.json"
        shutil.copyfile(acquisition_receipt_path.resolve(), acquisition_target)
        lock_target = receipt_root / "requirements.lock.txt"
        shutil.copyfile(acquisition["requirements_lock_ref"], lock_target)
        smoke_path = receipt_root / "model-load-smoke.py"
        smoke_path.write_text(_model_smoke_text(runtime_root), encoding="utf-8")

        runtime_environment = os.environ.copy()
        runtime_environment.update(_runtime_environment(runtime_root))
        installed_versions = _installed_versions(runtime_root, runtime_environment)
        paddle_check = _run(
            (
                (runtime_root / "venv/bin/python").as_posix(),
                "-c",
                "import paddle; print(paddle.__version__); paddle.utils.run_check()",
            ),
            environment=runtime_environment,
            timeout=600,
        )
        cli_help = _run(
            ((runtime_root / "bin/paddleocr").as_posix(), "--help"),
            environment=runtime_environment,
            timeout=180,
        )
        if "ocr" not in cli_help.stdout.lower():
            raise PaddleOcrRuntimeError("PaddleOCR CLI help omits the OCR surface")
        model_smoke = _run(
            ((runtime_root / "bin/python").as_posix(), smoke_path.as_posix()),
            environment=runtime_environment,
            timeout=1800,
        )
        smoke_payload = json.loads(model_smoke.stdout.strip().splitlines()[-1])
        if {row.get("model_name") for row in smoke_payload} != {
            "latin_PP-OCRv5_mobile_rec",
            "eslav_PP-OCRv5_mobile_rec",
        }:
            raise PaddleOcrRuntimeError(f"PaddleOCR model smoke drift: {smoke_payload}")

        build_receipt_path = receipt_root / "build.json"
        _write_json(
            build_receipt_path,
            {
                "schema_version": "tos_paddle_ocr_runtime_build_v1",
                "captured_at_utc": _utc_now(),
                "network_performed_by_builder": False,
                "python_command": python_command.resolve().as_posix(),
                "python_version": _run(
                    ((runtime_root / "venv/bin/python").as_posix(), "--version"),
                    environment=runtime_environment,
                ).stdout.strip(),
                "installed_principal_versions": installed_versions,
                "pip_install_stdout_sha256": hashlib.sha256(
                    install.stdout.encode("utf-8")
                ).hexdigest(),
                "pip_install_stderr_sha256": hashlib.sha256(
                    install.stderr.encode("utf-8")
                ).hexdigest(),
                "pip_check": check.stdout.strip(),
                "paddle_check_stdout": paddle_check.stdout.strip(),
                "paddle_check_stderr_sha256": hashlib.sha256(
                    paddle_check.stderr.encode("utf-8")
                ).hexdigest(),
                "cli_help_sha256": hashlib.sha256(cli_help.stdout.encode("utf-8")).hexdigest(),
                "model_smoke_stdout": model_smoke.stdout.strip(),
                "model_smoke_stderr_sha256": hashlib.sha256(
                    model_smoke.stderr.encode("utf-8")
                ).hexdigest(),
                "model_set_sha256": acquisition["model_set_sha256"],
                "owner_receipt_refs": [
                    path.resolve().as_posix() for path in (owner_receipt_refs or [])
                ],
                "invocation": invocation,
                "boundary": "offline runtime installation and synthetic model-load evidence only",
            },
        )

        roles = {
            "bin/paddleocr": "paddleocr-command-wrapper",
            "bin/python": "runtime-python-wrapper",
            "receipts/acquisition.json": "source-acquisition-receipt",
            "receipts/build.json": "offline-build-receipt",
            "receipts/requirements.lock.txt": "complete-wheel-hash-lock",
            "receipts/model-load-smoke.py": "synthetic-model-load-smoke",
        }
        for model in acquisition["models"]:
            for member in model["members"]:
                parts = PurePosixPath(member["path"]).parts[_strip_archive_root(model["members"]):]
                if parts:
                    roles[(Path("models") / model["model_name"] / Path(*parts)).as_posix()] = model[
                        "role"
                    ]
        artifacts = inventory_runtime(runtime_root, roles=roles)
        wheel_by_name = {row["distribution"]: row for row in acquisition["wheels"]}
        software = [
            {
                "name": "paddleocr",
                "version": PADDLEOCR_VERSION,
                "source_url": "https://pypi.org/project/paddleocr/3.7.0/",
                "source_sha256": wheel_by_name["paddleocr"]["sha256"],
                "license": "Apache-2.0",
            },
            {
                "name": "paddlex",
                "version": PADDLEX_VERSION,
                "source_url": "https://pypi.org/project/paddlex/3.7.2/",
                "source_sha256": wheel_by_name["paddlex"]["sha256"],
                "license": "Apache-2.0",
            },
            {
                "name": "paddlepaddle-cpu",
                "version": PADDLEPADDLE_VERSION,
                "source_url": "https://pypi.org/project/paddlepaddle/3.3.1/",
                "source_sha256": wheel_by_name["paddlepaddle"]["sha256"],
                "license": "Apache-2.0",
            },
        ]
        software.extend(
            {
                "name": model["model_name"],
                "version": "official-inference-model-paddle3.0.0",
                "source_url": model["source_url"],
                "source_sha256": model["sha256"],
                "license": "Apache-2.0",
            }
            for model in acquisition["models"]
        )
        manifest = {
            "schema_version": "tos_foundation_lab_runtime_manifest_v1",
            "runtime_id": RUNTIME_ID,
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "C",
            "status": "verified",
            "created_at_utc": _utc_now(),
            "runtime_root": runtime_root.as_posix(),
            "commands": {
                "paddleocr": (runtime_root / "bin/paddleocr").as_posix(),
                "python": (runtime_root / "bin/python").as_posix(),
            },
            "environment": _runtime_environment(runtime_root),
            "software": software,
            "artifacts": artifacts,
            "artifact_set_sha256": artifact_set_sha256(artifacts),
            "runtime_bytes": sum(row["bytes"] for row in artifacts),
            "licenses": [
                {
                    "subject": "PaddleOCR, PaddleX, PaddlePaddle, and three official OCR models",
                    "spdx": "Apache-2.0",
                    "evidence_ref": "receipts/acquisition.json",
                }
            ],
            "source_receipt_refs": [
                acquisition_target.as_posix(),
                build_receipt_path.as_posix(),
            ],
            "removal_route": {
                "kind": "delete-exact-runtime-tree-after-retention-review",
                "target": runtime_root.as_posix(),
                "requires_operator_confirmation": True,
            },
            "authority_boundary": RUNTIME_AUTHORITY_BOUNDARY,
        }
        manifest_path = runtime_root / MANIFEST_NAME
        _write_json(manifest_path, manifest)
        try:
            return verify_runtime_manifest(
                manifest_path,
                experiment_id="tos-ocr-foundation-v1",
                variant="C",
                required_commands=["paddleocr"],
            )
        except RuntimeManifestError as exc:
            raise PaddleOcrRuntimeError(str(exc)) from exc
    except Exception as exc:
        _write_json(
            failure_path,
            {
                "schema_version": "tos_paddle_ocr_runtime_build_failure_v1",
                "failed_at_utc": _utc_now(),
                "runtime_root": runtime_root.as_posix(),
                "error": str(exc),
                "retention": "preserve-for-diagnosis-until-explicit-cleanup",
            },
        )
        if isinstance(exc, PaddleOcrRuntimeError):
            raise
        raise PaddleOcrRuntimeError(str(exc)) from exc
