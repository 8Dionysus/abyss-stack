from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import stat
import subprocess

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PART_ROOT / "scripts" / "install_codex_hooks.py"
SPEC = importlib.util.spec_from_file_location("install_codex_hooks", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


def _native_fragment(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "description": "native test hook",
                "hooks": {
                    "SessionStart": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "/usr/bin/true",
                                    "timeout": 2,
                                }
                            ]
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )


def _git_source(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_part = source_root / "mechanics/config-projection/parts/codex-hooks"
    for relative in INSTALLER.RELEASE_FILES:
        source_path = PART_ROOT / relative
        target = source_part / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
    subprocess.run(["git", "init", "-q", str(source_root)], check=True)
    subprocess.run(
        ["git", "-C", str(source_root), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(source_root), "config", "user.name", "Codex Test"],
        check=True,
    )
    subprocess.run(["git", "-C", str(source_root), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(source_root), "commit", "-qm", "fixture"],
        check=True,
    )
    return source_root


def _install(tmp_path: Path) -> tuple[dict, dict[str, Path], Path]:
    source_root = _git_source(tmp_path)
    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    target = tmp_path / "codex" / "hooks.json"
    target.parent.mkdir()
    target.write_text('{"old":true}\n', encoding="utf-8")
    target.chmod(0o640)
    install_root = tmp_path / "runtime" / "agent-tool-routing"
    context = install_root / "contexts"
    composition = install_root / "composition.json"
    backups = install_root / "backups"
    result = INSTALLER.install(
        source_root=source_root,
        install_root=install_root,
        native_fragment=native,
        target=target,
        context_directory=context,
        sdk_source_root=sdk_root,
        composition_receipt=composition,
        backup_directory=backups,
    )
    return result, {
        "target": target,
        "install_root": install_root,
        "composition": composition,
        "native": native,
        "sdk": sdk_root,
    }, source_root


def test_install_materializes_verified_release_and_stable_commands(tmp_path: Path) -> None:
    result, paths, source_root = _install(tmp_path)
    active = result["active"]
    release_root = Path(active["release"]["release_root"])
    assert release_root.name == active["release"]["release_id"]
    assert INSTALLER.verify_release(release_root)["source"]["commit"]
    assert source_root.as_posix() not in paths["target"].read_text(encoding="utf-8")
    output = json.loads(paths["target"].read_text(encoding="utf-8"))
    pretool = output["hooks"]["PreToolUse"]
    assert len(pretool) == 2
    commands = [group["hooks"][0]["command"] for group in pretool]
    assert all(str(release_root) in command for command in commands)
    assert all("AOA_AGENT_TOOL_ROUTING_CONTEXT_BASE" not in command for command in commands)
    assert stat.S_IMODE(paths["target"].stat().st_mode) == 0o600
    assert active["composition"]["handler_count"] == 3
    assert Path(result["install_receipt"]).is_file()


def test_install_rejects_aliases_before_composition(tmp_path: Path) -> None:
    source_root = _git_source(tmp_path)
    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    install_root = tmp_path / "runtime"
    install_root.mkdir()

    with pytest.raises(INSTALLER.InstallError, match="installation paths must be distinct"):
        INSTALLER.install(
            source_root=source_root,
            install_root=install_root,
            native_fragment=native,
            target=install_root / "active.json",
            context_directory=install_root / "contexts",
            sdk_source_root=sdk_root,
            composition_receipt=install_root / "composition.json",
            backup_directory=install_root / "backups",
        )

    native_target = tmp_path / "native-target.json"
    _native_fragment(native_target)
    with pytest.raises(INSTALLER.InstallError, match="installation paths must be distinct"):
        INSTALLER.install(
            source_root=source_root,
            install_root=install_root,
            native_fragment=native_target,
            target=native_target,
            context_directory=install_root / "contexts-2",
            sdk_source_root=sdk_root,
            composition_receipt=install_root / "composition-2.json",
            backup_directory=install_root / "backups-2",
        )


def test_install_receipts_are_unique_and_release_is_read_only(tmp_path: Path) -> None:
    result, paths, source_root = _install(tmp_path)
    release_root = Path(result["release_root"])
    assert stat.S_IMODE(release_root.stat().st_mode) == 0o555
    for path in release_root.rglob("*"):
        assert not path.is_symlink()
        assert stat.S_IMODE(path.stat().st_mode) == (
            0o555 if path.is_dir() or path.suffix == ".py" else 0o444
        )

    second = INSTALLER.install(
        source_root=source_root,
        install_root=paths["install_root"],
        native_fragment=paths["native"],
        target=paths["target"],
        context_directory=paths["install_root"] / "contexts",
        sdk_source_root=paths["sdk"],
        composition_receipt=paths["composition"],
        backup_directory=paths["install_root"] / "backups",
    )
    assert second["install_receipt"] != result["install_receipt"]
    assert Path(second["install_receipt"]).is_file()


def test_install_reads_allowlisted_files_from_committed_blobs(tmp_path: Path) -> None:
    source_root = _git_source(tmp_path)
    relative = Path("mechanics/config-projection/parts/codex-hooks/scripts/codex_pretool_agent_routing.py")
    source_path = source_root / relative
    committed_bytes = source_path.read_bytes()
    source_path.write_bytes(b"tampered working-tree bytes\n")
    subprocess.run(
        ["git", "-C", str(source_root), "update-index", "--assume-unchanged", str(relative)],
        check=True,
    )
    assert subprocess.run(
        ["git", "-C", str(source_root), "status", "--porcelain=v1"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""

    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    target = tmp_path / "codex" / "hooks.json"
    target.parent.mkdir()
    target.write_text('{"old":true}\n', encoding="utf-8")
    install_root = tmp_path / "runtime"
    result = INSTALLER.install(
        source_root=source_root,
        install_root=install_root,
        native_fragment=native,
        target=target,
        context_directory=install_root / "contexts",
        sdk_source_root=sdk_root,
        composition_receipt=install_root / "composition.json",
        backup_directory=install_root / "backups",
    )

    release_file = Path(result["release_root"]) / relative.relative_to(
        "mechanics/config-projection/parts/codex-hooks"
    )
    assert release_file.read_bytes() == committed_bytes


def test_install_rejects_invalid_active_state_before_composition(tmp_path: Path) -> None:
    source_root = _git_source(tmp_path)
    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    target = tmp_path / "codex" / "hooks.json"
    target.parent.mkdir()
    old = b'{"old":true}\n'
    target.write_bytes(old)
    install_root = tmp_path / "runtime"
    install_root.mkdir()
    active_target = tmp_path / "active-target.json"
    active_target.write_text('{"old_active":true}\n', encoding="utf-8")
    (install_root / "active.json").symlink_to(active_target)
    composition = install_root / "composition.json"

    with pytest.raises(INSTALLER.InstallError, match="active install receipt must not be a symlink"):
        INSTALLER.install(
            source_root=source_root,
            install_root=install_root,
            native_fragment=native,
            target=target,
            context_directory=install_root / "contexts",
            sdk_source_root=sdk_root,
            composition_receipt=composition,
            backup_directory=install_root / "backups",
        )
    assert target.read_bytes() == old
    assert not composition.exists()


def test_install_rejects_mismatched_existing_release_manifest(tmp_path: Path) -> None:
    result, paths, _source_root = _install(tmp_path)
    release_root = Path(result["release_root"])
    manifest_path = release_root / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source"]["commit"] = "f" * 40
    identity = {
        "schema_version": manifest["schema_version"],
        "source": manifest["source"],
        "files": manifest["files"],
    }
    digest = INSTALLER.sha256_bytes(INSTALLER.canonical_bytes(identity))
    manifest["release_digest"] = digest
    manifest["release_id"] = digest.replace("sha256:", "sha256-")
    manifest_path.chmod(0o644)
    manifest_path.write_bytes(INSTALLER.rendered_bytes(manifest))
    manifest_path.chmod(0o444)

    with pytest.raises(INSTALLER.InstallError, match="does not match the current committed manifest"):
        INSTALLER.install(
            source_root=_source_root,
            install_root=paths["install_root"],
            native_fragment=paths["native"],
            target=paths["target"],
            context_directory=paths["install_root"] / "contexts-2",
            sdk_source_root=tmp_path / "sdk",
            composition_receipt=paths["install_root"] / "composition-2.json",
            backup_directory=paths["install_root"] / "backups-2",
        )


def test_install_rejects_dirty_source_before_touching_target(tmp_path: Path) -> None:
    result, paths, source_root = _install(tmp_path)
    previous = paths["target"].read_bytes()
    (source_root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(INSTALLER.InstallError, match="source root must be clean"):
        INSTALLER.install(
            source_root=source_root,
            install_root=paths["install_root"],
            native_fragment=paths["native"],
            target=paths["target"],
            context_directory=paths["install_root"] / "contexts-2",
            sdk_source_root=tmp_path / "sdk",
            composition_receipt=paths["install_root"] / "composition-2.json",
            backup_directory=paths["install_root"] / "backups-2",
        )
    assert paths["target"].read_bytes() == previous
    assert result["active"]["source"]["repository"] == "abyss-stack"


def test_install_rejects_symlinked_install_root_and_target(tmp_path: Path) -> None:
    source_root = _git_source(tmp_path)
    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    target_parent = tmp_path / "codex"
    target_parent.mkdir()
    real_target = target_parent / "real-hooks.json"
    real_target.write_text('{"old":true}\n', encoding="utf-8")
    target_link = target_parent / "hooks.json"
    target_link.symlink_to(real_target)
    real_install_root = tmp_path / "runtime-real"
    install_link = tmp_path / "runtime-link"
    install_link.symlink_to(real_install_root, target_is_directory=True)

    with pytest.raises(INSTALLER.InstallError, match="install root must not be a symlink"):
        INSTALLER.install(
            source_root=source_root,
            install_root=install_link,
            native_fragment=native,
            target=real_target,
            context_directory=real_install_root / "contexts",
            sdk_source_root=sdk_root,
            composition_receipt=real_install_root / "composition.json",
            backup_directory=real_install_root / "backups",
        )

    with pytest.raises(INSTALLER.InstallError, match="Codex hooks target must not be a symlink"):
        INSTALLER.install(
            source_root=source_root,
            install_root=real_install_root,
            native_fragment=native,
            target=target_link,
            context_directory=real_install_root / "contexts",
            sdk_source_root=sdk_root,
            composition_receipt=real_install_root / "composition.json",
            backup_directory=real_install_root / "backups",
        )
    assert real_target.read_text(encoding="utf-8") == '{"old":true}\n'


def test_install_restores_target_when_active_receipt_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_root = _git_source(tmp_path)
    sdk_root = tmp_path / "sdk"
    (sdk_root / "src/aoa_sdk").mkdir(parents=True)
    native = tmp_path / "native.json"
    _native_fragment(native)
    target = tmp_path / "codex" / "hooks.json"
    target.parent.mkdir()
    old = b'{"old":true}\n'
    target.write_bytes(old)
    target.chmod(0o640)
    install_root = tmp_path / "runtime"
    install_root.mkdir()
    composition = install_root / "composition.json"
    old_composition = b'{"old_composition":true}\n'
    composition.write_bytes(old_composition)
    original_atomic_write = INSTALLER._atomic_write

    def fail_active(path: Path, payload: bytes, *, mode: int) -> None:
        if path.name == "active.json":
            raise OSError("synthetic active receipt failure")
        original_atomic_write(path, payload, mode=mode)

    monkeypatch.setattr(INSTALLER, "_atomic_write", fail_active)
    with pytest.raises(OSError, match="synthetic active receipt failure"):
        INSTALLER.install(
            source_root=source_root,
            install_root=install_root,
            native_fragment=native,
            target=target,
            context_directory=install_root / "contexts",
            sdk_source_root=sdk_root,
            composition_receipt=composition,
            backup_directory=install_root / "backups",
        )
    assert target.read_bytes() == old
    assert stat.S_IMODE(target.stat().st_mode) == 0o640
    assert composition.read_bytes() == old_composition
