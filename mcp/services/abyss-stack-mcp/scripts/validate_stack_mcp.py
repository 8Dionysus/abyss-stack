#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from abyss_stack_mcp.audit import PolicyAuditJournal  # noqa: E402
from abyss_stack_mcp.canary import (  # noqa: E402
    CanaryReceipt,
    CanaryResultArtifact,
)
from abyss_stack_mcp.contracts import RuntimeObservation  # noqa: E402
from abyss_stack_mcp.observation import RuntimeTargetCatalog  # noqa: E402
from abyss_stack_mcp.policy import StackPolicySeam  # noqa: E402
from abyss_stack_mcp.proof_projection import (  # noqa: E402
    CentralProofProjectionError,
)
from abyss_stack_mcp.proof_packet import ProofPacketBindingError  # noqa: E402
from abyss_stack_mcp.rollback_candidate import RollbackCandidateError  # noqa: E402
from abyss_stack_mcp.rollback_projection import RollbackProjectionError  # noqa: E402


PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s\\]+)$")
LOCK_PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s\\]+)\s+\\$"
)
HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}$")


def normalized_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def validate_runtime_lock() -> None:
    pyproject_path = SERVICE_ROOT / "pyproject.toml"
    constraints_path = SERVICE_ROOT / "requirements.constraints"
    lock_path = SERVICE_ROOT / "requirements.lock"
    for path in (pyproject_path, constraints_path, lock_path):
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"{path.name} must be a regular non-symlink file")

    constraints: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        constraints_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_RE.fullmatch(line)
        if match is None:
            raise SystemExit(
                "requirements.constraints must contain only exact pins; "
                f"line {line_number} is invalid"
            )
        name = normalized_package(match.group("name"))
        if name in constraints:
            raise SystemExit(f"duplicate constraint pin: {name}")
        constraints[name] = match.group("version")

    lock_text = lock_path.read_text(encoding="utf-8")
    if any(prefix in lock_text for prefix in ("/home/", "/srv/", "/tmp/")):
        raise SystemExit("requirements.lock contains a machine-local absolute path")
    lock_lines = lock_text.splitlines()
    locked: dict[str, str] = {}
    for index, raw_line in enumerate(lock_lines):
        if not raw_line or raw_line[0].isspace() or raw_line.startswith("#"):
            continue
        match = LOCK_PIN_RE.fullmatch(raw_line)
        if match is None:
            raise SystemExit(
                "requirements.lock must contain only exact, continued pins; "
                f"line {index + 1} is invalid"
            )
        name = normalized_package(match.group("name"))
        if name in locked:
            raise SystemExit(f"duplicate lock pin: {name}")
        hashes: list[str] = []
        for following in lock_lines[index + 1 :]:
            if (
                following
                and not following[0].isspace()
                and not following.startswith("#")
            ):
                break
            stripped = following.strip().removesuffix("\\").strip()
            if stripped.startswith("--hash="):
                hashes.append(stripped)
        if not hashes or any(HASH_RE.fullmatch(value) is None for value in hashes):
            raise SystemExit(f"lock pin {name} is missing a valid sha256 hash")
        locked[name] = match.group("version")

    if locked != constraints:
        missing = sorted(set(constraints) - set(locked))
        extra = sorted(set(locked) - set(constraints))
        drifted = sorted(
            name
            for name in set(locked) & set(constraints)
            if locked[name] != constraints[name]
        )
        raise SystemExit(
            "requirements.lock does not match requirements.constraints: "
            f"missing={missing}, extra={extra}, drifted={drifted}"
        )

    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    declared = [
        *pyproject["build-system"]["requires"],
        *pyproject["project"]["dependencies"],
    ]
    for requirement in declared:
        match = PIN_RE.fullmatch(requirement)
        if match is None:
            raise SystemExit(f"pyproject dependency must be exact: {requirement}")
        name = normalized_package(match.group("name"))
        version = match.group("version")
        if constraints.get(name) != version:
            raise SystemExit(
                f"pyproject dependency {name}=={version} is absent from exact closure"
            )


def main() -> int:
    generator = SERVICE_ROOT / "scripts" / "generate_stack_mcp_contracts.py"
    result = subprocess.run(
        [sys.executable, str(generator), "--check"],
        cwd=SERVICE_ROOT,
        check=False,
    )
    if result.returncode:
        return result.returncode

    example = SERVICE_ROOT / "examples" / "runtime-observation.public.example.json"
    RuntimeObservation.model_validate(json.loads(example.read_text(encoding="utf-8")))
    if StackPolicySeam.__module__ != "abyss_stack_mcp.policy":
        raise SystemExit("protocol-independent stack policy seam is unavailable")
    if PolicyAuditJournal.__module__ != "abyss_stack_mcp.audit":
        raise SystemExit("persistent stack policy audit journal is unavailable")
    validate_runtime_lock()
    pyproject = tomllib.loads(
        (SERVICE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-audit")
        != "abyss_stack_mcp.audit:main"
    ):
        raise SystemExit("policy audit summary entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-canary")
        != "abyss_stack_mcp.canary:main"
    ):
        raise SystemExit("authenticated read canary entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-observe")
        != "abyss_stack_mcp.observation:main"
    ):
        raise SystemExit("runtime observation producer entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-overlay-compose")
        != "abyss_stack_mcp.overlay:main"
    ):
        raise SystemExit("runtime evidence overlay composer entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-proof-project")
        != "abyss_stack_mcp.proof_projection:main"
        or CentralProofProjectionError.__module__
        != "abyss_stack_mcp.proof_projection"
    ):
        raise SystemExit("central proof projection entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get(
            "abyss-stack-mcp-proof-packet-bind-consumer"
        )
        != "abyss_stack_mcp.proof_packet:main"
        or ProofPacketBindingError.__module__ != "abyss_stack_mcp.proof_packet"
    ):
        raise SystemExit("proof packet consumer-binding entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get(
            "abyss-stack-mcp-orchestration"
        )
        != "abyss_stack_mcp.orchestration:main"
    ):
        raise SystemExit("cross-organ host entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get(
            "abyss-stack-mcp-rollback-candidate"
        )
        != "abyss_stack_mcp.rollback_candidate:main"
        or RollbackCandidateError.__module__
        != "abyss_stack_mcp.rollback_candidate"
    ):
        raise SystemExit("rollback candidate entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get(
            "abyss-stack-mcp-rollback-project"
        )
        != "abyss_stack_mcp.rollback_projection:main"
        or RollbackProjectionError.__module__
        != "abyss_stack_mcp.rollback_projection"
    ):
        raise SystemExit("rollback projection entry point is unavailable")
    targets_path = SERVICE_ROOT / "src" / "abyss_stack_mcp" / "runtime-targets.v1.json"
    targets = RuntimeTargetCatalog.model_validate(
        json.loads(targets_path.read_text(encoding="utf-8"))
    )
    if len(targets.targets) != 15:
        raise SystemExit("runtime observation target catalog must name 15 contours")
    reviewed_canaries = {
        target.organ_id
        for target in targets.targets
        if target.canary_contract is not None
    }
    if reviewed_canaries != {target.organ_id for target in targets.targets}:
        raise SystemExit(
            "every migration-wave runtime target must have a reviewed canary contract"
        )
    if CanaryReceipt.__module__ != "abyss_stack_mcp.canary":
        raise SystemExit("authenticated read canary receipt is unavailable")
    if CanaryResultArtifact.__module__ != "abyss_stack_mcp.canary":
        raise SystemExit("private canary result artifact is unavailable")
    audit_schema = json.loads(
        (SERVICE_ROOT / "schemas" / "policy-audit-summary.schema.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        audit_schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or "claim_limit" not in audit_schema.get("properties", {})
    ):
        raise SystemExit("policy audit summary schema is unavailable")

    required = {
        "README.md": (
            "not a gateway",
            "read process",
            "candidate process",
            "execution_authorized=false",
            "policy seam",
            "hash chain",
            "legacy process",
            "authenticated read canary",
            "host-visible orchestration",
        ),
        "DESIGN.md": (
            "source",
            "package",
            "deploy",
            "process",
            "endpoint",
            "consumer",
            "journal continuity",
            "production observation",
            "cross-organ",
        ),
        "docs/BOUNDARIES.md": (
            "does not own",
            "aoa-evals",
            "owner acceptance",
            "audit summary",
            "shared-bearer",
            "host persistence",
        ),
        "docs/CODEX_CONSUMER_HANDOFF.md": (
            "consumer-schema evidence",
            "consumer-zero",
            "fresh Codex process",
            "execution_authorized=false",
            "must not",
        ),
        "docs/THREAT_MODEL.md": (
            "confused deputy",
            "separate credential",
            "symlink",
            "untrusted data",
            "tamper-evident",
            "observation producer",
            "host receipt",
        ),
    }
    for relative, needles in required.items():
        text = (SERVICE_ROOT / relative).read_text(encoding="utf-8").lower()
        for needle in needles:
            if needle.lower() not in text:
                raise SystemExit(f"{relative} is missing required boundary: {needle}")

    print(
        "[ok] abyss-stack MCP source, policy, public example, "
        "and hash-locked runtime closure"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
