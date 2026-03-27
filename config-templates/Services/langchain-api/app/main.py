import os
import json
import urllib.error
import urllib.request
from typing import Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

app = FastAPI()

BASE_URL = os.getenv("LC_BASE_URL", "http://ollama:11434/v1").rstrip("/")
API_KEY  = os.getenv("LC_API_KEY", "EMPTY")
MODEL    = os.getenv("LC_MODEL", "qwen3.5:9b")
TIMEOUT  = float(os.getenv("LC_TIMEOUT_S", "60"))
OLLAMA_THINK = os.getenv("LC_OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_NATIVE_CHAT = os.getenv("LC_OLLAMA_NATIVE_CHAT", "true").strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_NATIVE_CHAT_URL = os.getenv("LC_OLLAMA_NATIVE_CHAT_URL", "http://ollama:11434/api/chat").rstrip("/")
OLLAMA_NUM_THREAD = os.getenv("LC_OLLAMA_NUM_THREAD", "").strip()
OLLAMA_NUM_BATCH = os.getenv("LC_OLLAMA_NUM_BATCH", "").strip()
OLLAMA_NUM_CTX = os.getenv("LC_OLLAMA_NUM_CTX", "").strip()
EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "ovms").strip().lower()
OVMS_EMBEDDINGS_URL = os.getenv("OVMS_EMBEDDINGS_URL", "http://ovms:8000/v3/embeddings").rstrip("/")
OVMS_EMBEDDINGS_MODEL = os.getenv("OVMS_EMBEDDINGS_MODEL", "qwen3-embed-0.6b-int8-ov")
OLLAMA_EMBEDDINGS_URL = os.getenv("OLLAMA_EMBEDDINGS_URL", "http://ollama:11434/api/embed").rstrip("/")
OLLAMA_EMBEDDINGS_FALLBACK_URL = os.getenv(
    "OLLAMA_EMBEDDINGS_FALLBACK_URL", "http://ollama:11434/api/embeddings"
).rstrip("/")
OLLAMA_EMBEDDINGS_MODEL = os.getenv("OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text")
OVMS_EMBEDDINGS_API_KEY = os.getenv("OVMS_EMBEDDINGS_API_KEY", "").strip()

class RunReq(BaseModel):
    session_id: str | None = None
    user_text: str
    temperature: float = 0.3
    max_tokens: int = 256

class EmbeddingsReq(BaseModel):
    input: str | list[str]
    model: str | None = None
    encoding_format: str = "float"

def _http_post_json(
    url: str, payload: dict[str, Any], timeout_s: float, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged_headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_error {e.code} from {url}: {body[:300]}") from e
    except Exception as e:
        raise RuntimeError(f"request_error to {url}: {type(e).__name__}: {e}") from e

    try:
        parsed = json.loads(body) if body else {}
    except Exception as e:
        raise RuntimeError(f"invalid_json from {url}: {body[:200]}") from e

    if not isinstance(parsed, dict):
        raise RuntimeError(f"unexpected_json_type from {url}: {type(parsed).__name__}")
    return parsed

def _normalize_input(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        items = [value]
    else:
        items = value
    if not items:
        raise HTTPException(status_code=400, detail="input must not be empty")
    if not all(isinstance(x, str) for x in items):
        raise HTTPException(status_code=400, detail="input must be string or list of strings")
    return items

def _optional_int(raw: str) -> int | None:
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"invalid_integer_env: {raw}")

def _openai_embeddings_response(
    provider: str, model: str, vectors: list[list[float]], usage: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": vec}
            for i, vec in enumerate(vectors)
        ],
        "model": model,
        "provider": provider,
    }
    if usage is not None:
        payload["usage"] = usage
    return payload

def _ovms_embeddings(req: EmbeddingsReq, items: list[str]) -> dict[str, Any]:
    model = req.model or OVMS_EMBEDDINGS_MODEL
    payload: dict[str, Any] = {"model": model, "input": items, "encoding_format": req.encoding_format}
    ovms_headers: dict[str, str] = {}
    if OVMS_EMBEDDINGS_API_KEY:
        ovms_headers["Authorization"] = f"Bearer {OVMS_EMBEDDINGS_API_KEY}"
    data = _http_post_json(OVMS_EMBEDDINGS_URL, payload, TIMEOUT, headers=ovms_headers)

    if "data" not in data:
        raise RuntimeError("unexpected_ovms_response: missing data field")
    data.setdefault("model", model)
    data["provider"] = "ovms"
    return data

def _ollama_embeddings(req: EmbeddingsReq, items: list[str]) -> dict[str, Any]:
    model = req.model or OLLAMA_EMBEDDINGS_MODEL
    payload: dict[str, Any] = {"model": model, "input": items}
    data = _http_post_json(OLLAMA_EMBEDDINGS_URL, payload, TIMEOUT)

    vectors = data.get("embeddings")
    if isinstance(vectors, list) and vectors and all(isinstance(x, list) for x in vectors):
        return _openai_embeddings_response("ollama", model, vectors)

    fallback_vectors: list[list[float]] = []
    for text in items:
        item_data = _http_post_json(
            OLLAMA_EMBEDDINGS_FALLBACK_URL,
            {"model": model, "prompt": text},
            TIMEOUT,
        )
        vec = item_data.get("embedding")
        if not isinstance(vec, list):
            raise RuntimeError("unexpected_ollama_response: missing embedding field")
        fallback_vectors.append(vec)
    return _openai_embeddings_response("ollama", model, fallback_vectors)

def _ollama_chat(req: RunReq) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": MODEL,
        "messages": [{"role": "user", "content": req.user_text}],
        "stream": False,
        "think": OLLAMA_THINK,
        "options": {
            "temperature": float(req.temperature),
            "num_predict": int(req.max_tokens),
        },
    }
    num_thread = _optional_int(OLLAMA_NUM_THREAD)
    num_batch = _optional_int(OLLAMA_NUM_BATCH)
    num_ctx = _optional_int(OLLAMA_NUM_CTX)
    if num_thread is not None:
        payload["options"]["num_thread"] = num_thread
    if num_batch is not None:
        payload["options"]["num_batch"] = num_batch
    if num_ctx is not None:
        payload["options"]["num_ctx"] = num_ctx

    data = _http_post_json(OLLAMA_NATIVE_CHAT_URL, payload, TIMEOUT)
    message = data.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        content = data.get("response") or ""
    if not isinstance(content, str):
        raise RuntimeError("unexpected_ollama_chat_response: missing content")
    return {"ok": True, "backend": "ollama-native", "model": MODEL, "answer": content}

@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "langchain-api",
        "embeddings_provider": EMBEDDINGS_PROVIDER,
        "ovms_auth_enabled": bool(OVMS_EMBEDDINGS_API_KEY),
    }

@app.post("/run")
def run(req: RunReq):
    if OLLAMA_NATIVE_CHAT and ("litellm" in BASE_URL or "ollama" in BASE_URL):
        try:
            return _ollama_chat(req)
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"upstream_ollama_chat_error: {type(e).__name__}: {e}",
            )

    llm_kwargs = {
        "model": MODEL,
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "request_timeout": TIMEOUT,
        "max_retries": 0,
        "temperature": float(req.temperature),
        "max_tokens": int(req.max_tokens),
    }
    if "litellm" in BASE_URL or "ollama" in BASE_URL:
        extra_body: dict[str, Any] = {"think": OLLAMA_THINK}
        ollama_options: dict[str, Any] = {}
        num_thread = _optional_int(OLLAMA_NUM_THREAD)
        num_batch = _optional_int(OLLAMA_NUM_BATCH)
        num_ctx = _optional_int(OLLAMA_NUM_CTX)
        if num_thread is not None:
            ollama_options["num_thread"] = num_thread
        if num_batch is not None:
            ollama_options["num_batch"] = num_batch
        if num_ctx is not None:
            ollama_options["num_ctx"] = num_ctx
        if ollama_options:
            extra_body["options"] = ollama_options
        llm_kwargs["extra_body"] = extra_body

    llm = ChatOpenAI(
        **llm_kwargs,
    )
    try:
        resp = llm.invoke([HumanMessage(content=req.user_text)])
        return {"ok": True, "backend": "langchain", "model": MODEL, "answer": (resp.content or "")}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream_llm_error: {type(e).__name__}: {e}")

@app.post("/embeddings")
def embeddings(req: EmbeddingsReq):
    items = _normalize_input(req.input)
    try:
        if EMBEDDINGS_PROVIDER == "ovms":
            return _ovms_embeddings(req, items)
        if EMBEDDINGS_PROVIDER == "ollama":
            return _ollama_embeddings(req, items)
        raise HTTPException(
            status_code=500,
            detail=f"unsupported_embeddings_provider: {EMBEDDINGS_PROVIDER}",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"upstream_embeddings_error: {type(e).__name__}: {e}",
        )
