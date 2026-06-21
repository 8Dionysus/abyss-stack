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
DEFAULT_REGISTRY_DIR = REPO_ROOT / "dist" / "abyss-artifact-registry" / "abyss-stack-runtime-config"
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


def _public_seed_root() -> Path:
    return Path(os.environ.get("ABYSS_MACHINE_PUBLIC_SEED_ROOT", "/usr/local/share/abyss-machine")).expanduser()


def _import_from_package_root(package_root: Path) -> tuple[Any, Path] | None:
    root = package_root.expanduser().resolve()
    if (root / "abyss_machine" / "artifact_bundles.py").is_file():
        sys.path.insert(0, str(root))
        return importlib.import_module("abyss_machine.artifact_bundles"), _public_seed_root()
    return None


def _import_artifact_bundles() -> tuple[Any, Path | None]:
    package_root = os.environ.get("ABYSS_MACHINE_PACKAGE_ROOT")
    if package_root:
        imported = _import_from_package_root(Path(package_root))
        if imported is not None:
            return imported
    for candidate in _candidate_abyss_machine_roots():
        root = candidate.expanduser().resolve()
        module_root = root / "src"
        if (module_root / "abyss_machine" / "artifact_bundles.py").is_file():
            sys.path.insert(0, str(module_root))
            return importlib.import_module("abyss_machine.artifact_bundles"), root
    installed = _import_from_package_root(Path("/usr/local/libexec"))
    if installed is not None:
        return installed
    return importlib.import_module("abyss_machine.artifact_bundles"), None


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _path_ref(path: Path) -> str:
    resolved = path.expanduser().resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _sanitize_public_verify_sidecar(bundle_dir: Path) -> dict[str, Any]:
    sidecar = bundle_dir / "artifact.verify.json"
    if not sidecar.is_file():
        return {}
    payload = _load_json(sidecar)
    changed = False
    resolutions = payload.get("artifact_subject_resolution")
    if isinstance(resolutions, list):
        for item in resolutions:
            if not isinstance(item, dict):
                continue
            resolved_path = item.get("resolved_path")
            if not resolved_path:
                continue
            public_ref = _path_ref(Path(str(resolved_path)))
            if public_ref != resolved_path:
                item["resolved_path"] = public_ref
                changed = True
    if changed:
        _write_json(sidecar, payload)
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
        sync_completed = subprocess.run(sync_command, cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False)
        if sync_completed.returncode != 0:
            raise RuntimeError(
                f"prepare synthetic runtime config root failed with exit code {sync_completed.returncode}: "
                f"{sync_completed.stderr or sync_completed.stdout}"
            )
        stack_env = configs_root / "stack.env"
        if not stack_env.exists():
            shutil.copyfile(REPO_ROOT / "env" / "stack.env.example", stack_env)
        command = ("scripts/aoa-render-config", "--profile", "substrate", "--write", str(subject_path))
        completed = subprocess.run(command, cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(
                f"render runtime config failed with exit code {completed.returncode}: "
                f"{completed.stderr or completed.stdout}"
            )
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


def _copy_bundle(bundle_dir: Path, target: Path) -> Path:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(bundle_dir, target)
    return target


def _verify_missing_sbom(artifact_bundles: Any, abyss_repo_root: Path, bundle_dir: Path, tmp_root: Path) -> dict[str, Any]:
    candidate = _copy_bundle(bundle_dir, tmp_root / "missing-sbom")
    for name in (artifact_bundles.SBOM_CYCLONEDX_SIDECAR, artifact_bundles.SBOM_SPDX_SIDECAR):
        path = candidate / name
        if path.exists():
            path.unlink()
    verification = artifact_bundles.verify_bundle(candidate, repo_root=abyss_repo_root)
    return {
        "ok": verification.get("ok") is False and bool(verification.get("missing")),
        "verification": verification,
    }


def _verify_wrong_slsa_subject(artifact_bundles: Any, abyss_repo_root: Path, bundle_dir: Path, tmp_root: Path) -> dict[str, Any]:
    candidate = _copy_bundle(bundle_dir, tmp_root / "wrong-slsa-subject")
    path = candidate / artifact_bundles.SLSA_INTOTO_SIDECAR
    statement = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    statement["subject"][0]["digest"]["sha256"] = "0" * 64
    path.write_text(json.dumps(statement, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    verification = artifact_bundles.verify_bundle(candidate, repo_root=abyss_repo_root)
    return {
        "ok": verification.get("ok") is False
        and any("SLSA/in-toto sidecar does not cover artifact subject digests" in item for item in verification.get("errors", [])),
        "verification": verification,
    }


def _verify_private_render_marker(subject_path: Path, tmp_root: Path) -> dict[str, Any]:
    candidate = tmp_root / "private.rendered.yml"
    shutil.copyfile(subject_path, candidate)
    candidate.write_text(candidate.read_text(encoding="utf-8") + "\nTOKEN=private-negative\n", encoding="utf-8")
    try:
        _assert_rendered_subject_public_safe(candidate)
    except ValueError as exc:
        return {"ok": "rendered runtime config contains private or machine-local markers" in str(exc), "error": str(exc)}
    return {"ok": False, "error": "private rendered marker was not detected"}


def _registry_roundtrip(
    artifact_bundles: Any,
    bundle_dir: Path,
    registry_dir: Path,
    *,
    lifecycle_state: str,
    evidence_ref: str,
) -> dict[str, Any]:
    registered = artifact_bundles.write_bundle_registry_record(
        bundle_dir,
        registry_dir,
        lifecycle_state=lifecycle_state,
        consumer_refs=["abyss-stack:config-projection-rendering"],
        evidence_refs=[evidence_ref],
    )
    latest = artifact_bundles.read_bundle_registry(registry_dir, artifact_class="abyss_stack_runtime_config_bundle")
    latest_record = latest.get("latest_by_artifact_class", {}).get("abyss_stack_runtime_config_bundle")
    return {
        "ok": bool(
            registered.get("ok")
            and isinstance(latest_record, dict)
            and latest_record.get("record_id") == registered.get("record", {}).get("record_id")
            and latest_record.get("lifecycle_state") == lifecycle_state
        ),
        "registered": registered,
        "latest": latest,
    }


def _verify_terminal_registry_state(artifact_bundles: Any, bundle_dir: Path, tmp_root: Path) -> dict[str, Any]:
    registry_dir = tmp_root / "terminal-registry"
    release_ready = _registry_roundtrip(
        artifact_bundles,
        bundle_dir,
        registry_dir,
        lifecycle_state="release-ready",
        evidence_ref="terminal-state-rehearsal",
    )
    revoked = artifact_bundles.write_bundle_registry_record(
        bundle_dir,
        registry_dir,
        lifecycle_state="revoked",
        revocation_reason="abyss-stack runtime config terminal-state rehearsal",
    )
    after_revoke = artifact_bundles.read_bundle_registry(registry_dir, artifact_class="abyss_stack_runtime_config_bundle")
    return {
        "ok": bool(release_ready.get("ok") and revoked.get("ok") and not after_revoke.get("latest_by_artifact_class")),
        "release_ready": release_ready,
        "revoked": revoked,
        "after_revoke": after_revoke,
    }


def _run_adversarial_checks(artifact_bundles: Any, abyss_repo_root: Path, subject_path: Path, bundle_dir: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="abyss-stack-runtime-config-negative-") as tmp:
        tmp_root = Path(tmp)
        checks = {
            "missing_sbom": _verify_missing_sbom(artifact_bundles, abyss_repo_root, bundle_dir, tmp_root),
            "wrong_slsa_subject": _verify_wrong_slsa_subject(artifact_bundles, abyss_repo_root, bundle_dir, tmp_root),
            "private_render_marker": _verify_private_render_marker(subject_path, tmp_root),
            "terminal_registry_state": _verify_terminal_registry_state(artifact_bundles, bundle_dir, tmp_root),
        }
    return {
        "ok": all(bool(item.get("ok")) for item in checks.values()),
        "checks": checks,
    }


def validate_bundle(manifest: Path, subject_path: Path, bundle_dir: Path, registry_dir: Path, *, clean: bool) -> dict[str, Any]:
    artifact_bundles, abyss_machine_root = _import_artifact_bundles()
    _render_public_subject(subject_path)
    _assert_rendered_subject_public_safe(subject_path)
    if clean and bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if clean and registry_dir.exists():
        shutil.rmtree(registry_dir)
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
    registry = _registry_roundtrip(
        artifact_bundles,
        bundle_dir,
        registry_dir,
        lifecycle_state="release-ready",
        evidence_ref=f"{_path_ref(bundle_dir)}/artifact.verify.json",
    )
    adversarial = _run_adversarial_checks(artifact_bundles, abyss_repo_root, subject_path, bundle_dir)
    public_verify_sidecar = _sanitize_public_verify_sidecar(bundle_dir)
    _assert_public_sidecars_do_not_leak_local_root(bundle_dir)

    manifest_payload = _load_json(manifest)
    return {
        "ok": bool(
            build.get("ok")
            and sign.get("ok")
            and verify.get("ok")
            and release_check.get("ok")
            and registry.get("ok")
            and adversarial.get("ok")
        ),
        "schema": "abyss_stack_runtime_config_artifact_bundle_validation_v1",
        "manifest_ref": _path_ref(manifest),
        "subject_ref": _path_ref(subject_path),
        "bundle_dir": _path_ref(bundle_dir),
        "registry_dir": _path_ref(registry_dir),
        "artifact_class": manifest_payload.get("artifact_class"),
        "required_controls": verify.get("required_controls"),
        "verified_controls": verify.get("verified_controls"),
        "abyss_machine_repo_root": str(abyss_repo_root),
        "abyss_machine_package_root": os.environ.get("ABYSS_MACHINE_PACKAGE_ROOT"),
        "public_verify_sidecar": {
            "artifact_subject_resolution": public_verify_sidecar.get("artifact_subject_resolution", []),
        },
        "registry": registry,
        "adversarial_checks": adversarial,
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
    parser.add_argument("--registry-dir", type=Path, default=DEFAULT_REGISTRY_DIR)
    parser.add_argument("--no-clean", action="store_true", help="do not remove the previous generated bundle directory first")
    parser.add_argument("--json", action="store_true", help="print the full validation payload")
    args = parser.parse_args()

    manifest = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    subject = args.subject if args.subject.is_absolute() else REPO_ROOT / args.subject
    bundle_dir = args.bundle_dir if args.bundle_dir.is_absolute() else REPO_ROOT / args.bundle_dir
    registry_dir = args.registry_dir if args.registry_dir.is_absolute() else REPO_ROOT / args.registry_dir
    payload = validate_bundle(manifest, subject, bundle_dir, registry_dir, clean=not args.no_clean)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif payload["ok"]:
        print(
            "[ok] abyss-machine runtime config artifact bundle verified: "
            f"{payload['bundle_dir']} ({', '.join(payload['verified_controls'])}; registry={payload['registry_dir']})"
        )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
