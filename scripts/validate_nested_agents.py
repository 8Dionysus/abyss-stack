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
    'docs/AGENTS.md': (
        'repo-wide operator and source-checkout documentation',
        'docs/README.md',
        'docs/routes/START_HERE_ROUTE_CONTRACT.md',
        'routes/',
        'runtime/',
        'install/',
        'operations/',
        'profiles/',
        'governance/',
        'validation/',
        'testing/',
        'Mechanic-owned runtime doctrine',
        'docs/decisions',
        'docs/validation',
        'docs/testing',
        'python scripts/validate_decision_records.py',
        'python scripts/validate_nested_agents.py',
    ),
    'docs/validation/AGENTS.md': (
        'validation topology',
        'command authority',
        'validation_lanes.json',
        'inventories descriptive',
        'python scripts/ci_gate.py --mode source-fast',
    ),
    'docs/testing/AGENTS.md': (
        'test topology',
        'test_inventory.json',
        'docs/validation/validation_lanes.json',
        'Keep legacy paths out of default pytest discovery',
        'python scripts/ci_gate.py --mode tests',
    ),
    'docs/decisions/AGENTS.md': (
        'decision records',
        'Decision Review Gate',
        'TEMPLATE.md',
        'current source surfaces define what',
        'python scripts/validate_decision_records.py',
    ),
    '.agents/skills/AGENTS.md': (
        'transitional repo-local projection of shared skills',
        'aoa-skills',
        'Canonical',
        'root `skills/`',
        'python scripts/validate_nested_agents.py',
    ),
    '.agents/AGENTS.md': (
        'transitional repo-local agent projections',
        '.agents/README.md',
        'canonical skill law',
        'stack-owned canonical packages under `skills/`',
        'python scripts/validate_nested_agents.py',
    ),
    'scripts/AGENTS.md': (
        'runtime bridge, bootstrap helpers',
        'scripts/README.md',
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
    'systemd/system/AGENTS.md': (
        'privileged system unit skeletons',
        'managed-units.txt',
        '--system-units',
        'must not start, stop, restart, enable, disable, or mask system services',
    ),
    'systemd/AGENTS.md': (
        'source-managed systemd route surfaces',
        'systemd/user/',
        'systemd/system/',
        'mechanics/runtime-lifecycle',
        'Do not point units at the source checkout',
    ),
    '.github/AGENTS.md': (
        'GitHub platform surface',
        '.github/GITHUB_SURFACE.md',
        'GitHub automation public-safe',
        'Repo Validation',
        'root route card',
    ),
    'mcp/AGENTS.md': (
        'Model Context Protocol',
        'access planes',
        'mcp/protocol-lab/',
        'mcp/services/aoa-memo-mcp/',
        'mcp/services/aoa-decisions-mcp/',
        'mcp/services/aoa-evals-mcp/',
        'mcp/services/aoa-kag-mcp/',
        'mcp/services/aoa-stats-mcp/',
        'mcp/services/abyss-machine-mcp/',
        'mcp/services/aoa-session-memory-mcp/',
        'mcp/services/tos-corpus-mcp/',
        'mcp/services/aoa-4pda-connector-mcp/',
        'mcp/services/aoa-telegram-connector-mcp/',
        'mcp/services/aoa-discord-connector-mcp/',
        'mcp/services/aoa-course-connector-mcp/',
        'mcp/services/aoa-stackoverflow-connector-mcp/',
        'mcp/services/aoa-xda-connector-mcp/',
        'mcp/services/abyss-stack-mcp/',
        'python mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py',
        'python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py',
        'python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py',
        'python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py',
        'python mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py',
        'python mcp/services/aoa-stats-mcp/scripts/validate_stats_mcp.py',
        'python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py',
        'python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py',
        'python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py',
        'python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py',
        'python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py',
        'python mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py',
        'python mcp/services/aoa-course-connector-mcp/scripts/validate_course_connector_mcp.py',
        'python mcp/services/aoa-stackoverflow-connector-mcp/scripts/validate_stackoverflow_connector_mcp.py',
        'python mcp/services/aoa-xda-connector-mcp/scripts/validate_xda_connector_mcp.py',
        'python mcp/protocol-lab/scripts/validate_protocol_lab.py',
    ),
    'mcp/protocol-lab/AGENTS.md': (
        'fail-closed compatibility',
        'Production remains',
        'aoa-kag',
        'Tasks',
        'python mcp/protocol-lab/scripts/build_protocol_lab_status.py --check',
        'python mcp/protocol-lab/scripts/validate_protocol_lab.py',
        'python -m pytest -q mcp/protocol-lab/tests',
    ),
    'mcp/services/AGENTS.md': (
        'service-package district',
        'Model Context Protocol',
        'aoa-memo-mcp',
        'aoa-decisions-mcp',
        'aoa-evals-mcp',
        'aoa-kag-mcp',
        'aoa-stats-mcp',
        'abyss-machine-mcp',
        'aoa-session-memory-mcp',
        'tos-corpus-mcp',
        'aoa-4pda-connector-mcp',
        'aoa-telegram-connector-mcp',
        'aoa-discord-connector-mcp',
        'aoa-course-connector-mcp',
        'aoa-stackoverflow-connector-mcp',
        'aoa-xda-connector-mcp',
        'abyss-stack-mcp',
        'python mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py',
        'python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py',
        'python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py',
        'python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py',
        'python mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py',
        'python mcp/services/aoa-stats-mcp/scripts/validate_stats_mcp.py',
        'python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py',
        'python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py',
        'python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py',
        'python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py',
        'python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py',
        'python mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py',
        'python mcp/services/aoa-course-connector-mcp/scripts/validate_course_connector_mcp.py',
        'python mcp/services/aoa-stackoverflow-connector-mcp/scripts/validate_stackoverflow_connector_mcp.py',
        'python mcp/services/aoa-xda-connector-mcp/scripts/validate_xda_connector_mcp.py',
    ),
    'mcp/services/aoa-4pda-connector-mcp/AGENTS.md': (
        'read-only MCP access plane',
        'aoa-4pda-connector',
        'agent_answer',
        'network_touched=false',
        'python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py',
    ),
    'mcp/services/abyss-stack-mcp/AGENTS.md': (
        'runtime observation',
        'not a gateway',
        'execution_authorized=false',
        'python mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py',
    ),
    'mcp/services/aoa-telegram-connector-mcp/AGENTS.md': (
        'read-only',
        'aoa-telegram-connector',
        'permission_report',
        'network_touched=false',
        'python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py',
    ),
    'mcp/services/aoa-discord-connector-mcp/AGENTS.md': (
        'read-only',
        'aoa-discord-connector',
        'permission_report',
        'network_touched=false',
        'python mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py',
    ),
    'mcp/services/aoa-course-connector-mcp/AGENTS.md': (
        'stack-owned package',
        'aoa-course-connector',
        'connected_run',
        'read contour',
        'python mcp/services/aoa-course-connector-mcp/scripts/validate_course_connector_mcp.py',
    ),
    'mcp/services/aoa-stackoverflow-connector-mcp/AGENTS.md': (
        'read-only access plane',
        'aoa-stackoverflow-connector',
        'query-hybrid',
        'network_touched=false',
        'python mcp/services/aoa-stackoverflow-connector-mcp/scripts/validate_stackoverflow_connector_mcp.py',
    ),
    'mcp/services/aoa-xda-connector-mcp/AGENTS.md': (
        'read-only MCP access plane',
        'aoa-xda-connector',
        'query-hybrid',
        'network_touched=false',
        'python mcp/services/aoa-xda-connector-mcp/scripts/validate_xda_connector_mcp.py',
    ),
    'mcp/services/aoa-memo-mcp/AGENTS.md': (
        'thin MCP access plane',
        'aoa-memo',
        'repo-local `memo/`',
        'python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py',
    ),
    'mcp/services/aoa-decisions-mcp/AGENTS.md': (
        'thin MCP access plane',
        'decision graph',
        'require_fresh()',
        'python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py',
    ),
    'mcp/services/aoa-evals-mcp/AGENTS.md': (
        'thin MCP access plane',
        'aoa-evals',
        'candidate-only',
        'python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py',
    ),
    'mcp/services/aoa-kag-mcp/AGENTS.md': (
        'thin read-only MCP access plane',
        'aoa-kag',
        'provider map',
        'source-return',
        'python mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py',
    ),
    'mcp/services/aoa-stats-mcp/AGENTS.md': (
        'thin read-only MCP access plane',
        'aoa-stats',
        'stats_owner_port_read',
        'python mcp/services/aoa-stats-mcp/scripts/validate_stats_mcp.py',
    ),
    'mcp/services/abyss-machine-mcp/AGENTS.md': (
        'thin MCP access plane',
        'abyss-machine',
        'owner-aware',
        'python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py',
    ),
    'mcp/services/aoa-session-memory-mcp/AGENTS.md': (
        'thin MCP access plane',
        '.aoa',
        'session evidence',
        'python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py',
    ),
    'mcp/services/tos-corpus-mcp/AGENTS.md': (
        'thin MCP access plane',
        'Tree of Sophia corpus index',
        'ToS/derived-exports/tos_corpus_index.min.json',
        'MCP packets are navigation aids, not source truth',
        'python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py',
    ),
    'memo/AGENTS.md': (
        'abyss-stack local memory port',
        'write_candidate_only',
        'candidates/',
        'mcp/services/aoa-memo-mcp/AGENTS.md',
    ),
    'stats/AGENTS.md': (
        'stack-local statistical questions',
        'aoa-stats',
        'selected_now',
        'unknown, not zero',
        'python scripts/validate_local_stats_port.py',
    ),
    'skills/AGENTS.md': (
        'canonical home for agent procedures',
        'belongs to `abyss-stack`',
        'OS user profile',
        'session traces',
        'techniques as optional provenance',
        'manual positive, negative, owner-return, and coexistence pass',
    ),
    '.agents/spark/AGENTS.md': (
        'fast-loop lane',
        '.agents/spark/README.md',
        'one bounded patch per loop',
        'narrowest relevant validation',
        'secret-bearing material stayed out of committed surfaces',
    ),
    'quests/AGENTS.md': (
        'questbook district',
        'quests/<lane>/<state>',
        'quests/schemas',
        'quests/examples',
        'python scripts/validate_stack.py',
    ),
    'kag/AGENTS.md': (
        'repository-local KAG provider home',
        'kag/manifest.json',
        'runtime source home',
        'aoa-kag',
    ),
    'tests/AGENTS.md': (
        'runtime validation gate',
        'tests/README.md',
        'Package-owned mechanics tests',
        'deterministic and public-safe',
        'no live host state',
        'python -m pytest',
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
        'docs/install/DEPLOYMENT.md',
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
        'read-only machine bridge',
        'aoa-host-facts',
        'Do not mutate /srv/abyss-machine',
    ),
    'mechanics/inference-pilots/AGENTS.md': (
        'inference-pilots',
        'bounded local inference pilots',
        'aoa-llamacpp-pilot',
        'aoa-long-horizon-pilot',
        'mechanics/agon-runtime',
    ),
    'mechanics/inference-pilots/parts/tos-foundation-lab/AGENTS.md': (
        'Tree of Sophia source forensics',
        '/etc/abyss-machine/storage-policy.json',
        'Never synthesize a missing human-only lane',
        'Manual source-visible review owns content acceptance',
        'tos_foundation_lab.py validate',
    ),
    'mechanics/agon-runtime/AGENTS.md': (
        'agon-runtime',
        'dry-run kernel',
        'PROVENANCE.md',
        'parts/runtime-kernels',
        'validate_mechanical_trial_runs.py',
    ),
    'mechanics/experience-runtime/AGENTS.md': (
        'experience-runtime',
        'experience contract family',
        'legacy/ARCHIVE_CLASSIFICATION.md',
        'PROVENANCE.md',
        'EXPERIENCE_RECORDS_DISTILLATION.md',
        'not active runtime contracts',
    ),
    'mechanics/federation-seams/AGENTS.md': (
        'federation-seams',
        'runtime consumption of sibling owner surfaces',
        'aoa-sync-federation-surfaces',
        'mirrored owner surfaces',
    ),
    'mechanics/federation-seams/parts/memo-seam/AGENTS.md': (
        'runtime seam for bounded `aoa-memo` federation',
        'public-safe memo mirror',
        'route-api inspection',
        'scripts/aoa-export-memo-candidate',
    ),
    'mechanics/governed-execution/AGENTS.md': (
        'governed-execution',
        'governed local-worker execution',
        'mechanics/governed-execution/parts/governed-runner/tests',
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
}
LEGACY_ARCHIVE_AGENTS_DOCS: tuple[str, ...] = (
    'mechanics/agon-runtime/legacy/AGENTS.md',
    'mechanics/experience-runtime/legacy/AGENTS.md',
    'mechanics/inference-pilots/legacy/AGENTS.md',
    'mechanics/runtime-repair/legacy/AGENTS.md',
)
ADVISORY_AGENT_DIRS: tuple[str, ...] = ('config', 'manifests/recurrence')
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
    known_legacy_archive = set(LEGACY_ARCHIVE_AGENTS_DOCS)
    actual = discover_nested_agents(repo_root)
    untracked = sorted(actual - required - known_legacy_archive)
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
