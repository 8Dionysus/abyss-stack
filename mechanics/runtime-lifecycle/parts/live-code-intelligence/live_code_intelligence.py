"""Runtime-local Python LIVE code-observation provider.

This module owns runtime mechanics only.  It produces a compact, provider-
neutral observation envelope for a Python working tree and keeps candidate,
current, and last-good state separate.  It deliberately does not define KAG
meaning, install an LSP, or claim semantic lineage across renames and moves.
"""

from __future__ import annotations

import ast
import argparse
import base64
import copy
import errno
import hashlib
import json
import os
import queue
import shutil
import subprocess
import stat
import sys
import threading
import tempfile
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Iterator, Mapping, Sequence
from urllib.parse import unquote, urlsplit

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised only on non-POSIX hosts
    fcntl = None


CONFIG_SCHEMA = "abyss-stack-live-code-intelligence-provider-v1"
CONFIG_SCHEMA_REF = "schemas/live-code-intelligence-provider.schema.json"
OBSERVATION_SCHEMA = "abyss-stack-code-observation-v1"
STATE_SCHEMA = "abyss-stack-live-code-intelligence-state-v1"
STATUS_SCHEMA = "abyss-stack-live-code-intelligence-status-v1"
RECEIPT_SCHEMA = "abyss-stack-live-code-intelligence-refresh-receipt-v1"
OBSERVATION_ENVELOPE_SCHEMA = "abyss-stack-machine-bound-code-observation-v1"
PROVIDER_BOUNDARY_SCHEMA = "abyss-stack-live-code-intelligence-provider-boundary-v1"
PROVIDER_OPERATION_SCHEMA = "abyss-stack-live-code-intelligence-operation-v1"
MACHINE_BINDING_SCHEMA = "abyss-machine-code-intelligence-provider-binding-v1"
MACHINE_EVIDENCE_SCHEMA = "abyss-stack-machine-code-intelligence-evidence-v1"
PROVIDER_LIFECYCLE_SCHEMA = "abyss-stack-live-code-intelligence-provider-lifecycle-v1"
LSP_SESSION_SCHEMA = "abyss-stack-live-code-intelligence-lsp-session-v1"
OWNER_REVIEW_SCHEMA = "abyss-stack-live-code-intelligence-owner-review-v1"
PROVIDER_ID = "python-ast-bootstrap"
PROVIDER_VERSION = "1.1.0"
PROVIDER_LANGUAGE = "python"
PROVIDER_MODE = "bootstrap"
PROVIDER_PROTOCOL = "json-command-v1"
PROVIDER_ENTRYPOINT = "mechanics/runtime-lifecycle/parts/live-code-intelligence/live_code_intelligence.py"
PROVIDER_OPERATIONS = (
    "discover",
    "refresh",
    "status",
    "definitions",
    "references",
    "restart",
    "last_good",
    "canary",
    "rollback",
)
PROVIDER_EXECUTABLE = "python3"
MACHINE_INSTALLATION_IDENTITY = "source-local-provider-candidate"
MACHINE_ARTIFACT_KIND = "source-local-provider"
MACHINE_TRUST_STATE = "not-admitted"
MACHINE_ADMISSION_STATE = "unknown"
MACHINE_LIVE_MEASUREMENT_STATE = "unobserved"
MACHINE_EVIDENCE_CLASS = "machine-owned-verification"
MACHINE_EVIDENCE_METHOD = "abyss-machine-owner-receipt-v1"
AUTHORED_MAX_FILE_BYTES = 1_000_000
MACHINE_GATE_SCHEMA = "abyss-stack-machine-code-intelligence-gate-v1"
MACHINE_GATE_RECORD_SCHEMA = "abyss-machine-admission-gate-v1"
MACHINE_GATE_SIGNED_PAYLOAD_SCHEMA = "abyss-machine-admission-gate-signed-payload-v1"
MACHINE_REGISTRY_SCHEMA = "abyss-machine-content-addressed-registry-record-v1"
MACHINE_GATE_PUBLIC_KEY_SCHEMA = "abyss-machine-code-intelligence-gate-public-key-v1"
MACHINE_GATE_ALGORITHM = "ed25519"
MACHINE_GATE_VERIFICATION_METHOD = "ed25519-owner-signature-v1"
MACHINE_GATE_TRUST_ANCHOR = Path(
    "/etc/abyss-machine/trust/code-intelligence-gate-ed25519.json"
)
# This is the exact consumer ABI declared by the G59 MACHINE source. Keep it
# explicit at the stack boundary so schema, trust-anchor, lifecycle, and
# owner-separation drift is visible without accepting a provider artifact.
MACHINE_CONSUMER_ABI = {
    "owner": "abyss-stack",
    "binding_schema": MACHINE_BINDING_SCHEMA,
    "evidence_schema": MACHINE_EVIDENCE_SCHEMA,
    "gate_schema": MACHINE_GATE_SCHEMA,
    "gate_record_schema": MACHINE_GATE_RECORD_SCHEMA,
    "signed_payload_schema": MACHINE_GATE_SIGNED_PAYLOAD_SCHEMA,
    "public_key_schema": MACHINE_GATE_PUBLIC_KEY_SCHEMA,
    "algorithm": MACHINE_GATE_ALGORITHM,
    "verification_method": MACHINE_GATE_VERIFICATION_METHOD,
    "trust_anchor_ref": str(MACHINE_GATE_TRUST_ANCHOR),
    "trust_anchor_posture": "existing_root_owned_anchor_only",
    "provider_neutral": True,
    "state_axes": ["candidate", "current", "last_good"],
    "required_separations": [
        "machine artifact trust vs machine evidence gate",
        "installation and admission vs deployed runtime lifecycle",
        "runtime observation vs normalized observation meaning",
        "runtime evidence vs semantic proof and eval verdict",
    ],
}
PROVIDER_WORKER_SCHEMA = "abyss-stack-live-code-intelligence-provider-worker-v1"
PROVIDER_WORK_QUEUE_SCHEMA = "abyss-stack-live-code-intelligence-provider-work-queue-v1"
PROVIDER_QUEUE_CAPACITY = 128
SECOND_LANGUAGE_PROVIDER_ID = "typescript-lsp"
SECOND_LANGUAGE = "typescript"
MAX_QUERY_RESULTS = 100
PROVIDER_LIFECYCLE_OPERATIONS = (
    "discover",
    "refresh",
    "restart",
    "last_good",
    "canary",
    "rollback",
)
DEFAULT_EXCLUDE_DIRS = (
    ".git",
    ".hg",
    ".venv",
    "__pycache__",
    "node_modules",
)
DEFAULT_STATE_RELATIVE_ROOT = "Knowledge/code-intelligence/live/python"
DEFAULT_STATE_PROMOTION = "complete-observation-only"
DEFAULT_STATE_FALLBACK = "current-then-last-good"
DEFAULT_MACHINE_BINDING = {
    "schema_version": MACHINE_BINDING_SCHEMA,
    "owner": "abyss-machine",
    "installation_identity": MACHINE_INSTALLATION_IDENTITY,
    "artifact_subject": {
        "kind": MACHINE_ARTIFACT_KIND,
        "source_ref": PROVIDER_ENTRYPOINT,
        "trust_state": MACHINE_TRUST_STATE,
        "admission_state": MACHINE_ADMISSION_STATE,
    },
    "resource_envelope": {
        "max_file_bytes": AUTHORED_MAX_FILE_BYTES,
        "max_query_results": MAX_QUERY_RESULTS,
    },
    "live_measurement": {
        "required_for_admission": True,
        "state": MACHINE_LIVE_MEASUREMENT_STATE,
    },
}
DEFAULT_OWNER_BOUNDARIES = (
    ("runtime_lifecycle", "abyss-stack"),
    ("observation_meaning", "aoa-kag"),
    ("installation_and_admission", "abyss-machine"),
    ("proof_and_verdict", "aoa-evals"),
)
SOURCE_READ_CHUNK_BYTES = 64 * 1024
LSP_RUNTIME_MANIFEST_MAX_FILES = 4_096
LSP_RUNTIME_MANIFEST_MAX_BYTES = 256 * 1024 * 1024
# Source discovery has its own aggregate envelope.  A per-file limit does not
# bound the metadata retained for a tree containing many individually valid
# files, so the scan stops with a degraded candidate before that work can grow
# without limit.  Keep this aligned with the machine-owned manifest envelope
# while retaining an explicit source-scan contract.
SOURCE_SCAN_MAX_FILES = 4_096
SOURCE_SCAN_MAX_BYTES = 256 * 1024 * 1024
STATE_LOCK_NAME = ".refresh.lock"
OPERATION_RECEIPTS_DIRECTORY = "operations"
MACHINE_HEALTH_MAX_AGE_SECONDS = 15 * 60
LSP_MAX_HEADER_LINE_BYTES = 16 * 1024
LSP_MAX_HEADER_BYTES = 64 * 1024
LSP_MAX_HEADER_LINES = 32
# Bubblewrap is a machine-owned prerequisite of the immutable LSP launch
# boundary.  Do not resolve it through caller-controlled PATH.
MACHINE_BUBBLEWRAP_PATH = Path("/usr/bin/bwrap")
_PERSISTED_MACHINE_DYNAMIC_KEYS = frozenset(
    {
        "installation",
        "trust_binding",
        "admission",
        "live_measurement",
        "verified_evidence",
    }
)
_KNOWN_PYTHON_IMPORT_ROOTS = frozenset({"app", "lib", "python", "source", "src"})


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class LiveCodeIntelligenceError(RuntimeError):
    """Raised when a source or runtime-state boundary cannot be honored."""


_MACHINE_EVIDENCE_VALIDATION_TOKEN = object()


class _AuthenticatedMachineEvidence(Mapping[str, Any]):
    """Evidence wrapper that can only be produced after gate validation."""

    def __init__(
        self,
        payload: Mapping[str, Any],
        *,
        validation_token: object,
    ) -> None:
        if validation_token is not _MACHINE_EVIDENCE_VALIDATION_TOKEN:
            raise TypeError("machine evidence must come from gate validation")
        self._payload = copy.deepcopy(dict(payload))

    def __getitem__(self, key: str) -> Any:
        return copy.deepcopy(self._payload[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._payload)

    def __len__(self) -> int:
        return len(self._payload)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _digest_regular_file(path: Path, label: str) -> tuple[str, int]:
    """Digest one regular file without retaining its contents in memory."""

    try:
        if _contains_symlink(path):
            raise LiveCodeIntelligenceError(f"{label} must not contain symlinks")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise LiveCodeIntelligenceError(f"{label} must be a regular file")
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(SOURCE_READ_CHUNK_BYTES)
                if not chunk:
                    break
                digest.update(chunk)
                total += len(chunk)
        after = path.stat()
    except LiveCodeIntelligenceError:
        raise
    except (OSError, UnicodeError) as exc:
        raise LiveCodeIntelligenceError(f"unable to digest {label}") from exc
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise LiveCodeIntelligenceError(f"{label} changed while being digested")
    return f"sha256:{digest.hexdigest()}", total


def _directory_file_manifest(root: Path, label: str) -> tuple[tuple[str, str], ...]:
    """Return a bounded, symlink-free digest manifest for one directory tree."""

    root_input = Path(root).expanduser()
    if _contains_symlink(root_input):
        raise LiveCodeIntelligenceError(f"{label} must not contain symlinks")
    root = root_input.resolve()
    if not root.is_dir():
        raise LiveCodeIntelligenceError(f"{label} must be a real directory")
    entries: list[tuple[str, str]] = []
    total_bytes = 0

    def visit(directory: Path, relative_prefix: tuple[str, ...]) -> None:
        nonlocal total_bytes
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda entry: entry.name)
        except (OSError, UnicodeError) as exc:
            raise LiveCodeIntelligenceError(
                f"unable to enumerate {label}: {directory}"
            ) from exc
        for child in children:
            if _contains_surrogate(child.name):
                raise LiveCodeIntelligenceError(
                    f"{label} contains a non-UTF-8 filename"
                )
            child_path = directory / child.name
            relative_parts = relative_prefix + (child.name,)
            relative = "/".join(relative_parts)
            if child.is_symlink():
                raise LiveCodeIntelligenceError(
                    f"{label} contains a symlink: {relative}"
                )
            if child.is_dir(follow_symlinks=False):
                visit(child_path, relative_parts)
                continue
            if not child.is_file(follow_symlinks=False):
                raise LiveCodeIntelligenceError(
                    f"{label} contains a non-regular entry: {relative}"
                )
            if len(entries) >= LSP_RUNTIME_MANIFEST_MAX_FILES:
                raise LiveCodeIntelligenceError(
                    f"{label} exceeds the bounded file count"
                )
            digest, size = _digest_regular_file(child_path, f"{label} {relative}")
            total_bytes += size
            if total_bytes > LSP_RUNTIME_MANIFEST_MAX_BYTES:
                raise LiveCodeIntelligenceError(
                    f"{label} exceeds the bounded byte count"
                )
            entries.append((relative, digest))

    visit(root, ())
    return tuple(sorted(entries))


def _validated_file_manifest(
    value: Any,
    label: str,
    *,
    allow_empty: bool,
) -> tuple[tuple[str, str], ...]:
    """Validate a signed relative path/digest manifest with one ordering."""

    if not isinstance(value, list) or (not allow_empty and not value):
        suffix = "non-empty " if not allow_empty else ""
        raise LiveCodeIntelligenceError(f"{label} must be a {suffix}array")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        mapping = _mapping(item, item_label)
        _exact_keys(mapping, {"path", "digest"}, item_label)
        path = _non_empty_string(mapping.get("path"), f"{item_label}.path")
        relative = Path(path)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or "\\" in path
            or _contains_surrogate(path)
            or path != relative.as_posix()
        ):
            raise LiveCodeIntelligenceError(
                f"{item_label}.path must be a safe relative POSIX path"
            )
        if path in seen:
            raise LiveCodeIntelligenceError(f"{label} contains duplicate paths")
        seen.add(path)
        digest = _sha256_reference(mapping.get("digest"), f"{item_label}.digest")
        entries.append((path, digest))
    if entries != sorted(entries):
        raise LiveCodeIntelligenceError(f"{label} must be sorted by path")
    return tuple(entries)


def _is_python_interpreter(path: Path) -> bool:
    name = path.name.lower()
    return name.startswith("python") or name.startswith("pypy")


def _shebang_interpreter(path: Path) -> Path | None:
    """Return the exact absolute interpreter named by a script shebang.

    A script digest alone does not authenticate the code that an inherited
    ``PATH`` or a shebang helper will select.  Only a single absolute
    interpreter token is therefore admitted; callers bind its bytes
    separately to the machine receipt before launch.
    """

    try:
        with path.open("rb") as handle:
            first_line = handle.readline(4097)
    except OSError as exc:
        raise LiveCodeIntelligenceError(
            f"unable to inspect LSP executable interpreter: {path}"
        ) from exc
    if not first_line.startswith(b"#!"):
        return None
    try:
        shebang = first_line[2:].decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise LiveCodeIntelligenceError(
            "LSP script interpreter declaration is not valid UTF-8"
        ) from exc
    tokens = shebang.split()
    if len(tokens) != 1 or not Path(tokens[0]).is_absolute():
        raise LiveCodeIntelligenceError(
            "LSP script interpreter must be one absolute executable path"
        )
    interpreter = Path(tokens[0]).expanduser().resolve()
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise LiveCodeIntelligenceError("LSP script interpreter is not runnable")
    return interpreter


def _read_descriptor(descriptor: int, size: int, offset: int) -> bytes:
    """Read a bounded slice without changing the descriptor's launch state."""

    if hasattr(os, "pread"):
        return os.pread(descriptor, size, offset)
    current = os.lseek(descriptor, 0, os.SEEK_CUR)
    try:
        os.lseek(descriptor, offset, os.SEEK_SET)
        return os.read(descriptor, size)
    finally:
        os.lseek(descriptor, current, os.SEEK_SET)


def _open_regular_descriptor(path: Path, label: str) -> tuple[int, os.stat_result]:
    """Open one candidate without following links and require a regular file."""

    flags = os.O_RDONLY
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise LiveCodeIntelligenceError(
            f"unable to open {label} for exact launch"
        ) from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LiveCodeIntelligenceError(
                f"{label} must be a regular file for exact launch"
            )
        return descriptor, metadata
    except Exception:
        os.close(descriptor)
        raise


def _shebang_interpreter_from_descriptor(
    descriptor: int,
) -> Path | None:
    """Parse a shebang from the exact bytes selected for launch."""

    first_line = _read_descriptor(descriptor, 4097, 0)
    if not first_line.startswith(b"#!"):
        return None
    try:
        shebang = first_line[2:].decode("utf-8").splitlines()[0].strip()
    except (UnicodeDecodeError, IndexError) as exc:
        raise LiveCodeIntelligenceError(
            "LSP script interpreter declaration is not valid UTF-8"
        ) from exc
    tokens = shebang.split()
    if len(tokens) != 1 or not Path(tokens[0]).is_absolute():
        raise LiveCodeIntelligenceError(
            "LSP script interpreter must be one absolute executable path"
        )
    return Path(tokens[0]).expanduser().resolve()


def _digest_payload(value: object) -> str:
    return _digest_bytes(_canonical_json(value).encode("utf-8"))


def _fresh_utc_timestamp(value: Any, label: str, *, max_age_seconds: int) -> str:
    text = _non_empty_string(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LiveCodeIntelligenceError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise LiveCodeIntelligenceError(f"{label} must include a timezone")
    age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    if age < -60 or age > max_age_seconds:
        raise LiveCodeIntelligenceError(f"{label} is outside the live health window")
    return text


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _require_fresh_machine_health(evidence: Mapping[str, Any]) -> None:
    """Revalidate the owner health observation at each admission use."""

    health = _mapping(evidence.get("health"), "machine_evidence.health")
    _fresh_utc_timestamp(
        health.get("observed_at"),
        "machine_evidence.health.observed_at",
        max_age_seconds=MACHINE_HEALTH_MAX_AGE_SECONDS,
    )


def _lsp_launch_environment(
    runtime_root: Path,
    interpreter: Path | None,
) -> dict[str, str]:
    """Return the fixed environment admitted LSP children may observe.

    LSP commands are selected by an owner-authenticated artifact binding, so
    caller-controlled environment variables must not be another executable
    input. In particular, Python path/site hooks and native loader overrides
    remain absent; any Python path is a fixed runtime-root path covered by the
    admitted manifest, and the fixed PATH is only for child tools the admitted
    server itself may intentionally invoke.
    """

    environment = {
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.defpath,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if interpreter is not None and _is_python_interpreter(interpreter):
        # This is a fixed path selected from the manifest-bound runtime root,
        # not caller input. Python launch adds -S below, so system/user site
        # packages and sitecustomize hooks cannot become hidden dependencies.
        environment["PYTHONPATH"] = str(runtime_root)
    return environment


def _file_uri_path(value: Any, label: str) -> Path:
    """Resolve a file URI to a canonical path without accepting another root."""

    text = _non_empty_string(value, label)
    parsed = urlsplit(text)
    if (
        parsed.scheme.lower() != "file"
        or parsed.query
        or parsed.fragment
        or parsed.netloc not in {"", "localhost"}
    ):
        raise LiveCodeIntelligenceError(f"{label} must be a local file URI")
    decoded = unquote(parsed.path)
    if not decoded:
        raise LiveCodeIntelligenceError(f"{label} must identify a source root")
    if os.name == "nt" and decoded.startswith("/") and len(decoded) > 2 and decoded[2] == ":":
        decoded = decoded[1:]
    path = Path(decoded)
    if not path.is_absolute():
        raise LiveCodeIntelligenceError(f"{label} must identify an absolute source root")
    try:
        return path.resolve()
    except OSError as exc:
        raise LiveCodeIntelligenceError(f"{label} source root cannot be resolved") from exc


def _contains_symlink(path: Path) -> bool:
    """Return whether a path or any existing ancestor is a symlink.

    Resolving a caller path before checking it would turn a symlink escape into
    an apparently ordinary directory. Boundary paths are therefore checked in
    their lexical form before they are canonicalized.
    """

    current = Path(os.path.abspath(os.fspath(path.expanduser())))
    while True:
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _contains_surrogate(value: str) -> bool:
    """Return whether a decoded filesystem string contains surrogate escapes."""

    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    if _contains_symlink(path):
        raise LiveCodeIntelligenceError(
            f"refusing to write through symlinked state path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if _contains_symlink(path):
        raise LiveCodeIntelligenceError(
            f"refusing to write through symlinked state directory: {path.parent}"
        )
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = None
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.is_symlink():
            raise LiveCodeIntelligenceError(
                f"refusing to replace symlinked state path: {path}"
            )
        temporary.replace(path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    if _contains_symlink(path) or not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LiveCodeIntelligenceError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    missing = sorted(expected.difference(actual))
    unexpected = sorted(actual.difference(expected))
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
        raise LiveCodeIntelligenceError(
            f"{label} does not match the authored schema ({'; '.join(details)})"
        )


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LiveCodeIntelligenceError(f"{label} must be a non-empty string")
    return value


def _positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise LiveCodeIntelligenceError(f"{label} must be a positive integer")
    return value


def _sha256_reference(value: Any, label: str) -> str:
    text = _non_empty_string(value, label)
    if not _is_sha256_reference(text):
        raise LiveCodeIntelligenceError(f"{label} must be a sha256 reference")
    return text


def _is_sha256_reference(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len("sha256:") + 64
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _machine_binding_stable_projection(
    value: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Strip capture-time machine posture from a persisted binding identity."""

    if not isinstance(value, Mapping):
        return None
    projection = copy.deepcopy(dict(value))
    for key in _PERSISTED_MACHINE_DYNAMIC_KEYS:
        projection.pop(key, None)
    runtime_binding = projection.get("runtime_binding")
    if isinstance(runtime_binding, Mapping):
        runtime_binding = copy.deepcopy(dict(runtime_binding))
        runtime_binding.pop("source_epoch", None)
        projection["runtime_binding"] = runtime_binding
    return projection


def _string_list(value: Any, label: str, *, required: bool = True) -> list[str]:
    if not isinstance(value, list) or (required and not value):
        raise LiveCodeIntelligenceError(f"{label} must be a string array")
    if any(not isinstance(item, str) or not item for item in value):
        raise LiveCodeIntelligenceError(f"{label} must contain non-empty strings")
    return list(value)


def _base64_bytes(value: Any, label: str, *, length: int) -> bytes:
    text = _non_empty_string(value, label)
    try:
        decoded = base64.b64decode(text.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as exc:
        raise LiveCodeIntelligenceError(f"{label} must be valid base64") from exc
    if len(decoded) != length:
        raise LiveCodeIntelligenceError(f"{label} must decode to {length} bytes")
    return decoded


def _content_address(value: Any, label: str) -> str:
    text = _non_empty_string(value, label)
    if not text.startswith("cas://"):
        raise LiveCodeIntelligenceError(f"{label} must be a content-addressed reference")
    digest = _sha256_reference(text.removeprefix("cas://"), label)
    return f"cas://{digest}"


# These are deliberately local verification primitives.  They do not select
# the machine owner or create a trust root; the public key is read only from
# the fixed machine-owned trust anchor below.  Keeping verification here
# avoids turning an optional Python package or a caller-controlled helper into
# an authority boundary.
_ED25519_P = (1 << 255) - 19
_ED25519_Q = (1 << 252) + 27742317777372353535851937790883648493
_ED25519_D = (-121665 * pow(121666, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
_ED25519_I = pow(2, (_ED25519_P - 1) // 4, _ED25519_P)


def _ed25519_xrecover(y: int) -> int:
    xx = ((y * y - 1) * pow(_ED25519_D * y * y + 1, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
    x = pow(xx, (_ED25519_P + 3) // 8, _ED25519_P)
    if (x * x - xx) % _ED25519_P != 0:
        x = (x * _ED25519_I) % _ED25519_P
    if (x * x - xx) % _ED25519_P != 0:
        raise ValueError("invalid Ed25519 point")
    if x & 1:
        x = _ED25519_P - x
    return x


def _ed25519_decode_point(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise ValueError("invalid Ed25519 point length")
    value = int.from_bytes(encoded, "little")
    sign = value >> 255
    y = value & ((1 << 255) - 1)
    if y >= _ED25519_P:
        raise ValueError("invalid Ed25519 point y coordinate")
    x = _ed25519_xrecover(y)
    if (x & 1) != sign:
        x = _ED25519_P - x
    if x == 0 and sign:
        raise ValueError("invalid Ed25519 point sign")
    if (y * y - x * x - 1 - _ED25519_D * x * x * y * y) % _ED25519_P:
        raise ValueError("invalid Ed25519 point")
    return x, y


def _ed25519_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    product = (_ED25519_D * x1 * x2 * y1 * y2) % _ED25519_P
    x3 = ((x1 * y2 + x2 * y1) * pow(1 + product, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
    y3 = ((y1 * y2 + x1 * x2) * pow(1 - product, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
    return x3, y3


def _ed25519_scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = (0, 1)
    addend = point
    while scalar:
        if scalar & 1:
            result = _ed25519_add(result, addend)
        addend = _ed25519_add(addend, addend)
        scalar >>= 1
    return result


def _ed25519_base_point() -> tuple[int, int]:
    y = (4 * pow(5, _ED25519_P - 2, _ED25519_P)) % _ED25519_P
    return _ed25519_xrecover(y), y


def _ed25519_verify(public_key: bytes, signature: bytes, message: bytes) -> bool:
    if len(public_key) != 32 or len(signature) != 64:
        return False
    try:
        public_point = _ed25519_decode_point(public_key)
        signature_point = _ed25519_decode_point(signature[:32])
    except ValueError:
        return False
    identity = (0, 1)
    if (
        public_point == identity
        or signature_point == identity
        or _ed25519_scalar_mult(public_point, _ED25519_Q) != identity
        or _ed25519_scalar_mult(signature_point, _ED25519_Q) != identity
    ):
        return False
    scalar = int.from_bytes(signature[32:], "little")
    if scalar >= _ED25519_Q:
        return False
    challenge = int.from_bytes(
        hashlib.sha512(signature[:32] + public_key + message).digest(),
        "little",
    ) % _ED25519_Q
    base = _ed25519_base_point()
    left = _ed25519_scalar_mult(base, scalar)
    right = _ed25519_add(
        signature_point,
        _ed25519_scalar_mult(public_point, challenge),
    )
    return left == right


def machine_evidence_digest(value: Mapping[str, Any]) -> str:
    """Return the integrity digest for an external machine evidence receipt.

    The digest detects a changed receipt payload. It is not an issuer
    signature, trust grant, admission verdict, or proof result; those remain
    owned by the machine and review owners.
    """

    unsigned = dict(value)
    unsigned.pop("receipt_digest", None)
    return _digest_payload(unsigned)


def machine_evidence_gate_digest(value: Mapping[str, Any]) -> str:
    """Return the content digest of a registry gate record.

    This is an address for the gate bytes, not an authentication primitive.
    Authentication is supplied separately by the detached owner signature.
    """

    unsigned = dict(value)
    unsigned.pop("gate_digest", None)
    return _digest_payload(unsigned)


def machine_evidence_bundle_digest(value: Mapping[str, Any]) -> str:
    """Return the content digest of a registry/gate bundle."""

    unsigned = dict(value)
    unsigned.pop("bundle_digest", None)
    return _digest_payload(unsigned)


def _validate_lifecycle_component(
    value: Any,
    label: str,
    *,
    allowed_states: set[str],
) -> dict[str, Any]:
    component = _mapping(value, label)
    _exact_keys(component, {"state", "evidence_ref"}, label)
    state = _non_empty_string(component.get("state"), f"{label}.state")
    if state not in allowed_states:
        raise LiveCodeIntelligenceError(f"{label}.state is not a known lifecycle state")
    _non_empty_string(component.get("evidence_ref"), f"{label}.evidence_ref")
    return copy.deepcopy(dict(component))


def _validate_machine_evidence_payload(
    value: Any,
    *,
    expected_provider: Mapping[str, Any],
    expected_provider_source_digest: str,
    expected_config_digest: str,
) -> dict[str, Any]:
    """Validate the inner record carried by an owner-authenticated gate.

    Authored config is intentionally not an input to this receipt. The receipt
    must bind the exact provider source/config identities. This function only
    checks the record shape and its unkeyed integrity digest. It is never an
    authority boundary by itself; callers must use
    ``_validate_machine_evidence_gate_bundle`` before promotion.
    """

    raw = _mapping(value, "machine_evidence")
    _exact_keys(
        raw,
        {
            "schema_version",
            "evidence_class",
            "issuer",
            "receipt_id",
            "observed_at",
            "subject",
            "installation",
            "admission",
            "health",
            "verification",
            "providers",
            "lsp_sessions",
            "observations",
            "lifecycle",
            "owner_boundaries",
            "claim_limits",
            "receipt_digest",
        },
        "machine_evidence",
    )
    if raw.get("schema_version") != MACHINE_EVIDENCE_SCHEMA:
        raise LiveCodeIntelligenceError("machine evidence schema mismatch")
    if raw.get("evidence_class") != MACHINE_EVIDENCE_CLASS:
        raise LiveCodeIntelligenceError("machine evidence class mismatch")
    if raw.get("issuer") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine evidence issuer mismatch")
    _non_empty_string(raw.get("receipt_id"), "machine_evidence.receipt_id")
    _non_empty_string(raw.get("observed_at"), "machine_evidence.observed_at")

    subject = _mapping(raw.get("subject"), "machine_evidence.subject")
    _exact_keys(
        subject,
        {
            "provider",
            "provider_source_digest",
            "config_digest",
            "artifact_digest",
            "artifact_ref",
        },
        "machine_evidence.subject",
    )
    subject_provider = _mapping(
        subject.get("provider"), "machine_evidence.subject.provider"
    )
    if dict(subject_provider) != dict(expected_provider):
        raise LiveCodeIntelligenceError("machine evidence provider identity mismatch")
    if subject.get("provider_source_digest") != expected_provider_source_digest:
        raise LiveCodeIntelligenceError("machine evidence source digest mismatch")
    if subject.get("config_digest") != expected_config_digest:
        raise LiveCodeIntelligenceError("machine evidence config digest mismatch")
    artifact_digest = _sha256_reference(
        subject.get("artifact_digest"), "machine_evidence.subject.artifact_digest"
    )
    _non_empty_string(subject.get("artifact_ref"), "machine_evidence.subject.artifact_ref")

    installation = _mapping(raw.get("installation"), "machine_evidence.installation")
    _exact_keys(
        installation,
        {"owner", "state", "identity", "artifact_digest", "evidence_ref"},
        "machine_evidence.installation",
    )
    if installation.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine installation evidence owner mismatch")
    if installation.get("state") != "verified":
        raise LiveCodeIntelligenceError("machine installation evidence is not verified")
    _non_empty_string(installation.get("identity"), "machine_evidence.installation.identity")
    if installation.get("artifact_digest") != artifact_digest:
        raise LiveCodeIntelligenceError("machine installation artifact mismatch")
    _non_empty_string(
        installation.get("evidence_ref"), "machine_evidence.installation.evidence_ref"
    )

    admission = _mapping(raw.get("admission"), "machine_evidence.admission")
    _exact_keys(
        admission,
        {"owner", "state", "trust_state", "admission_ref"},
        "machine_evidence.admission",
    )
    if admission.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine admission evidence owner mismatch")
    if admission.get("state") != "admitted":
        raise LiveCodeIntelligenceError("machine provider admission is not admitted")
    if admission.get("trust_state") != "trusted":
        raise LiveCodeIntelligenceError("machine provider trust is not trusted")
    _non_empty_string(admission.get("admission_ref"), "machine_evidence.admission.admission_ref")

    health = _mapping(raw.get("health"), "machine_evidence.health")
    _exact_keys(
        health,
        {"owner", "state", "measurement_ref", "observed_at"},
        "machine_evidence.health",
    )
    if health.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine health evidence owner mismatch")
    if health.get("state") != "healthy":
        raise LiveCodeIntelligenceError("machine provider health is not healthy")
    _non_empty_string(health.get("measurement_ref"), "machine_evidence.health.measurement_ref")
    _fresh_utc_timestamp(
        health.get("observed_at"),
        "machine_evidence.health.observed_at",
        max_age_seconds=MACHINE_HEALTH_MAX_AGE_SECONDS,
    )

    verification = _mapping(raw.get("verification"), "machine_evidence.verification")
    _exact_keys(
        verification,
        {"owner", "state", "method", "verification_ref"},
        "machine_evidence.verification",
    )
    if verification.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine evidence verification owner mismatch")
    if verification.get("state") != "verified":
        raise LiveCodeIntelligenceError("machine evidence is not verified")
    if verification.get("method") != MACHINE_EVIDENCE_METHOD:
        raise LiveCodeIntelligenceError("machine evidence verification method mismatch")
    _non_empty_string(
        verification.get("verification_ref"),
        "machine_evidence.verification.verification_ref",
    )

    owner_boundaries = _mapping(
        raw.get("owner_boundaries"), "machine_evidence.owner_boundaries"
    )
    _exact_keys(
        owner_boundaries,
        {key for key, _ in DEFAULT_OWNER_BOUNDARIES},
        "machine_evidence.owner_boundaries",
    )
    if dict(owner_boundaries) != dict(DEFAULT_OWNER_BOUNDARIES):
        raise LiveCodeIntelligenceError("machine evidence owner boundaries mismatch")

    providers_value = raw.get("providers")
    if not isinstance(providers_value, list) or not providers_value:
        raise LiveCodeIntelligenceError("machine_evidence.providers must be non-empty")
    providers: list[dict[str, Any]] = []
    provider_by_id: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(providers_value):
        label = f"machine_evidence.providers[{index}]"
        provider = _mapping(item, label)
        _exact_keys(
            provider,
            {"id", "version", "language", "protocol", "observation_state"},
            label,
        )
        provider_id = _non_empty_string(provider.get("id"), f"{label}.id")
        if provider_id in provider_by_id:
            raise LiveCodeIntelligenceError("machine evidence provider ids must be unique")
        _non_empty_string(provider.get("version"), f"{label}.version")
        language = _non_empty_string(provider.get("language"), f"{label}.language")
        _non_empty_string(provider.get("protocol"), f"{label}.protocol")
        if provider.get("observation_state") not in {
            "observed",
            "available",
            "unobserved",
        }:
            raise LiveCodeIntelligenceError(f"{label}.observation_state is invalid")
        normalized = copy.deepcopy(dict(provider))
        normalized["language"] = language
        providers.append(normalized)
        provider_by_id[provider_id] = normalized
    expected_provider_id = str(expected_provider["id"])
    primary = provider_by_id.get(expected_provider_id)
    if primary is None or any(
        primary.get(key) != expected_provider.get(key)
        for key in ("id", "version", "language", "protocol")
    ):
        raise LiveCodeIntelligenceError("machine evidence omits the configured provider")

    lsp_sessions_value = raw.get("lsp_sessions")
    if not isinstance(lsp_sessions_value, list):
        raise LiveCodeIntelligenceError("machine_evidence.lsp_sessions must be an array")
    lsp_sessions: list[dict[str, Any]] = []
    for index, item in enumerate(lsp_sessions_value):
        label = f"machine_evidence.lsp_sessions[{index}]"
        session = _mapping(item, label)
        required_session_keys = {
            "session_id",
            "provider_id",
            "language",
            "state",
            "transport",
            "source_epoch",
            "evidence_ref",
            "runtime_manifest",
            "source_manifest",
        }
        optional_session_keys = {
            "source_root",
            "command_digest",
            "artifact_digest",
            "interpreter_digest",
        }
        missing_session_keys = sorted(required_session_keys.difference(session))
        unexpected_session_keys = sorted(
            set(session).difference(required_session_keys | optional_session_keys)
        )
        if missing_session_keys or unexpected_session_keys:
            details = []
            if missing_session_keys:
                details.append(f"missing={','.join(missing_session_keys)}")
            if unexpected_session_keys:
                details.append(f"unexpected={','.join(unexpected_session_keys)}")
            raise LiveCodeIntelligenceError(
                f"{label} does not match the authored schema ({'; '.join(details)})"
            )
        provider_id = _non_empty_string(session.get("provider_id"), f"{label}.provider_id")
        provider = provider_by_id.get(provider_id)
        if provider is None or session.get("language") != provider.get("language"):
            raise LiveCodeIntelligenceError(f"{label} provider/language mismatch")
        _non_empty_string(session.get("session_id"), f"{label}.session_id")
        _non_empty_string(session.get("language"), f"{label}.language")
        if session.get("state") not in {"observed", "unobserved"}:
            raise LiveCodeIntelligenceError(f"{label}.state is invalid")
        if session.get("state") == "observed" and "source_root" not in session:
            raise LiveCodeIntelligenceError(
                f"{label}.source_root is required for observed LSP sessions"
            )
        _non_empty_string(session.get("transport"), f"{label}.transport")
        _non_empty_string(session.get("source_epoch"), f"{label}.source_epoch")
        _non_empty_string(session.get("evidence_ref"), f"{label}.evidence_ref")
        if "source_root" in session:
            _non_empty_string(session.get("source_root"), f"{label}.source_root")
        if "command_digest" in session:
            _sha256_reference(
                session.get("command_digest"), f"{label}.command_digest"
            )
        if "artifact_digest" in session:
            _sha256_reference(
                session.get("artifact_digest"), f"{label}.artifact_digest"
            )
        if "interpreter_digest" in session:
            _sha256_reference(
                session.get("interpreter_digest"), f"{label}.interpreter_digest"
            )
        runtime_manifest = _validated_file_manifest(
            session.get("runtime_manifest"),
            f"{label}.runtime_manifest",
            allow_empty=session.get("state") != "observed",
        )
        source_manifest = _validated_file_manifest(
            session.get("source_manifest"),
            f"{label}.source_manifest",
            allow_empty=True,
        )
        normalized_session = copy.deepcopy(dict(session))
        normalized_session["runtime_manifest"] = [
            {"path": path, "digest": digest}
            for path, digest in runtime_manifest
        ]
        normalized_session["source_manifest"] = [
            {"path": path, "digest": digest}
            for path, digest in source_manifest
        ]
        lsp_sessions.append(normalized_session)

    observations_value = raw.get("observations")
    if not isinstance(observations_value, list):
        raise LiveCodeIntelligenceError("machine_evidence.observations must be an array")
    observations: list[dict[str, Any]] = []
    for index, item in enumerate(observations_value):
        label = f"machine_evidence.observations[{index}]"
        observation = _mapping(item, label)
        _exact_keys(
            observation,
            {
                "provider_id",
                "language",
                "state",
                "source_epoch",
                "observation_ref",
                "semantic_owner",
            },
            label,
        )
        provider_id = _non_empty_string(observation.get("provider_id"), f"{label}.provider_id")
        provider = provider_by_id.get(provider_id)
        if provider is None or observation.get("language") != provider.get("language"):
            raise LiveCodeIntelligenceError(f"{label} provider/language mismatch")
        _non_empty_string(observation.get("language"), f"{label}.language")
        if observation.get("state") not in {"observed", "unobserved"}:
            raise LiveCodeIntelligenceError(f"{label}.state is invalid")
        _non_empty_string(observation.get("source_epoch"), f"{label}.source_epoch")
        _non_empty_string(observation.get("observation_ref"), f"{label}.observation_ref")
        if observation.get("semantic_owner") != "aoa-kag":
            raise LiveCodeIntelligenceError(f"{label}.semantic_owner mismatch")
        observations.append(copy.deepcopy(dict(observation)))

    lifecycle = _mapping(raw.get("lifecycle"), "machine_evidence.lifecycle")
    _exact_keys(
        lifecycle,
        {"state", "restart", "last_good", "canary", "rollback"},
        "machine_evidence.lifecycle",
    )
    if lifecycle.get("state") not in {"ready", "degraded"}:
        raise LiveCodeIntelligenceError("machine evidence lifecycle state is invalid")
    lifecycle_components = {
        key: _validate_lifecycle_component(
            lifecycle.get(key),
            f"machine_evidence.lifecycle.{key}",
            allowed_states={
                "observed",
                "available",
                "passed",
                "ready",
                "unobserved",
                "not-observed",
            },
        )
        for key in ("restart", "last_good", "canary", "rollback")
    }

    claim_limits = _string_list(raw.get("claim_limits"), "machine_evidence.claim_limits")
    receipt_digest = _sha256_reference(
        raw.get("receipt_digest"), "machine_evidence.receipt_digest"
    )
    if receipt_digest != machine_evidence_digest(raw):
        raise LiveCodeIntelligenceError("machine evidence receipt digest mismatch")

    normalized = copy.deepcopy(dict(raw))
    normalized["subject"] = copy.deepcopy(dict(subject))
    normalized["installation"] = copy.deepcopy(dict(installation))
    normalized["admission"] = copy.deepcopy(dict(admission))
    normalized["health"] = copy.deepcopy(dict(health))
    normalized["verification"] = copy.deepcopy(dict(verification))
    normalized["owner_boundaries"] = copy.deepcopy(dict(owner_boundaries))
    normalized["providers"] = providers
    normalized["lsp_sessions"] = lsp_sessions
    normalized["observations"] = observations
    normalized["lifecycle"] = {
        "state": lifecycle["state"],
        **lifecycle_components,
    }
    normalized["claim_limits"] = claim_limits
    return normalized


def _machine_gate_trust_anchor() -> tuple[str, str, bytes]:
    """Read the machine-owned Ed25519 trust anchor.

    The trust anchor is intentionally not configurable by the receipt or the
    caller. A missing, symlinked, non-root-owned, or writable anchor fails
    closed. The machine owner provisions this file out of band; this source
    surface never creates or changes it.
    """

    path = MACHINE_GATE_TRUST_ANCHOR
    try:
        if _contains_symlink(path) or not path.is_file():
            raise LiveCodeIntelligenceError(
                "machine owner trust anchor is unavailable"
            )
        metadata = path.stat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_mode & 0o022
        ):
            raise LiveCodeIntelligenceError(
                "machine owner trust anchor is not a private root-owned regular file"
            )
        raw_bytes = path.read_bytes()
    except LiveCodeIntelligenceError:
        raise
    except (OSError, UnicodeError) as exc:
        raise LiveCodeIntelligenceError(
            "machine owner trust anchor is unavailable"
        ) from exc
    try:
        payload = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LiveCodeIntelligenceError(
            "machine owner trust anchor is not valid JSON"
        ) from exc
    anchor = _mapping(payload, "machine_gate_trust_anchor")
    _exact_keys(
        anchor,
        {"schema_version", "owner", "key_id", "algorithm", "public_key"},
        "machine_gate_trust_anchor",
    )
    if anchor.get("schema_version") != MACHINE_GATE_PUBLIC_KEY_SCHEMA:
        raise LiveCodeIntelligenceError("machine owner trust anchor schema mismatch")
    if anchor.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine owner trust anchor owner mismatch")
    key_id = _non_empty_string(anchor.get("key_id"), "machine_gate_trust_anchor.key_id")
    if anchor.get("algorithm") != MACHINE_GATE_ALGORITHM:
        raise LiveCodeIntelligenceError("machine owner trust anchor algorithm mismatch")
    public_key = _base64_bytes(
        anchor.get("public_key"),
        "machine_gate_trust_anchor.public_key",
        length=32,
    )
    return key_id, _digest_bytes(raw_bytes), public_key


def _validate_machine_evidence_gate_bundle(
    value: Any,
    *,
    expected_provider: Mapping[str, Any],
    expected_provider_source_digest: str,
    expected_config_digest: str,
) -> dict[str, Any]:
    """Authenticate and validate a machine-owned registry/gate bundle.

    A regular JSON receipt is deliberately not enough. The registry record is
    content-addressed, the gate signs the exact record identity and binding,
    and that signature is checked against the fixed machine-owned trust
    anchor. Owner strings, path locations, self-digests, and gate state fields
    are consistency checks only.
    """

    bundle = _mapping(value, "machine_evidence")
    if bundle.get("schema_version") != MACHINE_GATE_SCHEMA:
        raise LiveCodeIntelligenceError(
            "machine evidence requires an owner-authenticated registry gate bundle"
        )
    _exact_keys(
        bundle,
        {"schema_version", "registry", "evidence", "gate", "bundle_digest"},
        "machine_evidence",
    )
    evidence_value = _mapping(bundle.get("evidence"), "machine_evidence.evidence")
    evidence = _validate_machine_evidence_payload(
        evidence_value,
        expected_provider=expected_provider,
        expected_provider_source_digest=expected_provider_source_digest,
        expected_config_digest=expected_config_digest,
    )
    evidence_digest = _digest_payload(evidence)

    registry = _mapping(bundle.get("registry"), "machine_evidence.registry")
    _exact_keys(
        registry,
        {
            "schema_version",
            "owner",
            "record_ref",
            "record_digest",
            "gate_ref",
            "gate_digest",
        },
        "machine_evidence.registry",
    )
    if registry.get("schema_version") != MACHINE_REGISTRY_SCHEMA:
        raise LiveCodeIntelligenceError("machine evidence registry schema mismatch")
    if registry.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine evidence registry owner mismatch")
    record_digest = _sha256_reference(
        registry.get("record_digest"), "machine_evidence.registry.record_digest"
    )
    record_ref = _content_address(
        registry.get("record_ref"), "machine_evidence.registry.record_ref"
    )
    if record_digest != evidence_digest or record_ref != f"cas://{record_digest}":
        raise LiveCodeIntelligenceError(
            "machine evidence registry record is not content-addressed"
        )

    gate = _mapping(bundle.get("gate"), "machine_evidence.gate")
    _exact_keys(
        gate,
        {
            "schema_version",
            "owner",
            "state",
            "algorithm",
            "verification_method",
            "key_id",
            "key_digest",
            "gate_id",
            "verification_ref",
            "subject_digest",
            "signed_payload",
            "signature",
            "gate_digest",
        },
        "machine_evidence.gate",
    )
    if gate.get("schema_version") != MACHINE_GATE_RECORD_SCHEMA:
        raise LiveCodeIntelligenceError("machine evidence gate schema mismatch")
    if gate.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError("machine evidence gate owner mismatch")
    if gate.get("state") != "authenticated":
        raise LiveCodeIntelligenceError("machine evidence gate is not authenticated")
    if gate.get("algorithm") != MACHINE_GATE_ALGORITHM:
        raise LiveCodeIntelligenceError("machine evidence gate algorithm mismatch")
    if gate.get("verification_method") != MACHINE_GATE_VERIFICATION_METHOD:
        raise LiveCodeIntelligenceError(
            "machine evidence gate verification method mismatch"
        )
    key_id = _non_empty_string(gate.get("key_id"), "machine_evidence.gate.key_id")
    key_digest = _sha256_reference(
        gate.get("key_digest"), "machine_evidence.gate.key_digest"
    )
    gate_id = _non_empty_string(gate.get("gate_id"), "machine_evidence.gate.gate_id")
    verification_ref = _content_address(
        gate.get("verification_ref"), "machine_evidence.gate.verification_ref"
    )
    subject_digest = _digest_payload(evidence["subject"])
    if gate.get("subject_digest") != subject_digest:
        raise LiveCodeIntelligenceError("machine evidence gate subject mismatch")
    gate_digest = _sha256_reference(
        gate.get("gate_digest"), "machine_evidence.gate.gate_digest"
    )
    if gate_digest != machine_evidence_gate_digest(gate):
        raise LiveCodeIntelligenceError("machine evidence gate digest mismatch")
    gate_ref = _content_address(
        registry.get("gate_ref"), "machine_evidence.registry.gate_ref"
    )
    if gate_ref != f"cas://{gate_digest}" or registry.get("gate_digest") != gate_digest:
        raise LiveCodeIntelligenceError(
            "machine evidence registry gate is not content-addressed"
        )

    signed_payload = _mapping(
        gate.get("signed_payload"), "machine_evidence.gate.signed_payload"
    )
    _exact_keys(
        signed_payload,
        {
            "schema_version",
            "owner",
            "gate_id",
            "state",
            "algorithm",
            "verification_method",
            "key_id",
            "key_digest",
            "verification_ref",
            "registry_record_ref",
            "registry_record_digest",
            "evidence_digest",
            "subject_digest",
            "provider_source_digest",
            "config_digest",
            "claim_limits_digest",
        },
        "machine_evidence.gate.signed_payload",
    )
    expected_signed_payload = {
        "schema_version": MACHINE_GATE_SIGNED_PAYLOAD_SCHEMA,
        "owner": "abyss-machine",
        "gate_id": gate_id,
        "state": "authenticated",
        "algorithm": MACHINE_GATE_ALGORITHM,
        "verification_method": MACHINE_GATE_VERIFICATION_METHOD,
        "key_id": key_id,
        "key_digest": key_digest,
        "verification_ref": verification_ref,
        "registry_record_ref": record_ref,
        "registry_record_digest": record_digest,
        "evidence_digest": evidence_digest,
        "subject_digest": subject_digest,
        "provider_source_digest": expected_provider_source_digest,
        "config_digest": expected_config_digest,
        "claim_limits_digest": _digest_payload(evidence["claim_limits"]),
    }
    if dict(signed_payload) != expected_signed_payload:
        raise LiveCodeIntelligenceError(
            "machine evidence gate signed payload does not bind the exact record"
        )
    signature = _base64_bytes(
        gate.get("signature"), "machine_evidence.gate.signature", length=64
    )
    bundle_digest = _sha256_reference(
        bundle.get("bundle_digest"), "machine_evidence.bundle_digest"
    )
    if bundle_digest != machine_evidence_bundle_digest(bundle):
        raise LiveCodeIntelligenceError("machine evidence bundle digest mismatch")

    trusted_key_id, trusted_key_digest, public_key = _machine_gate_trust_anchor()
    if key_id != trusted_key_id or key_digest != trusted_key_digest:
        raise LiveCodeIntelligenceError("machine evidence gate trust anchor mismatch")
    if not _ed25519_verify(
        public_key,
        signature,
        _canonical_json(signed_payload).encode("utf-8"),
    ):
        raise LiveCodeIntelligenceError("machine evidence gate signature is invalid")
    return _AuthenticatedMachineEvidence(
        evidence,
        validation_token=_MACHINE_EVIDENCE_VALIDATION_TOKEN,
    )


def _validate_machine_binding_payload(
    value: Any,
    *,
    label: str = "machine_binding",
) -> dict[str, Any]:
    """Validate the source-candidate machine contract without trusting claims.

    The runtime intentionally accepts only the authored source-candidate
    posture.  A machine-owned installation, trust, or admission result must
    arrive through the machine owner's separate admission route; arbitrary
    config strings cannot upgrade this source candidate.
    """

    raw = _mapping(value, label)
    _exact_keys(
        raw,
        {
            "schema_version",
            "owner",
            "installation_identity",
            "artifact_subject",
            "resource_envelope",
            "live_measurement",
        },
        label,
    )
    if raw.get("schema_version") != MACHINE_BINDING_SCHEMA:
        raise LiveCodeIntelligenceError(f"{label} schema mismatch")
    if raw.get("owner") != "abyss-machine":
        raise LiveCodeIntelligenceError(f"{label} owner mismatch")
    if raw.get("installation_identity") != MACHINE_INSTALLATION_IDENTITY:
        raise LiveCodeIntelligenceError(
            f"{label} installation identity is not the authored source candidate"
        )

    artifact_subject = _mapping(raw.get("artifact_subject"), f"{label}.artifact_subject")
    _exact_keys(
        artifact_subject,
        {"kind", "source_ref", "trust_state", "admission_state"},
        f"{label}.artifact_subject",
    )
    expected_artifact = {
        "kind": MACHINE_ARTIFACT_KIND,
        "source_ref": PROVIDER_ENTRYPOINT,
        "trust_state": MACHINE_TRUST_STATE,
        "admission_state": MACHINE_ADMISSION_STATE,
    }
    if dict(artifact_subject) != expected_artifact:
        raise LiveCodeIntelligenceError(
            f"{label}.artifact_subject is not the authored unadmitted source subject"
        )

    resource_envelope = _mapping(
        raw.get("resource_envelope"), f"{label}.resource_envelope"
    )
    _exact_keys(
        resource_envelope,
        {"max_file_bytes", "max_query_results"},
        f"{label}.resource_envelope",
    )
    _positive_integer(
        resource_envelope.get("max_file_bytes"),
        f"{label}.resource_envelope.max_file_bytes",
    )
    if resource_envelope.get("max_query_results") != MAX_QUERY_RESULTS:
        raise LiveCodeIntelligenceError(
            f"{label}.resource_envelope.max_query_results mismatch"
        )

    live_measurement = _mapping(
        raw.get("live_measurement"), f"{label}.live_measurement"
    )
    _exact_keys(
        live_measurement,
        {"required_for_admission", "state"},
        f"{label}.live_measurement",
    )
    if live_measurement.get("required_for_admission") is not True:
        raise LiveCodeIntelligenceError(
            f"{label}.live_measurement must require admission measurement"
        )
    if live_measurement.get("state") != MACHINE_LIVE_MEASUREMENT_STATE:
        raise LiveCodeIntelligenceError(
            f"{label}.live_measurement must remain unobserved"
        )
    return copy.deepcopy(dict(raw))


def _validate_config_payload(payload: Mapping[str, Any]) -> None:
    """Apply the exact fail-closed contract authored by the provider schema.

    This deliberately mirrors the small schema in stdlib code so the
    executable boundary does not become dependent on an optional validator
    package.  Constants below correspond to the schema's const constraints;
    shape and type checks mirror its required/additionalProperties rules.
    """

    _exact_keys(
        payload,
        {
            "$schema",
            "schema_version",
            "provider",
            "source",
            "state",
            "machine_binding",
            "owner_boundaries",
        },
        "provider config",
    )
    if payload.get("$schema") != CONFIG_SCHEMA_REF:
        raise LiveCodeIntelligenceError("provider config schema reference mismatch")
    if payload.get("schema_version") != CONFIG_SCHEMA:
        raise LiveCodeIntelligenceError("live provider config schema mismatch")

    provider = _mapping(payload.get("provider"), "provider")
    _exact_keys(
        provider,
        {
            "id",
            "version",
            "language",
            "mode",
            "observation_schema",
            "boundary_schema",
            "executable",
            "entrypoint",
            "protocol",
            "operations",
        },
        "provider",
    )
    expected_provider = {
        "id": PROVIDER_ID,
        "language": PROVIDER_LANGUAGE,
        "mode": PROVIDER_MODE,
        "observation_schema": OBSERVATION_SCHEMA,
        "boundary_schema": PROVIDER_BOUNDARY_SCHEMA,
        "executable": PROVIDER_EXECUTABLE,
        "entrypoint": PROVIDER_ENTRYPOINT,
        "protocol": PROVIDER_PROTOCOL,
        "operations": list(PROVIDER_OPERATIONS),
    }
    for key, expected in expected_provider.items():
        if provider.get(key) != expected:
            raise LiveCodeIntelligenceError(f"provider.{key} identity mismatch")
    _non_empty_string(provider.get("version"), "provider.version")
    if provider.get("version") != PROVIDER_VERSION:
        raise LiveCodeIntelligenceError("provider.version identity mismatch")

    source = _mapping(payload.get("source"), "source")
    _exact_keys(source, {"include_suffixes", "exclude_dirs", "max_file_bytes"}, "source")
    include_suffixes = source.get("include_suffixes")
    if not isinstance(include_suffixes, list) or not include_suffixes:
        raise LiveCodeIntelligenceError("source.include_suffixes must be a non-empty array")
    if any(
        not isinstance(item, str) or not item.startswith(".")
        for item in include_suffixes
    ):
        raise LiveCodeIntelligenceError("source.include_suffixes contains an invalid suffix")
    exclude_dirs = source.get("exclude_dirs")
    if not isinstance(exclude_dirs, list) or any(
        not isinstance(item, str) or not item for item in exclude_dirs
    ):
        raise LiveCodeIntelligenceError("source.exclude_dirs contains an invalid directory")
    _positive_integer(source.get("max_file_bytes"), "source.max_file_bytes")
    if source.get("max_file_bytes") != AUTHORED_MAX_FILE_BYTES:
        raise LiveCodeIntelligenceError(
            "source.max_file_bytes must match the authored machine resource envelope"
        )

    state = _mapping(payload.get("state"), "state")
    _exact_keys(state, {"relative_root", "promotion", "fallback"}, "state")
    relative_root = _non_empty_string(state.get("relative_root"), "state.relative_root")
    relative_path = Path(relative_root)
    if relative_path.is_absolute() or any(
        part in {"", ".", ".."} for part in relative_path.parts
    ) or "\\" in relative_root:
        raise LiveCodeIntelligenceError("state.relative_root must be a safe relative path")
    if state.get("promotion") != DEFAULT_STATE_PROMOTION:
        raise LiveCodeIntelligenceError("state.promotion identity mismatch")
    if state.get("fallback") != DEFAULT_STATE_FALLBACK:
        raise LiveCodeIntelligenceError("state.fallback identity mismatch")

    _validate_machine_binding_payload(payload.get("machine_binding"))

    owner_boundaries = _mapping(payload.get("owner_boundaries"), "owner_boundaries")
    _exact_keys(
        owner_boundaries,
        {key for key, _ in DEFAULT_OWNER_BOUNDARIES},
        "owner_boundaries",
    )
    expected_boundaries = dict(DEFAULT_OWNER_BOUNDARIES)
    if dict(owner_boundaries) != expected_boundaries:
        raise LiveCodeIntelligenceError("owner_boundaries identity mismatch")


def _safe_relative(path: Path, root: Path, label: str) -> str:
    try:
        resolved = path.expanduser().resolve()
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise LiveCodeIntelligenceError(f"{label} escapes source root") from exc
    if not relative.parts:
        raise LiveCodeIntelligenceError(f"{label} must name a file")
    return relative.as_posix()


def _location(node: ast.AST) -> dict[str, int]:
    return {
        "start_line": int(getattr(node, "lineno", 1)),
        "start_column": int(getattr(node, "col_offset", 0)),
        "end_line": int(getattr(node, "end_lineno", getattr(node, "lineno", 1))),
        "end_column": int(
            getattr(node, "end_col_offset", getattr(node, "col_offset", 0))
        ),
    }


def _anchor(path: str, location: Mapping[str, int]) -> str:
    return (
        f"{path}#L{location['start_line']}:{location['start_column']}"
        f"-L{location['end_line']}:{location['end_column']}"
    )


def _anchor_is_well_formed(value: Any, path: str) -> bool:
    """Check a persisted AST anchor without treating it as semantic identity."""

    if not isinstance(value, str):
        return False
    prefix = f"{path}#L"
    if not value.startswith(prefix):
        return False
    coordinates = value[len(prefix) :]
    try:
        start, end = coordinates.split("-L", 1)
        start_line, start_column = start.split(":", 1)
        end_line, end_column = end.split(":", 1)
    except ValueError:
        return False

    def decimal(text: str) -> bool:
        return bool(text) and all(character in "0123456789" for character in text)

    if not all(
        decimal(item)
        for item in (start_line, start_column, end_line, end_column)
    ):
        return False
    return int(start_line) >= 1 and int(end_line) >= 1


def _expression_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _expression_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _module_name(path: str) -> str:
    stem = path.replace("\\", "/")
    if stem.startswith("src/"):
        stem = stem.removeprefix("src/")
    for suffix in (".py", ".pyi"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    parts = [part for part in stem.split("/") if part]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def _module_name_variants(
    path: str,
    known_paths: Collection[str] | None = None,
) -> set[str]:
    """Return stable module identities for common and discovered import roots.

    Source-relative paths are retained as one identity for backwards
    compatibility.  A package marker or a conventional import-root directory
    additionally yields the identity that a Python import statement uses when
    the working tree is mounted with that directory on ``sys.path``.
    """

    normalized = path.replace("\\", "/")
    stem = normalized
    for suffix in (".py", ".pyi"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    parts = [part for part in stem.split("/") if part]
    if not parts:
        return {"__root__"}
    is_package_init = parts[-1] == "__init__"
    module_parts = parts[:-1] if is_package_init else parts
    if not module_parts:
        return {"__root__"}
    known = {
        item.replace("\\", "/").lstrip("./")
        for item in (known_paths or ())
        if isinstance(item, str)
    }
    variants = {_module_name(path)}
    # A conventional root is an explicit, source-local convention and does
    # not need an __init__.py marker (e.g. src/pkg/mod.py).
    for index, part in enumerate(module_parts[:-1] if not is_package_init else module_parts):
        if part not in _KNOWN_PYTHON_IMPORT_ROOTS:
            continue
        stripped = module_parts[index + 1 :]
        if stripped:
            variants.add(".".join(stripped))

    # Otherwise discover a package root from the source manifest.  For a
    # regular module, the package marker is the directory containing it.  For
    # __init__.py, the marker is the module itself.
    marker_directory_end = len(parts) - 1 if not is_package_init else len(parts)
    for start in range(1, marker_directory_end):
        for marker_end in range(start + 1, marker_directory_end + 1):
            marker = "/".join(parts[start:marker_end] + ["__init__.py"])
            if marker in known:
                candidate = module_parts[start:]
                if candidate:
                    variants.add(".".join(candidate))
                break
    return {variant for variant in variants if variant}


def _symbol_id(
    path: str,
    kind: str,
    qualified_name: str,
    definition: str | None = None,
) -> str:
    identity = f"{PROVIDER_ID}:{path}:{kind}:{qualified_name}:{definition or ''}".encode("utf-8")
    return f"symbol:python:{hashlib.sha256(identity).hexdigest()}"


def _unresolved_id(name: str) -> str:
    return f"unresolved:python-name:{name}"


class _PythonObservationVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.scope_names: list[str] = []
        self.scope_ids: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.occurrences: list[dict[str, Any]] = []
        self.relations: list[dict[str, Any]] = []
        module_name = _module_name(path)
        module_id = _symbol_id(path, "module", module_name)
        self.symbols.append(
            {
                "id": module_id,
                "handle": f"python://{path}#{module_name}",
                "name": module_name,
                "qualified_name": module_name,
                "kind": "module",
                "identity_scope": "path-qualified",
                "lineage": {
                    "status": "unresolved",
                    "reason": "bootstrap provider does not infer rename or move continuity",
                    "confidence": "none",
                },
            }
        )
        self.scope_ids.append(module_id)

    @property
    def current_id(self) -> str:
        return self.scope_ids[-1]

    @property
    def current_qualified_name(self) -> str:
        return ".".join(self.scope_names) or _module_name(self.path)

    def _relation(
        self,
        relation_kind: str,
        target: str,
        node: ast.AST,
        *,
        confidence: str,
        target_id: str | None = None,
    ) -> None:
        location = _location(node)
        relation_id = _digest_payload(
            {
                "kind": relation_kind,
                "source": self.current_id,
                "target": target,
                "anchor": _anchor(self.path, location),
            }
        )
        self.relations.append(
            {
                "id": f"relation:python:{relation_id.removeprefix('sha256:')}",
                "relation_kind": relation_kind,
                "from_id": self.current_id,
                "to_id": target_id or _unresolved_id(target),
                "target": target,
                "occurrence": _anchor(self.path, location),
                "confidence": confidence,
                "provenance": "python-ast",
            }
        )

    def _definition(self, node: ast.AST, name: str, kind: str) -> str:
        qualified_name = ".".join((*self.scope_names, name))
        location = _location(node)
        definition = _anchor(self.path, location)
        symbol_id = _symbol_id(self.path, kind, qualified_name, definition)
        self.symbols.append(
            {
                "id": symbol_id,
                "handle": f"python://{self.path}#{qualified_name}@{definition.split('#', 1)[1]}",
                "name": name,
                "qualified_name": qualified_name,
                "kind": kind,
                "identity_scope": "path-qualified",
                "lineage": {
                    "status": "unresolved",
                    "reason": "bootstrap provider does not infer rename or move continuity",
                    "confidence": "none",
                },
                "definition": definition,
            }
        )
        self.occurrences.append(
            {
                "kind": "definition",
                "name": name,
                "symbol_id": symbol_id,
                "scope_id": self.current_id,
                "location": _anchor(self.path, location),
                "confidence": "high",
            }
        )
        self._relation(
            "contains",
            qualified_name,
            node,
            confidence="high",
            target_id=symbol_id,
        )
        return symbol_id

    def _visit_definition_expressions(self, node: ast.AST) -> None:
        for decorator in getattr(node, "decorator_list", ()):
            self.visit(decorator)
        for type_parameter in getattr(node, "type_params", ()):
            self.visit(type_parameter)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
                if argument.annotation is not None:
                    self.visit(argument.annotation)
            if arguments.vararg is not None and arguments.vararg.annotation is not None:
                self.visit(arguments.vararg.annotation)
            if arguments.kwarg is not None and arguments.kwarg.annotation is not None:
                self.visit(arguments.kwarg.annotation)
            for default in (*arguments.defaults, *arguments.kw_defaults):
                if default is not None:
                    self.visit(default)
            if node.returns is not None:
                self.visit(node.returns)
        elif isinstance(node, ast.ClassDef):
            for base in node.bases:
                self.visit(base)
            for keyword in node.keywords:
                self.visit(keyword.value)

    def _visit_definition(self, node: ast.AST, name: str, kind: str) -> None:
        self._visit_definition_expressions(node)
        symbol_id = self._definition(node, name, kind)
        self.scope_names.append(name)
        self.scope_ids.append(symbol_id)
        for statement in node.body:  # type: ignore[attr-defined]
            self.visit(statement)
        self.scope_ids.pop()
        self.scope_names.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_definition(node, node.name, "class")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_definition(node, node.name, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_definition(node, node.name, "function")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            imported = alias.name
            self.occurrences.append(
                {
                    "kind": "import",
                    "name": imported,
                    "scope_id": self.current_id,
                    "location": _anchor(self.path, _location(node)),
                    "confidence": "high",
                }
            )
            self._relation("imports", imported, alias, confidence="high")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * int(node.level) + (node.module or "")
        for alias in node.names:
            if node.module:
                imported = f"{module}.{alias.name}"
            else:
                # ``from . import name`` has no module component. Avoid
                # manufacturing an extra leading dot, which would break
                # dependency invalidation for package-level imports.
                imported = f"{'.' * int(node.level)}{alias.name}"
            self.occurrences.append(
                {
                    "kind": "import",
                    "name": imported,
                    "scope_id": self.current_id,
                    "location": _anchor(self.path, _location(node)),
                    "confidence": "high",
                }
            )
            self._relation("imports", imported, alias, confidence="high")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        target = _expression_name(node.func)
        if target:
            self._relation("calls", target, node.func, confidence="medium")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        context = node.ctx.__class__.__name__.lower()
        role = "read" if isinstance(node.ctx, ast.Load) else "write"
        self.occurrences.append(
            {
                "kind": "reference",
                "name": node.id,
                "role": role,
                "scope_id": self.current_id,
                "location": _anchor(self.path, _location(node)),
                "confidence": "medium" if role == "read" else "high",
                "context": context,
            }
        )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        context = node.ctx.__class__.__name__.lower()
        role = "read" if isinstance(node.ctx, ast.Load) else "write"
        self.occurrences.append(
            {
                "kind": "reference",
                "name": node.attr,
                "role": role,
                "scope_id": self.current_id,
                "location": _anchor(self.path, _location(node)),
                "confidence": "medium" if role == "read" else "high",
                "context": context,
            }
        )
        self.visit(node.value)


def _parse_file(path: str, content: bytes) -> dict[str, Any]:
    digest = _digest_bytes(content)
    base: dict[str, Any] = {
        "path": path,
        "content_digest": digest,
        "size_bytes": len(content),
    }
    try:
        tree = ast.parse(content, filename=path)
    except (MemoryError, RecursionError, SystemError) as exc:
        return {
            **base,
            "observation": None,
            "diagnostics": [
                {
                    "code": "python_parse_resource_error",
                    "severity": "error",
                    "message": type(exc).__name__,
                }
            ],
        }
    except (SyntaxError, UnicodeDecodeError, ValueError, TypeError) as exc:
        message = str(exc).splitlines()[0][:240] or exc.__class__.__name__
        return {
            **base,
            "observation": None,
            "diagnostics": [
                {
                    "code": "python_parse_error",
                    "severity": "error",
                    "message": message,
                }
            ],
        }
    visitor = _PythonObservationVisitor(path)
    try:
        visitor.visit(tree)
    except (MemoryError, RecursionError, SystemError) as exc:
        return {
            **base,
            "observation": None,
            "diagnostics": [
                {
                    "code": "python_ast_traversal_error",
                    "severity": "error",
                    "message": type(exc).__name__,
                }
            ],
        }
    return {
        **base,
        "observation": {
            "schema_version": OBSERVATION_SCHEMA,
            "state": "live",
            "provider": {
                "id": PROVIDER_ID,
                "version": PROVIDER_VERSION,
                "language": PROVIDER_LANGUAGE,
            },
            "source": {
                "path": path,
                "content_digest": digest,
                "epoch_binding": "state.source.source_epoch",
            },
            "symbols": sorted(visitor.symbols, key=lambda item: item["id"]),
            "occurrences": sorted(
                visitor.occurrences,
                key=lambda item: (item["location"], item["kind"], item["name"]),
            ),
            "relations": sorted(visitor.relations, key=lambda item: item["id"]),
            "provenance": {
                "source_kind": "working_tree",
                "semantic_owner": "aoa-kag",
                "runtime_owner": "abyss-stack",
            },
        },
        "diagnostics": [],
    }


def _file_map(value: Any) -> dict[str, dict[str, Any]]:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if isinstance(item, Mapping):
                result[str(key)] = dict(item)
        return result
    if isinstance(value, list):
        result = {}
        for item in value:
            if isinstance(item, Mapping) and isinstance(item.get("path"), str):
                result[item["path"]] = dict(item)
        return result
    return {}


def _state_files(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return _file_map(state.get("files"))


@dataclass(frozen=True)
class LiveCodeIntelligenceConfig:
    source_root: Path
    state_root: Path
    provider_id: str = PROVIDER_ID
    provider_version: str = PROVIDER_VERSION
    provider_executable: str = "python3"
    provider_entrypoint: str = PROVIDER_ENTRYPOINT
    provider_protocol: str = PROVIDER_PROTOCOL
    provider_operations: tuple[str, ...] = PROVIDER_OPERATIONS
    include_suffixes: tuple[str, ...] = (".py",)
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS
    max_file_bytes: int = AUTHORED_MAX_FILE_BYTES
    state_relative_root: str = DEFAULT_STATE_RELATIVE_ROOT
    state_promotion: str = DEFAULT_STATE_PROMOTION
    state_fallback: str = DEFAULT_STATE_FALLBACK
    machine_binding: Mapping[str, Any] = field(
        default_factory=lambda: copy.deepcopy(DEFAULT_MACHINE_BINDING)
    )
    owner_boundaries: tuple[tuple[str, str], ...] = DEFAULT_OWNER_BOUNDARIES
    machine_evidence: Mapping[str, Any] | None = None
    # Launch snapshots are process-local materialization, not provider state.
    # The owner must bind them to an explicit machine scratch route; keeping
    # this out of config_identity means a storage routing choice cannot alter
    # the admitted provider/config digest.
    launch_scratch_root: Path | None = None

    def __post_init__(self) -> None:
        source_input = Path(self.source_root).expanduser()
        state_input = Path(self.state_root).expanduser()
        if _contains_symlink(source_input):
            raise LiveCodeIntelligenceError("source root must not contain symlinks")
        if _contains_symlink(state_input):
            raise LiveCodeIntelligenceError("state root must not contain symlinks")
        source_root = source_input.resolve()
        state_root = state_input.resolve()
        object.__setattr__(self, "source_root", source_root)
        object.__setattr__(self, "state_root", state_root)
        if self.launch_scratch_root is not None:
            scratch_input = Path(self.launch_scratch_root).expanduser()
            if not scratch_input.is_absolute():
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must be an absolute path"
                )
            if _contains_symlink(scratch_input):
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must not contain symlinks"
                )
            object.__setattr__(self, "launch_scratch_root", scratch_input.resolve())
        if not source_root.is_dir():
            raise LiveCodeIntelligenceError(
                f"source root does not exist: {source_root}"
            )
        try:
            state_root.relative_to(source_root)
        except ValueError:
            pass
        else:
            raise LiveCodeIntelligenceError(
                "state root must be outside the source root"
            )
        if not self.provider_id or not self.provider_version:
            raise LiveCodeIntelligenceError("provider identity is required")
        if self.provider_id != PROVIDER_ID:
            raise LiveCodeIntelligenceError("provider id identity mismatch")
        if self.provider_version != PROVIDER_VERSION:
            raise LiveCodeIntelligenceError("provider version identity mismatch")
        if self.provider_executable != PROVIDER_EXECUTABLE:
            raise LiveCodeIntelligenceError("provider executable identity mismatch")
        if self.provider_entrypoint != PROVIDER_ENTRYPOINT:
            raise LiveCodeIntelligenceError("provider entrypoint identity mismatch")
        if self.provider_protocol != PROVIDER_PROTOCOL:
            raise LiveCodeIntelligenceError("provider protocol identity mismatch")
        if not self.provider_executable or not self.provider_protocol:
            raise LiveCodeIntelligenceError("provider executable and protocol are required")
        if (
            not self.provider_entrypoint
            or Path(self.provider_entrypoint).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(self.provider_entrypoint).parts)
        ):
            raise LiveCodeIntelligenceError(
                "provider entrypoint must be a non-empty safe relative path"
            )
        try:
            operations = tuple(self.provider_operations)
            include_suffixes = tuple(self.include_suffixes)
            exclude_dirs = tuple(self.exclude_dirs)
        except (TypeError, ValueError) as exc:
            raise LiveCodeIntelligenceError(
                "provider operations, suffixes, and excluded directories must be arrays"
            ) from exc
        if operations != PROVIDER_OPERATIONS:
            raise LiveCodeIntelligenceError("provider operations are required")
        object.__setattr__(self, "provider_operations", operations)
        object.__setattr__(self, "include_suffixes", include_suffixes)
        object.__setattr__(self, "exclude_dirs", exclude_dirs)
        if include_suffixes != (".py",):
            raise LiveCodeIntelligenceError(
                "the Python bootstrap provider requires the .py source suffix"
            )
        if any(
            not isinstance(suffix, str) or not suffix.startswith(".")
            for suffix in include_suffixes
        ):
            raise LiveCodeIntelligenceError("include_suffixes must contain extensions")
        _positive_integer(self.max_file_bytes, "max_file_bytes")
        if self.max_file_bytes > AUTHORED_MAX_FILE_BYTES:
            raise LiveCodeIntelligenceError(
                "max_file_bytes exceeds the authored machine resource envelope"
            )
        if any(
            not isinstance(directory, str) or not directory
            for directory in exclude_dirs
        ):
            raise LiveCodeIntelligenceError("exclude_dirs must contain names")
        if (
            not isinstance(self.state_relative_root, str)
            or not self.state_relative_root.strip()
            or Path(self.state_relative_root).is_absolute()
            or any(part in {"", ".", ".."} for part in Path(self.state_relative_root).parts)
            or "\\" in self.state_relative_root
        ):
            raise LiveCodeIntelligenceError(
                "state_relative_root must be a non-empty relative path"
            )
        if self.state_promotion != DEFAULT_STATE_PROMOTION:
            raise LiveCodeIntelligenceError("state promotion identity mismatch")
        if self.state_fallback != DEFAULT_STATE_FALLBACK:
            raise LiveCodeIntelligenceError("state fallback identity mismatch")
        machine_binding = _validate_machine_binding_payload(self.machine_binding)
        if (
            machine_binding["resource_envelope"]["max_file_bytes"]
            != self.max_file_bytes
        ):
            raise LiveCodeIntelligenceError(
                "source max_file_bytes must match the machine resource envelope"
            )
        object.__setattr__(self, "machine_binding", machine_binding)
        raw_boundaries = self.owner_boundaries
        if isinstance(raw_boundaries, Mapping):
            boundary_items = tuple(raw_boundaries.items())
        else:
            boundary_items = raw_boundaries
        normalized_boundaries: list[tuple[str, str]] = []
        try:
            for key, value in boundary_items:
                key_text = str(key)
                value_text = str(value)
                if not key_text or not value_text:
                    raise LiveCodeIntelligenceError(
                        "owner boundary keys and values are required"
                    )
                normalized_boundaries.append((key_text, value_text))
        except (TypeError, ValueError) as exc:
            raise LiveCodeIntelligenceError(
                "owner_boundaries must contain key/value pairs"
            ) from exc
        if not normalized_boundaries:
            raise LiveCodeIntelligenceError("owner_boundaries are required")
        if dict(normalized_boundaries) != dict(DEFAULT_OWNER_BOUNDARIES):
            raise LiveCodeIntelligenceError("owner_boundaries identity mismatch")
        object.__setattr__(
            self,
            "owner_boundaries",
            tuple(sorted(normalized_boundaries)),
        )
        if self.machine_evidence is not None:
            raise LiveCodeIntelligenceError(
                "machine evidence may only enter through the owner-authenticated gate"
            )

    @classmethod
    def from_file(
        cls,
        config_path: str | Path,
        *,
        source_root: str | Path,
        state_root: str | Path,
        machine_evidence_path: str | Path | None = None,
        launch_scratch_root: str | Path | None = None,
    ) -> "LiveCodeIntelligenceConfig":
        config_input = Path(config_path).expanduser()
        if _contains_symlink(config_input):
            raise LiveCodeIntelligenceError(
                "provider config path must not contain symlinks"
            )
        payload = _read_json(config_input)
        _validate_config_payload(payload)
        provider = _mapping(payload.get("provider"), "provider")
        source = _mapping(payload.get("source"), "source")
        state = _mapping(payload.get("state") or {}, "state")
        owner_boundaries = _mapping(
            payload.get("owner_boundaries") or {}, "owner_boundaries"
        )
        suffixes = tuple(source["include_suffixes"])
        excluded = tuple(source["exclude_dirs"])
        config = cls(
            source_root=Path(source_root),
            state_root=Path(state_root),
            provider_id=provider["id"],
            provider_version=provider["version"],
            provider_executable=provider["executable"],
            provider_entrypoint=provider["entrypoint"],
            provider_protocol=provider["protocol"],
            provider_operations=tuple(provider["operations"]),
            include_suffixes=suffixes,
            exclude_dirs=excluded,
            max_file_bytes=source["max_file_bytes"],
            state_relative_root=state["relative_root"],
            state_promotion=state["promotion"],
            state_fallback=state["fallback"],
            machine_binding=payload["machine_binding"],
            owner_boundaries=tuple(owner_boundaries.items()),
            launch_scratch_root=launch_scratch_root,
        )
        if machine_evidence_path is None:
            return config
        supplied_evidence_path = Path(machine_evidence_path).expanduser()
        if _contains_symlink(supplied_evidence_path):
            raise LiveCodeIntelligenceError(
                "machine evidence path must not contain symlinks"
            )
        evidence_path = supplied_evidence_path.resolve()
        if not evidence_path.is_file():
            raise LiveCodeIntelligenceError(
                "machine evidence path must be a real regular file"
            )
        try:
            evidence_path.relative_to(config.source_root)
        except ValueError:
            pass
        else:
            raise LiveCodeIntelligenceError(
                "machine evidence must be supplied outside the source root"
            )
        evidence = _validate_machine_evidence_gate_bundle(
            _read_json(evidence_path),
            expected_provider=config.provider_identity,
            expected_provider_source_digest=config.provider_source_digest,
            expected_config_digest=config.config_digest,
        )
        if not isinstance(evidence, _AuthenticatedMachineEvidence):
            evidence = _AuthenticatedMachineEvidence(
                evidence,
                validation_token=_MACHINE_EVIDENCE_VALIDATION_TOKEN,
            )
        # The value has passed the detached signature and content-addressed
        # registry checks above.  Install it only after the ordinary config
        # constructor has rejected every direct caller-supplied mapping.
        object.__setattr__(config, "machine_evidence", evidence)
        return config

    @property
    def provider_identity(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "version": self.provider_version,
            "language": PROVIDER_LANGUAGE,
            "mode": PROVIDER_MODE,
            "observation_schema": OBSERVATION_SCHEMA,
            "boundary_schema": PROVIDER_BOUNDARY_SCHEMA,
            "executable": self.provider_executable,
            "entrypoint": self.provider_entrypoint,
            "protocol": self.provider_protocol,
            "operations": list(self.provider_operations),
        }

    @property
    def provider_source_digest(self) -> str:
        try:
            return _digest_bytes(Path(__file__).resolve().read_bytes())
        except (OSError, UnicodeError):
            return "unavailable"

    @property
    def machine_binding_identity(self) -> dict[str, Any]:
        return _validate_machine_binding_payload(self.machine_binding)

    @property
    def config_identity(self) -> dict[str, Any]:
        return {
            "schema_version": CONFIG_SCHEMA,
            "provider": self.provider_identity,
            "provider_source_digest": self.provider_source_digest,
            "source": {
                "include_suffixes": list(self.include_suffixes),
                "exclude_dirs": list(self.exclude_dirs),
                "max_file_bytes": self.max_file_bytes,
            },
            "state": {
                "relative_root": self.state_relative_root,
                "promotion": self.state_promotion,
                "fallback": self.state_fallback,
            },
            "machine_binding": self.machine_binding_identity,
            "owner_boundaries": dict(self.owner_boundaries),
        }

    @property
    def config_digest(self) -> str:
        return _digest_payload(self.config_identity)


@dataclass(frozen=True)
class _ProviderWorkItem:
    """One source file handed to the local provider worker."""

    path: str
    metadata: Mapping[str, Any]


class _ProviderWorkQueue:
    """A bounded, deterministic queue for one refresh pass.

    The queue is deliberately local to the stack-owned runtime. It does not
    launch a process, activate an installed provider, or turn queue delivery
    into machine admission evidence. Refresh holds the state lock while the
    queue is drained, so candidate/current/last-good promotion remains one
    serialized transition.
    """

    def __init__(self, *, capacity: int = PROVIDER_QUEUE_CAPACITY) -> None:
        if capacity < 1:
            raise ValueError("provider work queue capacity must be positive")
        self.capacity = capacity
        self._items: deque[_ProviderWorkItem] = deque()

    def enqueue(self, item: _ProviderWorkItem) -> None:
        if len(self._items) >= self.capacity:
            raise LiveCodeIntelligenceError(
                "provider work queue capacity exceeded"
            )
        self._items.append(item)

    def dequeue(self) -> _ProviderWorkItem:
        try:
            return self._items.popleft()
        except IndexError as exc:
            raise LiveCodeIntelligenceError(
                "provider work queue is empty"
            ) from exc

    def __bool__(self) -> bool:
        return bool(self._items)

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class _LspLaunchBinding:
    """The immutable launch inputs handed to one LSP child."""

    command: tuple[str, ...]
    pass_fds: tuple[int, ...]
    runtime_root: Path
    snapshot_root: Path


class _BoundedQueryRows:
    """Retain only the deterministic prefix needed by one bounded query."""

    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("query result limit must be positive")
        self.limit = limit
        self.total_results = 0
        self._entries: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    def add(self, row: dict[str, Any], key: tuple[str, ...]) -> None:
        """Count one match while retaining only the smallest sorted prefix."""

        self.total_results += 1
        entry = (key, row)
        if len(self._entries) < self.limit:
            self._entries.append(entry)
            return
        worst_index = max(
            range(len(self._entries)),
            key=lambda index: self._entries[index][0],
        )
        if key < self._entries[worst_index][0]:
            self._entries[worst_index] = entry

    @property
    def rows(self) -> list[dict[str, Any]]:
        """Return the retained rows in the same order as the old full sort."""

        return [
            row
            for _, row in sorted(self._entries, key=lambda entry: entry[0])
        ]


class ManagedLspSession:
    """One admitted, bounded stdio LSP session with observable restart state.

    The stack owns the process lifecycle, but may start only an executable
    already identified by an abyss-machine admission result. JSON-RPC payloads
    remain provider output; they do not become KAG meaning or proof here.
    """

    def __init__(
        self,
        command: Sequence[str],
        *,
        provider_id: str,
        language: str,
        source_epoch: str,
        admission_config: LiveCodeIntelligenceConfig,
        runtime_root: Path = Path("/srv/abyss-machine/runtimes/code-intelligence"),
        launch_scratch_root: Path | None = None,
        request_timeout: float = 10.0,
        max_message_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        if not command:
            raise LiveCodeIntelligenceError("LSP command must not be empty")
        executable = Path(command[0]).expanduser().resolve()
        runtime_root_input = Path(runtime_root).expanduser()
        if _contains_symlink(runtime_root_input):
            raise LiveCodeIntelligenceError(
                "LSP runtime root must not contain symlinks"
            )
        root = runtime_root_input.resolve()
        try:
            executable.relative_to(root)
        except ValueError as exc:
            raise LiveCodeIntelligenceError(
                "LSP executable must remain inside the admitted machine runtime root"
            ) from exc
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise LiveCodeIntelligenceError("LSP executable is not runnable")
        configured_scratch_root = (
            launch_scratch_root
            if launch_scratch_root is not None
            else admission_config.launch_scratch_root
        )
        scratch_root: Path | None = None
        if configured_scratch_root is not None:
            scratch_input = Path(configured_scratch_root).expanduser()
            if not scratch_input.is_absolute():
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must be an absolute path"
                )
            if _contains_symlink(scratch_input):
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must not contain symlinks"
                )
            scratch_root = scratch_input.resolve()
            try:
                scratch_root.relative_to(root)
            except ValueError:
                pass
            else:
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must remain outside the admitted runtime root"
                )
            try:
                scratch_root.relative_to(admission_config.source_root)
            except ValueError:
                pass
            else:
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root must remain outside the admitted source root"
                )
        provider_id = _non_empty_string(provider_id, "provider_id")
        language = _non_empty_string(language, "language")
        source_epoch = _non_empty_string(source_epoch, "source_epoch")
        evidence = admission_config.machine_evidence
        if not isinstance(evidence, _AuthenticatedMachineEvidence):
            raise LiveCodeIntelligenceError(
                "LSP session requires evidence returned by the owner-authenticated machine gate"
            )
        try:
            _require_fresh_machine_health(evidence)
        except LiveCodeIntelligenceError as exc:
            raise LiveCodeIntelligenceError(
                "LSP session requires fresh machine health evidence"
            ) from exc
        admission = _mapping(evidence.get("admission"), "machine_evidence.admission")
        providers = evidence.get("providers")
        sessions = evidence.get("lsp_sessions")
        provider_bound = isinstance(providers, list) and any(
            isinstance(item, Mapping)
            and item.get("id") == provider_id
            and item.get("language") == language
            and item.get("protocol") == "lsp"
            and item.get("observation_state") in {"available", "observed"}
            for item in providers
        )
        bound_session = (
            next(
                (
                    item
                    for item in sessions
                    if isinstance(item, Mapping)
                    and item.get("provider_id") == provider_id
                    and item.get("language") == language
                    and item.get("source_epoch") == source_epoch
                    and item.get("state") == "observed"
                    and item.get("transport") == "stdio"
                    and item.get("source_root") == str(admission_config.source_root)
                ),
                None,
            )
            if isinstance(sessions, list)
            else None
        )
        if (
            admission.get("owner") != "abyss-machine"
            or admission.get("state") != "admitted"
            or admission.get("trust_state") != "trusted"
            or not isinstance(admission.get("admission_ref"), str)
            or not admission.get("admission_ref")
            or not provider_bound
            or bound_session is None
        ):
            raise LiveCodeIntelligenceError(
                "LSP session is not bound to an admitted provider and source epoch"
            )
        runtime_manifest = _validated_file_manifest(
            bound_session.get("runtime_manifest"),
            "machine_evidence.lsp_sessions.runtime_manifest",
            allow_empty=True,
        )
        if not runtime_manifest:
            raise LiveCodeIntelligenceError(
                "LSP session requires an admitted runtime dependency manifest"
            )
        source_manifest = _validated_file_manifest(
            bound_session.get("source_manifest"),
            "machine_evidence.lsp_sessions.source_manifest",
            allow_empty=True,
        )
        if _directory_file_manifest(root, "LSP runtime dependency root") != runtime_manifest:
            raise LiveCodeIntelligenceError(
                "LSP runtime dependency manifest does not match the admitted root"
            )
        self.command = (str(executable), *(str(item) for item in command[1:]))
        command_digest = _digest_payload(list(self.command))
        admitted_command_digest = (
            bound_session.get("command_digest") if bound_session is not None else None
        )
        if admitted_command_digest is None:
            if len(self.command) > 1:
                raise LiveCodeIntelligenceError(
                    "LSP command arguments require an admitted command digest"
                )
        elif admitted_command_digest != command_digest:
            raise LiveCodeIntelligenceError(
                "LSP command does not match admitted machine evidence"
            )
        interpreter = _shebang_interpreter(executable)
        admitted_interpreter_digest = (
            bound_session.get("interpreter_digest") if bound_session is not None else None
        )
        interpreter_digest: str | None = None
        if interpreter is not None:
            if admitted_interpreter_digest is None:
                raise LiveCodeIntelligenceError(
                    "LSP script requires an admitted interpreter digest"
                )
            interpreter_digest = _sha256_reference(
                admitted_interpreter_digest,
                "machine_evidence.lsp_sessions.interpreter_digest",
            )
        self.provider_id = provider_id
        self.language = language
        self.source_epoch = source_epoch
        self.admission_ref = str(admission["admission_ref"])
        subject = _mapping(evidence.get("subject"), "machine_evidence.subject")
        subject_provider = _mapping(
            subject.get("provider"), "machine_evidence.subject.provider"
        )
        session_artifact_digest = bound_session.get("artifact_digest")
        if session_artifact_digest is None:
            if subject_provider.get("id") != provider_id:
                raise LiveCodeIntelligenceError(
                    "LSP session lacks an admitted artifact digest for its provider"
                )
            session_artifact_digest = subject.get("artifact_digest")
            session_artifact_label = "machine_evidence.subject.artifact_digest"
        else:
            session_artifact_label = "machine_evidence.lsp_sessions.artifact_digest"
        self.admitted_artifact_digest = _sha256_reference(
            session_artifact_digest,
            session_artifact_label,
        )
        self.executable_digest = _digest_bytes(executable.read_bytes())
        if self.executable_digest != self.admitted_artifact_digest:
            raise LiveCodeIntelligenceError(
                "LSP executable does not match the admitted artifact"
            )
        if interpreter is not None:
            actual_interpreter_digest = _digest_bytes(interpreter.read_bytes())
            if actual_interpreter_digest != interpreter_digest:
                raise LiveCodeIntelligenceError(
                    "LSP script interpreter does not match admitted machine evidence"
                )
        self._admission_config = admission_config
        self._machine_evidence = evidence
        self.source_root = admission_config.source_root
        self._working_directory = root
        self._runtime_manifest = runtime_manifest
        self._source_manifest = dict(source_manifest)
        self._interpreter_path = interpreter
        self._interpreter_digest = interpreter_digest
        self.request_timeout = max(0.1, float(request_timeout))
        self.max_message_bytes = max(1024, int(max_message_bytes))
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=PROVIDER_QUEUE_CAPACITY
        )
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._request_id = 0
        self._generation = 0
        self._restart_count = 0
        self._started_at: str | None = None
        self._last_good_at: str | None = None
        self._client_capabilities: dict[str, Any] = {}
        self._last_error: str | None = None
        self._closing = False
        self._lifecycle_lock = threading.RLock()
        self._launch_snapshot_root: Path | None = None
        self._launch_scratch_root = scratch_root

    def _bound_machine_session(
        self, evidence: Mapping[str, Any]
    ) -> Mapping[str, Any] | None:
        sessions = evidence.get("lsp_sessions")
        if not isinstance(sessions, list):
            return None
        return next(
            (
                item
                for item in sessions
                if isinstance(item, Mapping)
                and item.get("provider_id") == self.provider_id
                and item.get("language") == self.language
                and item.get("source_epoch") == self.source_epoch
                and item.get("state") == "observed"
                and item.get("transport") == "stdio"
                and item.get("source_root") == str(self.source_root)
            ),
            None,
        )

    def _bound_artifact_digest(
        self,
        evidence: Mapping[str, Any],
        bound_session: Mapping[str, Any],
    ) -> str:
        subject = _mapping(evidence.get("subject"), "machine_evidence.subject")
        session_artifact_digest = bound_session.get("artifact_digest")
        if session_artifact_digest is None:
            subject_provider = _mapping(
                subject.get("provider"), "machine_evidence.subject.provider"
            )
            if subject_provider.get("id") != self.provider_id:
                raise LiveCodeIntelligenceError(
                    "LSP session lacks an admitted artifact digest for its provider"
                )
            session_artifact_digest = subject.get("artifact_digest")
            label = "machine_evidence.subject.artifact_digest"
        else:
            label = "machine_evidence.lsp_sessions.artifact_digest"
        return _sha256_reference(session_artifact_digest, label)

    def _send(self, payload: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None or process.poll() is not None:
            raise LiveCodeIntelligenceError("LSP session is not running")
        body = _canonical_json(payload).encode("utf-8")
        if len(body) > self.max_message_bytes:
            raise LiveCodeIntelligenceError("LSP request exceeds the bounded message size")
        frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
        with self._write_lock:
            try:
                process.stdin.write(frame)
                process.stdin.flush()
            except OSError as exc:
                self._last_error = str(exc)
                raise LiveCodeIntelligenceError("unable to write to LSP session") from exc

    def _validate_request_uri(self, value: Any, label: str) -> None:
        path = _file_uri_path(value, label)
        try:
            path.relative_to(self.source_root)
        except ValueError as exc:
            raise LiveCodeIntelligenceError(
                "LSP request URI must remain inside the admitted source root"
            ) from exc
        if path != self.source_root and path.exists() and path.is_dir():
            raise LiveCodeIntelligenceError(
                "LSP request URI must identify a file inside the admitted source root"
            )

    def _validate_request_params(self, params: Mapping[str, Any]) -> None:
        """Validate every URI-bearing value before an arbitrary request leaves."""

        if not isinstance(params, Mapping):
            raise LiveCodeIntelligenceError("LSP request params must be an object")
        uri_keys = {
            "uri",
            "rootUri",
            "scopeUri",
            "targetUri",
            "oldUri",
            "newUri",
            "documentUri",
        }

        def visit(value: Any) -> None:
            if isinstance(value, str):
                if value.lower().startswith("file:"):
                    self._validate_request_uri(value, "LSP request URI")
            elif isinstance(value, Mapping):
                for key, nested in value.items():
                    if key in uri_keys:
                        self._validate_request_uri(nested, f"LSP request {key}")
                    visit(nested)
            elif isinstance(value, (list, tuple)):
                for nested in value:
                    visit(nested)

        visit(params)

    def _read_message(self) -> dict[str, Any] | None:
        process = self._process
        if process is None or process.stdout is None:
            return None
        headers: dict[str, str] = {}
        header_bytes = 0
        header_lines = 0
        max_header_line_bytes = min(
            LSP_MAX_HEADER_LINE_BYTES,
            self.max_message_bytes,
        )
        max_header_bytes = min(LSP_MAX_HEADER_BYTES, self.max_message_bytes)
        while True:
            line = process.stdout.readline(max_header_line_bytes + 1)
            if not line:
                return None
            header_lines += 1
            header_bytes += len(line)
            if (
                len(line) > max_header_line_bytes
                or header_lines > LSP_MAX_HEADER_LINES
                or header_bytes > max_header_bytes
                or not line.endswith(b"\n")
            ):
                raise LiveCodeIntelligenceError(
                    "LSP response headers exceed the bounded header size"
                )
            if line in {b"\r\n", b"\n"}:
                break
            try:
                name, value = line.decode("ascii").split(":", 1)
            except (UnicodeDecodeError, ValueError) as exc:
                raise LiveCodeIntelligenceError("invalid LSP response header") from exc
            headers[name.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise LiveCodeIntelligenceError("LSP response lacks Content-Length") from exc
        if length < 0 or length > self.max_message_bytes:
            raise LiveCodeIntelligenceError("LSP response exceeds the bounded message size")
        body = process.stdout.read(length)
        if len(body) != length:
            return None
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise LiveCodeIntelligenceError("LSP response must be a JSON object")
        return payload

    def _reader_loop(self) -> None:
        try:
            while self._process is not None and self._process.poll() is None:
                payload = self._read_message()
                if payload is None:
                    if not self._closing:
                        self._fail_pending("LSP reader reached EOF")
                    break
                response_id = payload.get("id")
                if (
                    isinstance(response_id, int)
                    and not isinstance(response_id, bool)
                    and "method" not in payload
                    and ("result" in payload or "error" in payload)
                ):
                    with self._pending_lock:
                        destination = self._pending.get(response_id)
                    if destination is not None:
                        destination.put(payload)
                        continue
                if (
                    isinstance(response_id, (int, str))
                    and not isinstance(response_id, bool)
                    and isinstance(payload.get("method"), str)
                ):
                    self._send(
                        {
                            "jsonrpc": "2.0",
                            "id": response_id,
                            "error": {
                                "code": -32601,
                                "message": "server-to-client requests are unsupported",
                            },
                        }
                    )
                    continue
                try:
                    self._responses.put_nowait(payload)
                except queue.Full:
                    try:
                        self._responses.get_nowait()
                    except queue.Empty:
                        pass
                    self._responses.put_nowait(payload)
        except Exception as exc:  # bounded into observable session state
            self._fail_pending(f"{type(exc).__name__}: {exc}")

    def _fail_pending(self, message: str) -> None:
        self._last_error = message
        with self._pending_lock:
            destinations = list(self._pending.values())
        failure = {
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": message},
        }
        for destination in destinations:
            try:
                destination.put_nowait(failure)
            except queue.Full:
                pass

    @staticmethod
    def _copy_verified_file(
        source: Path,
        destination: Path,
        *,
        expected_digest: str,
        label: str,
    ) -> None:
        """Copy one admitted file while hashing the bytes actually copied."""

        source_descriptor, metadata = _open_regular_descriptor(source, label)
        destination_descriptor: int | None = None
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            destination_descriptor = os.open(destination, flags, 0o600)
            digest = hashlib.sha256()
            offset = 0
            while True:
                chunk = _read_descriptor(
                    source_descriptor,
                    SOURCE_READ_CHUNK_BYTES,
                    offset,
                )
                if not chunk:
                    break
                digest.update(chunk)
                written = 0
                while written < len(chunk):
                    written += os.write(destination_descriptor, chunk[written:])
                offset += len(chunk)
            actual_digest = f"sha256:{digest.hexdigest()}"
            if actual_digest != expected_digest:
                raise LiveCodeIntelligenceError(
                    f"{label} changed while preparing the exact launch snapshot"
                )
            # Preserve read/execute permission while making the private
            # snapshot immutable to ordinary writers.
            os.fchmod(destination_descriptor, metadata.st_mode & 0o555)
        except LiveCodeIntelligenceError:
            raise
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                f"unable to copy {label} into the exact launch snapshot"
            ) from exc
        finally:
            if destination_descriptor is not None:
                os.close(destination_descriptor)
            os.close(source_descriptor)

    def _materialize_runtime_snapshot(self) -> Path:
        """Create a private, read-only runtime dependency tree for one launch."""

        try:
            scratch_root = self._launch_scratch_root
            if scratch_root is None:
                raise LiveCodeIntelligenceError(
                    "LSP launch scratch root is required for installed LSP sessions"
                )
            # This root is supplied by the machine owner (for example the
            # machine-bound /srv/abyss-machine/tmp/code-intelligence route),
            # never inferred from provider state or Python's default /tmp.
            if _contains_symlink(scratch_root):
                raise LiveCodeIntelligenceError(
                    "LSP launch snapshot root must not contain symlinks"
                )
            scratch_root.mkdir(parents=True, exist_ok=True)
            if _contains_symlink(scratch_root):
                raise LiveCodeIntelligenceError(
                    "LSP launch snapshot root must not contain symlinks"
                )
            if not scratch_root.is_dir() or scratch_root.is_symlink():
                raise LiveCodeIntelligenceError(
                    "LSP launch snapshot root must be a real directory"
                )
            scratch_root.chmod(0o700)
            snapshot_root = Path(
                tempfile.mkdtemp(
                    prefix="abyss-lsp-runtime-",
                    dir=str(scratch_root),
                )
            )
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                "unable to create an exact LSP runtime snapshot"
            ) from exc
        try:
            for relative, digest in self._runtime_manifest:
                destination = snapshot_root / Path(relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                self._copy_verified_file(
                    self._working_directory / Path(relative),
                    destination,
                    expected_digest=digest,
                    label=f"LSP runtime dependency {relative}",
                )
            # A replacement/addition during the copy must fail closed. Once
            # this check succeeds, later changes to the admitted root cannot
            # affect the private tree used by the child.
            if _directory_file_manifest(
                self._working_directory,
                "LSP runtime dependency root",
            ) != self._runtime_manifest:
                raise LiveCodeIntelligenceError(
                    "LSP runtime dependency manifest changed while preparing the exact launch snapshot"
                )
            return snapshot_root
        except Exception:
            self._remove_snapshot_path(snapshot_root)
            raise

    @staticmethod
    def _can_use_immutable_launch_fds() -> bool:
        return bool(
            os.name == "posix"
            and hasattr(os, "memfd_create")
            and hasattr(os, "MFD_CLOEXEC")
            and hasattr(os, "MFD_ALLOW_SEALING")
            and fcntl is not None
            and hasattr(fcntl, "F_ADD_SEALS")
            and all(
                hasattr(fcntl, name)
                for name in (
                    "F_SEAL_WRITE",
                    "F_SEAL_SHRINK",
                    "F_SEAL_GROW",
                    "F_SEAL_SEAL",
                )
            )
            and Path("/proc/self/fd").is_dir()
        )

    @staticmethod
    def _immutable_launch_fd(
        path: Path,
        *,
        expected_digest: str,
        label: str,
    ) -> int:
        """Snapshot one admitted executable into a sealed Linux memfd."""

        source_descriptor, metadata = _open_regular_descriptor(path, label)
        launch_descriptor: int | None = None
        keep_descriptor = False
        try:
            launch_descriptor = os.memfd_create(
                "abyss-lsp-launch",
                os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
            )
            digest = hashlib.sha256()
            offset = 0
            while True:
                chunk = _read_descriptor(
                    source_descriptor,
                    SOURCE_READ_CHUNK_BYTES,
                    offset,
                )
                if not chunk:
                    break
                digest.update(chunk)
                written = 0
                while written < len(chunk):
                    written += os.write(launch_descriptor, chunk[written:])
                offset += len(chunk)
            actual_digest = f"sha256:{digest.hexdigest()}"
            if actual_digest != expected_digest:
                raise LiveCodeIntelligenceError(
                    f"{label} changed before exact launch"
                )
            os.fchmod(launch_descriptor, metadata.st_mode & 0o777)
            seals = (
                fcntl.F_SEAL_WRITE
                | fcntl.F_SEAL_SHRINK
                | fcntl.F_SEAL_GROW
                | fcntl.F_SEAL_SEAL
            )
            fcntl.fcntl(launch_descriptor, fcntl.F_ADD_SEALS, seals)
            os.lseek(launch_descriptor, 0, os.SEEK_SET)
            keep_descriptor = True
            return launch_descriptor
        except LiveCodeIntelligenceError:
            raise
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                f"unable to create an immutable exact launch image for {label}"
            ) from exc
        finally:
            os.close(source_descriptor)
            if launch_descriptor is not None and not keep_descriptor:
                os.close(launch_descriptor)

    @staticmethod
    def _launch_namespace_binary() -> str:
        """Return the verified machine-owned namespace launcher."""

        if os.name != "posix":
            raise LiveCodeIntelligenceError(
                "LSP runtime snapshot requires a read-only launch namespace"
            )
        try:
            descriptor, metadata = _open_regular_descriptor(
                MACHINE_BUBBLEWRAP_PATH,
                "machine-owned bubblewrap",
            )
        except LiveCodeIntelligenceError as exc:
            raise LiveCodeIntelligenceError(
                "LSP runtime snapshot requires the fixed machine-owned bubblewrap binary"
            ) from exc
        try:
            if metadata.st_uid != 0 or metadata.st_mode & 0o022:
                raise LiveCodeIntelligenceError(
                    "machine-owned bubblewrap must be root-owned and not writable"
                )
            if not metadata.st_mode & 0o111:
                raise LiveCodeIntelligenceError(
                    "machine-owned bubblewrap must be executable"
                )
        finally:
            os.close(descriptor)
        return str(MACHINE_BUBBLEWRAP_PATH)

    @staticmethod
    def _snapshot_namespace_directories(
        snapshot_root: Path,
        runtime_fds: tuple[tuple[int, str], ...],
        source_root: Path,
        source_fds: tuple[tuple[int, str], ...],
    ) -> tuple[Path, ...]:
        """Return directories needed before binding sealed launch files."""

        directories: set[Path] = set()
        for target in (snapshot_root, source_root):
            current = target
            while current != Path("/"):
                directories.add(current)
                current = current.parent
        for root, bindings in ((snapshot_root, runtime_fds), (source_root, source_fds)):
            for _, relative in bindings:
                current = (root / Path(relative)).parent
                while current != Path("/"):
                    directories.add(current)
                    current = current.parent
        return tuple(sorted(directories, key=lambda path: len(path.parts)))

    def _immutable_runtime_fds(
        self,
    ) -> tuple[tuple[int, str], ...]:
        """Seal every manifest file before the child namespace is created."""

        bindings: list[tuple[int, str]] = []
        try:
            for relative, digest in self._runtime_manifest:
                descriptor = self._immutable_launch_fd(
                    self._working_directory / Path(relative),
                    expected_digest=digest,
                    label=f"LSP runtime dependency {relative}",
                )
                bindings.append((descriptor, relative))
            # The sealed descriptors make the bytes stable even if the source
            # root changes after this point.  Rechecking the complete manifest
            # also rejects an unadmitted addition or deletion during sealing.
            if _directory_file_manifest(
                self._working_directory,
                "LSP runtime dependency root",
            ) != self._runtime_manifest:
                raise LiveCodeIntelligenceError(
                    "LSP runtime dependency manifest changed while sealing the exact launch snapshot"
                )
            return tuple(bindings)
        except Exception:
            for descriptor, _ in bindings:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

    def _immutable_source_fds(
        self,
    ) -> tuple[tuple[int, str], ...]:
        """Seal every admitted source file before the child namespace exists."""

        expected_manifest = tuple(sorted(self._source_manifest.items()))
        bindings: list[tuple[int, str]] = []
        try:
            if _directory_file_manifest(
                self.source_root,
                "LSP source root",
            ) != expected_manifest:
                raise LiveCodeIntelligenceError(
                    "LSP source epoch manifest changed while sealing the exact launch snapshot"
                )
            for relative, digest in expected_manifest:
                descriptor = self._immutable_launch_fd(
                    self.source_root / Path(relative),
                    expected_digest=digest,
                    label=f"LSP source file {relative}",
                )
                bindings.append((descriptor, relative))
            # Sealed descriptors are the source snapshot.  Rechecking the
            # complete manifest rejects an unadmitted addition or deletion
            # while the descriptors are being prepared.
            if _directory_file_manifest(
                self.source_root,
                "LSP source root",
            ) != expected_manifest:
                raise LiveCodeIntelligenceError(
                    "LSP source epoch manifest changed while sealing the exact launch snapshot"
                )
            return tuple(bindings)
        except Exception:
            for descriptor, _ in bindings:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

    def _sandbox_command(
        self,
        command: tuple[str, ...],
        *,
        snapshot_root: Path,
        runtime_fds: tuple[tuple[int, str], ...],
        source_fds: tuple[tuple[int, str], ...],
    ) -> tuple[str, ...]:
        """Run the launch with sealed runtime and source files in its namespace."""

        launcher = self._launch_namespace_binary()
        sandbox: list[str] = [
            launcher,
            "--die-with-parent",
            "--new-session",
            "--tmpfs",
            "/",
        ]
        # The interpreter's dynamic loader and standard library remain
        # machine-owned, root-owned system inputs.  Bind them read-only while
        # the manifest-bound runtime tree is reconstructed solely from sealed
        # descriptors below.  /tmp is private to the child namespace.
        for system_root in ("/bin", "/etc", "/lib", "/lib64", "/sbin", "/usr"):
            if Path(system_root).exists():
                sandbox.extend(("--ro-bind", system_root, system_root))
        sandbox.extend(("--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp"))
        for directory in self._snapshot_namespace_directories(
            snapshot_root,
            runtime_fds,
            self.source_root,
            source_fds,
        ):
            if (
                directory == snapshot_root
                or snapshot_root in directory.parents
                or directory == self.source_root
                or self.source_root in directory.parents
            ):
                # The source and runtime roots are mount points assembled
                # from sealed files.  Their directories must not remain
                # writable, otherwise the child could add an unadmitted
                # import or replace a mount before a lazy lookup.
                sandbox.extend(("--perms", "0555"))
            sandbox.extend(("--dir", str(directory)))
        for descriptor, relative in source_fds:
            # Materialize the admitted source epoch at the exact root URI
            # supplied to initialize.  Sealed descriptors keep the source
            # bytes stable after binding even when the working tree changes.
            sandbox.extend(
                (
                    "--perms",
                    "0555",
                    "--ro-bind-data",
                    str(descriptor),
                    str(self.source_root / Path(relative)),
                )
            )
        for descriptor, relative in runtime_fds:
            # Runtime files are never writable in the child, including files
            # whose source mode carried an execute bit.  0555 keeps executable
            # runtime helpers runnable without granting mutation rights.
            sandbox.extend(
                (
                    "--perms",
                    "0555",
                    "--ro-bind-data",
                    str(descriptor),
                    str(snapshot_root / Path(relative)),
                )
            )
        sandbox.extend(("--chdir", str(snapshot_root), "--"))
        sandbox.extend(command)
        return tuple(sandbox)

    def _snapshot_command_arguments(self, snapshot_root: Path) -> tuple[str, ...]:
        arguments: list[str] = []
        for argument in self.command[1:]:
            option_prefix = ""
            candidate = Path(argument)
            if not candidate.is_absolute():
                option, separator, value = argument.partition("=")
                if separator:
                    option_candidate = Path(value)
                    if option_candidate.is_absolute() or ".." in option_candidate.parts:
                        option_prefix = f"{option}="
                        candidate = option_candidate
                    else:
                        arguments.append(argument)
                        continue
                elif ".." in candidate.parts:
                    option_prefix = ""
                else:
                    arguments.append(argument)
                    continue
            try:
                resolved = (
                    candidate.resolve(strict=False)
                    if candidate.is_absolute()
                    else (self._working_directory / candidate).resolve(strict=False)
                )
                relative = resolved.relative_to(self._working_directory)
            except (OSError, ValueError) as exc:
                raise LiveCodeIntelligenceError(
                    "LSP command path dependency must remain inside the admitted runtime root"
                ) from exc
            arguments.append(f"{option_prefix}{snapshot_root / relative}")
        return tuple(arguments)

    def _prepare_launch_binding(self) -> _LspLaunchBinding:
        """Bind execution to immutable bytes and a private dependency root."""

        snapshot_root = self._materialize_runtime_snapshot()
        descriptors: list[int] = []
        try:
            if not self._can_use_immutable_launch_fds():
                raise LiveCodeIntelligenceError(
                    "LSP launch requires sealed descriptors for an immutable execution boundary"
                )
            runtime_fds = self._immutable_runtime_fds()
            descriptors.extend(descriptor for descriptor, _ in runtime_fds)
            source_fds = self._immutable_source_fds()
            descriptors.extend(descriptor for descriptor, _ in source_fds)
            executable_descriptor = self._immutable_launch_fd(
                Path(self.command[0]),
                expected_digest=self.executable_digest,
                label="LSP executable",
            )
            descriptors.append(executable_descriptor)
            interpreter = _shebang_interpreter_from_descriptor(
                executable_descriptor
            )
            if interpreter != self._interpreter_path:
                raise LiveCodeIntelligenceError(
                    "LSP script interpreter changed before exact launch"
                )
            interpreter_descriptor: int | None = None
            if interpreter is not None:
                if self._interpreter_digest is None:
                    raise LiveCodeIntelligenceError(
                        "LSP script interpreter lacks an admitted digest"
                    )
                interpreter_descriptor = self._immutable_launch_fd(
                    interpreter,
                    expected_digest=self._interpreter_digest,
                    label="LSP script interpreter",
                )
                descriptors.append(interpreter_descriptor)
            executable_ref = f"/proc/self/fd/{executable_descriptor}"
            interpreter_ref = (
                f"/proc/self/fd/{interpreter_descriptor}"
                if interpreter_descriptor is not None
                else None
            )
            for directory in sorted(
                (path for path in snapshot_root.rglob("*") if path.is_dir()),
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                directory.chmod(0o500)
            snapshot_root.chmod(0o500)
            arguments = self._snapshot_command_arguments(snapshot_root)
            if interpreter_ref is not None:
                command = (
                    (interpreter_ref, "-S", executable_ref, *arguments)
                    if _is_python_interpreter(self._interpreter_path)
                    else (interpreter_ref, executable_ref, *arguments)
                )
            else:
                command = (executable_ref, *arguments)
            command = self._sandbox_command(
                tuple(command),
                snapshot_root=snapshot_root,
                runtime_fds=runtime_fds,
                source_fds=source_fds,
            )
            return _LspLaunchBinding(
                command=tuple(command),
                pass_fds=tuple(descriptors),
                runtime_root=snapshot_root,
                snapshot_root=snapshot_root,
            )
        except Exception:
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            self._remove_snapshot_path(snapshot_root)
            raise

    @staticmethod
    def _remove_snapshot_path(snapshot_root: Path) -> None:
        """Restore private snapshot directory permissions before removing it."""

        if not snapshot_root.exists() and not snapshot_root.is_symlink():
            return
        try:
            if snapshot_root.is_symlink():
                raise LiveCodeIntelligenceError(
                    "refusing to remove a symlinked LSP launch snapshot"
                )
            for path in snapshot_root.rglob("*"):
                if path.is_symlink():
                    raise LiveCodeIntelligenceError(
                        "refusing to remove a symlink inside the LSP launch snapshot"
                    )
                if path.is_dir():
                    path.chmod(0o700)
                else:
                    path.chmod(0o600)
            snapshot_root.chmod(0o700)
            shutil.rmtree(snapshot_root, ignore_errors=False)
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                "unable to remove the exact LSP launch snapshot"
            ) from exc

    def _cleanup_launch_snapshot(self) -> None:
        snapshot_root = self._launch_snapshot_root
        self._launch_snapshot_root = None
        if snapshot_root is None:
            return
        try:
            self._remove_snapshot_path(snapshot_root)
        except LiveCodeIntelligenceError as exc:
            self._last_error = f"unable to remove LSP launch snapshot: {exc}"

    def _validate_launch_binding(self, root_uri: str) -> None:
        root_path = _file_uri_path(root_uri, "LSP root_uri")
        if root_path != self.source_root:
            raise LiveCodeIntelligenceError(
                "LSP root_uri does not match the admitted source root"
            )
        evidence = self._admission_config.machine_evidence
        if not isinstance(evidence, _AuthenticatedMachineEvidence):
            raise LiveCodeIntelligenceError(
                "LSP session requires evidence returned by the owner-authenticated machine gate"
            )
        try:
            _require_fresh_machine_health(evidence)
        except LiveCodeIntelligenceError as exc:
            raise LiveCodeIntelligenceError(
                "LSP session requires fresh machine health evidence"
            ) from exc
        bound_session = self._bound_machine_session(evidence)
        if bound_session is None:
            raise LiveCodeIntelligenceError(
                "LSP admission evidence no longer binds this provider and source epoch"
            )
        bound_runtime_manifest = _validated_file_manifest(
            bound_session.get("runtime_manifest"),
            "machine_evidence.lsp_sessions.runtime_manifest",
            allow_empty=True,
        )
        if bound_runtime_manifest != self._runtime_manifest:
            raise LiveCodeIntelligenceError(
                "LSP runtime dependency manifest changed after session construction"
            )
        bound_source_manifest = _validated_file_manifest(
            bound_session.get("source_manifest"),
            "machine_evidence.lsp_sessions.source_manifest",
            allow_empty=True,
        )
        if dict(bound_source_manifest) != self._source_manifest:
            raise LiveCodeIntelligenceError(
                "LSP source epoch manifest changed after session construction"
            )
        try:
            current_runtime_manifest = _directory_file_manifest(
                self._working_directory,
                "LSP runtime dependency root",
            )
        except LiveCodeIntelligenceError as exc:
            raise LiveCodeIntelligenceError(
                "LSP runtime dependency manifest cannot be revalidated"
            ) from exc
        if current_runtime_manifest != self._runtime_manifest:
            raise LiveCodeIntelligenceError(
                "LSP runtime dependency manifest changed after admission"
            )
        try:
            current_source_manifest = _directory_file_manifest(
                self.source_root,
                "LSP source root",
            )
        except LiveCodeIntelligenceError as exc:
            raise LiveCodeIntelligenceError(
                "LSP source epoch manifest cannot be revalidated"
            ) from exc
        if current_source_manifest != tuple(sorted(self._source_manifest.items())):
            raise LiveCodeIntelligenceError(
                "LSP source epoch manifest changed after admission"
            )
        artifact_digest = self._bound_artifact_digest(evidence, bound_session)
        if artifact_digest != self.admitted_artifact_digest:
            raise LiveCodeIntelligenceError(
                "LSP admission evidence changed after session construction"
            )
        current_command_digest = _digest_payload(list(self.command))
        admitted_command_digest = bound_session.get("command_digest")
        if admitted_command_digest is None:
            if len(self.command) > 1:
                raise LiveCodeIntelligenceError(
                    "LSP command arguments require an admitted command digest"
                )
        elif admitted_command_digest != current_command_digest:
            raise LiveCodeIntelligenceError(
                "LSP command does not match admitted machine evidence"
            )

    def start(self, *, root_uri: str, capabilities: Mapping[str, Any] | None = None) -> dict[str, Any]:
        with self._lifecycle_lock:
            self._validate_launch_binding(root_uri)
            if capabilities is not None and not isinstance(capabilities, Mapping):
                raise LiveCodeIntelligenceError(
                    "LSP client capabilities must be an object"
                )
            if self._process is not None and self._process.poll() is None:
                return self.snapshot()
            if self._process is not None:
                # A crashed child still owns pipes and a manifest snapshot.
                # Retire that generation before preparing its replacement so
                # retries cannot leak runtime storage or descriptors.
                self._terminate_process()
            # Health is generation-specific.  Clear the previous generation's
            # success before exposing a newly running child to observers.
            self._last_good_at = None
            launch_capabilities = (
                copy.deepcopy(self._client_capabilities)
                if capabilities is None
                else copy.deepcopy(dict(capabilities))
            )
            self._client_capabilities = launch_capabilities
            self._generation += 1
            binding = self._prepare_launch_binding()
            try:
                self._process = subprocess.Popen(
                    list(binding.command),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    pass_fds=binding.pass_fds,
                    cwd=str(binding.runtime_root),
                    env=_lsp_launch_environment(
                        binding.runtime_root,
                        self._interpreter_path,
                    ),
                )
                self._launch_snapshot_root = binding.snapshot_root
            except Exception:
                self._remove_snapshot_path(binding.snapshot_root)
                raise
            finally:
                for descriptor in binding.pass_fds:
                    try:
                        os.close(descriptor)
                    except OSError:
                        pass
            self._reader = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader.start()
            self._started_at = _now()
            self._last_error = None
            try:
                result = self.request("initialize", {
                    "processId": os.getpid(),
                    "rootUri": root_uri,
                    "capabilities": launch_capabilities,
                })
                self.notify("initialized", {})
                self._last_good_at = _now()
                return result
            except Exception:
                self._terminate_process()
                raise

    def request(self, method: str, params: Mapping[str, Any]) -> dict[str, Any]:
        self._validate_request_params(params)
        destination: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._request_id += 1
            request_id = self._request_id
            self._pending[request_id] = destination
        try:
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
            try:
                response = destination.get(timeout=self.request_timeout)
            except queue.Empty as exc:
                self._last_error = f"request timeout: {method}"
                raise LiveCodeIntelligenceError(self._last_error) from exc
            if "error" in response:
                self._last_error = f"LSP error for {method}: {response['error']}"
                raise LiveCodeIntelligenceError(self._last_error)
            self._last_good_at = _now()
            return response
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

    def notify(self, method: str, params: Mapping[str, Any]) -> None:
        self._validate_request_params(params)
        self._send({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    def _validated_document_uri(self, uri: str) -> str:
        path = _file_uri_path(uri, "LSP document URI")
        try:
            path.relative_to(self.source_root)
        except ValueError as exc:
            raise LiveCodeIntelligenceError(
                "LSP document URI must remain inside the admitted source root"
            ) from exc
        if path == self.source_root:
            raise LiveCodeIntelligenceError(
                "LSP document URI must identify a file inside the admitted source root"
            )
        if path.exists() and path.is_dir():
            raise LiveCodeIntelligenceError(
                "LSP document URI must identify a file inside the admitted source root"
            )
        return path.as_uri()

    def _admitted_document_content(self, uri: str) -> bytes:
        """Read bytes whose digest is present in the admitted source manifest."""

        path = _file_uri_path(uri, "LSP document URI")
        try:
            relative = path.relative_to(self.source_root).as_posix()
        except ValueError as exc:
            raise LiveCodeIntelligenceError(
                "LSP document is outside the admitted source epoch manifest"
            ) from exc
        expected_digest = self._source_manifest.get(relative)
        if expected_digest is None:
            raise LiveCodeIntelligenceError(
                "LSP document is absent from the admitted source epoch manifest"
            )
        metadata = LiveCodeIntelligenceRuntime._read_source_metadata(
            path,
            self.source_root,
            self._admission_config.max_file_bytes,
            retain_content=True,
        )
        content = metadata.get("content") if metadata is not None else None
        if not isinstance(content, bytes):
            raise LiveCodeIntelligenceError(
                "LSP document must have bounded admitted source bytes"
            )
        if metadata.get("content_digest") != expected_digest:
            raise LiveCodeIntelligenceError(
                "LSP document bytes no longer match the admitted source epoch manifest"
            )
        return content

    def open_document(self, *, uri: str, text: str, version: int = 1) -> None:
        validated_uri = self._validated_document_uri(uri)
        if not isinstance(text, str):
            raise LiveCodeIntelligenceError("LSP document text must be a string")
        try:
            encoded_text = text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise LiveCodeIntelligenceError(
                "LSP document text must be valid UTF-8"
            ) from exc
        if encoded_text != self._admitted_document_content(validated_uri):
            raise LiveCodeIntelligenceError(
                "LSP document text must match the admitted source epoch bytes"
            )
        self.notify("textDocument/didOpen", {"textDocument": {
            "uri": validated_uri, "languageId": self.language, "version": version, "text": text,
        }})

    def document_symbols(self, *, uri: str) -> dict[str, Any]:
        return self.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": self._validated_document_uri(uri)}},
        )

    def restart(self, *, root_uri: str) -> dict[str, Any]:
        with self._lifecycle_lock:
            capabilities = copy.deepcopy(self._client_capabilities)
            self.close()
            self._restart_count += 1
            return self.start(root_uri=root_uri, capabilities=capabilities)

    def close(self) -> None:
        with self._lifecycle_lock:
            process = self._process
            if process is None:
                self._cleanup_launch_snapshot()
                return
            self._closing = True
            if process.poll() is None:
                try:
                    self.request("shutdown", {})
                    self.notify("exit", {})
                    process.wait(timeout=2.0)
                except Exception:
                    process.kill()
                    process.wait()
            self._terminate_process()
            self._closing = False

    def _terminate_process(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        if process is not None:
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    try:
                        stream.close()
                    except OSError:
                        pass
        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join(timeout=1.0)
        self._process = None
        self._reader = None
        self._cleanup_launch_snapshot()

    def snapshot(self) -> dict[str, Any]:
        running = self._process is not None and self._process.poll() is None
        return {
            "schema_version": LSP_SESSION_SCHEMA,
            "session_id": f"lsp-session:{self.provider_id}:{self._generation}",
            "provider_id": self.provider_id,
            "language": self.language,
            "state": "degraded" if self._last_error else "observed" if running and self._last_good_at else "starting",
            "transport": "stdio",
            "source_epoch": self.source_epoch,
            "admission_ref": self.admission_ref,
            "generation": self._generation,
            "restart_count": self._restart_count,
            "started_at": self._started_at,
            "last_good_at": self._last_good_at,
            "last_error": self._last_error,
            "claim_limit": "runtime session evidence is not KAG meaning or semantic proof",
        }


class LiveCodeIntelligenceRuntime:
    """Refresh and query the runtime-local LIVE observation state."""

    def __init__(self, config: LiveCodeIntelligenceConfig) -> None:
        self.config = config
        self.current_path = config.state_root / "current.json"
        self.candidate_path = config.state_root / "candidate.json"
        self.last_good_path = config.state_root / "last-good.json"
        self.receipts_path = config.state_root / "receipts"
        self.operation_receipts_path = (
            config.state_root / OPERATION_RECEIPTS_DIRECTORY
        )
        self.lock_path = config.state_root / STATE_LOCK_NAME
        self._refresh_receipt_snapshot: tuple[Path, dict[str, Any]] | None = None
        self._refresh_attempt_source_epoch: str | None = None
        # A transition receipt in the writable state root is not an
        # authenticator.  Keep only digests of states committed by this
        # runtime instance so a same-UID writer cannot replace a historical
        # snapshot and make its replacement self-authenticating.
        self._trusted_observation_digests: dict[str, str] = {}
        self._captured_machine_evidence_summary = (
            copy.deepcopy(self._machine_evidence_summary(config.machine_evidence))
            if isinstance(config.machine_evidence, _AuthenticatedMachineEvidence)
            else None
        )

    def _current_machine_evidence(self) -> Mapping[str, Any] | None:
        evidence = self.config.machine_evidence
        if not isinstance(evidence, _AuthenticatedMachineEvidence):
            return None
        try:
            _require_fresh_machine_health(evidence)
        except LiveCodeIntelligenceError:
            return None
        return evidence

    @contextmanager
    def _refresh_lock(self) -> Iterator[None]:
        key = str(self.config.state_root)
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(key, threading.RLock())
        with thread_lock:
            if fcntl is None:
                raise LiveCodeIntelligenceError(
                    "cross-process refresh locking is unavailable on this platform"
                )
            if self.config.state_root.is_symlink():
                raise LiveCodeIntelligenceError(
                    "state root must not be a symlink"
                )
            try:
                self.config.state_root.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise LiveCodeIntelligenceError(
                    f"unable to create state root: {self.config.state_root}"
                ) from exc
            if not self.config.state_root.is_dir() or self.config.state_root.is_symlink():
                raise LiveCodeIntelligenceError(
                    "state root must be a real directory"
                )
            if self.lock_path.is_symlink():
                raise LiveCodeIntelligenceError(
                    "refresh lock must not be a symlink"
                )
            descriptor: int | None = None
            try:
                flags = os.O_RDWR | os.O_CREAT
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                descriptor = os.open(self.lock_path, flags, 0o600)
                if fcntl is not None:
                    fcntl.flock(descriptor, fcntl.LOCK_EX)
            except OSError as exc:
                if descriptor is not None:
                    os.close(descriptor)
                raise LiveCodeIntelligenceError(
                    f"unable to acquire refresh lock: {self.lock_path}"
                ) from exc
            try:
                yield
            finally:
                if descriptor is not None:
                    if fcntl is not None:
                        try:
                            fcntl.flock(descriptor, fcntl.LOCK_UN)
                        except OSError:
                            pass
                    os.close(descriptor)

    @staticmethod
    def _read_source_metadata(
        path: Path,
        source_root: Path,
        max_file_bytes: int,
        *,
        retain_content: bool = False,
    ) -> dict[str, Any] | None:
        try:
            relative = path.relative_to(source_root)
        except ValueError:
            return None
        parts = relative.parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            return None

        descriptor: int | None = None
        parent_descriptor: int | None = None
        source_flags = os.O_RDONLY
        if hasattr(os, "O_NONBLOCK"):
            source_flags |= os.O_NONBLOCK
        if hasattr(os, "O_NOFOLLOW"):
            source_flags |= os.O_NOFOLLOW
        secure_descriptor_walk = (
            os.name == "posix"
            and hasattr(os, "O_DIRECTORY")
            and hasattr(os, "O_NOFOLLOW")
            and os.open in getattr(os, "supports_dir_fd", set())
        )
        try:
            if secure_descriptor_walk:
                parent_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                parent_descriptor = os.open(source_root, parent_flags)
                for component in parts[:-1]:
                    next_descriptor = os.open(
                        component,
                        parent_flags,
                        dir_fd=parent_descriptor,
                    )
                    os.close(parent_descriptor)
                    parent_descriptor = next_descriptor
                descriptor = os.open(
                    parts[-1],
                    source_flags,
                    dir_fd=parent_descriptor,
                )
            else:
                # Windows has no portable openat/O_NOFOLLOW pair.  Preserve
                # the existing fail-closed canonical check there while the
                # POSIX route above eliminates the check/open race.
                resolved = path.resolve(strict=True)
                resolved.relative_to(source_root)
                descriptor = os.open(resolved, source_flags)
        except (OSError, ValueError) as exc:
            if isinstance(exc, OSError) and exc.errno in {
                errno.ELOOP,
                errno.ENOENT,
                errno.ENOTDIR,
            }:
                return None
            raise LiveCodeIntelligenceError(
                f"unable to read source file safely: {path}"
            ) from exc
        finally:
            if parent_descriptor is not None:
                os.close(parent_descriptor)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                os.close(descriptor)
                return None
        except OSError as exc:
            os.close(descriptor)
            raise LiveCodeIntelligenceError(
                f"unable to inspect source file safely: {path}"
            ) from exc
        digest = hashlib.sha256()
        retained = bytearray()
        total = 0
        try:
            with os.fdopen(descriptor, "rb") as handle:
                while True:
                    chunk = handle.read(SOURCE_READ_CHUNK_BYTES)
                    if not chunk:
                        break
                    digest.update(chunk)
                    total += len(chunk)
                    if retain_content and total <= max_file_bytes:
                        retained.extend(chunk)
                    elif total > max_file_bytes:
                        retained.clear()
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                f"unable to read source file: {path}"
            ) from exc
        return {
            "path": path.relative_to(source_root).as_posix(),
            "content_digest": f"sha256:{digest.hexdigest()}",
            "size_bytes": total,
            "content": (
                bytes(retained)
                if retain_content and total <= max_file_bytes
                else None
            ),
        }

    def _scan(self) -> dict[str, dict[str, Any]]:
        if self.config.source_root.is_symlink() or not self.config.source_root.is_dir():
            raise LiveCodeIntelligenceError(
                f"source root must be a real directory: {self.config.source_root}"
            )
        files: dict[str, dict[str, Any]] = {}
        total_bytes = 0
        def traversal_error(exc: OSError) -> None:
            raise LiveCodeIntelligenceError(
                f"unable to traverse source tree: {exc.filename or self.config.source_root}"
            ) from exc

        for directory, dirnames, filenames in os.walk(
            self.config.source_root,
            topdown=True,
            onerror=traversal_error,
            followlinks=False,
        ):
            directory_path = Path(directory)
            dirnames[:] = [
                name
                for name in sorted(dirnames)
                if name not in self.config.exclude_dirs
                and not (directory_path / name).is_symlink()
            ]
            for name in sorted(filenames):
                path = directory_path / name
                if path.suffix not in self.config.include_suffixes:
                    continue
                metadata = self._read_source_metadata(
                    path,
                    self.config.source_root,
                    self.config.max_file_bytes,
                )
                if metadata is not None:
                    if "\\" in metadata["path"]:
                        raise LiveCodeIntelligenceError(
                            f"unsupported backslash in source path: {metadata['path']}"
                        )
                    if _contains_surrogate(metadata["path"]):
                        metadata["scan_diagnostics"] = [
                            {
                                "code": "source_path_not_utf8",
                                "severity": "error",
                                "message": "source filename is not valid UTF-8",
                            }
                        ]
                    if len(files) >= SOURCE_SCAN_MAX_FILES:
                        # Keep the bounded partial candidate queryable only as
                        # degraded state.  Attach the envelope diagnostic to
                        # the last admitted record because persisted
                        # degradation diagnostics are intentionally
                        # path-qualified by the state contract.
                        diagnostic = {
                            "code": "source_scan_limit",
                            "severity": "error",
                            "message": (
                                "source scan exceeded the authored aggregate "
                                f"file-count envelope of {SOURCE_SCAN_MAX_FILES}"
                            ),
                        }
                        target = files[max(files)]
                        target.setdefault("scan_diagnostics", []).append(diagnostic)
                        return files
                    files[metadata["path"]] = metadata
                    total_bytes += int(metadata.get("size_bytes", 0))
                    if total_bytes > SOURCE_SCAN_MAX_BYTES:
                        metadata.setdefault("scan_diagnostics", []).append(
                            {
                                "code": "source_scan_limit",
                                "severity": "error",
                                "message": (
                                    "source scan exceeded the authored aggregate "
                                    f"byte envelope of {SOURCE_SCAN_MAX_BYTES}"
                                ),
                            }
                        )
                        return files
        return files

    def _source_epoch(self, files: Mapping[str, Mapping[str, Any]]) -> str:
        manifest = [
            {
                "path": path,
                "content_digest": str(item["content_digest"]),
                "size_bytes": int(item["size_bytes"]),
            }
            for path, item in sorted(files.items())
        ]
        return _digest_payload(
            {
                "provider": self.config.provider_identity,
                "config_digest": self.config.config_digest,
                "source_root": str(self.config.source_root),
                "files": manifest,
            }
        )

    def _machine_binding_envelope(
        self,
        source_epoch: str | None = None,
    ) -> dict[str, Any]:
        binding = self.config.machine_binding_identity
        artifact_subject = dict(binding.get("artifact_subject", {}))
        subject_digest = _digest_payload(
            {
                "provider": self.config.provider_identity,
                "provider_source_digest": self.config.provider_source_digest,
                "config_digest": self.config.config_digest,
                "artifact_subject": artifact_subject,
            }
        )
        artifact_subject["subject_digest"] = subject_digest
        binding["artifact_subject"] = artifact_subject
        resource_envelope = dict(binding.get("resource_envelope", {}))
        resource_envelope["max_file_bytes"] = self.config.max_file_bytes
        resource_envelope["max_query_results"] = int(
            resource_envelope.get("max_query_results", MAX_QUERY_RESULTS)
        )
        binding["resource_envelope"] = resource_envelope
        live_measurement = dict(binding.get("live_measurement", {}))
        live_measurement.setdefault("required_for_admission", True)
        live_measurement["state"] = MACHINE_LIVE_MEASUREMENT_STATE
        live_measurement["owner"] = "abyss-machine"
        live_measurement["claim"] = (
            "No host health, resource health, installation, or admission is observed"
        )
        binding["live_measurement"] = live_measurement
        binding["provider"] = self.config.provider_identity
        binding["runtime_binding"] = {
            "source_root": str(self.config.source_root),
            "state_root": str(self.config.state_root),
            "state_relative_root": self.config.state_relative_root,
            "source_epoch": source_epoch,
        }
        binding["installation"] = {
            "identity": binding.get("installation_identity"),
            "state": "source-candidate",
        }
        binding["trust_binding"] = {
            "owner": "abyss-machine",
            "state": artifact_subject.get("trust_state"),
        }
        binding["admission"] = {
            "owner": "abyss-machine",
            "state": artifact_subject.get("admission_state"),
        }
        binding["claim_limits"] = [
            "source binding is a candidate envelope, not an installed artifact",
            "artifact subject and trust fields do not grant admission",
            "live measurement is required by the machine owner and is unobserved here",
        ]
        evidence = self._current_machine_evidence()
        if evidence is not None:
            binding["verified_evidence"] = self._machine_evidence_summary(evidence)
            binding["installation"] = {
                "identity": evidence["installation"]["identity"],
                "state": "verified",
                "evidence_class": MACHINE_EVIDENCE_CLASS,
            }
            binding["trust_binding"] = {
                "owner": "abyss-machine",
                "state": evidence["admission"]["trust_state"],
                "evidence_class": MACHINE_EVIDENCE_CLASS,
            }
            binding["admission"] = {
                "owner": "abyss-machine",
                "state": evidence["admission"]["state"],
                "evidence_class": MACHINE_EVIDENCE_CLASS,
            }
            binding["live_measurement"] = {
                **binding["live_measurement"],
                "state": "observed",
                "evidence_class": MACHINE_EVIDENCE_CLASS,
                "measurement_ref": evidence["health"]["measurement_ref"],
                "observed_at": evidence["health"]["observed_at"],
            }
        return binding

    @staticmethod
    def _machine_evidence_summary(
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        providers = evidence.get("providers", [])
        observations = evidence.get("observations", [])
        return {
            "schema_version": MACHINE_EVIDENCE_SCHEMA,
            "evidence_class": MACHINE_EVIDENCE_CLASS,
            "issuer": evidence["issuer"],
            "receipt_id": evidence["receipt_id"],
            "receipt_digest": evidence["receipt_digest"],
            "subject": {
                "provider_source_digest": evidence["subject"]["provider_source_digest"],
                "config_digest": evidence["subject"]["config_digest"],
                "artifact_digest": evidence["subject"]["artifact_digest"],
                "artifact_ref": evidence["subject"]["artifact_ref"],
            },
            "installation_state": evidence["installation"]["state"],
            "admission_state": evidence["admission"]["state"],
            "health_state": evidence["health"]["state"],
            "health_observed_at": evidence["health"]["observed_at"],
            "provider_count": len(providers),
            "observation_count": len(observations),
            "second_language_observed": any(
                item.get("state") == "observed"
                and item.get("language") != PROVIDER_LANGUAGE
                for item in observations
                if isinstance(item, Mapping)
            ),
            "lsp_session_count": len(evidence.get("lsp_sessions", [])),
            "lifecycle_state": evidence["lifecycle"]["state"],
            "providers_digest": _digest_payload(evidence["providers"]),
            "observations_digest": _digest_payload(evidence["observations"]),
            "lsp_sessions_digest": _digest_payload(evidence["lsp_sessions"]),
            "lifecycle_digest": _digest_payload(evidence["lifecycle"]),
            "claim_limits": list(evidence["claim_limits"]),
        }

    def _observation_lanes(
        self,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        lanes = [
            {
                "provider": self.config.provider_identity,
                "language": PROVIDER_LANGUAGE,
                "state": "source-candidate",
                "evidence_class": "owner-local-source-observation",
                "semantic_owner": "aoa-kag",
            }
        ]
        if evidence is None:
            evidence = self._current_machine_evidence()
        if evidence is None:
            lanes.append(
                {
                    "provider": "machine-owned-provider-adapter",
                    "language": "second-language",
                    "state": "receipt-only",
                    "evidence_class": "not-observed",
                    "semantic_owner": "aoa-kag",
                }
            )
            return lanes
        for provider in evidence["providers"]:
            lanes.append(
                {
                    "provider": {
                        "id": provider["id"],
                        "version": provider["version"],
                        "protocol": provider["protocol"],
                    },
                    "language": provider["language"],
                    "state": provider["observation_state"],
                    "evidence_class": MACHINE_EVIDENCE_CLASS,
                    "semantic_owner": "aoa-kag",
                }
            )
        return lanes

    def _lsp_session_surface(
        self,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence is None:
            evidence = self._current_machine_evidence()
        sessions = [] if evidence is None else evidence["lsp_sessions"]
        return {
            "schema_version": LSP_SESSION_SCHEMA,
            "owner": "abyss-stack",
            "state": (
                "observed"
                if any(session["state"] == "observed" for session in sessions)
                else "unobserved"
            ),
            "sessions": [
                {
                    "session_id": session["session_id"],
                    "provider_id": session["provider_id"],
                    "language": session["language"],
                    "state": session["state"],
                    "transport": session["transport"],
                    "source_epoch": session["source_epoch"],
                    "evidence_ref": session["evidence_ref"],
                    **(
                        {"source_root": session["source_root"]}
                        if "source_root" in session
                        else {}
                    ),
                    **(
                        {"command_digest": session["command_digest"]}
                        if "command_digest" in session
                        else {}
                    ),
                    **(
                        {"artifact_digest": session["artifact_digest"]}
                        if "artifact_digest" in session
                        else {}
                    ),
                    **(
                        {"interpreter_digest": session["interpreter_digest"]}
                        if "interpreter_digest" in session
                        else {}
                    ),
                    "evidence_class": MACHINE_EVIDENCE_CLASS,
                }
                for session in sessions
            ],
            "claim_limits": [
                "an LSP session surface is an observation boundary, not installation or proof",
                "no session is live merely because this source surface is present",
            ],
        }

    def _lifecycle_surface(
        self,
        *,
        last_good_available: bool,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence is None:
            evidence = self._current_machine_evidence()
        external = evidence["lifecycle"] if evidence is not None else None

        def component(
            name: str,
            *,
            source_state: str,
            source_ref: str,
        ) -> dict[str, Any]:
            if external is not None:
                item = external[name]
                return {
                    "state": item["state"],
                    "evidence_ref": item["evidence_ref"],
                    "evidence_class": MACHINE_EVIDENCE_CLASS,
                }
            return {
                "state": source_state,
                "evidence_ref": source_ref,
                "evidence_class": "owner-local-source-observation",
            }

        return {
            "schema_version": PROVIDER_LIFECYCLE_SCHEMA,
            "owner": "abyss-stack",
            "provider": self.config.provider_identity,
            "provider_neutral": True,
            "state": "machine-verified" if external is not None else "source-candidate",
            "operations": list(PROVIDER_LIFECYCLE_OPERATIONS),
            "refresh": {
                "state": "source-observed",
                "evidence_ref": "runtime:live-code-intelligence:refresh",
                "evidence_class": "owner-local-source-observation",
            },
            "restart": component(
                "restart",
                source_state="not-observed",
                source_ref="runtime:live-code-intelligence:restart-not-observed",
            ),
            "last_good": component(
                "last_good",
                source_state="available" if last_good_available else "unavailable",
                source_ref="runtime:live-code-intelligence:last-good-state",
            ),
            "canary": component(
                "canary",
                source_state="not-observed",
                source_ref="runtime:live-code-intelligence:canary-not-observed",
            ),
            "rollback": component(
                "rollback",
                source_state="available" if last_good_available else "unavailable",
                source_ref="runtime:live-code-intelligence:rollback-state",
            ),
            "claim_limits": [
                "source refresh and last-good state do not prove deployed lifecycle behavior",
                "restart, canary, rollback, and host health remain explicit evidence axes",
                "operator activation and machine admission remain outside this source boundary",
            ],
        }

    def _provider_worker_surface(
        self,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Describe the bounded worker plane without claiming external execution."""

        primary = {
            "id": self.config.provider_id,
            "version": self.config.provider_version,
            "language": PROVIDER_LANGUAGE,
            "protocol": self.config.provider_protocol,
        }
        workers = [
            {
                "worker_id": f"worker:{self.config.provider_id}",
                "provider": primary,
                "language": PROVIDER_LANGUAGE,
                "state": "source-candidate",
                "execution": "in-process",
                "queue_id": "queue:live-code-intelligence",
                "evidence_class": "owner-local-source-observation",
            }
        ]
        if evidence is None:
            evidence = self._current_machine_evidence()
        second_language_providers = (
            [
                provider
                for provider in evidence["providers"]
                if provider["language"] != PROVIDER_LANGUAGE
            ]
            if evidence is not None
            else []
        )
        if not second_language_providers:
            second_language_providers = [
                {
                    "id": SECOND_LANGUAGE_PROVIDER_ID,
                    "version": "receipt-only",
                    "language": SECOND_LANGUAGE,
                    "protocol": "lsp",
                }
            ]
        for provider in second_language_providers:
            workers.append(
                {
                    "worker_id": f"worker:{provider['id']}",
                    "provider": {
                        "id": provider["id"],
                        "version": provider["version"],
                        "language": provider["language"],
                        "protocol": provider["protocol"],
                    },
                    "language": provider["language"],
                    "state": "receipt-only",
                    "execution": "not-started",
                    "queue_id": "queue:live-code-intelligence",
                    "evidence_class": (
                        MACHINE_EVIDENCE_CLASS
                        if evidence is not None
                        else "not-observed"
                    ),
                }
            )
        return {
            "schema_version": PROVIDER_WORKER_SCHEMA,
            "owner": "abyss-stack",
            "queue": {
                "schema_version": PROVIDER_WORK_QUEUE_SCHEMA,
                "queue_id": "queue:live-code-intelligence",
                "state": "idle",
                "capacity": PROVIDER_QUEUE_CAPACITY,
                "depth": 0,
                "ordering": "path-lexicographic",
                "delivery": "bounded-serialized",
            },
            "workers": workers,
            "claim_limits": [
                "the Python worker is a source-local in-process observer",
                "the bounded queue does not activate or admit a machine provider",
                "the second-language worker is a receipt-only route until its owner supplies live evidence",
            ],
        }

    def _owner_review_surface(
        self,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if evidence is None:
            evidence = self._current_machine_evidence()
        return {
            "schema_version": OWNER_REVIEW_SCHEMA,
            "owner": "abyss-stack",
            "state": "review_required",
            "source_readiness": "candidate",
            "machine_evidence": (
                "present"
                if evidence is not None
                else "missing"
                if self.config.machine_evidence is None
                else "stale"
            ),
            "landing": "not_authorized",
            "proof": "unclaimed",
            "owner_acceptance": "unclaimed",
            "required_separations": [
                "source readiness vs CI collection",
                "machine installation/admission/health vs deployed runtime",
                "runtime evidence vs proof/eval verdict",
                "review readiness vs landing and owner acceptance",
            ],
        }

    def _observation_envelope(
        self,
        *,
        status: str,
        source_epoch: str,
        files: Mapping[str, Mapping[str, Any]],
        invalidation: Mapping[str, Any],
        diagnostics: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_ENVELOPE_SCHEMA,
            "layer": "LIVE",
            "status": status,
            "source_epoch": source_epoch,
            "provider": self.config.provider_identity,
            "machine_binding": self._machine_binding_envelope(source_epoch),
            "source": {
                "root": str(self.config.source_root),
                "file_count": len(files),
                "bytes_scanned": sum(
                    int(item.get("size_bytes", 0)) for item in files.values()
                ),
            },
            "invalidation": dict(invalidation),
            "diagnostic_count": len(diagnostics),
            "claim_limits": [
                "LIVE observation is runtime evidence, not INDEXED knowledge or proof",
                "provider installation, admission, and host health remain machine-owned",
                "observation meaning and normalization remain aoa-kag-owned",
            ],
        }

    @staticmethod
    def _import_targets(record: Mapping[str, Any]) -> set[str]:
        observation = record.get("observation")
        if not isinstance(observation, Mapping):
            return set()
        return {
            str(item.get("target"))
            for item in observation.get("relations", [])
            if isinstance(item, Mapping) and item.get("relation_kind") == "imports"
        }

    @staticmethod
    def _normalized_import_targets(
        path: str,
        imported: str,
        known_paths: Collection[str],
    ) -> set[str]:
        if not imported.startswith("."):
            return {imported}
        targets: set[str] = set()
        level = len(imported) - len(imported.lstrip("."))
        suffix = imported[level:]
        for module_name in _module_name_variants(path, known_paths):
            module_parts = module_name.split(".")
            package_parts = (
                module_parts
                if Path(path).name == "__init__.py"
                else module_parts[:-1]
            )
            parent_parts = package_parts[: max(0, len(package_parts) - level + 1)]
            target = ".".join(part for part in (*parent_parts, suffix) if part)
            if target:
                targets.add(target)
        return targets

    def _dependency_impacts(
        self,
        previous: Mapping[str, Mapping[str, Any]],
        changed_paths: set[str],
    ) -> set[str]:
        known_paths = set(previous).union(changed_paths)
        changed_modules = set().union(
            *(
                _module_name_variants(path, known_paths)
                for path in changed_paths
            )
        )
        if not changed_modules:
            return set()
        impacted: set[str] = set()
        frontier = set(changed_modules)
        while frontier:
            next_frontier: set[str] = set()
            for path, record in previous.items():
                if path in changed_paths or path in impacted:
                    continue
                imports = {
                    target
                    for imported in self._import_targets(record)
                    for target in self._normalized_import_targets(
                        path, imported, known_paths
                    )
                }
                if any(
                    imported == changed or imported.startswith(f"{changed}.")
                    for imported in imports
                    for changed in frontier
                ):
                    impacted.add(path)
                    next_frontier.update(
                        _module_name_variants(path, known_paths)
                    )
            frontier = next_frontier
        return impacted

    def _read_and_parse(self, path: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
        size_bytes = int(metadata.get("size_bytes", 0))
        if size_bytes > self.config.max_file_bytes:
            return {
                "path": path,
                "content_digest": metadata["content_digest"],
                "size_bytes": size_bytes,
                "observation": None,
                "diagnostics": [
                    {
                        "code": "file_too_large",
                        "severity": "error",
                        "message": f"file exceeds {self.config.max_file_bytes} bytes",
                    }
                ],
            }
        path_diagnostics = metadata.get("scan_diagnostics")
        if isinstance(path_diagnostics, Sequence) and not isinstance(
            path_diagnostics, (str, bytes, bytearray)
        ) and path_diagnostics:
            return {
                "path": path,
                "content_digest": metadata["content_digest"],
                "size_bytes": size_bytes,
                "observation": None,
                "diagnostics": [
                    dict(diagnostic)
                    for diagnostic in path_diagnostics
                    if isinstance(diagnostic, Mapping)
                ],
            }
        source_path = self.config.source_root / Path(path)
        fresh_metadata = self._read_source_metadata(
            source_path,
            self.config.source_root,
            self.config.max_file_bytes,
            retain_content=True,
        )
        if (
            fresh_metadata is None
            or fresh_metadata.get("content_digest") != metadata.get("content_digest")
            or int(fresh_metadata.get("size_bytes", -1)) != size_bytes
        ):
            raise LiveCodeIntelligenceError(
                f"source changed during refresh: {path}"
            )
        content = fresh_metadata.get("content")
        if not isinstance(content, bytes):
            raise LiveCodeIntelligenceError(f"missing source bytes for {path}")
        return _parse_file(path, content)

    def _run_provider_work_queue(
        self,
        paths: set[str],
        scanned: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Drain source parse work in bounded, deterministic batches."""

        queue = _ProviderWorkQueue()
        records: dict[str, dict[str, Any]] = {}

        def drain() -> None:
            while queue:
                item = queue.dequeue()
                records[item.path] = self._read_and_parse(item.path, item.metadata)

        for path in sorted(paths):
            queue.enqueue(_ProviderWorkItem(path=path, metadata=scanned[path]))
            if len(queue) == queue.capacity:
                drain()
        drain()
        return records

    def _state_payload(
        self,
        *,
        status: str,
        source_epoch: str,
        files: Mapping[str, Mapping[str, Any]],
        invalidation: Mapping[str, Any],
        diagnostics: Sequence[Mapping[str, Any]],
        previous_epoch: str | None,
        last_good_epoch: str | None,
        full_rebuild: bool,
        last_good_available: bool,
    ) -> dict[str, Any]:
        serial_files = {
            path: {
                key: copy.deepcopy(value)
                for key, value in record.items()
                if key not in {"content", "scan_diagnostics"}
            }
            for path, record in sorted(files.items())
        }
        symbols = sum(
            len(record.get("observation", {}).get("symbols", []))
            for record in serial_files.values()
            if isinstance(record.get("observation"), Mapping)
        )
        occurrences = sum(
            len(record.get("observation", {}).get("occurrences", []))
            for record in serial_files.values()
            if isinstance(record.get("observation"), Mapping)
        )
        relations = sum(
            len(record.get("observation", {}).get("relations", []))
            for record in serial_files.values()
            if isinstance(record.get("observation"), Mapping)
        )
        error_count = sum(len(record.get("diagnostics", [])) for record in serial_files.values())
        observation_envelope = self._observation_envelope(
            status=status,
            source_epoch=source_epoch,
            files=serial_files,
            invalidation=invalidation,
            diagnostics=diagnostics,
        )
        return {
            "schema_version": STATE_SCHEMA,
            "status": status,
            "state": status,
            "observed_at": _now(),
            "provider": self.config.provider_identity,
            "machine_consumer_abi": copy.deepcopy(MACHINE_CONSUMER_ABI),
            "config": {
                "digest": self.config.config_digest,
                "include_suffixes": list(self.config.include_suffixes),
                "exclude_dirs": list(self.config.exclude_dirs),
                "max_file_bytes": self.config.max_file_bytes,
                "state_relative_root": self.config.state_relative_root,
                "state_promotion": self.config.state_promotion,
                "state_fallback": self.config.state_fallback,
                "owner_boundaries": dict(self.config.owner_boundaries),
            },
            "source": {
                "root": str(self.config.source_root),
                "source_epoch": source_epoch,
                "file_count": len(serial_files),
            },
            "machine_binding": observation_envelope["machine_binding"],
            "observation_envelope": observation_envelope,
            "observation_lanes": self._observation_lanes(),
            "provider_workers": self._provider_worker_surface(),
            "lsp_sessions": self._lsp_session_surface(),
            "lifecycle": self._lifecycle_surface(
                last_good_available=last_good_available
            ),
            "owner_review": self._owner_review_surface(),
            "files": serial_files,
            "summary": {
                "source_file_count": len(serial_files),
                "symbol_count": symbols,
                "occurrence_count": occurrences,
                "relation_count": relations,
                "diagnostic_count": error_count,
            },
            "invalidation": dict(invalidation),
            "freshness": {
                "layer": "LIVE",
                "source_epoch": source_epoch,
                "provider": self.config.provider_identity,
                "confidence": "observed" if status == "current" else "degraded",
            },
            "degradation": [dict(item) for item in diagnostics],
            "fallback": (
                {"state": "current", "source_epoch": previous_epoch}
                if status == "degraded" and previous_epoch
                else (
                    {"state": "last-good", "source_epoch": last_good_epoch}
                    if status == "degraded" and last_good_epoch
                    else None
                )
            ),
            "provenance": {
                "runtime_owner": "abyss-stack",
                "observation_meaning_owner": "aoa-kag",
                "proof_owner": "aoa-evals",
                "source_kind": "working_tree",
                "full_rebuild": full_rebuild,
            },
        }

    def _write_receipt(
        self,
        *,
        state: Mapping[str, Any],
        outcome: str,
        previous_epoch: str | None,
    ) -> None:
        source_epoch = str(state["source"]["source_epoch"])
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "observed_at": state["observed_at"],
            "observation_digest": _digest_payload(state["files"]),
            "outcome": outcome,
            "source_epoch": source_epoch,
            "previous_source_epoch": previous_epoch,
            "current_source_epoch": (
                source_epoch if outcome == "current" else previous_epoch
            ),
            "candidate_source_epoch": source_epoch if outcome == "degraded" else None,
            "invalidation": state["invalidation"],
            "degradation": state["degradation"],
            "provenance": state["provenance"],
        }
        self._prepare_receipt_directory()
        _write_json_atomic(
            self.receipts_path
            / f"{source_epoch.removeprefix('sha256:')}.json",
            receipt,
        )

    def _prepare_receipt_directory(self) -> None:
        if _contains_symlink(self.receipts_path):
            raise LiveCodeIntelligenceError(
                f"refusing to write through symlinked receipt directory: {self.receipts_path}"
            )
        try:
            self.receipts_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                f"unable to prepare receipt directory: {self.receipts_path}"
            ) from exc
        if not self.receipts_path.is_dir() or self.receipts_path.is_symlink():
            raise LiveCodeIntelligenceError(
                f"receipt path must be a real directory: {self.receipts_path}"
            )

    @staticmethod
    def _restore_json_snapshot(
        path: Path,
        snapshot: Mapping[str, Any],
    ) -> None:
        """Restore one valid JSON state file, or remove its prior absence."""

        if snapshot:
            _write_json_atomic(path, snapshot)
            return
        if not path.parent.exists() or not path.parent.is_dir():
            return
        if _contains_symlink(path):
            raise LiveCodeIntelligenceError(
                f"refusing to remove symlinked state path: {path}"
            )
        path.unlink(missing_ok=True)

    def _prepare_operation_receipt_directory(self) -> None:
        if _contains_symlink(self.operation_receipts_path):
            raise LiveCodeIntelligenceError(
                "refusing to write through symlinked operation receipt directory: "
                f"{self.operation_receipts_path}"
            )
        try:
            self.operation_receipts_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LiveCodeIntelligenceError(
                "unable to prepare operation receipt directory: "
                f"{self.operation_receipts_path}"
            ) from exc
        if (
            not self.operation_receipts_path.is_dir()
            or self.operation_receipts_path.is_symlink()
        ):
            raise LiveCodeIntelligenceError(
                "operation receipt path must be a real directory: "
                f"{self.operation_receipts_path}"
            )

    @staticmethod
    def _observation_is_well_formed(
        observation: Any,
        *,
        path: str,
        content_digest: str,
    ) -> bool:
        """Validate the complete provider output before it becomes queryable."""

        if not isinstance(observation, Mapping) or set(observation) != {
            "schema_version",
            "state",
            "provider",
            "source",
            "symbols",
            "occurrences",
            "relations",
            "provenance",
        }:
            return False
        expected_provider = {
            "id": PROVIDER_ID,
            "version": PROVIDER_VERSION,
            "language": PROVIDER_LANGUAGE,
        }
        if (
            observation.get("schema_version") != OBSERVATION_SCHEMA
            or observation.get("state") != "live"
            or observation.get("provider") != expected_provider
        ):
            return False
        source = observation.get("source")
        if (
            not isinstance(source, Mapping)
            or set(source) != {"path", "content_digest", "epoch_binding"}
            or source.get("path") != path
            or source.get("content_digest") != content_digest
            or source.get("epoch_binding") != "state.source.source_epoch"
        ):
            return False
        if observation.get("provenance") != {
            "source_kind": "working_tree",
            "semantic_owner": "aoa-kag",
            "runtime_owner": "abyss-stack",
        }:
            return False

        symbols = observation.get("symbols")
        if not isinstance(symbols, list):
            return False
        symbol_ids: set[str] = set()
        symbols_by_id: dict[str, Mapping[str, Any]] = {}
        expected_lineage = {
            "status": "unresolved",
            "reason": "bootstrap provider does not infer rename or move continuity",
            "confidence": "none",
        }
        for symbol in symbols:
            if not isinstance(symbol, Mapping):
                return False
            base_keys = {
                "id",
                "handle",
                "name",
                "qualified_name",
                "kind",
                "identity_scope",
                "lineage",
            }
            symbol_keys = set(symbol)
            if symbol_keys not in (base_keys, base_keys | {"definition"}):
                return False
            if any(
                not isinstance(symbol.get(key), str) or not symbol.get(key)
                for key in ("id", "handle", "name", "qualified_name", "kind")
            ):
                return False
            kind = symbol["kind"]
            if kind not in {"module", "class", "function"}:
                return False
            if ("definition" in symbol) != (kind != "module"):
                return False
            qualified_name = symbol["qualified_name"]
            expected_name = (
                _module_name(path)
                if kind == "module"
                else qualified_name.rsplit(".", 1)[-1]
            )
            if symbol["name"] != expected_name:
                return False
            if symbol.get("identity_scope") != "path-qualified":
                return False
            if symbol.get("lineage") != expected_lineage:
                return False
            symbol_id = symbol["id"]
            definition = symbol.get("definition") if kind != "module" else None
            expected_id = _symbol_id(path, kind, qualified_name, definition)
            expected_handle = (
                f"python://{path}#{qualified_name}"
                if definition is None
                else f"python://{path}#{qualified_name}@{definition.split('#', 1)[1]}"
            )
            if (
                symbol_id != expected_id
                or symbol.get("handle")
                != expected_handle
                or symbol_id in symbol_ids
            ):
                return False
            if "definition" in symbol and not _anchor_is_well_formed(
                symbol["definition"], path
            ):
                return False
            symbol_ids.add(symbol_id)
            symbols_by_id[symbol_id] = symbol
        if [symbol["id"] for symbol in symbols] != sorted(symbol_ids):
            return False

        occurrences = observation.get("occurrences")
        if not isinstance(occurrences, list):
            return False
        occurrence_keys = {
            "definition": {
                "kind",
                "name",
                "symbol_id",
                "scope_id",
                "location",
                "confidence",
            },
            "import": {"kind", "name", "scope_id", "location", "confidence"},
            "reference": {
                "kind",
                "name",
                "role",
                "scope_id",
                "location",
                "confidence",
                "context",
            },
        }
        for occurrence in occurrences:
            if not isinstance(occurrence, Mapping):
                return False
            kind = occurrence.get("kind")
            if kind not in occurrence_keys or set(occurrence) != occurrence_keys[kind]:
                return False
            if (
                not isinstance(occurrence.get("name"), str)
                or not occurrence["name"]
                or occurrence.get("scope_id") not in symbol_ids
                or not _anchor_is_well_formed(occurrence.get("location"), path)
            ):
                return False
            if occurrence.get("confidence") not in {"medium", "high"}:
                return False
            if kind == "definition":
                symbol_id = occurrence.get("symbol_id")
                if (
                    symbol_id not in symbol_ids
                    or symbols_by_id[symbol_id].get("name") != occurrence["name"]
                    or occurrence.get("confidence") != "high"
                ):
                    return False
            elif kind == "import":
                if occurrence.get("confidence") != "high":
                    return False
            else:
                role = occurrence.get("role")
                if role not in {"read", "write"} or occurrence.get("context") not in {
                    "load",
                    "store",
                    "del",
                }:
                    return False
                if occurrence["confidence"] != (
                    "high" if role == "write" else "medium"
                ):
                    return False
        if [
            (item["location"], item["kind"], item["name"])
            for item in occurrences
        ] != sorted(
            (item["location"], item["kind"], item["name"])
            for item in occurrences
        ):
            return False

        relations = observation.get("relations")
        if not isinstance(relations, list):
            return False
        relation_ids: set[str] = set()
        for relation in relations:
            if not isinstance(relation, Mapping) or set(relation) != {
                "id",
                "relation_kind",
                "from_id",
                "to_id",
                "target",
                "occurrence",
                "confidence",
                "provenance",
            }:
                return False
            if any(
                not isinstance(relation.get(key), str) or not relation.get(key)
                for key in (
                    "id",
                    "relation_kind",
                    "from_id",
                    "to_id",
                    "target",
                    "occurrence",
                    "confidence",
                    "provenance",
                )
            ):
                return False
            relation_kind = relation["relation_kind"]
            if relation_kind not in {"contains", "imports", "calls"}:
                return False
            expected_confidence = "high" if relation_kind in {"contains", "imports"} else "medium"
            if (
                relation["from_id"] not in symbol_ids
                or not _anchor_is_well_formed(relation["occurrence"], path)
                or relation["confidence"] != expected_confidence
                or relation["provenance"] != "python-ast"
            ):
                return False
            expected_relation_id = _digest_payload(
                {
                    "kind": relation_kind,
                    "source": relation["from_id"],
                    "target": relation["target"],
                    "anchor": relation["occurrence"],
                }
            )
            if relation["id"] != (
                f"relation:python:{expected_relation_id.removeprefix('sha256:')}"
            ) or relation["id"] in relation_ids:
                return False
            if relation_kind == "contains":
                target = symbols_by_id.get(relation["to_id"])
                if target is None or target.get("qualified_name") != relation["target"]:
                    return False
            elif relation["to_id"] != _unresolved_id(relation["target"]):
                return False
            relation_ids.add(relation["id"])
        if [relation["id"] for relation in relations] != sorted(relation_ids):
            return False
        return True

    def _lifecycle_matches_config(
        self,
        lifecycle: Any,
        *,
        evidence: Mapping[str, Any] | None = None,
    ) -> bool:
        """Accept only a lifecycle surface emitted for this exact config."""

        return any(
            lifecycle
            == self._lifecycle_surface(
                last_good_available=available,
                evidence=evidence,
            )
            for available in (False, True)
        )

    def _persisted_machine_binding_is_well_formed(
        self,
        binding: Any,
        source_epoch: str,
    ) -> bool:
        """Validate capture-time posture without making it a freshness gate.

        The source snapshot is independently useful after machine health has
        expired.  Its stable machine identity must still match this config,
        while observed/verified fields are retained as historical evidence and
        are not re-emitted as current posture by ``status``.
        """

        if not isinstance(binding, Mapping):
            return False
        expected = self._machine_binding_envelope(source_epoch)
        expected_stable = _machine_binding_stable_projection(expected)
        actual_stable = _machine_binding_stable_projection(binding)
        if actual_stable is None or actual_stable != expected_stable:
            return False
        if not set(binding).issubset(set(expected) | {"verified_evidence"}):
            return False

        runtime_binding = binding.get("runtime_binding")
        if not isinstance(runtime_binding, Mapping) or set(runtime_binding) != {
            "source_root",
            "state_root",
            "state_relative_root",
            "source_epoch",
        }:
            return False
        if (
            runtime_binding.get("source_root") != str(self.config.source_root)
            or runtime_binding.get("state_root") != str(self.config.state_root)
            or runtime_binding.get("state_relative_root")
            != self.config.state_relative_root
            or runtime_binding.get("source_epoch") != source_epoch
        ):
            return False

        installation = binding.get("installation")
        if not isinstance(installation, Mapping):
            return False
        installation_state = installation.get("state")
        expected_installation_keys = {
            "identity",
            "state",
        }
        if installation_state == "verified":
            expected_installation_keys.add("evidence_class")
        if (
            set(installation) != expected_installation_keys
            or not isinstance(installation.get("identity"), str)
            or not installation.get("identity")
            or installation_state not in {"source-candidate", "verified"}
        ):
            return False
        if installation_state == "source-candidate" and installation.get(
            "identity"
        ) != self.config.machine_binding_identity["installation_identity"]:
            return False
        if installation_state == "verified" and installation.get(
            "evidence_class"
        ) != MACHINE_EVIDENCE_CLASS:
            return False

        for name, allowed_states in (
            ("trust_binding", {"not-admitted", "trusted"}),
            ("admission", {"unknown", "admitted"}),
        ):
            component = binding.get(name)
            if not isinstance(component, Mapping):
                return False
            expected_component_keys = {"owner", "state"}
            if component.get("state") == ("trusted" if name == "trust_binding" else "admitted"):
                expected_component_keys.add("evidence_class")
            if (
                set(component) != expected_component_keys
                or component.get("owner") != "abyss-machine"
                or component.get("state") not in allowed_states
            ):
                return False
            if "evidence_class" in component and component.get(
                "evidence_class"
            ) != MACHINE_EVIDENCE_CLASS:
                return False

        live_measurement = binding.get("live_measurement")
        if not isinstance(live_measurement, Mapping):
            return False
        live_base_keys = {
            "required_for_admission",
            "state",
            "owner",
            "claim",
        }
        if (
            live_measurement.get("required_for_admission") is not True
            or live_measurement.get("owner") != "abyss-machine"
            or live_measurement.get("claim")
            != "No host health, resource health, installation, or admission is observed"
        ):
            return False
        if live_measurement.get("state") == "unobserved":
            if set(live_measurement) != live_base_keys:
                return False
        elif live_measurement.get("state") == "observed":
            if set(live_measurement) != live_base_keys | {
                "evidence_class",
                "measurement_ref",
                "observed_at",
            }:
                return False
            if live_measurement.get("evidence_class") != MACHINE_EVIDENCE_CLASS:
                return False
            if not all(
                isinstance(live_measurement.get(key), str)
                and bool(live_measurement.get(key))
                for key in ("measurement_ref", "observed_at")
            ):
                return False
        else:
            return False

        verified_evidence = binding.get("verified_evidence")
        if verified_evidence is not None:
            if not isinstance(verified_evidence, Mapping):
                return False
            required_keys = {
                "schema_version",
                "evidence_class",
                "issuer",
                "receipt_id",
                "receipt_digest",
                "subject",
                "installation_state",
                "admission_state",
                "health_state",
                "health_observed_at",
                "provider_count",
                "observation_count",
                "second_language_observed",
                "lsp_session_count",
                "lifecycle_state",
                "providers_digest",
                "observations_digest",
                "lsp_sessions_digest",
                "lifecycle_digest",
                "claim_limits",
            }
            if set(verified_evidence) != required_keys:
                return False
            if (
                verified_evidence.get("schema_version") != MACHINE_EVIDENCE_SCHEMA
                or verified_evidence.get("evidence_class") != MACHINE_EVIDENCE_CLASS
                or verified_evidence.get("issuer") != "abyss-machine"
                or not _is_sha256_reference(verified_evidence.get("receipt_digest"))
                or not isinstance(verified_evidence.get("subject"), Mapping)
                or not isinstance(verified_evidence.get("claim_limits"), list)
            ):
                return False
        expected_verified_evidence = self._captured_machine_evidence_summary
        if expected_verified_evidence is not None:
            dynamic_posture_is_verified = (
                installation_state == "verified"
                or binding["trust_binding"].get("state") == "trusted"
                or binding["admission"].get("state") == "admitted"
                or live_measurement.get("state") == "observed"
            )
            if dynamic_posture_is_verified:
                if verified_evidence != expected_verified_evidence:
                    return False
            elif (
                verified_evidence is not None
                and verified_evidence != expected_verified_evidence
            ):
                return False
        if not isinstance(self.config.machine_evidence, _AuthenticatedMachineEvidence):
            if (
                installation_state != "source-candidate"
                or binding["trust_binding"].get("state") != "not-admitted"
                or binding["admission"].get("state") != "unknown"
                or live_measurement.get("state") != "unobserved"
                or verified_evidence is not None
            ):
                return False
        return True

    def _persisted_state_is_well_formed(self, state: Mapping[str, Any]) -> bool:
        """Reject structurally corrupted state before it can be queried.

        The state files are runtime outputs, not signed artifacts. Identity
        binding alone is therefore insufficient: a locally modified file must
        not become a trusted query surface merely because its provider and
        config fields still match.
        """

        expected_keys = {
            "schema_version",
            "status",
            "state",
            "observed_at",
            "provider",
            "machine_consumer_abi",
            "config",
            "source",
            "machine_binding",
            "observation_envelope",
            "observation_lanes",
            "provider_workers",
            "lsp_sessions",
            "lifecycle",
            "owner_review",
            "files",
            "summary",
            "invalidation",
            "freshness",
            "degradation",
            "fallback",
            "provenance",
        }
        if set(state) != expected_keys:
            return False
        status = state.get("status")
        if status not in {"current", "degraded"} or state.get("state") != status:
            return False
        if not isinstance(state.get("observed_at"), str) or not state["observed_at"]:
            return False

        source = state.get("source")
        if not isinstance(source, Mapping) or set(source) != {
            "root",
            "source_epoch",
            "file_count",
        }:
            return False
        if source.get("root") != str(self.config.source_root):
            return False
        source_epoch = source.get("source_epoch")
        if not _is_sha256_reference(source_epoch):
            return False
        file_count = source.get("file_count")
        if isinstance(file_count, bool) or not isinstance(file_count, int):
            return False

        files = state.get("files")
        if not isinstance(files, Mapping):
            return False
        record_keys = {"path", "content_digest", "size_bytes", "observation", "diagnostics"}
        symbol_count = 0
        occurrence_count = 0
        relation_count = 0
        diagnostic_records: list[dict[str, Any]] = []
        for path, record in files.items():
            if (
                not isinstance(path, str)
                or not path
                or "\\" in path
                or Path(path).is_absolute()
                or any(part in {"", ".", ".."} for part in Path(path).parts)
                or not isinstance(record, Mapping)
                or set(record) != record_keys
                or record.get("path") != path
                or not _is_sha256_reference(record.get("content_digest"))
            ):
                return False
            size_bytes = record.get("size_bytes")
            if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes < 0:
                return False
            diagnostics = record.get("diagnostics")
            if not isinstance(diagnostics, list):
                return False
            for diagnostic in diagnostics:
                if (
                    not isinstance(diagnostic, Mapping)
                    or set(diagnostic) != {"code", "severity", "message"}
                    or any(
                        not isinstance(diagnostic.get(key), str) or not diagnostic.get(key)
                        for key in ("code", "severity", "message")
                    )
                ):
                    return False
                diagnostic_records.append(
                    {**dict(diagnostic), "path": path}
                )
            observation = record.get("observation")
            if observation is None:
                if not diagnostics:
                    return False
                continue
            if not self._observation_is_well_formed(
                observation,
                path=path,
                content_digest=record["content_digest"],
            ):
                return False
            symbol_count += len(observation["symbols"])
            occurrence_count += len(observation["occurrences"])
            relation_count += len(observation["relations"])

        if file_count != len(files):
            return False
        if source_epoch != self._source_epoch(files):
            return False
        if not self._persisted_machine_binding_is_well_formed(
            state.get("machine_binding"), source_epoch
        ):
            return False
        summary = state.get("summary")
        expected_summary = {
            "source_file_count": len(files),
            "symbol_count": symbol_count,
            "occurrence_count": occurrence_count,
            "relation_count": relation_count,
            "diagnostic_count": len(diagnostic_records),
        }
        if summary != expected_summary:
            return False
        degradation = state.get("degradation")
        if degradation != diagnostic_records or (status == "current") != (not degradation):
            return False

        invalidation = state.get("invalidation")
        if not isinstance(invalidation, Mapping) or set(invalidation) != {
            "changed_paths",
            "added_paths",
            "deleted_paths",
            "dependency_impacted_paths",
            "invalidated_paths",
            "reused_paths",
            "full_rebuild",
            "blast_radius_universe",
            "blast_radius",
        }:
            return False

        def path_list(value: Any) -> list[str] | None:
            if not isinstance(value, list) or any(
                not isinstance(item, str)
                or not item
                or "\\" in item
                or Path(item).is_absolute()
                or any(part in {"", ".", ".."} for part in Path(item).parts)
                for item in value
            ):
                return None
            if value != sorted(set(value)):
                return None
            return list(value)

        changed = path_list(invalidation.get("changed_paths"))
        added = path_list(invalidation.get("added_paths"))
        deleted = path_list(invalidation.get("deleted_paths"))
        impacted = path_list(invalidation.get("dependency_impacted_paths"))
        invalidated = path_list(invalidation.get("invalidated_paths"))
        reused = path_list(invalidation.get("reused_paths"))
        if any(item is None for item in (changed, added, deleted, impacted, invalidated, reused)):
            return False
        universe = invalidation.get("blast_radius_universe")
        if not isinstance(universe, Mapping) or set(universe) != {"kind", "count", "paths"}:
            return False
        universe_paths = path_list(universe.get("paths"))
        universe_count = universe.get("count")
        if (
            universe.get("kind") != "previous-and-current-source-files"
            or universe_paths is None
            or isinstance(universe_count, bool)
            or not isinstance(universe_count, int)
            or universe_count != len(universe_paths)
            or universe_count < 0
        ):
            return False
        if not set(invalidated or []).issubset(set(universe_paths)):
            return False
        if not set(added or []).issubset(set(changed or [])):
            return False
        if not set(reused or []).issubset(set(files)):
            return False
        if invalidation.get("full_rebuild") is not True and invalidation.get("full_rebuild") is not False:
            return False
        blast_radius = invalidation.get("blast_radius")
        if (
            isinstance(blast_radius, bool)
            or not isinstance(blast_radius, (int, float))
            or not 0.0 <= float(blast_radius) <= 1.0
            or blast_radius
            != round((len(invalidated or []) / universe_count) if universe_count else 0.0, 6)
        ):
            return False

        envelope = state.get("observation_envelope")
        if not isinstance(envelope, Mapping) or set(envelope) != {
            "schema_version",
            "layer",
            "status",
            "source_epoch",
            "provider",
            "machine_binding",
            "source",
            "invalidation",
            "diagnostic_count",
            "claim_limits",
        }:
            return False
        envelope_source = envelope.get("source")
        if (
            envelope.get("schema_version") != OBSERVATION_ENVELOPE_SCHEMA
            or envelope.get("layer") != "LIVE"
            or envelope.get("status") != status
            or envelope.get("source_epoch") != source_epoch
            or envelope.get("provider") != self.config.provider_identity
            or envelope.get("machine_binding") != state.get("machine_binding")
            or envelope.get("invalidation") != invalidation
            or envelope.get("diagnostic_count") != len(diagnostic_records)
            or not isinstance(envelope_source, Mapping)
            or envelope_source != {
                "root": str(self.config.source_root),
                "file_count": len(files),
                "bytes_scanned": sum(int(record["size_bytes"]) for record in files.values()),
            }
        ):
            return False

        freshness = state.get("freshness")
        if freshness != {
            "layer": "LIVE",
            "source_epoch": source_epoch,
            "provider": self.config.provider_identity,
            "confidence": "observed" if status == "current" else "degraded",
        }:
            return False
        fallback = state.get("fallback")
        if status == "current":
            if fallback is not None:
                return False
        elif fallback is not None and (
            not isinstance(fallback, Mapping)
            or set(fallback) != {"state", "source_epoch"}
            or fallback.get("state") not in {"current", "last-good"}
            or not _is_sha256_reference(fallback.get("source_epoch"))
        ):
            return False
        provenance = state.get("provenance")
        if provenance != {
            "runtime_owner": "abyss-stack",
            "observation_meaning_owner": "aoa-kag",
            "proof_owner": "aoa-evals",
            "source_kind": "working_tree",
            "full_rebuild": invalidation.get("full_rebuild"),
        }:
            return False
        if not self._persisted_observations_match_source(
            source_epoch=source_epoch,
            files=files,
        ):
            return False
        return True

    def _persisted_observations_match_source(
        self,
        *,
        source_epoch: str,
        files: Mapping[str, Mapping[str, Any]],
    ) -> bool:
        """Re-derive persisted rows from the epoch-bound source before use.

        State files are runtime outputs rather than signed artifacts.  Their
        shape and content digests therefore cannot authenticate observations:
        a local writer could replace a symbol or relation while preserving
        every structural field and the recorded epoch.  Re-reading and
        parsing the current source binds every served observation to the
        actual bytes represented by that epoch.
        """

        try:
            scanned = self._scan()
            if self._source_epoch(scanned) != source_epoch:
                # A historical snapshot has no live source bytes to rederive
                # against.  A receipt beside the state is writable by the
                # same UID and therefore cannot authenticate it.  Only a
                # state committed by this still-live runtime instance may be
                # used until an owner-backed immutable epoch store exists.
                return self._trusted_observation_digests.get(source_epoch) == (
                    _digest_payload(files)
                )
            parsed = self._run_provider_work_queue(set(scanned), scanned)
            expected = {
                path: {
                    key: copy.deepcopy(value)
                    for key, value in record.items()
                    if key not in {"content", "scan_diagnostics"}
                }
                for path, record in parsed.items()
            }
            actual = {
                path: copy.deepcopy(dict(record))
                for path, record in files.items()
            }
            return actual == expected
        except Exception:
            return False

    def _state_identity_matches_config(self, state: Mapping[str, Any]) -> bool:
        if not self._persisted_state_is_well_formed(state):
            return False
        config = state.get("config")
        source = state.get("source")
        if (
            state.get("schema_version") != STATE_SCHEMA
            or state.get("provider") != self.config.provider_identity
            or state.get("machine_consumer_abi") != MACHINE_CONSUMER_ABI
            or not isinstance(config, Mapping)
            or not isinstance(source, Mapping)
        ):
            return False
        expected_config = {
            "digest": self.config.config_digest,
            "include_suffixes": list(self.config.include_suffixes),
            "exclude_dirs": list(self.config.exclude_dirs),
            "max_file_bytes": self.config.max_file_bytes,
            "state_relative_root": self.config.state_relative_root,
            "state_promotion": self.config.state_promotion,
            "state_fallback": self.config.state_fallback,
            "owner_boundaries": dict(self.config.owner_boundaries),
        }
        if dict(config) != expected_config or source.get("root") != str(
            self.config.source_root
        ):
            return False
        source_epoch = source.get("source_epoch")
        if not isinstance(source_epoch, str) or not source_epoch:
            return False
        machine_binding = state.get("machine_binding")
        if not self._persisted_machine_binding_is_well_formed(
            machine_binding, source_epoch
        ):
            return False
        observation_envelope = state.get("observation_envelope")
        if not isinstance(observation_envelope, Mapping):
            return False
        if (
            observation_envelope.get("schema_version") != OBSERVATION_ENVELOPE_SCHEMA
            or observation_envelope.get("layer") != "LIVE"
            or observation_envelope.get("source_epoch") != source_epoch
            or observation_envelope.get("provider") != self.config.provider_identity
            or observation_envelope.get("machine_binding")
            != machine_binding
        ):
            return False
        identity_evidence = self._current_machine_evidence()
        if identity_evidence is None and isinstance(
            self.config.machine_evidence, _AuthenticatedMachineEvidence
        ):
            # Reconstruct the capture-time dynamic surfaces for an otherwise
            # valid persisted snapshot, while status/discover continue to use
            # the fresh-only path above and therefore report stale posture.
            identity_evidence = self.config.machine_evidence
        lifecycle = state.get("lifecycle")
        if not self._lifecycle_matches_config(
            lifecycle,
            evidence=identity_evidence,
        ):
            return False
        lsp_sessions = state.get("lsp_sessions")
        if (
            not isinstance(lsp_sessions, Mapping)
            or lsp_sessions.get("schema_version") != LSP_SESSION_SCHEMA
            or lsp_sessions.get("owner") != "abyss-stack"
            or not isinstance(lsp_sessions.get("sessions"), list)
        ):
            return False
        if lsp_sessions != self._lsp_session_surface(evidence=identity_evidence):
            return False
        if state.get("observation_lanes") != self._observation_lanes(
            evidence=identity_evidence
        ):
            return False
        if state.get("provider_workers") != self._provider_worker_surface(
            evidence=identity_evidence
        ):
            return False
        owner_review = state.get("owner_review")
        if (
            not isinstance(owner_review, Mapping)
            or dict(owner_review)
            != self._owner_review_surface(evidence=identity_evidence)
        ):
            return False
        files = state.get("files")
        if not isinstance(files, Mapping):
            return False
        for path, record in files.items():
            if not isinstance(record, Mapping):
                return False
            observation = record.get("observation")
            if observation is not None and not self._observation_is_well_formed(
                observation,
                path=path,
                content_digest=record.get("content_digest"),
            ):
                return False
        return True

    def _preferred_state(
        self,
        current: Mapping[str, Any],
        last_good: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], str] | tuple[None, None]:
        if self._state_identity_matches_config(current) and current.get(
            "status"
        ) == "current":
            return current, "current"
        if self._state_identity_matches_config(last_good) and last_good.get(
            "status"
        ) == "current":
            return last_good, "last-good"
        return None, None

    def _refresh_unlocked(self, *, force_rebuild: bool = False) -> dict[str, Any]:
        self._refresh_receipt_snapshot = None
        self._refresh_attempt_source_epoch = None
        scanned = self._scan()
        source_epoch = self._source_epoch(scanned)
        self._refresh_attempt_source_epoch = source_epoch
        transition_receipt_path = self.receipts_path / (
            f"{source_epoch.removeprefix('sha256:')}.json"
        )
        self._refresh_receipt_snapshot = (
            transition_receipt_path,
            _read_json(transition_receipt_path),
        )
        previous_current = _read_json(self.current_path)
        existing_candidate = _read_json(self.candidate_path)
        previous_files = _state_files(previous_current)
        compatible = self._state_identity_matches_config(previous_current) and (
            previous_current.get("status") == "current"
        )
        previous_epoch = (
            str(previous_current.get("source", {}).get("source_epoch"))
            if compatible and previous_current.get("source", {}).get("source_epoch")
            else None
        )
        full_rebuild = force_rebuild or not compatible
        current_meta = {
            path: {
                key: value
                for key, value in item.items()
                if key not in {"content", "scan_diagnostics"}
            }
            for path, item in scanned.items()
        }
        previous_meta = {
            path: {
                key: value
                for key, value in item.items()
                if key not in {"observation", "diagnostics"}
            }
            for path, item in previous_files.items()
        }
        content_changed = {
            path
            for path, item in current_meta.items()
            if path not in previous_meta
            or item.get("content_digest") != previous_meta[path].get("content_digest")
            or item.get("size_bytes") != previous_meta[path].get("size_bytes")
        }
        deleted = set(previous_files).difference(current_meta)
        dependency_impacted = (
            set()
            if full_rebuild
            else self._dependency_impacts(
                previous_files,
                content_changed.union(deleted),
            )
        )
        parse_paths = (
            set(current_meta)
            if full_rebuild
            else content_changed.union(dependency_impacted)
        )
        records: dict[str, dict[str, Any]] = {}
        reused: set[str] = set()
        parsed = self._run_provider_work_queue(parse_paths, scanned)
        for path, metadata in scanned.items():
            if path in parse_paths or path not in previous_files:
                records[path] = parsed[path]
            else:
                records[path] = copy.deepcopy(previous_files[path])
                reused.add(path)
        diagnostics = [
            diagnostic
            | {"path": path}
            for path, record in records.items()
            for diagnostic in record.get("diagnostics", [])
        ]
        stable_universe = set(previous_files).union(current_meta)
        invalidated_paths = parse_paths.union(deleted)
        stable_universe_count = len(stable_universe)
        invalidation = {
            "changed_paths": sorted(content_changed),
            "added_paths": sorted(set(content_changed).difference(previous_files)),
            "deleted_paths": sorted(deleted),
            "dependency_impacted_paths": sorted(dependency_impacted),
            "invalidated_paths": sorted(invalidated_paths),
            "reused_paths": sorted(reused),
            "full_rebuild": full_rebuild,
            "blast_radius_universe": {
                "kind": "previous-and-current-source-files",
                "count": stable_universe_count,
                "paths": sorted(stable_universe),
            },
            "blast_radius": round(
                (len(invalidated_paths) / stable_universe_count)
                if stable_universe_count
                else 0.0,
                6,
            ),
        }
        existing_last_good = _read_json(self.last_good_path)
        last_good_available = bool(
            self._state_identity_matches_config(existing_last_good)
            and existing_last_good.get("status") == "current"
        )
        last_good_epoch = (
            str(existing_last_good.get("source", {}).get("source_epoch"))
            if last_good_available
            else None
        )
        if (
            not diagnostics
            and compatible
            and previous_epoch
            and previous_epoch != source_epoch
        ):
            # The previous current state is promoted immediately below, so it
            # becomes the post-refresh rollback target even when no older
            # last-good file existed.
            last_good_available = True
        status = "degraded" if diagnostics else "current"
        state = self._state_payload(
            status=status,
            source_epoch=source_epoch,
            files=records,
            invalidation=invalidation,
            diagnostics=diagnostics,
            previous_epoch=previous_epoch,
            last_good_epoch=last_good_epoch,
            full_rebuild=full_rebuild,
            last_good_available=last_good_available,
        )
        self._prepare_receipt_directory()
        try:
            _write_json_atomic(self.candidate_path, state)
            if status == "degraded":
                self._write_receipt(
                    state=state,
                    outcome="degraded",
                    previous_epoch=previous_epoch,
                )
                return state
            if compatible and previous_epoch and previous_epoch != source_epoch:
                _write_json_atomic(self.last_good_path, previous_current)
            _write_json_atomic(self.current_path, state)
            self._write_receipt(
                state=state,
                outcome="current",
                previous_epoch=previous_epoch,
            )
            self.candidate_path.unlink(missing_ok=True)
        except Exception:
            if previous_current:
                _write_json_atomic(self.current_path, previous_current)
            else:
                self.current_path.unlink(missing_ok=True)
            if existing_last_good:
                _write_json_atomic(self.last_good_path, existing_last_good)
            else:
                self.last_good_path.unlink(missing_ok=True)
            self._restore_json_snapshot(self.candidate_path, existing_candidate)
            if self._refresh_receipt_snapshot is not None:
                receipt_path, receipt_snapshot = self._refresh_receipt_snapshot
                self._restore_json_snapshot(receipt_path, receipt_snapshot)
            raise
        return state

    def refresh(self) -> dict[str, Any]:
        with self._refresh_lock():
            state, _, _ = self._refresh_with_operation("refresh")
            return state

    def _write_operation_receipt(
        self,
        *,
        operation: str,
        state: str,
        source_epoch: str | None,
        previous_source_epoch: str | None = None,
        target_source_epoch: str | None = None,
    ) -> dict[str, Any]:
        """Record the bounded, stack-local outcome of one lifecycle action.

        The receipt is deliberately separate from ``current.json`` and
        ``last-good.json``.  Those snapshots have a strict identity contract;
        adding an operation marker to either would make a successful action
        alter the observation it is meant to manage.  One receipt per action
        keeps this audit surface bounded while still making the executable
        route observable after the CLI process exits.
        """

        if operation not in PROVIDER_LIFECYCLE_OPERATIONS:
            raise LiveCodeIntelligenceError(
                f"unsupported lifecycle operation: {operation}"
            )
        if not state:
            raise LiveCodeIntelligenceError("lifecycle operation state is required")
        receipt = {
            "schema_version": PROVIDER_OPERATION_SCHEMA,
            "owner": "abyss-stack",
            "operation": operation,
            "state": state,
            "observed_at": _now(),
            "source_epoch": source_epoch,
            "previous_source_epoch": previous_source_epoch,
            "target_source_epoch": target_source_epoch,
            "claim_limits": [
                "this is stack-local source-state evidence, not deployed service lifecycle evidence",
                "machine installation, admission, health, and provider activation remain outside this route",
                "the operation receipt is not semantic proof or owner acceptance",
            ],
        }
        self._prepare_operation_receipt_directory()
        _write_json_atomic(
            self.operation_receipts_path / f"{operation}.json",
            receipt,
        )
        return receipt

    @staticmethod
    def _state_epoch(state: Mapping[str, Any]) -> str | None:
        source = state.get("source")
        epoch = source.get("source_epoch") if isinstance(source, Mapping) else None
        return epoch if isinstance(epoch, str) and epoch else None

    def _refresh_with_operation(
        self,
        operation: str,
        *,
        force_rebuild: bool = False,
    ) -> tuple[dict[str, Any], str | None, dict[str, Any]]:
        """Promote a refresh only when its lifecycle receipt also commits.

        ``_refresh_unlocked`` owns the source transition receipt and the
        candidate/current/last-good snapshots.  The outer operation receipt is
        part of the same observable lifecycle action, so a publication error
        restores every snapshot touched by the refresh before propagating the
        error to the caller.
        """

        self._prepare_operation_receipt_directory()
        previous_current = _read_json(self.current_path)
        previous_last_good = _read_json(self.last_good_path)
        previous_candidate = _read_json(self.candidate_path)
        previous_epoch = self._state_epoch(previous_current)
        operation_path = self.operation_receipts_path / f"{operation}.json"
        previous_operation = _read_json(operation_path)
        try:
            state = (
                self._refresh_unlocked(force_rebuild=True)
                if force_rebuild
                else self._refresh_unlocked()
            )
            source_epoch = self._state_epoch(state)
            operation_state = (
                "current" if state.get("status") == "current" else "degraded"
            )
            receipt = self._write_operation_receipt(
                operation=operation,
                state=operation_state,
                source_epoch=source_epoch,
                previous_source_epoch=previous_epoch,
                target_source_epoch=source_epoch,
            )
            if source_epoch is not None:
                self._trusted_observation_digests[source_epoch] = _digest_payload(
                    state["files"]
                )
        except Exception:
            self._restore_json_snapshot(self.current_path, previous_current)
            self._restore_json_snapshot(self.last_good_path, previous_last_good)
            self._restore_json_snapshot(self.candidate_path, previous_candidate)
            self._restore_json_snapshot(operation_path, previous_operation)
            if self._refresh_receipt_snapshot is not None:
                transition_path, transition_snapshot = self._refresh_receipt_snapshot
                self._restore_json_snapshot(transition_path, transition_snapshot)
            try:
                self._write_operation_receipt(
                    operation=operation,
                    state="failed",
                    source_epoch=self._refresh_attempt_source_epoch or previous_epoch,
                    previous_source_epoch=previous_epoch,
                    target_source_epoch=None,
                )
            except Exception as receipt_exc:
                raise LiveCodeIntelligenceError(
                    "refresh failed and failed lifecycle operation receipt could not be recorded"
                ) from receipt_exc
            raise
        finally:
            self._refresh_attempt_source_epoch = None
        return state, previous_epoch, receipt

    def _state_pointer(
        self,
        state: Mapping[str, Any],
        *,
        label: str,
        expected_status: str = "current",
    ) -> dict[str, Any] | None:
        """Return a compact pointer only for an identity-valid state snapshot."""

        if not self._state_identity_matches_config(state):
            return None
        if state.get("status") != expected_status:
            return None
        source = state.get("source")
        summary = state.get("summary")
        if not isinstance(source, Mapping) or not isinstance(summary, Mapping):
            return None
        return {
            "label": label,
            "status": state["status"],
            "source_epoch": source["source_epoch"],
            "observed_at": state.get("observed_at"),
            "summary": dict(summary),
        }

    def _operation_result(
        self,
        *,
        operation: str,
        state: str,
        source_epoch: str | None,
        receipt: Mapping[str, Any],
        target: Mapping[str, Any] | None = None,
        previous_source_epoch: str | None = None,
        target_source_epoch: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": PROVIDER_OPERATION_SCHEMA,
            "owner": "abyss-stack",
            "operation": operation,
            "state": state,
            "source_epoch": source_epoch,
            "previous_source_epoch": previous_source_epoch,
            "target_source_epoch": target_source_epoch,
            "target": copy.deepcopy(dict(target)) if target is not None else None,
            "receipt": copy.deepcopy(dict(receipt)),
            "claim_limits": [
                "this result describes a bounded source-local lifecycle action",
                "it does not establish deployed service restart, canary, rollback, health, or admission",
                "runtime evidence remains distinct from semantic proof and owner acceptance",
            ],
        }
        if details:
            result.update(copy.deepcopy(dict(details)))
        return result

    def restart(self) -> dict[str, Any]:
        """Rebuild the source observer under the runtime lifecycle lock.

        The bootstrap provider has no resident daemon to signal.  A restart
        therefore means a fresh, complete source scan and parse followed by
        the ordinary candidate/current/last-good promotion rules.  It is a
        real executable stack-local lifecycle action, without claiming that a
        deployed provider process was restarted.
        """

        with self._refresh_lock():
            refreshed, previous_epoch, receipt = self._refresh_with_operation(
                "restart",
                force_rebuild=True,
            )
            source_epoch = self._state_epoch(refreshed)
            operation_state = (
                "current" if refreshed.get("status") == "current" else "degraded"
            )
            target = self._state_pointer(
                refreshed,
                label="current" if operation_state == "current" else "candidate",
                expected_status=operation_state,
            )
            return self._operation_result(
                operation="restart",
                state=operation_state,
                source_epoch=source_epoch,
                previous_source_epoch=previous_epoch,
                target_source_epoch=source_epoch,
                target=target,
                receipt=receipt,
                details={
                    "rebuild": "full",
                    "diagnostics": copy.deepcopy(refreshed.get("degradation", [])),
                },
            )

    def last_good(self) -> dict[str, Any]:
        """Expose the identity-validated rollback snapshot, if one exists."""

        with self._refresh_lock():
            self._prepare_operation_receipt_directory()
            current = _read_json(self.current_path)
            last_good = _read_json(self.last_good_path)
            target = self._state_pointer(last_good, label="last-good")
            current_epoch = self._state_epoch(current)
            target_epoch = self._state_epoch(last_good) if target is not None else None
            operation_state = "available" if target is not None else "unavailable"
            receipt = self._write_operation_receipt(
                operation="last_good",
                state=operation_state,
                source_epoch=current_epoch,
                previous_source_epoch=current_epoch,
                target_source_epoch=target_epoch,
            )
            return self._operation_result(
                operation="last_good",
                state=operation_state,
                source_epoch=current_epoch,
                previous_source_epoch=current_epoch,
                target_source_epoch=target_epoch,
                target=target,
                receipt=receipt,
            )

    def canary(self) -> dict[str, Any]:
        """Parse the current source tree without promoting it to runtime state."""

        with self._refresh_lock():
            self._prepare_operation_receipt_directory()
            operation_path = self.operation_receipts_path / "canary.json"
            previous_operation = _read_json(operation_path)
            current = _read_json(self.current_path)
            current_epoch = self._state_epoch(current)
            self._refresh_attempt_source_epoch = None
            try:
                scanned = self._scan()
                source_epoch = self._source_epoch(scanned)
                self._refresh_attempt_source_epoch = source_epoch
                records = self._run_provider_work_queue(set(scanned), scanned)
                diagnostics = [
                    diagnostic | {"path": path}
                    for path, record in records.items()
                    for diagnostic in record.get("diagnostics", [])
                ]
                operation_state = "passed" if not diagnostics else "failed"
                receipt = self._write_operation_receipt(
                    operation="canary",
                    state=operation_state,
                    source_epoch=source_epoch,
                    previous_source_epoch=current_epoch,
                    target_source_epoch=source_epoch,
                )
                return self._operation_result(
                    operation="canary",
                    state=operation_state,
                    source_epoch=source_epoch,
                    previous_source_epoch=current_epoch,
                    target_source_epoch=source_epoch,
                    receipt=receipt,
                    details={
                        "source": {
                            "root": str(self.config.source_root),
                            "source_file_count": len(scanned),
                            "bytes_scanned": sum(
                                int(item.get("size_bytes", 0))
                                for item in scanned.values()
                            ),
                        },
                        "diagnostics": diagnostics,
                        "promotion": "none",
                    },
                )
            except Exception:
                self._restore_json_snapshot(operation_path, previous_operation)
                try:
                    self._write_operation_receipt(
                        operation="canary",
                        state="failed",
                        source_epoch=self._refresh_attempt_source_epoch or current_epoch,
                        previous_source_epoch=current_epoch,
                        target_source_epoch=None,
                    )
                except Exception as receipt_exc:
                    raise LiveCodeIntelligenceError(
                        "canary failed and failed lifecycle receipt could not be recorded"
                    ) from receipt_exc
                raise
            finally:
                self._refresh_attempt_source_epoch = None

    def rollback(self) -> dict[str, Any]:
        """Restore the identity-valid last-good snapshot as current state."""

        with self._refresh_lock():
            self._prepare_operation_receipt_directory()
            current = _read_json(self.current_path)
            last_good = _read_json(self.last_good_path)
            previous_candidate = _read_json(self.candidate_path)
            previous_epoch = self._state_epoch(current)
            target = self._state_pointer(last_good, label="last-good")
            if target is None:
                operation_path = self.operation_receipts_path / "rollback.json"
                try:
                    self._write_operation_receipt(
                        operation="rollback",
                        state="failed",
                        source_epoch=previous_epoch,
                        previous_source_epoch=previous_epoch,
                        target_source_epoch=None,
                    )
                except Exception as receipt_exc:
                    raise LiveCodeIntelligenceError(
                        "rollback failed and failed lifecycle receipt could not be recorded"
                    ) from receipt_exc
                raise LiveCodeIntelligenceError(
                    "rollback requires an identity-valid last-good state"
                )
            target_epoch = self._state_epoch(last_good)
            if previous_epoch == target_epoch and self._state_pointer(
                current, label="current"
            ) is not None:
                if self.candidate_path.is_symlink():
                    raise LiveCodeIntelligenceError(
                        "rollback candidate state must not be a symlink"
                    )
                operation_path = self.operation_receipts_path / "rollback.json"
                previous_operation = _read_json(operation_path)
                try:
                    receipt = self._write_operation_receipt(
                        operation="rollback",
                        state="already-current",
                        source_epoch=target_epoch,
                        previous_source_epoch=previous_epoch,
                        target_source_epoch=target_epoch,
                    )
                    self.candidate_path.unlink(missing_ok=True)
                except Exception:
                    self._restore_json_snapshot(self.candidate_path, previous_candidate)
                    self._restore_json_snapshot(operation_path, previous_operation)
                    raise
                return self._operation_result(
                    operation="rollback",
                    state="already-current",
                    source_epoch=target_epoch,
                    previous_source_epoch=previous_epoch,
                    target_source_epoch=target_epoch,
                    target=target,
                    receipt=receipt,
                )

            if self.candidate_path.is_symlink():
                raise LiveCodeIntelligenceError(
                    "rollback candidate state must not be a symlink"
                )
            operation_path = self.operation_receipts_path / "rollback.json"
            previous_operation = _read_json(operation_path)
            try:
                _write_json_atomic(self.current_path, last_good)
                # A rollback explicitly abandons a degraded candidate.  The
                # target remains in last-good.json, so this is reversible by a
                # subsequent refresh from the source tree.
                self.candidate_path.unlink(missing_ok=True)
                receipt = self._write_operation_receipt(
                    operation="rollback",
                    state="rolled-back",
                    source_epoch=target_epoch,
                    previous_source_epoch=previous_epoch,
                    target_source_epoch=target_epoch,
                )
            except Exception:
                if current:
                    _write_json_atomic(self.current_path, current)
                else:
                    self.current_path.unlink(missing_ok=True)
                self._restore_json_snapshot(self.candidate_path, previous_candidate)
                self._restore_json_snapshot(operation_path, previous_operation)
                raise
            return self._operation_result(
                operation="rollback",
                state="rolled-back",
                source_epoch=target_epoch,
                previous_source_epoch=previous_epoch,
                target_source_epoch=target_epoch,
                target=self._state_pointer(
                    last_good,
                    label="current",
                ),
                receipt=receipt,
            )

    def status(self, *, _lock_held: bool = False) -> dict[str, Any]:
        if not _lock_held:
            with self._refresh_lock():
                return self.status(_lock_held=True)
        current = _read_json(self.current_path)
        candidate = _read_json(self.candidate_path)
        last_good = _read_json(self.last_good_path)
        candidate_valid = self._state_identity_matches_config(candidate) and (
            candidate.get("status") == "degraded"
        )
        current_valid = self._state_identity_matches_config(current) and (
            current.get("status") == "current"
        )
        last_good_valid = self._state_identity_matches_config(last_good) and (
            last_good.get("status") == "current"
        )
        if candidate_valid:
            state = "degraded"
        elif current_valid:
            state = "current"
        elif last_good_valid:
            state = "last-good"
        else:
            state = "unavailable"

        def pointer(payload: Mapping[str, Any], label: str) -> dict[str, Any] | None:
            if not self._state_identity_matches_config(payload):
                return None
            source = payload.get("source")
            summary = payload.get("summary")
            return {
                "label": label,
                "status": payload.get("status"),
                "source_epoch": source.get("source_epoch")
                if isinstance(source, Mapping)
                else None,
                "observed_at": payload.get("observed_at"),
                "summary": dict(summary) if isinstance(summary, Mapping) else {},
            }

        return {
            "schema_version": STATUS_SCHEMA,
            "state": state,
            "provider": self.config.provider_identity,
            "machine_consumer_abi": copy.deepcopy(MACHINE_CONSUMER_ABI),
            "provider_boundary": {
                "schema_version": PROVIDER_BOUNDARY_SCHEMA,
                "protocol": self.config.provider_protocol,
                "executable": self.config.provider_executable,
                "entrypoint": self.config.provider_entrypoint,
                "operations": list(self.config.provider_operations),
            },
            "config_digest": self.config.config_digest,
            "config_identity": self.config.config_identity,
            "source_root": str(self.config.source_root),
            "machine_binding": self._machine_binding_envelope(),
            "observation_lanes": self._observation_lanes(),
            "provider_workers": self._provider_worker_surface(),
            "lsp_sessions": self._lsp_session_surface(),
            "lifecycle": self._lifecycle_surface(
                last_good_available=last_good_valid
            ),
            "owner_review": self._owner_review_surface(),
            "current": pointer(current, "current"),
            "candidate": pointer(candidate, "candidate"),
            "last_good": pointer(last_good, "last-good"),
            "degradation": (
                list(candidate.get("degradation", []))
                if candidate_valid and isinstance(candidate.get("degradation"), list)
                else []
            ),
            "claim_limits": [
                "LIVE observations are not indexed knowledge or proof",
                "the bootstrap provider does not infer rename or move lineage",
                "installed provider, service health, and owner acceptance require their owners",
            ],
        }

    def discover(self, *, _lock_held: bool = False) -> dict[str, Any]:
        if not _lock_held:
            with self._refresh_lock():
                return self.discover(_lock_held=True)
        persisted_last_good = _read_json(self.last_good_path)
        last_good_available = self._state_identity_matches_config(
            persisted_last_good
        ) and persisted_last_good.get("status") == "current"
        return {
            "schema_version": "abyss-stack-live-code-intelligence-capabilities-v1",
            "status": self.status(_lock_held=True),
            "capabilities": [
                "python_definitions",
                "python_references",
                "python_calls",
                "python_imports",
                "source_epoch",
                "delta_refresh",
                "candidate_current_last_good",
                "bounded_provider_workers",
                "provider_work_queue",
            ],
            "provider": self.config.provider_identity,
            "machine_consumer_abi": copy.deepcopy(MACHINE_CONSUMER_ABI),
            "owner_boundaries": dict(self.config.owner_boundaries),
            "provider_boundary": {
                "schema_version": PROVIDER_BOUNDARY_SCHEMA,
                "protocol": self.config.provider_protocol,
                "executable": self.config.provider_executable,
                "entrypoint": self.config.provider_entrypoint,
                "operations": list(self.config.provider_operations),
            },
            "machine_binding": self._machine_binding_envelope(),
            "observation_lanes": self._observation_lanes(),
            "provider_workers": self._provider_worker_surface(),
            "lsp_sessions": self._lsp_session_surface(),
            "lifecycle": self._lifecycle_surface(
                last_good_available=last_good_available
            ),
            "owner_review": self._owner_review_surface(),
            "observation_envelope_schema": OBSERVATION_ENVELOPE_SCHEMA,
            "config": {
                "digest": self.config.config_digest,
                "state_relative_root": self.config.state_relative_root,
                "state_promotion": self.config.state_promotion,
                "state_fallback": self.config.state_fallback,
            },
        }

    def _query_state(
        self,
        *,
        _lock_held: bool = False,
    ) -> tuple[
        Mapping[str, Any] | None,
        str | None,
        list[dict[str, Any]],
    ]:
        if not _lock_held:
            with self._refresh_lock():
                return self._query_state(_lock_held=True)
        current = _read_json(self.current_path)
        candidate = _read_json(self.candidate_path)
        last_good = _read_json(self.last_good_path)
        state, freshness = self._preferred_state(current, last_good)
        candidate_valid = self._state_identity_matches_config(candidate) and (
            candidate.get("status") == "degraded"
        )
        degradation = (
            copy.deepcopy(candidate.get("degradation", []))
            if candidate_valid and isinstance(candidate.get("degradation"), list)
            else []
        )
        if state is not None and candidate_valid:
            freshness = f"fallback-{freshness}"
        return state, freshness, degradation

    def _query_result(
        self,
        query_kind: str,
        rows: Sequence[dict[str, Any]],
        *,
        freshness: str | None,
        source_epoch: str | None,
        degradation: list[dict[str, Any]] | None = None,
        total_results: int | None = None,
    ) -> dict[str, Any]:
        limit = int(
            self.config.machine_binding_identity["resource_envelope"][
                "max_query_results"
            ]
        )
        retained_rows = list(rows)
        if total_results is None:
            total_results = len(retained_rows)
        truncated = total_results > limit
        returned_rows = retained_rows[:limit]
        return {
            "schema_version": "abyss-stack-live-code-intelligence-query-v1",
            "query": query_kind,
            "status": (
                "truncated"
                if truncated
                else "ok"
                if rows
                else "empty"
                if freshness
                else "degraded"
            ),
            "freshness": freshness or "unknown",
            "source_epoch": source_epoch,
            "provider": self.config.provider_identity,
            "machine_binding": self._machine_binding_envelope(source_epoch),
            "provider_workers": self._provider_worker_surface(),
            "results": returned_rows,
            "result_count": len(returned_rows),
            "total_results": total_results,
            "result_limit": limit,
            "truncated": truncated,
            "degradation": (degradation or []) if freshness else [
                {
                    "target": "live-code-intelligence",
                    "state": "no-current-or-last-good-observation",
                    "fallback": "none",
                }
            ],
        }

    def execute(self, operation: str, *, name: str | None = None) -> dict[str, Any]:
        """Execute one stable provider-boundary operation."""
        if operation == "discover":
            return self.discover()
        if operation == "refresh":
            return self.refresh()
        if operation == "status":
            return self.status()
        if operation == "definitions":
            return self.definitions(name)
        if operation == "references":
            if not name:
                raise LiveCodeIntelligenceError(
                    "references operation requires --name"
                )
            return self.references(name)
        if operation == "restart":
            return self.restart()
        if operation == "last_good":
            return self.last_good()
        if operation == "canary":
            return self.canary()
        if operation == "rollback":
            return self.rollback()
        raise LiveCodeIntelligenceError(
            f"unsupported provider operation: {operation}"
        )

    def definitions(self, name: str | None = None) -> dict[str, Any]:
        state, freshness, degradation = self._query_state()
        if state is None:
            return self._query_result("definitions", [], freshness=None, source_epoch=None)
        source_epoch = str(state.get("source", {}).get("source_epoch") or "")
        limit = int(
            self.config.machine_binding_identity["resource_envelope"][
                "max_query_results"
            ]
        )
        rows = _BoundedQueryRows(limit)
        for record in _state_files(state).values():
            observation = record.get("observation")
            if not isinstance(observation, Mapping):
                continue
            for symbol in observation.get("symbols", []):
                if not isinstance(symbol, Mapping):
                    continue
                if name and name not in {
                    symbol.get("name"),
                    symbol.get("qualified_name"),
                }:
                    continue
                row = {
                    "id": symbol.get("id"),
                    "handle": symbol.get("handle"),
                    "name": symbol.get("name"),
                    "qualified_name": symbol.get("qualified_name"),
                    "kind": symbol.get("kind"),
                    "definition": symbol.get("definition"),
                    "lineage": symbol.get("lineage"),
                }
                rows.add(
                    row,
                    key=(
                        str(row.get("qualified_name")),
                        str(row.get("id")),
                    ),
                )
        return self._query_result(
            "definitions",
            rows.rows,
            freshness=freshness,
            source_epoch=source_epoch,
            degradation=degradation,
            total_results=rows.total_results,
        )

    def references(self, name: str) -> dict[str, Any]:
        state, freshness, degradation = self._query_state()
        if state is None:
            return self._query_result("references", [], freshness=None, source_epoch=None)
        source_epoch = str(state.get("source", {}).get("source_epoch") or "")
        limit = int(
            self.config.machine_binding_identity["resource_envelope"][
                "max_query_results"
            ]
        )
        rows = _BoundedQueryRows(limit)
        for record in _state_files(state).values():
            observation = record.get("observation")
            if not isinstance(observation, Mapping):
                continue
            for occurrence in observation.get("occurrences", []):
                if not isinstance(occurrence, Mapping):
                    continue
                if occurrence.get("name") != name:
                    continue
                row = {
                    "path": record.get("path"),
                    "kind": occurrence.get("kind"),
                    "name": occurrence.get("name"),
                    "role": occurrence.get("role"),
                    "location": occurrence.get("location"),
                    "scope_id": occurrence.get("scope_id"),
                    "confidence": occurrence.get("confidence"),
                }
                rows.add(
                    row,
                    key=(
                        str(row.get("path")),
                        str(row.get("location")),
                    ),
                )
        return self._query_result(
            "references",
            rows.rows,
            freshness=freshness,
            source_epoch=source_epoch,
            degradation=degradation,
            total_results=rows.total_results,
        )


def _provider_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the bounded LIVE Python code-intelligence provider boundary."
    )
    parser.add_argument(
        "operation",
        nargs="?",
        choices=PROVIDER_OPERATIONS,
        help="provider operation (also accepted as --operation)",
    )
    parser.add_argument(
        "--operation",
        dest="operation_option",
        choices=PROVIDER_OPERATIONS,
        help="provider operation",
    )
    parser.add_argument(
        "--config",
        default=str(
            Path(__file__).resolve().parent
            / "config"
            / "python-ast-live-provider.json"
        ),
        help="provider config JSON path",
    )
    parser.add_argument(
        "--machine-evidence",
        help="owner-authenticated content-addressed abyss-machine gate bundle JSON path",
    )
    parser.add_argument("--source-root", required=True, help="working-tree source root")
    parser.add_argument("--state-root", required=True, help="runtime state root")
    parser.add_argument("--name", help="definition or reference name")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one JSON-output provider operation for an operator/runtime caller."""
    parser = _provider_parser()
    args = parser.parse_args(argv)
    operation = args.operation_option or args.operation
    if not operation:
        parser.error("one provider operation is required")
    try:
        config = LiveCodeIntelligenceConfig.from_file(
            args.config,
            source_root=args.source_root,
            state_root=args.state_root,
            machine_evidence_path=args.machine_evidence,
        )
        runtime = LiveCodeIntelligenceRuntime(config)
        result = runtime.execute(operation, name=args.name)
        source_epoch = (
            str(result.get("source_epoch"))
            if isinstance(result, Mapping) and result.get("source_epoch")
            else None
        )
        payload = {
            "schema_version": PROVIDER_BOUNDARY_SCHEMA,
            "status": "ok",
            "operation": operation,
            "provider": config.provider_identity,
            "machine_binding": runtime._machine_binding_envelope(source_epoch),
            "result": result,
        }
        json.dump(payload, sys.stdout, ensure_ascii=True, sort_keys=True, indent=2)
        sys.stdout.write("\n")
        return 0
    except (LiveCodeIntelligenceError, OSError, ValueError, TypeError) as exc:
        error = {
            "schema_version": PROVIDER_BOUNDARY_SCHEMA,
            "status": "error",
            "operation": operation,
            "error": {
                "code": exc.__class__.__name__,
                "message": str(exc),
            },
        }
        json.dump(error, sys.stderr, ensure_ascii=True, sort_keys=True, indent=2)
        sys.stderr.write("\n")
        return 2


__all__ = [
    "CONFIG_SCHEMA",
    "OBSERVATION_SCHEMA",
    "OBSERVATION_ENVELOPE_SCHEMA",
    "PROVIDER_BOUNDARY_SCHEMA",
    "PROVIDER_OPERATION_SCHEMA",
    "MACHINE_BINDING_SCHEMA",
    "MACHINE_EVIDENCE_SCHEMA",
    "MACHINE_GATE_SCHEMA",
    "MACHINE_GATE_RECORD_SCHEMA",
    "MACHINE_GATE_SIGNED_PAYLOAD_SCHEMA",
    "MACHINE_REGISTRY_SCHEMA",
    "MACHINE_GATE_ALGORITHM",
    "MACHINE_GATE_VERIFICATION_METHOD",
    "MACHINE_GATE_TRUST_ANCHOR",
    "MACHINE_CONSUMER_ABI",
    "PROVIDER_WORKER_SCHEMA",
    "PROVIDER_WORK_QUEUE_SCHEMA",
    "PROVIDER_QUEUE_CAPACITY",
    "SECOND_LANGUAGE_PROVIDER_ID",
    "SECOND_LANGUAGE",
    "PROVIDER_LIFECYCLE_SCHEMA",
    "LSP_SESSION_SCHEMA",
    "OWNER_REVIEW_SCHEMA",
    "STATE_SCHEMA",
    "STATUS_SCHEMA",
    "RECEIPT_SCHEMA",
    "machine_evidence_digest",
    "machine_evidence_gate_digest",
    "machine_evidence_bundle_digest",
    "LiveCodeIntelligenceConfig",
    "LiveCodeIntelligenceError",
    "LiveCodeIntelligenceRuntime",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
