from __future__ import annotations

from pathlib import Path

from scripts.validators import profile_topology


REPO_ROOT = Path(__file__).resolve().parents[1]


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_current_surface(relative_path: Path, *, into: Path) -> None:
    write_text(into / relative_path, (REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def copy_current_profile_surface(repo_root: Path) -> None:
    for directory in (
        profile_topology.PROFILE_DIR,
        profile_topology.PRESET_DIR,
        profile_topology.MODULE_DIR,
    ):
        for source_path in (REPO_ROOT / directory).glob("*"):
            if source_path.is_file():
                copy_current_surface(source_path.relative_to(REPO_ROOT), into=repo_root)

    for relative_path in (
        Path("scripts") / "aoa-lib.sh",
        Path("systemd") / "user" / "podman-compose-abyss.service",
        Path(".github") / "workflows" / "validate-stack.yml",
        Path("env") / "stack.env.example",
        Path("docs") / "runtime" / "SERVICE_CATALOG.md",
        Path("mechanics") / "runtime-lifecycle" / "parts" / "start-stop" / "aoa_warmup.sh",
        Path("docs") / "install" / "DEPLOYMENT.md",
        Path("mechanics") / "runtime-lifecycle" / "parts" / "start-stop" / "README.md",
        Path("mechanics") / "config-projection" / "parts" / "bootstrap" / "docs" / "SECRETS_BOOTSTRAP.md",
        *profile_topology.ACTIVE_ROUTE_PROFILE_DOCS,
    ):
        copy_current_surface(relative_path, into=repo_root)


def run_all_profile_validators(repo_root: Path) -> list[str]:
    errors: list[str] = []
    profile_topology.validate_profiles(errors, root=repo_root)
    profile_topology.validate_presets(errors, root=repo_root)
    return errors


def test_current_repo_profile_topology_module_passes() -> None:
    assert run_all_profile_validators(REPO_ROOT) == []


def test_profile_module_requirements_stay_explicit(tmp_path: Path) -> None:
    copy_current_profile_surface(tmp_path)
    profile_path = tmp_path / profile_topology.PROFILE_DIR / "intel-worker.txt"
    write_text(
        profile_path,
        profile_path.read_text(encoding="utf-8").replace("31-intel-inference.yml\n", ""),
    )

    errors = run_all_profile_validators(tmp_path)

    assert "profile intel-worker.txt must be 32-llamacpp-inference.yml, 31-intel-inference.yml, 41-agent-api.yml, 42-agent-api-intel.yml" in errors
    assert "profile intel-worker.txt includes 42-agent-api-intel.yml but is missing required modules: 31-intel-inference.yml" in errors


def test_normal_profiles_must_not_select_llamacpp_sidecar(tmp_path: Path) -> None:
    copy_current_profile_surface(tmp_path)
    profile_path = tmp_path / profile_topology.PROFILE_DIR / "local-worker.txt"
    write_text(
        profile_path,
        profile_path.read_text(encoding="utf-8") + "44-llamacpp-agent-sidecar.yml\n",
    )

    errors = run_all_profile_validators(tmp_path)

    assert "profile local-worker.txt must not include 44-llamacpp-agent-sidecar.yml; route it through the inference-pilot sidecar" in errors


def test_n8n_task_runner_image_must_stay_digest_pinned(tmp_path: Path) -> None:
    copy_current_profile_surface(tmp_path)
    module_path = tmp_path / profile_topology.MODULE_DIR / "20-orchestration.yml"
    module_text = module_path.read_text(encoding="utf-8")
    write_text(module_path, module_text.replace("@sha256:", "@sha257:"))

    errors = run_all_profile_validators(tmp_path)

    assert "compose/modules/20-orchestration.yml must pin n8n-task-runners as docker.io/n8nio/runners:<version>@sha256:<digest>" in errors


def test_active_route_docs_must_not_use_core_profile(tmp_path: Path) -> None:
    copy_current_profile_surface(tmp_path)
    doc_path = tmp_path / profile_topology.ACTIVE_ROUTE_PROFILE_DOCS[0]
    write_text(doc_path, doc_path.read_text(encoding="utf-8") + "\nscripts/aoa-up --profile core\n")

    errors = run_all_profile_validators(tmp_path)

    assert (
        f"{profile_topology.ACTIVE_ROUTE_PROFILE_DOCS[0].as_posix()} must use substrate/local-worker/fallback-gateway or an explicit preset instead of --profile core"
        in errors
    )


def test_presets_must_reference_existing_profiles(tmp_path: Path) -> None:
    copy_current_profile_surface(tmp_path)
    preset_path = tmp_path / profile_topology.PRESET_DIR / "custom.txt"
    write_text(preset_path, "missing-profile\n")

    errors = run_all_profile_validators(tmp_path)

    assert "preset custom.txt references missing profile missing-profile" in errors
