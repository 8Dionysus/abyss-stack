from __future__ import annotations

from pathlib import Path

from scripts.validators import active_topology_language


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in active_topology_language.ACTIVE_TOPOLOGY_LANGUAGE_FILES:
        copy_current_surface(relative_path, into=repo_root)


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def run_active_topology_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    active_topology_language.validate_active_topology_language(
        errors,
        root=repo_root,
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_active_topology_language_module_passes() -> None:
    assert run_active_topology_validator(REPO_ROOT) == []


def test_roadmap_must_not_restore_phase_heading_topology(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    roadmap_path = tmp_path / active_topology_language.ROADMAP_PATH
    write_text(roadmap_path, roadmap_path.read_text(encoding="utf-8") + "\n## Phase 7\n")

    errors = run_active_topology_validator(tmp_path)

    assert "ROADMAP.md must not keep active topology wording `## Phase `" in errors


def test_rpg_runtime_must_not_point_to_legacy_wave_doc(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    rpg_path = tmp_path / active_topology_language.GENERATED_QUEST_RUN_RESULTS_PATH
    write_text(rpg_path, rpg_path.read_text(encoding="utf-8") + "\nRPG_RUNTIME_PROJECTION_WAVE.md\n")

    errors = run_active_topology_validator(tmp_path)

    assert (
        "mechanics/federation-seams/parts/rpg-runtime/generated/quest_run_results.json "
        "must target the Agents-of-Abyss runtime-projection part, not the legacy wave doc"
    ) in errors


def test_frontend_projection_bundle_must_not_use_seed_status(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    bundle_path = tmp_path / active_topology_language.FRONTEND_PROJECTION_BUNDLE_EXAMPLE_PATH
    write_text(bundle_path, bundle_path.read_text(encoding="utf-8") + '\n{"status": "seed"}\n')

    errors = run_active_topology_validator(tmp_path)

    assert (
        "mechanics/federation-seams/parts/rpg-runtime/examples/frontend_projection_bundle.example.json "
        "must use draft/promoted runtime status language instead of seed status"
    ) in errors


def test_playbook_federation_config_must_not_require_old_activation_example(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    config_path = tmp_path / active_topology_language.PLAYBOOKS_FEDERATION_CONFIG_PATH
    write_text(
        config_path,
        config_path.read_text(encoding="utf-8")
        + "\nplaybook_activation.split-wave-cross-repo-rollout.example.json\n",
    )

    errors = run_active_topology_validator(tmp_path)

    assert "aoa-playbooks federation allowlist must not require the split-wave activation example" in errors


def test_upstream_bridge_must_keep_clean_memo_contradiction_rerun_route(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    bridge_path = tmp_path / active_topology_language.UPSTREAM_COMPATIBILITY_BRIDGE_PATH
    write_text(
        bridge_path,
        bridge_path.read_text(encoding="utf-8").replace(
            "memo-contradiction-rerun",
            "memo-contradiction-review",
        ),
    )

    errors = run_active_topology_validator(tmp_path)

    assert (
        "upstream compatibility bridge config must expose clean route "
        "`memo-contradiction-rerun`"
    ) in errors


def test_route_api_must_expose_clean_active_playbook_plan_bridge(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    route_api_path = tmp_path / active_topology_language.ROUTE_API_PATH
    write_text(
        route_api_path,
        route_api_path.read_text(encoding="utf-8").replace(
            '"/playbooks/automation-plans"',
            '"/playbooks/plans"',
        ),
    )

    errors = run_active_topology_validator(tmp_path)

    assert (
        'route-api must expose clean active bridge `"/playbooks/automation-plans"`'
        in errors
    )
