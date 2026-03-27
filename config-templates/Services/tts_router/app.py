import os, re, time
from pathlib import Path
import yaml, requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

CFG_PATH = os.environ.get("VOICE_CFG", "/cfg/voices.yaml")
BACKEND = os.environ.get("TTS_BACKEND_URL", "http://qwen-tts:5001/custom")
LOG_DIR = Path(os.environ.get("TTS_LOG_DIR", "/logs"))
VOICE_STORE = Path(os.environ.get("VOICE_STORE", "/voices"))

app = FastAPI(title="AoA TTS Router", version="1.1-voice-store")

_cfg = {}

def load_cfg():
    global _cfg
    with open(CFG_PATH, "r", encoding="utf-8") as f:
        _cfg = yaml.safe_load(f) or {}

def safe_name(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^a-zA-Z0-9_.\-]+", "_", s)
    return s[:80] if s else ""

def ensure_wav(name: str) -> str:
    return name if name.lower().endswith(".wav") else name + ".wav"

def load_voice(voice_id: str) -> dict:
    vid = safe_name(voice_id)
    p = VOICE_STORE / vid / "voice.yaml"
    if not p.exists():
        raise HTTPException(400, f"voice_id '{vid}' not found at {p}")
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception as e:
        raise HTTPException(500, f"failed to read {p}: {e}")

class SpeakIn(BaseModel):
    text: str
    agent_id: str | None = None
    profile: str | None = None
    voice_id: str | None = None

    # overrides:
    language: str | None = None
    speaker: str | None = None
    instruct: str | None = None
    model_id: str | None = None
    save_name: str | None = None

@app.on_event("startup")
def _startup():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_STORE.mkdir(parents=True, exist_ok=True)
    load_cfg()

@app.get("/health")
def health():
    return {"ok": True, "backend": BACKEND, "cfg": CFG_PATH, "voice_store": str(VOICE_STORE)}

@app.post("/reload")
def reload_cfg():
    load_cfg()
    return {"ok": True}

@app.get("/voices")
def voices():
    items = []
    for d in sorted(VOICE_STORE.glob("*")):
        if d.is_dir() and (d / "voice.yaml").exists():
            items.append(d.name)
    return {"voices": items}

@app.post("/speak")
def speak(inp: SpeakIn):
    if not inp.text or not inp.text.strip():
        raise HTTPException(400, "text is empty")

    agents = _cfg.get("agents") or {}
    profiles = _cfg.get("profiles") or {}
    default_profile = _cfg.get("default_profile")

    agent_id = safe_name(inp.agent_id or inp.voice_id or "unknown_agent")
    prof_name = inp.profile or (agents.get(agent_id, {}) or {}).get("profile") or default_profile
    prof = profiles.get(prof_name) or profiles.get(default_profile) or {}

    # voice selection order:
    voice_id = inp.voice_id or prof.get("voice_id") or (agents.get(agent_id, {}) or {}).get("voice_id")

    voice_cfg = load_voice(voice_id) if voice_id else {}

    # merge priority: input overrides > profile > voice.yaml
    model_id = inp.model_id or prof.get("model_id") or voice_cfg.get("model_id")
    language = inp.language or prof.get("language") or voice_cfg.get("language") or "Russian"
    speaker  = inp.speaker  or prof.get("speaker")  or voice_cfg.get("speaker")  or "Aiden"
    instruct = inp.instruct if inp.instruct is not None else (prof.get("instruct") if prof.get("instruct") is not None else (voice_cfg.get("instruct") or ""))

    if not model_id:
        raise HTTPException(400, "model_id is empty (set in voice.yaml or profile or request)")

    base = safe_name(inp.save_name or f"{time.strftime('%Y%m%d_%H%M%S')}_{agent_id}")
    base = ensure_wav(base)
    out_rel = f"{agent_id}/{base}"

    payload = {
        "text": inp.text,
        "language": language,
        "speaker": speaker,
        "instruct": instruct,
        "model_id": model_id,
        "save_name": out_rel,
    }

    try:
        r = requests.post(BACKEND, json=payload, timeout=600)
    except Exception as e:
        raise HTTPException(502, f"backend request failed: {e}")

    if r.status_code >= 400:
        try:
            j = r.json()
        except Exception:
            j = {"detail": r.text[:500]}
        raise HTTPException(500, j.get("detail", "backend error"))

    j = r.json()
    saved_path = j.get("saved_path")
    host_root = os.environ.get("TTS_HOST_LOG_DIR")
    host_saved_path = f"{host_root.rstrip('/')}/{out_rel}" if host_root else None


    # meta рядом с wav (в логах)
    try:
        meta_path = (LOG_DIR / out_rel).with_suffix(".json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            yaml.safe_dump({
                "agent_id": agent_id,
                "profile": prof_name,
                "voice_id": voice_id,
                "model_id": model_id,
                "language": language,
                "speaker": speaker,
                "instruct": instruct,
                "text": inp.text,
                "saved_path": saved_path,
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, allow_unicode=True),
            encoding="utf-8"
        )
    except Exception:
        pass

    return {
        "ok": True,
        "agent_id": agent_id,
        "profile": prof_name,
        "voice_id": voice_id,
        "model_id": model_id,
        "language": language,
        "speaker": speaker,
        "instruct": instruct,
        "saved_path": saved_path,
        "rel_path": out_rel,
        "host_saved_path": host_saved_path,

    }
