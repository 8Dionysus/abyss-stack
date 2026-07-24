#!/usr/bin/env python3
"""Build OCR A's exact removable Tesseract runtime from cached Fedora RPMs.

This builder performs no network access and no package-manager installation.
Acquisition is a separate owner-gated cache step; the builder verifies the five
frozen RPM identities, extracts them into one `/srv` tree, records host-linked
dependencies, and emits the generic laboratory runtime manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runtime_manifest import (
    MANIFEST_NAME,
    RUNTIME_OWNER_ROOT,
    RuntimeManifestError,
    artifact_set_sha256,
    inventory_runtime,
    verify_runtime_manifest,
)


RUNTIME_ID = "tesseract-5.5.2-fc44"
DEFAULT_RUNTIME_ROOT = RUNTIME_OWNER_ROOT / RUNTIME_ID
EXPECTED_PACKAGES = {
    "tesseract": ("5.5.2-1.fc44", "x86_64", "https://packages.fedoraproject.org/pkgs/tesseract/tesseract/"),
    "tesseract-libs": ("5.5.2-1.fc44", "x86_64", "https://packages.fedoraproject.org/pkgs/tesseract/tesseract-libs/"),
    "tesseract-common": ("5.5.2-1.fc44", "noarch", "https://packages.fedoraproject.org/pkgs/tesseract/tesseract-common/"),
    "tesseract-langpack-deu": ("4.1.0-12.fc44", "noarch", "https://packages.fedoraproject.org/pkgs/tesseract-tessdata/tesseract-langpack-deu/"),
    "tesseract-langpack-rus": ("4.1.0-12.fc44", "noarch", "https://packages.fedoraproject.org/pkgs/tesseract-tessdata/tesseract-langpack-rus/"),
}
RPM_QUERY_FORMAT = "%{NAME}|%{EVR}|%{ARCH}|%{LICENSE}|%{URL}|%{SOURCERPM}"


class TesseractRuntimeError(RuntimeError):
    """Raised when OCR A's isolated runtime cannot be built exactly."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _rpm_metadata(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ("rpm", "-qp", "--qf", RPM_QUERY_FORMAT, path.as_posix()),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise TesseractRuntimeError(f"cannot inspect RPM {path}: {completed.stderr.strip()}")
    fields = completed.stdout.split("|")
    if len(fields) != 6:
        raise TesseractRuntimeError(f"unexpected RPM metadata for {path}")
    signature = subprocess.run(
        ("rpm", "-K", path.as_posix()),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    signature_output = "\n".join(
        part for part in (signature.stdout, signature.stderr) if part
    ).strip()
    # `rpm -K` localizes the final OK token (for example, `ОК` under ru_RU),
    # while its return code remains the machine contract for verification.
    if signature.returncode != 0:
        raise TesseractRuntimeError(
            f"RPM signature verification failed for {path}: {signature_output[:300]}"
        )
    name, evr, arch, license_name, upstream_url, source_rpm = fields
    return {
        "name": name,
        "version": evr,
        "arch": arch,
        "license": license_name,
        "upstream_url": upstream_url,
        "source_rpm": source_rpm,
        "cached_path": path.resolve().as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "rpm_signature_verification": signature_output,
    }


def inspect_frozen_rpms(rpm_cache: Path) -> list[dict[str, Any]]:
    rpm_cache = rpm_cache.resolve()
    records: list[dict[str, Any]] = []
    for path in sorted(rpm_cache.glob("*.rpm")):
        record = _rpm_metadata(path)
        if record["name"] in EXPECTED_PACKAGES:
            records.append(record)
    by_name = {record["name"]: record for record in records}
    if set(by_name) != set(EXPECTED_PACKAGES) or len(records) != len(EXPECTED_PACKAGES):
        missing = sorted(set(EXPECTED_PACKAGES) - set(by_name))
        extra_or_duplicate = sorted(record["name"] for record in records if record["name"] not in EXPECTED_PACKAGES)
        raise TesseractRuntimeError(
            f"cached RPM set is not the exact five-package lock; missing={missing}, unexpected={extra_or_duplicate}"
        )
    for name, (version, arch, _) in EXPECTED_PACKAGES.items():
        record = by_name[name]
        if (record["version"], record["arch"]) != (version, arch):
            raise TesseractRuntimeError(
                f"RPM identity drift for {name}: {(record['version'], record['arch'])} != {(version, arch)}"
            )
        if record["license"] != "Apache-2.0":
            raise TesseractRuntimeError(f"unexpected license for {name}: {record['license']}")
    return [by_name[name] for name in EXPECTED_PACKAGES]


def _extract_rpm(rpm_path: Path, destination: Path) -> dict[str, Any]:
    rpm2cpio = shutil.which("rpm2cpio")
    cpio = shutil.which("cpio")
    if rpm2cpio is None or cpio is None:
        raise TesseractRuntimeError("rpm2cpio and cpio are required")
    producer = subprocess.Popen((rpm2cpio, rpm_path.as_posix()), stdout=subprocess.PIPE)
    assert producer.stdout is not None
    consumer = subprocess.run(
        (cpio, "-idm", "--quiet", "--no-absolute-filenames"),
        stdin=producer.stdout,
        cwd=destination,
        check=False,
        capture_output=True,
        timeout=180,
    )
    producer.stdout.close()
    producer_returncode = producer.wait(timeout=30)
    if producer_returncode != 0 or consumer.returncode != 0:
        raise TesseractRuntimeError(
            f"RPM extraction failed for {rpm_path.name}: rpm2cpio={producer_returncode}, "
            f"cpio={consumer.returncode}, stderr={consumer.stderr.decode(errors='replace')[:300]}"
        )
    return {
        "rpm": rpm_path.name,
        "rpm2cpio_returncode": producer_returncode,
        "cpio_returncode": consumer.returncode,
        "cpio_stdout_sha256": hashlib.sha256(consumer.stdout).hexdigest(),
        "cpio_stderr_sha256": hashlib.sha256(consumer.stderr).hexdigest(),
    }


def _wrapper_text() -> str:
    return """#!/usr/bin/bash
set -euo pipefail
runtime_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export TESSDATA_PREFIX="$runtime_root/usr/share/tesseract/tessdata"
export LD_LIBRARY_PATH="$runtime_root/usr/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$runtime_root/usr/bin/tesseract" "$@"
"""


def _dependency_receipt(runtime_root: Path) -> dict[str, Any]:
    wrapper = runtime_root / "bin/tesseract"
    environment = os.environ.copy()
    environment.update(
        {
            "TESSDATA_PREFIX": (runtime_root / "usr/share/tesseract/tessdata").as_posix(),
            "LD_LIBRARY_PATH": (runtime_root / "usr/lib64").as_posix(),
            "LC_ALL": "C.UTF-8",
        }
    )
    version = subprocess.run(
        (wrapper.as_posix(), "--version"),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    combined = "\n".join(part for part in (version.stdout, version.stderr) if part).strip()
    if version.returncode != 0 or "tesseract 5.5.2" not in combined.lower():
        raise TesseractRuntimeError(f"runtime smoke failed: {combined[:500]}")
    ldd = subprocess.run(
        ("ldd", (runtime_root / "usr/bin/tesseract").as_posix()),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )
    if ldd.returncode != 0 or "not found" in ldd.stdout:
        raise TesseractRuntimeError(f"runtime dependency resolution failed: {ldd.stdout[:700]}")
    dependencies: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for line in ldd.stdout.splitlines():
        match = re.search(r"(?:=>\s+)?(/[^ ]+)", line)
        if match is None:
            continue
        dependency_path = Path(match.group(1))
        if not dependency_path.is_file():
            continue
        resolved = dependency_path.resolve()
        key = resolved.as_posix()
        if key in seen_paths:
            continue
        seen_paths.add(key)
        package = subprocess.run(
            ("rpm", "-qf", "--qf", "%{NAME}|%{EVR}|%{ARCH}", key),
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        dependencies.append(
            {
                "resolved_path": key,
                "inside_runtime": _within(resolved, runtime_root),
                "sha256": _sha256_file(resolved),
                "bytes": resolved.stat().st_size,
                "rpm_owner": package.stdout if package.returncode == 0 else None,
            }
        )
    return {
        "schema_version": "tos_tesseract_runtime_dependency_receipt_v1",
        "captured_at_utc": _utc_now(),
        "version_command": ["bin/tesseract", "--version"],
        "version_output": combined,
        "ldd_command": ["ldd", "usr/bin/tesseract"],
        "ldd_output": ldd.stdout,
        "dependencies": dependencies,
        "boundary": "host-linked dependency snapshot; not a claim of cross-host portability",
    }


def build_tesseract_runtime(
    rpm_cache: Path,
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    runtime_root = runtime_root.resolve()
    if runtime_root != DEFAULT_RUNTIME_ROOT.resolve() or not _within(runtime_root, RUNTIME_OWNER_ROOT):
        raise TesseractRuntimeError(f"runtime root must be exactly {DEFAULT_RUNTIME_ROOT}")
    if runtime_root.exists():
        raise TesseractRuntimeError(f"runtime root already exists: {runtime_root}")
    records = inspect_frozen_rpms(rpm_cache)
    runtime_root.mkdir(parents=True, exist_ok=False)
    failure_path = runtime_root / "build-failure.json"
    try:
        extraction = [
            _extract_rpm(Path(record["cached_path"]), runtime_root) for record in records
        ]
        real_binary = runtime_root / "usr/bin/tesseract"
        if not real_binary.is_file():
            raise TesseractRuntimeError("extracted runtime has no usr/bin/tesseract")
        for language in ("deu", "rus"):
            traineddata = runtime_root / f"usr/share/tesseract/tessdata/{language}.traineddata"
            if not traineddata.is_file():
                raise TesseractRuntimeError(f"extracted runtime has no {language}.traineddata")
        wrapper = runtime_root / "bin/tesseract"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text(_wrapper_text(), encoding="utf-8")
        wrapper.chmod(0o755)

        acquisition_path = runtime_root / "receipts/acquisition.json"
        _write_json(
            acquisition_path,
            {
                "schema_version": "tos_tesseract_rpm_acquisition_receipt_v1",
                "captured_at_utc": _utc_now(),
                "network_performed_by_builder": False,
                "cache_root": rpm_cache.resolve().as_posix(),
                "packages": records,
                "extraction": extraction,
                "owner_receipt_refs": [
                    path.resolve().as_posix() for path in (owner_receipt_refs or [])
                ],
                "invocation": invocation,
                "boundary": "cached Fedora RPM identity and extraction evidence only",
            },
        )
        dependency_path = runtime_root / "receipts/dependencies.json"
        _write_json(dependency_path, _dependency_receipt(runtime_root))

        roles = {
            "bin/tesseract": "command-wrapper",
            "usr/bin/tesseract": "tesseract-command",
            "usr/share/tesseract/tessdata/deu.traineddata": "german-language-model",
            "usr/share/tesseract/tessdata/rus.traineddata": "russian-language-model",
            "receipts/acquisition.json": "source-acquisition-receipt",
            "receipts/dependencies.json": "host-dependency-receipt",
        }
        artifacts = inventory_runtime(runtime_root, roles=roles)
        software = []
        for record in records:
            _, _, source_url = EXPECTED_PACKAGES[record["name"]]
            software.append(
                {
                    "name": record["name"],
                    "version": record["version"],
                    "source_url": source_url,
                    "source_sha256": record["sha256"],
                    "license": record["license"],
                }
            )
        manifest = {
            "schema_version": "tos_foundation_lab_runtime_manifest_v1",
            "runtime_id": RUNTIME_ID,
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "A",
            "status": "verified",
            "created_at_utc": _utc_now(),
            "runtime_root": runtime_root.as_posix(),
            "commands": {"tesseract": wrapper.as_posix()},
            "environment": {
                "PATH": f"{runtime_root / 'bin'}:/usr/bin",
                "LD_LIBRARY_PATH": (runtime_root / "usr/lib64").as_posix(),
                "TESSDATA_PREFIX": (runtime_root / "usr/share/tesseract/tessdata").as_posix(),
            },
            "software": software,
            "artifacts": artifacts,
            "artifact_set_sha256": artifact_set_sha256(artifacts),
            "runtime_bytes": sum(row["bytes"] for row in artifacts),
            "licenses": [
                {
                    "subject": "Tesseract runtime and German/Russian traineddata RPM set",
                    "spdx": "Apache-2.0",
                    "evidence_ref": "receipts/acquisition.json#packages",
                }
            ],
            "source_receipt_refs": [
                acquisition_path.as_posix(),
                dependency_path.as_posix(),
            ],
            "removal_route": {
                "kind": "delete-exact-runtime-tree-after-retention-review",
                "target": runtime_root.as_posix(),
                "requires_operator_confirmation": True,
            },
            "authority_boundary": "runtime identity and fixity only; no software quality, source-text, or promotion verdict",
        }
        manifest_path = runtime_root / MANIFEST_NAME
        _write_json(manifest_path, manifest)
        try:
            return verify_runtime_manifest(
                manifest_path,
                experiment_id="tos-ocr-foundation-v1",
                variant="A",
                required_commands=["tesseract"],
            )
        except RuntimeManifestError as exc:
            raise TesseractRuntimeError(str(exc)) from exc
    except Exception as exc:
        _write_json(
            failure_path,
            {
                "schema_version": "tos_tesseract_runtime_build_failure_v1",
                "failed_at_utc": _utc_now(),
                "runtime_root": runtime_root.as_posix(),
                "error": str(exc),
                "retention": "preserve-for-diagnosis-until-explicit-cleanup",
            },
        )
        if isinstance(exc, TesseractRuntimeError):
            raise
        raise TesseractRuntimeError(str(exc)) from exc
