#!/usr/bin/env python3
"""Freeze and build OCR B's exact Kraken/Party CPU runtime.

Network acquisition is deliberately outside this module.  The freezer checks
an already cached Party source checkout, Zenodo record, model, and resolved
wheel directory and emits a complete hash lock.  The builder then creates one
Python 3.12 runtime using only that lock and copies the model into the runtime
closure.
"""

from __future__ import annotations

import email
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import zipfile
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


PARTY_COMMIT = "c2589b1b515ed690f883c6afaef6c01ce29bf72d"
PARTY_VERSION = "0.0.0.post492+gc2589b1"
PARTY_MODEL_DOI = "10.5281/zenodo.20642057"
PARTY_MODEL_BYTES = 518_329_816
PARTY_MODEL_MD5 = "cf165e67061d492b72f600a6a72b7c61"
PARTY_MODEL_SHA256 = "d6f3c2273687a79dd4852c4cfe63ec4c9e75a2a148fe02a8b787ab6afec236aa"
KRAKEN_VERSION = "7.0.2"
KRAKEN_WHEEL_SHA256 = "5882392e9e4ffdb69bf582483ce0d238017d0e8ad61b0ada38b97d2504e9bb21"
LIGHTNING_VERSION = "2.6.1"
FORBIDDEN_LIGHTNING_VERSIONS = {"2.6.2", "2.6.3"}
TORCH_VERSION = "2.10.0+cpu"
RUNTIME_ID = "kraken-7.0.2-party-c2589b1"
DEFAULT_RUNTIME_ROOT = RUNTIME_OWNER_ROOT / RUNTIME_ID
DEFAULT_RUNTIME_CACHE = (
    Path("/srv/abyss-machine/cache/ai/tree-of-sophia-foundation-lab")
    / RUNTIME_ID
    / "runtime-cache"
)
REQUIRED_DISTRIBUTIONS = {
    "kraken": KRAKEN_VERSION,
    "party": PARTY_VERSION,
    "lightning": LIGHTNING_VERSION,
    "pytorch-lightning": LIGHTNING_VERSION,
    "lightning-fabric": LIGHTNING_VERSION,
    "torch": TORCH_VERSION,
}


class KrakenPartyRuntimeError(RuntimeError):
    """Raised when OCR B acquisition or runtime closure is not exact."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KrakenPartyRuntimeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise KrakenPartyRuntimeError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: object) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _run(
    arguments: tuple[str, ...],
    *,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        raise KrakenPartyRuntimeError(
            f"command failed ({completed.returncode}): {' '.join(arguments)}: {detail[:800]}"
        )
    return completed


def _normalize_distribution(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wheel_metadata(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as archive:
            metadata_names = [
                name
                for name in archive.namelist()
                if name.count("/") == 1 and name.endswith(".dist-info/METADATA")
            ]
            if len(metadata_names) != 1:
                raise KrakenPartyRuntimeError(
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
        raise KrakenPartyRuntimeError(f"cannot inspect wheel {path}: {exc}") from exc
    name = message.get("Name")
    version = message.get("Version")
    if not name or not version:
        raise KrakenPartyRuntimeError(f"wheel {path.name} omits Name or Version")
    return {
        "distribution": _normalize_distribution(name),
        "declared_name": name,
        "version": version,
        "filename": path.name,
        "path": path.resolve().as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
        "license_expression": message.get("License-Expression"),
        "license": message.get("License"),
        "license_classifiers": [
            value
            for value in message.get_all("Classifier", [])
            if value.startswith("License ::")
        ],
        "license_files": license_files,
        "requires_python": message.get("Requires-Python"),
        "requires_dist": message.get_all("Requires-Dist", []),
    }


def _inspect_party_source(source: Path) -> dict[str, Any]:
    source = source.resolve()
    head = _run(("git", "-C", source.as_posix(), "rev-parse", "HEAD")).stdout.strip()
    if head != PARTY_COMMIT:
        raise KrakenPartyRuntimeError(f"Party source commit drift: {head}")
    status = _run(
        ("git", "-C", source.as_posix(), "status", "--porcelain", "--untracked-files=all")
    ).stdout
    if status.strip():
        raise KrakenPartyRuntimeError(f"Party source checkout is dirty: {status[:500]}")
    tree = _run(("git", "-C", source.as_posix(), "rev-parse", "HEAD^{tree}")).stdout.strip()
    license_path = source / "LICENSE"
    if not license_path.is_file() or "Apache License" not in license_path.read_text(
        encoding="utf-8", errors="replace"
    ):
        raise KrakenPartyRuntimeError("Party source does not carry the expected Apache license")
    return {
        "repository": "https://github.com/mittagessen/party",
        "path": source.as_posix(),
        "commit": head,
        "tree": tree,
        "license": "Apache-2.0",
        "license_sha256": _sha256_file(license_path),
        "clean_checkout": True,
    }


def _safetensors_metadata(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            header_bytes = struct.unpack("<Q", handle.read(8))[0]
            if header_bytes <= 0 or header_bytes > 16 * 1024 * 1024:
                raise KrakenPartyRuntimeError("Party model has an implausible safetensors header")
            header = json.loads(handle.read(header_bytes))
    except (OSError, struct.error, json.JSONDecodeError) as exc:
        raise KrakenPartyRuntimeError(f"cannot inspect Party safetensors header: {exc}") from exc
    metadata = header.get("__metadata__", {})
    if not isinstance(metadata, dict) or "kraken_meta" not in metadata:
        raise KrakenPartyRuntimeError("Party model omits kraken_meta")
    try:
        kraken_meta = json.loads(metadata["kraken_meta"])
    except (TypeError, json.JSONDecodeError) as exc:
        raise KrakenPartyRuntimeError("Party model kraken_meta is not valid JSON") from exc
    models = list(kraken_meta.values()) if isinstance(kraken_meta, dict) else []
    if len(models) != 1 or models[0].get("_model") != "PartyModel":
        raise KrakenPartyRuntimeError("Party model header does not identify one PartyModel")
    if models[0].get("model_variant") != "base" or models[0].get("image_size") != [2560, 1920]:
        raise KrakenPartyRuntimeError("Party model architecture metadata drift")
    return {
        "header_bytes": header_bytes,
        "tensor_count": len(header) - int("__metadata__" in header),
        "kraken_meta": kraken_meta,
    }


def _inspect_model(model_path: Path, zenodo_record_path: Path) -> dict[str, Any]:
    model_path = model_path.resolve()
    zenodo_record_path = zenodo_record_path.resolve()
    record = _load_json(zenodo_record_path)
    files = {row.get("key"): row for row in record.get("files", []) if isinstance(row, dict)}
    remote = files.get("model.safetensors", {})
    if (
        record.get("id") != 20642057
        or record.get("doi") != PARTY_MODEL_DOI
        or record.get("metadata", {}).get("license", {}).get("id") != "apache2.0"
        or remote.get("size") != PARTY_MODEL_BYTES
        or remote.get("checksum") != f"md5:{PARTY_MODEL_MD5}"
    ):
        raise KrakenPartyRuntimeError("Zenodo Party v4 record identity drift")
    if not model_path.is_file() or model_path.stat().st_size != PARTY_MODEL_BYTES:
        raise KrakenPartyRuntimeError("Party model byte count drift")
    md5 = _md5_file(model_path)
    sha256 = _sha256_file(model_path)
    if md5 != PARTY_MODEL_MD5 or sha256 != PARTY_MODEL_SHA256:
        raise KrakenPartyRuntimeError("Party model digest drift")
    return {
        "doi": PARTY_MODEL_DOI,
        "record_url": "https://zenodo.org/records/20642057",
        "record_path": zenodo_record_path.as_posix(),
        "record_sha256": _sha256_file(zenodo_record_path),
        "path": model_path.as_posix(),
        "bytes": PARTY_MODEL_BYTES,
        "source_md5": md5,
        "sha256": sha256,
        "license": "Apache-2.0",
        "safetensors": _safetensors_metadata(model_path),
    }


def _inspect_wheels(wheel_cache: Path) -> list[dict[str, Any]]:
    wheel_cache = wheel_cache.resolve()
    wheels = [_wheel_metadata(path) for path in sorted(wheel_cache.glob("*.whl"))]
    if not wheels:
        raise KrakenPartyRuntimeError(f"wheel cache is empty: {wheel_cache}")
    by_distribution: dict[str, dict[str, Any]] = {}
    for wheel in wheels:
        distribution = wheel["distribution"]
        if distribution in by_distribution:
            raise KrakenPartyRuntimeError(f"wheel lock has duplicate distribution {distribution}")
        by_distribution[distribution] = wheel
    for distribution, version in REQUIRED_DISTRIBUTIONS.items():
        wheel = by_distribution.get(distribution)
        if wheel is None or wheel["version"] != version:
            raise KrakenPartyRuntimeError(
                f"wheel lock requires {distribution}=={version}, observed {wheel and wheel['version']}"
            )
    if by_distribution["kraken"]["sha256"] != KRAKEN_WHEEL_SHA256:
        raise KrakenPartyRuntimeError("Kraken 7.0.2 wheel digest drift")
    expected_licenses = {
        "kraken": "Apache-2.0",
        "party": "Apache-2.0",
        "lightning": "Apache-2.0",
        "pytorch-lightning": "Apache-2.0",
        "lightning-fabric": "Apache-2.0",
        "torch": "BSD-3-Clause",
    }
    for distribution, expected in expected_licenses.items():
        wheel = by_distribution[distribution]
        declared = wheel.get("license_expression") or wheel.get("license")
        if declared != expected:
            raise KrakenPartyRuntimeError(
                f"principal wheel license drift for {distribution}: {declared!r}"
            )
    for distribution in ("lightning", "pytorch-lightning", "lightning-fabric"):
        if by_distribution[distribution]["version"] in FORBIDDEN_LIGHTNING_VERSIONS:
            raise KrakenPartyRuntimeError(f"compromised {distribution} wheel is forbidden")
    return wheels


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


def freeze_kraken_party_acquisition(
    wheel_cache: Path,
    party_source: Path,
    model_path: Path,
    zenodo_record_path: Path,
    output_path: Path,
    *,
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    """Freeze a complete local acquisition packet without network access."""

    output_path = output_path.resolve()
    source = _inspect_party_source(party_source)
    model = _inspect_model(model_path, zenodo_record_path)
    wheels = _inspect_wheels(wheel_cache)
    lock_path = output_path.with_name("requirements.lock.txt")
    lock_lines = [
        f"{row['distribution']}=={row['version']} --hash=sha256:{row['sha256']}"
        for row in sorted(wheels, key=lambda item: item["distribution"])
    ]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("\n".join(lock_lines) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": "tos_kraken_party_acquisition_v1",
        "captured_at_utc": _utc_now(),
        "network_performed_by_freezer": False,
        "party_source": source,
        "model": model,
        "wheel_cache": wheel_cache.resolve().as_posix(),
        "wheels": wheels,
        "wheel_count": len(wheels),
        "wheel_set_sha256": _wheel_set_sha256(wheels),
        "requirements_lock_ref": lock_path.as_posix(),
        "requirements_lock_sha256": _sha256_file(lock_path),
        "security_pins": {
            "lightning": LIGHTNING_VERSION,
            "pytorch-lightning": LIGHTNING_VERSION,
            "lightning-fabric": LIGHTNING_VERSION,
            "forbidden_versions": sorted(FORBIDDEN_LIGHTNING_VERSIONS),
            "advisory": "https://github.com/Lightning-AI/pytorch-lightning/security/advisories/GHSA-w37p-236h-pfx3",
        },
        "owner_receipt_refs": [
            path.resolve().as_posix() for path in (owner_receipt_refs or [])
        ],
        "invocation": invocation,
        "authority_boundary": "software/model acquisition identity only; no OCR quality or source-text verdict",
    }
    for ref in receipt["owner_receipt_refs"]:
        if not Path(ref).is_file():
            raise KrakenPartyRuntimeError(f"owner receipt is missing: {ref}")
    _write_json(output_path, receipt)
    return verify_kraken_party_acquisition(output_path)


def verify_kraken_party_acquisition(receipt_path: Path) -> dict[str, Any]:
    """Recheck every mutable external byte named by an acquisition receipt."""

    receipt_path = receipt_path.resolve()
    receipt = _load_json(receipt_path)
    if receipt.get("schema_version") != "tos_kraken_party_acquisition_v1":
        raise KrakenPartyRuntimeError("unexpected Kraken/Party acquisition schema")
    source = _inspect_party_source(Path(receipt["party_source"]["path"]))
    if source != receipt.get("party_source"):
        raise KrakenPartyRuntimeError("Party source receipt drift")
    model = _inspect_model(
        Path(receipt["model"]["path"]), Path(receipt["model"]["record_path"])
    )
    if model != receipt.get("model"):
        raise KrakenPartyRuntimeError("Party model receipt drift")
    wheels = _inspect_wheels(Path(receipt["wheel_cache"]))
    if wheels != receipt.get("wheels") or _wheel_set_sha256(wheels) != receipt.get(
        "wheel_set_sha256"
    ):
        raise KrakenPartyRuntimeError("wheel set receipt drift")
    lock_path = Path(receipt["requirements_lock_ref"])
    if not lock_path.is_file() or _sha256_file(lock_path) != receipt.get(
        "requirements_lock_sha256"
    ):
        raise KrakenPartyRuntimeError("requirements lock drift")
    for ref in receipt.get("owner_receipt_refs", []):
        if not Path(ref).is_file():
            raise KrakenPartyRuntimeError(f"owner receipt is missing: {ref}")
    return receipt


def _wrapper_text(command: str) -> str:
    if command == "party":
        target = '"$runtime_root/venv/bin/python" "$runtime_root/lib/party_offline_cli.py"'
    else:
        target = f'"$runtime_root/venv/bin/{command}"'
    return f"""#!/usr/bin/bash
set -euo pipefail
runtime_root="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd -P)"
export VIRTUAL_ENV="$runtime_root/venv"
export PATH="$runtime_root/bin:$runtime_root/venv/bin:/usr/bin"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export PYTHONHASHSEED=0
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HOME="{DEFAULT_RUNTIME_CACHE}/huggingface"
export TORCH_HOME="{DEFAULT_RUNTIME_CACHE}/torch"
export XDG_CACHE_HOME="{DEFAULT_RUNTIME_CACHE}/xdg-cache"
export XDG_DATA_HOME="{DEFAULT_RUNTIME_CACHE}/xdg-data"
export TORCHINDUCTOR_CACHE_DIR="{DEFAULT_RUNTIME_CACHE}/torchinductor"
exec {target} "$@"
"""


def _party_offline_bridge_text() -> str:
    return '''#!/usr/bin/env python3
"""Run exact Party code while suppressing redundant pretrained initialization."""
from __future__ import annotations

import os

if os.environ.get("HF_HUB_OFFLINE") != "1":
    raise RuntimeError("Party offline adapter requires HF_HUB_OFFLINE=1")

from party.party import PartyModel

_original_init = PartyModel.__init__


def _offline_init(self, **kwargs):
    if kwargs.get("pretrained") not in (None, False):
        raise RuntimeError("Party model metadata requested external pretrained initialization")
    kwargs["pretrained"] = False
    _original_init(self, **kwargs)


PartyModel.__init__ = _offline_init

if __name__ == "__main__":
    from party.cli import cli
    cli()
'''


def _runtime_environment(runtime_root: Path) -> dict[str, str]:
    return {
        "PATH": f"{runtime_root / 'bin'}:{runtime_root / 'venv/bin'}:/usr/bin",
        "VIRTUAL_ENV": (runtime_root / "venv").as_posix(),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_HOME": (DEFAULT_RUNTIME_CACHE / "huggingface").as_posix(),
        "TORCH_HOME": (DEFAULT_RUNTIME_CACHE / "torch").as_posix(),
        "XDG_CACHE_HOME": (DEFAULT_RUNTIME_CACHE / "xdg-cache").as_posix(),
        "XDG_DATA_HOME": (DEFAULT_RUNTIME_CACHE / "xdg-data").as_posix(),
        "TORCHINDUCTOR_CACHE_DIR": (DEFAULT_RUNTIME_CACHE / "torchinductor").as_posix(),
    }


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
        raise KrakenPartyRuntimeError(f"installed principal versions drift: {versions}")
    return versions


def build_kraken_party_runtime(
    acquisition_receipt_path: Path,
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    python_command: Path = Path("/usr/bin/python3.12"),
    owner_receipt_refs: list[Path] | None = None,
    invocation: list[str],
) -> dict[str, Any]:
    """Build OCR B's runtime offline from the frozen wheel/model packet."""

    runtime_root = runtime_root.resolve()
    if runtime_root != DEFAULT_RUNTIME_ROOT.resolve() or not runtime_root.is_relative_to(
        RUNTIME_OWNER_ROOT.resolve()
    ):
        raise KrakenPartyRuntimeError(f"runtime root must be exactly {DEFAULT_RUNTIME_ROOT}")
    if runtime_root.exists():
        raise KrakenPartyRuntimeError(f"runtime root already exists: {runtime_root}")
    acquisition = verify_kraken_party_acquisition(acquisition_receipt_path)
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

        model_target = runtime_root / "models/model.safetensors"
        model_target.parent.mkdir(parents=True)
        shutil.copyfile(acquisition["model"]["path"], model_target)
        if (
            model_target.stat().st_size != PARTY_MODEL_BYTES
            or _sha256_file(model_target) != PARTY_MODEL_SHA256
        ):
            raise KrakenPartyRuntimeError("copied Party model failed closure check")

        wrapper_root = runtime_root / "bin"
        wrapper_root.mkdir()
        bridge_root = runtime_root / "lib"
        bridge_root.mkdir()
        party_bridge = bridge_root / "party_offline_cli.py"
        party_bridge.write_text(_party_offline_bridge_text(), encoding="utf-8")
        party_bridge.chmod(0o755)
        for command in ("kraken", "party"):
            wrapper = wrapper_root / command
            wrapper.write_text(_wrapper_text(command), encoding="utf-8")
            wrapper.chmod(0o755)

        receipt_root = runtime_root / "receipts"
        receipt_root.mkdir()
        acquisition_target = receipt_root / "acquisition.json"
        shutil.copyfile(acquisition_receipt_path.resolve(), acquisition_target)
        lock_target = receipt_root / "requirements.lock.txt"
        shutil.copyfile(acquisition["requirements_lock_ref"], lock_target)
        zenodo_target = receipt_root / "zenodo-record-20642057.json"
        shutil.copyfile(acquisition["model"]["record_path"], zenodo_target)
        party_license_target = receipt_root / "party-LICENSE"
        shutil.copyfile(Path(acquisition["party_source"]["path"]) / "LICENSE", party_license_target)

        runtime_environment = os.environ.copy()
        runtime_environment.update(_runtime_environment(runtime_root))
        kraken_version = _run(
            ((runtime_root / "bin/kraken").as_posix(), "--version"),
            environment=runtime_environment,
            timeout=60,
        )
        if KRAKEN_VERSION not in "\n".join((kraken_version.stdout, kraken_version.stderr)):
            raise KrakenPartyRuntimeError("Kraken smoke did not report 7.0.2")
        party_help = _run(
            ((runtime_root / "bin/party").as_posix(), "--help"),
            environment=runtime_environment,
            timeout=120,
        )
        if "ocr" not in party_help.stdout or "set-lang" not in party_help.stdout:
            raise KrakenPartyRuntimeError("Party smoke omits required OCR commands")
        installed_versions = _installed_versions(runtime_root, runtime_environment)
        model_load = _run(
            (
                (runtime_root / "venv/bin/python").as_posix(),
                "-c",
                (
                    "import runpy;"
                    f"runpy.run_path({party_bridge.as_posix()!r},run_name='party_offline_adapter');"
                    "from kraken.tasks import RecognitionTaskModel;"
                    f"model=RecognitionTaskModel.load_model({model_target.as_posix()!r});"
                    "print(type(model).__name__)"
                ),
            ),
            environment=runtime_environment,
            timeout=600,
        )
        if "RecognitionTaskModel" not in model_load.stdout:
            raise KrakenPartyRuntimeError("Party model-load smoke returned an unexpected task model")

        build_receipt_path = receipt_root / "build.json"
        _write_json(
            build_receipt_path,
            {
                "schema_version": "tos_kraken_party_runtime_build_v1",
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
                "kraken_version_output": "\n".join(
                    part for part in (kraken_version.stdout, kraken_version.stderr) if part
                ).strip(),
                "party_help_sha256": hashlib.sha256(party_help.stdout.encode("utf-8")).hexdigest(),
                "party_loader_adapter": {
                    "ref": party_bridge.as_posix(),
                    "sha256": _sha256_file(party_bridge),
                    "effect": "force pretrained=False only during empty architecture construction",
                    "model_weight_closure": "Kraken safetensors loader rejects every missing or unexpected key",
                },
                "model_load_smoke_stdout": model_load.stdout.strip(),
                "model_load_smoke_stderr_sha256": hashlib.sha256(
                    model_load.stderr.encode("utf-8")
                ).hexdigest(),
                "model_sha256": PARTY_MODEL_SHA256,
                "owner_receipt_refs": [
                    path.resolve().as_posix() for path in (owner_receipt_refs or [])
                ],
                "invocation": invocation,
                "boundary": "offline runtime installation and smoke evidence only",
            },
        )

        roles = {
            "bin/kraken": "kraken-command-wrapper",
            "bin/party": "party-command-wrapper",
            "lib/party_offline_cli.py": "offline-constructor-adapter",
            "models/model.safetensors": "party-v4-model",
            "receipts/acquisition.json": "source-acquisition-receipt",
            "receipts/build.json": "offline-build-receipt",
            "receipts/requirements.lock.txt": "complete-wheel-hash-lock",
            "receipts/zenodo-record-20642057.json": "model-license-and-origin-record",
            "receipts/party-LICENSE": "party-source-license",
        }
        artifacts = inventory_runtime(runtime_root, roles=roles)
        wheel_by_name = {row["distribution"]: row for row in acquisition["wheels"]}
        software = [
            {
                "name": "kraken",
                "version": KRAKEN_VERSION,
                "source_url": "https://pypi.org/project/kraken/7.0.2/",
                "source_sha256": wheel_by_name["kraken"]["sha256"],
                "license": "Apache-2.0",
            },
            {
                "name": "party",
                "version": PARTY_VERSION,
                "source_url": f"https://github.com/mittagessen/party/commit/{PARTY_COMMIT}",
                "source_sha256": wheel_by_name["party"]["sha256"],
                "license": "Apache-2.0",
            },
            {
                "name": "lightning",
                "version": LIGHTNING_VERSION,
                "source_url": "https://github.com/Lightning-AI/pytorch-lightning/releases/tag/2.6.1",
                "source_sha256": wheel_by_name["lightning"]["sha256"],
                "license": "Apache-2.0",
            },
            {
                "name": "torch-cpu",
                "version": TORCH_VERSION,
                "source_url": "https://download.pytorch.org/whl/cpu/torch/",
                "source_sha256": wheel_by_name["torch"]["sha256"],
                "license": "BSD-3-Clause",
            },
            {
                "name": "party-model-v4",
                "version": PARTY_MODEL_DOI,
                "source_url": "https://zenodo.org/records/20642057",
                "source_sha256": PARTY_MODEL_SHA256,
                "license": "Apache-2.0",
            },
        ]
        manifest = {
            "schema_version": "tos_foundation_lab_runtime_manifest_v1",
            "runtime_id": RUNTIME_ID,
            "experiment_id": "tos-ocr-foundation-v1",
            "variant": "B",
            "status": "verified",
            "created_at_utc": _utc_now(),
            "runtime_root": runtime_root.as_posix(),
            "commands": {
                "kraken": (runtime_root / "bin/kraken").as_posix(),
                "party": (runtime_root / "bin/party").as_posix(),
            },
            "environment": _runtime_environment(runtime_root),
            "software": software,
            "artifacts": artifacts,
            "artifact_set_sha256": artifact_set_sha256(artifacts),
            "runtime_bytes": sum(row["bytes"] for row in artifacts),
            "licenses": [
                {
                    "subject": "Kraken 7.0.2, Party exact source commit, and Party v4 model",
                    "spdx": "Apache-2.0",
                    "evidence_ref": "receipts/acquisition.json",
                },
                {
                    "subject": "PyTorch 2.10.0 CPU runtime",
                    "spdx": "BSD-3-Clause",
                    "evidence_ref": "receipts/requirements.lock.txt",
                },
            ],
            "source_receipt_refs": [
                acquisition_target.as_posix(),
                build_receipt_path.as_posix(),
                zenodo_target.as_posix(),
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
                variant="B",
                required_commands=["kraken", "party"],
            )
        except RuntimeManifestError as exc:
            raise KrakenPartyRuntimeError(str(exc)) from exc
    except Exception as exc:
        _write_json(
            failure_path,
            {
                "schema_version": "tos_kraken_party_runtime_build_failure_v1",
                "failed_at_utc": _utc_now(),
                "runtime_root": runtime_root.as_posix(),
                "error": str(exc),
                "retention": "preserve-for-diagnosis-until-explicit-cleanup",
            },
        )
        if isinstance(exc, KrakenPartyRuntimeError):
            raise
        raise KrakenPartyRuntimeError(str(exc)) from exc
