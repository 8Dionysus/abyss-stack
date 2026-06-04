from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

TextReader = Callable[[Path], str | None]

ROADMAP_PATH = Path("ROADMAP.md")
PLAYBOOK_RUNTIME_SEAM_PATH = (
    Path("mechanics")
    / "federation-seams"
    / "parts"
    / "playbook-seam"
    / "docs"
    / "PLAYBOOK_RUNTIME_SEAM.md"
)
EVAL_RUNTIME_SEAM_PATH = (
    Path("mechanics")
    / "federation-seams"
    / "parts"
    / "eval-seam"
    / "docs"
    / "EVAL_RUNTIME_SEAM.md"
)
MEMO_RUNTIME_SEAM_PATH = (
    Path("mechanics")
    / "federation-seams"
    / "parts"
    / "memo-seam"
    / "docs"
    / "MEMO_RUNTIME_SEAM.md"
)
RPG_RUNTIME_ROOT = Path("mechanics") / "federation-seams" / "parts" / "rpg-runtime"
RPG_RUNTIME_BUILDERS_PATH = RPG_RUNTIME_ROOT / "docs" / "RPG_RUNTIME_BUILDERS.md"
LOCAL_AI_TRIALS_DOC_PATH = (
    Path("mechanics")
    / "inference-pilots"
    / "parts"
    / "local-trials"
    / "docs"
    / "LOCAL_AI_TRIALS.md"
)
LOCAL_AI_TRIALS_README_PATH = (
    Path("mechanics") / "inference-pilots" / "parts" / "local-trials" / "README.md"
)
RPG_PROJECTION_PATH = RPG_RUNTIME_ROOT / "aoa_rpg_runtime_projection.py"
RPG_QUEST_RUN_RESULT_EXAMPLE_PATH = RPG_RUNTIME_ROOT / "examples" / "quest_run_result.example.json"
GENERATED_QUEST_RUN_RESULTS_PATH = RPG_RUNTIME_ROOT / "generated" / "quest_run_results.json"
GENERATED_REPUTATION_LEDGERS_PATH = RPG_RUNTIME_ROOT / "generated" / "reputation_ledgers.json"
FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH = (
    RPG_RUNTIME_ROOT / "schemas" / "frontend_projection_bundle.schema.json"
)
FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH = (
    RPG_RUNTIME_ROOT / "examples" / "frontend_projection_bundle.example.json"
)
GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH = (
    RPG_RUNTIME_ROOT / "generated" / "frontend_projection_bundles.json"
)
PLAYBOOKS_FEDERATION_CONFIG_PATH = (
    Path("config-templates") / "Configs" / "federation" / "aoa-playbooks.yaml"
)
ROUTE_API_PATH = (
    Path("config-templates") / "Services" / "route-api" / "app" / "main.py"
)
UPSTREAM_COMPATIBILITY_BRIDGE_PATH = (
    Path("config-templates") / "Configs" / "federation" / "upstream-compatibility-bridge.json"
)

TEXT_GUARDS: Mapping[Path, Sequence[str]] = {
    ROADMAP_PATH: (
        "## Phase ",
        "Phases 0 through 6",
    ),
    PLAYBOOK_RUNTIME_SEAM_PATH: (
        "/playbooks/automation-seeds",
        "/playbooks/automation-seed",
        "automation-seed",
        "automation seeds",
    ),
    EVAL_RUNTIME_SEAM_PATH: (
        "Phase Alpha",
        "phase-alpha",
        "this phase",
    ),
    MEMO_RUNTIME_SEAM_PATH: (
        "Phase 3",
        "this phase",
    ),
    RPG_RUNTIME_BUILDERS_PATH: (
        "### Phase ",
    ),
    LOCAL_AI_TRIALS_DOC_PATH: (
        "qualification phase",
        "phase-by-phase",
        "archived phase",
    ),
    LOCAL_AI_TRIALS_README_PATH: (
        "phase-gated",
    ),
}
RPG_TEXT_PATHS = (
    RPG_PROJECTION_PATH,
    RPG_QUEST_RUN_RESULT_EXAMPLE_PATH,
    GENERATED_QUEST_RUN_RESULTS_PATH,
    GENERATED_REPUTATION_LEDGERS_PATH,
)
RPG_BUNDLE_PATHS = (
    FRONTEND_PROJECTION_BUNDLE_SCHEMA_PATH,
    FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH,
    GENERATED_FRONTEND_PROJECTION_BUNDLES_PATH,
)
ACTIVE_TOPOLOGY_LANGUAGE_FILES = tuple(TEXT_GUARDS) + RPG_TEXT_PATHS + RPG_BUNDLE_PATHS + (
    PLAYBOOKS_FEDERATION_CONFIG_PATH,
    ROUTE_API_PATH,
    UPSTREAM_COMPATIBILITY_BRIDGE_PATH,
)


def read_text(root: Path, relative_path: Path, read_text_func: TextReader) -> str:
    return read_text_func(root / relative_path) or ""


def validate_forbidden_topology_words(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
) -> None:
    for path, forbidden_snippets in TEXT_GUARDS.items():
        text = read_text(root, path, read_text_func)
        for snippet in forbidden_snippets:
            if snippet in text:
                errors.append(
                    f"{path.as_posix()} must not keep active topology wording `{snippet}`"
                )


def validate_rpg_runtime_language(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
) -> None:
    for path in RPG_TEXT_PATHS:
        text = read_text(root, path, read_text_func)
        if "RPG_RUNTIME_PROJECTION_WAVE.md" in text:
            errors.append(
                f"{path.as_posix()} must target the Agents-of-Abyss runtime-projection part, not the legacy wave doc"
            )

    for path in RPG_BUNDLE_PATHS:
        text = read_text(root, path, read_text_func)
        if '"seed"' in text or '"status": "seed"' in text:
            errors.append(
                f"{path.as_posix()} must use draft/promoted runtime status language instead of seed status"
            )


def validate_route_api_bridge_language(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
) -> None:
    playbooks_config = read_text(root, PLAYBOOKS_FEDERATION_CONFIG_PATH, read_text_func)
    if "playbook_activation.split-wave-cross-repo-rollout.example.json" in playbooks_config:
        errors.append("aoa-playbooks federation allowlist must not require the split-wave activation example")

    route_api = read_text(root, ROUTE_API_PATH, read_text_func)
    bridge_config_text = read_text(root, UPSTREAM_COMPATIBILITY_BRIDGE_PATH, read_text_func)
    for required_snippet in ("memo-recall-rerun", "memo-contradiction-gap", "memo-contradiction-rerun"):
        if required_snippet not in bridge_config_text:
            errors.append(f"upstream compatibility bridge config must expose clean route `{required_snippet}`")
    for required_snippet in (
        '"/playbooks/automation-plans"',
        '"/playbooks/automation-plan"',
        "upstream-compatibility-bridge.json",
    ):
        if required_snippet not in route_api:
            errors.append(f"route-api must expose clean active bridge `{required_snippet}`")
    for required_bridge in (
        '"/playbooks/automation-seeds"',
        '"/playbooks/automation-seed"',
        "compatibility_bridge_for",
    ):
        if required_bridge not in route_api:
            errors.append(f"route-api must preserve compatibility bridge `{required_bridge}`")


def validate_active_topology_language(
    errors: list[str],
    *,
    root: Path,
    read_text_func: TextReader,
) -> None:
    validate_forbidden_topology_words(errors, root=root, read_text_func=read_text_func)
    validate_rpg_runtime_language(errors, root=root, read_text_func=read_text_func)
    validate_route_api_bridge_language(errors, root=root, read_text_func=read_text_func)
