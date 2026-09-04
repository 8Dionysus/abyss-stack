from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT
    / "mechanics"
    / "federation-seams"
    / "parts"
    / "tos-graph"
    / "aoa_tos_graph.sh"
)
UI_PATH = REPO_ROOT / "config-templates" / "Services" / "tos-graph" / "app" / "ui.py"
FRONTEND_PATH = (
    REPO_ROOT
    / "config-templates"
    / "Services"
    / "tos-graph"
    / "frontend"
    / "src"
    / "main.ts"
)


def test_force_start_bypasses_tos_graph_only_shortcut() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert (
        "elif ((force_start == 0)) && ((${#forward_args[@]} == 0)) && substrate_ready; then"
        in script
    )


def test_wait_route_honors_custom_tos_graph_host_port() -> None:
    script = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'health_url="http://127.0.0.1:${host_port}/health"' in script
    assert "wait_for_health()" in script
    assert 'if [[ "$host_port" != "5410" ]]; then' in script
    assert "wait_for_health" in script.split('if [[ "$host_port" != "5410" ]]; then', 1)[1]


def test_public_shell_uses_product_title_and_hydrates_shared_routes() -> None:
    ui = UI_PATH.read_text(encoding="utf-8")
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")

    assert '<html lang="ru">' in ui
    assert "<title>Древо Софии</title>" in ui
    assert "const initialRoute = readInitialRoute();" in frontend
    assert (
        "loadMode(initialRoute.mode, initialRoute.viewId, initialRoute.graphMode, initialRoute.clusterId)"
        in frontend
    )
    assert 'url.searchParams.set("view", state.currentViewId)' in frontend


def test_public_shell_excludes_internal_material_workflow_from_the_atlas() -> None:
    frontend = FRONTEND_PATH.read_text(encoding="utf-8")

    assert 'if (posture === "candidate") return false;' in frontend
    assert 'if (itemLayers(source).includes("material-candidate")) return false;' in frontend
    assert 'if (representationLayer === "view_projection") return false;' in frontend
    assert 'if (isPublicSourceNote(source)) return false;' in frontend
    assert '"source_planting",' in frontend
    assert 'if (text(item.node_id)) return short(displayTitle(item), 30);' in frontend
    assert 'class="source-note-list"' in frontend
    assert "function projectPublicPhilosophyPayload" in frontend
    assert 'localizedProperty(item, "public_summary_ru", "public_summary_en")' in frontend
