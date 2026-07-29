from __future__ import annotations

from pathlib import Path

from scripts.validators import runtime_route_contracts


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def write_valid_surface(repo_root: Path) -> None:
    for relative_path in runtime_route_contracts.RUNTIME_ROUTE_CONTRACT_FILES:
        copy_current_surface(relative_path, into=repo_root)


def iter_text_files(root: Path) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def read_text_or_none(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def run_runtime_route_validator(repo_root: Path) -> list[str]:
    errors: list[str] = []
    runtime_route_contracts.validate_paths(
        errors,
        root=repo_root,
        text_file_iter_func=lambda: iter_text_files(repo_root),
        read_text_func=read_text_or_none,
    )
    return errors


def test_current_repo_runtime_route_contracts_module_passes() -> None:
    assert run_runtime_route_validator(REPO_ROOT) == []


def test_stale_runtime_root_is_blocked_outside_legacy_migration(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    stale_doc = tmp_path / "docs" / "runtime" / "STALE_ROOT.md"
    write_text(stale_doc, f"old root: {runtime_route_contracts.STALE_ABYSS_PATH}/runtime")

    errors = run_runtime_route_validator(tmp_path)

    assert (
        f"stale path '{runtime_route_contracts.STALE_ABYSS_PATH}' found in docs/runtime/STALE_ROOT.md"
        in errors
    )


def test_stale_stack_root_is_blocked_in_active_source(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    stale_doc = tmp_path / "docs" / "runtime" / "STALE_STACK_ROOT.md"
    write_text(stale_doc, f"old root: {runtime_route_contracts.STALE_STACK_ROOT}")

    errors = run_runtime_route_validator(tmp_path)

    assert (
        f"stale stack root '{runtime_route_contracts.STALE_STACK_ROOT}' "
        "found in docs/runtime/STALE_STACK_ROOT.md"
        in errors
    )


def test_historical_kag_indexes_are_not_reclassified_as_active_source(
    tmp_path: Path,
) -> None:
    write_valid_surface(tmp_path)
    event_index = tmp_path / "kag" / "indexes" / "repo_event_index.json"
    write_text(
        event_index,
        '{"label":"historical '
        + runtime_route_contracts.STALE_STACK_ROOT
        + ' migration event"}\n',
    )

    assert run_runtime_route_validator(tmp_path) == []


def test_readme_must_stay_route_focused(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    readme_path = tmp_path / "README.md"
    write_text(
        readme_path,
        readme_path.read_text(encoding="utf-8") + "\npython scripts/validate_stack.py\n",
    )

    errors = run_runtime_route_validator(tmp_path)

    assert (
        "README.md must stay route-focused; move root inventory detail "
        "to the owning surface instead of `python scripts/validate_stack.py`"
        in errors
    )


def test_runtime_paths_doc_must_keep_tos_root_route(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    paths_doc = tmp_path / runtime_route_contracts.PATHS_DOC_PATH
    write_text(
        paths_doc,
        paths_doc.read_text(encoding="utf-8").replace("AOA_TOS_ROOT", "AOA TOS ROOT"),
    )

    errors = run_runtime_route_validator(tmp_path)

    assert "docs/runtime/PATHS.md must mention AOA_TOS_ROOT" in errors


def test_governed_policy_must_keep_surface_type(tmp_path: Path) -> None:
    write_valid_surface(tmp_path)
    policy_path = tmp_path / runtime_route_contracts.GOVERNED_POLICY_PATH
    write_text(
        policy_path,
        policy_path.read_text(encoding="utf-8").replace(
            '"runtime_governed_execution_policy"',
            '"runtime_governed_execution_policy_broken"',
        ),
    )

    errors = run_runtime_route_validator(tmp_path)

    assert (
        "governed execution policy must declare "
        "surface_type=runtime_governed_execution_policy"
        in errors
    )


def test_governed_policy_rejects_retired_routing_mutation_target(
    tmp_path: Path,
) -> None:
    write_valid_surface(tmp_path)
    policy_path = tmp_path / runtime_route_contracts.GOVERNED_POLICY_PATH
    write_text(
        policy_path,
        policy_path.read_text(encoding="utf-8").replace(
            '"targets": {',
            '"targets": {"aoa-routing": {},',
            1,
        ),
    )

    errors = run_runtime_route_validator(tmp_path)

    assert (
        "governed execution policy must declare only the active abyss-stack "
        "mutation target"
        in errors
    )


def test_runtime_paths_doc_rejects_retired_routing_checkout_root(
    tmp_path: Path,
) -> None:
    write_valid_surface(tmp_path)
    paths_doc = tmp_path / runtime_route_contracts.PATHS_DOC_PATH
    write_text(
        paths_doc,
        paths_doc.read_text(encoding="utf-8")
        + "\nretired root accidentally restored: "
        + runtime_route_contracts.RETIRED_ROUTING_ENV
        + "\n",
    )

    errors = run_runtime_route_validator(tmp_path)

    assert (
        "docs/runtime/PATHS.md must not advertise retired routing checkout "
        f"dependency {runtime_route_contracts.RETIRED_ROUTING_ENV}"
        in errors
    )


def test_active_source_rejects_retired_routing_checkout_consumer(
    tmp_path: Path,
) -> None:
    write_valid_surface(tmp_path)
    service = tmp_path / "systemd" / "user" / "retired-routing-consumer.service"
    write_text(
        service,
        "Environment="
        + runtime_route_contracts.RETIRED_ROUTING_ENV
        + "="
        + runtime_route_contracts.RETIRED_ROUTING_CHECKOUT
        + "\n",
    )

    errors = run_runtime_route_validator(tmp_path)

    assert (
        "retired routing checkout consumer found in "
        "systemd/user/retired-routing-consumer.service: "
        f"{runtime_route_contracts.RETIRED_ROUTING_ENV}"
        in errors
    )
    assert (
        "retired routing checkout consumer found in "
        "systemd/user/retired-routing-consumer.service: "
        f"{runtime_route_contracts.RETIRED_ROUTING_CHECKOUT}"
        in errors
    )


def test_derived_decision_graph_may_preserve_retired_checkout_provenance(
    tmp_path: Path,
) -> None:
    write_valid_surface(tmp_path)
    graph = (
        tmp_path
        / "Logs"
        / "decision-graph"
        / "latest"
        / "workspace_decision_graph.json"
    )
    write_text(
        graph,
        '{"source_root":"'
        + runtime_route_contracts.RETIRED_ROUTING_CHECKOUT
        + '"}\n',
    )

    assert run_runtime_route_validator(tmp_path) == []
