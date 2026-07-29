from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from aoa_stats_mcp.core import AoAStatsMCPState, StatsAccessError
from aoa_stats_mcp.server import build_server


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def seed_workspace(tmp_path: Path) -> tuple[AoAStatsMCPState, Path, Path, Path]:
    workspace = tmp_path / "workspace"
    central = workspace / "aoa-stats"
    memo = workspace / "aoa-memo"
    stack = tmp_path / "abyss-stack-source"

    write_json(
        central / "stats/federation/owner-inventory.json",
        {
            "schema_version": "aoa_stats_owner_inventory_v1",
            "contract_version": "1.0.0",
            "owners": [
                {
                    "repo_id": "aoa-stats",
                    "workspace_route": "workspace:aoa-stats",
                    "owner_boundary_ref": "aoa-stats:AGENTS.md",
                    "classification": "implemented",
                    "port_ref": "aoa-stats:stats/source_home.manifest.json",
                },
                {
                    "repo_id": "aoa-memo",
                    "workspace_route": "workspace:aoa-memo",
                    "owner_boundary_ref": "aoa-memo:AGENTS.md",
                    "classification": "implemented",
                    "port_ref": "aoa-memo:stats/port.manifest.json",
                },
                {
                    "repo_id": "abyss-stack",
                    "workspace_route": "source:abyss-stack",
                    "owner_boundary_ref": "abyss-stack:AGENTS.md",
                    "classification": "implemented",
                    "port_ref": "abyss-stack:stats/port.manifest.json",
                },
            ],
            "routed_surfaces": [
                {
                    "id": "runtime-mirror",
                    "classification": "routed_to_stronger_owner",
                    "owner_repo": "abyss-stack",
                    "owner_route": "source:abyss-stack",
                    "rationale": "not a second source owner",
                }
            ],
        },
    )
    write_json(
        central / "stats/source_home.manifest.json",
        {
            "schema_version": "aoa_stats_source_home_v3",
            "owner_repo": "aoa-stats",
            "status": "active_source_home",
            "role": "shared statistical grammar",
            "branches": [
                {
                    "id": "measurement_contract",
                    "path": "stats/measurement-contract",
                    "role": "portable measurement grammar",
                    "owner_surface": "stats/measurement-contract/AGENTS.md",
                    "authority_ceiling": "shape only",
                },
                {
                    "id": "federation",
                    "path": "stats/federation",
                    "role": "owner inventory",
                    "owner_surface": "stats/federation/AGENTS.md",
                    "authority_ceiling": "coverage only",
                },
            ],
        },
    )
    write_json(
        central / "generated/summary_surface_catalog.min.json",
        {
            "schema_version": "aoa_stats_summary_surface_catalog_v2",
            "surfaces": [
                {
                    "name": "example_summary",
                    "surface_ref": "generated/example_summary.min.json",
                    "schema_ref": "schemas/example.schema.json",
                    "primary_question": "What was observed?",
                    "derivation_rule": "owner-defined fixture derivation",
                    "input_posture": "reference",
                    "owner_truth_inputs": ["owner evidence refs"],
                    "authority_ceiling": "weaker than owner evidence",
                    "consumer_risk": "low",
                    "live_state_capable": True,
                }
            ],
        },
    )
    write_json(
        central / "generated/example_summary.min.json",
        {"schema_version": "example_v1", "rows": [{"id": 1}, {"id": 2}, {"id": 3}]},
    )
    reader = central / "scripts/read_measurement_packet.py"
    reader.parent.mkdir(parents=True, exist_ok=True)
    reader.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "if request['packet'].get('force_error'):\n"
        "    print('[error] forced adapter failure', file=sys.stderr)\n"
        "    raise SystemExit(3)\n"
        "print(json.dumps(request['packet']['adapter_result'], sort_keys=True))\n",
        encoding="utf-8",
    )

    measurement = {
        "schema_version": "aoa_stats_measurement_contract_v1",
        "measurement_id": "aoa-memo/reviewed-object-count",
        "contract_version": "1.0.0",
        "owner_repo": "aoa-memo",
        "question_ref": "question:reviewed-object-count",
        "semantic_class": "measure",
        "statistic": "count",
        "object_kind": "reviewed-object",
        "unit": {"symbol": "object", "quantity": "count"},
        "population": {"subject": "reviewed objects"},
        "window": {"temporality": "instant", "clock": "owner_defined"},
        "dimensions": {"allowed": [], "prohibited": ["raw_content"]},
        "missingness": {"states": ["missing", "unknown", "stale"], "zero_is_observation": True},
        "uncertainty": {"required": False, "methods": ["not_applicable"]},
        "authority_ceiling": "count only",
    }
    port = {
        "schema_version": "aoa_stats_local_port_v1",
        "contract_version": "1.0.0",
        "owner_repo": "aoa-memo",
        "status": "active",
        "evidence_posture": {
            "live_state": "reference_only",
            "privacy": "public",
            "raw_content_allowed": False,
        },
        "questions": [
            {
                "id": "question:reviewed-object-count",
                "question": "How many reviewed objects exist?",
                "consumer_refs": ["stats/README.md"],
            }
        ],
        "measurements": [measurement],
        "exports": [
            {
                "measurement_id": measurement["measurement_id"],
                "posture": "reference",
                "packet_refs": ["stats/packets/reviewed-object-count.reference.json"],
                "evidence_refs": ["memo/objects/**/object.json"],
            }
        ],
    }
    write_json(memo / "stats/port.manifest.json", port)
    stack.mkdir(parents=True)

    return (
        AoAStatsMCPState.discover(
            workspace_root=workspace,
            aoa_stats_root=central,
            source_roots={"abyss-stack": stack},
        ),
        workspace,
        central,
        stack,
    )


def compatible_adapter_result() -> dict[str, object]:
    return {
        "schema_version": "aoa_stats_packet_read_result_v1",
        "truth_status": "compatibility_check_only",
        "compatible": True,
        "measurement_id": "aoa-memo/reviewed-object-count",
        "contract_version": "1.0.0",
        "semantic_identity": "aoa-stats-statistic:sha256:" + "a" * 64,
        "evidence_identity": "aoa-stats-evidence:sha256:" + "b" * 64,
        "owner_authority_ceiling": "count only",
        "access_authority_ceiling": "owner-produced fixture result",
        "issues": [],
    }


def test_owner_inventory_reports_materialization_without_promoting_it_to_truth(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    packet = state.owner_port_read()

    assert packet["owner_count"] == 3
    assert packet["materialization_counts"] == {"available": 2, "port_missing": 1}
    assert packet["truth_status"] == "inventory_and_local_materialization_only"
    assert packet["routed_surfaces"][0]["classification"] == "routed_to_stronger_owner"


def test_deployed_stack_environment_materializes_stack_owner_port(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, workspace, central, stack = seed_workspace(tmp_path)
    write_json(
        stack / "stats/port.manifest.json",
        {
            "schema_version": "aoa_stats_local_port_v1",
            "contract_version": "1.0.0",
            "owner_repo": "abyss-stack",
            "status": "active",
            "questions": [],
            "measurements": [],
            "exports": [],
        },
    )
    monkeypatch.delenv("AOA_SOURCE_ROOT", raising=False)
    monkeypatch.setenv("AOA_ABYSS_STACK_ROOT", str(stack))

    state = AoAStatsMCPState.discover(
        workspace_root=workspace,
        aoa_stats_root=central,
    )
    packet = state.owner_port_read(repo="abyss-stack")

    assert state.source_roots["abyss-stack"] == stack.resolve()
    assert packet["status"] == "available"
    assert packet["port"]["owner_repo"] == "abyss-stack"


def test_owner_measurement_read_preserves_definition_and_evidence_refs(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    packet = state.owner_port_read(
        repo="aoa-memo",
        measurement_id="aoa-memo/reviewed-object-count",
    )

    assert packet["status"] == "available"
    assert packet["truth_status"] == "owner_local_definition_only"
    assert packet["measurement"]["population"]["subject"] == "reviewed objects"
    assert packet["measurement"]["missingness"]["states"] == ["missing", "unknown", "stale"]
    assert packet["exports"][0]["evidence_refs"] == ["memo/objects/**/object.json"]
    assert packet["owner_authority_ceiling"] == "count only"


def test_unknown_owner_and_measurement_are_explicit(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    assert state.owner_port_read(repo="unknown")["status"] == "unknown_owner"
    missing = state.owner_port_read(repo="aoa-memo", measurement_id="aoa-memo/missing")
    assert missing["status"] == "measurement_missing"
    assert missing["available_measurement_ids"] == ["aoa-memo/reviewed-object-count"]


def test_inventory_workspace_route_cannot_escape_workspace(tmp_path: Path) -> None:
    state, _, central, _ = seed_workspace(tmp_path)
    inventory_path = central / "stats/federation/owner-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["owners"][1]["workspace_route"] = "workspace:../outside"
    write_json(inventory_path, inventory)

    with pytest.raises(StatsAccessError, match="escapes its owner root"):
        state.owner_port_read()


def test_surface_read_is_catalog_confined_and_reference_explicit(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    packet = state.surface_read(surface_name="example_summary", limit=2)

    assert packet["status"] == "available"
    assert packet["observation_posture"] == "reference_only"
    assert packet["freshness_status"] == "not_attested"
    assert packet["payload"]["rows_total_items"] == 3
    assert len(packet["payload"]["rows"]) == 2
    with pytest.raises(StatsAccessError, match="unknown catalog surface"):
        state.surface_read(surface_ref="../../etc/passwd")


def test_live_surface_materialization_does_not_attest_freshness(tmp_path: Path) -> None:
    state, _, central, _ = seed_workspace(tmp_path)
    committed = json.loads(
        (central / "generated/summary_surface_catalog.min.json").read_text(encoding="utf-8")
    )
    write_json(central / "state/generated/summary_surface_catalog.min.json", committed)
    write_json(
        central / "state/generated/example_summary.min.json",
        {"schema_version": "example_v1", "rows": [{"id": 9}]},
    )

    packet = state.surface_read(surface_name="example_summary")

    assert packet["surface_ref"] == "state/generated/example_summary.min.json"
    assert packet["observation_posture"] == "live_materialized_freshness_unattested"
    assert packet["freshness_status"] == "not_attested"


def test_boundary_packet_is_compact_and_source_linked(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    packet = state.boundary_rules()

    assert packet["source_owner"] == "aoa-stats"
    assert packet["access_owner"] == "abyss-stack"
    assert [row["id"] for row in packet["branch_authority_ceilings"]] == [
        "measurement_contract",
        "federation",
    ]
    assert "boundary_text" not in packet
    assert "architecture_text" not in packet


def test_packet_adapter_returns_owner_result_without_semantic_reimplementation(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)
    expected = compatible_adapter_result()

    result = state.packet_check(contract={"owner": "fixture"}, packet={"adapter_result": expected})

    assert result == expected


def test_packet_adapter_reports_owner_reader_failure(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    with pytest.raises(StatsAccessError, match="failed with exit 3"):
        state.packet_check(contract={}, packet={"force_error": True})


def test_packet_adapter_rejects_oversized_requests_before_subprocess(tmp_path: Path) -> None:
    state, _, _, _ = seed_workspace(tmp_path)

    with pytest.raises(StatsAccessError, match="packet request exceeds"):
        state.packet_check(contract={}, packet={"padding": "x" * (2 * 1024 * 1024)})


def test_server_exposes_only_proven_read_only_tools(tmp_path: Path) -> None:
    _, workspace, central, stack = seed_workspace(tmp_path)
    server = build_server(
        workspace_root=workspace,
        aoa_stats_root=central,
        source_roots={"abyss-stack": stack},
    )

    tools = asyncio.run(server.list_tools())
    assert server._mcp_server.version == "0.1.0"
    assert {tool.name for tool in tools} == {
        "stats_catalog",
        "stats_surface_read",
        "stats_boundary_rules",
        "stats_owner_port_read",
        "stats_packet_check",
    }
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.openWorldHint is False
    assert asyncio.run(server.list_resources()) == []
    assert asyncio.run(server.list_resource_templates()) == []
    assert asyncio.run(server.list_prompts()) == []


@pytest.mark.skipif(
    not os.environ.get("AOA_STATS_ROOT"),
    reason="external aoa-stats public contract owner is not configured",
)
def test_external_packet_reader_boundary_matches_direct_cli() -> None:
    central = Path(os.environ["AOA_STATS_ROOT"]).resolve()
    reader = central / "scripts/read_measurement_packet.py"
    assert reader.is_file(), (
        "configured aoa-stats owner does not expose the public packet reader: "
        f"{reader}"
    )
    request = {
        "schema_version": "aoa_stats_packet_read_request_v1",
        "contract": {},
        "packet": {},
    }
    direct = subprocess.run(
        [sys.executable, str(reader)],
        cwd=central,
        input=json.dumps(request),
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert direct.returncode == 0, direct.stderr

    via_adapter = AoAStatsMCPState.discover(aoa_stats_root=central).packet_check(
        contract={},
        packet={},
    )

    assert via_adapter == json.loads(direct.stdout)
    assert via_adapter["truth_status"] == "compatibility_check_only"
    assert via_adapter["compatible"] is False
