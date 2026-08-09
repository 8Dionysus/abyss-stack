from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
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
    for directory in (release_root / "sdk/src").rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    ambient = tmp_path / "ambient-python"
    ambient_bin = ambient / "bin"
    ambient_bin.mkdir(parents=True)
    path_marker = tmp_path / "ambient-python-path-ran"
    path_python = ambient_bin / "python3"
    path_python.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(path_marker))}\n"
        "exit 97\n",
        encoding="utf-8",
    )
    path_python.chmod(0o700)
    import_marker = tmp_path / "ambient-pythonpath-ran"
    (ambient / "json.py").write_text(
        f"open({str(import_marker)!r}, 'w', encoding='utf-8').write('ran\\n')\n",
        encoding="utf-8",
    )
    ambient_environment = dict(os.environ)
    ambient_environment.update(
        {
            "PATH": f"{ambient_bin}:/usr/bin:/bin",
            "PYTHONPATH": str(ambient),
        }
    )
    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
        env=ambient_environment,
    )
    assert completed.stdout == "agent:exact-sdk\n"
    assert path_marker.exists() is False
    assert import_marker.exists() is False
    assert (bin_dir / "aoa-external-codex-agent").read_text(
        encoding="utf-8"
    ).startswith("#!/bin/sh\nexec ")
    agent_entrypoint = release_root / "agent-entrypoint.py"
    assert agent_entrypoint.read_text(encoding="utf-8").startswith("#!/bin/false\n")
    assert agent_entrypoint.stat().st_mode & 0o111 == 0
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
    assert not list(release_root.rglob("__pycache__"))

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


def test_interpreter_activation_publishes_at_active_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    alternate_python = tmp_path / "alternate-python"
    shutil.copyfile(Path(sys.executable).resolve(), alternate_python)
    alternate_python.chmod(0o700)
    active_path = runtime_root / "active.json"
    original_atomic_write = runtime_install.atomic_write

    def fail_active_publication(path: Path, content: bytes, mode: int) -> None:
        if path == active_path:
            raise runtime_install.InstallError("simulated active publication failure")
        original_atomic_write(path, content, mode)

    monkeypatch.setattr(runtime_install, "atomic_write", fail_active_publication)
    with pytest.raises(runtime_install.InstallError, match="simulated active"):
        runtime_install.activate(
            runtime_root,
            bin_dir,
            first["active"]["release_id"],
            alternate_python,
        )

    assert json.loads(active_path.read_text(encoding="utf-8"))["python_executable"] == (
        first["active"]["python_executable"]
    )
    assert runtime_install.status(runtime_root, bin_dir)["healthy"] is True
    failed_transition_run = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert failed_transition_run.stdout == "agent:exact-sdk\n"

    monkeypatch.setattr(runtime_install, "atomic_write", original_atomic_write)
    activated = runtime_install.activate(
        runtime_root,
        bin_dir,
        first["active"]["release_id"],
        alternate_python,
    )

    assert activated["active"]["python_executable"] == str(
        alternate_python.resolve()
    )
    assert runtime_install.status(runtime_root, bin_dir)["healthy"] is True
    completed_transition_run = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed_transition_run.stdout == "agent:exact-sdk\n"


def test_wrapper_rejects_release_drift_before_execution(tmp_path: Path) -> None:
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
    release_root = Path(receipt["active"]["release_root"])
    target = release_root / "runtime/external_codex_agent.py"
    marker = tmp_path / "drifted-release-ran"
    target.parent.chmod(0o755)
    target.chmod(0o644)
    target.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "release file drift" in completed.stderr
    assert marker.exists() is False


def test_wrapper_rejects_compatible_interpreter_replacement(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    real_python = Path(sys.executable).resolve()
    selected_python = tmp_path / "selected-python"
    shutil.copyfile(real_python, selected_python)
    selected_python.chmod(0o700)
    receipt = runtime_install.install(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        bin_dir,
        selected_python,
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    assert receipt["active"]["python_identity"]["sha256"].startswith("sha256:")
    assert subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == "agent:exact-sdk\n"
    marker = tmp_path / "replacement-python-ran"
    selected_python.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        f"exec {shlex.quote(str(real_python))} \"$@\"\n",
        encoding="utf-8",
    )
    selected_python.chmod(0o700)

    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "interpreter identity drift" in completed.stderr
    assert marker.exists() is False
    with pytest.raises(runtime_install.InstallError, match="identity drift"):
        runtime_install.status(runtime_root, bin_dir)


def test_install_rejects_python_shim_with_unbound_delegate(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    real_python = Path(sys.executable).resolve()
    shim = tmp_path / "python-shim"
    shim.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(str(real_python))} \"$@\"\n",
        encoding="utf-8",
    )
    shim.chmod(0o700)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"

    with pytest.raises(runtime_install.InstallError, match="direct CPython ELF"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            runtime_root,
            bin_dir,
            shim,
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )

    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()


def test_install_rejects_interpreter_drift_before_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    real_python = Path(sys.executable).resolve()
    selected_python = tmp_path / "selected-python"
    shutil.copyfile(real_python, selected_python)
    selected_python.chmod(0o700)
    original_require = runtime_install.require_python_executable
    selected_admissions = 0

    def mutate_after_initial_admission(
        path: Path,
    ) -> tuple[Path, dict[str, object]]:
        nonlocal selected_admissions
        admitted = original_require(path)
        if admitted[0] == selected_python.resolve() and selected_admissions == 0:
            selected_admissions += 1
            selected_python.write_text(
                "#!/bin/sh\n"
                f"exec {shlex.quote(str(real_python))} -B \"$@\"\n",
                encoding="utf-8",
            )
            selected_python.chmod(0o700)
        return admitted

    monkeypatch.setattr(
        runtime_install,
        "require_python_executable",
        mutate_after_initial_admission,
    )

    with pytest.raises(runtime_install.InstallError, match="changed before activation"):
        runtime_install.install(
            source,
            sdk,
            agents,
            skills,
            runtime_root,
            bin_dir,
            selected_python,
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )

    assert selected_admissions == 1
    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()


def test_wrapper_imports_from_private_verified_release_snapshot(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    deferred = sdk / "src/aoa_sdk/deferred.py"
    deferred.write_text("MARKER = 'verified-snapshot'\n", encoding="utf-8")
    commit_all(sdk)
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/"
        "external_codex_agent.py"
    )
    controller.write_text(
        "import os\n"
        "import time\n"
        "from pathlib import Path\n"
        "ready = Path(os.environ['AOA_SNAPSHOT_TEST_READY'])\n"
        "release = Path(os.environ['AOA_SNAPSHOT_TEST_RELEASE'])\n"
        "ready.write_text('ready\\n', encoding='utf-8')\n"
        "while not release.exists():\n"
        "    time.sleep(0.01)\n"
        "from aoa_sdk import deferred\n"
        "print(deferred.MARKER)\n",
        encoding="utf-8",
    )
    commit_all(source)
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
    ready = tmp_path / "snapshot-ready"
    release = tmp_path / "snapshot-release"
    environment = dict(os.environ)
    environment.update(
        {
            "AOA_SNAPSHOT_TEST_READY": str(ready),
            "AOA_SNAPSHOT_TEST_RELEASE": str(release),
        }
    )
    process = subprocess.Popen(
        [str(bin_dir / "aoa-external-codex-agent")],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    deadline = time.monotonic() + 10
    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert ready.exists(), f"snapshot actor did not become ready; returncode={process.poll()}"
    installed_deferred = (
        Path(receipt["active"]["release_root"])
        / "sdk/src/aoa_sdk/deferred.py"
    )
    installed_deferred.parent.chmod(0o755)
    installed_deferred.chmod(0o644)
    installed_deferred.write_text("MARKER = 'mutated-host-release'\n", encoding="utf-8")
    release.write_text("continue\n", encoding="utf-8")

    stdout, stderr = process.communicate(timeout=10)

    assert process.returncode == 0, stderr
    assert stdout == "verified-snapshot\n"


def test_git_posture_does_not_run_repository_fsmonitor_or_content_filter(
    tmp_path: Path,
) -> None:
    source, _sdk, _agents, _skills = make_sources(tmp_path)
    fsmonitor_marker = tmp_path / "fsmonitor-ran"
    fsmonitor = tmp_path / "fsmonitor"
    fsmonitor.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(fsmonitor_marker))}\n"
        "/usr/bin/printf '{}\\n'\n",
        encoding="utf-8",
    )
    fsmonitor.chmod(0o700)
    filter_marker = tmp_path / "filter-ran"
    filter_helper = tmp_path / "clean-filter"
    filter_helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(filter_marker))}\n"
        "/bin/cat\n",
        encoding="utf-8",
    )
    filter_helper.chmod(0o700)
    (source / ".gitattributes").write_text(
        "mechanics/** filter=leak\n",
        encoding="utf-8",
    )
    git("add", ".gitattributes", cwd=source)
    git("commit", "-qm", "attributes", cwd=source)
    git("config", "core.fsmonitor", str(fsmonitor), cwd=source)
    git("config", "filter.leak.clean", str(filter_helper), cwd=source)
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/"
        "external_codex_agent.py"
    )
    controller.write_text(
        controller.read_text(encoding="utf-8") + "# visible drift\n",
        encoding="utf-8",
    )

    posture = runtime_install.git_posture(source)

    assert posture["dirty"] is True
    assert fsmonitor_marker.exists() is False
    assert filter_marker.exists() is False


def test_git_posture_snapshot_ignores_filter_config_added_before_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _sdk, _agents, _skills = make_sources(tmp_path)
    marker = tmp_path / "late-filter-ran"
    helper = tmp_path / "late-filter"
    helper.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        "/bin/cat\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    (source / ".gitattributes").write_text(
        "mechanics/** filter=late\n",
        encoding="utf-8",
    )
    git("add", ".gitattributes", cwd=source)
    git("commit", "-qm", "late attributes", cwd=source)
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/"
        "external_codex_agent.py"
    )
    controller.write_text(
        controller.read_text(encoding="utf-8") + "# late-filter drift\n",
        encoding="utf-8",
    )
    original_run = subprocess.run
    mutation_observed = False

    def mutate_before_status(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        nonlocal mutation_observed
        argv = args[0] if args else kwargs.get("args")
        if (
            not mutation_observed
            and isinstance(argv, (list, tuple))
            and "status" in argv
        ):
            mutation_observed = True
            original_run(
                ["/usr/bin/git", "config", "filter.late.clean", str(helper)],
                cwd=source,
                check=True,
                capture_output=True,
                text=True,
            )
        return original_run(*args, **kwargs)

    monkeypatch.setattr(runtime_install.subprocess, "run", mutate_before_status)

    posture = runtime_install.git_posture(source)

    assert mutation_observed is True
    assert posture["dirty"] is True
    assert marker.exists() is False


def test_git_posture_snapshot_carries_split_index_backing_file(tmp_path: Path) -> None:
    source, _sdk, _agents, _skills = make_sources(tmp_path)
    git("update-index", "--split-index", cwd=source)
    shared_index = subprocess.run(
        ["/usr/bin/git", "rev-parse", "--shared-index-path"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    posture = runtime_install.git_posture(source)

    assert shared_index
    assert posture["dirty"] is False


def test_git_posture_snapshot_rejects_corrupt_split_index_backing(
    tmp_path: Path,
) -> None:
    source, _sdk, _agents, _skills = make_sources(tmp_path)
    git("update-index", "--split-index", cwd=source)
    shared_index = Path(
        subprocess.run(
            ["/usr/bin/git", "rev-parse", "--shared-index-path"],
            cwd=source,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if not shared_index.is_absolute():
        shared_index = source / shared_index
    payload = bytearray(shared_index.read_bytes())
    payload[16] ^= 0x01
    shared_index.write_bytes(payload)

    with pytest.raises(runtime_install.InstallError, match="digest mismatch"):
        runtime_install.git_posture(source)


def test_install_refuses_clean_checkout_race_before_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    old_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    controller = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/"
        "external_codex_agent.py"
    )
    controller.write_text(
        controller.read_text(encoding="utf-8") + "# competing clean revision\n",
        encoding="utf-8",
    )
    commit_all(source)
    new_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    git("checkout", "-q", old_head, cwd=source)
    original_release_manifest = runtime_install.release_manifest

    def release_manifest_after_checkout(
        files: list[tuple[Path, Path]],
    ) -> dict[str, object]:
        git("checkout", "-q", new_head, cwd=source)
        return original_release_manifest(files)

    monkeypatch.setattr(
        runtime_install,
        "release_manifest",
        release_manifest_after_checkout,
    )
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"

    with pytest.raises(runtime_install.InstallError, match="Git posture changed"):
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

    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()


def test_release_verification_rejects_unmanifested_importable_file(
    tmp_path: Path,
) -> None:
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
    release_root = Path(receipt["active"]["release_root"])
    injected = release_root / "sdk/src/jsonschema.py"
    injected.parent.chmod(0o755)
    injected.write_text("raise RuntimeError('unmanifested import')\n", encoding="utf-8")

    with pytest.raises(runtime_install.InstallError, match="manifest closure"):
        runtime_install.verify_release(release_root)
    with pytest.raises(runtime_install.InstallError, match="manifest closure"):
        runtime_install.status(runtime_root, bin_dir)


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
