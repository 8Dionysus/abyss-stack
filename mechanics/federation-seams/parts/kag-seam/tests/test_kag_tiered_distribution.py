from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[5]
PART_ROOT = REPO_ROOT / "mechanics" / "federation-seams" / "parts" / "kag-seam"
sys.path.insert(0, str(PART_ROOT))

from kag_runtime.distribution import (  # noqa: E402
    COMPOSITION_ARTIFACT_CLASS,
    COMPOSITION_SCHEMA,
    CURRENT_STATE_SCHEMA,
    DistributionError,
    OWNER_RELEASE_ARTIFACT_CLASS,
    OWNER_RELEASE_SCHEMA,
    PUBLIC_ACCESS_POLICY,
    TRUST_GATE_SCHEMA,
    ZERO_DIGEST,
    activate_composition,
    distribution_status,
    load_trusted_composition,
    load_trusted_owner_family,
    materialize_owner_family,
    rollback_owner,
)


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_uri(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _identity_digest(
    payload: dict[str, Any],
    field: str,
    *,
    excluded: tuple[str, ...] = (),
) -> str:
    candidate = copy.deepcopy(payload)
    candidate[field]["content_digest"] = ZERO_DIGEST
    for key in excluded:
        candidate.pop(key, None)
    return _sha256_uri(_canonical_bytes(candidate))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _object(content: bytes, *, kind: str, range_value: str) -> dict[str, Any]:
    digest = _sha256_uri(content)
    token = digest.removeprefix("sha256:")
    return {
        "kind": kind,
        "range": range_value,
        "content_digest": digest,
        "bytes": len(content),
        "records": 1,
        "placement": "git_hot" if kind == "source" else "artifact_cold",
        "object_key": f"objects/sha256/{token[:2]}/{token}",
    }


def _trust_gate(
    root: Path,
    *,
    artifact_class: str,
    owner: str,
    source_ref: str,
    content_digest: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "schema": TRUST_GATE_SCHEMA,
        "verdict": "allow",
        "artifact_class": artifact_class,
        "consumer_intent": "runtime",
        "subject_digest": "sha256:" + ("f" * 64),
        "record_id": "registry-record:" + owner,
        "blockers": [],
        "record": {
            "artifact_class": artifact_class,
            "source_repo": owner,
            "source_ref": source_ref,
            "access_policy": PUBLIC_ACCESS_POLICY,
            "lifecycle_state": "release-ready",
            "terminal_state": False,
            "trust_root_mode": "public_release",
            "external_artifact_identity": {
                "content_digest": content_digest,
            },
        },
        "inspected_claims": {
            "artifact_subject_store": {
                "ok": True,
                "path": str(root.resolve()),
                "aggregate_digest": "sha256:" + ("f" * 64),
            }
        },
    }


def write_family(
    root: Path,
    owner: str,
    *,
    version: int = 1,
    packed_cold: bool = False,
) -> Path:
    root.mkdir(parents=True)
    source_ref = "commit:" + f"{version:040x}"
    hot_content = f"{owner}:source:{version}\n".encode()
    cold_content = f"{owner}:anchor:{version}\n".encode()
    hot = _object(hot_content, kind="source", range_value="0")
    cold = _object(cold_content, kind="anchor", range_value="a")
    packs: list[dict[str, Any]] = []
    pack_entries: list[dict[str, Any]] = []
    if packed_cold:
        pack_digest = _sha256_uri(cold_content)
        pack_token = pack_digest.removeprefix("sha256:")
        pack_key = f"packs/sha256/{pack_token[:2]}/{pack_token}.pack"
        packs.append(
            {
                "pack_digest": pack_digest,
                "object_key": pack_key,
                "bytes": len(cold_content),
                "objects": 1,
            }
        )
        pack_entries.append(
            {
                "kind": "anchor",
                "range": "a",
                "object_digest": cold["content_digest"],
                "pack_digest": pack_digest,
                "offset": 0,
                "length": len(cold_content),
            }
        )
        cold["pack"] = {
            "pack_digest": pack_digest,
            "offset": 0,
            "length": len(cold_content),
        }
        pack_path = root / pack_key
        pack_path.parent.mkdir(parents=True)
        pack_path.write_bytes(cold_content)

    corpus = {
        "schema_version": "aoa-repo-local-kag-corpus-manifest-v1",
        "repo": {"name": owner},
        "corpus_identity": {
            "content_digest": ZERO_DIGEST,
            "source_snapshot": _sha256_uri(f"{owner}:{version}".encode()),
        },
        "objects": [
            {
                key: value
                for key, value in item.items()
                if key in {"kind", "range", "content_digest", "bytes", "records"}
            }
            for item in (hot, cold)
        ],
    }
    corpus_digest = _sha256_uri(
        _canonical_bytes(
            {
                "owner": corpus["repo"],
                "source_snapshot": corpus["corpus_identity"][
                    "source_snapshot"
                ],
                "epochs": None,
                "partitioning": None,
                "normalization": None,
                "source_index_header": None,
                "compatibility": None,
                "objects": corpus["objects"],
            }
        )
    )
    corpus["corpus_identity"]["content_digest"] = corpus_digest
    distribution = {
        "schema_version": "aoa-repo-local-kag-distribution-manifest-v1",
        "repo": {"name": owner},
        "distribution_identity": {
            "local_id": "family:repo-local:tiered-distribution",
            "artifact_kind": "repo_local_kag_distribution",
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
        },
        "corpus_manifest": {"content_digest": corpus_digest},
        "hot_profile": {"content_digest": ZERO_DIGEST},
        "artifact_locators": {"content_digest": ZERO_DIGEST},
        "transport": {"pack_index_digest": ZERO_DIGEST},
    }
    hot_profile = {
        "schema_version": "aoa-repo-local-kag-hot-profile-v1",
        "repo": {"name": owner},
        "profile_identity": {
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
        },
        "selection": {"include_record_kinds": ["source"]},
    }
    hot_profile["profile_identity"]["content_digest"] = _identity_digest(
        hot_profile, "profile_identity"
    )
    locator_manifest = {
        "schema_version": "aoa-kag-artifact-locator-v1",
        "repo": {"name": owner},
        "locator_identity": {
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
        },
        "locators": [],
    }
    locator_manifest["locator_identity"]["content_digest"] = _identity_digest(
        locator_manifest, "locator_identity"
    )
    pack_index = {
        "schema_version": "aoa-kag-pack-index-v1",
        "repo": {"name": owner},
        "pack_index_identity": {
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
        },
        "packs": packs,
        "entries": pack_entries,
    }
    pack_index["pack_index_identity"]["content_digest"] = _identity_digest(
        pack_index, "pack_index_identity"
    )
    distribution["hot_profile"]["content_digest"] = hot_profile[
        "profile_identity"
    ]["content_digest"]
    distribution["artifact_locators"]["content_digest"] = locator_manifest[
        "locator_identity"
    ]["content_digest"]
    distribution["transport"]["pack_index_digest"] = pack_index[
        "pack_index_identity"
    ]["content_digest"]
    distribution["distribution_identity"]["content_digest"] = _identity_digest(
        distribution, "distribution_identity"
    )
    distribution_digest = distribution["distribution_identity"]["content_digest"]
    release = {
        "schema_version": OWNER_RELEASE_SCHEMA,
        "repo": {"name": owner, "git_ref": source_ref},
        "release_identity": {
            "artifact_class": OWNER_RELEASE_ARTIFACT_CLASS,
            "artifact_kind": OWNER_RELEASE_ARTIFACT_CLASS,
            "abi_epoch": OWNER_RELEASE_SCHEMA,
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
            "distribution_digest": distribution_digest,
        },
        "source": {
            "owner": owner,
            "ref": source_ref,
            "snapshot": corpus["corpus_identity"]["source_snapshot"],
        },
        "objects": [hot, cold],
        "packs": packs,
        "manifests": {
            "corpus_digest": corpus_digest,
            "distribution_digest": distribution_digest,
            "hot_profile_digest": hot_profile["profile_identity"][
                "content_digest"
            ],
            "locator_digest": locator_manifest["locator_identity"][
                "content_digest"
            ],
            "pack_index_digest": pack_index["pack_index_identity"][
                "content_digest"
            ],
        },
        "provenance": {"verification_receipt": f"fixture:{owner}:{version}"},
        "lifecycle": {
            "state": "release-ready",
            "revoked": False,
            "supersedes": "",
            "rollback_to": "",
        },
        "signature": {
            "algorithm": "ecdsa-p256-sha256",
            "subject_digest": ZERO_DIGEST,
            "signature_ref": "trust/kag-identity.sigstore.json",
            "verification_state": "verified",
        },
    }
    release_digest = _identity_digest(
        release, "release_identity", excluded=("signature",)
    )
    release["release_identity"]["content_digest"] = release_digest
    release["signature"]["subject_digest"] = release_digest
    bundle = {
        "schema_version": "aoa-kag-portable-family-bundle-v1",
        "bundle_identity": {
            "content_digest": ZERO_DIGEST,
            "corpus_digest": corpus_digest,
            "distribution_digest": distribution_digest,
            "release_digest": release_digest,
        },
        "network_required": False,
    }
    bundle["bundle_identity"]["content_digest"] = _identity_digest(
        bundle, "bundle_identity"
    )

    for item, content in ((hot, hot_content), (cold, cold_content)):
        if packed_cold and item is cold:
            continue
        path = root / item["object_key"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    _write_json(root / "owner-family-release.json", release)
    _write_json(root / "bundle.manifest.json", bundle)
    _write_json(root / "kag/indexes/corpus.manifest.json", corpus)
    _write_json(root / "kag/indexes/index_family.manifest.json", distribution)
    _write_json(root / "kag/indexes/hot_profile.json", hot_profile)
    _write_json(
        root / "kag/indexes/artifact_locators.json", locator_manifest
    )
    _write_json(root / "pack-index.json", pack_index)
    gate_path = root / "trust-gate.json"
    _write_json(
        gate_path,
        _trust_gate(
            root,
            artifact_class=OWNER_RELEASE_ARTIFACT_CLASS,
            owner=owner,
            source_ref=source_ref,
            content_digest=release_digest,
        ),
    )
    return gate_path


def write_composition(root: Path, owner_states: list[dict[str, Any]]) -> Path:
    root.mkdir(parents=True)
    owners = [
        {
            "owner": item["owner"],
            "source_ref": item["source_ref"],
            "corpus_digest": item["corpus_digest"],
            "release_digest": item["release_digest"],
            "distribution_digest": item["distribution_digest"],
            "verification_state": "verified",
        }
        for item in owner_states
    ]
    payload = {
        "schema_version": COMPOSITION_SCHEMA,
        "composition_identity": {
            "artifact_class": COMPOSITION_ARTIFACT_CLASS,
            "abi_epoch": COMPOSITION_SCHEMA,
            "content_digest": ZERO_DIGEST,
            "schema_epoch": "repo-local-kag-corpus-v1",
            "canonicalization_epoch": "portable-record-normalization-v3",
        },
        "federation": {
            "owner_count": 24,
            "membership_digest": _sha256_uri(
                _canonical_bytes(sorted(item["owner"] for item in owners))
            ),
        },
        "owners": owners,
        "aggregate": {
            "git_hot_bytes": 24,
            "corpus_total_bytes": 48,
            "artifact_unique_bytes": 24,
        },
        "unresolved_references": {},
        "provenance": {
            "builder_owner": "aoa-kag",
            "trust_owner": "abyss-machine",
        },
        "signature": {
            "algorithm": "ecdsa-p256-sha256",
            "key_id": "fixture",
            "subject_digest": ZERO_DIGEST,
            "signature_ref": "trust/kag-identity.sigstore.json",
            "verification_state": "verified",
        },
    }
    digest = _identity_digest(
        payload, "composition_identity", excluded=("signature",)
    )
    payload["composition_identity"]["content_digest"] = digest
    payload["signature"]["subject_digest"] = digest
    _write_json(root / "os-kag-composition.json", payload)
    gate_path = root / "trust-gate.json"
    _write_json(
        gate_path,
        _trust_gate(
            root,
            artifact_class=COMPOSITION_ARTIFACT_CLASS,
            owner="aoa-kag",
            source_ref="commit:" + ("a" * 40),
            content_digest=digest,
        ),
    )
    return gate_path


class TieredDistributionTest(unittest.TestCase):
    def test_inner_manifest_identity_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "family"
            gate = write_family(root, "owner-a")
            corpus_path = root / "kag/indexes/corpus.manifest.json"
            corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
            corpus["objects"][0]["records"] = 2
            _write_json(corpus_path, corpus)

            with self.assertRaisesRegex(
                DistributionError, "corpus identity digest mismatch"
            ):
                load_trusted_owner_family(root, gate, expected_owner="owner-a")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime = self.root / "runtime"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_full_hydration_reuses_objects_and_rejects_corrupt_local_cas(self) -> None:
        family_root = self.root / "family"
        gate = write_family(family_root, "owner-a")
        family = load_trusted_owner_family(
            family_root, gate, expected_owner="owner-a"
        )

        first = materialize_owner_family(family, self.runtime)
        second = materialize_owner_family(family, self.runtime)

        self.assertEqual(first["delivery_state"], "complete")
        self.assertEqual(first["cache"]["objects_added"], 2)
        self.assertEqual(first["cache"]["network_fetch_bytes"], 0)
        self.assertEqual(second["cache"]["objects_added"], 0)
        self.assertEqual(second["cache"]["objects_reused"], 2)
        self.assertEqual(second["projection_impact"]["class"], "none")
        self.assertEqual(
            distribution_status(self.runtime)["schema_version"],
            CURRENT_STATE_SCHEMA,
        )

        object_key = family.objects[0]["object_key"]
        (self.runtime / "cas" / object_key).write_text(
            "corrupt\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(DistributionError, "local CAS object"):
            materialize_owner_family(family, self.runtime)

    def test_selective_hot_hydration_stays_candidate_then_full_promotes(self) -> None:
        family_root = self.root / "selective-family"
        gate = write_family(family_root, "owner-a")
        family = load_trusted_owner_family(family_root, gate)

        partial = materialize_owner_family(
            family, self.runtime, kinds=["source"]
        )
        owner_root = self.runtime / "distribution/owners/owner-a"
        self.assertEqual(partial["delivery_state"], "hot_only")
        self.assertFalse((owner_root / "current.json").exists())
        self.assertTrue((owner_root / "candidate.json").is_file())

        complete = materialize_owner_family(family, self.runtime)
        self.assertEqual(complete["delivery_state"], "complete")
        self.assertTrue((owner_root / "current.json").is_file())
        self.assertFalse((owner_root / "candidate.json").exists())

    def test_pack_range_extracts_exact_object_and_rejects_corruption(self) -> None:
        family_root = self.root / "packed-family"
        gate = write_family(family_root, "owner-a", packed_cold=True)
        family = load_trusted_owner_family(family_root, gate)

        result = materialize_owner_family(family, self.runtime)
        self.assertEqual(result["delivery_state"], "complete")

        second_root = self.root / "packed-corrupt"
        second_gate = write_family(
            second_root, "owner-b", packed_cold=True
        )
        second = load_trusted_owner_family(second_root, second_gate)
        pack_key = next(iter(second.packs.values()))["object_key"]
        (second_root / pack_key).write_text("corrupt\n", encoding="utf-8")
        with self.assertRaisesRegex(DistributionError, "corrupted transport pack"):
            materialize_owner_family(second, self.runtime)

    def test_source_store_and_access_identity_are_fail_closed(self) -> None:
        family_root = self.root / "untrusted-family"
        gate_path = write_family(family_root, "owner-a")
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        gate["record"]["access_policy"] = "restricted-kag"
        _write_json(gate_path, gate)

        with self.assertRaisesRegex(DistributionError, "access policy"):
            load_trusted_owner_family(family_root, gate_path)

    def test_last_good_owner_rollback_preserves_content_addressed_state(self) -> None:
        first_root = self.root / "owner-v1"
        first_gate = write_family(first_root, "owner-a", version=1)
        first = load_trusted_owner_family(first_root, first_gate)
        materialize_owner_family(first, self.runtime)

        second_root = self.root / "owner-v2"
        second_gate = write_family(second_root, "owner-a", version=2)
        second = load_trusted_owner_family(second_root, second_gate)
        materialize_owner_family(second, self.runtime)

        result = rollback_owner(self.runtime, "owner-a")
        self.assertEqual(result["to_release_digest"], first.release_digest)
        current = json.loads(
            (
                self.runtime
                / "distribution/owners/owner-a/current.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(current["release_digest"], first.release_digest)
        self.assertEqual(
            current["projection_impact"]["affected_owners"], ["owner-a"]
        )

    def test_verified_24_owner_composition_is_the_only_complete_os_state(self) -> None:
        owner_states: list[dict[str, Any]] = []
        for index in range(24):
            owner = f"owner-{index:02d}"
            family_root = self.root / "families" / owner
            gate = write_family(family_root, owner, version=index + 1)
            family = load_trusted_owner_family(family_root, gate)
            materialize_owner_family(family, self.runtime)
            owner_states.append(
                json.loads(
                    (
                        self.runtime
                        / "distribution"
                        / "owners"
                        / owner
                        / "current.json"
                    ).read_text(encoding="utf-8")
                )
            )
        self.assertEqual(
            distribution_status(self.runtime)["state"], "rebuild_required"
        )

        composition_root = self.root / "composition"
        gate_path = write_composition(composition_root, owner_states)
        composition, trust = load_trusted_composition(
            composition_root, gate_path
        )
        result = activate_composition(composition, trust, self.runtime)

        self.assertEqual(result["owner_count"], 24)
        self.assertEqual(result["aggregate_state"], "complete")
        self.assertEqual(distribution_status(self.runtime)["state"], "complete")


if __name__ == "__main__":
    unittest.main()
