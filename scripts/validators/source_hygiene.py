from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence, Set
import json
from pathlib import Path
import re
import subprocess

TextFileIterator = Callable[[], list[Path]]
GitFileIterator = Callable[[], list[str]]

BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".zip", ".pyc"}
AUTHORED_TEXT_SCAN_EXCLUDED_PARTS = {".git", ".deps"}
REPO_SELF_INDEX_SCHEMA_VERSIONS = {
    "aoa-repo-local-kag-index-v2",
    "aoa-repo-local-kag-repository-index-v2",
}
PORTABLE_INDEX_FAMILY_MANIFEST = Path("kag/indexes/index_family.manifest.json")
PORTABLE_INDEX_FAMILY_SHARDS = ("kag", "indexes", "shards")
SOURCE_HYGIENE_VALIDATOR_PATH = Path("scripts") / "validators" / "source_hygiene.py"
GIT_MIRROR_RUNTIME_TOP_LEVEL_DIRS = {"Secrets", "Logs", "Models"}
GIT_MIRROR_CACHE_PARTS = {
    "__pycache__",
    ".deps",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "node_modules",
}
GIT_MIRROR_LIVE_ENV_NAMES = {"stack.env", ".env"}
GIT_MIRROR_PRIVATE_SUFFIXES = (".private.json", ".private.yaml", ".private.yml")
GIT_MIRROR_RENDERED_SUFFIXES = (".rendered.yml", ".rendered.yaml")
GIT_MIRROR_DATABASE_SUFFIXES = (".db", ".sqlite", ".sqlite3")
GIT_MIRROR_HEAVY_SUFFIXES = (
    ".gguf",
    ".safetensors",
    ".pt",
    ".pth",
    ".onnx",
    ".ckpt",
    ".zip",
    ".tar",
    ".tar.gz",
    ".tgz",
    ".zst",
)
GIT_MIRROR_FIXTURE_PREFIXES = (
    "docs/",
    "examples/",
    "quests/",
    "schemas/",
    "tests/",
    "mechanics/",
    "config-templates/",
)
STALE_ACTIVE_SIBLING_ROOT_PATTERN = re.compile(
    r"/srv/(?:aoa-[A-Za-z0-9_-]+|Agents-of-Abyss|Tree-of-Sophia)"
)
HOST_LOCAL_SOURCE_CHECKOUT_PATTERNS = (
    re.compile(r"/home/[^/\s]+/src/abyss-stack(?=/|\s|$|[.,;:!?)\]}])"),
)
MOVED_MECHANIC_DOC_REFS = (
    "mechanics/config-projection/docs/RENDER_TRUTH.md",
    "mechanics/config-projection/docs/SECRETS_BOOTSTRAP.md",
    "mechanics/diagnostic-spine/docs/DIAGNOSTIC_SPINE.md",
    "mechanics/diagnostic-spine/docs/DOCTOR.md",
    "mechanics/diagnostic-spine/docs/LOCAL_OPS_DOCTOR_SPLIT.md",
    "mechanics/diagnostic-spine/docs/TRUTH_SURFACES.md",
    "mechanics/governed-execution/docs/CONTEXT_BUDGET_POLICY.md",
    "mechanics/governed-execution/docs/GOVERNED_EXECUTION.md",
    "mechanics/governed-execution/docs/RECURRENCE_RUNTIME_POLICY.md",
    "mechanics/inference-pilots/docs/LANGGRAPH_PILOT.md",
    "mechanics/inference-pilots/docs/LLAMACPP_PILOT.md",
    "mechanics/inference-pilots/docs/LOCAL_AI_TRIALS.md",
    "mechanics/inference-pilots/docs/RUNTIME_BENCH_POLICY.md",
    "mechanics/inference-pilots/docs/RUNTIME_WINNER_PROMOTION_LOOP.md",
    "mechanics/runtime-lifecycle/docs/GATEWAY_CACHE_POLICY.md",
    "mechanics/runtime-lifecycle/docs/INTERNAL_PROBES.md",
    "mechanics/runtime-lifecycle/docs/USAGE_BUDGET_POLICY.md",
)


def is_repo_self_index(path: Path, *, root: Path) -> bool:
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        return False
    if (
        relative_path.parts[:3] == PORTABLE_INDEX_FAMILY_SHARDS
        and path.suffix.lower() == ".jsonl"
    ):
        return True
    if relative_path.parts[:2] != ("kag", "indexes") or path.suffix.lower() != ".json":
        return False
    if relative_path == PORTABLE_INDEX_FAMILY_MANIFEST:
        return True
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") in REPO_SELF_INDEX_SCHEMA_VERSIONS
    )


def iter_text_files(root: Path, *, binary_suffixes: Set[str]) -> list[Path]:
    paths: list[Path] = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if AUTHORED_TEXT_SCAN_EXCLUDED_PARTS.intersection(path.parts):
            continue
        if path.suffix.lower() in binary_suffixes:
            continue
        if is_repo_self_index(path, root=root):
            continue

        paths.append(path)

    return paths


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def is_public_fixture_like_tracked_path(
    relative_path: str,
    *,
    fixture_prefixes: Sequence[str],
) -> bool:
    name = relative_path.rsplit("/", 1)[-1]
    if not relative_path.startswith(tuple(fixture_prefixes)):
        return False
    return (
        name.endswith(".example")
        or ".example." in name
        or name.endswith(".example.json")
        or name.endswith(".json.example")
        or name.endswith(".env.example")
        or ".public." in name
        or relative_path.startswith(("docs/", "schemas/", "tests/"))
    )


def tracked_file_git_mirror_hygiene_issue(
    relative_path: str,
    *,
    runtime_top_level_dirs: Set[str],
    cache_parts: Set[str],
    live_env_names: Set[str],
    private_suffixes: Sequence[str],
    rendered_suffixes: Sequence[str],
    database_suffixes: Sequence[str],
    heavy_suffixes: Sequence[str],
    fixture_prefixes: Sequence[str],
) -> str | None:
    normalized = relative_path.replace("\\", "/").strip("/")
    if not normalized:
        return None

    parts = normalized.split("/")
    name = parts[-1]
    lower_name = name.lower()
    lower_path = normalized.lower()
    fixture_like = is_public_fixture_like_tracked_path(
        normalized,
        fixture_prefixes=fixture_prefixes,
    )

    if parts[0] in runtime_top_level_dirs:
        return f"live runtime directory `{parts[0]}/`"
    if any(part in cache_parts for part in parts):
        return "local cache or dependency directory"
    if name in live_env_names:
        return "live env file"
    if lower_name.endswith(".env") and not lower_name.endswith(".env.example"):
        return "live env file"
    if lower_path.endswith(tuple(rendered_suffixes)):
        return "rendered compose/config output"
    if lower_path.endswith(tuple(database_suffixes)):
        return "database artifact"
    if lower_path.endswith(tuple(heavy_suffixes)):
        return "heavy archive or model artifact"
    if lower_path.endswith(tuple(private_suffixes)) and not fixture_like:
        return "private capture artifact"
    return None


def iter_tracked_git_files(root: Path) -> list[str]:
    if not (root / ".git").exists():
        return []
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return []
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line]


def validate_git_mirror_hygiene(
    errors: list[str],
    *,
    tracked_file_iter_func: GitFileIterator,
    runtime_top_level_dirs: Set[str],
    cache_parts: Set[str],
    live_env_names: Set[str],
    private_suffixes: Sequence[str],
    rendered_suffixes: Sequence[str],
    database_suffixes: Sequence[str],
    heavy_suffixes: Sequence[str],
    fixture_prefixes: Sequence[str],
) -> None:
    for relative_path in tracked_file_iter_func():
        issue = tracked_file_git_mirror_hygiene_issue(
            relative_path,
            runtime_top_level_dirs=runtime_top_level_dirs,
            cache_parts=cache_parts,
            live_env_names=live_env_names,
            private_suffixes=private_suffixes,
            rendered_suffixes=rendered_suffixes,
            database_suffixes=database_suffixes,
            heavy_suffixes=heavy_suffixes,
            fixture_prefixes=fixture_prefixes,
        )
        if issue:
            errors.append(
                "tracked file is not GitHub mirror safe: "
                f"{relative_path} ({issue})"
            )


def validate_no_host_local_source_checkout_paths(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    host_local_source_checkout_patterns: Sequence[re.Pattern[str]],
    skip_paths: Iterable[Path],
) -> None:
    skip_paths = set(skip_paths)
    for path in text_file_iter_func():
        if path in skip_paths:
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for pattern in host_local_source_checkout_patterns:
            for match in pattern.finditer(text):
                errors.append(
                    "host-local source checkout path found in "
                    f"{path.relative_to(root)}: {match.group(0).rstrip('/')}"
                )


def validate_no_moved_mechanic_doc_refs(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    moved_mechanic_doc_refs: Sequence[str],
    skip_paths: Iterable[Path],
) -> None:
    skip_paths = set(skip_paths)
    for path in text_file_iter_func():
        if path in skip_paths:
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for moved_ref in moved_mechanic_doc_refs:
            if moved_ref in text:
                errors.append(
                    f"moved mechanic doc ref found in {path.relative_to(root)}: "
                    f"{moved_ref}"
                )


def is_legacy_archive_path(path: Path, *, root: Path) -> bool:
    try:
        return "legacy" in path.relative_to(root).parts
    except ValueError:
        return "legacy" in path.parts


def validate_no_stale_active_sibling_roots(
    errors: list[str],
    *,
    root: Path,
    text_file_iter_func: TextFileIterator,
    stale_active_sibling_root_pattern: re.Pattern[str],
) -> None:
    for path in text_file_iter_func():
        if is_legacy_archive_path(path, root=root):
            continue
        text = read_text_or_none(path)
        if text is None:
            continue
        for match in stale_active_sibling_root_pattern.finditer(text):
            errors.append(
                "stale active sibling root found in "
                f"{path.relative_to(root)}: {match.group(0)}"
            )
