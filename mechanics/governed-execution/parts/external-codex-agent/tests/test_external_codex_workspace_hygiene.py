from __future__ import annotations

import importlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType


PART_ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_PATH = PART_ROOT / "external_codex_agent.py"


def _load_runtime_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "abyss_stack_external_codex_workspace_hygiene", CONTROLLER_PATH
    )
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot load controller: {CONTROLLER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RUNTIME = _load_runtime_module()
PROFILE = json.loads(
    (PART_ROOT / "runtime-profile.v1.json").read_text(encoding="utf-8")
)


def _tool_profile(profile_id: str) -> dict[str, object]:
    return next(
        item for item in PROFILE["tool_profiles"] if item["profile_id"] == profile_id
    )


def _git_workspace(path: Path) -> None:
    path.mkdir()
    subprocess.run(
        ["/usr/bin/git", "init", "--quiet", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _release_root(root: Path, monkeypatch) -> Path:
    release = root / "verified-release"
    (release / "environments/landing-validation-v1/pythonpath").mkdir(
        parents=True
    )
    (release / "sdk/src").mkdir(parents=True)
    (release / "owners/aoa-stats").mkdir(parents=True)
    package_root = release / "environments/landing-validation-v1/pythonpath"
    for package_name in (
        "_pytest",
        "pytest",
        "pluggy",
        "packaging",
        "iniconfig",
        "pygments",
        "py",
    ):
        source_file = Path(importlib.import_module(package_name).__file__)
        if source_file.name == "__init__.py":
            shutil.copytree(
                source_file.parent,
                package_root / package_name,
                dirs_exist_ok=True,
            )
        else:
            shutil.copy2(source_file, package_root / source_file.name)
    monkeypatch.setenv("AOA_EXTERNAL_CODEX_VERIFIED_RELEASE_ROOT", str(release))
    return release


def _launch(workspace: Path, codex_home: Path) -> dict[str, object]:
    return {
        "environment_allowlist": [],
        "codex_home": str(codex_home),
        "workspace_path": str(workspace),
        "codex_executable": "/usr/bin/true",
    }


def _run_python_hygiene(
    workspace: Path,
    environment: dict[str, str],
    *,
    run_pytest: bool,
) -> None:
    (workspace / "imported_module.py").write_text(
        "value = 42\n",
        encoding="utf-8",
    )
    (workspace / "test_imported_module.py").write_text(
        (
            "from imported_module import value\n\n"
            "def test_value():\n"
            "    assert value == 42\n"
        ),
        encoding="utf-8",
    )
    py_compile = subprocess.run(
        [sys.executable, "-m", "py_compile", "imported_module.py"],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert py_compile.returncode == 0, py_compile.stderr
    imported = subprocess.run(
        [
            sys.executable,
            "-c",
            "import imported_module; assert imported_module.value == 42",
        ],
        cwd=workspace,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert imported.returncode == 0, imported.stderr
    if run_pytest:
        pytest_run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert pytest_run.returncode == 0, pytest_run.stdout + pytest_run.stderr


def test_all_external_profiles_keep_python_and_pytest_residue_outside_projection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "actor-projection"
    _git_workspace(workspace)
    _release_root(tmp_path, monkeypatch)
    runtime = RUNTIME.ExternalCodexRuntime(tmp_path / "state")
    launch = _launch(workspace, tmp_path / "codex-home")

    profile_ids = tuple(item["profile_id"] for item in PROFILE["tool_profiles"])
    for profile_id in profile_ids:
        scratch = tmp_path / "attempts" / profile_id.rsplit("/", 1)[-1] / "scratch"
        scratch.mkdir(parents=True)
        entry = _tool_profile(profile_id)
        environment = runtime._codex_environment(launch, scratch, entry)

        prefix = Path(environment["PYTHONPYCACHEPREFIX"])
        assert prefix == scratch / "python-pycache"
        assert prefix.is_dir()
        assert prefix.is_relative_to(scratch)
        assert not prefix.is_relative_to(workspace)
        assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
        assert environment["PYTHONNOUSERSITE"] == "1"
        assert environment["PYTEST_ADDOPTS"] == "-p no:cacheprovider"
        _run_python_hygiene(
            workspace,
            environment,
            run_pytest="landing-" in profile_id,
        )

        projection_residue = {
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*")
            if path.name == "__pycache__" or path.name == ".pytest_cache"
        }
        assert projection_residue == set()
        assert tuple(prefix.rglob("*.pyc"))

        specialized, _ = RUNTIME._specialized_environment(PROFILE, entry) if entry.get(
            "specialized_environment"
        ) else ({}, ())
        shell_environment = RUNTIME._attempt_shell_environment(
            scratch,
            specialized,
        )
        assert shell_environment["PYTHONPYCACHEPREFIX"] == str(prefix)
        assert shell_environment["PYTEST_ADDOPTS"] == "-p no:cacheprovider"
        assert shell_environment["GIT_OPTIONAL_LOCKS"] == "0"

    first_scratch = tmp_path / "attempts" / "resume-001" / "scratch"
    first_scratch.mkdir(parents=True)
    first = RUNTIME._attempt_local_python_environment(first_scratch)
    second_scratch = tmp_path / "attempts" / "resume-002" / "scratch"
    second_scratch.mkdir(parents=True)
    second = RUNTIME._attempt_local_python_environment(second_scratch)
    assert first["PYTHONPYCACHEPREFIX"] != second["PYTHONPYCACHEPREFIX"]


def test_fixed_validation_identity_stays_argv_exact_and_retains_command_id(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "actor-projection"
    workspace.mkdir()
    task = {
        "validation_commands": [
            {
                "command_id": "explicit-py-compile",
                "argv": ["python", "-m", "py_compile", "imported_module.py"],
                "cwd": ".",
            }
        ]
    }
    wrapper = [
        "/usr/bin/env",
        "-C",
        str(workspace),
        "--",
        "python",
        "-m",
        "py_compile",
        "imported_module.py",
    ]
    annotated = RUNTIME._annotate_validation_executions(
        [{"command": " ".join(wrapper), "status": "completed", "exit_code": 0}],
        task=task,
        workspace=workspace,
    )
    assert annotated[0]["validation_command_id"] == "explicit-py-compile"
    assert annotated[0]["validation_argv"] == task["validation_commands"][0]["argv"]
    assert annotated[0]["validation_wrapper_argv"] == wrapper
    assert "PYTHONPYCACHEPREFIX" not in annotated[0]["command"]

    prefixed = " ".join(
        wrapper[:4] + ["PYTHONPYCACHEPREFIX=/runtime/cache"] + wrapper[4:]
    )
    prefixed_result = RUNTIME._annotate_validation_executions(
        [{"command": prefixed, "status": "completed", "exit_code": 0}],
        task=task,
        workspace=workspace,
    )
    assert "validation_command_id" not in prefixed_result[0]
