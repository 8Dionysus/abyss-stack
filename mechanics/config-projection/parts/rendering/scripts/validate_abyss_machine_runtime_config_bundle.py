#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _find_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "AGENTS.md").is_file() and (parent / "scripts" / "aoa-render-config").is_file():
            return parent
    raise RuntimeError("could not find abyss-stack repository root")


REPO_ROOT = _find_repo_root()
DEFAULT_MANIFEST = REPO_ROOT / "mechanics" / "config-projection" / "parts" / "rendering" / "manifests" / "runtime_config.bundle.json"
DEFAULT_SUBJECT_DIR = REPO_ROOT / "dist" / "abyss-stack-runtime-config"
DEFAULT_SUBJECT = DEFAULT_SUBJECT_DIR / "substrate.rendered.yml"
DEFAULT_BUNDLE_DIR = REPO_ROOT / "dist" / "abyss-artifact-bundle" / "abyss-stack-runtime-config"
PUBLIC_RUNTIME_ROOT = "/srv/AbyssOS/abyss-stack"


def _candidate_abyss_machine_roots() -> list[Path]:
    candidates: list[Path] = []
    env_root = os.environ.get("ABYSS_MACHINE_REPO_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(
        [
            REPO_ROOT.parent / "abyss-machine",
            Path("/home/dionysus/src/abyss-machine"),
            Path("/srv/AbyssOS/abyss-machine"),
        ]
    )
    return candidates


def _import_artifact_bundles() -> tuple[Any, Path | None]:
    for candidate in _candidate_abyss_machine_roots():
        root = candidate.expanduser().resolve()
        module_root = root / "src"
        if (module_root / "abyss_machine" / "artifact_bundles.py").is_file():
            sys.path.insert(0, str(module_root))
            return importlib.import_module("abyss_machine.artifact_bundles"), root
    return importlib.import_module("abyss_machine.artifact_bundles"), None


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _render_public_subject(subject_path: Path) -> None:
    subject_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="abyss-stack-runtime-config-") as temp_root:
        stack_root = Path(temp_root)
        configs_root = stack_root / "Configs"
        env = os.environ.copy()
        env["AOA_STACK_ROOT"] = str(stack_root)
        env["AOA_CONFIGS_ROOT"] = str(configs_root)
        sync_command = ("scripts/aoa-sync-configs",)
        sync_completed = subprocess.run(sync_command, cwd=REPO_ROOT, env=env, check=False)
        if sync_completed.returncode != 0:
            raise RuntimeError(f"prepare synthetic runtime config root failed with exit code {sync_completed.returncode}")
        stack_env = configs_root / "stack.env"
        if not stack_env.exists():
            shutil.copyfile(REPO_ROOT / "env" / "stack.env.example", stack_env)
        command = ("scripts/aoa-render-config", "--profile", "substrate", "--write", str(subject_path))
        completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"render runtime config failed with exit code {completed.returncode}")
        synthetic_root = str(stack_root)
        text = subject_path.read_text(encoding="utf-8")
        normalized = text.replace(synthetic_root, PUBLIC_RUNTIME_ROOT)
        subject_path.write_text(normalized, encoding="utf-8")
        if synthetic_root in normalized:
            raise ValueError(f"rendered runtime config still contains synthetic root: {synthetic_root}")


def _assert_rendered_subject_public_safe(subject_path: Path) -> None:
    text = subject_path.read_text(encoding="utf-8")
    forbidden = [
        str(REPO_ROOT.resolve()),
        str(Path.home()),
        "/srv/abyss-machine",
        "Secrets/",
        "PASSWORD=",
        "TOKEN=",
        "SECRET=",
    ]
    leaked = [item for item in forbidden if item and item in text]
    if leaked:
        raise ValueError("rendered runtime config contains private or machine-local markers: " + ", ".join(leaked))


def _assert_public_sidecars_do_not_leak_local_root(bundle_dir: Path) -> None:
    local_root = str(REPO_ROOT.resolve())
    leaks: list[str] = []
    for path in sorted(bundle_dir.iterdir()):
        if path.is_file() and path.suffix in {".json", ".jsonl"}:
            if local_root in path.read_text(encoding="utf-8"):
                leaks.append(path.name)
    if leaks:
        raise ValueError("public artifact sidecars leak local repo root: " + ", ".join(leaks))


def validate_bundle(manifest: Path, subject_path: Path, bundle_dir: Path, *, clean: bool) -> dict[str, Any]:
    artifact_bundles, abyss_machine_root = _import_artifact_bundles()
    _render_public_subject(subject_path)
    _assert_rendered_subject_public_safe(subject_path)
    if clean and bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)

    abyss_repo_root = abyss_machine_root or artifact_bundles.REPO_ROOT
    producer_command = "python mechanics/config-projection/parts/rendering/scripts/validate_abyss_machine_runtime_config_bundle.py"
    build = artifact_bundles.build_sidecars(
        bundle_dir,
        manifest_ref=manifest,
        repo_root=abyss_repo_root,
        producer_command=producer_command,
    )
    sign = artifact_bundles.sign_bundle(bundle_dir, repo_root=abyss_repo_root)
    verify = artifact_bundles.verify_bundle(bundle_dir, repo_root=abyss_repo_root)
    release_check = artifact_bundles.release_check(bundle_dir, repo_root=abyss_repo_root)
    _assert_public_sidecars_do_not_leak_local_root(bundle_dir)

    manifest_payload = _load_json(manifest)
    return {
        "ok": bool(build.get("ok") and sign.get("ok") and verify.get("ok") and release_check.get("ok")),
        "schema": "abyss_stack_runtime_config_artifact_bundle_validation_v1",
        "manifest_ref": manifest.relative_to(REPO_ROOT).as_posix(),
        "subject_ref": subject_path.relative_to(REPO_ROOT).as_posix(),
        "bundle_dir": bundle_dir.relative_to(REPO_ROOT).as_posix(),
        "artifact_class": manifest_payload.get("artifact_class"),
        "required_controls": verify.get("required_controls"),
        "verified_controls": verify.get("verified_controls"),
        "abyss_machine_repo_root": str(abyss_repo_root),
        "steps": {
            "build_sidecars": build,
            "sign": sign,
            "verify": verify,
            "release_check": release_check,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rendered abyss-stack runtime config as an OS Abyss artifact bundle.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--subject", type=Path, default=DEFAULT_SUBJECT)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--no-clean", action="store_true", help="do not remove the previous generated bundle directory first")
    parser.add_argument("--json", action="store_true", help="print the full validation payload")
    args = parser.parse_args()

    manifest = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    subject = args.subject if args.subject.is_absolute() else REPO_ROOT / args.subject
    bundle_dir = args.bundle_dir if args.bundle_dir.is_absolute() else REPO_ROOT / args.bundle_dir
    payload = validate_bundle(manifest, subject, bundle_dir, clean=not args.no_clean)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif payload["ok"]:
        print(
            "[ok] abyss-machine runtime config artifact bundle verified: "
            f"{payload['bundle_dir']} ({', '.join(payload['verified_controls'])})"
        )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
