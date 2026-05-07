from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError("could not find abyss-stack repository root")


ROOT = find_repo_root(Path(__file__).resolve())
ARTIFACTS = ROOT / "mechanics" / "experience-runtime" / "legacy" / "artifacts"
SCHEMAS = ARTIFACTS / "schemas"
EXAMPLES = ARTIFACTS / "examples"
WAVE2_PREFIXES = (
    "canary_worker_",
    "deployment_runtime_",
    "release_lifecycle_",
    "rollback_job_",
    "watchtower_job_",
)


def wave2_pairs() -> tuple[list[tuple[Path, Path]], list[str]]:
    pairs: list[tuple[Path, Path]] = []
    missing_pairs: list[str] = []
    for example_path in sorted(EXAMPLES.glob("*.example.json")):
        stem = example_path.name.removesuffix(".example.json")
        if stem.endswith("_v1"):
            continue
        if not stem.startswith(WAVE2_PREFIXES):
            continue
        schema_path = SCHEMAS / f"{stem}_v1.json"
        if schema_path.exists():
            pairs.append((schema_path, example_path))
        else:
            missing_pairs.append(f"{example_path.relative_to(ROOT)} -> {schema_path.relative_to(ROOT)}")
    return pairs, missing_pairs


def test_experience_wave2_examples_match_schemas() -> None:
    pairs, missing_pairs = wave2_pairs()
    assert not missing_pairs, "missing wave2 schema pair(s): " + ", ".join(missing_pairs)
    assert pairs
    for schema_path, example_path in pairs:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(example), key=lambda error: list(error.path))
        assert not errors, f"{example_path.name}: {errors[0].message if errors else ''}"
