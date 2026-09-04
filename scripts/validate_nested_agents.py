#!/usr/bin/env python3
"""Validate nested AGENTS.md guidance for abyss-stack.

This validator-first spine protects local AGENTS.md surfaces that already exist.
It also reports high-risk directories that are likely to need future local
guidance, without making those future files blocking before they land.
"""
from __future__ import annotations

import argparse
import re
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
        'VALIDATION.md#shared-repository-checks',
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
        'VALIDATION.md#shared-repository-checks',
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
        'VALIDATION.md#shared-repository-checks',
    ),
    'docs/validation/AGENTS.md': (
        'validation topology',
        'command authority',
        'validation_lanes.json',
        'inventories descriptive',
        'source-fast lane',
    ),
    'docs/testing/AGENTS.md': (
        'test topology',
        'test_inventory.json',
        'docs/validation/validation_lanes.json',
        'Keep legacy paths out of default pytest discovery',
        'tests lane',
    ),
    'docs/decisions/AGENTS.md': (
        'decision records',
        'Decision Review Gate',
        'TEMPLATE.md',
        'current source surfaces define what',
        'VALIDATION.md#shared-repository-checks',
    ),
    '.agents/skills/AGENTS.md': (
        'transitional repo-local projection of shared skills',
        'aoa-skills',
        'Canonical',
        'root `skills/`',
        'VALIDATION.md#shared-repository-checks',
    ),
    '.agents/AGENTS.md': (
        'transitional repo-local agent projections',
        '.agents/README.md',
        'canonical skill law',
        'stack-owned canonical packages under `skills/`',
        'VALIDATION.md#shared-repository-checks',
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
        'VALIDATION.md#shared-repository-checks',
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
        'mcp/services/README.md',
        'service-local `AGENTS.md`',
        'mcp-services lane',
        'VALIDATION.md#shared-repository-checks',
        'mcp/protocol-lab/VALIDATION.md',
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
        'mcp/services/README.md',
        'service-local `AGENTS.md`',
        'mcp-services lane',
        'VALIDATION.md#shared-repository-checks',
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
        'VALIDATION.md#shared-repository-checks',
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
        'VALIDATION.md#shared-repository-checks',
    ),
    'skills/AGENTS.md': (
        'canonical home for agent procedures',
        'belongs to `abyss-stack`',
        'OS user profile',
        'session traces',
        'techniques as optional provenance',
        'manual positive, negative, owner-return, and coexistence pass',
    ),
    'quests/AGENTS.md': (
        'questbook district',
        'quests/<lane>/<state>',
        'quests/schemas',
        'quests/examples',
        'VALIDATION.md#shared-repository-checks',
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
        'tests lane',
    ),
    'mechanics/AGENTS.md': (
        'runtime mechanics tree',
        'mechanics/README.md',
        'Package law',
        'VALIDATION.md#shared-repository-checks',
    ),
    'mechanics/runtime-lifecycle/AGENTS.md': (
        'runtime-lifecycle',
        'Runtime activation remains an explicit operator action',
        'docs/install/DEPLOYMENT.md',
        'VALIDATION.md#shared-repository-checks',
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
        'PROVENANCE.md',
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
    'mechanics/governed-execution/parts/external-codex-agent/AGENTS.md': (
        'external Codex incarnation',
        'built-in Codex multi-agent transport',
        'workspace-byte drift',
        'AOA_SDK_SOURCE_ROOT',
    ),
    'mechanics/governed-execution/parts/ephemeral-worker/AGENTS.md': (
        'bounded runtime-side read worker',
        'default-off',
        'content-addressed in-memory evidence',
        'Built-in Codex child-agent transport is forbidden.',
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
ADVISORY_AGENT_DIRS: tuple[str, ...] = ('config', 'manifests/recurrence')
HEADING_PREFIXES = ("# AGENTS.md", "# AGENTS")
IGNORED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
AGENTS_CHAIN_BUDGET_BYTES = 32 * 1024
RUNNABLE_FENCE_RE = re.compile(r"^\s*```(?:bash|sh|shell|console)\s*$", re.IGNORECASE | re.MULTILINE)
PROCEDURAL_HEADING_RE = re.compile(
    r"^(?:Validation|Verify|Validate|Smoke|Local Smoke|Run|Check)$", re.IGNORECASE
)
ORPHAN_LEADIN_RE = re.compile(
    r"^\s*(?:Run:|Validate with:|Then validate[^:]*:|start with:|use:)\s*$",
    re.IGNORECASE,
)
COMMAND_LINE_RE = re.compile(
    r"^\s*(?:[-*]\s+)?(?:"
    r"(?:python3?|pytest|bash|sh|shellcheck|systemctl|systemd-analyze)\s+"
    r"[-./\w$=|;&]"
    r"|(?:scripts/aoa[-\w./]+|aoa-[\w./-]+)\s+[-./\w$=|;&])",
    re.IGNORECASE,
)
INLINE_COMMAND_RE = re.compile(
    r"\b(?:run|execute|invoke|start|validate with|then validate|use)\s*:?[ \t]+"
    r"`?(?:"
    r"(?:python3?|pytest|bash|sh|shellcheck|systemctl|systemd-analyze)\s+[-./\w$=|;&]"
    r"|(?:scripts/aoa[-\w./]+|aoa-[\w./-]+)\s+[-./\w$=|;&])",
    re.IGNORECASE,
)
DANGLING_COLON_LINE_RE = re.compile(r"^\s*(?!#{1,6}\s).+?:\s*$")
ROOT_VALIDATION_SOURCE_RE = re.compile(r"^## `([^`]+/AGENTS\.md)`\s*$")
COMMAND_SNIPPET_MARKERS = (
    "python ",
    "pytest ",
    "bash -n",
    "shellcheck ",
    "systemctl ",
    "systemd-analyze",
    "scripts/aoa-",
    "aoa-",
    "AOA_",
)


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


def _is_validation_route_snippet(snippet: str) -> bool:
    normalized = _normalize(snippet)
    return (
        "validation.md" in normalized
        or normalized.endswith(" lane")
        or normalized.startswith("-")
        or any(
        marker.lower() in normalized for marker in COMMAND_SNIPPET_MARKERS
        )
    )


def _validation_route_text(path: Path, repo_root: Path) -> str:
    """Return on-demand validation prose for a card and its nearest route."""
    candidates: list[Path] = []
    current = path.parent
    while True:
        candidate = current / "VALIDATION.md"
        if candidate.is_file():
            candidates.append(candidate)
            break
        if current == repo_root:
            break
        current = current.parent
    root_validation = repo_root / "VALIDATION.md"
    if root_validation.is_file() and root_validation not in candidates:
        candidates.append(root_validation)

    rel_path = _relative(path, repo_root)
    route_texts: list[str] = []
    for candidate in candidates:
        text = candidate.read_text(encoding="utf-8")
        if candidate == root_validation:
            text = _root_validation_route_section(text, rel_path)
        route_texts.append(text)
    return "\n".join(route_texts)


def _root_validation_route_section(text: str, rel_path: str) -> str:
    """Return only the root VALIDATION section owned by one nested card."""
    section: list[str] = []
    collecting = False
    for line in text.splitlines():
        heading = ROOT_VALIDATION_SOURCE_RE.match(line)
        if heading:
            if collecting:
                break
            collecting = heading.group(1) == rel_path
        if collecting:
            section.append(line)
    return "\n".join(section)


def _active_lines(text: str) -> list[tuple[int, str]]:
    """Return source lines outside any Markdown fenced block."""
    active: list[tuple[int, str]] = []
    in_fence = False
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            active.append((line_number, line))
    return active


def _validate_root_validation_routes(text: str) -> list[str]:
    """Reject repeated source routes that make the human map ambiguous."""
    headings = [match.group(1) for match in map(ROOT_VALIDATION_SOURCE_RE.match, text.splitlines()) if match]
    duplicates = sorted({path for path in headings if headings.count(path) > 1})
    return [
        f"VALIDATION.md: duplicate source route heading {path!r}"
        for path in duplicates
    ]


def _validate_card_hygiene(rel_path: str, text: str) -> list[str]:
    issues: list[str] = []
    if RUNNABLE_FENCE_RE.search(text):
        issues.append(f"{rel_path}: runnable command fence remains in AGENTS.md; move it to VALIDATION.md")
    active = _active_lines(text)
    for line_number, line in active:
        if COMMAND_LINE_RE.match(line) or INLINE_COMMAND_RE.search(line):
            issues.append(
                f"{rel_path}:{line_number}: imperative command sequence remains in AGENTS.md; "
                "move it to VALIDATION.md"
            )
        if ORPHAN_LEADIN_RE.match(line):
            next_lines = [candidate for number, candidate in active if number > line_number and candidate.strip()]
            if not next_lines or not COMMAND_LINE_RE.match(next_lines[0]):
                issues.append(
                    f"{rel_path}:{line_number}: orphan procedural lead-in remains in AGENTS.md"
                )
        if DANGLING_COLON_LINE_RE.match(line):
            next_lines = [candidate for number, candidate in active if number > line_number and candidate.strip()]
            if not next_lines or re.match(r"^#{1,6}\s+", next_lines[0]):
                issues.append(
                    f"{rel_path}:{line_number}: dangling colon lead-in remains in AGENTS.md"
                )
    for index, (line_number, line) in enumerate(active):
        heading_match = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if not heading_match or not PROCEDURAL_HEADING_RE.match(heading_match.group(1).strip()):
            continue
        body: list[str] = []
        for _, candidate in active[index + 1 :]:
            if re.match(r"^#{1,6}\s+", candidate):
                break
            body.append(candidate)
        if not any(candidate.strip() and not candidate.strip().startswith("<!--") for candidate in body):
            issues.append(
                f"{rel_path}:{line_number}: empty procedural heading {heading_match.group(1)!r}"
            )
    return issues


def discover_nested_agents(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for path in repo_root.rglob("AGENTS.md"):
        if _is_ignored(path, repo_root):
            continue
        rel = _relative(path, repo_root)
        if rel != "AGENTS.md":
            found.add(rel)
    return found


def inherited_agents_chain(rel_path: str, available_agents: set[str]) -> tuple[str, ...]:
    path = Path(rel_path)
    candidates = ["AGENTS.md"]
    current = Path()
    for part in path.parent.parts:
        current /= part
        candidates.append((current / "AGENTS.md").as_posix())
    return tuple(candidate for candidate in candidates if candidate in available_agents)


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
    root_validation = repo_root / "VALIDATION.md"
    if root_validation.is_file():
        issues.extend(_validate_root_validation_routes(root_validation.read_text(encoding="utf-8")))

    for rel_path, snippets in REQUIRED_AGENTS_DOCS.items():
        path = repo_root / rel_path
        if not path.is_file():
            issues.append(f"{rel_path}: required nested AGENTS.md is missing")
            continue
        text = path.read_text(encoding="utf-8")
        if not _has_agents_heading(text):
            issues.append(f"{rel_path}: missing AGENTS heading")
        normalized = _normalize(text)
        validation_text = _normalize(_validation_route_text(path, repo_root))
        issues.extend(_validate_card_hygiene(rel_path, text))
        for snippet in snippets:
            needle = _normalize(snippet)
            haystack = normalized
            if _is_validation_route_snippet(snippet):
                haystack = f"{normalized} {validation_text}"
            if needle not in haystack:
                issues.append(f"{rel_path}: missing required snippet {snippet!r}")

    required = set(REQUIRED_AGENTS_DOCS)
    actual = discover_nested_agents(repo_root)
    available_agents = set(actual)
    if root_agents.is_file():
        available_agents.add("AGENTS.md")
    for rel_path in sorted(available_agents):
        chain = inherited_agents_chain(rel_path, available_agents)
        chain_bytes = sum((repo_root / item).stat().st_size for item in chain)
        if chain_bytes > AGENTS_CHAIN_BUDGET_BYTES:
            rendered_chain = " + ".join(chain)
            issues.append(
                f"{rel_path}: inherited AGENTS chain is {chain_bytes} bytes, "
                f"over {AGENTS_CHAIN_BUDGET_BYTES}: {rendered_chain}"
            )
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
        f"{len(REQUIRED_AGENTS_DOCS)} required nested document(s); "
        f"chain budget {AGENTS_CHAIN_BUDGET_BYTES} bytes."
    )
    for warning in result.warnings:
        print(f"[advisory] {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
