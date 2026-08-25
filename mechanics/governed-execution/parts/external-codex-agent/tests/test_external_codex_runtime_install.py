from __future__ import annotations

import importlib.util
import json
import os
import resource
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


def lower_wrapper_descriptor_limit() -> None:
    _, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (16, hard_limit))


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
    (part / "external_codex_nested_evidence.py").write_text(
        "SCHEMA_VERSION = 'fixture'\n",
        encoding="utf-8",
    )
    (part / "external_codex_landing_effect.py").write_text(
        "PASS = True\n",
        encoding="utf-8",
    )
    (part / "bind_external_actor_launch.py").write_text(
        "import aoa_sdk\n"
        "with open('/dev/null', 'rb+') as null:\n"
        "    assert null.write(b'') == 0\n"
        "print('bind:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "prepare_landing_study.py").write_text(
        "import aoa_sdk\nprint('study:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "visible_incarnation_home.py").write_text(
        "import aoa_sdk\nprint('incarnation:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "external_codex_return.py").write_text(
        "import aoa_sdk\nprint('return:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "external_codex_responsibility_movement.py").write_text(
        "import aoa_sdk\nprint('stasis:' + aoa_sdk.MARKER)\n",
        encoding="utf-8",
    )
    (part / "schema_validation.py").write_text(
        "PASS = True\n",
        encoding="utf-8",
    )
    (part / "external_codex_supervisor.py").write_text(
        "PASS = True\n", encoding="utf-8"
    )
    (part / "external_codex_mount_launcher.py").write_text(
        "PASS = True\n", encoding="utf-8"
    )
    (part / "external_codex_projection.py").write_text(
        "PASS = True\n", encoding="utf-8"
    )
    (part / runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_NAME).write_text(
        json.dumps(
            {
                "schema_version": (
                    runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_SCHEMA_VERSION
                ),
                "catalog_id": "fixture-empty-default",
                "captured_at": "2026-08-13T00:00:00Z",
                "entries": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(
        PART_ROOT / "external_codex_static_bootstrap.S",
        part / "external_codex_static_bootstrap.S",
    )
    shutil.copyfile(
        PART_ROOT / runtime_install.CAPABILITY_CLASS_REGISTRY_NAME,
        part / runtime_install.CAPABILITY_CLASS_REGISTRY_NAME,
    )
    profile_path = part / "runtime-profile.v1.json"
    (schemas / "external-codex-test.schema.json").write_text("{}\n", encoding="utf-8")
    (schemas / "external-codex-actor-input-envelope.schema.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    for schema_name in (
        "external-codex-holder-terminal-join.schema.json",
        "external-codex-holder-terminal-closure-authorization.schema.json",
        "external-codex-holder-terminal-closure.schema.json",
    ):
        (schemas / schema_name).write_text("{}\n", encoding="utf-8")
    shutil.copyfile(
        PART_ROOT / "schemas" / "external-codex-capability-classes.schema.json",
        schemas / "external-codex-capability-classes.schema.json",
    )
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


def artifact_gate_payload(
    release_root: Path,
    source_ref: str,
    *,
    admitted_subject_digest: str | None = None,
) -> dict[str, object]:
    artifact_subjects_digest = (
        admitted_subject_digest
        or runtime_install.release_artifact_subject_digest(release_root)
    )
    signed_subject_digest = "sha256:" + "b" * 64
    record_id = runtime_install.sha256_bytes(
        runtime_install.canonical_bytes(
            {
                "artifact_class": runtime_install.ARTIFACT_CLASS,
                "subject_digest": signed_subject_digest,
                "bundle_manifest_ref": runtime_install.ARTIFACT_BUNDLE_MANIFEST_REF,
            }
        )
    )
    record = {
        "record_id": record_id,
        "artifact_class": runtime_install.ARTIFACT_CLASS,
        "artifact_subjects_digest": artifact_subjects_digest,
        "subject_digest": signed_subject_digest,
        "bundle_manifest_ref": runtime_install.ARTIFACT_BUNDLE_MANIFEST_REF,
        "source_repo": runtime_install.ARTIFACT_SOURCE_REPO,
        "source_ref": source_ref,
        "trust_root_mode": runtime_install.ARTIFACT_TRUST_ROOT_MODE,
        "lifecycle_state": "manually-verified",
        "latest_eligible": True,
        "terminal_state": False,
        "verification_ok": True,
        "required_controls": sorted(runtime_install.ARTIFACT_REQUIRED_CONTROLS),
        "verified_controls": sorted(runtime_install.ARTIFACT_REQUIRED_CONTROLS),
    }
    return {
        "ok": True,
        "schema": runtime_install.ARTIFACT_GATE_SCHEMA_VERSION,
        "verdict": "allow",
        "decision": {
            "allow": True,
            "verdict": "allow",
            "consumer_intent": runtime_install.ARTIFACT_CONSUMER_INTENT,
            "blockers": [],
            "manual_review": [],
        },
        "artifact_class": runtime_install.ARTIFACT_CLASS,
        "consumer_intent": runtime_install.ARTIFACT_CONSUMER_INTENT,
        "subject_digest": artifact_subjects_digest,
        "record_id": record_id,
        "latest_record_id": record_id,
        "blockers": [],
        "manual_review": [],
        "warnings": [],
        "record": record,
        "inspected_claims": {
            "registry_latest": {"selected_record_is_latest": True},
            "subject_identity": {"subject_digest_matched": True},
            "source": {
                "source_repo_matched": True,
                "source_ref_matched": True,
            },
            "trust_root": {"trust_root_mode_matched": True},
            "artifact_subject_store": {
                "ok": True,
                "aggregate_digest": artifact_subjects_digest,
            },
            "verification": {"ok": True},
        },
    }


def test_release_identity_covers_wrapper_bootstrap_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_material = runtime_install.wrapper_material_text
    baseline = runtime_install.release_manifest([])
    monkeypatch.setattr(
        runtime_install,
        "wrapper_material_text",
        lambda entrypoint: original_material(entrypoint) + "# material drift\n",
    )

    changed = runtime_install.release_manifest([])

    assert changed["release_id"] != baseline["release_id"]
    assert changed["release_digest"] != baseline["release_digest"]


def test_stage_seals_operator_legacy_migration_catalog_into_release(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    catalog = tmp_path / "operator-legacy-catalog.json"
    value = {
        "schema_version": runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_SCHEMA_VERSION,
        "catalog_id": "host-pre-upgrade-inventory",
        "captured_at": "2026-08-13T12:00:00Z",
        "entries": [
            {
                "session_id": "legacy-session",
                "launch_id": "launch:legacy-session",
                "launch_digest": "sha256:" + "1" * 64,
                "owner_admission_digest": "sha256:" + "2" * 64,
                "owner_request_ref": "task://legacy/owner-request",
            }
        ],
    }
    catalog.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    result = runtime_install.stage(
        source,
        sdk,
        agents,
        skills,
        tmp_path / "runtime",
        Path(sys.executable),
        legacy_owner_migration_catalog=catalog,
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )

    release = Path(result["staged"]["release_root"])
    sealed = release / "runtime" / runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_NAME
    assert sealed.read_bytes() == catalog.read_bytes()
    assert runtime_install.verify_release(release)["release_id"] == result["staged"][
        "release_id"
    ]


def test_catalog_bearing_release_requires_artifact_admitted_activation(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    catalog = tmp_path / "operator-legacy-catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": (
                    runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_SCHEMA_VERSION
                ),
                "catalog_id": "host-pre-upgrade-inventory",
                "captured_at": "2026-08-13T12:00:00Z",
                "entries": [
                    {
                        "session_id": "legacy-session",
                        "launch_id": "launch:legacy-session",
                        "launch_digest": "sha256:" + "1" * 64,
                        "owner_admission_digest": "sha256:" + "2" * 64,
                        "owner_request_ref": "task://legacy/owner-request",
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    staged_result = runtime_install.stage(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        Path(sys.executable),
        legacy_owner_migration_catalog=catalog,
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    staged = staged_result["staged"]

    with pytest.raises(
        runtime_install.InstallError,
        match="requires activate-admitted artifact trust",
    ):
        runtime_install.activate(
            runtime_root,
            bin_dir,
            str(staged["release_id"]),
            Path(sys.executable),
        )
    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()

    release_root = Path(staged["release_root"])
    registry = tmp_path / "registry"
    registry.mkdir()
    gate = tmp_path / "abyss-machine"
    write_artifact_gate(
        gate,
        artifact_gate_payload(release_root, str(staged["source"]["head"])),
    )
    activated = runtime_install.activate_admitted(
        runtime_root,
        bin_dir,
        str(staged["release_id"]),
        Path(sys.executable),
        gate,
        registry,
    )
    assert activated["active"]["legacy_owner_migration_catalog"][
        "entry_count"
    ] == 1
    assert activated["active"]["artifact_admission"] is not None


def test_ordinary_install_refuses_nonempty_authored_catalog(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    catalog = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent"
        / runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_NAME
    )
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    payload["catalog_id"] = "unadmitted-authored-inventory"
    payload["entries"] = [
        {
            "session_id": "rewritten-session",
            "launch_id": "launch:rewritten-session",
            "launch_digest": "sha256:" + "3" * 64,
            "owner_admission_digest": "sha256:" + "4" * 64,
            "owner_request_ref": "task://rewritten/owner-request",
        }
    ]
    catalog.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    commit_all(source)

    with pytest.raises(
        runtime_install.InstallError,
        match="ordinary install refuses a catalog-bearing release",
    ):
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
    assert not (tmp_path / "runtime/active.json").exists()
    assert not (tmp_path / "bin").exists()


def test_stage_rejects_ambiguous_legacy_migration_catalog(tmp_path: Path) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    entry = {
        "session_id": "legacy-session",
        "launch_id": "launch:legacy-session",
        "launch_digest": "sha256:" + "1" * 64,
        "owner_admission_digest": "sha256:" + "2" * 64,
        "owner_request_ref": "task://legacy/owner-request",
    }
    catalog = tmp_path / "ambiguous-catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema_version": (
                    runtime_install.LEGACY_OWNER_MIGRATION_CATALOG_SCHEMA_VERSION
                ),
                "catalog_id": "ambiguous",
                "captured_at": "2026-08-13T12:00:00Z",
                "entries": [entry, entry],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        runtime_install.InstallError,
        match="session identities must be unique",
    ):
        runtime_install.stage(
            source,
            sdk,
            agents,
            skills,
            tmp_path / "runtime",
            Path(sys.executable),
            legacy_owner_migration_catalog=catalog,
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )


def test_wrapper_snapshot_avoids_per_file_permission_arguments() -> None:
    bootstrap = runtime_install.wrapper_bootstrap_text(
        Path("/runtime/active.json"),
        "agent-entrypoint.py",
        "sha256:" + "1" * 64,
    )

    assert '"--ro-bind-data"' in bootstrap
    assert '"0444"' not in bootstrap


def make_specialized_environment_sources(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    source, sdk, agents, skills = make_sources(tmp_path)
    stats = tmp_path / "aoa-stats"
    make_repo(stats)
    (stats / "validator.py").write_text("OWNER = 'aoa-stats'\n", encoding="utf-8")
    commit_all(stats)
    stats_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stats,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    validation_python = tmp_path / "validation-pythonpath"
    package = validation_python / "pytest"
    metadata = validation_python / "pytest-1.0.dist-info"
    package.mkdir(parents=True)
    metadata.mkdir(parents=True)
    (package / "__init__.py").write_text("VERSION = '1.0'\n", encoding="utf-8")
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: pytest\nVersion: 1.0\n",
        encoding="utf-8",
    )

    profile_path = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["tool_profiles"] = [
        {
            "profile_id": "test/landing",
            "specialized_environment": {
                "environment_id": "test/landing-validation-v1",
                "pythonpath_ref": "environments/landing-validation-v1/pythonpath",
                "sdk_pythonpath_ref": "sdk/src",
                "python_packages": [
                    {
                        "distribution": "pytest",
                        "version": "1.0",
                        "paths": ["pytest", "pytest-1.0.dist-info"],
                    }
                ],
                "owner_roots": [
                    {
                        "owner_repo": "aoa-stats",
                        "source_ref": stats_head,
                        "root_ref": "owners/aoa-stats",
                        "environment_variable": "AOA_STATS_ROOT",
                        "access": "read_only",
                    }
                ],
                "environment_variables": {
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1",
                    "PYTEST_ADDOPTS": "-p no:cacheprovider",
                },
            },
        }
    ]
    profile_path.write_text(json.dumps(profile, sort_keys=True) + "\n", encoding="utf-8")
    commit_all(source)
    return source, sdk, agents, skills, stats, validation_python


def stage_specialized_environment(
    source: Path,
    sdk: Path,
    agents: Path,
    skills: Path,
    stats: Path,
    validation_python: Path,
    runtime_root: Path,
) -> dict[str, object]:
    return runtime_install.stage(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        Path(sys.executable),
        stats_root=stats,
        validation_python_root=validation_python,
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )


def test_stage_packages_profile_bound_specialized_environment(tmp_path: Path) -> None:
    source, sdk, agents, skills, stats, validation_python = (
        make_specialized_environment_sources(tmp_path)
    )
    stats_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=stats,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = stage_specialized_environment(
        source,
        sdk,
        agents,
        skills,
        stats,
        validation_python,
        tmp_path / "runtime",
    )

    release = Path(result["staged"]["release_root"])
    assert (release / "environments/landing-validation-v1/pythonpath/pytest/__init__.py").is_file()
    assert (release / "sdk/src/aoa_sdk/__init__.py").is_file()
    assert (release / "owners/aoa-stats/validator.py").is_file()
    assert result["staged"]["stats"]["head"] == stats_head
    assert result["staged"]["nonproduction_dirty_source"] is False


def test_stage_refuses_missing_specialized_environment_inputs(tmp_path: Path) -> None:
    source, sdk, agents, skills, _, _ = make_specialized_environment_sources(tmp_path)

    with pytest.raises(
        runtime_install.InstallError,
        match="requires --stats-root and --validation-python-root",
    ):
        runtime_install.stage(
            source,
            sdk,
            agents,
            skills,
            tmp_path / "runtime",
            Path(sys.executable),
            allow_dirty_source=False,
            allow_dirty_sdk=False,
            allow_dirty_agents=False,
            allow_dirty_skills=False,
        )


def test_stage_refuses_drifted_specialized_sdk_python_path(tmp_path: Path) -> None:
    source, sdk, agents, skills, stats, validation_python = (
        make_specialized_environment_sources(tmp_path)
    )
    profile_path = (
        source
        / "mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json"
    )
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["tool_profiles"][0]["specialized_environment"][
        "sdk_pythonpath_ref"
    ] = "sdk/other"
    profile_path.write_text(json.dumps(profile, sort_keys=True) + "\n", encoding="utf-8")
    commit_all(source)

    with pytest.raises(
        runtime_install.InstallError,
        match="SDK Python path is invalid",
    ):
        stage_specialized_environment(
            source,
            sdk,
            agents,
            skills,
            stats,
            validation_python,
            tmp_path / "runtime",
        )


def test_stage_refuses_specialized_python_package_drift(tmp_path: Path) -> None:
    source, sdk, agents, skills, stats, validation_python = (
        make_specialized_environment_sources(tmp_path)
    )
    metadata = validation_python / "pytest-1.0.dist-info/METADATA"
    metadata.write_text(
        "Metadata-Version: 2.4\nName: pytest\nVersion: 2.0\n",
        encoding="utf-8",
    )

    with pytest.raises(
        runtime_install.InstallError,
        match="Python package differs from profile pin",
    ):
        stage_specialized_environment(
            source,
            sdk,
            agents,
            skills,
            stats,
            validation_python,
            tmp_path / "runtime",
        )


def test_stage_refuses_dirty_specialized_owner_snapshot(tmp_path: Path) -> None:
    source, sdk, agents, skills, stats, validation_python = (
        make_specialized_environment_sources(tmp_path)
    )
    (stats / "validator.py").write_text("OWNER = 'dirty'\n", encoding="utf-8")

    with pytest.raises(
        runtime_install.InstallError,
        match="aoa-stats source must be clean",
    ):
        stage_specialized_environment(
            source,
            sdk,
            agents,
            skills,
            stats,
            validation_python,
            tmp_path / "runtime",
        )


def write_artifact_gate(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        "#!/usr/bin/python3\n"
        "import json\n"
        f"print(json.dumps({payload!r}, sort_keys=True))\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


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
    assert (
        runtime_install.verify_release(release_root)["release_id"]
        == active["release_id"]
    )
    status = runtime_install.status(runtime_root, bin_dir)
    assert status["healthy"] is True
    assert status["artifact_admission"]["status"] == "not_recorded"
    assert (release_root / "runtime/schema_validation.py").is_file()
    for relative in runtime_install.SDK_CONTRACT_FILES:
        assert (release_root / "sdk" / relative).is_file()
    for owner, relative in runtime_install.OWNER_CONTRACT_FILES:
        assert (release_root / "owners" / owner / relative).is_file()
    for schema_name in (
        "external-codex-actor-input-envelope.schema.json",
        "external-codex-holder-terminal-join.schema.json",
        "external-codex-holder-terminal-closure-authorization.schema.json",
        "external-codex-holder-terminal-closure.schema.json",
        "external-codex-capability-classes.schema.json",
    ):
        assert (release_root / "runtime/schemas" / schema_name).is_file()
    assert (
        release_root / "runtime" / runtime_install.CAPABILITY_CLASS_REGISTRY_NAME
    ).is_file()
    for directory in (release_root / "sdk/src").rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    ambient = tmp_path / "ambient-python"
    ambient_bin = ambient / "bin"
    ambient_bin.mkdir(parents=True)
    path_marker = tmp_path / "ambient-python-path-ran"
    path_python = ambient_bin / "python3"
    path_python.write_text(
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(path_marker))}\nexit 97\n",
        encoding="utf-8",
    )
    path_python.chmod(0o700)
    import_marker = tmp_path / "ambient-pythonpath-ran"
    (ambient / "json.py").write_text(
        f"open({str(import_marker)!r}, 'w', encoding='utf-8').write('ran\\n')\n",
        encoding="utf-8",
    )
    ambient_environment = dict(os.environ)
    preload_marker = tmp_path / "ambient-loader-ran"
    preload_source = tmp_path / "ambient-loader.c"
    preload_library = tmp_path / "ambient-loader.so"
    preload_source.write_text(
        "#include <fcntl.h>\n"
        "#include <unistd.h>\n"
        "__attribute__((constructor)) static void injected(void) {\n"
        f"  int fd = open({json.dumps(str(preload_marker))}, "
        "O_WRONLY | O_CREAT | O_APPEND, 0600);\n"
        '  if (fd >= 0) { (void)write(fd, "ran\\n", 4); (void)close(fd); }\n'
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            "/usr/bin/cc",
            "-shared",
            "-fPIC",
            "-o",
            str(preload_library),
            str(preload_source),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    ambient_environment.update(
        {
            "LD_PRELOAD": str(preload_library),
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
        preexec_fn=lower_wrapper_descriptor_limit,
    )
    assert completed.stdout == "agent:exact-sdk\n"
    assert path_marker.exists() is False
    assert import_marker.exists() is False
    assert preload_marker.exists() is False
    launcher = bin_dir / "aoa-external-codex-agent"
    assert launcher.read_bytes().startswith(b"\x7fELF")
    assert b".bootstrap.py" not in launcher.read_bytes()
    runtime_install.validate_static_wrapper(launcher.read_bytes())
    companion = Path(str(launcher) + ".bootstrap.py")
    assert companion.exists() is False
    assert status["wrappers"]["aoa-external-codex-agent"]["bootstrap_transport"] == (
        "embedded_elf_rodata"
    )
    assert status["wrappers"]["aoa-external-codex-agent"]["bootstrap_path"] is None
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
    incarnation = subprocess.run(
        [str(bin_dir / "aoa-external-codex-incarnation")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert incarnation.stdout == "incarnation:exact-sdk\n"
    actor_return = subprocess.run(
        [str(bin_dir / "aoa-external-codex-return")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert actor_return.stdout == "return:exact-sdk\n"
    stasis = subprocess.run(
        [str(bin_dir / "aoa-external-codex-stasis")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert stasis.stdout == "stasis:exact-sdk\n"
    study = subprocess.run(
        [str(bin_dir / "aoa-external-codex-study")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert study.stdout == "study:exact-sdk\n"
    assert not list(release_root.rglob("__pycache__"))

    replacement_marker = tmp_path / "replacement-companion-ran"
    companion.write_text(
        f"open({str(replacement_marker)!r}, 'w').write('ran')\n",
        encoding="utf-8",
    )
    companion.chmod(0o755)
    replacement_attempt = subprocess.run(
        [str(launcher)],
        check=True,
        capture_output=True,
        text=True,
        env=ambient_environment,
        preexec_fn=lower_wrapper_descriptor_limit,
    )
    assert replacement_attempt.stdout == "agent:exact-sdk\n"
    assert replacement_marker.exists() is False

    active_path = runtime_root / "active.json"
    active_raw = active_path.read_bytes()
    active_path.write_bytes(active_raw + b"\n")
    drifted_active_attempt = subprocess.run(
        [str(launcher)],
        check=False,
        capture_output=True,
        text=True,
        env=ambient_environment,
        preexec_fn=lower_wrapper_descriptor_limit,
    )
    assert drifted_active_attempt.returncode != 0
    assert "active release identity drift" in drifted_active_attempt.stderr
    active_path.write_bytes(active_raw)

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


def test_wrapper_set_follows_legacy_release_contents(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir()
    for entrypoint in (
        "agent-entrypoint.py",
        "bind-entrypoint.py",
        "study-entrypoint.py",
    ):
        (release_root / entrypoint).write_text("#!/bin/false\n", encoding="utf-8")

    legacy = runtime_install.wrapper_specs_for_release(release_root)

    assert set(legacy) == {
        "aoa-external-codex-agent",
        "aoa-external-actor-bind",
        "aoa-external-codex-study",
    }
    assert "aoa-external-codex-incarnation" not in legacy

    (release_root / "incarnation-entrypoint.py").write_text(
        "#!/bin/false\n", encoding="utf-8"
    )
    current = runtime_install.wrapper_specs_for_release(release_root)

    assert "aoa-external-codex-incarnation" in current


def test_stage_then_artifact_admitted_activation_is_fail_closed(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    staged_result = runtime_install.stage(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    staged = staged_result["staged"]
    release_root = Path(staged["release_root"])
    source_ref = str(staged["source"]["head"])
    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()
    assert Path(staged_result["staged_record"]).stat().st_mode & 0o777 == 0o444

    registry = tmp_path / "registry"
    registry.mkdir()
    gate = tmp_path / "abyss-machine"
    write_artifact_gate(gate, artifact_gate_payload(release_root, source_ref))
    activated = runtime_install.activate_admitted(
        runtime_root,
        bin_dir,
        str(staged["release_id"]),
        Path(sys.executable),
        gate,
        registry,
    )

    active = activated["active"]
    admission = active["artifact_admission"]
    assert activated["operation"] == "activate-admitted"
    assert active["nonproduction_dirty_source"] is False
    assert admission["artifact_subjects_digest"] == (
        runtime_install.release_artifact_subject_digest(release_root)
    )
    assert admission["gate"]["verdict"] == "allow"
    assert admission["gate_command"][1:3] == ["artifacts", "trust-gate"]
    status = runtime_install.status(runtime_root, bin_dir)
    assert status["healthy"] is True
    assert status["artifact_admission"]["status"] == "recorded_and_bound"


def test_artifact_admitted_activation_rejects_unbound_subject_before_publication(
    tmp_path: Path,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    staged_result = runtime_install.stage(
        source,
        sdk,
        agents,
        skills,
        runtime_root,
        Path(sys.executable),
        allow_dirty_source=False,
        allow_dirty_sdk=False,
        allow_dirty_agents=False,
        allow_dirty_skills=False,
    )
    staged = staged_result["staged"]
    release_root = Path(staged["release_root"])
    source_ref = str(staged["source"]["head"])
    registry = tmp_path / "registry"
    registry.mkdir()
    gate = tmp_path / "abyss-machine"
    write_artifact_gate(
        gate,
        artifact_gate_payload(
            release_root,
            source_ref,
            admitted_subject_digest="sha256:" + "c" * 64,
        ),
    )

    with pytest.raises(
        runtime_install.InstallError,
        match="does not bind the staged release",
    ):
        runtime_install.activate_admitted(
            runtime_root,
            bin_dir,
            str(staged["release_id"]),
            Path(sys.executable),
            gate,
            registry,
        )

    assert not (runtime_root / "active.json").exists()
    assert not bin_dir.exists()


def test_activate_release_without_packaged_static_source_uses_rollback_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, sdk, agents, skills = make_sources(tmp_path)
    runtime_root = tmp_path / "runtime"
    bin_dir = tmp_path / "bin"
    current_runtime_files = runtime_install.RUNTIME_FILES
    monkeypatch.setattr(
        runtime_install,
        "RUNTIME_FILES",
        tuple(
            name
            for name in current_runtime_files
            if name != "external_codex_static_bootstrap.S"
        ),
    )
    legacy = runtime_install.install(
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
    monkeypatch.setattr(runtime_install, "RUNTIME_FILES", current_runtime_files)
    current = runtime_install.install(
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
    assert current["active"]["release_id"] != legacy["active"]["release_id"]

    activated = runtime_install.activate(
        runtime_root,
        bin_dir,
        legacy["active"]["release_id"],
        Path(sys.executable),
    )

    assert activated["active"]["release_id"] == legacy["active"]["release_id"]
    assert runtime_install.status(runtime_root, bin_dir)["healthy"] is True
    completed = subprocess.run(
        [str(bin_dir / "aoa-external-codex-agent")],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout == "agent:exact-sdk\n"


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

    assert (
        json.loads(active_path.read_text(encoding="utf-8"))["python_executable"]
        == (first["active"]["python_executable"])
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

    assert activated["active"]["python_executable"] == str(alternate_python.resolve())
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
    assert (
        subprocess.run(
            [str(bin_dir / "aoa-external-codex-agent")],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == "agent:exact-sdk\n"
    )
    marker = tmp_path / "replacement-python-ran"
    selected_python.write_text(
        "#!/bin/sh\n"
        f"/usr/bin/touch {shlex.quote(str(marker))}\n"
        f'exec {shlex.quote(str(real_python))} "$@"\n',
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
        f'#!/bin/sh\nexec {shlex.quote(str(real_python))} "$@"\n',
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
                f'#!/bin/sh\nexec {shlex.quote(str(real_python))} -B "$@"\n',
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
        source / "mechanics/governed-execution/parts/external-codex-agent/"
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
    assert ready.exists(), (
        f"snapshot actor did not become ready; returncode={process.poll()}"
    )
    installed_release = Path(receipt["active"]["release_root"])
    moved_release = installed_release.with_name(installed_release.name + "-host-moved")
    os.replace(installed_release, moved_release)
    installed_release.mkdir()
    (installed_release / "sdk/src/aoa_sdk").mkdir(parents=True)
    (installed_release / "sdk/src/aoa_sdk/deferred.py").write_text(
        "MARKER = 'replacement-host-release'\n",
        encoding="utf-8",
    )
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
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(filter_marker))}\n/bin/cat\n",
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
        source / "mechanics/governed-execution/parts/external-codex-agent/"
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
        f"#!/bin/sh\n/usr/bin/touch {shlex.quote(str(marker))}\n/bin/cat\n",
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
        source / "mechanics/governed-execution/parts/external-codex-agent/"
        "external_codex_agent.py"
    )
    controller.write_text(
        controller.read_text(encoding="utf-8") + "# late-filter drift\n",
        encoding="utf-8",
    )
    original_run = subprocess.run
    mutation_observed = False

    def mutate_before_status(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess:
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
        source / "mechanics/governed-execution/parts/external-codex-agent/"
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


def test_dirty_source_requires_explicit_admission_and_preserves_rollback(
    tmp_path: Path,
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
    assert (
        json.loads((runtime_root / "active.json").read_text())["release_id"]
        == first["active"]["release_id"]
    )


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
    controller.write_text(
        controller.read_text() + "# hidden change\n", encoding="utf-8"
    )

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
    (sdk / ".gitignore").write_text(
        "src/aoa_sdk/local_generated.py\n", encoding="utf-8"
    )
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
        Path(receipt["active"]["release_root"]) / "sdk/src/aoa_sdk/local_generated.py"
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
