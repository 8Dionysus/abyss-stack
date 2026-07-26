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

from abyss_stack_mcp.contracts import RuntimeObservation  # noqa: E402


PIN_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[^\s\\]+)$"
)
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
            if following and not following[0].isspace() and not following.startswith(
                "#"
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
    validate_runtime_lock()

    required = {
        "README.md": (
            "not a gateway",
            "read process",
            "candidate process",
            "execution_authorized=false",
        ),
        "DESIGN.md": (
            "source",
            "package",
            "deploy",
            "process",
            "endpoint",
            "consumer",
        ),
        "docs/BOUNDARIES.md": (
            "does not own",
            "aoa-evals",
            "owner acceptance",
        ),
        "docs/THREAT_MODEL.md": (
            "confused deputy",
            "separate credential",
            "symlink",
        ),
    }
    for relative, needles in required.items():
        text = (SERVICE_ROOT / relative).read_text(encoding="utf-8").lower()
        for needle in needles:
            if needle.lower() not in text:
                raise SystemExit(f"{relative} is missing required boundary: {needle}")

    print(
        "[ok] abyss-stack MCP source contracts, public example, "
        "and hash-locked runtime closure"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
