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
DEFAULT_SUBJECT_STORE_ROOT = REPO_ROOT / "dist" / "abyss-artifact-subjects" / "abyss-stack-runtime-config"
PUBLIC_RUNTIME_ROOT = "/srv/AbyssOS/abyss-stack"
ARTIFACT_CLASS = "abyss_stack_runtime_config_bundle"
CONSUMER_INTENT = "runtime"
CONSUMER_REF = "abyss-stack:config-projection-rendering"
SOURCE_REPO = "abyss-stack"
TRUST_ROOT_MODE = "host_managed"
PRODUCER = "abyss-stack config rendering scripts from tracked compose modules and public-safe runtime route inputs"


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


def _sanitize_public_payload(payload: Any) -> Any:
    local_root = str(REPO_ROOT.resolve())
    if isinstance(payload, dict):
        return {key: _sanitize_public_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [_sanitize_public_payload(item) for item in payload]
    if isinstance(payload, str):
        if payload == local_root or payload.startswith(local_root + os.sep):
            return _path_ref(Path(payload))
        tmp_root = "/srv/abyss-machine/tmp"
        if payload == tmp_root:
            return "host-tmp:abyss-machine"
        if payload.startswith(tmp_root + os.sep):
            suffix = Path(payload).resolve().relative_to(Path(tmp_root)).as_posix()
            return f"host-tmp:abyss-machine/{suffix}"
        home = Path.home().resolve()
        if payload == str(home) or payload.startswith(str(home) + os.sep):
            return "host-home-redacted"
    return payload


def _default_tmp_root() -> Path | None:
    for raw in (os.environ.get("ABYSS_MACHINE_TMP_ROOT"), "/srv/abyss-machine/tmp"):
        if not raw:
            continue
        path = Path(raw)
        if path.is_dir():
            return path
    return None


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


def _sanitize_public_json_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")) if root.exists() else []:
        if not path.is_file() or path.suffix not in {".json", ".jsonl"}:
            continue
        if path.suffix == ".jsonl":
            lines = []
            changed = False
            for line in path.read_text(encoding="utf-8").splitlines():
                payload = json.loads(line)
                sanitized = _sanitize_public_payload(payload)
                changed = changed or sanitized != payload
                lines.append(json.dumps(sanitized, ensure_ascii=False, sort_keys=True))
            if changed:
                path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            continue
        payload = _load_json(path)
        sanitized = _sanitize_public_payload(payload)
        if sanitized != payload:
            _write_json(path, sanitized)


def _sanitize_public_registry(registry_dir: Path) -> None:
    _sanitize_public_json_tree(registry_dir)


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
    forbidden = [str(REPO_ROOT.resolve()), str(Path.home()), "/srv/abyss-machine/tmp"]
    leaks: list[str] = []
    for path in sorted(bundle_dir.iterdir()):
        if path.is_file() and path.suffix in {".json", ".jsonl"}:
            text = path.read_text(encoding="utf-8")
            if any(item and item in text for item in forbidden):
                leaks.append(path.name)
    if leaks:
        raise ValueError("public artifact sidecars leak local repo roots: " + ", ".join(leaks))


def _assert_public_json_tree_does_not_leak_local_root(root: Path, *, label: str) -> None:
    forbidden = [str(REPO_ROOT.resolve()), str(Path.home()), "/srv/abyss-machine/tmp"]
    leaks: list[str] = []
    for path in sorted(root.rglob("*")) if root.exists() else []:
        if path.is_file() and path.suffix in {".json", ".jsonl"}:
            if any(item and item in path.read_text(encoding="utf-8") for item in forbidden):
                leaks.append(path.name)
    if leaks:
        raise ValueError(f"public artifact {label} leaks local repo roots: " + ", ".join(leaks))


def _assert_manifest_trust_contract(manifest: Path) -> None:
    payload = _load_json(manifest)
    if payload.get("artifact_class") != ARTIFACT_CLASS:
        raise ValueError(f"manifest artifact_class must be {ARTIFACT_CLASS}")
    if payload.get("owner_repo") != "abyss-stack":
        raise ValueError("manifest owner_repo must be abyss-stack")
    contract = payload.get("consumer_contract")
    if not isinstance(contract, dict):
        raise ValueError("manifest consumer_contract must be an object")
    if contract.get("registry_required") is not True:
        raise ValueError("manifest consumer_contract.registry_required must be true")
    if contract.get("subject_store_required") is not True:
        raise ValueError("manifest consumer_contract.subject_store_required must be true")
    if contract.get("admission_gate") != "fail_closed_consumer_admission":
        raise ValueError("manifest consumer_contract.admission_gate must be fail_closed_consumer_admission")
    commands = "\n".join(str(item) for item in payload.get("consumer_command") or [])
    for token in (
        "artifacts evidence-promote",
        "artifacts materialize-subjects",
        "artifacts trust-gate",
        "artifacts registry-latest",
        "--store-root SUBJECT_STORE_ROOT",
        "--source-repo abyss-stack",
        "--trust-root-mode host_managed",
    ):
        if token not in commands:
            raise ValueError(f"manifest consumer_command must include {token}")


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
    registered = artifact_bundles.promote_bundle_evidence(
        bundle_dir,
        registry_dir,
        lifecycle_state=lifecycle_state,
        consumer_refs=[CONSUMER_REF],
        evidence_refs=[evidence_ref],
        source_repo=SOURCE_REPO,
        source_ref=_path_ref(DEFAULT_MANIFEST),
        producer=PRODUCER,
        trust_root_mode=TRUST_ROOT_MODE,
    )
    latest = artifact_bundles.read_bundle_registry(registry_dir, artifact_class=ARTIFACT_CLASS)
    latest_record = latest.get("latest_by_artifact_class", {}).get(ARTIFACT_CLASS)
    return {
        "ok": bool(
            registered.get("ok")
            and isinstance(latest_record, dict)
            and latest_record.get("record_id") == registered.get("promotion", {}).get("record_id")
            and latest_record.get("lifecycle_state") == lifecycle_state
        ),
        "promoted": registered,
        "latest": latest,
    }


def _registry_roundtrip_with_subject_store(
    artifact_bundles: Any,
    bundle_dir: Path,
    registry_dir: Path,
    store_root: Path,
    *,
    lifecycle_state: str,
    evidence_ref: str,
) -> dict[str, Any]:
    env_root = "ABYSS_MACHINE_ARTIFACT_SUBJECT_STORE_ROOT"
    env_roots = "ABYSS_MACHINE_ARTIFACT_SUBJECT_STORE_ROOTS"
    old_root = os.environ.get(env_root)
    old_roots = os.environ.get(env_roots)
    os.environ[env_root] = str(store_root)
    os.environ[env_roots] = str(store_root)
    try:
        return _registry_roundtrip(
            artifact_bundles,
            bundle_dir,
            registry_dir,
            lifecycle_state=lifecycle_state,
            evidence_ref=evidence_ref,
        )
    finally:
        if old_root is None:
            os.environ.pop(env_root, None)
        else:
            os.environ[env_root] = old_root
        if old_roots is None:
            os.environ.pop(env_roots, None)
        else:
            os.environ[env_roots] = old_roots


def _trust_gate_allow_latest(
    artifact_bundles: Any,
    registry_dir: Path,
    registry_roundtrip: dict[str, Any],
    *,
    require_subject_store: bool = True,
) -> dict[str, Any]:
    record = registry_roundtrip.get("promoted", {}).get("record", {})
    trust_gate = artifact_bundles.trust_gate(
        registry_dir,
        artifact_class=ARTIFACT_CLASS,
        subject_digest=str(record.get("subject_digest") or ""),
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    inspected_claims = trust_gate.get("inspected_claims", {})
    return {
        "ok": bool(
            trust_gate.get("ok")
            and trust_gate.get("verdict") in {"allow", "warn"}
            and trust_gate.get("decision", {}).get("model") == "fail_closed_consumer_admission"
            and trust_gate.get("decision", {}).get("allow") is True
            and inspected_claims.get("registry_latest", {}).get("selected_record_is_latest") is True
            and inspected_claims.get("controls", {}).get("required_controls_missing") == []
            and inspected_claims.get("source", {}).get("source_repo_matched") is True
            and inspected_claims.get("trust_root", {}).get("trust_root_mode_matched") is True
            and (
                not require_subject_store
                or inspected_claims.get("artifact_subject_store", {}).get("ok") is True
            )
        ),
        "trust_gate": trust_gate,
    }


def _trust_gate_pre_materialization_state(
    artifact_bundles: Any,
    registry_dir: Path,
    registry_roundtrip: dict[str, Any],
) -> dict[str, Any]:
    gate_check = _trust_gate_allow_latest(
        artifact_bundles,
        registry_dir,
        registry_roundtrip,
        require_subject_store=False,
    )
    trust_gate = gate_check.get("trust_gate", {})
    blockers = set(trust_gate.get("blockers") or [])
    reasons = set(trust_gate.get("reasons") or [])
    inspected_claims = trust_gate.get("inspected_claims") if isinstance(trust_gate, dict) else {}
    subject_store = (
        inspected_claims.get("artifact_subject_store")
        if isinstance(inspected_claims, dict) and isinstance(inspected_claims.get("artifact_subject_store"), dict)
        else {}
    )
    tolerated_pre_materialization_reasons = {"required_artifact_subject_store_not_verified"}
    gate_failures = blockers | reasons
    missing_subject_store = (
        gate_failures == tolerated_pre_materialization_reasons
        and subject_store.get("ok") is False
    )
    return {
        "ok": bool(gate_check.get("ok") or missing_subject_store),
        "mode": "allow_existing_subject_store" if gate_check.get("ok") else "deny_until_subject_store_materialized",
        "expected_pre_materialization_deny": bool(missing_subject_store),
        "trust_gate": trust_gate,
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
        source_repo=SOURCE_REPO,
        source_ref=_path_ref(DEFAULT_MANIFEST),
        producer=PRODUCER,
        trust_root_mode=TRUST_ROOT_MODE,
    )
    revoked_gate = artifact_bundles.trust_gate(
        registry_dir,
        artifact_class=ARTIFACT_CLASS,
        record_id=str(release_ready.get("promoted", {}).get("record", {}).get("record_id") or ""),
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    after_revoke = artifact_bundles.read_bundle_registry(registry_dir, artifact_class=ARTIFACT_CLASS)
    return {
        "ok": bool(
            release_ready.get("ok")
            and revoked.get("ok")
            and revoked_gate.get("verdict") == "deny"
            and revoked_gate.get("decision", {}).get("allow") is False
            and revoked_gate.get("inspected_claims", {}).get("lifecycle", {}).get("terminal_state") is True
            and not after_revoke.get("latest_by_artifact_class")
        ),
        "release_ready": release_ready,
        "revoked": revoked,
        "revoked_trust_gate": revoked_gate,
        "after_revoke": after_revoke,
    }


def _verify_materialized_subject_store(
    artifact_bundles: Any,
    manifest: Path,
    bundle_dir: Path,
    registry_dir: Path,
    store_root: Path,
) -> dict[str, Any]:
    pre_registry = _registry_roundtrip(
        artifact_bundles,
        bundle_dir,
        registry_dir,
        lifecycle_state="release-ready",
        evidence_ref="materialized-subject-store-precondition",
    )
    materialized = artifact_bundles.materialize_artifact_subjects(
        bundle_dir,
        store_root=store_root,
        registry_dir=registry_dir,
        manifest_ref=manifest,
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    refreshed_registry = _registry_roundtrip_with_subject_store(
        artifact_bundles,
        bundle_dir,
        registry_dir,
        store_root,
        lifecycle_state="release-ready",
        evidence_ref="materialized-subject-store-rehearsal",
    )
    _sanitize_public_json_tree(store_root)
    latest_record = refreshed_registry.get("latest", {}).get("latest_by_artifact_class", {}).get(ARTIFACT_CLASS, {})
    store_status = latest_record.get("artifact_subject_store") if isinstance(latest_record, dict) else {}
    gate = artifact_bundles.trust_gate(
        registry_dir,
        artifact_class=ARTIFACT_CLASS,
        subject_digest=str(materialized.get("aggregate_digest") or ""),
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    return _sanitize_public_payload({
        "ok": bool(
            pre_registry.get("ok")
            and materialized.get("ok")
            and refreshed_registry.get("ok")
            and isinstance(store_status, dict)
            and store_status.get("ok") is True
            and gate.get("verdict") in {"allow", "warn"}
            and gate.get("decision", {}).get("allow") is True
            and gate.get("inspected_claims", {}).get("artifact_subject_store", {}).get("ok") is True
        ),
        "pre_registry": pre_registry,
        "materialized": materialized,
        "refreshed_registry": refreshed_registry,
        "trust_gate": gate,
    })


def _run_adversarial_checks(
    artifact_bundles: Any,
    abyss_repo_root: Path,
    manifest: Path,
    subject_path: Path,
    bundle_dir: Path,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="abyss-stack-runtime-config-negative-", dir=_default_tmp_root()) as tmp:
        tmp_root = Path(tmp)
        checks = {
            "missing_sbom": _verify_missing_sbom(artifact_bundles, abyss_repo_root, bundle_dir, tmp_root),
            "wrong_slsa_subject": _verify_wrong_slsa_subject(artifact_bundles, abyss_repo_root, bundle_dir, tmp_root),
            "private_render_marker": _verify_private_render_marker(subject_path, tmp_root),
            "terminal_registry_state": _verify_terminal_registry_state(artifact_bundles, bundle_dir, tmp_root),
            "materialized_subject_store": _verify_materialized_subject_store(
                artifact_bundles,
                manifest,
                bundle_dir,
                tmp_root / "materialized-registry",
                tmp_root / "subject-store",
            ),
        }
    return _sanitize_public_payload({
        "ok": all(bool(item.get("ok")) for item in checks.values()),
        "checks": checks,
    })


def validate_bundle(
    manifest: Path,
    subject_path: Path,
    bundle_dir: Path,
    registry_dir: Path,
    subject_store_root: Path,
    *,
    clean: bool,
) -> dict[str, Any]:
    artifact_bundles, abyss_machine_root = _import_artifact_bundles()
    _assert_manifest_trust_contract(manifest)
    _render_public_subject(subject_path)
    _assert_rendered_subject_public_safe(subject_path)
    if clean and bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if clean and registry_dir.exists():
        shutil.rmtree(registry_dir)
    if clean and subject_store_root.exists():
        shutil.rmtree(subject_store_root)
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
    pre_materialization_gate = _trust_gate_pre_materialization_state(
        artifact_bundles,
        registry_dir,
        registry,
    )
    materialized = artifact_bundles.materialize_artifact_subjects(
        bundle_dir,
        store_root=subject_store_root,
        registry_dir=registry_dir,
        manifest_ref=manifest,
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    registry_with_subject_store = _registry_roundtrip_with_subject_store(
        artifact_bundles,
        bundle_dir,
        registry_dir,
        subject_store_root,
        lifecycle_state="release-ready",
        evidence_ref="materialized-subject-store",
    )
    trust_gate = _trust_gate_allow_latest(artifact_bundles, registry_dir, registry_with_subject_store)
    subject_store_gate = artifact_bundles.trust_gate(
        registry_dir,
        artifact_class=ARTIFACT_CLASS,
        subject_digest=str(materialized.get("aggregate_digest") or ""),
        consumer_intent=CONSUMER_INTENT,
        expected_source_repo=SOURCE_REPO,
        expected_trust_root_mode=TRUST_ROOT_MODE,
    )
    adversarial = _run_adversarial_checks(
        artifact_bundles,
        abyss_repo_root,
        manifest,
        subject_path,
        bundle_dir,
    )
    public_verify_sidecar = _sanitize_public_verify_sidecar(bundle_dir)
    _sanitize_public_json_tree(subject_store_root)
    _assert_public_sidecars_do_not_leak_local_root(bundle_dir)
    _sanitize_public_registry(registry_dir)
    _assert_public_json_tree_does_not_leak_local_root(registry_dir, label="registry")
    _assert_public_json_tree_does_not_leak_local_root(subject_store_root, label="subject-store")
    registry = artifact_bundles.read_bundle_registry(registry_dir, artifact_class=ARTIFACT_CLASS)

    manifest_payload = _load_json(manifest)
    payload = {
        "ok": bool(
            build.get("ok")
            and sign.get("ok")
            and verify.get("ok")
            and release_check.get("ok")
            and registry.get("ok")
            and pre_materialization_gate.get("ok")
            and trust_gate.get("ok")
            and materialized.get("ok")
            and registry_with_subject_store.get("ok")
            and subject_store_gate.get("ok")
            and subject_store_gate.get("verdict") in {"allow", "warn"}
            and subject_store_gate.get("decision", {}).get("allow") is True
            and subject_store_gate.get("inspected_claims", {}).get("artifact_subject_store", {}).get("ok") is True
            and adversarial.get("ok")
        ),
        "schema": "abyss_stack_runtime_config_artifact_bundle_validation_v1",
        "manifest_ref": _path_ref(manifest),
        "subject_ref": _path_ref(subject_path),
        "bundle_dir": _path_ref(bundle_dir),
        "registry_dir": _path_ref(registry_dir),
        "subject_store_root": _path_ref(subject_store_root),
        "artifact_class": manifest_payload.get("artifact_class"),
        "required_controls": verify.get("required_controls"),
        "verified_controls": verify.get("verified_controls"),
        "abyss_machine_repo_root": str(abyss_repo_root),
        "abyss_machine_package_root": os.environ.get("ABYSS_MACHINE_PACKAGE_ROOT"),
        "public_verify_sidecar": {
            "artifact_subject_resolution": public_verify_sidecar.get("artifact_subject_resolution", []),
        },
        "registry": registry,
        "pre_materialization_gate": pre_materialization_gate,
        "trust_gate": trust_gate,
        "materialized_subject_store": materialized,
        "registry_with_subject_store": registry_with_subject_store,
        "subject_store_gate": subject_store_gate,
        "adversarial_checks": adversarial,
        "steps": {
            "build_sidecars": build,
            "sign": sign,
            "verify": verify,
            "release_check": release_check,
        },
    }
    return _sanitize_public_payload(payload)


def _failure_summary(payload: dict[str, Any], *, limit: int = 32) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []

    def visit(path: str, value: Any) -> None:
        if len(failures) >= limit:
            return
        if isinstance(value, dict):
            if value.get("ok") is False:
                entry: dict[str, Any] = {"path": path, "ok": False}
                for key in (
                    "verdict",
                    "errors",
                    "missing",
                    "blockers",
                    "reasons",
                    "warnings",
                    "manual_review",
                    "returncode",
                ):
                    if key in value:
                        entry[key] = value.get(key)
                failures.append(_sanitize_public_payload(entry))
            for key, child in value.items():
                visit(f"{path}.{key}" if path else str(key), child)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(f"{path}[{index}]", child)

    visit("", payload)
    if len(failures) >= limit:
        failures.append({"path": "<truncated>", "reason": f"showing first {limit} failed nodes"})
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rendered abyss-stack runtime config as an OS Abyss artifact bundle.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--subject", type=Path, default=DEFAULT_SUBJECT)
    parser.add_argument("--bundle-dir", type=Path, default=DEFAULT_BUNDLE_DIR)
    parser.add_argument("--registry-dir", type=Path, default=DEFAULT_REGISTRY_DIR)
    parser.add_argument("--subject-store-root", type=Path, default=DEFAULT_SUBJECT_STORE_ROOT)
    parser.add_argument("--no-clean", action="store_true", help="do not remove the previous generated bundle directory first")
    parser.add_argument("--json", action="store_true", help="print the full validation payload")
    args = parser.parse_args()

    manifest = args.manifest if args.manifest.is_absolute() else REPO_ROOT / args.manifest
    subject = args.subject if args.subject.is_absolute() else REPO_ROOT / args.subject
    bundle_dir = args.bundle_dir if args.bundle_dir.is_absolute() else REPO_ROOT / args.bundle_dir
    registry_dir = args.registry_dir if args.registry_dir.is_absolute() else REPO_ROOT / args.registry_dir
    subject_store_root = (
        args.subject_store_root if args.subject_store_root.is_absolute() else REPO_ROOT / args.subject_store_root
    )
    payload = validate_bundle(manifest, subject, bundle_dir, registry_dir, subject_store_root, clean=not args.no_clean)
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif payload["ok"]:
        print(
            "[ok] abyss-machine runtime config artifact bundle verified: "
            f"{payload['bundle_dir']} ({', '.join(payload['verified_controls'])}; registry={payload['registry_dir']})"
        )
    else:
        print(
            json.dumps(
                {
                    "ok": False,
                    "schema": "abyss_stack_runtime_config_artifact_bundle_failure_summary_v1",
                    "bundle_dir": payload.get("bundle_dir"),
                    "registry_dir": payload.get("registry_dir"),
                    "abyss_machine_repo_root": payload.get("abyss_machine_repo_root"),
                    "verified_controls": payload.get("verified_controls"),
                    "failure_summary": _failure_summary(payload),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
