from __future__ import annotations

import ctypes
import gc
import json
import math
import os
import re
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator


DEFAULT_INSTRUCTION = (
    "Given a local machine memory search query, retrieve relevant evidence "
    "chunks that answer the query"
)
PROMPT_PREFIX = (
    "<|im_start|>system\n"
    "Judge whether the Document meets the requirements based on the Query and "
    "the Instruct provided. Note that the answer can only be \"yes\" or \"no\"."
    "<|im_end|>\n<|im_start|>user\n"
)
PROMPT_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def env_str(primary: str, fallback: str, default: str) -> str:
    return os.environ.get(primary) or os.environ.get(fallback) or default


def env_int(primary: str, fallback: str, default: int) -> int:
    value = os.environ.get(primary) or os.environ.get(fallback)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{primary} must be an integer") from exc


def env_bool(primary: str, fallback: str, default: bool = False) -> bool:
    value = os.environ.get(primary) or os.environ.get(fallback)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


MODEL_NAME = env_str("AOA_RERANK_MODEL_NAME", "RERANK_MODEL_NAME", "qwen3-reranker-0.6b-int8-ov")
MODEL_DIR = Path(env_str("AOA_RERANK_MODEL_DIR", "RERANK_MODEL_DIR", "/models/qwen3-reranker"))
CACHE_DIR = Path(env_str("AOA_RERANK_CACHE_DIR", "RERANK_CACHE_DIR", "/cache/openvino"))
DEVICE = env_str("AOA_RERANK_DEVICE", "RERANK_DEVICE", "GPU")
MAX_LENGTH = env_int("AOA_RERANK_MAX_LENGTH", "RERANK_MAX_LENGTH", 2048)
BATCH_SIZE = env_int("AOA_RERANK_BATCH_SIZE", "RERANK_BATCH_SIZE", 4)
DEFAULT_TOP_N = env_int("AOA_RERANK_DEFAULT_TOP_N", "RERANK_DEFAULT_TOP_N", 5)
IDLE_UNLOAD_SEC = env_int("AOA_RERANK_IDLE_UNLOAD_SEC", "RERANK_IDLE_UNLOAD_SEC", 900)
IDLE_UNLOAD_CHECK_SEC = env_int("AOA_RERANK_IDLE_UNLOAD_CHECK_SEC", "RERANK_IDLE_UNLOAD_CHECK_SEC", 60)
EXIT_AFTER_IDLE_UNLOAD = env_bool("AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD", "RERANK_EXIT_AFTER_IDLE_UNLOAD", True)
EXIT_AFTER_MEMORY_RELIEF = env_bool(
    "AOA_RERANK_EXIT_AFTER_MEMORY_RELIEF",
    "RERANK_EXIT_AFTER_MEMORY_RELIEF",
    True,
)
RELIEF_RECEIPT_PATH = Path(
    env_str(
        "AOA_RERANK_RELIEF_RECEIPT_PATH",
        "RERANK_RELIEF_RECEIPT_PATH",
        "/state/memory-relief-receipts.json",
    )
)
FAKE_MODE = env_bool("AOA_RERANK_FAKE", "RERANK_FAKE", False)


def now_ms() -> float:
    return time.perf_counter() * 1000.0


def trim_process_heap() -> bool:
    try:
        libc = ctypes.CDLL("libc.so.6")
        return bool(libc.malloc_trim(0))
    except Exception:
        return False


def format_pair(instruction: str | None, query: str, document: str) -> str:
    return (
        f"<Instruct>: {instruction or DEFAULT_INSTRUCTION}\n"
        f"<Query>: {query}\n"
        f"<Document>: {document}"
    )


def lexical_score(query: str, document: str) -> float:
    query_tokens = set(re.findall(r"[\w.-]+", query.lower()))
    if not query_tokens:
        return 0.0
    document_tokens = set(re.findall(r"[\w.-]+", document.lower()))
    overlap = len(query_tokens & document_tokens)
    return min(1.0, overlap / math.sqrt(len(query_tokens) * max(len(document_tokens), 1)))


class RerankRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model: str | None = None
    query: str = Field(min_length=1)
    documents: list[str | dict[str, Any]]
    top_n: int | None = Field(default=None, ge=1)
    return_documents: bool = True
    instruction: str | None = None

    @model_validator(mode="after")
    def validate_documents(self) -> "RerankRequest":
        if not self.documents:
            raise ValueError("documents must not be empty")
        return self


class MemoryReliefRequest(BaseModel):
    action: str
    action_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    owner: str
    workload_id: str


@dataclass(frozen=True)
class DocumentEnvelope:
    index: int
    text: str
    original: str | dict[str, Any]


def document_text(value: str | dict[str, Any]) -> str:
    if isinstance(value, str):
        return value
    parts = []
    for key in ("title", "text", "snippet", "body", "body_preview", "content"):
        item = value.get(key)
        if isinstance(item, str) and item.strip():
            parts.append(item.strip())
    if parts:
        return "\n".join(parts)
    return str(value)


class Qwen3OpenVINOReranker:
    def __init__(self, model_dir: Path, device: str, cache_dir: Path, max_length: int, batch_size: int) -> None:
        self.model_dir = model_dir
        self.device = device
        self.cache_dir = cache_dir
        self.max_length = max_length
        self.batch_size = max(1, batch_size)
        self.load_ms = 0.0

    def load(self) -> None:
        started = now_ms()
        import torch
        from optimum.intel.openvino import OVModelForCausalLM
        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_dir,
            padding_side="left",
            local_files_only=True,
            fix_mistral_regex=True,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = OVModelForCausalLM.from_pretrained(
            self.model_dir,
            device=self.device,
            ov_config={"CACHE_DIR": str(self.cache_dir)},
            use_cache=False,
            export=False,
            local_files_only=True,
        )
        self.model.eval()
        self.torch = torch
        self.token_false_id = self.tokenizer.convert_tokens_to_ids("no")
        self.token_true_id = self.tokenizer.convert_tokens_to_ids("yes")
        if self.token_false_id is None or self.token_true_id is None:
            raise RuntimeError("tokenizer must resolve yes/no token ids")
        self.prefix_tokens = self.tokenizer.encode(PROMPT_PREFIX, add_special_tokens=False)
        self.suffix_tokens = self.tokenizer.encode(PROMPT_SUFFIX, add_special_tokens=False)
        self.load_ms = round(now_ms() - started, 3)

    def _process(self, pairs: list[str]) -> dict[str, Any]:
        budget = max(16, self.max_length - len(self.prefix_tokens) - len(self.suffix_tokens))
        inputs = self.tokenizer(
            pairs,
            padding=False,
            truncation="longest_first",
            return_attention_mask=False,
            max_length=budget,
        )
        for index, item in enumerate(inputs["input_ids"]):
            inputs["input_ids"][index] = self.prefix_tokens + item + self.suffix_tokens
        return self.tokenizer.pad(inputs, padding=True, return_tensors="pt", max_length=self.max_length)

    def score(self, query: str, documents: list[str], instruction: str | None) -> dict[str, Any]:
        scores: list[float] = []
        raw_scores: list[float] = []
        tokenize_ms = 0.0
        infer_ms = 0.0
        for offset in range(0, len(documents), self.batch_size):
            batch = documents[offset : offset + self.batch_size]
            pairs = [format_pair(instruction, query, doc) for doc in batch]
            tokenize_started = now_ms()
            inputs = self._process(pairs)
            tokenize_ms += now_ms() - tokenize_started
            infer_started = now_ms()
            with self.torch.no_grad():
                logits = self.model(**inputs).logits[:, -1, :]
                true_vector = logits[:, self.token_true_id]
                false_vector = logits[:, self.token_false_id]
                two = self.torch.stack([false_vector, true_vector], dim=1)
                log_probs = self.torch.nn.functional.log_softmax(two, dim=1)
                batch_scores = log_probs[:, 1].exp().detach().cpu().tolist()
                raw = (true_vector - false_vector).detach().cpu().tolist()
            infer_ms += now_ms() - infer_started
            scores.extend(float(item) for item in batch_scores)
            raw_scores.extend(float(item) for item in raw)
        return {
            "scores": scores,
            "raw_logit_diff": raw_scores,
            "tokenize_ms": round(tokenize_ms, 3),
            "infer_ms": round(infer_ms, 3),
        }


class LazyScorer:
    def __init__(self, relief_receipt_path: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._scorer: Qwen3OpenVINOReranker | None = None
        self._loaded_at_epoch: float | None = None
        self._last_used_epoch: float | None = None
        self._last_used_monotonic: float | None = None
        self._last_unload_epoch: float | None = None
        self._last_unload_reason: str | None = None
        self._active_requests = 0
        self._draining = False
        self._relief_receipt_path = relief_receipt_path
        self._relief_receipt_error: str | None = None
        self._relief_results = self._load_relief_results()

    def _load_relief_results(self) -> dict[str, dict[str, Any]]:
        if self._relief_receipt_path is None or not self._relief_receipt_path.exists():
            return {}
        try:
            payload = json.loads(self._relief_receipt_path.read_text(encoding="utf-8"))
            results = payload.get("results") if isinstance(payload, dict) else None
            if not isinstance(results, dict):
                raise ValueError("results must be an object")
            valid = {
                action_id: dict(result)
                for action_id, result in results.items()
                if re.fullmatch(r"[a-f0-9]{32}", action_id) and isinstance(result, dict)
            }
            if len(valid) != len(results):
                raise ValueError("receipt contains malformed action results")
            return dict(list(valid.items())[-32:])
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._relief_receipt_error = f"{type(exc).__name__}: {exc}"
            return {}

    def _persist_relief_results(self, results: dict[str, dict[str, Any]]) -> None:
        if self._relief_receipt_path is None:
            return
        path = self._relief_receipt_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        payload = json.dumps(
            {"schema": "abyss_rerank_memory_relief_receipts_v1", "results": results},
            sort_keys=False,
            separators=(",", ":"),
        ).encode("utf-8")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    @property
    def loaded(self) -> bool:
        return self._scorer is not None

    @property
    def load_ms(self) -> float | None:
        if self._scorer is None:
            return None
        return self._scorer.load_ms

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
    def idle_for_sec(self) -> float | None:
        if self._scorer is None or self._last_used_monotonic is None:
            return None
        return round(max(0.0, time.monotonic() - self._last_used_monotonic), 3)

    @property
    def active_requests(self) -> int:
        return self._active_requests

    @property
    def draining(self) -> bool:
        return self._draining

    def begin_request(self) -> bool:
        with self._lock:
            if self._draining:
                return False
            self._active_requests += 1
            return True

    def end_request(self) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def _mark_used(self) -> None:
        self._last_used_epoch = time.time()
        self._last_used_monotonic = time.monotonic()

    def unload(self, reason: str, *, exit_process: bool = False) -> dict[str, Any]:
        with self._lock:
            was_loaded = self._scorer is not None
            load_ms = self.load_ms
            self._scorer = None
            self._loaded_at_epoch = None
            self._last_unload_epoch = time.time()
            self._last_unload_reason = reason
        if was_loaded:
            gc.collect()
            heap_trimmed = trim_process_heap()
        else:
            heap_trimmed = False
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

    def owner_memory_relief(
        self,
        req: MemoryReliefRequest,
        *,
        exit_process: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if req.action_id in self._relief_results:
                return dict(self._relief_results[req.action_id])
            if self._relief_receipt_error is not None:
                return {
                    "ok": False,
                    "action_id": req.action_id,
                    "reason": "receipt_store_unavailable",
                    "loaded": self._scorer is not None,
                    "owner_gate": {
                        "active_requests_at_action": self._active_requests,
                        "data_risk": False,
                    },
                }
            if req.action != "relieve_memory" or req.owner != "abyss-stack" or req.workload_id != "rerank-api:qwen3-0.6b":
                return {
                    "ok": False,
                    "action_id": req.action_id,
                    "reason": "owner_contract_mismatch",
                    "loaded": self._scorer is not None,
                    "owner_gate": {
                        "active_requests_at_action": self._active_requests,
                        "data_risk": False,
                    },
                }
            if self._active_requests != 0:
                return {
                    "ok": False,
                    "action_id": req.action_id,
                    "reason": "active_requests",
                    "loaded": self._scorer is not None,
                    "owner_gate": {
                        "active_requests_at_action": self._active_requests,
                        "data_risk": False,
                    },
                }
            was_loaded = self._scorer is not None
            load_ms = self.load_ms
            should_exit = exit_process and was_loaded
            result = {
                "ok": True,
                "action_id": req.action_id,
                "unloaded": was_loaded,
                "reason": "owner_memory_relief",
                "load_ms": load_ms,
                "loaded": False,
                "owner_gate": {
                    "active_requests_at_action": 0,
                    "data_risk": False,
                },
                "resume": "lazy_load_on_next_rerank",
                "exit_process": should_exit,
            }
            committed_results = dict(self._relief_results)
            committed_results[req.action_id] = dict(result)
            while len(committed_results) > 32:
                committed_results.pop(next(iter(committed_results)))
            try:
                self._persist_relief_results(committed_results)
            except OSError:
                return {
                    "ok": False,
                    "action_id": req.action_id,
                    "reason": "receipt_store_unavailable",
                    "loaded": was_loaded,
                    "owner_gate": {
                        "active_requests_at_action": 0,
                        "data_risk": False,
                    },
                }
            self._relief_results = committed_results
            self._scorer = None
            self._loaded_at_epoch = None
            self._last_unload_epoch = time.time()
            self._last_unload_reason = "owner_memory_relief"
            if was_loaded:
                gc.collect()
                trim_process_heap()
            if should_exit:
                self._draining = True
                threading.Timer(1.0, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
            return result

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
            if self._scorer is None or self._last_used_monotonic is None:
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

    def score(self, query: str, documents: list[str], instruction: str | None) -> dict[str, Any]:
        if FAKE_MODE:
            self._mark_used()
            return {
                "scores": [lexical_score(query, document) for document in documents],
                "raw_logit_diff": [],
                "tokenize_ms": 0.0,
                "infer_ms": 0.0,
            }
        if not MODEL_DIR.is_dir():
            raise RuntimeError(f"model directory is missing: {MODEL_DIR}")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if self._scorer is None:
                scorer = Qwen3OpenVINOReranker(MODEL_DIR, DEVICE, CACHE_DIR, MAX_LENGTH, BATCH_SIZE)
                scorer.load()
                self._scorer = scorer
                self._loaded_at_epoch = time.time()
            self._mark_used()
            return self._scorer.score(query, documents, instruction)


scorer = LazyScorer(None if FAKE_MODE else RELIEF_RECEIPT_PATH)
app = FastAPI(title="Abyss Stack Rerank API", version="0.1.0")


def idle_unload_loop() -> None:
    interval = max(5, IDLE_UNLOAD_CHECK_SEC)
    while True:
        time.sleep(interval)
        scorer.unload_if_idle(IDLE_UNLOAD_SEC)


if IDLE_UNLOAD_SEC > 0 and not FAKE_MODE:
    threading.Thread(target=idle_unload_loop, name="rerank-idle-unloader", daemon=True).start()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "rerank-api",
        "model": MODEL_NAME,
        "backend": "openvino_qwen3_reranker",
        "device": DEVICE,
        "model_dir": str(MODEL_DIR),
        "model_dir_exists": MODEL_DIR.is_dir(),
        "cache_dir": str(CACHE_DIR),
        "cache_dir_exists": CACHE_DIR.is_dir(),
        "max_length": MAX_LENGTH,
        "batch_size": BATCH_SIZE,
        "loaded": scorer.loaded,
        "load_ms": scorer.load_ms,
        "loaded_at_epoch": scorer.loaded_at_epoch,
        "last_used_epoch": scorer.last_used_epoch,
        "idle_for_sec": scorer.idle_for_sec,
        "idle_unload_sec": IDLE_UNLOAD_SEC,
        "idle_unload_check_sec": IDLE_UNLOAD_CHECK_SEC,
        "exit_after_idle_unload": EXIT_AFTER_IDLE_UNLOAD,
        "active_requests": scorer.active_requests,
        "draining": scorer.draining,
        "last_unload_epoch": scorer.last_unload_epoch,
        "last_unload_reason": scorer.last_unload_reason,
        "fake_mode": FAKE_MODE,
    }


@app.post("/admin/unload")
def unload(exit_process: bool = False) -> dict[str, Any]:
    return scorer.unload("admin_request", exit_process=exit_process)


@app.post("/admin/memory-relief")
def memory_relief(req: MemoryReliefRequest) -> dict[str, Any]:
    return scorer.owner_memory_relief(req, exit_process=EXIT_AFTER_MEMORY_RELIEF)


@app.post("/v3/rerank")
def rerank(req: RerankRequest) -> dict[str, Any]:
    if not scorer.begin_request():
        raise HTTPException(status_code=503, detail="reranker is draining for owner memory relief")
    started = now_ms()
    try:
        envelopes = [
            DocumentEnvelope(index=index, text=document_text(document), original=document)
            for index, document in enumerate(req.documents)
        ]
        try:
            result = scorer.score(req.query, [item.text for item in envelopes], req.instruction)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"rerank failed: {type(exc).__name__}: {exc}") from exc

        raw_scores = result.get("raw_logit_diff") or []
        ranked = []
        for index, envelope in enumerate(envelopes):
            item: dict[str, Any] = {
                "index": envelope.index,
                "relevance_score": result["scores"][index],
            }
            if index < len(raw_scores):
                item["raw_logit_diff"] = raw_scores[index]
            if req.return_documents:
                item["document"] = envelope.original
            ranked.append(item)
        ranked.sort(key=lambda item: item["relevance_score"], reverse=True)
        top_n = req.top_n or DEFAULT_TOP_N
        return {
            "id": f"rerank-{time.time_ns()}",
            "model": req.model or MODEL_NAME,
            "results": ranked[:top_n],
            "meta": {
                "backend": "openvino_qwen3_reranker",
                "device": DEVICE,
                "documents": len(envelopes),
                "returned": min(top_n, len(ranked)),
                "loaded": scorer.loaded,
                "load_ms": scorer.load_ms,
                "tokenize_ms": result.get("tokenize_ms"),
                "infer_ms": result.get("infer_ms"),
                "total_ms": round(now_ms() - started, 3),
                "active_requests": scorer.active_requests,
                "fake_mode": FAKE_MODE,
            },
        }
    finally:
        scorer.end_request()


@app.post("/rerank")
def rerank_alias(req: RerankRequest) -> dict[str, Any]:
    return rerank(req)
