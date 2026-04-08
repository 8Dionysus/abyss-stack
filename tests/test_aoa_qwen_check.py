import importlib.machinery
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "aoa-qwen-check"


def load_module():
    loader = importlib.machinery.SourceFileLoader("aoa_qwen_check_under_test", str(MODULE_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class QwenCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_build_prompt_supports_new_repo_choice_case(self) -> None:
        prompt, max_tokens = self.module.build_prompt("repo-choice")

        self.assertIn("Allowed answers: aoa-evals, abyss-stack, Tree-of-Sophia.", prompt)
        self.assertEqual(max_tokens, 8)

    def test_build_prompt_supports_new_json_decision_case(self) -> None:
        prompt, max_tokens = self.module.build_prompt("json-decision")

        self.assertIn('{"verdict":"...","repo":"..."}', prompt)
        self.assertEqual(max_tokens, 32)

    def test_run_check_validates_repo_choice_exact_token(self) -> None:
        fake_payload = {
            "answer": "aoa-evals",
            "backend": "langchain",
            "model": "OpenVINO/Qwen3-8B-int4-ov",
        }

        with patch.object(self.module.urllib.request, "urlopen", return_value=FakeHTTPResponse(fake_payload)):
            result = self.module.run_check(
                url="http://example.test/run",
                case="repo-choice",
                timeout_s=5.0,
                temperature=0.0,
                max_tokens=None,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["validation"]["expected"], "aoa-evals")
        self.assertEqual(result["validation"]["observed"], "aoa-evals")

    def test_run_check_validates_json_decision_from_fenced_block(self) -> None:
        fake_payload = {
            "answer": '```json\n{"verdict":"candidate","repo":"abyss-stack"}\n```',
            "backend": "langchain",
            "model": "OpenVINO/Qwen3-8B-int4-ov",
        }

        with patch.object(self.module.urllib.request, "urlopen", return_value=FakeHTTPResponse(fake_payload)):
            result = self.module.run_check(
                url="http://example.test/run",
                case="json-decision",
                timeout_s=5.0,
                temperature=0.0,
                max_tokens=None,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["validation"]["expected"],
            {"verdict": "candidate", "repo": "abyss-stack"},
        )
        self.assertEqual(
            result["validation"]["observed"],
            {"verdict": "candidate", "repo": "abyss-stack"},
        )
