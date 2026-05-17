from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
BABELVOX_APP = ROOT / "config-templates" / "Services" / "babelvox-tts-api" / "app" / "main.py"
RAG_APP = ROOT / "config-templates" / "Services" / "rag-api" / "app" / "main.py"


def load_module(path: Path, stem: str):
    module_name = f"{stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def stub_babelvox_dependencies(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "soundfile", types.SimpleNamespace(write=lambda *args, **kwargs: None))


def test_babelvox_save_path_rejects_parent_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AOA_BABELVOX_TTS_OUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("AOA_BABELVOX_TTS_FAKE", "1")
    stub_babelvox_dependencies(monkeypatch)
    app = load_module(BABELVOX_APP, "babelvox_tts_api")

    with pytest.raises(HTTPException) as exc_info:
        app.safe_save_path("../../etc/cron.d/pwn")

    assert exc_info.value.status_code == 400
    assert not (tmp_path / "etc").exists()


def test_babelvox_save_path_keeps_relative_outputs_under_out_dir(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / "out"
    monkeypatch.setenv("AOA_BABELVOX_TTS_OUT_DIR", str(out_dir))
    monkeypatch.setenv("AOA_BABELVOX_TTS_FAKE", "1")
    stub_babelvox_dependencies(monkeypatch)
    app = load_module(BABELVOX_APP, "babelvox_tts_api")

    path = app.safe_save_path("nested/demo")

    assert path == (out_dir / "nested" / "demo.wav").resolve()
    assert path.parent.is_dir()


def test_rag_chunk_settings_reject_non_shrinking_overlap() -> None:
    app = load_module(RAG_APP, "rag_api")

    with pytest.raises(RuntimeError, match="less than"):
        app.validate_chunk_settings(100, 100)

    with pytest.raises(RuntimeError, match="less than"):
        app.validate_chunk_settings(100, 120)


def test_rag_app_fails_fast_when_overlap_env_cannot_shrink_chunks(monkeypatch) -> None:
    monkeypatch.setenv("AOA_RAG_MAX_CHUNK_CHARS", "100")
    monkeypatch.setenv("AOA_RAG_CHUNK_OVERLAP_CHARS", "100")

    with pytest.raises(RuntimeError, match="less than"):
        load_module(RAG_APP, "rag_api")
