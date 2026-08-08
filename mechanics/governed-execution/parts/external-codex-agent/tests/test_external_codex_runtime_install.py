from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "external_codex_runtime_install",
    PART_ROOT / "install_external_codex_runtime.py",
)
assert SPEC and SPEC.loader
runtime_install = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_install)


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(path: Path) -> None:
    path.mkdir(parents=True)
    git("init", "-q", cwd=path)
    git("config", "user.name", "Runtime Test", cwd=path)
    git("config", "user.email", "runtime-test@example.invalid", cwd=path)


def commit_all(path: Path) -> None:
    git("add", ".", cwd=path)
    git("commit", "-qm", "fixture", cwd=path)


def make_sources(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    source = tmp_path / "abyss-stack"
    sdk = tmp_path / "aoa-sdk"
    agents = tmp_path / "aoa-agents"
    skills = tmp_path / "aoa-skills"
    make_repo(source)
    make_repo(sdk)
    make_repo(agents)
    make_repo(skills)
    part = source / "mechanics/governed-execution/parts/external-codex-agent"
    schemas = part / "schemas"
    schemas.mkdir(parents=True)
    (part / "external_codex_agent.py").write_text(
        "import aoa_sdk\nprint('agent:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "bind_external_actor_launch.py").write_text(
        "import aoa_sdk\nprint('bind:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "prepare_landing_study.py").write_text(
        "import aoa_sdk\nprint('study:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "external_codex_supervisor.py").write_text("PASS = True\n", encoding="utf-8")
    profile_path = part / "runtime-profile.v1.json"
    (schemas / "external-codex-test.schema.json").write_text("{}\n", encoding="utf-8")
    package = sdk / "src/aoa_sdk"
    (package / "contracts").mkdir(parents=True)
    (package / "__init__.py").write_text("MARKER = 'exact-sdk'\n", encoding="utf-8")
    (package / "contracts/__init__.py").write_text("", encoding="utf-8")
    (package / "contracts/incarnation.py").write_text("ABI = 1\n", encoding="utf-8")
    for relative in runtime_install.SDK_CONTRACT_FILES:
        contract = sdk / relative
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text("{}\n", encoding="utf-8")
    owner_roots = {"aoa-agents": agents, "aoa-skills": skills}
    for owner, relative in runtime_install.OWNER_CONTRACT_FILES:
        contract = owner_roots[owner] / relative
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text("{}\n", encoding="utf-8")
    profile_path.write_text(
        json.dumps(
            {
                "owner_contracts": {
                    "owner_execution_request_schema": {
                        "owner_repo": "aoa-agents",
                        "artifact_ref": runtime_install.OWNER_CONTRACT_FILES[0][1],
                        "digest": runtime_install.sha256_file(
                            agents / runtime_install.OWNER_CONTRACT_FILES[0][1]
                        ),
                    },
                    "task_local_dag_schema": {
                        "owner_repo": "aoa-skills",
                        "artifact_ref": runtime_install.OWNER_CONTRACT_FILES[1][1],
                        "digest": runtime_install.sha256_file(
                            skills / runtime_install.OWNER_CONTRACT_FILES[1][1]
                        ),
                    },
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    commit_all(source)
    commit_all(sdk)
    commit_all(agents)
    commit_all(skills)
    return source, sdk, agents, skills


def test_content_addressed_install_and_wrapper_use_exact_sdk(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"

    receipt = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )

    active = receipt["active"]
    release_root = Path(active["release_root"])
    assert active["nonproduction_dirty_source"] is False
    assert release_root.name == active["release_id"]
    assert runtime_install.verify_release(release_root)["release_id"] == active["release_id"]
    assert runtime_install.status(runtime_root, bin_dir)["healthy"] is True
    for relative in runtime_install.SDK_CONTRACT_FILES:
        assert (release_root / "sdk" / relative).is_file()
    for owner, relative in runtime_install.OWNER_CONTRACT_FILES:
        assert (release_root / "owners" / owner / relative).is_file()
    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == "agent:exact-sdk\n"
    bound = subprocess.run(
        [str(bin_dir / "aoa-external-actor-bind")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert bound.stdout == "bind:exact-sdk\n"
    study = subprocess.run(
        [str(bin_dir / "aoa-external-codex-study")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert study.stdout == "study:exact-sdk\n"

    repeated = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    assert repeated["release_created"] is False
    assert repeated["active"]["release_id"] == active["release_id"]


def test_dirty_source_requires_explicit_admission_and_preserves_rollback(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    first = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py"
    )
    controller.write_text(controller.read_text() + "# changed\n", encoding="utf-8")

    with pytest.raises(runtime_install.InstallError, match="--allow-dirty-source"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            runtime_root,
            bin_dir,
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )

    second = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=True,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    assert second["active"]["nonproduction_dirty_source"] is True
    assert second["active"]["previous_release_id"] == first["active"]["release_id"]
    assert second["active"]["release_id"] != first["active"]["release_id"]

    restored = runtime_install.activate(
        runtime_root,
        bin_dir,
        first["active"]["release_id"],
        Path(sys.executable),
    )
    assert restored["active"]["release_id"] == first["active"]["release_id"]
    assert json.loads((runtime_root / "active.json").read_text())["release_id"] == first["active"]["release_id"]


@pytest.mark.parametrize("index_flag", ["--assume-unchanged", "--skip-worktree"])
def test_hidden_index_posture_requires_explicit_source_admission(
    tmp_path: Path,
    index_flag: str,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py"
    )
    git("update-index", index_flag, str(controller.relative_to(source)), cwd=source)
    controller.write_text(controller.read_text() + "# hidden change\n", encoding="utf-8")

    with pytest.raises(runtime_install.InstallError, match="--allow-dirty-source"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            tmp_path / "runtime",
            tmp_path / "bin",
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )

    receipt = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        tmp_path / "runtime",
        tmp_path / "bin",
        Path(sys.executable),
        allow_dirty_source=True,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    assert receipt["active"]["nonproduction_dirty_source"] is True
    assert receipt["active"]["source"]["packaged_index_flag_count"] == 1


def test_ignored_packaged_sdk_file_requires_explicit_admission(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    (sdk / ".gitignore").write_text("src/aoa_sdk/local_generated.py\n", encoding="utf-8")
    commit_all(sdk)
    ignored = sdk / "src/aoa_sdk/local_generated.py"
    ignored.write_text("LOCAL = True\n", encoding="utf-8")

    with pytest.raises(runtime_install.InstallError, match="--allow-dirty-sdk"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            tmp_path / "runtime",
            tmp_path / "bin",
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )

    receipt = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        tmp_path / "runtime",
        tmp_path / "bin",
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=True,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    assert receipt["active"]["nonproduction_dirty_source"] is True
    assert receipt["active"]["sdk"]["ignored_packaged_file_count"] == 1
    assert (
        Path(receipt["active"]["release_root"])
        / "sdk/src/aoa_sdk/local_generated.py"
    ).is_file()


def test_install_rejects_owner_contract_outside_runtime_profile_pin(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    contract = agents / runtime_install.OWNER_CONTRACT_FILES[0][1]
    contract.write_text('{"changed":true}\n', encoding="utf-8")
    commit_all(agents)

    with pytest.raises(runtime_install.InstallError, match="runtime profile pin"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            tmp_path / "runtime",
            tmp_path / "bin",
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )


def test_install_and_status_reject_non_executable_python(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    non_executable = tmp_path / "python-without-execute-bit"
    non_executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    non_executable.chmod(0o644)

    with pytest.raises(runtime_install.InstallError, match="not executable"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            runtime_root,
            bin_dir,
            non_executable,
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )
    assert not (runtime_root / "active.json").exists()

    runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    active_path = runtime_root / "active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    active["python_executable"] = str(non_executable)
    active_path.write_text(
        json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(runtime_install.InstallError, match="not executable"):
        runtime_install.status(runtime_root, bin_dir)


def test_install_and_status_reject_executable_non_python(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    non_python = Path("/bin/true")

    with pytest.raises(runtime_install.InstallError, match="compatibility probe"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            runtime_root,
            bin_dir,
            non_python,
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )
    assert not (runtime_root / "active.json").exists()

    runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    active_path = runtime_root / "active.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    active["python_executable"] = str(non_python)
    active_path.write_text(
        json.dumps(active, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(runtime_install.InstallError, match="compatibility probe"):
        runtime_install.status(runtime_root, bin_dir)


@pytest.mark.parametrize("release_id", ["../../outside", "sha256-" + "g" * 64])
def test_activate_rejects_non_content_addressed_release_id(
    tmp_path: Path,
    release_id: str,
) -> None:
    runtime_root = tmp_path / "runtime"
    (runtime_root / "releases").mkdir(parents=True)

    with pytest.raises(runtime_install.InstallError, match="content address"):
        runtime_install.activate(
            runtime_root,
            tmp_path / "bin",
            release_id,
            Path(sys.executable),
        )
