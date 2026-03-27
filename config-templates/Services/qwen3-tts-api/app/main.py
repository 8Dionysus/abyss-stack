import os
import base64
from io import BytesIO
from typing import Dict, Optional

import torch
import soundfile as sf
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from qwen_tts import Qwen3TTSModel

app = FastAPI(title="AoA Qwen3-TTS API", version="0.2-local-only")

DEFAULT_MODEL = os.getenv(
    "QWEN_TTS_DEFAULT_MODEL",
    "/models/hf/local/Qwen3-TTS-12Hz-1.7B-CustomVoice"
)
DEVICE = os.getenv("QWEN_TTS_DEVICE", "cpu")
DTYPE  = os.getenv("QWEN_TTS_DTYPE", "float32")
OUT_DIR = os.getenv("QWEN_TTS_OUT_DIR", "/out")

LOCAL_ONLY = os.getenv("AOA_TTS_LOCAL_ONLY", "1") == "1"
LOCAL_PREFIX = os.getenv("QWEN_TTS_LOCAL_PREFIX", "/models/hf/local/")

_models: Dict[str, Qwen3TTSModel] = {}

def _torch_dtype(dtype_str: str):
    s = dtype_str.lower()
    if s in ("bf16", "bfloat16"):
        return torch.bfloat16
    if s in ("fp16", "float16"):
        return torch.float16
    return torch.float32

def _assert_local(model_id: str):
    if LOCAL_ONLY and not model_id.startswith(LOCAL_PREFIX):
        raise HTTPException(
            status_code=400,
            detail=f"Local-only mode is ON. Use a local model path under {LOCAL_PREFIX}"
        )

def get_model(model_id: str) -> Qwen3TTSModel:
    _assert_local(model_id)
    if model_id not in _models:
        _models[model_id] = Qwen3TTSModel.from_pretrained(
            model_id,
            device_map=DEVICE,
            dtype=_torch_dtype(DTYPE),
        )
    return _models[model_id]

class CustomReq(BaseModel):
    text: str = Field(..., min_length=1)
    language: str = "Russian"
    speaker: str = "Aiden"
    instruct: str = ""
    model_id: Optional[str] = None
    save_name: Optional[str] = None

@app.get("/health")
def health():
    return {
        "ok": True,
        "default_model": DEFAULT_MODEL,
        "device": DEVICE,
        "dtype": DTYPE,
        "local_only": LOCAL_ONLY,
        "local_prefix": LOCAL_PREFIX,
    }

@app.post("/custom")
def tts_custom(req: CustomReq):
    model_id = req.model_id or DEFAULT_MODEL
    model = get_model(model_id)

    try:
        wavs, sr = model.generate_custom_voice(
            text=req.text,
            language=req.language,
            speaker=req.speaker,
            instruct=req.instruct,
        )
        wav = wavs[0]

        # base64 (для n8n/интеграций)
        bio = BytesIO()
        sf.write(bio, wav, sr, format="WAV")
        b64 = base64.b64encode(bio.getvalue()).decode("ascii")

        out_path = None
        if req.save_name:
            os.makedirs(OUT_DIR, exist_ok=True)
            name = req.save_name if req.save_name.endswith(".wav") else req.save_name + ".wav"
            out_path = os.path.join(OUT_DIR, name)

            # ВАЖНО: создаём вложенные папки, если save_name содержит "/"
            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            sf.write(out_path, wav, sr)


        return {"model_id": model_id, "sr": sr, "wav_base64": b64, "saved_path": out_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
