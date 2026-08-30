#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version


SERVICE_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = SERVICE_ROOT / "src"
RUNTIME_TARGET_BUILDER = SERVICE_ROOT / "scripts" / "build_runtime_targets.py"
sys.path.insert(0, str(SRC_ROOT))
SHARED_ROOT = SERVICE_ROOT.parent / "_shared"
sys.path.insert(0, str(SHARED_ROOT))

from runtime_config import load_catalog, raw_config  # noqa: E402
from validate_systemd_projection import validate_systemd_projection  # noqa: E402

from abyss_stack_mcp.audit import PolicyAuditJournal  # noqa: E402
from abyss_stack_mcp.canary import (  # noqa: E402
    CanaryReceipt,
    CanaryResultArtifact,
)
from abyss_stack_mcp.contracts import RuntimeObservation  # noqa: E402
from abyss_stack_mcp.observation import RuntimeTargetCatalog  # noqa: E402
from abyss_stack_mcp.organ_access import (  # noqa: E402
    CANDIDATE_TOOL_BINDINGS,
    INTERNAL_EFFECT_TOOL_BINDINGS,
    READ_TOOL_BINDINGS,
    load_organ_access_manifest,
)
from abyss_stack_mcp.policy import StackPolicySeam  # noqa: E402
from abyss_stack_mcp.proof_projection import (  # noqa: E402
    CentralProofProjectionError,
)
from abyss_stack_mcp.proof_packet import ProofPacketBindingError  # noqa: E402
from abyss_stack_mcp.rollback_candidate import RollbackCandidateError  # noqa: E402
from abyss_stack_mcp.rollback_projection import RollbackProjectionError  # noqa: E402


PIN_RE = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s\\]+)$")
DIRECT_URL_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s+@\s+(?P<url>https://[^\s\\]+)$"
)
LOCK_PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s\\]+)\s+\\$"
)
LOCK_DIRECT_URL_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)\s+@\s+"
    r"(?P<url>https://[^\s\\]+)\s+\\$"
)
HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}$")


def approved_aoa_sdk_artifact() -> dict[str, str]:
    """Read the approved SDK artifact from the central runtime catalog."""

    artifacts = raw_config().get("deployment", {}).get("approved_artifacts", {})
    artifact = artifacts.get("aoa_sdk") if isinstance(artifacts, dict) else None
    if not isinstance(artifact, dict):
        raise SystemExit("runtime catalog lacks the approved aoa-sdk artifact")
    required = ("distribution", "version", "wheel_url", "sha256")
    if any(not isinstance(artifact.get(key), str) or not artifact[key] for key in required):
        raise SystemExit("approved aoa-sdk artifact is incomplete")
    if artifact["distribution"] != "aoa-sdk" or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", artifact["version"]
    ) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
        raise SystemExit("approved aoa-sdk artifact is malformed")
    return {key: str(artifact[key]) for key in required}


def validate_runtime_target_projection(targets: RuntimeTargetCatalog) -> None:
    """Ensure the canary target projection has one current runtime authority."""
    catalog = load_catalog()
    config = raw_config()
    paths = config["paths"]
    deployment = config["deployment"]
    admitted_service_ids = {
        item["service_id"] for item in deployment["client_read_contours"]
    }
    if len(targets.targets) != len(catalog.services):
        raise SystemExit(
            "runtime target catalog and declarative MCP catalog have different sizes"
        )
    seen_services: set[str] = set()
    for target in targets.targets:
        if target.service_id in seen_services:
            raise SystemExit(f"runtime target service is duplicated: {target.service_id}")
        seen_services.add(target.service_id)
        try:
            service = catalog.service(target.service_id)
            contour = service.contour(target.policy_family)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        if target.organ_id != service.organ_id:
            raise SystemExit(
                f"runtime target organ drifted for {target.service_id}: "
                f"{target.organ_id} != {service.organ_id}"
            )
        if target.registry_organ_id != service.registry_organ_id:
            raise SystemExit(
                f"runtime target registry organ drifted for {target.service_id}: "
                f"{target.registry_organ_id} != {service.registry_organ_id}"
            )
        expected_endpoint = (
            f"http://{catalog.transport.default_host}:{contour.port}"
            f"{catalog.transport.streamable_http_path}"
        )
        expected_unit = service.read_unit_name(target.organ_id)
        if target.endpoint_ref != expected_endpoint:
            raise SystemExit(
                f"runtime target endpoint drifted for {target.service_id}: "
                f"{target.endpoint_ref} != {expected_endpoint}"
            )
        if target.unit_name != expected_unit:
            raise SystemExit(
                f"runtime target unit drifted for {target.service_id}: "
                f"{target.unit_name} != {expected_unit}"
            )
        if target.protocol_versions != (catalog.transport.protocol_version,):
            raise SystemExit(
                f"runtime target protocol drifted for {target.service_id}"
            )
        expected_executable = (
            f"${{{paths['workspace_env_var']}}}/"
            f"{paths['stack_codex_executable_relative_to_workspace_template'].format(instance=service.read_unit_instance)}"
            if service.runtime_executable_mode == "workspace_codex"
            else f"${{{paths['stack_root_env_var']}}}/"
            f"{deployment['runtime_python_relative_template'].format(service_id=service.service_id)}"
        )
        if target.executable_ref != expected_executable:
            raise SystemExit(
                f"runtime target executable drifted for {target.service_id}: "
                f"{target.executable_ref} != {expected_executable}"
            )
        expected_cohort = (
            "admitted-read"
            if target.service_id in admitted_service_ids
            else "package-only-shadow"
        )
        if target.rollout_cohort != expected_cohort:
            raise SystemExit(
                f"runtime target rollout cohort drifted for {target.service_id}: "
                f"{target.rollout_cohort} != {expected_cohort}"
            )
    if seen_services != set(catalog.services):
        raise SystemExit("runtime target catalog lost a declarative MCP service")


def validate_generated_runtime_targets() -> None:
    if not RUNTIME_TARGET_BUILDER.is_file():
        raise SystemExit("runtime target generator is unavailable")
    completed = subprocess.run(
        [sys.executable, str(RUNTIME_TARGET_BUILDER), "--check"],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr).strip()
        raise SystemExit(detail or "generated runtime target projection is stale")


def validate_systemd_projection_gate() -> None:
    try:
        validate_systemd_projection(raw_config())
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def normalized_package(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def validate_runtime_lock() -> None:
    artifact = approved_aoa_sdk_artifact()
    aoa_sdk_wheel_url = artifact["wheel_url"]
    aoa_sdk_wheel_hash = f"--hash=sha256:{artifact['sha256']}"
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
        direct_match = DIRECT_URL_RE.fullmatch(line)
        if match is None and direct_match is None:
            raise SystemExit(
                "requirements.constraints must contain only exact pins or the "
                "approved aoa-sdk release wheel; "
                f"line {line_number} is invalid"
            )
        selected = match or direct_match
        assert selected is not None
        name = normalized_package(selected.group("name"))
        if name in constraints:
            raise SystemExit(f"duplicate constraint pin: {name}")
        if direct_match is not None:
            url = direct_match.group("url")
            if name != "aoa-sdk" or url != aoa_sdk_wheel_url:
                raise SystemExit("only the approved aoa-sdk release wheel is allowed")
            constraints[name] = url
        else:
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
        direct_match = LOCK_DIRECT_URL_RE.fullmatch(raw_line)
        if match is None and direct_match is None:
            raise SystemExit(
                "requirements.lock must contain only exact, continued pins or "
                "the approved aoa-sdk release wheel; "
                f"line {index + 1} is invalid"
            )
        selected = match or direct_match
        assert selected is not None
        name = normalized_package(selected.group("name"))
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
        if direct_match is not None:
            url = direct_match.group("url")
            if (
                name != "aoa-sdk"
                or url != aoa_sdk_wheel_url
                or hashes != [aoa_sdk_wheel_hash]
            ):
                raise SystemExit("aoa-sdk lock must bind the approved wheel and digest")
            locked[name] = url
        else:
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
    flexible_mcp_requirement = Requirement(
        load_catalog().transport.sdk_requirement
    )
    declared = [
        *pyproject["build-system"]["requires"],
        *pyproject["project"]["dependencies"],
    ]
    for requirement in declared:
        match = PIN_RE.fullmatch(requirement)
        direct_match = DIRECT_URL_RE.fullmatch(requirement)
        if match is None and direct_match is None:
            try:
                flexible = Requirement(requirement)
            except (TypeError, ValueError) as exc:
                raise SystemExit(
                    f"pyproject dependency is not a valid requirement: {requirement}"
                ) from exc
            name = normalized_package(flexible.name)
            expected_name = normalized_package(flexible_mcp_requirement.name)
            if (
                name != expected_name
                or flexible.specifier != flexible_mcp_requirement.specifier
                or name not in constraints
                or Version(constraints[name]) not in flexible.specifier
            ):
                raise SystemExit(
                    "only the central MCP major-line requirement may be flexible: "
                    f"{requirement}"
                )
            continue
        selected = match or direct_match
        assert selected is not None
        name = normalized_package(selected.group("name"))
        value = (
            direct_match.group("url")
            if direct_match is not None
            else match.group("version")
        )
        if direct_match is not None and (
            name != "aoa-sdk" or value != aoa_sdk_wheel_url
        ):
            raise SystemExit("pyproject aoa-sdk dependency is not the approved wheel")
        if constraints.get(name) != value:
            raise SystemExit(
                f"pyproject dependency {requirement} is absent from exact closure"
            )


def main() -> int:
    catalog = load_catalog()
    internal_effect_port = catalog.service("abyss-stack-mcp").contour(
        "internal_effect"
    ).port
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
    organ_access = load_organ_access_manifest(SERVICE_ROOT / "organ-access.v1.json")
    declared_tools = {
        item.mcp_name
        for capability in organ_access.capabilities
        for item in capability.primitives
    }
    expected_tools = set(READ_TOOL_BINDINGS.values()) | set(
        CANDIDATE_TOOL_BINDINGS.values()
    ) | set(INTERNAL_EFFECT_TOOL_BINDINGS.values())
    if declared_tools != expected_tools:
        raise SystemExit("stack organ capability tools drifted from owner policy seams")
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
        pyproject["project"]["scripts"].get("abyss-stack-mcp-effect")
        != "abyss_stack_mcp.effect:main"
        or pyproject["project"]["scripts"].get(
            "abyss-stack-mcp-effect-server"
        )
        != "abyss_stack_mcp.effect_server:main"
    ):
        raise SystemExit("exact internal-effect entry points are unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-observe")
        != "abyss_stack_mcp.observation:main"
    ):
        raise SystemExit("runtime observation producer entry point is unavailable")
    if (
        pyproject["project"]["scripts"].get("abyss-stack-mcp-system-status")
        != "abyss_stack_mcp.system_status:main"
    ):
        raise SystemExit("bounded MCP system status entry point is unavailable")
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
    validate_generated_runtime_targets()
    validate_systemd_projection_gate()
    validate_runtime_target_projection(targets)
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
            "runtime-topology-read",
            "stack-access-plan",
            "read process",
            "candidate process",
            "internal-effect process",
            "mandatory second restart",
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
            "pre-effect, denial, recovery, and success receipts",
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
            f"port-`{internal_effect_port}` internal-effect process",
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
