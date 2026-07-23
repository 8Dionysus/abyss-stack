#!/usr/bin/env python3
"""Freeze and build Structure Recovery B/C offline runtimes.

Network acquisition is deliberately outside this module. The freezer accepts
only already downloaded wheel/model closures; builders then create removable,
owner-contained runtimes below ``/srv/abyss-machine/runtimes``.
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
from pathlib import Path
from typing import Any

from paddle_ocr_runtime import PRINCIPAL_WHEEL_SHA256
from runtime_manifest import (
    MANIFEST_NAME,
    RUNTIME_OWNER_ROOT,
    artifact_set_sha256,
    inventory_runtime,
    verify_runtime_manifest,
)


DOC_PREFIX = "docling"
PADDLE_PREFIX = "paddle-vl"
DOC_RUNTIME_ID = "docling-2.115.0-heron-8f39ad3-cpu"
PADDLE_RUNTIME_ID = "paddleocr-vl-1.6-structure-ocr-cpu"
DOC_RUNTIME_ROOT = RUNTIME_OWNER_ROOT / DOC_RUNTIME_ID
PADDLE_RUNTIME_ROOT = RUNTIME_OWNER_ROOT / PADDLE_RUNTIME_ID
DOC_CACHE_ROOT = (
    Path("/srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab")
    / "tos-structure-recovery-v1"
    / DOC_RUNTIME_ID
)
PADDLE_CACHE_ROOT = (
    Path("/srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab")
    / "tos-structure-recovery-v1"
    / PADDLE_RUNTIME_ID
)
BASE_PADDLE_MANIFEST = (
    RUNTIME_OWNER_ROOT
    / "paddleocr-3.7.0-paddlex-3.7.2-paddle-3.3.1-cpu"
    / MANIFEST_NAME
)
TESSERACT_MANIFEST = RUNTIME_OWNER_ROOT / "tesseract-5.5.2-fc44" / MANIFEST_NAME

DOC_VERSION = "2.115.0"
DOC_WHEEL_SHA256 = "1a3d9bdf2f82610e97085a1a1b53cf259d1bd7aff97651ff2decc3b2b105123c"
DOC_TORCH_VERSION = "2.10.0+cpu"
DOC_TORCHVISION_VERSION = "0.25.0+cpu"
DOC_FORBIDDEN_ACCELERATOR_DISTRIBUTIONS = ("cuda-", "nvidia-", "triton")
DOC_BUILD_BACKEND_ARTIFACTS = {
    "setuptools-83.0.0-py3-none-any.whl": (
        "29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"
    ),
    "wheel-0.47.0-py3-none-any.whl": (
        "212281cab4dff978f6cedd499cd893e1f620791ca6ff7107cf270781e587eced"
    ),
}
HERON_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
HERON_MODEL_SHA256 = "00333a43451945aaf89db8ca9c0a17e75d1537c17db60fdb91aa95f4c7929e0c"
PADDLE_VL_REVISION = "66317acc4c9fc17bd154591ce650735cd2855f3e"
PADDLE_VL_MODEL_SHA256 = "85a479d506a11e724e7285d395c551be69f41dbc16b6342d3cacfb189aed71db"
PADDLE_LAYOUT_REVISION = "7b48a7566925fa464281f930c58eee04fe2c862a"
PADDLE_LAYOUT_MODEL_SHA256 = (
    "70bd316b0582769ec968829fd1feb1a6a58b7c941b938327e551b6b12b45c137"
)
PADDLE_OCR_EXTRA_REQUIRED_DISTRIBUTIONS = (
    "beautifulsoup4",
    "einops",
    "ftfy",
    "jinja2",
    "latex2mathml",
    "lxml",
    "openpyxl",
    "premailer",
    "regex",
    "scikit-learn",
    "scipy",
    "sentencepiece",
    "tiktoken",
    "tokenizers",
)
PADDLE_FORBIDDEN_ACCELERATOR_DISTRIBUTIONS = ("cuda-", "nvidia-", "triton")
AUTHORITY_BOUNDARY = (
    "runtime identity and fixity only; no software quality, source-text, or promotion verdict"
)


class StructureRuntimeError(RuntimeError):
    """Raised when a Structure B/C acquisition or runtime is not exact."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StructureRuntimeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StructureRuntimeError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _package_record(path: Path) -> dict[str, Any]:
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = [
                    name
                    for name in archive.namelist()
                    if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
                ]
                if len(names) != 1:
                    raise StructureRuntimeError(
                        f"wheel {path.name} has {len(names)} METADATA files"
                    )
                metadata = archive.read(names[0])
            package_kind = "wheel"
        elif path.name.endswith(".tar.gz"):
            with tarfile.open(path, "r:gz") as archive:
                members = [
                    member
                    for member in archive.getmembers()
                    if member.isfile() and member.name.count("/") == 1
                    and member.name.endswith("/PKG-INFO")
                ]
                if len(members) != 1:
                    raise StructureRuntimeError(
                        f"sdist {path.name} has {len(members)} top-level PKG-INFO files"
                    )
                stream = archive.extractfile(members[0])
                if stream is None:
                    raise StructureRuntimeError(f"cannot read sdist metadata: {path.name}")
                metadata = stream.read()
            package_kind = "sdist"
        else:
            raise StructureRuntimeError(f"unsupported package artifact: {path.name}")
        message = email.message_from_bytes(metadata)
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as exc:
        raise StructureRuntimeError(f"cannot inspect package {path}: {exc}") from exc
    name = str(message.get("Name") or "")
    version = str(message.get("Version") or "")
    if not name or not version:
        raise StructureRuntimeError(f"wheel {path.name} omits Name or Version")
    return {
        "distribution": _normalize_distribution(name),
        "version": version,
        "filename": path.name,
        "path": path.resolve().as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "package_kind": package_kind,
        "license_expression": str(message.get("License-Expression") or ""),
        "license": str(message.get("License") or ""),
    }


def _wheel_closure(wheel_cache: Path) -> list[dict[str, Any]]:
    package_paths = list(wheel_cache.resolve().glob("*.whl"))
    package_paths.extend(wheel_cache.resolve().glob("*.tar.gz"))
    rows = [_package_record(path) for path in sorted(package_paths)]
    if not rows:
        raise StructureRuntimeError(f"wheel cache is empty: {wheel_cache}")
    names = [row["distribution"] for row in rows]
    if len(names) != len(set(names)):
        raise StructureRuntimeError("wheel closure contains duplicate distributions")
    docling = next((row for row in rows if row["distribution"] == "docling"), None)
    if (
        docling is None
        or docling["version"] != DOC_VERSION
        or docling["sha256"] != DOC_WHEEL_SHA256
    ):
        raise StructureRuntimeError("Docling principal wheel identity drift")
    forbidden = sorted(
        row["distribution"]
        for row in rows
        if row["distribution"].startswith(DOC_FORBIDDEN_ACCELERATOR_DISTRIBUTIONS)
    )
    if forbidden:
        raise StructureRuntimeError(
            "Docling CPU closure contains accelerator distributions: "
            + ", ".join(forbidden)
        )
    exact_cpu_packages = {
        "torch": DOC_TORCH_VERSION,
        "torchvision": DOC_TORCHVISION_VERSION,
    }
    for distribution, version in exact_cpu_packages.items():
        row = next((item for item in rows if item["distribution"] == distribution), None)
        if row is None or row["version"] != version:
            raise StructureRuntimeError(
                f"Docling CPU closure requires {distribution}=={version}"
            )
    return rows


def _paddle_extra_closure(wheel_cache: Path) -> list[dict[str, Any]]:
    package_paths = sorted(wheel_cache.resolve().glob("*.whl"))
    rows = [_package_record(path) for path in package_paths]
    if not rows:
        raise StructureRuntimeError(f"Paddle OCR extra wheel cache is empty: {wheel_cache}")
    names = [row["distribution"] for row in rows]
    if len(names) != len(set(names)):
        raise StructureRuntimeError("Paddle OCR extra closure contains duplicate distributions")
    missing = sorted(set(PADDLE_OCR_EXTRA_REQUIRED_DISTRIBUTIONS) - set(names))
    if missing:
        raise StructureRuntimeError(
            "Paddle OCR extra closure omits required distributions: " + ", ".join(missing)
        )
    forbidden = sorted(
        row["distribution"]
        for row in rows
        if row["distribution"].startswith(PADDLE_FORBIDDEN_ACCELERATOR_DISTRIBUTIONS)
    )
    if forbidden:
        raise StructureRuntimeError(
            "Paddle OCR extra closure contains accelerator distributions: "
            + ", ".join(forbidden)
        )
    return rows


def _source_inventory(root: Path) -> list[dict[str, Any]]:
    root = root.resolve()
    if not root.is_dir():
        raise StructureRuntimeError(f"model directory is missing: {root}")
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if ".cache" in relative.parts:
            continue
        if path.is_symlink():
            raise StructureRuntimeError(f"model directory contains symlink: {path}")
        if path.is_file():
            rows.append(
                {
                    "relative_path": relative.as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
        elif not path.is_dir():
            raise StructureRuntimeError(f"model directory contains non-regular path: {path}")
    if not rows:
        raise StructureRuntimeError(f"model directory is empty: {root}")
    return rows


def _model_record(
    root: Path,
    *,
    repository: str,
    revision: str,
    principal_file: str,
    principal_sha256: str,
    role: str,
) -> dict[str, Any]:
    inventory = _source_inventory(root)
    principal = next(
        (row for row in inventory if row["relative_path"] == principal_file), None
    )
    if principal is None or principal["sha256"] != principal_sha256:
        raise StructureRuntimeError(f"principal model file identity drift: {repository}")
    return {
        "repository": repository,
        "revision": revision,
        "source_url": f"https://huggingface.co/{repository}/tree/{revision}",
        "local_dir": root.resolve().as_posix(),
        "role": role,
        "principal_file": principal_file,
        "principal_sha256": principal_sha256,
        "files": inventory,
        "file_set_sha256": _canonical_sha256(inventory),
        "license": "Apache-2.0",
    }


def _owner_refs(refs: list[Path] | None) -> list[str]:
    result = [path.resolve().as_posix() for path in (refs or [])]
    for ref in result:
        if not Path(ref).is_file():
            raise StructureRuntimeError(f"owner receipt is missing: {ref}")
    return result


def freeze_docling_acquisition(
    wheel_cache: Path,
    model_dir: Path,
    output_path: Path,
    *,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    wheels = _wheel_closure(wheel_cache)
    model = _model_record(
        model_dir,
        repository="docling-project/docling-layout-heron",
        revision=HERON_REVISION,
        principal_file="model.safetensors",
        principal_sha256=HERON_MODEL_SHA256,
        role="layout-reading-order",
    )
    lock_path = output_path.resolve().with_name("requirements.lock.txt")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        "\n".join(
            f"{row['distribution']}=={row['version']} --hash=sha256:{row['sha256']}"
            for row in sorted(wheels, key=lambda item: item["distribution"])
        )
        + "\n",
        encoding="utf-8",
    )
    tesseract = verify_runtime_manifest(
        TESSERACT_MANIFEST,
        experiment_id="tos-ocr-foundation-v1",
        variant="A",
        required_commands=["tesseract"],
    )
    receipt = {
        "schema_version": "tos_docling_structure_acquisition_v1",
        "captured_at_utc": _utc_now(),
        "network_performed_by_freezer": False,
        "wheel_cache": wheel_cache.resolve().as_posix(),
        "wheels": wheels,
        "wheel_set_sha256": _canonical_sha256(wheels),
        "requirements_lock_ref": lock_path.as_posix(),
        "requirements_lock_sha256": _sha256_file(lock_path),
        "model": model,
        "tesseract_manifest_ref": TESSERACT_MANIFEST.as_posix(),
        "tesseract_manifest_sha256": _sha256_file(TESSERACT_MANIFEST),
        "tesseract_artifact_set_sha256": tesseract["artifact_set_sha256"],
        "owner_receipt_refs": _owner_refs(owner_receipt_refs),
        "invocation": invocation,
        "rights_posture": "Apache-2.0 Docling/Heron and bounded local research",
        "authority_boundary": "software/model acquisition identity only; no structure quality verdict",
    }
    _write_json(output_path.resolve(), receipt)
    return verify_docling_acquisition(output_path)


def verify_docling_acquisition(path: Path) -> dict[str, Any]:
    receipt = _load_json(path.resolve())
    if receipt.get("schema_version") != "tos_docling_structure_acquisition_v1":
        raise StructureRuntimeError("unexpected Docling acquisition schema")
    wheels = _wheel_closure(Path(receipt["wheel_cache"]))
    if wheels != receipt.get("wheels") or _canonical_sha256(wheels) != receipt.get(
        "wheel_set_sha256"
    ):
        raise StructureRuntimeError("Docling wheel closure drift")
    model = _model_record(
        Path(receipt["model"]["local_dir"]),
        repository="docling-project/docling-layout-heron",
        revision=HERON_REVISION,
        principal_file="model.safetensors",
        principal_sha256=HERON_MODEL_SHA256,
        role="layout-reading-order",
    )
    if model != receipt.get("model"):
        raise StructureRuntimeError("Docling model closure drift")
    lock = Path(receipt["requirements_lock_ref"])
    if not lock.is_file() or _sha256_file(lock) != receipt.get("requirements_lock_sha256"):
        raise StructureRuntimeError("Docling requirements lock drift")
    if _sha256_file(TESSERACT_MANIFEST) != receipt.get("tesseract_manifest_sha256"):
        raise StructureRuntimeError("Tesseract source manifest drift")
    _owner_refs([Path(ref) for ref in receipt.get("owner_receipt_refs", [])])
    return receipt


def freeze_paddle_vl_acquisition(
    wheel_cache: Path,
    vl_model_dir: Path,
    layout_model_dir: Path,
    output_path: Path,
    *,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    base = verify_runtime_manifest(
        BASE_PADDLE_MANIFEST,
        experiment_id="tos-ocr-foundation-v1",
        variant="C",
        required_commands=["paddleocr"],
    )
    wheels = _paddle_extra_closure(wheel_cache)
    models = [
        _model_record(
            vl_model_dir,
            repository="PaddlePaddle/PaddleOCR-VL-1.6",
            revision=PADDLE_VL_REVISION,
            principal_file="model.safetensors",
            principal_sha256=PADDLE_VL_MODEL_SHA256,
            role="document-vlm",
        ),
        _model_record(
            layout_model_dir,
            repository="PaddlePaddle/PP-DocLayoutV3",
            revision=PADDLE_LAYOUT_REVISION,
            principal_file="inference.pdiparams",
            principal_sha256=PADDLE_LAYOUT_MODEL_SHA256,
            role="layout-detection",
        ),
    ]
    lock_path = output_path.resolve().with_name("ocr-extra-requirements.lock.txt")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        "\n".join(
            f"{row['distribution']}=={row['version']} --hash=sha256:{row['sha256']}"
            for row in sorted(wheels, key=lambda item: item["distribution"])
        )
        + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "tos_paddle_vl_structure_acquisition_v2",
        "captured_at_utc": _utc_now(),
        "network_performed_by_freezer": False,
        "base_runtime_manifest_ref": BASE_PADDLE_MANIFEST.as_posix(),
        "base_runtime_manifest_sha256": _sha256_file(BASE_PADDLE_MANIFEST),
        "base_runtime_artifact_set_sha256": base["artifact_set_sha256"],
        "ocr_extra_wheel_cache": wheel_cache.resolve().as_posix(),
        "ocr_extra_wheels": wheels,
        "ocr_extra_wheel_set_sha256": _canonical_sha256(wheels),
        "ocr_extra_requirements_lock_ref": lock_path.as_posix(),
        "ocr_extra_requirements_lock_sha256": _sha256_file(lock_path),
        "models": models,
        "model_set_sha256": _canonical_sha256(models),
        "owner_receipt_refs": _owner_refs(owner_receipt_refs),
        "invocation": invocation,
        "rights_posture": "Apache-2.0 PaddleOCR/PaddleX/PaddlePaddle/model sources; bounded local research",
        "authority_boundary": "software/model acquisition identity only; no structure quality verdict",
    }
    _write_json(output_path.resolve(), receipt)
    return verify_paddle_vl_acquisition(output_path)


def verify_paddle_vl_acquisition(path: Path) -> dict[str, Any]:
    receipt = _load_json(path.resolve())
    if receipt.get("schema_version") != "tos_paddle_vl_structure_acquisition_v2":
        raise StructureRuntimeError("unexpected Paddle VLM acquisition schema")
    base = verify_runtime_manifest(
        BASE_PADDLE_MANIFEST,
        experiment_id="tos-ocr-foundation-v1",
        variant="C",
        required_commands=["paddleocr"],
    )
    if (
        _sha256_file(BASE_PADDLE_MANIFEST)
        != receipt.get("base_runtime_manifest_sha256")
        or base["artifact_set_sha256"] != receipt.get("base_runtime_artifact_set_sha256")
    ):
        raise StructureRuntimeError("base PaddleOCR runtime drift")
    wheels = _paddle_extra_closure(Path(receipt["ocr_extra_wheel_cache"]))
    if wheels != receipt.get("ocr_extra_wheels") or _canonical_sha256(
        wheels
    ) != receipt.get("ocr_extra_wheel_set_sha256"):
        raise StructureRuntimeError("Paddle OCR extra wheel closure drift")
    lock = Path(receipt["ocr_extra_requirements_lock_ref"])
    if not lock.is_file() or _sha256_file(lock) != receipt.get(
        "ocr_extra_requirements_lock_sha256"
    ):
        raise StructureRuntimeError("Paddle OCR extra requirements lock drift")
    expected = [
        _model_record(
            Path(receipt["models"][0]["local_dir"]),
            repository="PaddlePaddle/PaddleOCR-VL-1.6",
            revision=PADDLE_VL_REVISION,
            principal_file="model.safetensors",
            principal_sha256=PADDLE_VL_MODEL_SHA256,
            role="document-vlm",
        ),
        _model_record(
            Path(receipt["models"][1]["local_dir"]),
            repository="PaddlePaddle/PP-DocLayoutV3",
            revision=PADDLE_LAYOUT_REVISION,
            principal_file="inference.pdiparams",
            principal_sha256=PADDLE_LAYOUT_MODEL_SHA256,
            role="layout-detection",
        ),
    ]
    if expected != receipt.get("models") or _canonical_sha256(expected) != receipt.get(
        "model_set_sha256"
    ):
        raise StructureRuntimeError("Paddle structure model closure drift")
    _owner_refs([Path(ref) for ref in receipt.get("owner_receipt_refs", [])])
    return receipt


def _run(
    argv: tuple[str, ...],
    *,
    environment: dict[str, str] | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=timeout,
    )
    if completed.returncode:
        detail = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise StructureRuntimeError(
            f"command failed ({completed.returncode}): {' '.join(argv)}: {detail[-1600:]}"
        )
    return completed


def _copy_inventory(source_root: Path, inventory: list[dict[str, Any]], target: Path) -> None:
    target.mkdir(parents=True, exist_ok=False)
    for row in inventory:
        source = source_root / row["relative_path"]
        destination = target / row["relative_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if (
            destination.stat().st_size != row["bytes"]
            or _sha256_file(destination) != row["sha256"]
        ):
            raise StructureRuntimeError(f"copied model artifact drift: {destination}")


def _install_docling_build_backend(
    runtime_python: Path,
    *,
    wheel_cache: Path,
    environment: dict[str, str],
) -> None:
    """Seed the exact offline backend required by the pinned pylatexenc sdist."""
    backend_wheels: list[str] = []
    for filename, expected_sha256 in DOC_BUILD_BACKEND_ARTIFACTS.items():
        artifact = wheel_cache / filename
        if not artifact.is_file() or _sha256_file(artifact) != expected_sha256:
            raise StructureRuntimeError(f"Docling build-backend artifact drift: {artifact}")
        backend_wheels.append(artifact.as_posix())
    _run(
        (
            runtime_python.as_posix(),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            *backend_wheels,
        ),
        environment=environment,
    )


def _write_executable(path: Path, body: str) -> None:
    if path.exists() or path.is_symlink():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _manifest(
    runtime_root: Path,
    *,
    runtime_id: str,
    variant: str,
    commands: dict[str, str],
    environment: dict[str, str],
    software: list[dict[str, str]],
    licenses: list[dict[str, str]],
    source_receipt_refs: list[str],
    roles: dict[str, str],
) -> dict[str, Any]:
    artifacts = inventory_runtime(runtime_root, roles=roles)
    payload = {
        "schema_version": "tos_foundation_lab_runtime_manifest_v1",
        "runtime_id": runtime_id,
        "experiment_id": "tos-structure-recovery-v1",
        "variant": variant,
        "status": "verified",
        "created_at_utc": _utc_now(),
        "runtime_root": runtime_root.as_posix(),
        "commands": commands,
        "environment": environment,
        "software": software,
        "artifacts": artifacts,
        "artifact_set_sha256": artifact_set_sha256(artifacts),
        "runtime_bytes": sum(row["bytes"] for row in artifacts),
        "licenses": licenses,
        "source_receipt_refs": source_receipt_refs,
        "removal_route": {
            "kind": "delete-exact-runtime-tree-after-retention-review",
            "target": runtime_root.as_posix(),
            "requires_operator_confirmation": True,
        },
        "authority_boundary": AUTHORITY_BOUNDARY,
    }
    _write_json(runtime_root / MANIFEST_NAME, payload)
    return verify_runtime_manifest(
        runtime_root / MANIFEST_NAME,
        experiment_id="tos-structure-recovery-v1",
        variant=variant,
        required_commands=list(commands),
    )


def build_docling_runtime(
    acquisition_path: Path,
    *,
    runtime_root: Path = DOC_RUNTIME_ROOT,
    python_command: Path = Path("/usr/bin/python3.12"),
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    receipt = verify_docling_acquisition(acquisition_path)
    runtime_root = runtime_root.resolve()
    if runtime_root != DOC_RUNTIME_ROOT or runtime_root.exists():
        raise StructureRuntimeError(f"Docling runtime root must be new and exact: {DOC_RUNTIME_ROOT}")
    runtime_root.mkdir(parents=True)
    try:
        _run((python_command.as_posix(), "-m", "venv", "--copies", (runtime_root / "venv").as_posix()))
        environment = {
            **os.environ,
            "PIP_CACHE_DIR": (DOC_CACHE_ROOT / "pip").as_posix(),
            "PYTHONNOUSERSITE": "1",
        }
        runtime_python = runtime_root / "venv/bin/python"
        _install_docling_build_backend(
            runtime_python,
            wheel_cache=Path(receipt["wheel_cache"]),
            environment=environment,
        )
        _run(
            (
                runtime_python.as_posix(),
                "-m",
                "pip",
                "install",
                "--no-index",
                "--find-links",
                receipt["wheel_cache"],
                "--require-hashes",
                "--no-build-isolation",
                "-r",
                receipt["requirements_lock_ref"],
            ),
            environment=environment,
            timeout=3600,
        )
        model_target = runtime_root / "models/docling-project--docling-layout-heron"
        _copy_inventory(
            Path(receipt["model"]["local_dir"]),
            receipt["model"]["files"],
            model_target,
        )
        tesseract_source = TESSERACT_MANIFEST.parent
        shutil.copytree(
            tesseract_source,
            runtime_root / "vendor/tesseract",
            ignore=shutil.ignore_patterns(MANIFEST_NAME),
        )
        cache = DOC_CACHE_ROOT / "runtime-cache"
        common = f'''#!/usr/bin/bash
set -euo pipefail
runtime_root="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd -P)"
export VIRTUAL_ENV="$runtime_root/venv"
export PATH="$runtime_root/bin:$runtime_root/venv/bin:/usr/bin"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export DOCLING_ARTIFACTS_PATH="$runtime_root/models"
export HF_HOME="{cache}/huggingface"
export XDG_CACHE_HOME="{cache}/xdg"
'''
        _write_executable(
            runtime_root / "bin/docling",
            common + 'exec "$runtime_root/venv/bin/docling" "$@"\n',
        )
        _write_executable(
            runtime_root / "bin/python",
            common + 'exec "$runtime_root/venv/bin/python" "$@"\n',
        )
        _write_executable(
            runtime_root / "bin/tesseract",
            common
            + 'export TESSDATA_PREFIX="$runtime_root/vendor/tesseract/usr/share/tesseract/tessdata"\n'
            + 'export LD_LIBRARY_PATH="$runtime_root/vendor/tesseract/usr/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"\n'
            + 'exec "$runtime_root/vendor/tesseract/usr/bin/tesseract" "$@"\n',
        )
        versions = _run(
            (
                (runtime_root / "bin/python").as_posix(),
                "-c",
                (
                    "import docling,docling_core;"
                    "from importlib.metadata import version;"
                    "print(version('docling'))"
                ),
            ),
            environment=environment,
        ).stdout.strip()
        if versions != DOC_VERSION:
            raise StructureRuntimeError(f"installed Docling version drift: {versions}")
        _run(((runtime_root / "bin/tesseract").as_posix(), "--version"), timeout=60)
        acquisition_copy = runtime_root / "receipts/acquisition.json"
        acquisition_copy.parent.mkdir(parents=True, exist_ok=False)
        shutil.copy2(acquisition_path.resolve(), acquisition_copy)
        roles = {
            "bin/docling": "operator-command",
            "bin/python": "bridge-command",
            "bin/tesseract": "ocr-fallback-command",
            "receipts/acquisition.json": "acquisition-receipt",
            "models/docling-project--docling-layout-heron/model.safetensors": "layout-model",
        }
        manifest_environment = {
            "PATH": f"{runtime_root / 'bin'}:{runtime_root / 'venv/bin'}:/usr/bin",
            "VIRTUAL_ENV": (runtime_root / "venv").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DOCLING_ARTIFACTS_PATH": (runtime_root / "models").as_posix(),
            "HF_HOME": (cache / "huggingface").as_posix(),
            "XDG_CACHE_HOME": (cache / "xdg").as_posix(),
        }
        refs = [acquisition_copy.as_posix(), *_owner_refs(owner_receipt_refs)]
        return _manifest(
            runtime_root,
            runtime_id=DOC_RUNTIME_ID,
            variant="B",
            commands={
                "docling": (runtime_root / "bin/docling").as_posix(),
                "python": (runtime_root / "bin/python").as_posix(),
                "tesseract": (runtime_root / "bin/tesseract").as_posix(),
            },
            environment=manifest_environment,
            software=[
                {
                    "name": "docling",
                    "version": DOC_VERSION,
                    "source_url": f"https://pypi.org/project/docling/{DOC_VERSION}/",
                    "source_sha256": DOC_WHEEL_SHA256,
                    "license": "MIT",
                },
                {
                    "name": "docling-layout-heron",
                    "version": HERON_REVISION,
                    "source_url": receipt["model"]["source_url"],
                    "source_sha256": HERON_MODEL_SHA256,
                    "license": "Apache-2.0",
                },
                {
                    "name": "tesseract",
                    "version": "5.5.2-fc44",
                    "source_url": "https://github.com/tesseract-ocr/tesseract",
                    "source_sha256": receipt["tesseract_manifest_sha256"],
                    "license": "Apache-2.0",
                },
            ],
            licenses=[
                {"subject": "Docling", "spdx": "MIT", "evidence_ref": acquisition_copy.as_posix()},
                {
                    "subject": "Heron model",
                    "spdx": "Apache-2.0",
                    "evidence_ref": acquisition_copy.as_posix(),
                },
                {
                    "subject": "Tesseract fallback",
                    "spdx": "Apache-2.0",
                    "evidence_ref": TESSERACT_MANIFEST.as_posix(),
                },
            ],
            source_receipt_refs=refs,
            roles=roles,
        )
    except Exception as exc:
        _write_json(
            runtime_root / "build-failure.json",
            {
                "schema_version": "tos_structure_runtime_build_failure_v1",
                "captured_at_utc": _utc_now(),
                "runtime_id": DOC_RUNTIME_ID,
                "invocation": invocation,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise


def build_paddle_vl_runtime(
    acquisition_path: Path,
    *,
    runtime_root: Path = PADDLE_RUNTIME_ROOT,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    receipt = verify_paddle_vl_acquisition(acquisition_path)
    runtime_root = runtime_root.resolve()
    if runtime_root != PADDLE_RUNTIME_ROOT or runtime_root.exists():
        raise StructureRuntimeError(
            f"Paddle VLM runtime root must be new and exact: {PADDLE_RUNTIME_ROOT}"
        )
    base = _load_json(BASE_PADDLE_MANIFEST)
    shutil.copytree(
        BASE_PADDLE_MANIFEST.parent,
        runtime_root,
        copy_function=shutil.copy2,
        ignore=shutil.ignore_patterns(MANIFEST_NAME),
    )
    try:
        install_environment = {
            **os.environ,
            "PIP_CACHE_DIR": (PADDLE_CACHE_ROOT / "pip-cache").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        _run(
            (
                (runtime_root / "venv/bin/python").as_posix(),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--no-index",
                "--find-links",
                receipt["ocr_extra_wheel_cache"],
                "--require-hashes",
                "--requirement",
                receipt["ocr_extra_requirements_lock_ref"],
            ),
            environment=install_environment,
            timeout=900,
        )
        _run(
            (
                (runtime_root / "venv/bin/python").as_posix(),
                "-m",
                "pip",
                "check",
            ),
            environment=install_environment,
            timeout=120,
        )
        verify_runtime_manifest(
            BASE_PADDLE_MANIFEST,
            experiment_id="tos-ocr-foundation-v1",
            variant="C",
            required_commands=["paddleocr"],
        )
        models_root = runtime_root / "models-structure"
        for model in receipt["models"]:
            target_name = (
                "paddleocr-vl-1.6"
                if model["repository"].endswith("PaddleOCR-VL-1.6")
                else "pp-doclayout-v3"
            )
            _copy_inventory(Path(model["local_dir"]), model["files"], models_root / target_name)
        cache = PADDLE_CACHE_ROOT / "runtime-cache"
        common = f'''#!/usr/bin/bash
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
export PADDLE_HOME="{cache}/paddle"
export PADDLE_PDX_CACHE_HOME="{cache}/paddlex"
export HF_HOME="{cache}/huggingface"
export XDG_CACHE_HOME="{cache}/xdg-cache"
export XDG_DATA_HOME="{cache}/xdg-data"
'''
        _write_executable(
            runtime_root / "bin/python",
            common + 'exec "$runtime_root/venv/bin/python" "$@"\n',
        )
        _write_executable(
            runtime_root / "bin/paddleocr",
            common + 'exec "$runtime_root/venv/bin/python" -m paddleocr "$@"\n',
        )
        installed = _run(
            (
                (runtime_root / "bin/python").as_posix(),
                "-c",
                (
                    "from paddleocr import PaddleOCRVL; "
                    "from paddlex.utils.deps import require_extra; "
                    "import paddle; require_extra('ocr'); print(paddle.__version__)"
                ),
            ),
            timeout=120,
        ).stdout.strip()
        if installed != "3.3.1":
            raise StructureRuntimeError(f"installed PaddlePaddle version drift: {installed}")
        acquisition_copy = runtime_root / "receipts/structure-acquisition.json"
        acquisition_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(acquisition_path.resolve(), acquisition_copy)
        lock_copy = runtime_root / "receipts/ocr-extra-requirements.lock.txt"
        shutil.copy2(receipt["ocr_extra_requirements_lock_ref"], lock_copy)
        roles = {
            "bin/python": "bridge-command",
            "bin/paddleocr": "operator-command",
            "receipts/structure-acquisition.json": "acquisition-receipt",
            "receipts/ocr-extra-requirements.lock.txt": "ocr-extra-wheel-hash-lock",
            "models-structure/paddleocr-vl-1.6/model.safetensors": "document-vlm",
            "models-structure/pp-doclayout-v3/inference.pdiparams": "layout-model",
        }
        environment = {
            "PATH": f"{runtime_root / 'bin'}:{runtime_root / 'venv/bin'}:/usr/bin",
            "VIRTUAL_ENV": (runtime_root / "venv").as_posix(),
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PADDLE_PDX_MODEL_SOURCE": "BOS",
            "PADDLE_HOME": (cache / "paddle").as_posix(),
            "PADDLE_PDX_CACHE_HOME": (cache / "paddlex").as_posix(),
            "HF_HOME": (cache / "huggingface").as_posix(),
            "XDG_CACHE_HOME": (cache / "xdg-cache").as_posix(),
            "XDG_DATA_HOME": (cache / "xdg-data").as_posix(),
        }
        software = [dict(row) for row in base["software"][:3]]
        software.extend(
            {
                "name": row["distribution"],
                "version": row["version"],
                "source_url": f"file://{row['path']}",
                "source_sha256": row["sha256"],
                "license": row["license_expression"] or row["license"] or "package-metadata",
            }
            for row in receipt["ocr_extra_wheels"]
        )
        software.extend(
            [
                {
                    "name": "PaddleOCR-VL-1.6",
                    "version": PADDLE_VL_REVISION,
                    "source_url": receipt["models"][0]["source_url"],
                    "source_sha256": PADDLE_VL_MODEL_SHA256,
                    "license": "Apache-2.0",
                },
                {
                    "name": "PP-DocLayoutV3",
                    "version": PADDLE_LAYOUT_REVISION,
                    "source_url": receipt["models"][1]["source_url"],
                    "source_sha256": PADDLE_LAYOUT_MODEL_SHA256,
                    "license": "Apache-2.0",
                },
            ]
        )
        refs = [acquisition_copy.as_posix(), BASE_PADDLE_MANIFEST.as_posix()]
        refs.extend(_owner_refs(owner_receipt_refs))
        return _manifest(
            runtime_root,
            runtime_id=PADDLE_RUNTIME_ID,
            variant="C",
            commands={
                "paddleocr": (runtime_root / "bin/paddleocr").as_posix(),
                "python": (runtime_root / "bin/python").as_posix(),
            },
            environment=environment,
            software=software,
            licenses=[
                {
                    "subject": "PaddleOCR/PaddleX/PaddlePaddle runtime",
                    "spdx": "Apache-2.0",
                    "evidence_ref": BASE_PADDLE_MANIFEST.as_posix(),
                },
                {
                    "subject": "PaddleOCR-VL-1.6 and PP-DocLayoutV3",
                    "spdx": "Apache-2.0",
                    "evidence_ref": acquisition_copy.as_posix(),
                },
            ],
            source_receipt_refs=refs,
            roles=roles,
        )
    except Exception as exc:
        _write_json(
            runtime_root / "build-failure.json",
            {
                "schema_version": "tos_structure_runtime_build_failure_v1",
                "captured_at_utc": _utc_now(),
                "runtime_id": PADDLE_RUNTIME_ID,
                "invocation": invocation,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
