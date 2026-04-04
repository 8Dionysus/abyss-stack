import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "aoa-llamacpp-pilot"


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
