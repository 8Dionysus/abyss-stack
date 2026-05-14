from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[5]


def write_fake_curl(fakebin: Path, body: str) -> Path:
    curl_path = fakebin / "curl"
    curl_path.write_text(body, encoding="utf-8")
    curl_path.chmod(0o755)
    return curl_path


class AoaWarmupTests(unittest.TestCase):
    def warmup_env(self, tmpdir: str, fakebin: Path) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "AOA_CONFIGS_ROOT": str(REPO_ROOT),
                "AOA_STACK_ROOT": str(Path(tmpdir) / "runtime"),
                "AOA_VAULT_ROOT": str(Path(tmpdir) / "vault"),
                "AOA_MACHINE_FIT_AUTO_APPLY": "false",
                "PATH": f"{fakebin}:{env['PATH']}",
            }
        )
        return env

    def run_warmup(self, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO_ROOT / "scripts" / "aoa-warmup"), *args],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_fallback_gateway_does_not_warm_ollama_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fakebin = Path(tmpdir) / "bin"
            fakebin.mkdir()
            curl_log = Path(tmpdir) / "curl.log"
            write_fake_curl(
                fakebin,
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf '%s\n' "$*" >> "$AOA_TEST_CURL_LOG"
                    exit 23
                    """
                ),
            )
            env = self.warmup_env(tmpdir, fakebin)
            env["AOA_TEST_CURL_LOG"] = str(curl_log)

            result = self.run_warmup(["--profile", "fallback-gateway"], env)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ollama warmup disabled", result.stdout)
            self.assertNotIn("warming ollama model", result.stdout)
            self.assertFalse(curl_log.exists())

    def test_combined_worker_and_fallback_can_warm_both_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fakebin = Path(tmpdir) / "bin"
            fakebin.mkdir()
            curl_log = Path(tmpdir) / "curl.log"
            write_fake_curl(
                fakebin,
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf '%s\n' "$*" >> "$AOA_TEST_CURL_LOG"
                    target="${@: -1}"
                    case "$target" in
                      */api/ps)
                        printf '{"models":[{"model":"qwen3.5:9b"}]}'
                        ;;
                      */api/chat)
                        printf '{"message":{"content":"ok"}}'
                        ;;
                      *)
                        printf '{}'
                        ;;
                    esac
                    """
                ),
            )
            env = self.warmup_env(tmpdir, fakebin)
            env.update(
                {
                    "AOA_TEST_CURL_LOG": str(curl_log),
                    "AOA_OLLAMA_WARMUP_ENABLED": "true",
                    "AOA_LLAMACPP_WARMUP_ENABLED": "true",
                }
            )

            result = self.run_warmup(
                ["--profile", "local-worker", "--profile", "fallback-gateway"],
                env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("llama.cpp warmup complete", result.stdout)
            self.assertIn("ollama warmup complete for qwen3.5:9b", result.stdout)
            curl_calls = curl_log.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1:11435/health", curl_calls)
            self.assertIn("127.0.0.1:11434/api/tags", curl_calls)
            self.assertIn("127.0.0.1:11434/api/chat", curl_calls)
            self.assertIn("127.0.0.1:11434/api/ps", curl_calls)

    def test_llamacpp_timeout_does_not_block_enabled_ollama_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fakebin = Path(tmpdir) / "bin"
            fakebin.mkdir()
            curl_log = Path(tmpdir) / "curl.log"
            write_fake_curl(
                fakebin,
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    printf '%s\n' "$*" >> "$AOA_TEST_CURL_LOG"
                    target="${@: -1}"
                    case "$target" in
                      *11435/health)
                        exit 7
                        ;;
                      */api/ps)
                        printf '{"models":[{"model":"qwen3.5:9b"}]}'
                        ;;
                      */api/chat)
                        printf '{"message":{"content":"ok"}}'
                        ;;
                      *)
                        printf '{}'
                        ;;
                    esac
                    """
                ),
            )
            env = self.warmup_env(tmpdir, fakebin)
            env.update(
                {
                    "AOA_TEST_CURL_LOG": str(curl_log),
                    "AOA_OLLAMA_WARMUP_ENABLED": "true",
                    "AOA_LLAMACPP_WARMUP_ENABLED": "true",
                    "AOA_LLAMACPP_WARMUP_WAIT_S": "0",
                }
            )

            result = self.run_warmup(
                ["--profile", "local-worker", "--profile", "fallback-gateway"],
                env,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("warn llama.cpp warmup skipped", result.stdout)
            self.assertIn("ollama warmup complete for qwen3.5:9b", result.stdout)
            curl_calls = curl_log.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1:11435/health", curl_calls)
            self.assertIn("127.0.0.1:11434/api/chat", curl_calls)


if __name__ == "__main__":
    unittest.main()
