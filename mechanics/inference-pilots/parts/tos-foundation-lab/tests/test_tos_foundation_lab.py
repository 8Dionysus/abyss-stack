from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import signal
import tarfile
import tempfile
import zipfile
from pathlib import Path

import pytest


PART_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PART_ROOT / "tos_foundation_lab.py"
SPEC = importlib.util.spec_from_file_location("tos_foundation_lab", MODULE_PATH)
assert SPEC and SPEC.loader
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)

NATIVE_MODULE_PATH = PART_ROOT / "native_structure.py"
NATIVE_SPEC = importlib.util.spec_from_file_location("native_structure_test", NATIVE_MODULE_PATH)
assert NATIVE_SPEC and NATIVE_SPEC.loader
native = importlib.util.module_from_spec(NATIVE_SPEC)
NATIVE_SPEC.loader.exec_module(native)

LEXICAL_MODULE_PATH = PART_ROOT / "lexical_retrieval.py"
LEXICAL_SPEC = importlib.util.spec_from_file_location("lexical_retrieval_test", LEXICAL_MODULE_PATH)
assert LEXICAL_SPEC and LEXICAL_SPEC.loader
lexical = importlib.util.module_from_spec(LEXICAL_SPEC)
LEXICAL_SPEC.loader.exec_module(lexical)

GRAPH_MODULE_PATH = PART_ROOT / "canonical_graph.py"
GRAPH_SPEC = importlib.util.spec_from_file_location("canonical_graph_test", GRAPH_MODULE_PATH)
assert GRAPH_SPEC and GRAPH_SPEC.loader
canonical_graph = importlib.util.module_from_spec(GRAPH_SPEC)
GRAPH_SPEC.loader.exec_module(canonical_graph)

SEMANTIC_MODULE_PATH = PART_ROOT / "semantic_retrieval.py"
SEMANTIC_SPEC = importlib.util.spec_from_file_location("semantic_retrieval_test", SEMANTIC_MODULE_PATH)
assert SEMANTIC_SPEC and SEMANTIC_SPEC.loader
semantic = importlib.util.module_from_spec(SEMANTIC_SPEC)
SEMANTIC_SPEC.loader.exec_module(semantic)

GRANITE_BRIDGE_MODULE_PATH = PART_ROOT / "granite_embedding_bridge.py"
GRANITE_BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "granite_embedding_bridge_test", GRANITE_BRIDGE_MODULE_PATH
)
assert GRANITE_BRIDGE_SPEC and GRANITE_BRIDGE_SPEC.loader
granite_bridge = importlib.util.module_from_spec(GRANITE_BRIDGE_SPEC)
GRANITE_BRIDGE_SPEC.loader.exec_module(granite_bridge)

GRANITE_MODULE_PATH = PART_ROOT / "granite_retrieval.py"
GRANITE_SPEC = importlib.util.spec_from_file_location("granite_retrieval_test", GRANITE_MODULE_PATH)
assert GRANITE_SPEC and GRANITE_SPEC.loader
granite = importlib.util.module_from_spec(GRANITE_SPEC)
GRANITE_SPEC.loader.exec_module(granite)

NEO4J_BRIDGE_MODULE_PATH = PART_ROOT / "neo4j_bridge.py"
NEO4J_BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "neo4j_bridge_test", NEO4J_BRIDGE_MODULE_PATH
)
assert NEO4J_BRIDGE_SPEC and NEO4J_BRIDGE_SPEC.loader
neo4j_bridge = importlib.util.module_from_spec(NEO4J_BRIDGE_SPEC)
NEO4J_BRIDGE_SPEC.loader.exec_module(neo4j_bridge)

NEO4J_GRAPH_MODULE_PATH = PART_ROOT / "neo4j_graph.py"
NEO4J_GRAPH_SPEC = importlib.util.spec_from_file_location(
    "neo4j_graph_test", NEO4J_GRAPH_MODULE_PATH
)
assert NEO4J_GRAPH_SPEC and NEO4J_GRAPH_SPEC.loader
neo4j_graph = importlib.util.module_from_spec(NEO4J_GRAPH_SPEC)
NEO4J_GRAPH_SPEC.loader.exec_module(neo4j_graph)

OXIGRAPH_BRIDGE_MODULE_PATH = PART_ROOT / "oxigraph_bridge.py"
OXIGRAPH_BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "oxigraph_bridge_test", OXIGRAPH_BRIDGE_MODULE_PATH
)
assert OXIGRAPH_BRIDGE_SPEC and OXIGRAPH_BRIDGE_SPEC.loader
oxigraph_bridge = importlib.util.module_from_spec(OXIGRAPH_BRIDGE_SPEC)
OXIGRAPH_BRIDGE_SPEC.loader.exec_module(oxigraph_bridge)

OXIGRAPH_GRAPH_MODULE_PATH = PART_ROOT / "oxigraph_graph.py"
OXIGRAPH_GRAPH_SPEC = importlib.util.spec_from_file_location(
    "oxigraph_graph_test", OXIGRAPH_GRAPH_MODULE_PATH
)
assert OXIGRAPH_GRAPH_SPEC and OXIGRAPH_GRAPH_SPEC.loader
oxigraph_graph = importlib.util.module_from_spec(OXIGRAPH_GRAPH_SPEC)
OXIGRAPH_GRAPH_SPEC.loader.exec_module(oxigraph_graph)

OCR_RENDER_MODULE_PATH = PART_ROOT / "ocr_render.py"
OCR_RENDER_SPEC = importlib.util.spec_from_file_location("ocr_render_test", OCR_RENDER_MODULE_PATH)
assert OCR_RENDER_SPEC and OCR_RENDER_SPEC.loader
ocr_render = importlib.util.module_from_spec(OCR_RENDER_SPEC)
OCR_RENDER_SPEC.loader.exec_module(ocr_render)

RUNTIME_MANIFEST_MODULE_PATH = PART_ROOT / "runtime_manifest.py"
RUNTIME_MANIFEST_SPEC = importlib.util.spec_from_file_location(
    "runtime_manifest_test", RUNTIME_MANIFEST_MODULE_PATH
)
assert RUNTIME_MANIFEST_SPEC and RUNTIME_MANIFEST_SPEC.loader
runtime_manifest = importlib.util.module_from_spec(RUNTIME_MANIFEST_SPEC)
RUNTIME_MANIFEST_SPEC.loader.exec_module(runtime_manifest)

TESSERACT_MODULE_PATH = PART_ROOT / "tesseract_ocr.py"
TESSERACT_SPEC = importlib.util.spec_from_file_location("tesseract_ocr_test", TESSERACT_MODULE_PATH)
assert TESSERACT_SPEC and TESSERACT_SPEC.loader
tesseract_ocr = importlib.util.module_from_spec(TESSERACT_SPEC)
TESSERACT_SPEC.loader.exec_module(tesseract_ocr)

TESSERACT_RUNTIME_MODULE_PATH = PART_ROOT / "tesseract_runtime.py"
TESSERACT_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "tesseract_runtime_test", TESSERACT_RUNTIME_MODULE_PATH
)
assert TESSERACT_RUNTIME_SPEC and TESSERACT_RUNTIME_SPEC.loader
tesseract_runtime = importlib.util.module_from_spec(TESSERACT_RUNTIME_SPEC)
TESSERACT_RUNTIME_SPEC.loader.exec_module(tesseract_runtime)

KRAKEN_PARTY_RUNTIME_MODULE_PATH = PART_ROOT / "kraken_party_runtime.py"
KRAKEN_PARTY_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "kraken_party_runtime_test", KRAKEN_PARTY_RUNTIME_MODULE_PATH
)
assert KRAKEN_PARTY_RUNTIME_SPEC and KRAKEN_PARTY_RUNTIME_SPEC.loader
kraken_party_runtime = importlib.util.module_from_spec(KRAKEN_PARTY_RUNTIME_SPEC)
KRAKEN_PARTY_RUNTIME_SPEC.loader.exec_module(kraken_party_runtime)

KRAKEN_PARTY_OCR_MODULE_PATH = PART_ROOT / "kraken_party_ocr.py"
KRAKEN_PARTY_OCR_SPEC = importlib.util.spec_from_file_location(
    "kraken_party_ocr_test", KRAKEN_PARTY_OCR_MODULE_PATH
)
assert KRAKEN_PARTY_OCR_SPEC and KRAKEN_PARTY_OCR_SPEC.loader
kraken_party_ocr = importlib.util.module_from_spec(KRAKEN_PARTY_OCR_SPEC)
KRAKEN_PARTY_OCR_SPEC.loader.exec_module(kraken_party_ocr)

PADDLE_OCR_RUNTIME_MODULE_PATH = PART_ROOT / "paddle_ocr_runtime.py"
PADDLE_OCR_RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "paddle_ocr_runtime_test", PADDLE_OCR_RUNTIME_MODULE_PATH
)
assert PADDLE_OCR_RUNTIME_SPEC and PADDLE_OCR_RUNTIME_SPEC.loader
paddle_ocr_runtime = importlib.util.module_from_spec(PADDLE_OCR_RUNTIME_SPEC)
PADDLE_OCR_RUNTIME_SPEC.loader.exec_module(paddle_ocr_runtime)

PADDLE_OCR_BRIDGE_MODULE_PATH = PART_ROOT / "paddle_ocr_bridge.py"
PADDLE_OCR_BRIDGE_SPEC = importlib.util.spec_from_file_location(
    "paddle_ocr_bridge_test", PADDLE_OCR_BRIDGE_MODULE_PATH
)
assert PADDLE_OCR_BRIDGE_SPEC and PADDLE_OCR_BRIDGE_SPEC.loader
paddle_ocr_bridge = importlib.util.module_from_spec(PADDLE_OCR_BRIDGE_SPEC)
PADDLE_OCR_BRIDGE_SPEC.loader.exec_module(paddle_ocr_bridge)

PADDLE_OCR_MODULE_PATH = PART_ROOT / "paddle_ocr.py"
PADDLE_OCR_SPEC = importlib.util.spec_from_file_location(
    "paddle_ocr_test", PADDLE_OCR_MODULE_PATH
)
assert PADDLE_OCR_SPEC and PADDLE_OCR_SPEC.loader
paddle_ocr = importlib.util.module_from_spec(PADDLE_OCR_SPEC)
PADDLE_OCR_SPEC.loader.exec_module(paddle_ocr)

TRANSLATION_SOURCE_MODULE_PATH = PART_ROOT / "translation_source.py"
TRANSLATION_SOURCE_SPEC = importlib.util.spec_from_file_location(
    "translation_source_test", TRANSLATION_SOURCE_MODULE_PATH
)
assert TRANSLATION_SOURCE_SPEC and TRANSLATION_SOURCE_SPEC.loader
translation_source = importlib.util.module_from_spec(TRANSLATION_SOURCE_SPEC)
TRANSLATION_SOURCE_SPEC.loader.exec_module(translation_source)

TRANSLATION_SOURCE_REVIEW_MODULE_PATH = PART_ROOT / "translation_source_review.py"
TRANSLATION_SOURCE_REVIEW_SPEC = importlib.util.spec_from_file_location(
    "translation_source_review_test", TRANSLATION_SOURCE_REVIEW_MODULE_PATH
)
assert TRANSLATION_SOURCE_REVIEW_SPEC and TRANSLATION_SOURCE_REVIEW_SPEC.loader
translation_source_review = importlib.util.module_from_spec(TRANSLATION_SOURCE_REVIEW_SPEC)
TRANSLATION_SOURCE_REVIEW_SPEC.loader.exec_module(translation_source_review)


def thermal_owner(
    temperature_c: float = 102.0,
    *,
    resource_allowed: bool = True,
    workload_class: str = "medium",
    workload_kind: str = "indexing",
) -> dict[str, object]:
    return {
        "owner": "abyss-machine",
        "workload_class": workload_class,
        "workload_kind": workload_kind,
        "temperature_c_max": temperature_c,
        "cooling_status": {
            "command_available": True,
            "returncode": 0,
            "allowed": False,
            "payload": {
                "temperature": {
                    "summary": {"temperature_c_max": temperature_c},
                    "episode": {
                        "band": "active_high" if temperature_c <= 105 else "watch",
                        "thresholds": {"watch_c": 105.0, "critical_c": 109.0},
                    },
                }
            },
        },
        "resource_plan": {
            "command_available": True,
            "returncode": 0,
            "allowed": resource_allowed,
            "decision": "allow" if resource_allowed else "defer",
            "payload": {},
        },
    }


def test_frozen_suite_and_schemas_validate() -> None:
    assert lab.validate_suite() == []


def test_running_service_inventory_keeps_container_and_compose_names() -> None:
    records = [
        {
            "Names": ["abyss_qdrant_1"],
            "Labels": {
                "com.docker.compose.service": "qdrant",
                "io.podman.compose.service": "qdrant",
            },
        },
        {"Names": ["rag-api"], "Labels": {}},
    ]

    assert lab._service_names_from_podman_records(records) == [
        "abyss_qdrant_1",
        "qdrant",
        "rag-api",
    ]


def test_every_experiment_has_exact_abc_and_all_cost_dimensions() -> None:
    suite = lab.load_suite()
    assert len(suite["experiments"]) >= 9
    for experiment in suite["experiments"]:
        assert {variant["label"] for variant in experiment["variants"]} == {"A", "B", "C"}
        assert {metric["dimension"] for metric in experiment["metrics"]} >= {
            "quality",
            "speed",
            "machine-cost",
            "human-cost",
            "traceability",
        }


def test_golden_kernel_transfer_spec_covers_benefit_and_ontology_risk() -> None:
    experiment = lab.find_experiment(
        lab.load_suite(),
        "tos-golden-kernel-transfer-v1",
    )

    assert experiment["sample_plan_ref"].endswith("/transfer-samples.json")
    assert [variant["label"] for variant in experiment["variants"]] == ["A", "B", "C"]
    assert [
        variant["comparison_role"] for variant in experiment["variants"]
    ] == [
        "no golden kernel",
        "contracts and format examples only",
        "reviewed Zarathustra golden-kernel examples",
    ]
    metric_ids = {metric["metric_id"] for metric in experiment["metrics"]}
    assert {
        "annotation-accuracy",
        "zarathustra-overfit-rate",
        "hallucinated-relation-rate",
        "reusable-sign-utility",
        "tasks-per-minute",
        "prompt-tokens",
        "correction-minutes",
        "traceable-proposal-rate",
    } <= metric_ids
    assert any(
        "title-page scouting units are ineligible" in precondition
        for precondition in experiment["preconditions"]
    )
    assert any(
        "human-accepted sign or translation packets" in precondition
        for precondition in experiment["preconditions"]
    )
    assert "negative transfer preserved as a first-class result" in experiment[
        "promotion_conditions"
    ]


def test_semantic_and_llm_specs_require_source_gated_tree_plans() -> None:
    suite = lab.load_suite()
    semantic = lab.find_experiment(suite, "tos-semantic-annotation-v1")
    llm = lab.find_experiment(suite, "tos-llm-assistance-v1")

    assert semantic["sample_plan_ref"].endswith("/semantic-samples.json")
    assert llm["sample_plan_ref"].endswith("/llm-tasks.json")
    for experiment in (semantic, llm):
        assert any(
            "30/30 accepted source units and 15/15 double-checked human gold units"
            in precondition
            for precondition in experiment["preconditions"]
        )
        assert any(
            "20 content-bearing tasks" in precondition
            and "10 random and 10 hard" in precondition
            for precondition in experiment["preconditions"]
        )


def test_ocr_experiment_uses_exact_visual_witnesses_and_honest_gold_gate() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-ocr-foundation-v1")

    assert experiment["sample_plan_ref"].endswith("/ocr-visual-samples.json")
    assert (
        "tos.item.friedrich-nietzsche.also-sprach-zarathustra.de-naumann-1893.internet-archive-image-container-pdf"
        in experiment["source_refs"]
    )
    assert all("internet-archive-cornell-auto-epub" not in ref for ref in experiment["source_refs"])
    assert experiment["reference_witness_reveal_stage"] == "after-independent-drafts-frozen"
    assert any(
        "formal CER, WER, correction-time, and quality-winner claims remain blocked"
        in precondition
        for precondition in experiment["preconditions"]
    )

    variant_a = lab.find_variant(experiment, "A")
    variant_b = lab.find_variant(experiment, "B")
    variant_c = lab.find_variant(experiment, "C")
    assert "Tesseract 5.5.2" in variant_a["implementation"]
    assert "OCRmyPDF 17.8.1" in variant_a["implementation"]
    assert variant_a["required_commands"] == ["tesseract"]
    assert "Kraken 7.0.2" in variant_b["implementation"]
    assert "10.5281/zenodo.20642057" in variant_b["model"]
    assert variant_b["required_commands"] == ["kraken", "party"]
    assert "PaddleOCR 3.7.0" in variant_c["implementation"]
    assert "PaddleX 3.7.2" in variant_c["implementation"]
    assert "eslav_PP-OCRv5_mobile_rec" in variant_c["model"]
    assert "PP-OCRv6 is excluded" in variant_c["model"]


def test_preflight_blocks_missing_software_and_storage_denial() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-ocr-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    facts = {
        "captured_at_utc": "2026-07-22T12:00:00+00:00",
        "srv_free_bytes": 100 * 1024**3,
        "memory_available_bytes": 16 * 1024**3,
        "load_1m": 1.0,
        "thermal_owner": thermal_owner(workload_class="heavy", workload_kind="ai"),
        "commands": {"ocrmypdf": {"path": None}, "tesseract": {"path": None}},
        "running_services": [],
        "devices": {"CPU": True, "GPU": True, "NPU": True, "Vulkan": True},
    }
    storage = {"allowed": False, "reason": "pressure"}

    receipt = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight=storage,
    )

    assert receipt["decision"] == "blocked"
    failed = {check["name"] for check in receipt["checks"] if not check["passed"]}
    assert {
        "command:tesseract",
        "runtime-admission",
        "candidate-installation",
        "storage-owner-preflight",
    } <= failed


def test_verified_runtime_admission_satisfies_requires_setup_gate() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-ocr-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    facts = {
        "captured_at_utc": "2026-07-22T12:00:00+00:00",
        "srv_free_bytes": 100 * 1024**3,
        "memory_available_bytes": 16 * 1024**3,
        "load_1m": 1.0,
        "thermal_owner": thermal_owner(workload_class="heavy", workload_kind="ai"),
        "commands": {"tesseract": {"path": "/srv/abyss-machine/runtimes/test/tesseract"}},
        "running_services": [],
        "devices": {"CPU": True, "GPU": True, "NPU": True, "Vulkan": True},
    }
    admission = {
        "verified": True,
        "commands": {"tesseract": "/srv/abyss-machine/runtimes/test/tesseract"},
        "environment": {},
    }

    receipt = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight={"allowed": True},
        runtime_admission=admission,
    )

    assert receipt["decision"] == "ready"
    checks = {row["name"]: row for row in receipt["checks"]}
    assert checks["runtime-admission"]["passed"] is True
    assert checks["candidate-installation"]["passed"] is True


def test_png_header_reads_exact_rgb_ihdr_without_image_dependency() -> None:
    header = (
        ocr_render.PNG_SIGNATURE
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + (2480).to_bytes(4, "big")
        + (3508).to_bytes(4, "big")
        + bytes([8, 2, 0, 0, 0])
        + b"\x00\x00\x00\x00"
    )
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "page.png"
        path.write_bytes(header)
        assert ocr_render.png_header(path) == {
            "width_pixels": 2480,
            "height_pixels": 3508,
            "bit_depth": 8,
            "png_color_type": 2,
            "color_space": "rgb",
        }


def test_runtime_inventory_and_set_digest_cover_files_and_symlinks() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        binary = root / "bin/tesseract-real"
        binary.parent.mkdir()
        binary.write_bytes(b"runtime-binary")
        link = root / "bin/tesseract"
        os.symlink("tesseract-real", link)

        artifacts = runtime_manifest.inventory_runtime(
            root,
            roles={"bin/tesseract": "command", "bin/tesseract-real": "command-target"},
        )

        assert [row["relative_path"] for row in artifacts] == [
            "bin/tesseract",
            "bin/tesseract-real",
        ]
        assert [row["kind"] for row in artifacts] == ["symlink", "file"]
        assert runtime_manifest.artifact_set_sha256(artifacts) == runtime_manifest.artifact_set_sha256(
            list(reversed(artifacts))
        )


def test_tesseract_repeat_comparison_ignores_timing_but_not_output_drift() -> None:
    base = {
        "schema_version": "tos_tesseract_ocr_output_manifest_v1",
        "sample_plan_sha256": "a" * 64,
        "render_set_sha256": "b" * 64,
        "runtime_artifact_set_sha256": "c" * 64,
        "tesseract_version": "tesseract 5.5.2",
        "configuration": {"psm": 3},
        "recognition_set_sha256": "d" * 64,
        "samples": [
            {
                "sample_id": "sample-1",
                "elapsed_seconds": 1.0,
                "outputs": {"text": {"sha256": "e" * 64, "bytes": 12}},
            }
        ],
    }
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = root / "first/raw-output"
        second = root / "second/raw-output"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        first_payload = json.loads(json.dumps(base))
        first_payload["run_id"] = "first"
        second_payload = json.loads(json.dumps(base))
        second_payload["run_id"] = "second"
        second_payload["samples"][0]["elapsed_seconds"] = 2.0
        (first / "ocr-output-manifest.json").write_text(json.dumps(first_payload), encoding="utf-8")
        (second / "ocr-output-manifest.json").write_text(json.dumps(second_payload), encoding="utf-8")

        comparison = tesseract_ocr.compare_tesseract_runs(root / "first", root / "second")
        assert comparison["mechanically_identical"] is True

        second_payload["samples"][0]["outputs"]["text"]["sha256"] = "f" * 64
        (second / "ocr-output-manifest.json").write_text(json.dumps(second_payload), encoding="utf-8")
        drift = tesseract_ocr.compare_tesseract_runs(root / "first", root / "second")
        assert drift["mechanically_identical"] is False
        assert drift["sample_differences"] == [
            {"sample_id": "sample-1", "difference": "output-digest", "output": "text"}
        ]


def test_tesseract_runtime_lock_is_exact_and_wrapper_is_relocatable_inside_owner_tree() -> None:
    assert tesseract_runtime.EXPECTED_PACKAGES == {
        "tesseract": (
            "5.5.2-1.fc44",
            "x86_64",
            "https://packages.fedoraproject.org/pkgs/tesseract/tesseract/",
        ),
        "tesseract-libs": (
            "5.5.2-1.fc44",
            "x86_64",
            "https://packages.fedoraproject.org/pkgs/tesseract/tesseract-libs/",
        ),
        "tesseract-common": (
            "5.5.2-1.fc44",
            "noarch",
            "https://packages.fedoraproject.org/pkgs/tesseract/tesseract-common/",
        ),
        "tesseract-langpack-deu": (
            "4.1.0-12.fc44",
            "noarch",
            "https://packages.fedoraproject.org/pkgs/tesseract-tessdata/tesseract-langpack-deu/",
        ),
        "tesseract-langpack-rus": (
            "4.1.0-12.fc44",
            "noarch",
            "https://packages.fedoraproject.org/pkgs/tesseract-tessdata/tesseract-langpack-rus/",
        ),
    }
    wrapper = tesseract_runtime._wrapper_text()
    assert 'dirname "${BASH_SOURCE[0]}"' in wrapper
    assert "TESSDATA_PREFIX" in wrapper
    assert "/home/" not in wrapper and ".partial" not in wrapper


def test_kraken_party_alto_canonicalization_exposes_uuid_drift_without_text_drift() -> None:
    def alto(first_id: str, second_id: str, string_id: str) -> str:
        return f'''<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <ReadingOrder><OrderedGroup ID="order"><ElementRef ID="r1" REF="{second_id}"/><ElementRef ID="r2" REF="{first_id}"/></OrderedGroup></ReadingOrder>
  <Layout><Page ID="page" WIDTH="100" HEIGHT="200"><PrintSpace HPOS="0" VPOS="0" WIDTH="100" HEIGHT="200"><TextBlock ID="block">
    <TextLine ID="{first_id}" LANG="deu" HPOS="1" VPOS="2" WIDTH="10" HEIGHT="4"><String ID="{string_id}" CONTENT="alpha" WC="0.9"/></TextLine>
    <TextLine ID="{second_id}" LANG="deu" HPOS="1" VPOS="8" WIDTH="10" HEIGHT="4"><String ID="segment-2" CONTENT="beta" WC="0.8"/></TextLine>
  </TextBlock></PrintSpace></Page></Layout>
</alto>
'''

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = root / "first.xml"
        second = root / "second.xml"
        first.write_text(alto("uuid-a", "uuid-b", "segment-a"), encoding="utf-8")
        second.write_text(alto("uuid-x", "uuid-y", "segment-x"), encoding="utf-8")

        first_diagnostics = kraken_party_ocr._alto_diagnostics(first)
        second_diagnostics = kraken_party_ocr._alto_diagnostics(second)

        assert first.read_bytes() != second.read_bytes()
        assert first_diagnostics["canonical_sha256"] == second_diagnostics["canonical_sha256"]
        assert first_diagnostics["diplomatic_text"] == "beta\nalpha\n"
        assert first_diagnostics["reading_order_mode"] == "alto-reading-order"
        assert first_diagnostics["language_counts"] == {"deu": 2}


def test_kraken_party_repeat_comparison_separates_canonical_and_raw_byte_identity() -> None:
    outputs_first = {
        "raw_segmentation": {"sha256": "1" * 64, "canonical_sha256": "a" * 64, "bytes": 10},
        "conditioned_segmentation": {
            "sha256": "2" * 64,
            "canonical_sha256": "b" * 64,
            "bytes": 11,
        },
        "recognized_alto": {"sha256": "3" * 64, "canonical_sha256": "c" * 64, "bytes": 12},
        "diplomatic_text": {"sha256": "d" * 64, "bytes": 13},
    }
    outputs_second = json.loads(json.dumps(outputs_first))
    outputs_second["raw_segmentation"]["sha256"] = "4" * 64
    outputs_second["conditioned_segmentation"]["sha256"] = "5" * 64
    outputs_second["recognized_alto"]["sha256"] = "6" * 64
    base = {
        "sample_plan_sha256": "7" * 64,
        "render_set_sha256": "8" * 64,
        "runtime_artifact_set_sha256": "9" * 64,
        "kraken_version": kraken_party_ocr.EXPECTED_KRAKEN_VERSION,
        "party_version": kraken_party_ocr.EXPECTED_PARTY_VERSION,
        "party_model": {"sha256": kraken_party_ocr.EXPECTED_PARTY_MODEL_SHA256},
        "baseline_model": {"sha256": kraken_party_ocr.EXPECTED_BASELINE_MODEL_SHA256},
        "configuration": {"seed": 42, "deterministic": True},
        "semantic_output_set_sha256": "e" * 64,
        "samples": [{"sample_id": "sample-1", "outputs": outputs_first}],
    }
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first_root = root / "first/raw-output"
        second_root = root / "second/raw-output"
        first_root.mkdir(parents=True)
        second_root.mkdir(parents=True)
        first_payload = json.loads(json.dumps(base))
        first_payload.update({"run_id": "first", "raw_output_set_sha256": "f" * 64})
        second_payload = json.loads(json.dumps(base))
        second_payload.update({"run_id": "second", "raw_output_set_sha256": "0" * 64})
        second_payload["samples"][0]["outputs"] = outputs_second
        (first_root / "kraken-party-ocr-output-manifest.json").write_text(
            json.dumps(first_payload), encoding="utf-8"
        )
        (second_root / "kraken-party-ocr-output-manifest.json").write_text(
            json.dumps(second_payload), encoding="utf-8"
        )

        comparison = kraken_party_ocr.compare_kraken_party_runs(
            root / "first", root / "second"
        )

        assert comparison["mechanically_identical"] is True
        assert comparison["raw_byte_identical"] is False
        assert comparison["semantic_differences"] == []
        assert {row["output"] for row in comparison["raw_byte_differences"]} == {
            "raw_segmentation",
            "conditioned_segmentation",
            "recognized_alto",
        }


def test_kraken_party_decoder_saturation_guard_requires_repeated_near_cap_lines() -> None:
    safe = kraken_party_ocr._decoder_saturation_guard(
        {"decoder_saturation_line_count": 1, "max_line_characters": 360}
    )
    stopped = kraken_party_ocr._decoder_saturation_guard(
        {"decoder_saturation_line_count": 2, "max_line_characters": 362}
    )

    assert safe["triggered"] is False
    assert stopped == {
        "character_threshold": 300,
        "line_limit": 2,
        "observed_saturated_lines": 2,
        "max_line_characters": 362,
        "triggered": True,
        "boundary": (
            "mechanical near-decoder-cap guard only; it does not determine "
            "source-visible accuracy"
        ),
    }


def test_kraken_party_abort_finalizer_preserves_partial_files_and_truthful_status() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_root = Path(temporary)
        completed_root = run_root / "raw-output/sample-complete"
        partial_root = run_root / "raw-output/sample-partial"
        invocation_path = run_root / "receipts/kraken-party-ocr-invocation.json"
        completed_root.mkdir(parents=True)
        partial_root.mkdir(parents=True)
        invocation_path.parent.mkdir(parents=True)
        (completed_root / "sample.json").write_text("{}\n", encoding="utf-8")
        (partial_root / "segmentation.raw.alto.xml").write_text(
            "<alto/>\n", encoding="utf-8"
        )
        invocation_path.write_text("{}\n", encoding="utf-8")
        receipt_path = run_root / "run.receipt.json"
        receipt = {"status": "running", "sample_ids": [], "artifact_refs": [], "errors": []}

        kraken_party_ocr._finalize_aborted_receipt(
            run_root,
            receipt_path,
            receipt,
            [{"sample_id": "sample-complete"}],
            [],
            status="stopped",
            error="stopped: SIGTERM",
        )

        finalized = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert finalized["status"] == "stopped"
        assert finalized["sample_ids"] == ["sample-complete"]
        assert finalized["errors"] == [
            "stopped: SIGTERM",
            "partial-output-sample-ids: sample-partial",
        ]
        assert finalized["artifact_refs"] == [
            "raw-output/sample-complete/sample.json",
            "raw-output/sample-partial/segmentation.raw.alto.xml",
            "receipts/kraken-party-ocr-invocation.json",
        ]


def test_kraken_party_sigterm_is_typed_as_experimental_stop() -> None:
    with pytest.raises(kraken_party_ocr.KrakenPartyOcrStop, match="SIGTERM"):
        kraken_party_ocr._stop_on_sigterm(signal.SIGTERM, None)


def test_kraken_party_runtime_security_and_offline_constructor_locks_are_exact() -> None:
    assert kraken_party_runtime.PARTY_COMMIT == "c2589b1b515ed690f883c6afaef6c01ce29bf72d"
    assert kraken_party_runtime.KRAKEN_VERSION == "7.0.2"
    assert kraken_party_runtime.LIGHTNING_VERSION == "2.6.1"
    assert kraken_party_runtime.FORBIDDEN_LIGHTNING_VERSIONS == {"2.6.2", "2.6.3"}
    assert kraken_party_runtime.TORCH_VERSION == "2.10.0+cpu"
    assert (
        kraken_party_ocr.EXPECTED_PARTY_MODEL_SHA256
        == kraken_party_runtime.PARTY_MODEL_SHA256
    )
    bridge = kraken_party_runtime._party_offline_bridge_text()
    assert 'kwargs["pretrained"] = False' in bridge
    assert 'HF_HUB_OFFLINE") != "1"' in bridge
    party_wrapper = kraken_party_runtime._wrapper_text("party")
    assert "TRANSFORMERS_OFFLINE=1" in party_wrapper
    assert "party_offline_cli.py" in party_wrapper


def test_paddle_ocr_runtime_principal_versions_sources_and_offline_wrapper_are_exact() -> None:
    assert paddle_ocr_runtime.PADDLEOCR_VERSION == "3.7.0"
    assert paddle_ocr_runtime.PADDLEX_VERSION == "3.7.2"
    assert paddle_ocr_runtime.PADDLEPADDLE_VERSION == "3.3.1"
    assert paddle_ocr_runtime.RUNTIME_AUTHORITY_BOUNDARY == (
        "runtime identity and fixity only; no software quality, source-text, or promotion verdict"
    )
    assert paddle_ocr_runtime.PRINCIPAL_WHEEL_SHA256 == {
        "paddleocr": "c0f0a81ad4112727f30c6fcf986ac0ef6a120d31ee0991a01fae0357ee32d338",
        "paddlex": "f1678bf650bbaccfd8f0d4e49d0ae631b4685c829fdae6e802ccd90d4fcb9a7f",
        "paddlepaddle": "9016fc497213e1101261684321fbb31ef5960019ef39cb07ded27bc70e2a9858",
    }
    assert set(paddle_ocr_runtime.MODEL_SOURCES) == {
        "PP-OCRv5_server_det",
        "latin_PP-OCRv5_mobile_rec",
        "eslav_PP-OCRv5_mobile_rec",
    }
    assert all(
        row["url"].startswith(
            "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/"
        )
        for row in paddle_ocr_runtime.MODEL_SOURCES.values()
    )
    wrapper = paddle_ocr_runtime._wrapper_text("paddleocr")
    assert "HF_HUB_OFFLINE=1" in wrapper
    assert "PADDLE_HOME=" in wrapper and "/srv/abyss-machine/cache/" in wrapper
    assert "/home/" not in wrapper and 'venv/bin/paddleocr' in wrapper
    smoke = paddle_ocr_runtime._model_smoke_text(paddle_ocr_runtime.DEFAULT_RUNTIME_ROOT)
    assert "enable_mkldnn=False" in smoke
    assert 'os.environ.get("OMP_NUM_THREADS", "1")' in smoke


def test_paddle_ocr_metadata_normalization_is_json_safe() -> None:
    from email.header import Header

    normalized = paddle_ocr_runtime._metadata_text(Header("Apache License 2.0"))
    assert normalized == "Apache License 2.0"
    assert json.dumps({"license": normalized}) == '{"license": "Apache License 2.0"}'


def test_paddle_ocr_bridge_regions_preserve_order_scores_and_polygons() -> None:
    payload = {
        "rec_texts": ["Übermensch", "вечность"],
        "rec_scores": [0.91, 0.82],
        "rec_polys": [
            [[1, 2], [3, 2], [3, 4], [1, 4]],
            [[5, 6], [8, 6], [8, 9], [5, 9]],
        ],
        "rec_boxes": [[1, 2, 3, 4], [5, 6, 8, 9]],
    }
    regions = paddle_ocr_bridge._region_payload("sample-1", payload)
    assert [row["text"] for row in regions["regions"]] == ["Übermensch", "вечность"]
    assert [row["score"] for row in regions["regions"]] == [0.91, 0.82]
    assert regions["regions"][1]["polygon"] == payload["rec_polys"][1]
    assert len(regions["semantic_sha256"]) == 64

    payload["rec_scores"] = [0.91]
    with pytest.raises(paddle_ocr_bridge.PaddleOcrBridgeError, match="differ in length"):
        paddle_ocr_bridge._region_payload("sample-1", payload)


def test_paddle_ocr_detector_resize_and_bounded_selection_are_explicit() -> None:
    assert paddle_ocr_bridge.REQUEST_SCHEMA == "tos_paddle_ocr_bridge_request_v2"
    assert paddle_ocr_bridge.DETECTOR_RESIZE == {
        "limit_side_len": 960,
        "limit_type": "max",
    }
    assert paddle_ocr.DETECTOR_RESIZE == paddle_ocr_bridge.DETECTOR_RESIZE
    renders = [
        {"sample_id": "sample-a"},
        {"sample_id": "sample-b"},
        {"sample_id": "sample-c"},
    ]
    selected = paddle_ocr._select_renders(renders, ["sample-c", "sample-a"])
    assert [row["sample_id"] for row in selected] == ["sample-a", "sample-c"]
    with pytest.raises(paddle_ocr.PaddleOcrError, match="duplicates"):
        paddle_ocr._select_renders(renders, ["sample-a", "sample-a"])
    with pytest.raises(paddle_ocr.PaddleOcrError, match="absent"):
        paddle_ocr._select_renders(renders, ["sample-z"])
    paddle_ocr._verify_detector_resize_configuration(
        {
            "text_det_limit_side_len": 960,
            "text_det_limit_type": "max",
            "engine": "paddle_static",
        },
        "test",
    )
    with pytest.raises(paddle_ocr.PaddleOcrError, match="resize drift"):
        paddle_ocr._verify_detector_resize_configuration(
            {"text_det_limit_side_len": 64, "text_det_limit_type": "min"},
            "test",
        )


def test_cli_routes_bounded_selection_only_to_paddle_ocr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paddle_call: dict[str, object] = {}
    kraken_call: dict[str, object] = {}

    def fake_paddle(*args: object, **kwargs: object) -> dict[str, object]:
        paddle_call["args"] = args
        paddle_call["kwargs"] = kwargs
        return {"engine": "paddle-test"}

    def fake_kraken(*args: object, **kwargs: object) -> dict[str, object]:
        kraken_call["args"] = args
        kraken_call["kwargs"] = kwargs
        return {"engine": "kraken-test"}

    monkeypatch.setattr(lab, "execute_paddle_ocr", fake_paddle)
    monkeypatch.setattr(lab, "execute_kraken_party_ocr", fake_kraken)
    monkeypatch.setattr(lab, "verify_run", lambda _run_root: [])

    common = [
        str(tmp_path / "run"),
        "--sample-plan",
        str(tmp_path / "samples.json"),
        "--render-manifest",
        str(tmp_path / "renders.json"),
        "--runtime-manifest",
        str(tmp_path / "runtime.json"),
    ]
    selected = "tos.item.zarathustra.antonovsky.1899.p002"
    assert lab.main(["execute-paddle-ocr", *common, "--sample-id", selected]) == 0
    assert paddle_call["kwargs"]["selected_sample_ids"] == [selected]

    assert lab.main(["execute-kraken-party-ocr", *common]) == 0
    assert "selected_sample_ids" not in kraken_call["kwargs"]


def test_paddle_ocr_repeat_comparison_separates_semantic_and_raw_drift() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        first = root / "first/raw-output"
        second = root / "second/raw-output"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        base = {
            "sample_plan_sha256": "p" * 64,
            "render_set_sha256": "r" * 64,
            "runtime_artifact_set_sha256": "a" * 64,
            "versions": {"paddleocr": "3.7.0"},
            "models": {"detector": {"source_sha256": "m" * 64}},
            "configuration": {"engine": "paddle_static", "enable_mkldnn": False},
            "language_order": ["ru", "de"],
            "bridge_sha256": "b" * 64,
            "samples": [
                {
                    "sample_id": "sample-1",
                    "outputs": {
                        "diplomatic_text": {"sha256": "t" * 64, "bytes": 8},
                        "regions": {"canonical_sha256": "c" * 64, "sha256": "j" * 64},
                        "paddle_result": {"sha256": "x" * 64, "bytes": 64},
                    },
                }
            ],
            "semantic_output_set_sha256": "s" * 64,
            "raw_output_set_sha256": "q" * 64,
        }
        left = {"run_id": "r1", **base}
        right = json.loads(json.dumps({"run_id": "r2", **base}))
        right["samples"][0]["outputs"]["paddle_result"]["sha256"] = "y" * 64
        right["raw_output_set_sha256"] = "z" * 64
        (first / "paddle-ocr-output-manifest.json").write_text(
            json.dumps(left), encoding="utf-8"
        )
        (second / "paddle-ocr-output-manifest.json").write_text(
            json.dumps(right), encoding="utf-8"
        )
        comparison = paddle_ocr.compare_paddle_ocr_runs(root / "first", root / "second")
        assert comparison["mechanically_identical"] is True
        assert comparison["raw_byte_identical"] is False
        assert comparison["semantic_differences"] == []


def test_paddle_ocr_model_tar_inventory_rejects_escape_and_hashes_static_graph() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        valid = root / "valid.tar"
        with tarfile.open(valid, "w") as archive:
            for name, body in (
                ("model/inference.json", b"{}"),
                ("model/inference.pdiparams", b"weights"),
                ("model/inference.yml", b"Global: {}\n"),
            ):
                info = tarfile.TarInfo(name)
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
        inventory = paddle_ocr_runtime._tar_inventory(valid)
        assert [row["path"] for row in inventory] == [
            "model/inference.json",
            "model/inference.pdiparams",
            "model/inference.yml",
        ]
        assert all(len(row["sha256"]) == 64 for row in inventory)

        unsafe = root / "unsafe.tar"
        with tarfile.open(unsafe, "w") as archive:
            body = b"escape"
            info = tarfile.TarInfo("../escape.json")
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        with pytest.raises(paddle_ocr_runtime.PaddleOcrRuntimeError, match="unsafe"):
            paddle_ocr_runtime._tar_inventory(unsafe)


def test_real_human_lane_is_never_reported_ready_for_automatic_execution() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-translation-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    facts = {
        "captured_at_utc": "2026-07-22T12:00:00+00:00",
        "srv_free_bytes": 100 * 1024**3,
        "memory_available_bytes": 16 * 1024**3,
        "load_1m": 1.0,
        "thermal_owner": thermal_owner(workload_class="heavy", workload_kind="ai"),
        "commands": {},
        "running_services": [],
        "devices": {"CPU": True, "GPU": True, "NPU": True, "Vulkan": True},
    }
    storage = {"allowed": True}

    receipt = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight=storage,
    )

    assert receipt["decision"] == "awaiting-human-input"


def test_owner_active_high_range_is_not_misclassified_as_blocked() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-retrieval-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    facts = {
        "captured_at_utc": "2026-07-22T12:00:00+00:00",
        "srv_free_bytes": 100 * 1024**3,
        "memory_available_bytes": 16 * 1024**3,
        "load_1m": 1.0,
        "thermal_owner": thermal_owner(102.0),
        "commands": {"sqlite3": {"path": "/usr/bin/sqlite3"}},
        "running_services": [],
        "devices": {"CPU": True, "GPU": True, "NPU": True, "Vulkan": True},
    }

    receipt = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight={"allowed": True},
    )

    assert receipt["decision"] == "ready"
    thermal_checks = {item["name"]: item for item in receipt["checks"] if item["name"].startswith("thermal")}
    assert thermal_checks["thermal-owner-telemetry"]["passed"] is True
    assert thermal_checks["thermal-watch-band"]["passed"] is True
    assert thermal_checks["thermal-owner-admission"]["passed"] is True


def test_watch_band_warns_but_current_owner_admission_controls_run() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-retrieval-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    facts = {
        "captured_at_utc": "2026-07-22T12:00:00+00:00",
        "srv_free_bytes": 100 * 1024**3,
        "memory_available_bytes": 16 * 1024**3,
        "load_1m": 1.0,
        "thermal_owner": thermal_owner(106.0),
        "commands": {"sqlite3": {"path": "/usr/bin/sqlite3"}},
        "running_services": [],
        "devices": {"CPU": True, "GPU": True, "NPU": True, "Vulkan": True},
    }

    receipt = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight={"allowed": True},
    )

    assert receipt["decision"] == "ready"
    watch = next(item for item in receipt["checks"] if item["name"] == "thermal-watch-band")
    assert watch["passed"] is False
    assert watch["severity"] == "warn"

    facts["thermal_owner"] = thermal_owner(106.0, resource_allowed=False)
    denied = lab.build_preflight_receipt(
        suite,
        experiment,
        variant,
        host_facts=facts,
        storage_preflight={"allowed": True},
    )
    assert denied["decision"] == "blocked"


def test_prepare_run_requires_allowed_preflight_and_writes_no_source_bytes() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-retrieval-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    preflight = {
        "experiment_id": experiment["experiment_id"],
        "experiment_sha256": lab.sha256_json(experiment),
        "variant": "A",
        "decision": "ready",
    }

    with tempfile.TemporaryDirectory() as temporary:
        durable = Path(temporary) / "durable"
        suite_copy = json.loads(json.dumps(suite))
        suite_copy["artifact_roots"]["durable"] = durable.as_posix()
        run_root = lab.prepare_run(
            suite_copy,
            experiment,
            variant,
            preflight,
            "test-run-001",
            durable,
        )

        assert (run_root / "run.receipt.json").is_file()
        assert (run_root / "receipts" / "preflight.json").is_file()
        assert list((run_root / "inputs").iterdir()) == []
        assert lab.verify_run(run_root) == []


def test_prepare_run_rejects_blocked_preflight() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-retrieval-foundation-v1")
    variant = lab.find_variant(experiment, "A")
    preflight = {
        "experiment_id": experiment["experiment_id"],
        "experiment_sha256": lab.sha256_json(experiment),
        "variant": "A",
        "decision": "blocked",
    }
    with tempfile.TemporaryDirectory() as temporary:
        try:
            lab.prepare_run(
                suite,
                experiment,
                variant,
                preflight,
                "blocked-run",
                Path(temporary),
            )
        except lab.LaboratoryError as exc:
            assert "blocked preflight" in str(exc)
        else:
            raise AssertionError("blocked preflight unexpectedly materialized a run")


def test_native_xhtml_extraction_keeps_visible_text_and_omits_style() -> None:
    raw = b"<html><head><title>Page 1</title><style>hidden</style></head><body><h1>Title</h1><p>One &amp; two.</p></body></html>"
    assert native.extract_xhtml_text(raw) == "Title\nOne & two.\n"


def _translation_source_fixture(root: Path) -> dict[str, object]:
    tree = root / "tree"
    source_item_ref = "tos.item.test.zarathustra-source-epub"
    visual_item_ref = "tos.item.test.zarathustra-visual-pdf"
    comparator_item_ref = "tos.item.test.sealed-recognized-comparator"

    source_item_root = tree / "ToS/source-witnesses/test/source"
    visual_item_root = tree / "ToS/source-witnesses/test/visual"
    comparator_item_root = tree / "ToS/source-witnesses/test/comparator"
    for item_root in (source_item_root, visual_item_root, comparator_item_root):
        (item_root / "payload").mkdir(parents=True)

    epub_path = source_item_root / "payload/source.epub"
    member_hashes: dict[str, str] = {}
    with zipfile.ZipFile(epub_path, "w") as archive:
        for number in range(1, 31):
            member = f"EPUB/page_{number}.html"
            body = (
                "<html><head><title>ignored</title></head><body>"
                f"<p>Als Probe {number} begann, sprach er: „Werde!“ Danach blieb er.</p>"
                "<p>Zweiter Absatz.</p></body></html>"
            ).encode("utf-8")
            archive.writestr(member, body)
            member_hashes[member] = hashlib.sha256(body).hexdigest()
    source_sha256 = hashlib.sha256(epub_path.read_bytes()).hexdigest()
    source_file_ref = f"tos.file.sha256.{source_sha256}"

    pdf_path = visual_item_root / "payload/source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nsynthetic visual witness\n%%EOF\n")
    visual_sha256 = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    visual_file_ref = f"tos.file.sha256.{visual_sha256}"

    comparator_sentinel = "ПРИЗНАННЫЙ-ПЕРЕВОД-НЕ-ЧИТАТЬ"
    comparator_path = comparator_item_root / "payload/comparator.txt"
    comparator_path.write_text(comparator_sentinel, encoding="utf-8")
    comparator_sha256 = hashlib.sha256(comparator_path.read_bytes()).hexdigest()

    def write_rights(item_root: Path, item_ref: str, file_ref: str, suffix: str) -> str:
        relative = item_root.relative_to(tree) / "rights.json"
        payload = {
            "rights_id": f"tos.rights.test.{suffix}",
            "scope_refs": [item_ref, file_ref],
            "assessment_status": "test-only",
            "review_status": "unreviewed",
            "visibility": "local_only",
            "redistribution_posture": "not_authorized",
            "derivative_posture": "local_research_only",
        }
        (tree / relative).write_text(json.dumps(payload), encoding="utf-8")
        return relative.as_posix()

    source_rights_ref = write_rights(
        source_item_root, source_item_ref, source_file_ref, "source"
    )
    visual_rights_ref = write_rights(
        visual_item_root, visual_item_ref, visual_file_ref, "visual"
    )
    (source_item_root / "item.manifest.json").write_text(
        json.dumps(
            {
                "item_id": source_item_ref,
                "payload_files": [
                    {
                        "file_id": source_file_ref,
                        "relative_path": "payload/source.epub",
                        "sha256": source_sha256,
                    }
                ],
                "rights_ref": source_rights_ref,
            }
        ),
        encoding="utf-8",
    )
    (visual_item_root / "item.manifest.json").write_text(
        json.dumps(
            {
                "item_id": visual_item_ref,
                "payload_files": [
                    {
                        "file_id": visual_file_ref,
                        "relative_path": "payload/source.pdf",
                        "sha256": visual_sha256,
                    }
                ],
                "rights_ref": visual_rights_ref,
            }
        ),
        encoding="utf-8",
    )
    (comparator_item_root / "item.manifest.json").write_text(
        json.dumps(
            {
                "item_id": comparator_item_ref,
                "payload_files": [
                    {
                        "file_id": f"tos.file.sha256.{comparator_sha256}",
                        "relative_path": "payload/comparator.txt",
                        "sha256": comparator_sha256,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    fragments: list[dict[str, object]] = []
    anchors: list[dict[str, object]] = []
    for number in range(1, 31):
        fragment_id = f"tos-translation-fragment-{number:03d}"
        anchor_ref = f"tos.anchor.test.translation.t{number:03d}"
        member = f"EPUB/page_{number}.html"
        fragment = {
            "fragment_id": fragment_id,
            "source_anchor_ref": anchor_ref,
            "container_member": member,
            "member_sha256": member_hashes[member],
            "page_member_index": number,
            "printed_page": number,
            "structural_context": f"synthetic context {number}",
            "strata": ["synthetic"],
            "analysis_tags": ["syntax", "rhythm"],
            "source_transcription_status": "not_started",
            "human_source_acceptance": False,
        }
        fragments.append(fragment)
        anchors.append(
            {
                "anchor_id": anchor_ref,
                "item_id": source_item_ref,
                "file_id": source_file_ref,
                "file_sha256": source_sha256,
                "selectors": [
                    {
                        "type": "container_member",
                        "member_path": member,
                        "member_sha256": member_hashes[member],
                    },
                    {
                        "type": "structural",
                        "path": [
                            "html",
                            "body",
                            "p:nth-of-type(1)",
                            "sentence:nth-of-type(1)",
                        ],
                        "scheme": "tos-local-sentence-segmentation-v1",
                    },
                ],
                "selector_method": {
                    "maker_type": "model",
                    "method": "first-complete-sentence candidate selection",
                },
                "status": "proposed",
                "review_ref": None,
            }
        )

    plan = {
        "schema_version": "tos_translation_sample_plan_v1",
        "translation_sample_plan_id": "tos.translation-sample-plan.test",
        "source_item_ref": source_item_ref,
        "source_file_ref": source_file_ref,
        "source_file_sha256": source_sha256,
        "source_language": "de",
        "target_language": "ru",
        "status": "frozen",
        "frozen_before_drafts": True,
        "fragment_count": 30,
        "selector_method": {
            "unit": "first_complete_sentence_in_body-p-1",
            "segmentation": "tos-local-sentence-segmentation-v1",
            "selector_status": "proposed_until_source_visible_human_acceptance",
        },
        "recognized_comparator": {
            "expression_ref": "tos.expression.test.sealed-comparator",
            "item_ref": comparator_item_ref,
            "visibility": "sealed",
            "anchor_resolution_status": "not_started",
            "reveal_stage": "after_human_ai_and_ai-human_independent_drafts_are_frozen",
        },
        "lanes": {
            "human_only": "not_started",
            "ai_only": "not_started",
            "ai_human": "not_started",
            "recognized_comparator": "sealed",
        },
        "review_status": "unreviewed",
        "fragments": fragments,
    }
    plan_path = root / "translation-samples.json"
    anchors_path = root / "translation-anchors.jsonl"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    anchors_path.write_text(
        "".join(json.dumps(record) + "\n" for record in anchors), encoding="utf-8"
    )
    return {
        "tree": tree,
        "plan": plan,
        "plan_path": plan_path,
        "anchors_path": anchors_path,
        "visual_item_ref": visual_item_ref,
        "visual_file_ref": visual_file_ref,
        "visual_sha256": visual_sha256,
        "comparator_sentinel": comparator_sentinel,
    }


def test_translation_source_sentence_candidate_is_structural_and_explicitly_unreviewed() -> None:
    raw = (
        "<html><head><style>hidden</style></head><body>"
        "<h1>Furniture</h1><p>Als er ging, sprach er: „Werde!“ Danach blieb er.</p>"
        "<p>Später.</p></body></html>"
    ).encode("utf-8")
    paragraph = translation_source.extract_first_body_paragraph(raw)

    assert paragraph == "Als er ging, sprach er: „Werde!“ Danach blieb er."
    assert translation_source.first_complete_sentence(paragraph) == (
        "Als er ging, sprach er: „Werde!“"
    )
    with pytest.raises(translation_source.TranslationSourceError, match="no complete"):
        translation_source.first_complete_sentence("Kein erratener Abschluss")

    heading = translation_source.mechanical_candidate_hazards(
        "Vom Freunde.", "Vom Freunde"
    )
    assert heading == {
        "status": "software-advisory-not-review",
        "candidate_character_count": 12,
        "candidate_token_count": 2,
        "starts_with_lowercase": False,
        "starts_with_nonletter": False,
        "short_candidate": True,
        "matches_structural_context_surface": True,
        "page_start_boundary_unverified": True,
        "requires_source_visible_review": True,
    }
    assert translation_source.mechanical_candidate_hazards(
        "am meisten?", "continuation"
    )["starts_with_lowercase"] is True
    assert translation_source.mechanical_candidate_hazards(
        ".Vom Freunde.", "Vom Freunde"
    )["starts_with_nonletter"] is True


def test_translation_source_plan_rejects_unsealed_or_synthetic_human_progress(
    tmp_path: Path,
) -> None:
    fixture = _translation_source_fixture(tmp_path)
    plan = fixture["plan"]
    assert isinstance(plan, dict)
    assert translation_source.validate_translation_plan(plan) == []

    drifted = json.loads(json.dumps(plan))
    drifted["recognized_comparator"]["visibility"] = "revealed"
    drifted["fragments"][0]["human_source_acceptance"] = True
    issues = translation_source.validate_translation_plan(drifted)
    assert any("not sealed" in issue for issue in issues)
    assert any("absent human" in issue for issue in issues)


def test_translation_source_packet_seals_comparator_and_detects_artifact_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _translation_source_fixture(tmp_path)
    shared_root = tmp_path / "artifacts/shared-inputs/tos-translation-foundation-v1"
    shared_root.mkdir(parents=True)
    monkeypatch.setattr(translation_source, "DEFAULT_SHARED_ROOT", shared_root)
    monkeypatch.setattr(
        translation_source,
        "_pdf_inventory",
        lambda _command, _path: {
            "page_count": 600,
            "pdfinfo_version": "pdfinfo synthetic-test",
            "encrypted": "no",
            "page_size": "test",
        },
    )

    manifest = translation_source.materialize_translation_source(
        fixture["tree"],
        fixture["plan_path"],
        fixture["anchors_path"],
        "synthetic-source-packet-v1",
        fixture["visual_item_ref"],
        fixture["visual_file_ref"],
        fixture["visual_sha256"],
        shared_root=shared_root,
        invocation=["test"],
    )
    packet_root = shared_root / "synthetic-source-packet-v1"
    manifest_path = packet_root / "translation-source-manifest.json"

    assert manifest["status"] == "awaiting-source-visible-human-review"
    assert manifest["fragment_count"] == 30
    assert manifest["recognized_comparator"]["visibility"] == "sealed"
    assert manifest["recognized_comparator"]["content_consulted"] is False
    assert manifest["lanes"] == {
        "human_only": "awaiting-real-human-source-input",
        "ai_only": "blocked-pending-human-source-acceptance",
        "ai_human": "blocked-pending-independent-drafts",
        "recognized_comparator": "sealed",
    }
    assert [row["visual_pdf_page_proposal"] for row in manifest["fragments"]] == list(
        range(2, 32)
    )
    assert all(
        row["mechanical_hazard_signals"]["requires_source_visible_review"] is True
        for row in manifest["fragments"]
    )
    review_rows = [
        json.loads(line)
        for line in (packet_root / "reviews/source-review.template.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(review_rows) == 30
    assert all(row["pass_1"]["performed_by_real_human"] is False for row in review_rows)
    assert all(row["source_acceptance"] is None for row in review_rows)
    assert translation_source.verify_translation_source_manifest(manifest_path) == manifest

    all_artifact_bytes = b"".join(
        path.read_bytes() for path in packet_root.rglob("*") if path.is_file()
    )
    assert str(fixture["comparator_sentinel"]).encode("utf-8") not in all_artifact_bytes

    candidate_path = packet_root / manifest["fragments"][0]["sentence_candidate"]["ref"]
    candidate_path.write_text("drifted candidate\n", encoding="utf-8")
    with pytest.raises(translation_source.TranslationSourceError, match="fixity drift"):
        translation_source.verify_translation_source_manifest(manifest_path)


def _translation_source_model_inspection(
    manifest: dict[str, object], manifest_path: Path
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    fragments = manifest["fragments"]
    assert isinstance(fragments, list)
    for index, fragment in enumerate(fragments, start=1):
        assert isinstance(fragment, dict)
        candidate = fragment["sentence_candidate"]
        assert isinstance(candidate, dict)
        if index <= 7:
            decision = "accept-with-limits"
            signals = [
                "visual-page-correspondence-observed",
                "sentence-boundary-visually-plausible",
            ]
        elif index <= 29:
            decision = "reject"
            signals = ["visual-page-correspondence-observed", "heading-selected"]
        else:
            decision = "uncertain"
            signals = [
                "visual-page-correspondence-observed",
                "page-start-boundary-unverified",
            ]
        records.append(
            {
                "fragment_id": fragment["fragment_id"],
                "source_anchor_ref": fragment["source_anchor_ref"],
                "visual_pdf_page": fragment["visual_pdf_page_proposal"],
                "sentence_candidate_ref": candidate["ref"],
                "sentence_candidate_sha256": candidate["sha256"],
                "decision": decision,
                "signals": signals,
                "rationale": "Synthetic source-visible inspection fixture.",
                "human_source_acceptance": False,
            }
        )
    visual_witness = manifest["visual_witness"]
    assert isinstance(visual_witness, dict)
    return {
        "schema_version": "tos_translation_source_model_inspection_v1",
        "inspection_id": "synthetic-source-selector-inspection-v1",
        "experiment_id": "tos-translation-foundation-v1",
        "stage": "source-preparation",
        "source_packet": {
            "packet_id": manifest["packet_id"],
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "candidate_set_sha256": manifest["candidate_set_sha256"],
            "sample_plan_sha256": manifest["sample_plan_sha256"],
        },
        "selector_method": {
            "plan_scheme": "tos-local-sentence-segmentation-v1",
            "implementation": "first-body-p punctuation-boundary software proposal",
        },
        "source_visible": True,
        "inspection_scope": "exhaustive",
        "maker": {
            "maker_type": "model",
            "agent_ref": "model:test",
            "method": "synthetic full-page visual comparison",
        },
        "visual_review": {
            "visual_witness_sha256": visual_witness["file_sha256"],
            "render_method": "pdftoppm-full-page-png-rgb",
            "render_dpi": 180,
            "expected_page_count": 30,
            "inspected_page_count": 30,
            "page_file_count_confirmed_manually": True,
        },
        "records": records,
        "summary": {
            "record_count": 30,
            "decision_counts": {
                "accept_with_limits": 7,
                "reject": 22,
                "uncertain": 1,
                "abstain": 0,
            },
            "failure_mode_counts": {
                "heading_selected": 22,
                "page_start_tail": 0,
                "ocr_contamination": 0,
                "boundary_uncertain": 1,
                "usable_only_with_limits": 7,
            },
            "overall_result": "reject-selector-method",
            "method_disposition": "retain-v1-as-negative-baseline-and-design-v2",
        },
        "translation_lanes": {
            "human_only": "awaiting-real-human-source-input",
            "ai_only": "blocked-pending-human-source-acceptance",
            "ai_human": "blocked-pending-independent-drafts",
        },
        "recognized_comparator_visibility": "sealed",
        "next_method_requirements": [
            "classify-layout-role-before-sentence-selection",
            "inspect-previous-current-next-page-context",
            "select-first-prose-after-heading-on-openings",
            "perform-diplomatic-transcription-after-source-review",
            "supersede-v1-without-rewriting-negative-baseline",
        ],
        "inspected_at_utc": "2026-07-23T12:00:00Z",
        "review_authority": "advisory-nonhuman",
        "promotion_authorized": False,
        "human_source_acceptance_count": 0,
    }


def test_translation_source_model_inspection_closes_over_frozen_packet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _translation_source_fixture(tmp_path)
    shared_root = tmp_path / "artifacts/shared-inputs/tos-translation-foundation-v1"
    shared_root.mkdir(parents=True)
    monkeypatch.setattr(translation_source, "DEFAULT_SHARED_ROOT", shared_root)
    monkeypatch.setattr(
        translation_source,
        "_pdf_inventory",
        lambda _command, _path: {
            "page_count": 600,
            "pdfinfo_version": "pdfinfo synthetic-test",
            "encrypted": "no",
            "page_size": "test",
        },
    )
    manifest = translation_source.materialize_translation_source(
        fixture["tree"],
        fixture["plan_path"],
        fixture["anchors_path"],
        "synthetic-inspection-packet-v1",
        fixture["visual_item_ref"],
        fixture["visual_file_ref"],
        fixture["visual_sha256"],
        shared_root=shared_root,
        invocation=["test"],
    )
    manifest_path = (
        shared_root / "synthetic-inspection-packet-v1/translation-source-manifest.json"
    )
    inspection = _translation_source_model_inspection(manifest, manifest_path)
    inspection_path = tmp_path / "translation-source-model-inspection.json"
    inspection_path.write_text(json.dumps(inspection), encoding="utf-8")

    assert translation_source.verify_translation_source_inspection(
        inspection_path, manifest_path
    ) == inspection

    inspection["records"][0]["sentence_candidate_sha256"] = "0" * 64
    inspection_path.write_text(json.dumps(inspection), encoding="utf-8")
    with pytest.raises(translation_source.TranslationSourceError, match="drifted"):
        translation_source.verify_translation_source_inspection(
            inspection_path, manifest_path
        )


def _translation_source_review_plan(
    fixture: dict[str, object], root: Path
) -> tuple[Path, str]:
    tree = fixture["tree"]
    assert isinstance(tree, Path)
    contract_path = tree / "ToS/contracts/translation-source-review-plan.schema.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_path.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
        encoding="utf-8",
    )

    v1_plan_path = tree / "ToS/source-witnesses/test/gold/translation-samples.json"
    v1_plan_path.parent.mkdir(parents=True, exist_ok=True)
    v1_plan_path.write_text(json.dumps(fixture["plan"]), encoding="utf-8")
    v1_plan_sha256 = hashlib.sha256(v1_plan_path.read_bytes()).hexdigest()
    inspection_path = tree / "ToS/research-packets/test/inspection.json"
    inspection_path.parent.mkdir(parents=True, exist_ok=True)
    inspection = {
        "inspection_id": "synthetic-selector-inspection-v1",
        "promotion_authorized": False,
    }
    inspection_path.write_text(json.dumps(inspection), encoding="utf-8")
    inspection_sha256 = hashlib.sha256(inspection_path.read_bytes()).hexdigest()

    source_sha256 = fixture["plan"]["source_file_sha256"]
    source_file_ref = fixture["plan"]["source_file_ref"]
    source_item_ref = fixture["plan"]["source_item_ref"]
    units: list[dict[str, object]] = []
    fragments = fixture["plan"]["fragments"]
    assert isinstance(fragments, list)
    for index, fragment in enumerate(fragments, start=1):
        assert isinstance(fragment, dict)
        current_page = index + 1
        units.append(
            {
                "review_unit_id": f"tos-translation-source-review-v2-{index:03d}",
                "supersedes_fragment_id": fragment["fragment_id"],
                "context_anchor_ref": fragment["source_anchor_ref"],
                "container_member": fragment["container_member"],
                "member_sha256": fragment["member_sha256"],
                "visual_context": {
                    "previous_pdf_page": current_page - 1,
                    "current_pdf_page": current_page,
                    "next_pdf_page": current_page + 1,
                },
                "layout_posture": "prose-at-page-start",
                "selection_instruction": (
                    "confirm-visible-complete-prose-unit-without-reusing-v1-text"
                ),
                "v1_inspection_decision": "accept-with-limits",
                "v1_failure_signals": ["candidate-usable-with-limits"],
                "reuse_v1_candidate": False,
                "diplomatic_transcription_status": "not-started",
                "human_source_acceptance": False,
                "recognized_comparator_visible": False,
            }
        )
    plan = {
        "schema_version": "tos_translation_source_review_plan_v2",
        "review_plan_id": "tos.translation-source-review-plan.synthetic-v2",
        "experiment_id": "tos-translation-foundation-v1",
        "source_witness": {
            "item_ref": source_item_ref,
            "file_ref": source_file_ref,
            "file_sha256": source_sha256,
            "role": "automatic-ocr-derivative-not-source-truth",
        },
        "visual_witness": {
            "item_ref": fixture["visual_item_ref"],
            "file_ref": fixture["visual_file_ref"],
            "file_sha256": fixture["visual_sha256"],
            "role": "source-visible-scan-witness",
        },
        "supersedes": {
            "v1_plan_ref": v1_plan_path.relative_to(tree).as_posix(),
            "v1_plan_sha256": v1_plan_sha256,
            "v1_inspection_ref": inspection_path.relative_to(tree).as_posix(),
            "v1_inspection_sha256": inspection_sha256,
            "v1_inspection_id": inspection["inspection_id"],
            "disposition": "retain-v1-as-negative-baseline",
        },
        "recognized_comparator": {
            "expression_ref": "tos.expression.test.sealed-comparator",
            "item_ref": fixture["plan"]["recognized_comparator"]["item_ref"],
            "visibility": "sealed",
            "content_consulted": False,
            "reveal_stage": "after_human_ai_and_ai-human_independent_drafts_are_frozen",
        },
        "review_questions": ["Inspect source only.", "Record uncertainty."],
        "units": units,
    }
    plan_path = tree / "ToS/source-witnesses/test/gold/translation-source-review-plan.v2.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path, str(fixture["comparator_sentinel"])


def test_translation_source_review_packet_is_blind_blank_and_fixity_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _translation_source_fixture(tmp_path)
    plan_path, comparator_sentinel = _translation_source_review_plan(fixture, tmp_path)
    shared_root = tmp_path / "artifacts/shared-inputs/tos-translation-foundation-v1"
    shared_root.mkdir(parents=True)
    monkeypatch.setattr(translation_source_review, "DEFAULT_SHARED_ROOT", shared_root)
    monkeypatch.setattr(
        translation_source_review,
        "_pdf_inventory",
        lambda _command, _path: {
            "page_count": 600,
            "pdfinfo_version": "pdfinfo synthetic-test",
            "encrypted": "no",
            "page_size": "test",
        },
    )
    monkeypatch.setattr(
        translation_source_review,
        "_pdftoppm_version",
        lambda _command: "pdftoppm synthetic-test",
    )

    def fake_render(_command: Path, _pdf: Path, output: Path, _page: int) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            + (100).to_bytes(4, "big")
            + (200).to_bytes(4, "big")
        )

    monkeypatch.setattr(translation_source_review, "_render_page", fake_render)
    manifest = translation_source_review.materialize_translation_source_review(
        fixture["tree"],
        plan_path,
        "synthetic-human-review-packet-v2",
        shared_root=shared_root,
        invocation=["test"],
    )
    packet_root = shared_root / "synthetic-human-review-packet-v2"
    manifest_path = packet_root / "translation-source-review-manifest.json"
    assert manifest["status"] == "awaiting-real-human-source-review"
    assert len(manifest["units"]) == 30
    assert manifest["render"]["unique_page_count"] == 32
    assert manifest["recognized_comparator"]["visibility"] == "sealed"
    assert all(row["v1_candidate_visible"] is False for row in manifest["units"])
    assert translation_source_review.verify_translation_source_review_manifest(
        manifest_path
    ) == manifest

    artifact_bytes = b"".join(
        path.read_bytes() for path in packet_root.rglob("*") if path.is_file()
    )
    assert comparator_sentinel.encode("utf-8") not in artifact_bytes
    assert b"v1_inspection_decision" not in (
        packet_root / "review/pass-1-layout-and-transcription.html"
    ).read_bytes()

    first_page = packet_root / manifest["pages"][0]["artifact"]["ref"]
    first_page.write_bytes(first_page.read_bytes() + b"drift")
    with pytest.raises(translation_source_review.TranslationSourceReviewError, match="drift"):
        translation_source_review.verify_translation_source_review_manifest(manifest_path)


def test_translation_lab_readiness_blocks_blank_and_model_labeled_human_work(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = _translation_source_fixture(tmp_path)
    review_plan_path, _ = _translation_source_review_plan(fixture, tmp_path)
    shared_root = tmp_path / "artifacts/shared-inputs/tos-translation-foundation-v1"
    shared_root.mkdir(parents=True)
    monkeypatch.setattr(translation_source_review, "DEFAULT_SHARED_ROOT", shared_root)
    monkeypatch.setattr(
        translation_source_review,
        "_pdf_inventory",
        lambda _command, _path: {
            "page_count": 600,
            "pdfinfo_version": "pdfinfo synthetic-test",
            "encrypted": "no",
            "page_size": "test",
        },
    )
    monkeypatch.setattr(
        translation_source_review,
        "_pdftoppm_version",
        lambda _command: "pdftoppm synthetic-test",
    )

    def fake_render(_command: Path, _pdf: Path, output: Path, _page: int) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            + (100).to_bytes(4, "big")
            + (200).to_bytes(4, "big")
        )

    monkeypatch.setattr(translation_source_review, "_render_page", fake_render)
    manifest = translation_source_review.materialize_translation_source_review(
        fixture["tree"],
        review_plan_path,
        "synthetic-readiness-review-v2",
        shared_root=shared_root,
        invocation=["synthetic-test"],
    )
    packet_root = shared_root / "synthetic-readiness-review-v2"
    manifest_path = packet_root / "translation-source-review-manifest.json"

    tree = fixture["tree"]
    assert isinstance(tree, Path)
    laboratory_schema = tree / "ToS/contracts/translation-laboratory-plan.schema.json"
    laboratory_schema.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
            }
        ),
        encoding="utf-8",
    )
    reference_schema = tree / "ToS/contracts/translation-reference-register.schema.json"
    reference_schema.write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
            }
        ),
        encoding="utf-8",
    )
    laboratory_plan = {
        "$schema": (
            "https://tree-of-sophia.local/ToS/contracts/"
            "translation-laboratory-plan.schema.json"
        ),
        "experiment_id": "tos-translation-foundation-v1",
        "work_ref": "tos.work.synthetic.zarathustra",
        "source_review_gate": {
            "review_plan_sha256": manifest["review_plan_sha256"],
            "interface_manifest_sha256": hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest(),
            "interface_page_set_sha256": manifest["page_set_sha256"],
            "review_unit_count": 30,
        },
        "recognized_comparator": manifest["recognized_comparator"],
    }
    laboratory_root = tree / "ToS/test-translation-laboratory"
    laboratory_root.mkdir(parents=True)
    laboratory_plan_path = laboratory_root / "translation-laboratory-plan.json"
    laboratory_plan_path.write_text(json.dumps(laboratory_plan), encoding="utf-8")
    required_reference_categories = {
        "historical_dictionary",
        "modern_dictionary",
        "etymological_dictionary",
        "historical_corpus",
        "nietzsche_critical_edition",
        "nietzsche_lexical_resource",
        "recognized_ru_translation_candidate",
        "additional_ru_translation_candidate",
        "additional_en_translation_candidate",
    }
    reference_entries = [
        {
            "reference_id": f"tos-ref.synthetic.{index}",
            "category": category,
            "access": {"content_ingested_for_translation_lab": False},
            "admission": {"accepted_as_truth": False},
            "tos_refs": {
                "record_refs": (
                    [
                        laboratory_plan["recognized_comparator"]["expression_ref"],
                        laboratory_plan["recognized_comparator"]["item_ref"],
                    ]
                    if category == "recognized_ru_translation_candidate"
                    else []
                )
            },
        }
        for index, category in enumerate(sorted(required_reference_categories), start=1)
    ]
    reference_register = {
        "$schema": (
            "https://tree-of-sophia.local/ToS/contracts/"
            "translation-reference-register.schema.json"
        ),
        "work_ref": laboratory_plan["work_ref"],
        "laboratory_plan_ref": "ToS/test-translation-laboratory/translation-laboratory-plan.json",
        "required_categories": sorted(required_reference_categories),
        "entries": reference_entries,
        "coverage": {
            "required_category_count": 9,
            "entry_count": 9,
            "all_required_categories_present": True,
            "content_admitted_entries": 0,
            "human_bibliographic_reviews": 0,
            "human_rights_reviews": 0,
            "permission_requests_sent": 0,
        },
    }
    reference_register_path = laboratory_root / "translation-reference-register.v1.json"
    reference_register_path.write_text(json.dumps(reference_register), encoding="utf-8")
    template_path = packet_root / manifest["review_template"]["ref"]

    blank = lab.inspect_translation_lab_readiness(
        tree,
        laboratory_plan_path,
        manifest_path,
        template_path,
    )
    assert blank["decision"] == "blocked"
    assert blank["human_review"] == {
        "review_output_ref": template_path.resolve().as_posix(),
        "review_output_sha256": hashlib.sha256(template_path.read_bytes()).hexdigest(),
        "record_count": 30,
        "pass_1_complete": 0,
        "pass_2_complete": 0,
        "accepted_source_units": 0,
        "non_accepted_source_units": 0,
        "all_units_double_checked": False,
    }
    assert all(
        blank["translation_lanes"][lane]["state"] == "blocked"
        for lane in ("human_only", "ai_only", "ai_alternatives", "ai_human")
    )
    assert all(
        blank["translation_lanes"][lane]["state"] == "blocked"
        for lane in (
            "human_pre_draft_analysis",
            "ai_pre_draft_analysis",
            "ai_alternative_pre_draft_analysis",
        )
    )
    assert blank["reference_register"]["entry_count"] == 9
    assert blank["reference_register"]["content_admitted_entries"] == 0

    rows = [
        json.loads(line)
        for line in template_path.read_text(encoding="utf-8").splitlines()
    ]
    for index, row in enumerate(rows, start=1):
        row["schema_version"] = "tos_translation_source_human_review_v2"
        row["template_status"] = "completed-human-review"
        row["pass_1"].update(
            {
                "performed_by_real_human": True,
                "reviewer_ref": "model:synthetic-impostor",
                "reviewed_at_utc": f"2026-07-23T15:{index:02d}:00Z",
                "layout_role": "prose",
                "begins_on_previous_page": False,
                "continues_on_next_page": False,
                "boundary_start_note": "synthetic explicit start",
                "boundary_end_note": "synthetic explicit end",
                "diplomatic_transcription": f"Synthetic source {index}.",
                "decision": "accept",
            }
        )
        row["pass_2"].update(
            {
                "performed_by_real_human": True,
                "reviewer_ref": "human:synthetic-reviewer-2",
                "reviewed_at_utc": f"2026-07-23T16:{index:02d}:00Z",
                "independent_diplomatic_transcription": f"Synthetic source {index}.",
                "punctuation_case_orthography_checked": True,
                "boundary_checked": True,
                "lineation_and_page_furniture_checked": True,
                "decision": "accept",
            }
        )
        row["source_acceptance"] = "accept"
    review_output_path = tmp_path / "synthetic-human-review.jsonl"
    review_output_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    mislabeled = lab.inspect_translation_lab_readiness(
        tree,
        laboratory_plan_path,
        manifest_path,
        review_output_path,
    )
    assert mislabeled["decision"] == "blocked"
    assert mislabeled["human_review"]["pass_1_complete"] == 0
    assert mislabeled["human_review"]["accepted_source_units"] == 0

    for row in rows:
        row["pass_1"]["reviewer_ref"] = "human:synthetic-reviewer-1"
    review_output_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    ready = lab.inspect_translation_lab_readiness(
        tree,
        laboratory_plan_path,
        manifest_path,
        review_output_path,
    )
    assert ready["decision"] == "ready-for-independent-source-grounded-pre-draft-analysis"
    assert ready["human_review"]["accepted_source_units"] == 30
    assert all(
        ready["translation_lanes"][lane]["state"] == "ready"
        for lane in (
            "human_pre_draft_analysis",
            "ai_pre_draft_analysis",
            "ai_alternative_pre_draft_analysis",
        )
    )
    assert ready["translation_lanes"]["human_only"]["state"] == "blocked"
    assert ready["translation_lanes"]["ai_only"]["state"] == "blocked"
    assert ready["translation_lanes"]["ai_alternatives"]["state"] == "blocked"
    assert ready["translation_lanes"]["ai_human"]["state"] == "blocked"
    assert ready["translation_lanes"]["recognized_comparator"]["state"] == "sealed"
    assert ready["gates"]["pre_draft_analysis"] == "blocked"


def test_cli_routes_translation_source_without_translation_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_materialize(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"fragment_count": 30, "candidate_set_sha256": "a" * 64}

    monkeypatch.setattr(lab, "materialize_translation_source", fake_materialize)
    command = [
        "materialize-translation-source",
        "--tree-repo-root",
        str(tmp_path / "tree"),
        "--sample-plan",
        str(tmp_path / "translation-samples.json"),
        "--anchors",
        str(tmp_path / "translation-anchors.jsonl"),
        "--packet-id",
        "packet-v1",
        "--visual-item-ref",
        "tos.item.test.visual",
        "--visual-file-ref",
        "tos.file.test.visual",
        "--visual-file-sha256",
        "b" * 64,
    ]

    assert lab.main(command) == 0
    assert captured["args"][3:] == (
        "packet-v1",
        "tos.item.test.visual",
        "tos.file.test.visual",
        "b" * 64,
    )


def test_cli_routes_translation_source_inspection_without_promotion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_verify(inspection: Path, manifest: Path) -> dict[str, object]:
        captured["inspection"] = inspection
        captured["manifest"] = manifest
        return {
            "summary": {
                "record_count": 30,
                "decision_counts": {
                    "accept_with_limits": 7,
                    "reject": 22,
                    "uncertain": 1,
                    "abstain": 0,
                },
            }
        }

    monkeypatch.setattr(lab, "verify_translation_source_inspection", fake_verify)
    inspection_path = tmp_path / "inspection.json"
    manifest_path = tmp_path / "manifest.json"
    assert lab.main(
        [
            "verify-translation-source-inspection",
            str(inspection_path),
            "--manifest",
            str(manifest_path),
        ]
    ) == 0
    assert captured == {
        "inspection": inspection_path,
        "manifest": manifest_path,
    }


def test_cli_routes_blank_translation_source_review_interface(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_materialize(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {
            "units": [{} for _ in range(30)],
            "render": {"unique_page_count": 89},
        }

    monkeypatch.setattr(lab, "materialize_translation_source_review", fake_materialize)
    assert lab.main(
        [
            "materialize-translation-source-review",
            "--tree-repo-root",
            str(tmp_path / "tree"),
            "--review-plan",
            str(tmp_path / "review-plan.json"),
            "--packet-id",
            "review-packet-v2",
        ]
    ) == 0
    assert captured["args"] == (
        tmp_path / "tree",
        tmp_path / "review-plan.json",
        "review-packet-v2",
    )


def test_cli_translation_gate_returns_two_while_human_source_review_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_readiness(*args: object, **kwargs: object) -> dict[str, object]:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return {"decision": "blocked", "gates": {"blocked_reasons": ["human_missing"]}}

    monkeypatch.setattr(lab, "inspect_translation_lab_readiness", fake_readiness)
    tree = tmp_path / "tree"
    plan = tmp_path / "plan.json"
    manifest = tmp_path / "manifest.json"
    references = tmp_path / "references.json"
    output = tmp_path / "human.jsonl"
    assert (
        lab.main(
            [
                "gate-translation-lab",
                "--tree-repo-root",
                str(tree),
                "--laboratory-plan",
                str(plan),
                "--reference-register",
                str(references),
                "--source-review-manifest",
                str(manifest),
                "--human-review-output",
                str(output),
            ]
        )
        == 2
    )
    assert captured["args"] == (tree, plan, manifest, output)
    assert captured["kwargs"] == {"reference_register_path": references}


def test_lexical_normalization_and_fts5_keep_source_anchors() -> None:
    assert lexical.normalize_text("  ÜBERMENSCH\nErde ") == "übermensch erde"
    passages = [
        {
            "sample_id": "sample-1",
            "anchor_ref": "anchor-1",
            "language": "de",
            "item_ref": "item-1",
            "unit": {"page": 1},
            "page": "1",
            "exact_text": "Der Uebermensch ist der Sinn der Erde.",
            "normalized_text": "der uebermensch ist der sinn der erde.",
        },
        {
            "sample_id": "sample-2",
            "anchor_ref": "anchor-2",
            "language": "ru",
            "item_ref": "item-2",
            "unit": {"page": 2},
            "page": "2",
            "exact_text": "Другой текст.",
            "normalized_text": "другой текст.",
        },
    ]
    with tempfile.TemporaryDirectory() as temporary:
        database = Path(temporary) / "index.sqlite3"
        lexical._build_index(database, passages)
        connection = lexical.sqlite3.connect(database)
        try:
            rows = lexical._query_rows(connection, '"Uebermensch ist der Sinn der Erde"')
        finally:
            connection.close()
        assert [row["source_anchor_ref"] for row in rows] == ["anchor-1"]


def test_semantic_point_identity_and_localhost_boundary_are_deterministic() -> None:
    first = semantic._point_id("sample-1", "anchor-1", "a" * 64)
    second = semantic._point_id("sample-1", "anchor-1", "a" * 64)

    assert first == second
    assert len(first) == 36
    assert semantic._validate_local_url("http://127.0.0.1:5406/") == "http://127.0.0.1:5406"
    try:
        semantic._validate_local_url("https://example.org/retrieve")
    except semantic.SemanticRetrievalError as exc:
        assert "localhost" in str(exc)
    else:
        raise AssertionError("non-local restricted-content route was accepted")


def test_semantic_hit_validation_requires_anchor_and_text_digest() -> None:
    source = {
        "anchor-1": {
            "text": "source text",
            "text_sha256": semantic._sha256_text("source text"),
        }
    }
    hit = {
        "text": "source text",
        "payload": {
            "source_anchor_ref": "anchor-1",
            "text_sha256": semantic._sha256_text("source text"),
        },
    }

    assert semantic._validate_hits([hit], source) == ["anchor-1"]
    hit["text"] = "projection drift"
    try:
        semantic._validate_hits([hit], source)
    except semantic.SemanticRetrievalError as exc:
        assert "source digest" in str(exc)
    else:
        raise AssertionError("semantic result with drifted text was accepted")


def test_granite_suite_variant_is_one_exact_independent_text_challenger() -> None:
    experiment = lab.find_experiment(lab.load_suite(), "tos-retrieval-foundation-v1")
    variant = lab.find_variant(experiment, "C")

    assert variant["model"] == granite.MODEL_ID
    assert granite.MODEL_REVISION in variant["version_posture"]
    assert variant["required_devices"] == ["CPU"]
    assert "visual" not in variant["comparison_role"]
    assert "fusion" not in variant["method"].lower()


def test_granite_normalization_is_stable_and_rejects_zero_rows() -> None:
    rows = granite_bridge._rounded_normalized_rows([[3.0, 4.0], [0.0, 2.0]])

    assert rows[0] == pytest.approx([0.6, 0.8], abs=1e-7)
    assert rows[1] == [0.0, 1.0]
    with pytest.raises(ValueError):
        granite_bridge._rounded_normalized_rows([[0.0, 0.0]])


def test_granite_cosine_ranking_is_deterministic_and_source_visible() -> None:
    passages = [
        {
            "sample_id": "sample-a",
            "source_anchor_ref": "anchor-a",
            "item_ref": "item-a",
            "language": "de",
            "unit": {"page": 1},
            "text_sha256": "a" * 64,
            "text": "first",
        },
        {
            "sample_id": "sample-b",
            "source_anchor_ref": "anchor-b",
            "item_ref": "item-b",
            "language": "ru",
            "unit": {"page": 2},
            "text_sha256": "b" * 64,
            "text": "second",
        },
    ]
    ranked = granite._rank_passages(
        [1.0, 0.0],
        passages,
        {"sample-a": [1.0, 0.0], "sample-b": [0.0, 1.0]},
        top_k=2,
    )

    assert [row["source_anchor_ref"] for row in ranked] == ["anchor-a", "anchor-b"]
    assert ranked[0]["text"] == "first"
    assert ranked[0]["score"] == 1.0


def test_granite_index_cleanup_is_limited_to_exact_run_local_path() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_root = root / "run"
        canonical = run_root / granite.INDEX_RELATIVE_PATH
        canonical.parent.mkdir(parents=True)
        canonical.write_text("{}", encoding="utf-8")

        granite._safe_remove_index(canonical, run_root)
        assert not canonical.exists()

        outside = root / "outside.json"
        outside.write_text("{}", encoding="utf-8")
        with pytest.raises(granite.GraniteRetrievalError):
            granite._safe_remove_index(outside, run_root)
        assert outside.is_file()


def test_canonical_graph_keeps_layers_paths_and_competing_claims_explicit() -> None:
    claims = [
        {
            "claim_id": "tos.claim.test.work-expression",
            "claim_type": "bibliographic",
            "subject_ref": "tos.work.test",
            "predicate": "has_expression",
            "object": "tos.expression.test",
            "evidence_refs": ["tos.item.evidence-a"],
            "maker": {"agent_ref": "model:test"},
            "provenance_event_ref": "tos.event.test",
            "review_status": "unreviewed",
            "reviews": [],
        },
        {
            "claim_id": "tos.claim.test.expression-item",
            "claim_type": "textual",
            "subject_ref": "tos.expression.test",
            "predicate": "exemplified_by",
            "object": "tos.item.test",
            "evidence_refs": ["tos.item.evidence-b"],
            "maker": {"agent_ref": "model:test"},
            "provenance_event_ref": "tos.event.test",
            "review_status": "unreviewed",
            "reviews": [],
        },
        {
            "claim_id": "tos.claim.test.sign-candidate",
            "claim_type": "semantic",
            "subject_ref": "tos.anchor.one",
            "predicate": "may_align_with",
            "object": "tos.anchor.two",
            "evidence_refs": ["tos.anchor.one", "tos.anchor.two"],
            "maker": {"agent_ref": "model:test"},
            "provenance_event_ref": "tos.event.test",
            "alternative_claim_refs": ["tos.claim.test.sign-deferred"],
            "review_status": "unreviewed",
            "reviews": [],
        },
        {
            "claim_id": "tos.claim.test.sign-deferred",
            "claim_type": "semantic",
            "subject_ref": "tos.anchor.one",
            "predicate": "alignment_status",
            "object": "deferred",
            "evidence_refs": ["tos.anchor.one", "tos.anchor.two"],
            "maker": {"agent_ref": "model:test"},
            "provenance_event_ref": "tos.event.test",
            "alternative_claim_refs": ["tos.claim.test.sign-candidate"],
            "review_status": "unreviewed",
            "reviews": [],
        },
    ]
    index = canonical_graph.build_claim_index(claims)

    claim_path, node_path = canonical_graph._claim_path(
        "tos.work.test", "tos.item.test", 2, claims
    )
    assert claim_path == [
        "tos.claim.test.work-expression",
        "tos.claim.test.expression-item",
    ]
    assert node_path == ["tos.work.test", "tos.expression.test", "tos.item.test"]
    assert canonical_graph._claim_family("tos.claim.test.sign-candidate", index) == [
        "tos.claim.test.sign-candidate",
        "tos.claim.test.sign-deferred",
    ]
    assert canonical_graph.graph_layer(claims[0]) == "bibliographic"
    assert canonical_graph.graph_layer(claims[1]) == "textual"
    assert canonical_graph.graph_layer(claims[2]) == "interpretive"
    references = {
        ref: "ToS/test.json"
        for ref in {
            "tos.work.test",
            "tos.expression.test",
            "tos.item.test",
            "tos.item.evidence-a",
            "tos.item.evidence-b",
            "tos.anchor.one",
            "tos.anchor.two",
            "tos.event.test",
        }
    }
    assert all(
        canonical_graph._trace_record(claim, Path("/"), references)["traceable"]
        for claim in claims
    )


def test_neo4j_bridge_catalog_covers_only_frozen_graph_operations() -> None:
    assert set(neo4j_bridge.query_catalog()) == {
        "subject_predicate",
        "claim_family",
        "path",
        "layer_inventory",
        "review_inventory",
        "traceability_inventory",
    }
    assert "TOS_LAB_ASSERTS" in neo4j_bridge.query_catalog()["path"]
    assert "canonical_traceable" in neo4j_bridge.query_catalog()["traceability_inventory"]
    assert "subject.ref_kind = 'tos_id'" in neo4j_bridge.query_catalog()["claim_family"]
    assert "object.ref_kind = 'literal'" in neo4j_bridge.query_catalog()["claim_family"]


def test_neo4j_claim_family_keeps_literals_out_of_identity_refs() -> None:
    normalized = neo4j_bridge._normalize_query_record(
        "claim_family",
        {
            "claim_refs": ["tos.claim.deferred", "tos.claim.candidate"],
            "node_refs": ["tos.anchor.two", "tos.anchor.one", None],
            "literal_values": ["deferred_pending_human_review", None],
        },
    )

    assert normalized["claim_refs"] == ["tos.claim.candidate", "tos.claim.deferred"]
    assert normalized["node_refs"] == ["tos.anchor.one", "tos.anchor.two"]
    assert normalized["detail"] == {
        "literal_object_values": ["deferred_pending_human_review"]
    }


def test_neo4j_projection_row_keeps_claim_review_and_literal_typing() -> None:
    claim = {
        "claim_id": "tos.claim.test",
        "claim_type": "semantic",
        "assertion_layer": "semantic_interpretation",
        "subject_ref": "tos.anchor.one",
        "predicate": "alignment_status",
        "object": "deferred",
        "evidence_refs": ["tos.anchor.one", "ToS/test.json"],
        "maker": {"agent_ref": "model:test"},
        "provenance_event_ref": "tos.event.test",
        "epistemic_status": "uncertain",
        "alternative_claim_refs": ["tos.claim.alternative"],
        "review_status": "unreviewed",
        "reviews": [],
        "visibility": "local_only",
    }

    row = neo4j_graph.projection_row(claim, {"traceable": True})

    assert row["layer"] == "interpretive"
    assert row["object_kind"] == "literal"
    assert row["review_status"] == "unreviewed"
    assert row["review_count"] == 0
    assert row["canonical_traceable"] is True
    assert row["alternative_claim_refs"] == ["tos.claim.alternative"]


def test_oxigraph_bridge_catalog_covers_only_frozen_graph_operations() -> None:
    catalog = oxigraph_bridge.query_catalog()

    assert set(catalog) == {
        "subject_predicate",
        "claim_family",
        "path",
        "layer_inventory",
        "review_inventory",
        "traceability_inventory",
    }
    assert "tos:alternativeTo" in catalog["claim_family"]
    assert "GRAPH ?graph" in catalog["traceability_inventory"]
    assert "tos:claimOrder" in catalog["path"]
    assert all("<<" not in query and ">>" not in query for query in catalog.values())


def test_oxigraph_identity_and_claim_graph_iris_are_stable_and_separate() -> None:
    claim_id = "tos.claim.test"
    lab_run = "tos_graph_c_test_20260722"

    assert oxigraph_bridge.claim_iri(claim_id) == "urn:tos:claim:tos.claim.test"
    assert oxigraph_bridge.ref_iri("tos.anchor.test") == "urn:tos:id:tos.anchor.test"
    assert oxigraph_bridge.ref_iri("ToS/test.json", "repo_path") == "urn:tos:path:ToS%2Ftest.json"
    assert oxigraph_bridge.graph_iri(lab_run, claim_id) == (
        "urn:tos:graph:tos_graph_c_test_20260722:claim:tos.claim.test"
    )
    assert oxigraph_bridge.claim_iri(claim_id) != oxigraph_bridge.graph_iri(lab_run, claim_id)


def test_oxigraph_projection_row_keeps_claim_review_and_literal_typing() -> None:
    claim = {
        "claim_id": "tos.claim.test",
        "claim_type": "semantic",
        "assertion_layer": "semantic_interpretation",
        "subject_ref": "tos.anchor.one",
        "predicate": "alignment_status",
        "object": "deferred",
        "evidence_refs": ["tos.anchor.one", "ToS/test.json"],
        "maker": {"agent_ref": "model:test"},
        "provenance_event_ref": "tos.event.test",
        "epistemic_status": "uncertain",
        "alternative_claim_refs": ["tos.claim.alternative"],
        "review_status": "unreviewed",
        "reviews": [],
        "visibility": "local_only",
    }

    row = oxigraph_graph.projection_row(claim, {"traceable": True})

    assert row["layer"] == "interpretive"
    assert row["subject_kind"] == "tos_id"
    assert row["object_kind"] == "literal"
    assert row["review_status"] == "unreviewed"
    assert row["review_count"] == 0
    assert row["canonical_traceable"] is True
    assert row["alternative_claim_refs"] == ["tos.claim.alternative"]


def test_oxigraph_store_cleanup_is_limited_to_exact_run_local_path() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        run_root = root / "run"
        canonical_store = run_root / "derived-store/oxigraph"
        canonical_store.mkdir(parents=True)
        (canonical_store / "marker").write_text("test", encoding="utf-8")

        oxigraph_graph._safe_remove_store(canonical_store, run_root)
        assert not canonical_store.exists()

        outside = root / "outside"
        outside.mkdir()
        with pytest.raises(oxigraph_graph.OxigraphGraphError):
            oxigraph_graph._safe_remove_store(outside, run_root)
        assert outside.is_dir()


def test_awaiting_manual_review_is_a_valid_non_promoted_run_status() -> None:
    suite = lab.load_suite()
    experiment = lab.find_experiment(suite, "tos-structure-recovery-v1")
    variant = lab.find_variant(experiment, "A")
    preflight = {
        "experiment_id": experiment["experiment_id"],
        "experiment_sha256": lab.sha256_json(experiment),
        "variant": "A",
        "decision": "ready",
    }
    with tempfile.TemporaryDirectory() as temporary:
        durable = Path(temporary) / "durable"
        suite_copy = json.loads(json.dumps(suite))
        suite_copy["artifact_roots"]["durable"] = durable.as_posix()
        run_root = lab.prepare_run(
            suite_copy,
            experiment,
            variant,
            preflight,
            "manual-review-boundary",
            durable,
        )
        receipt_path = run_root / "run.receipt.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["status"] = "awaiting-manual-review"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        assert lab.verify_run(run_root) == []
