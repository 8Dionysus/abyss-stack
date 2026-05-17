import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def find_repo_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (
            (candidate / "AGENTS.md").is_file()
            and (candidate / "scripts").is_dir()
            and (candidate / "mechanics").is_dir()
        ):
            return candidate
    raise RuntimeError("could not locate abyss-stack repository root")


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)
MODULE_PATH = (
    REPO_ROOT
    / "mechanics"
    / "inference-pilots"
    / "parts"
    / "llamacpp-pilot"
    / "aoa_llamacpp_pilot.py"
)


def load_module():
    loader = importlib.machinery.SourceFileLoader("aoa_llamacpp_pilot_under_test", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LlamacppPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_resolve_model_info_marks_curated_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            model_root = temp_root / "bartowski"
            model_root.mkdir(parents=True, exist_ok=True)
            model_path = model_root / "Qwen_Qwen3.5-9B-Q4_K_M.gguf"
            model_path.write_bytes(b"GGUFtest")

            with patch.object(self.module, "MODEL_STORE_ROOT", model_root):
                with patch.object(self.module, "ollama_runtime_details", return_value=None):
                    payload = self.module.resolve_model_info(str(model_path))

        self.assertEqual(payload["reuse_strategy"], "curated_bartowski_candidate")
        self.assertEqual(payload["candidate_quant"], "Q4_K_M")
        self.assertEqual(payload["model_host_path"], str(model_path.resolve()))

    def test_should_try_curated_fallback_only_for_resident_model_load_failure(self) -> None:
        self.assertTrue(
            self.module.should_try_curated_fallback(
                model_info={"reuse_strategy": "resident_ollama_gguf_blob"},
                llama_ready={"error": "llama.cpp reported a model-load failure"},
            )
        )
        self.assertFalse(
            self.module.should_try_curated_fallback(
                model_info={"reuse_strategy": "curated_bartowski_candidate"},
                llama_ready={"error": "llama.cpp reported a model-load failure"},
            )
        )
        self.assertFalse(
            self.module.should_try_curated_fallback(
                model_info={"reuse_strategy": "resident_ollama_gguf_blob"},
                llama_ready={"error": "timeout waiting for llama.cpp health"},
            )
        )

    def test_resolve_startable_model_falls_back_to_curated_candidate(self) -> None:
        resident = {"model_host_path": "/tmp/resident.gguf", "reuse_strategy": "resident_ollama_gguf_blob"}
        fallback = {
            "model_host_path": "/tmp/fallback.gguf",
            "reuse_strategy": "curated_bartowski_fallback",
            "candidate_quant": "Q4_K_M",
        }
        attempts = [
            (
                {"ready": False, "error": "llama.cpp reported a model-load failure"},
                {"ready": False},
            ),
            (
                {"ready": True},
                {"ready": True},
            ),
        ]

        with patch.object(self.module, "curated_fallback_model_infos", return_value=[fallback]):
            with patch.object(self.module, "stop_sidecars") as stop_sidecars:
                with patch.object(self.module, "start_candidate_sidecar", side_effect=attempts):
                    chosen, llama_ready, candidate_ready, trace = self.module.resolve_startable_model(
                        initial_model_info=resident,
                        wait_timeout=30.0,
                        allow_curated_fallback=True,
                    )

        self.assertEqual(chosen["model_host_path"], fallback["model_host_path"])
        self.assertTrue(llama_ready["ready"])
        self.assertTrue(candidate_ready["ready"])
        self.assertEqual(len(trace), 2)
        self.assertEqual(trace[0]["reuse_strategy"], "resident_ollama_gguf_blob")
        self.assertEqual(trace[1]["reuse_strategy"], "curated_bartowski_fallback")
        stop_sidecars.assert_called_once()

    def test_parse_prometheus_metrics_keeps_llamacpp_values(self) -> None:
        payload = self.module.parse_prometheus_metrics(
            "\n".join(
                [
                    "# HELP ignored",
                    "llamacpp:prompt_tokens_total 895",
                    "llamacpp:prompt_tokens_seconds 12.3872",
                    "other_metric 99",
                    "llamacpp:requests_deferred not-a-number",
                ]
            )
        )

        self.assertEqual(payload["llamacpp:prompt_tokens_total"], 895.0)
        self.assertEqual(payload["llamacpp:prompt_tokens_seconds"], 12.3872)
        self.assertNotIn("other_metric", payload)
        self.assertNotIn("llamacpp:requests_deferred", payload)

    def test_summarize_llama_logs_counts_cache_signatures(self) -> None:
        summary = self.module.summarize_llama_logs(
            "\n".join(
                [
                    "slot update_slots: restored context checkpoint (pos_min = 118)",
                    "slot update_slots: forcing full prompt re-processing due to lack of cache data",
                    "srv update: - cache state: 2 prompts",
                    "srv get_availabl: prompt cache update took 73.91 ms",
                    "slot get_availabl: selected slot by LCP similarity, sim_best = 1.000",
                    "srv get_availabl: prompt cache update took 349.11 ms",
                ]
            )
        )

        self.assertEqual(summary["restored_context_checkpoint"]["count"], 1)
        self.assertEqual(summary["full_prompt_reprocessing"]["count"], 1)
        self.assertEqual(summary["cache_state"]["count"], 1)
        self.assertEqual(summary["selected_lcp_similarity"]["count"], 1)
        self.assertEqual(summary["prompt_cache_update_ms"]["count"], 2)
        self.assertEqual(summary["prompt_cache_update_ms"]["min"], 73.91)
        self.assertEqual(summary["prompt_cache_update_ms"]["max"], 349.11)
