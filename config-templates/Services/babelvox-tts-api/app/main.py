from __future__ import annotations

import base64
import ctypes
import gc
import math
import os
import threading
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def env_str(name: str, default: str) -> str:
    return os.environ.get(name) or default


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a float") from exc


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


SERVICE_NAME = "babelvox-tts-api"
DEVICE = env_str("AOA_BABELVOX_TTS_DEVICE", "NPU")
PRECISION = env_str("AOA_BABELVOX_TTS_PRECISION", "int8")
CACHE_DIR = Path(env_str("AOA_BABELVOX_TTS_CACHE_DIR", "/cache/babelvox"))
OUT_DIR = Path(env_str("AOA_BABELVOX_TTS_OUT_DIR", "/out"))
LANGUAGE = env_str("AOA_BABELVOX_TTS_LANGUAGE", "Russian")
USE_KV_CACHE = env_bool("AOA_BABELVOX_TTS_USE_KV_CACHE", True)
USE_CP_KV_CACHE = env_bool("AOA_BABELVOX_TTS_USE_CP_KV_CACHE", True)
MAX_KV_LEN = env_int("AOA_BABELVOX_TTS_MAX_KV_LEN", 64)
MAX_SPEAKER_FRAMES = env_int("AOA_BABELVOX_TTS_MAX_SPEAKER_FRAMES", 128)
MAX_DECODER_FRAMES = env_int("AOA_BABELVOX_TTS_MAX_DECODER_FRAMES", 64)
MAX_TALKER_SEQ = env_int("AOA_BABELVOX_TTS_MAX_TALKER_SEQ", 0)
MAX_CP_SEQ = env_int("AOA_BABELVOX_TTS_MAX_CP_SEQ", 0)
MAX_NEW_TOKENS = env_int("AOA_BABELVOX_TTS_MAX_NEW_TOKENS", 44)
TEMPERATURE = env_float("AOA_BABELVOX_TTS_TEMPERATURE", 0.8)
TOP_K = env_int("AOA_BABELVOX_TTS_TOP_K", 30)
TOP_P = env_float("AOA_BABELVOX_TTS_TOP_P", 1.0)
REPETITION_PENALTY = env_float("AOA_BABELVOX_TTS_REPETITION_PENALTY", 1.05)
IDLE_UNLOAD_SEC = env_int("AOA_BABELVOX_TTS_IDLE_UNLOAD_SEC", 900)
IDLE_UNLOAD_CHECK_SEC = env_int("AOA_BABELVOX_TTS_IDLE_UNLOAD_CHECK_SEC", 60)
EXIT_AFTER_IDLE_UNLOAD = env_bool("AOA_BABELVOX_TTS_EXIT_AFTER_IDLE_UNLOAD", True)
FAKE_MODE = env_bool("AOA_BABELVOX_TTS_FAKE", False)


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1)
    language: str | None = None
    save_name: str | None = None
    return_audio_base64: bool = True
    max_new_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = None
    top_k: int | None = Field(default=None, ge=1)
    top_p: float | None = None
    repetition_penalty: float | None = None


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def trim_process_heap() -> bool:
    try:
        libc = ctypes.CDLL("libc.so.6")
        return bool(libc.malloc_trim(0))
    except Exception:
        return False


def safe_save_path(save_name: str | None) -> Path:
    out_dir = OUT_DIR.resolve()
    if save_name:
        clean = save_name.replace("\\", "/").lstrip("/")
        path = out_dir / clean
        if path.suffix.lower() != ".wav":
            path = path.with_suffix(".wav")
    else:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = out_dir / f"{stamp}-babelvox.wav"
    path = path.resolve()
    try:
        path.relative_to(out_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="save_name escapes output directory") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def audio_payload(wav: np.ndarray, sample_rate: int, include_base64: bool) -> dict[str, Any]:
    audio_sec = round(float(len(wav)) / float(sample_rate), 3) if sample_rate else None
    payload: dict[str, Any] = {
        "sample_rate": int(sample_rate),
        "samples": int(len(wav)),
        "audio_sec": audio_sec,
    }
    if include_base64:
        bio = BytesIO()
        sf.write(bio, wav, sample_rate, format="WAV")
        payload["wav_base64"] = base64.b64encode(bio.getvalue()).decode("ascii")
    return payload


def fake_speech(text: str) -> tuple[np.ndarray, int]:
    sample_rate = 24000
    duration = min(3.0, max(0.4, 0.045 * len(text)))
    samples = max(1, int(sample_rate * duration))
    timeline = np.linspace(0.0, duration, samples, endpoint=False)
    wav = 0.08 * np.sin(2.0 * math.pi * 220.0 * timeline)
    return wav.astype(np.float32), sample_rate


class LazyBabelVox:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._model: Any | None = None
        self._load_ms: float | None = None
        self._loaded_at_epoch: float | None = None
        self._last_used_epoch: float | None = None
        self._last_used_monotonic: float | None = None
        self._last_unload_epoch: float | None = None
        self._last_unload_reason: str | None = None
        self._active_requests = 0

    @property
    def loaded(self) -> bool:
        return self._model is not None

    @property
    def load_ms(self) -> float | None:
        return self._load_ms

    @property
    def loaded_at_epoch(self) -> float | None:
        return self._loaded_at_epoch

    @property
    def last_used_epoch(self) -> float | None:
        return self._last_used_epoch

    @property
    def last_unload_epoch(self) -> float | None:
        return self._last_unload_epoch

    @property
    def last_unload_reason(self) -> str | None:
        return self._last_unload_reason

    @property
    def active_requests(self) -> int:
        return self._active_requests

    @property
    def idle_for_sec(self) -> float | None:
        if self._model is None or self._last_used_monotonic is None:
            return None
        return round(max(0.0, time.monotonic() - self._last_used_monotonic), 3)

    def begin_request(self) -> None:
        with self._lock:
            self._active_requests += 1

    def end_request(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def _mark_used(self) -> None:
        self._last_used_epoch = time.time()
        self._last_used_monotonic = time.monotonic()

    def _load(self) -> Any:
        if FAKE_MODE:
            self._load_ms = 0.0
            self._loaded_at_epoch = time.time()
            return object()
        from babelvox import BabelVox

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {
            "device": DEVICE,
            "precision": PRECISION,
            "cache_dir": str(CACHE_DIR),
            "use_kv_cache": USE_KV_CACHE,
            "use_cp_kv_cache": USE_CP_KV_CACHE,
        }
        for key, value in {
            "max_kv_len": MAX_KV_LEN,
            "max_speaker_frames": MAX_SPEAKER_FRAMES,
            "max_decoder_frames": MAX_DECODER_FRAMES,
            "max_talker_seq": MAX_TALKER_SEQ,
            "max_cp_seq": MAX_CP_SEQ,
        }.items():
            if value > 0:
                kwargs[key] = value
        started = now_ms()
        model = BabelVox(**kwargs)
        self._load_ms = round(now_ms() - started, 3)
        self._loaded_at_epoch = time.time()
        return model

    def synthesize(self, req: SpeechRequest) -> dict[str, Any]:
        with self._lock:
            if self._model is None:
                self._model = self._load()
            model = self._model
            self._mark_used()

        synth_started = now_ms()
        if FAKE_MODE:
            wav, sample_rate = fake_speech(req.text)
        else:
            generate_kwargs = {
                "language": req.language or LANGUAGE,
                "max_new_tokens": req.max_new_tokens or MAX_NEW_TOKENS,
                "temperature": req.temperature if req.temperature is not None else TEMPERATURE,
                "top_k": req.top_k or TOP_K,
                "top_p": req.top_p if req.top_p is not None else TOP_P,
                "repetition_penalty": (
                    req.repetition_penalty
                    if req.repetition_penalty is not None
                    else REPETITION_PENALTY
                ),
            }
            wav, sample_rate = model.generate(req.text, **generate_kwargs)
        synth_ms = round(now_ms() - synth_started, 3)

        path = safe_save_path(req.save_name)
        sf.write(path, wav, sample_rate)
        audio = audio_payload(wav, sample_rate, req.return_audio_base64)
        audio["path"] = str(path)
        audio["size_bytes"] = path.stat().st_size
        return {
            "ok": True,
            "service": SERVICE_NAME,
            "backend": "babelvox_openvino",
            "device": DEVICE,
            "precision": PRECISION,
            "text_chars": len(req.text),
            "load_ms": self._load_ms,
            "synth_ms": synth_ms,
            "wall_ms": synth_ms,
            "rtf": round((synth_ms / 1000.0) / audio["audio_sec"], 4) if audio.get("audio_sec") else None,
            "audio": audio,
            "fake_mode": FAKE_MODE,
        }

    def unload(self, reason: str, *, exit_process: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._active_requests > 0:
                return {
                    "ok": False,
                    "unloaded": False,
                    "reason": "active_requests",
                    "active_requests": self._active_requests,
                    "loaded": self.loaded,
                }
            was_loaded = self._model is not None
            load_ms = self._load_ms
            self._model = None
            self._load_ms = None
            self._loaded_at_epoch = None
            self._last_unload_epoch = time.time()
            self._last_unload_reason = reason
        heap_trimmed = False
        if was_loaded:
            gc.collect()
            heap_trimmed = trim_process_heap()
        response = {
            "ok": True,
            "unloaded": was_loaded,
            "reason": reason,
            "load_ms": load_ms,
            "loaded": self.loaded,
            "heap_trimmed": heap_trimmed,
            "exit_process": exit_process and was_loaded,
        }
        if exit_process and was_loaded:
            threading.Timer(0.2, lambda: os._exit(0)).start()
        return response

    def unload_if_idle(self, idle_unload_sec: int) -> dict[str, Any]:
        if idle_unload_sec <= 0:
            return {"ok": True, "unloaded": False, "reason": "disabled", "loaded": self.loaded}
        with self._lock:
            if self._active_requests > 0:
                return {
                    "ok": True,
                    "unloaded": False,
                    "reason": "active_requests",
                    "active_requests": self._active_requests,
                    "loaded": self.loaded,
                }
            if self._model is None or self._last_used_monotonic is None:
                return {"ok": True, "unloaded": False, "reason": "not_loaded", "loaded": self.loaded}
            idle_for = time.monotonic() - self._last_used_monotonic
            if idle_for < idle_unload_sec:
                return {
                    "ok": True,
                    "unloaded": False,
                    "reason": "not_idle",
                    "idle_for_sec": round(idle_for, 3),
                    "loaded": self.loaded,
                }
        return self.unload(f"idle_for_{int(idle_unload_sec)}s", exit_process=EXIT_AFTER_IDLE_UNLOAD)


engine = LazyBabelVox()
app = FastAPI(title="Abyss Stack BabelVox TTS API", version="0.1.0")


def idle_unload_loop() -> None:
    interval = max(5, IDLE_UNLOAD_CHECK_SEC)
    while True:
        time.sleep(interval)
        engine.unload_if_idle(IDLE_UNLOAD_SEC)


if IDLE_UNLOAD_SEC > 0 and not FAKE_MODE:
    threading.Thread(target=idle_unload_loop, name="babelvox-tts-idle-unloader", daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "backend": "babelvox_openvino",
        "device": DEVICE,
        "precision": PRECISION,
        "cache_dir": str(CACHE_DIR),
        "cache_dir_exists": CACHE_DIR.is_dir(),
        "out_dir": str(OUT_DIR),
        "loaded": engine.loaded,
        "load_ms": engine.load_ms,
        "loaded_at_epoch": engine.loaded_at_epoch,
        "last_used_epoch": engine.last_used_epoch,
        "idle_for_sec": engine.idle_for_sec,
        "idle_unload_sec": IDLE_UNLOAD_SEC,
        "idle_unload_check_sec": IDLE_UNLOAD_CHECK_SEC,
        "exit_after_idle_unload": EXIT_AFTER_IDLE_UNLOAD,
        "active_requests": engine.active_requests,
        "last_unload_epoch": engine.last_unload_epoch,
        "last_unload_reason": engine.last_unload_reason,
        "fake_mode": FAKE_MODE,
    }


@app.post("/admin/unload")
def unload(exit_process: bool = False) -> dict[str, Any]:
    return engine.unload("admin_request", exit_process=exit_process)


@app.post("/synthesize")
@app.post("/custom")
@app.post("/v1/audio/speech")
def synthesize(req: SpeechRequest) -> dict[str, Any]:
    engine.begin_request()
    started = now_ms()
    try:
        try:
            response = engine.synthesize(req)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"TTS failed: {type(exc).__name__}: {exc}") from exc
        response["wall_ms"] = round(now_ms() - started, 3)
        return response
    finally:
        engine.end_request()
