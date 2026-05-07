#!/usr/bin/env python3
"""Validate nested AGENTS.md guidance for abyss-stack.

This validator-first spine protects local AGENTS.md surfaces that already exist.
It also reports high-risk directories that are likely to need future local
guidance, without making those future files blocking before they land.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_NAME = 'abyss-stack'

REQUIRED_AGENTS_DOCS: dict[str, tuple[str, ...]] = {
    'compose/AGENTS.md': (
        'compose-time runtime shape',
        'modules/*.yml',
        'profiles/*.txt',
        'presets/*.txt',
        '127.0.0.1',
        'python scripts/validate_stack.py',
    ),
    'config-templates/AGENTS.md': (
        'public-safe runtime config templates',
        'Configs/',
        'Services/',
        'aoa-bootstrap-configs',
        'do not place live secrets in templates',
    ),
    'env/AGENTS.md': (
        'public-safe env examples',
        'Secrets/Configs',
        '.example',
        'CHANGE_ME',
        'python scripts/validate_stack.py',
    ),
    'scripts/AGENTS.md': (
        'runtime bridge, bootstrap helpers',
        'scripts/validate_stack.py',
        'AOA_STACK_ROOT=/srv/AbyssOS/abyss-stack',
        'aoa-host-facts',
        'aoa-diagnose',
        'python -m py_compile',
    ),
    'systemd/user/AGENTS.md': (
        'rootless `systemd --user` unit skeletons',
        'podman-compose-abyss.service',
        'systemd-analyze --user verify',
        'do not point units at the source checkout',
    ),
    'schemas/AGENTS.md': (
        'runtime-owned machine-readable contracts',
        'schema changes are contract changes',
        '$schema',
        'diagnostic_surface_catalog.min.json',
        'python scripts/validate_stack.py',
    ),
    'generated/AGENTS.md': (
        'Generated artifacts are lower authority than their sources',
        'do not hand-edit generated JSON',
        'diagnostic_surface_catalog.min.json',
        'python scripts/build_diagnostic_surface_catalog.py --check',
    ),
    'mechanics/AGENTS.md': (
        'runtime mechanics tree',
        'mechanics/README.md',
        'Package law',
        'python scripts/validate_nested_agents.py',
    ),
    'mechanics/runtime-lifecycle/AGENTS.md': (
        'runtime-lifecycle',
        'Runtime activation remains an explicit operator action',
        'docs/DEPLOYMENT.md',
        'systemd-analyze --user verify',
    ),
    'mechanics/config-projection/AGENTS.md': (
        'config-projection',
        'public-safe templates',
        'aoa-bootstrap-configs',
        'Do not commit live secrets',
    ),
    'mechanics/machine-fit/AGENTS.md': (
        'machine-fit',
        'future read-only machine bridge',
        'aoa-host-facts',
        'Do not mutate /srv/abyss-machine',
    ),
    'mechanics/inference-pilots/AGENTS.md': (
        'inference-pilots',
        'bounded local inference pilots',
        'aoa-llamacpp-pilot',
        'mechanics/agon-runtime',
    ),
    'mechanics/agon-runtime/AGENTS.md': (
        'agon-runtime',
        'dry-run kernel',
        'PROVENANCE.md',
        'validate_agon_mechanical_trial_runs.py',
    ),
    'mechanics/agon-runtime/legacy/AGENTS.md': (
        'Agon runtime surfaces',
        'legacy/raw',
        'generated registries',
        'build_agon_mechanical_trial_run_registry.py --check',
    ),
    'mechanics/experience-runtime/AGENTS.md': (
        'experience-runtime',
        'experience seed contract',
        'PROVENANCE.md',
        'test_experience_wave',
    ),
    'mechanics/experience-runtime/legacy/AGENTS.md': (
        'experience runtime seed surfaces',
        '_v1',
        'legacy/artifacts/tests',
        'python -m pytest',
    ),
    'mechanics/federation-seams/AGENTS.md': (
        'federation-seams',
        'runtime consumption of sibling owner surfaces',
        'aoa-sync-federation-surfaces',
        'mirrored owner surfaces',
    ),
    'mechanics/governed-execution/AGENTS.md': (
        'governed-execution',
        'governed local-worker execution',
        'tests.test_governed_execution',
        'Do not turn advisory execution into autonomous authority',
    ),
    'mechanics/diagnostic-spine/AGENTS.md': (
        'diagnostic-spine',
        'doctor readiness',
        'build_diagnostic_surface_catalog.py --check',
        'handoff candidates',
    ),
    'mechanics/runtime-repair/AGENTS.md': (
        'runtime-repair',
        'degradation receipts',
        'repair-safe closeout',
        'Do not perform repair',
    ),
    'tests/AGENTS.md': (
        'runtime validation gate',
        'deterministic and public-safe',
        'no live host state',
        'python -m pytest',
    ),
}
ADVISORY_AGENT_DIRS: tuple[str, ...] = ('.agents/skills', 'config', 'docs', 'examples', 'manifests/recurrence', 'quests')
HEADING_PREFIXES = ("# AGENTS.md", "# AGENTS")
IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}


@dataclass(frozen=True)
class ValidationResult:
    issues: tuple[str, ...]
    warnings: tuple[str, ...]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _has_agents_heading(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(prefix) for prefix in HEADING_PREFIXES)


def _relative(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_ignored(path: Path, repo_root: Path) -> bool:
    try:
        parts = path.relative_to(repo_root).parts
    except ValueError:
        return False
    return any(part in IGNORED_DIRS for part in parts)


def discover_nested_agents(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for path in repo_root.rglob("AGENTS.md"):
        if _is_ignored(path, repo_root):
            continue
        rel = _relative(path, repo_root)
        if rel != "AGENTS.md":
            found.add(rel)
    return found


def validate(
    repo_root: Path = REPO_ROOT,
    *,
    strict_advisory: bool = False,
    fail_on_untracked: bool = False,
) -> ValidationResult:
    repo_root = repo_root.resolve()
    issues: list[str] = []
    warnings: list[str] = []

    root_agents = repo_root / "AGENTS.md"
    if not root_agents.is_file():
        issues.append("AGENTS.md: root guidance file is missing")
    else:
        root_text = root_agents.read_text(encoding="utf-8")
        if not _has_agents_heading(root_text):
            issues.append("AGENTS.md: missing AGENTS heading")

    for rel_path, snippets in REQUIRED_AGENTS_DOCS.items():
        path = repo_root / rel_path
        if not path.is_file():
            issues.append(f"{rel_path}: required nested AGENTS.md is missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_agents_heading(text):
            issues.append(f"{rel_path}: missing AGENTS heading")
        normalized = _normalize(text)
        for snippet in snippets:
            if _normalize(snippet) not in normalized:
                issues.append(f"{rel_path}: missing required snippet {snippet!r}")

    required = set(REQUIRED_AGENTS_DOCS)
    actual = discover_nested_agents(repo_root)
    untracked = sorted(actual - required)
    if untracked:
        message = "untracked nested AGENTS.md not yet in validator map: " + ", ".join(untracked)
        warnings.append(message)
        if fail_on_untracked:
            issues.append(message)

    for rel_dir in ADVISORY_AGENT_DIRS:
        dir_path = repo_root / rel_dir
        agent_path = f"{rel_dir.rstrip('/')}/AGENTS.md"
        if not dir_path.is_dir():
            continue
        if agent_path in required or agent_path in actual:
            continue
        warnings.append(f"{rel_dir}: high-risk directory has no local AGENTS.md yet")

    if strict_advisory:
        issues.extend(warnings)

    return ValidationResult(tuple(issues), tuple(warnings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--strict-advisory", action="store_true")
    parser.add_argument("--fail-on-untracked", action="store_true")
    args = parser.parse_args(argv)

    result = validate(
        args.repo_root,
        strict_advisory=args.strict_advisory,
        fail_on_untracked=args.fail_on_untracked,
    )
    if result.issues:
        print(f"Nested AGENTS validation failed for {REPOSITORY_NAME}.")
        for issue in result.issues:
            print(f"- {issue}")
        return 1
    print(
        f"Nested AGENTS validation passed for {REPOSITORY_NAME}: "
        f"{len(REQUIRED_AGENTS_DOCS)} required nested document(s)."
    )
    for warning in result.warnings:
        print(f"[advisory] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
