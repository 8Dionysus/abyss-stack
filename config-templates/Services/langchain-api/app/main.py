import json
import hashlib
import http.client
import os
import re
import secrets
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator

try:
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI
except ImportError:
    HumanMessage = None
    ChatOpenAI = None

app = FastAPI()

THINK_TAG_PREFIX_RE = re.compile(r"^\s*<think>.*?</think>\s*", re.DOTALL)
LITERAL_REPLY_PROMPT_RE = re.compile(r"^Reply exactly with:\s*(.+?)\s*$", re.DOTALL)

BASE_URL = os.getenv(
    "LC_BASE_URL",
    os.getenv("AOA_RUNTIME_CHAT_BASE_URL", "http://llama-cpp:8080/v1"),
).rstrip("/")
API_KEY = os.getenv("LC_API_KEY", os.getenv("AOA_RUNTIME_CHAT_API_KEY", "EMPTY"))
MODEL = os.getenv(
    "LC_MODEL",
    os.getenv(
        "AOA_RUNTIME_CHAT_MODEL",
        os.getenv("AOA_LLAMACPP_MODEL_ALIAS", "qwen3.5:9b"),
    ),
)
TIMEOUT = float(os.getenv("LC_TIMEOUT_S", "60"))
OLLAMA_THINK = os.getenv("LC_OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_NATIVE_CHAT = os.getenv("LC_OLLAMA_NATIVE_CHAT", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
OPENAI_CHAT_TEMPLATE_ENABLE_THINKING_RAW = os.getenv(
    "LC_OPENAI_CHAT_TEMPLATE_ENABLE_THINKING",
    "",
).strip().lower()
OPENAI_LITERAL_COMPLETIONS = os.getenv(
    "LC_OPENAI_LITERAL_COMPLETIONS",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
OLLAMA_NATIVE_CHAT_URL = os.getenv(
    "LC_OLLAMA_NATIVE_CHAT_URL",
    "http://ollama:11434/api/chat",
).rstrip("/")
OLLAMA_NUM_THREAD = os.getenv("LC_OLLAMA_NUM_THREAD", "").strip()
OLLAMA_NUM_BATCH = os.getenv("LC_OLLAMA_NUM_BATCH", "").strip()
OLLAMA_NUM_CTX = os.getenv("LC_OLLAMA_NUM_CTX", "").strip()
EMBEDDINGS_PROVIDER = os.getenv("EMBEDDINGS_PROVIDER", "disabled").strip().lower()
OVMS_EMBEDDINGS_URL = os.getenv("OVMS_EMBEDDINGS_URL", "http://ovms:8000/v3/embeddings").rstrip("/")
OVMS_EMBEDDINGS_UNIX_SOCKET = os.getenv("OVMS_EMBEDDINGS_UNIX_SOCKET", "").strip()
OVMS_EMBEDDINGS_MODEL = os.getenv("OVMS_EMBEDDINGS_MODEL", "qwen3-embed-0.6b-int8-ov")
OVMS_EMBEDDINGS_TIMEOUT = float(os.getenv("OVMS_EMBEDDINGS_TIMEOUT_S", "180"))
OLLAMA_EMBEDDINGS_URL = os.getenv("OLLAMA_EMBEDDINGS_URL", "http://ollama:11434/api/embed").rstrip("/")
OLLAMA_EMBEDDINGS_FALLBACK_URL = os.getenv(
    "OLLAMA_EMBEDDINGS_FALLBACK_URL",
    "http://ollama:11434/api/embeddings",
).rstrip("/")
OLLAMA_EMBEDDINGS_MODEL = os.getenv("OLLAMA_EMBEDDINGS_MODEL", "nomic-embed-text")


def _secret_from_file_or_env(file_env: str, value_env: str) -> str:
    secret_path = os.getenv(file_env, "").strip()
    if secret_path:
        path = Path(secret_path)
        try:
            value = path.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, IndexError) as exc:
            raise RuntimeError(f"configured_secret_file_unreadable: {file_env}") from exc
        if not value:
            raise RuntimeError(f"configured_secret_file_empty: {file_env}")
        return value
    return os.getenv(value_env, "").strip()


OVMS_EMBEDDINGS_API_KEY = _secret_from_file_or_env(
    "OVMS_EMBEDDINGS_API_KEY_FILE",
    "OVMS_EMBEDDINGS_API_KEY",
)
FEDERATED_RUN_ENABLED = os.getenv("AOA_FEDERATED_RUN_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
ROUTE_API_BASE_URL = os.getenv("AOA_ROUTE_API_BASE_URL", "http://route-api:5402").rstrip("/")
RETURN_POLICY_PATH = Path(os.getenv("AOA_RETURN_POLICY_PATH", "/app/config/return-policy.yaml"))
LANGGRAPH_INVENTORY_ROOT = Path(
    os.getenv("AOA_LANGGRAPH_INVENTORY_ROOT", "/app/logs/langgraph-inventory")
)
LANGGRAPH_INVENTORY_LIMIT = max(1, int(os.getenv("AOA_LANGGRAPH_INVENTORY_LIMIT", "50")))
LANGGRAPH_INVENTORY_OTLP_ENABLED = os.getenv(
    "AOA_LANGGRAPH_INVENTORY_OTLP_ENABLED",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}
LANGGRAPH_INVENTORY_OTLP_URL = os.getenv(
    "AOA_LANGGRAPH_INVENTORY_OTLP_URL",
    os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://alloy:4318/v1/traces"),
).strip()
LANGGRAPH_INVENTORY_OTLP_TIMEOUT = float(os.getenv("AOA_LANGGRAPH_INVENTORY_OTLP_TIMEOUT_S", "1.5"))

PROFILE_CLASS = Literal["spark", "workhorse", "deep", "archive"]
MEMO_FAMILY = Literal["router", "object"]
MEMO_MODE = Literal["working", "semantic", "lineage"]
MEMO_READ_PATH = Literal["inspect_only", "inspect_then_expand", "inspect_capsule_then_expand"]
KAG_QUERY_MODE = Literal["local_search", "global_search", "drift_search"]
KAG_REPO = Literal["Tree-of-Sophia", "aoa-techniques"]

PLAYBOOK_MEMO_KEYS = (
    "memo_recall_modes",
    "memo_scope_default",
    "memo_scope_ceiling",
    "memo_read_path",
    "memo_checkpoint_posture",
    "memo_source_route_policy",
)
PLAYBOOK_SELECT_KEYS = (
    "scenario",
    "trigger",
    "evaluation_posture",
    "memory_posture",
    "fallback_mode",
    "return_reentry_mode",
    "eval_anchor",
    "required_skill",
)
SUMMARY_KEYS = (
    "id",
    "kind",
    "name",
    "title",
    "summary",
    "description",
    "temperature",
    "temperature_band",
    "trust_posture",
    "lifecycle",
    "current_recall",
    "status",
    "source_route",
    "source_route_required",
    "strongest_next_source_hint",
    "stronger_source_route",
    "salience",
    "priority",
)


def _optional_env_bool(raw: str) -> bool | None:
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


OPENAI_CHAT_TEMPLATE_ENABLE_THINKING = _optional_env_bool(
    OPENAI_CHAT_TEMPLATE_ENABLE_THINKING_RAW
)


class RouteAPIHTTPError(RuntimeError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class RouteAPIUnavailableError(RuntimeError):
    pass


class RunReq(BaseModel):
    session_id: str | None = None
    user_text: str
    temperature: float = 0.3
    max_tokens: int = 256


class EmbeddingsReq(BaseModel):
    input: str | list[str]
    model: str | None = None
    encoding_format: str = "float"


class LangGraphSmokeReq(BaseModel):
    session_id: str | None = None
    note: str = "synthetic langchain-api inventory smoke"


class PlaybookSelectReq(BaseModel):
    scenario: str | None = None
    trigger: str | None = None
    evaluation_posture: str | None = None
    memory_posture: str | None = None
    fallback_mode: str | None = None
    return_reentry_mode: str | None = None
    eval_anchor: str | None = None
    required_skill: str | None = None

    @model_validator(mode="after")
    def validate_non_empty(self) -> "PlaybookSelectReq":
        if not any(getattr(self, key) is not None for key in PLAYBOOK_SELECT_KEYS):
            raise ValueError("playbook_select requires at least one filter field")
        return self


class MemoSelector(BaseModel):
    family: MEMO_FAMILY
    mode: MEMO_MODE
    id: str | None = None
    section_id: str | None = None
    expand: bool = False
    return_ready: bool = False

    @model_validator(mode="after")
    def validate_shape(self) -> "MemoSelector":
        if self.family == "router" and self.mode == "working":
            raise ValueError("router family supports only semantic or lineage modes")
        if self.return_ready and not (self.family == "object" and self.mode == "working"):
            raise ValueError("return_ready requires family=object and mode=working")
        if self.section_id is not None and self.id is None:
            raise ValueError("section_id requires an explicit memo id")
        return self


class KagSelector(BaseModel):
    inspect_id: str | None = None
    query_mode: KAG_QUERY_MODE | None = None
    regrounding_mode: str | None = None
    repo: KAG_REPO | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "KagSelector":
        selector_count = sum(
            value is not None
            for value in (
                self.inspect_id,
                self.query_mode,
                self.regrounding_mode,
                self.repo,
            )
        )
        if selector_count != 1:
            raise ValueError("kag requires exactly one selector")
        return self


class FederatedRunReq(RunReq):
    playbook_id: str | None = None
    playbook_select: PlaybookSelectReq | None = None
    memo: MemoSelector | None = None
    kag: KagSelector | None = None
    profile_class: PROFILE_CLASS | None = None

    @model_validator(mode="after")
    def validate_selector_shape(self) -> "FederatedRunReq":
        if self.playbook_id is not None and self.playbook_select is not None:
            raise ValueError("use playbook_id or playbook_select, not both")
        if self.playbook_id is None and self.playbook_select is None and self.memo is None and self.kag is None:
            raise ValueError("run/federated requires at least one advisory selector")
        return self


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    timeout_s: float,
    headers: dict[str, str] | None = None,
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
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"http_error {exc.code} from {url}: {body[:300]}") from exc
    except Exception as exc:
        raise RuntimeError(f"request_error to {url}: {type(exc).__name__}: {exc}") from exc

    try:
        parsed = json.loads(body) if body else {}
    except Exception as exc:
        raise RuntimeError(f"invalid_json from {url}: {body[:200]}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(f"unexpected_json_type from {url}: {type(parsed).__name__}")
    return parsed


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        connection.connect(self.socket_path)
        self.sock = connection


def _unix_post_json(
    socket_path: str,
    request_path: str,
    payload: dict[str, Any],
    timeout_s: float,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    merged_headers = {"Content-Type": "application/json"}
    if headers:
        merged_headers.update(headers)
    body = json.dumps(payload).encode("utf-8")
    connection = _UnixHTTPConnection(socket_path, timeout_s)
    try:
        connection.request("POST", request_path, body=body, headers=merged_headers)
        response = connection.getresponse()
        response_body = response.read().decode("utf-8", errors="ignore")
        if response.status >= 400:
            raise RuntimeError(
                f"http_error {response.status} from unix:{request_path}: {response_body[:300]}"
            )
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(
            f"request_error to unix:{request_path}: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        connection.close()

    try:
        parsed = json.loads(response_body) if response_body else {}
    except Exception as exc:
        raise RuntimeError(
            f"invalid_json from unix:{request_path}: {response_body[:200]}"
        ) from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"unexpected_json_type from unix:{request_path}: {type(parsed).__name__}"
        )
    return parsed


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _bounded_string(value: Any, limit: int = 240) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _safe_inventory_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return safe[:96] or secrets.token_hex(8)


def _runtime_trace_context(req: RunReq | LangGraphSmokeReq, run_kind: str) -> dict[str, Any]:
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)
    session_id = getattr(req, "session_id", None)
    thread_seed = session_id or trace_id
    thread_id = f"thread.{_sha256_text(thread_seed)[:16]}"
    checkpoint_id = f"checkpoint.{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.{span_id}"
    started_ns = time.time_ns()
    return {
        "run_kind": run_kind,
        "trace_id": trace_id,
        "span_id": span_id,
        "traceparent": f"00-{trace_id}-{span_id}-01",
        "thread_id": _safe_inventory_id(thread_id),
        "checkpoint_id": _safe_inventory_id(checkpoint_id),
        "started_ns": started_ns,
        "started_at": _utc_now(),
        "session_present": session_id is not None,
        "session_id_sha256": _sha256_text(session_id) if isinstance(session_id, str) else None,
    }


def _text_fingerprint(value: str | None) -> dict[str, Any]:
    if value is None:
        return {"present": False, "length": 0, "sha256": None}
    return {
        "present": True,
        "length": len(value),
        "sha256": _sha256_text(value),
    }


def _record_path(root: Path, *parts: str) -> Path:
    path = root
    for part in parts:
        path /= _safe_inventory_id(part)
    return path


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl_tail(path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    except Exception:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _inventory_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": record.get("schema"),
        "created_at": record.get("created_at"),
        "run_kind": record.get("run_kind"),
        "status": record.get("status"),
        "thread_id": record.get("thread_id"),
        "checkpoint_id": record.get("checkpoint_id"),
        "trace_id": record.get("trace_id"),
        "span_id": record.get("span_id"),
        "traceparent": record.get("traceparent"),
        "backend": record.get("backend"),
        "model": record.get("model"),
        "input": record.get("input"),
        "output": record.get("output"),
        "error": record.get("error"),
        "storage": record.get("storage"),
        "observability": record.get("observability"),
    }


def _otlp_attributes(record: dict[str, Any]) -> list[dict[str, Any]]:
    attrs: list[dict[str, Any]] = []

    def add_string(key: str, value: Any) -> None:
        if value is not None:
            attrs.append({"key": key, "value": {"stringValue": str(value)}})

    def add_bool(key: str, value: Any) -> None:
        if value is not None:
            attrs.append({"key": key, "value": {"boolValue": bool(value)}})

    add_string("service.name", "abyss-stack.langchain-api")
    add_string("abyss.run_kind", record.get("run_kind"))
    add_string("abyss.thread_id", record.get("thread_id"))
    add_string("abyss.checkpoint_id", record.get("checkpoint_id"))
    add_string("abyss.status", record.get("status"))
    add_string("abyss.backend", record.get("backend"))
    add_string("abyss.model", record.get("model"))
    add_bool("abyss.session_present", record.get("session_present"))
    add_bool("abyss.raw_payload_stored", False)
    return attrs


def _send_otlp_trace(record: dict[str, Any]) -> dict[str, Any]:
    if not LANGGRAPH_INVENTORY_OTLP_ENABLED:
        return {"enabled": False, "ok": False, "reason": "disabled"}
    if not LANGGRAPH_INVENTORY_OTLP_URL:
        return {"enabled": True, "ok": False, "reason": "missing_endpoint"}

    payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "abyss-stack.langchain-api"}},
                        {"key": "abyss.component", "value": {"stringValue": "langchain-runtime-inventory"}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "abyss-stack.langchain-api.inventory"},
                        "spans": [
                            {
                                "traceId": record["trace_id"],
                                "spanId": record["span_id"],
                                "name": f"langchain-api {record['run_kind']}",
                                "kind": 2,
                                "startTimeUnixNano": str(record["started_ns"]),
                                "endTimeUnixNano": str(record["ended_ns"]),
                                "attributes": _otlp_attributes(record),
                                "status": {
                                    "code": 1 if record.get("status") == "ok" else 2,
                                    "message": _bounded_string(record.get("error", {}).get("detail", ""), 120)
                                    if isinstance(record.get("error"), dict)
                                    else "",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }
    try:
        _http_post_json(LANGGRAPH_INVENTORY_OTLP_URL, payload, LANGGRAPH_INVENTORY_OTLP_TIMEOUT)
    except Exception as exc:
        return {
            "enabled": True,
            "ok": False,
            "endpoint": LANGGRAPH_INVENTORY_OTLP_URL,
            "error": f"{type(exc).__name__}: {_bounded_string(exc, 180)}",
        }
    return {"enabled": True, "ok": True, "endpoint": LANGGRAPH_INVENTORY_OTLP_URL}


def _store_inventory_record(record: dict[str, Any]) -> dict[str, Any]:
    root = LANGGRAPH_INVENTORY_ROOT
    date_id = time.strftime("%Y%m%d", time.gmtime())
    paths = {
        "latest": root / "latest.json",
        "records": root / "records" / f"{date_id}.jsonl",
        "thread": _record_path(root, "threads", f"{record['thread_id']}.jsonl"),
        "checkpoint": _record_path(root, "checkpoints", f"{record['checkpoint_id']}.json"),
        "trace": _record_path(root, "traces", f"{record['trace_id']}.json"),
    }
    try:
        _append_jsonl(paths["records"], record)
        _append_jsonl(paths["thread"], record)
        _write_json_atomic(paths["checkpoint"], record)
        _write_json_atomic(paths["trace"], record)
        _write_json_atomic(paths["latest"], record)
    except Exception as exc:
        return {
            "ok": False,
            "root": str(root),
            "error": f"{type(exc).__name__}: {_bounded_string(exc, 180)}",
        }
    return {
        "ok": True,
        "root": str(root),
        "paths": {key: str(value) for key, value in paths.items()},
    }


def _emit_inventory_log(record: dict[str, Any]) -> None:
    event = {
        "event": "langchain_runtime_trace",
        "service": "langchain-api",
        "created_at": record.get("created_at"),
        "run_kind": record.get("run_kind"),
        "status": record.get("status"),
        "thread_id": record.get("thread_id"),
        "checkpoint_id": record.get("checkpoint_id"),
        "trace_id": record.get("trace_id"),
        "span_id": record.get("span_id"),
        "traceparent": record.get("traceparent"),
        "raw_payload_stored": False,
    }
    print(json.dumps(event, ensure_ascii=True, sort_keys=True), flush=True)


def _record_runtime_trace(
    trace_context: dict[str, Any],
    req: RunReq | FederatedRunReq | LangGraphSmokeReq,
    *,
    status: Literal["ok", "error"],
    response: dict[str, Any] | None = None,
    advisory_trace: dict[str, Any] | None = None,
    error: Exception | HTTPException | None = None,
) -> dict[str, Any]:
    answer = response.get("answer") if isinstance(response, dict) and isinstance(response.get("answer"), str) else None
    input_text = getattr(req, "user_text", None)
    if input_text is None:
        input_text = getattr(req, "note", None)
    ended_ns = time.time_ns()
    record: dict[str, Any] = {
        "schema": "abyss_stack_langchain_runtime_trace_v1",
        "service": "langchain-api",
        "created_at": _utc_now(),
        "started_at": trace_context["started_at"],
        "run_kind": trace_context["run_kind"],
        "status": status,
        "thread_id": trace_context["thread_id"],
        "checkpoint_id": trace_context["checkpoint_id"],
        "trace_id": trace_context["trace_id"],
        "span_id": trace_context["span_id"],
        "traceparent": trace_context["traceparent"],
        "started_ns": trace_context["started_ns"],
        "ended_ns": ended_ns,
        "duration_ms": round((ended_ns - int(trace_context["started_ns"])) / 1_000_000.0, 3),
        "session_present": trace_context["session_present"],
        "session_id_sha256": trace_context["session_id_sha256"],
        "backend": response.get("backend") if isinstance(response, dict) else None,
        "model": response.get("model") if isinstance(response, dict) else MODEL,
        "input": _text_fingerprint(input_text if isinstance(input_text, str) else None),
        "output": _text_fingerprint(answer),
        "settings": {
            "temperature": getattr(req, "temperature", None),
            "max_tokens": getattr(req, "max_tokens", None),
        },
        "federated": {
            "request": isinstance(req, FederatedRunReq),
            "advisory_trace_keys": sorted(advisory_trace.keys()) if isinstance(advisory_trace, dict) else [],
        },
        "redaction": {
            "raw_prompt_stored": False,
            "raw_answer_stored": False,
            "raw_advisory_payload_stored": False,
            "stores_hashes_and_lengths": True,
        },
    }
    if isinstance(req, FederatedRunReq):
        record["federated"].update(
            {
                "profile_class": _effective_profile_class(req.profile_class),
                "playbook_requested": req.playbook_id is not None or req.playbook_select is not None,
                "memo_requested": req.memo is not None,
                "kag_requested": req.kag is not None,
            }
        )
    if error is not None:
        status_code = getattr(error, "status_code", None)
        detail = getattr(error, "detail", None)
        record["error"] = {
            "type": type(error).__name__,
            "status_code": status_code,
            "detail": _bounded_string(detail if detail is not None else error),
        }

    record["observability"] = {
        "trace_backend": "tempo",
        "otlp": _send_otlp_trace(record),
        "loki_trace_correlation": "trace_id and traceparent are emitted as log fields, not high-cardinality labels",
    }
    record["storage"] = _store_inventory_record(record)
    try:
        _emit_inventory_log(record)
    except Exception:
        pass
    return _inventory_summary(record)


def _latest_thread_summaries(limit: int) -> list[dict[str, Any]]:
    root = LANGGRAPH_INVENTORY_ROOT / "threads"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("thread.*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True):
        tail = _read_jsonl_tail(path, 1)
        if tail:
            rows.append(_inventory_summary(tail[-1]))
        if len(rows) >= limit:
            break
    return rows


def _latest_trace_summaries(limit: int) -> list[dict[str, Any]]:
    root = LANGGRAPH_INVENTORY_ROOT / "traces"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = _read_json_file(path)
        if payload is not None:
            rows.append(_inventory_summary(payload))
        if len(rows) >= limit:
            break
    return rows


def _http_auth_headers() -> dict[str, str] | None:
    if not API_KEY:
        return None
    return {"Authorization": f"Bearer {API_KEY}"}


def _llamacpp_completion_url() -> str:
    if BASE_URL.endswith("/v1"):
        return f"{BASE_URL[:-3]}/completion"
    return ""


def _route_api_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{ROUTE_API_BASE_URL}{path}"
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        detail = _http_error_detail(exc)
        raise RouteAPIHTTPError(exc.code, detail) from exc
    except Exception as exc:
        raise RouteAPIUnavailableError(
            f"route-api request failed for {path}: {type(exc).__name__}: {exc}"
        ) from exc

    try:
        parsed = json.loads(body) if body else {}
    except Exception as exc:
        raise RouteAPIUnavailableError(f"route-api returned invalid JSON for {path}") from exc

    if not isinstance(parsed, dict):
        raise RouteAPIUnavailableError(f"route-api returned {type(parsed).__name__} for {path}")
    return parsed


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="ignore")
    if not body:
        return f"route-api returned HTTP {exc.code}"
    try:
        parsed = json.loads(body)
    except Exception:
        return body[:300]
    detail = parsed.get("detail") if isinstance(parsed, dict) else None
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return json.dumps(detail, ensure_ascii=True)
    return body[:300]


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
    except ValueError as exc:
        raise RuntimeError(f"invalid_integer_env: {raw}") from exc


def _openai_embeddings_response(
    provider: str,
    model: str,
    vectors: list[list[float]],
    usage: dict[str, Any] | None = None,
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
    payload: dict[str, Any] = {
        "model": model,
        "input": items,
        "encoding_format": req.encoding_format,
    }
    ovms_headers: dict[str, str] = {}
    if OVMS_EMBEDDINGS_API_KEY:
        ovms_headers["Authorization"] = f"Bearer {OVMS_EMBEDDINGS_API_KEY}"
    if OVMS_EMBEDDINGS_UNIX_SOCKET:
        data = _unix_post_json(
            OVMS_EMBEDDINGS_UNIX_SOCKET,
            "/v3/embeddings",
            payload,
            OVMS_EMBEDDINGS_TIMEOUT,
            headers=ovms_headers,
        )
    else:
        data = _http_post_json(
            OVMS_EMBEDDINGS_URL,
            payload,
            OVMS_EMBEDDINGS_TIMEOUT,
            headers=ovms_headers,
        )

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


def _flatten_response_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, str):
                chunks.append(item)
                continue
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                chunks.append(item["text"])
        return "".join(chunks)
    return ""


def _normalize_answer_text(content: Any) -> str:
    text = _flatten_response_content(content).strip()
    while text:
        updated = THINK_TAG_PREFIX_RE.sub("", text, count=1).strip()
        if updated == text:
            break
        text = updated
    return text


def _literal_reply_target(req: RunReq) -> str | None:
    if not OPENAI_LITERAL_COMPLETIONS:
        return None
    if OPENAI_CHAT_TEMPLATE_ENABLE_THINKING is not None:
        return None
    if float(req.temperature) != 0.0:
        return None
    if int(req.max_tokens) > 16:
        return None
    match = LITERAL_REPLY_PROMPT_RE.fullmatch(req.user_text.strip())
    if not match:
        return None
    target = match.group(1).strip()
    if not target or len(target) > 160:
        return None
    return target


def _openai_completion(req: RunReq) -> dict[str, Any]:
    text = ""
    native_completion_url = _llamacpp_completion_url()
    if native_completion_url:
        try:
            native_payload = {
                "model": MODEL,
                "prompt": req.user_text,
                "temperature": float(req.temperature),
                "n_predict": int(req.max_tokens),
            }
            native_data = _http_post_json(
                native_completion_url,
                native_payload,
                TIMEOUT,
                headers=_http_auth_headers(),
            )
            native_text = native_data.get("content")
            if isinstance(native_text, str):
                text = native_text
        except RuntimeError:
            text = ""

    if not text:
        payload = {
            "model": MODEL,
            "prompt": req.user_text,
            "temperature": float(req.temperature),
            "max_tokens": int(req.max_tokens),
        }
        data = _http_post_json(
            f"{BASE_URL}/completions",
            payload,
            TIMEOUT,
            headers=_http_auth_headers(),
        )
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = str(first.get("text") or "")
    if not isinstance(text, str) or not text:
        raise RuntimeError("unexpected_openai_completion_response: missing text")
    return {
        "ok": True,
        "backend": "langchain",
        "model": MODEL,
        "answer": _normalize_answer_text(text),
    }


def _invoke_run_backend(req: RunReq) -> dict[str, Any]:
    if OLLAMA_NATIVE_CHAT and ("litellm" in BASE_URL or "ollama" in BASE_URL):
        return _ollama_chat(req)

    if ChatOpenAI is None or HumanMessage is None:
        raise RuntimeError("langchain_openai dependencies are not installed")

    if _literal_reply_target(req) is not None:
        return _openai_completion(req)

    llm_kwargs: dict[str, Any] = {
        "model": MODEL,
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "request_timeout": TIMEOUT,
        "max_retries": 0,
        "temperature": float(req.temperature),
        "max_tokens": int(req.max_tokens),
    }
    extra_body: dict[str, Any] = {}
    if OPENAI_CHAT_TEMPLATE_ENABLE_THINKING is not None:
        extra_body["chat_template_kwargs"] = {
            "enable_thinking": OPENAI_CHAT_TEMPLATE_ENABLE_THINKING
        }
    if "litellm" in BASE_URL or "ollama" in BASE_URL:
        extra_body["think"] = OLLAMA_THINK
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
    if extra_body:
        llm_kwargs["extra_body"] = extra_body

    llm = ChatOpenAI(**llm_kwargs)
    resp = llm.invoke([HumanMessage(content=req.user_text)])
    return {
        "ok": True,
        "backend": "langchain",
        "model": MODEL,
        "answer": _normalize_answer_text(resp.content),
    }


def _effective_profile_class(profile_class: PROFILE_CLASS | None) -> PROFILE_CLASS:
    return profile_class or "workhorse"


def _load_return_policy_snapshot(profile_class: PROFILE_CLASS | None) -> dict[str, Any]:
    effective_class = _effective_profile_class(profile_class)
    if not RETURN_POLICY_PATH.exists():
        return {
            "available": False,
            "path": str(RETURN_POLICY_PATH),
            "effective_profile_class": effective_class,
        }

    try:
        payload = yaml.safe_load(RETURN_POLICY_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "available": False,
            "path": str(RETURN_POLICY_PATH),
            "effective_profile_class": effective_class,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if not isinstance(payload, dict):
        return {
            "available": False,
            "path": str(RETURN_POLICY_PATH),
            "effective_profile_class": effective_class,
            "error": "return policy did not parse as an object",
        }

    profile_rule = None
    for rule in payload.get("profile_class_rules", []):
        if isinstance(rule, dict) and rule.get("profile_class") == effective_class:
            profile_rule = rule
            break

    reentry = payload.get("reentry") if isinstance(payload.get("reentry"), dict) else {}
    logging = payload.get("logging") if isinstance(payload.get("logging"), dict) else {}
    snapshot: dict[str, Any] = {
        "available": True,
        "path": str(RETURN_POLICY_PATH),
        "policy_id": payload.get("policy_id"),
        "enabled": payload.get("enabled"),
        "effective_profile_class": effective_class,
        "default_reentry_mode": reentry.get("default_mode"),
        "allowed_reentry_modes": reentry.get("allowed_modes", []),
        "emit_return_events": logging.get("emit_return_events"),
        "redact_runtime_values": logging.get("redact_runtime_values"),
    }
    if isinstance(profile_rule, dict):
        snapshot["profile_rule"] = {
            "profile_class": profile_rule.get("profile_class"),
            "max_return_loops": profile_rule.get("max_return_loops"),
            "default_memory_access_strategy": profile_rule.get("default_memory_access_strategy"),
            "max_long_reload_segments": profile_rule.get("max_long_reload_segments"),
            "allow_profile_escalation": profile_rule.get("allow_profile_escalation"),
            "notes": profile_rule.get("notes"),
        }
    return snapshot


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return None


def _pick_summary(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    summary = {key: payload[key] for key in SUMMARY_KEYS if key in payload}
    if summary:
        return summary

    compact = {}
    for key in payload:
        if isinstance(payload[key], (str, int, float, bool)) or payload[key] is None:
            compact[key] = payload[key]
        if len(compact) >= 8:
            break
    if compact:
        return compact

    return {"keys": sorted(payload.keys())[:8]}


def _playbook_summary(card: dict[str, Any]) -> dict[str, Any]:
    registry_entry = card.get("registry_entry") if isinstance(card.get("registry_entry"), dict) else {}
    activation_entry = card.get("activation_entry") if isinstance(card.get("activation_entry"), dict) else {}
    federation_entry = card.get("federation_entry") if isinstance(card.get("federation_entry"), dict) else {}

    summary: dict[str, Any] = {
        "playbook_id": card.get("playbook_id"),
        "name": card.get("name"),
        "scenario": _first_non_empty(activation_entry.get("scenario"), registry_entry.get("scenario")),
        "trigger": _first_non_empty(activation_entry.get("trigger"), registry_entry.get("trigger")),
        "evaluation_posture": _first_non_empty(
            activation_entry.get("evaluation_posture"),
            registry_entry.get("evaluation_posture"),
        ),
        "memory_posture": _first_non_empty(
            activation_entry.get("memory_posture"),
            federation_entry.get("memory_posture"),
            registry_entry.get("memory_posture"),
        ),
        "fallback_mode": _first_non_empty(
            activation_entry.get("fallback_mode"),
            registry_entry.get("fallback_mode"),
        ),
        "return_reentry_modes": activation_entry.get("return_reentry_modes", []),
        "required_skills": federation_entry.get("required_skills", []),
    }

    for key in PLAYBOOK_MEMO_KEYS:
        value = _first_non_empty(
            activation_entry.get(key),
            federation_entry.get(key),
            registry_entry.get(key),
        )
        if value is not None:
            summary[key] = value

    return {key: value for key, value in summary.items() if value not in (None, [], {})}


def _playbook_review_status_note(card: dict[str, Any]) -> dict[str, Any] | None:
    review_status = card.get("review_status")
    if not isinstance(review_status, dict):
        return None

    note = {
        "playbook_id": review_status.get("playbook_id"),
        "gate_verdict": review_status.get("gate_verdict"),
        "reviewed_run_count": review_status.get("reviewed_run_count"),
        "latest_reviewed_run_ref": review_status.get("latest_reviewed_run_ref"),
        "minimum_evidence_threshold": review_status.get("minimum_evidence_threshold"),
        "next_trigger": review_status.get("next_trigger"),
        "composition_signal_summary": review_status.get("composition_signal_summary"),
    }
    return {key: value for key, value in note.items() if value not in (None, [], {})}


def _playbook_review_packet_contract_note(card: dict[str, Any]) -> dict[str, Any] | None:
    contract = card.get("review_packet_contract")
    if not isinstance(contract, dict):
        return None

    note = {
        "playbook_id": contract.get("playbook_id"),
        "scenario": contract.get("scenario"),
        "expected_artifacts": contract.get("expected_artifacts"),
        "eval_anchors": contract.get("eval_anchors"),
        "memo_runtime_surfaces": contract.get("memo_runtime_surfaces"),
        "candidate_packet_kinds": contract.get("candidate_packet_kinds"),
        "review_required": contract.get("review_required"),
        "gate_verdict": contract.get("gate_verdict"),
    }
    return {key: value for key, value in note.items() if value not in (None, [], {})}


def _compact_playbook_bucket(card: dict[str, Any]) -> dict[str, Any]:
    summary = _playbook_summary(card)
    bucket: dict[str, Any] = {
        "playbook_id": summary.get("playbook_id"),
        "name": summary.get("name"),
        "scenario": summary.get("scenario"),
        "trigger": summary.get("trigger"),
        "evaluation_posture": summary.get("evaluation_posture"),
        "memory_posture": summary.get("memory_posture"),
        "fallback_mode": summary.get("fallback_mode"),
        "required_skills": summary.get("required_skills", []),
    }
    for key in PLAYBOOK_MEMO_KEYS:
        if key in summary:
            bucket[key] = summary[key]
    return {key: value for key, value in bucket.items() if value not in (None, [], {})}


def _default_memo_plan_from_playbook(card: dict[str, Any]) -> dict[str, Any] | None:
    playbook_summary = _playbook_summary(card)
    raw_modes = playbook_summary.get("memo_recall_modes")
    if not isinstance(raw_modes, list):
        return None

    modes = [value for value in raw_modes if isinstance(value, str)]
    if not modes:
        return None

    family: MEMO_FAMILY
    mode: MEMO_MODE
    return_ready = False
    checkpoint_posture = playbook_summary.get("memo_checkpoint_posture")
    if "working" in modes:
        family = "object"
        mode = "working"
        return_ready = checkpoint_posture in {"preferred", "required"}
    elif "lineage" in modes:
        family = "router"
        mode = "lineage"
    elif any(candidate in modes for candidate in ("semantic", "episodic", "procedural")):
        family = "router"
        mode = "semantic"
    else:
        return None

    read_path = playbook_summary.get("memo_read_path")
    if read_path not in {"inspect_only", "inspect_then_expand", "inspect_capsule_then_expand"}:
        if family == "object" and mode == "working":
            read_path = "inspect_then_expand"
        elif mode in {"semantic", "lineage"}:
            read_path = "inspect_capsule_then_expand"
        else:
            read_path = "inspect_only"

    return {
        "source": "playbook",
        "family": family,
        "mode": mode,
        "id": None,
        "section_id": None,
        "expand_requested": False,
        "return_ready": return_ready,
        "read_path": read_path,
        "spec": {key: playbook_summary.get(key) for key in PLAYBOOK_MEMO_KEYS if key in playbook_summary},
    }


def _explicit_memo_plan(selector: MemoSelector) -> dict[str, Any]:
    return {
        "source": "request",
        "family": selector.family,
        "mode": selector.mode,
        "id": selector.id,
        "section_id": selector.section_id,
        "expand_requested": selector.expand,
        "return_ready": selector.return_ready,
        "read_path": None,
        "spec": {},
    }


def _inspect_family_for_plan(plan: dict[str, Any]) -> Literal["doctrine", "object"]:
    if plan["family"] == "router":
        return "doctrine"
    return "object"


def _memo_should_expand(plan: dict[str, Any]) -> bool:
    if plan["id"] is None:
        return False
    if plan["section_id"] is not None:
        return True
    if plan["expand_requested"]:
        return True
    if plan["family"] == "object" and plan["mode"] == "working":
        return True
    return plan.get("read_path") in {"inspect_then_expand", "inspect_capsule_then_expand"}


def _memo_contract_note(contract: dict[str, Any]) -> dict[str, Any]:
    note: dict[str, Any] = {
        "mode": contract.get("mode"),
        "inspect_surface": contract.get("inspect_surface"),
        "expand_surface": contract.get("expand_surface"),
        "capsule_surface": contract.get("capsule_surface"),
        "source_route_required": contract.get("source_route_required"),
        "preferred_kinds": contract.get("preferred_kinds"),
        "allowed_scopes": contract.get("allowed_scopes"),
        "preferred_anchor_kinds": contract.get("preferred_anchor_kinds"),
        "checkpoint_continuity_supported": contract.get("checkpoint_continuity_supported"),
        "support_artifact_refs": contract.get("support_artifact_refs"),
    }
    return {key: value for key, value in note.items() if value not in (None, [], {})}


def _memo_writeback_note(writeback_map: dict[str, Any] | None) -> dict[str, Any] | None:
    if writeback_map is None:
        return None

    mapping = writeback_map.get("mapping")
    if not isinstance(mapping, dict):
        return None

    note = {
        "runtime_surface": writeback_map.get("runtime_surface"),
        "contract_id": writeback_map.get("contract_id"),
        "target_kind": mapping.get("target_kind"),
        "writeback_class": mapping.get("writeback_class"),
        "temperature_hint": mapping.get("temperature_hint"),
        "review_state_default": mapping.get("review_state_default"),
        "requires_human_review": mapping.get("requires_human_review"),
    }
    return {key: value for key, value in note.items() if value not in (None, [], {})}


def _kag_context_note(kag_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if kag_context is None:
        return None
    payload = kag_context.get("payload")
    if not isinstance(payload, dict):
        return None
    return payload


def _resolve_playbook_card(req: FederatedRunReq) -> dict[str, Any] | None:
    if req.playbook_id is None and req.playbook_select is None:
        return None

    if req.playbook_id is not None:
        response = _route_api_post("/playbooks/inspect", {"playbook_id": req.playbook_id})
        playbook = response.get("playbook")
        if not isinstance(playbook, dict):
            raise HTTPException(status_code=502, detail="route-api returned invalid playbook inspect payload")
        return playbook

    assert req.playbook_select is not None
    select_response = _route_api_post(
        "/playbooks/select",
        req.playbook_select.model_dump(exclude_none=True),
    )
    matches = select_response.get("playbooks")
    if not isinstance(matches, list):
        raise HTTPException(status_code=502, detail="route-api returned invalid playbook select payload")
    if len(matches) > 1:
        raise HTTPException(
            status_code=409,
            detail="playbook selector matched more than one advisory playbook",
        )
    if not matches:
        raise HTTPException(status_code=404, detail="playbook selector returned no advisory playbook")

    match = matches[0]
    if not isinstance(match, dict) or not isinstance(match.get("playbook_id"), str):
        raise HTTPException(status_code=502, detail="route-api returned invalid compact playbook card")
    inspect_response = _route_api_post("/playbooks/inspect", {"playbook_id": match["playbook_id"]})
    playbook = inspect_response.get("playbook")
    if not isinstance(playbook, dict):
        raise HTTPException(status_code=502, detail="route-api returned invalid playbook inspect payload")
    return playbook


def _resolve_memo_context(plan: dict[str, Any]) -> dict[str, Any]:
    contract_response = _route_api_post(
        "/memo/recall-contract",
        {
            "family": plan["family"],
            "mode": plan["mode"],
            "return_ready": plan["return_ready"],
        },
    )
    contract = contract_response.get("contract")
    if not isinstance(contract, dict):
        raise HTTPException(status_code=502, detail="route-api returned invalid memo recall contract")

    context: dict[str, Any] = {
        "selector": {
            "source": plan["source"],
            "family": plan["family"],
            "mode": plan["mode"],
            "id": plan["id"],
            "section_id": plan["section_id"],
            "expand_requested": plan["expand_requested"],
            "return_ready": plan["return_ready"],
            "read_path": plan.get("read_path"),
            "spec": plan.get("spec", {}),
        },
        "contract": _memo_contract_note(contract),
        "contract_source_files": contract_response.get("source_files", []),
        "sequence": ["recall_contract"],
        "resolution": "contract_only",
        "surface_refs": {
            "inspect_surface": contract.get("inspect_surface"),
            "capsule_surface": contract.get("capsule_surface"),
            "expand_surface": contract.get("expand_surface"),
        },
    }

    if plan["id"] is None:
        return context

    inspect_family = _inspect_family_for_plan(plan)
    inspect_response = _route_api_post(
        "/memo/inspect",
        {"family": inspect_family, "id": plan["id"]},
    )
    inspect_entry = inspect_response.get("entry")
    context["inspect_entry"] = _pick_summary(inspect_entry)
    context["sequence"].append("inspect")
    context["resolution"] = "inspect"

    if contract.get("capsule_surface"):
        capsule_response = _route_api_post(
            "/memo/capsule",
            {"family": inspect_family, "id": plan["id"]},
        )
        context["capsule_entry"] = _pick_summary(capsule_response.get("entry"))
        context["sequence"].append("capsule")
        context["resolution"] = "capsule"

    if _memo_should_expand(plan):
        expand_payload: dict[str, Any] = {
            "family": inspect_family,
            "id": plan["id"],
        }
        if plan["section_id"] is not None:
            expand_payload["section_id"] = plan["section_id"]
        expand_response = _route_api_post("/memo/expand", expand_payload)
        if plan["section_id"] is not None and "section" in expand_response:
            context["expanded_entry"] = {
                "section_id": expand_response.get("section_id"),
                "section": _pick_summary(expand_response.get("section")),
            }
        else:
            context["expanded_entry"] = _pick_summary(expand_response.get("entry"))
        context["sequence"].append("expand")
        context["resolution"] = "expand"

    return context


def _resolve_memo_writeback_map(memo_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if memo_context is None:
        return None

    selector = memo_context.get("selector")
    if not isinstance(selector, dict) or not selector.get("return_ready"):
        return None

    response = _route_api_post("/memo/writeback-map", {"runtime_surface": "checkpoint_export"})
    mapping = response.get("mapping")
    if not isinstance(mapping, dict):
        raise HTTPException(status_code=502, detail="route-api returned invalid memo writeback map")

    return {
        "runtime_surface": response.get("runtime_surface"),
        "contract_type": response.get("contract_type"),
        "contract_id": response.get("contract_id"),
        "runtime_boundary": response.get("runtime_boundary"),
        "mapping": mapping,
        "source_files": response.get("source_files", []),
    }


def _resolve_kag_context(selector: KagSelector) -> dict[str, Any]:
    selector_payload = selector.model_dump(exclude_none=True)

    if selector.inspect_id is not None:
        response = _route_api_post("/kag/inspect", {"surface_id": selector.inspect_id})
        registry_entry = response.get("registry_entry")
        pack = response.get("pack")
        if not isinstance(registry_entry, dict) or not isinstance(pack, dict):
            raise HTTPException(status_code=502, detail="route-api returned invalid kag inspect payload")
        payload = {
            "selector_kind": "inspect_id",
            "surface_id": response.get("surface_id"),
            "registry_entry": _pick_summary(registry_entry),
            "pack": _pick_summary(pack),
        }
        resolution = "inspect"
    elif selector.query_mode is not None:
        response = _route_api_post("/kag/query-mode", {"mode": selector.query_mode})
        scenarios = response.get("reasoning_scenarios")
        regrounding_modes = response.get("regrounding_modes")
        if not isinstance(scenarios, list) or not isinstance(regrounding_modes, list):
            raise HTTPException(status_code=502, detail="route-api returned invalid kag query-mode payload")
        payload = {
            "selector_kind": "query_mode",
            "mode": response.get("mode"),
            "reasoning_scenarios": [_pick_summary(item) for item in scenarios],
            "regrounding_modes": [_pick_summary(item) for item in regrounding_modes],
        }
        resolution = "query_mode"
    elif selector.regrounding_mode is not None:
        response = _route_api_post("/kag/regrounding", {"mode_id": selector.regrounding_mode})
        regrounding_mode = response.get("regrounding_mode")
        if not isinstance(regrounding_mode, dict):
            raise HTTPException(status_code=502, detail="route-api returned invalid kag regrounding payload")
        payload = {
            "selector_kind": "regrounding_mode",
            "mode_id": response.get("mode_id"),
            "regrounding_mode": _pick_summary(regrounding_mode),
        }
        resolution = "regrounding"
    else:
        assert selector.repo is not None
        response = _route_api_post("/kag/repo-entry", {"repo": selector.repo})
        repo_entry = response.get("repo_entry")
        if not isinstance(repo_entry, dict):
            raise HTTPException(status_code=502, detail="route-api returned invalid kag repo-entry payload")
        payload = {
            "selector_kind": "repo",
            "repo": response.get("repo"),
            "repo_entry": _pick_summary(repo_entry),
        }
        resolution = "repo_entry"

    return {
        "selector": selector_payload,
        "resolution": resolution,
        "payload": payload,
        "source_files": response.get("source_files", []),
    }


def _compact_memo_summary(memo_context: dict[str, Any] | None) -> Any:
    if memo_context is None:
        return None
    if "capsule_entry" in memo_context:
        return memo_context["capsule_entry"]
    if "inspect_entry" in memo_context:
        return memo_context["inspect_entry"]
    return None


def _memory_access_payload(memo_context: dict[str, Any] | None) -> Any:
    if memo_context is None:
        return None
    if "expanded_entry" in memo_context:
        return memo_context["expanded_entry"]
    if "capsule_entry" in memo_context:
        return memo_context["capsule_entry"]
    if "inspect_entry" in memo_context:
        return memo_context["inspect_entry"]
    return None


def _knowledge_access_payload(kag_context: dict[str, Any] | None) -> Any:
    note = _kag_context_note(kag_context)
    if note is None:
        return None
    return note


def _json_line(label: str, payload: Any) -> str:
    return f"{label}={json.dumps(payload, ensure_ascii=True, sort_keys=True)}"


def _bucket_block(name: str, lines: list[str]) -> str:
    return f"## {name}\n" + "\n".join(lines)


def _build_federated_prompt(
    req: FederatedRunReq,
    *,
    playbook_card: dict[str, Any] | None,
    memo_context: dict[str, Any] | None,
    memo_writeback_map: dict[str, Any] | None,
    kag_context: dict[str, Any] | None,
    policy_snapshot: dict[str, Any],
) -> str:
    blocks: list[str] = []

    core_lines: list[str] = []
    if playbook_card is not None:
        core_lines.append(_json_line("playbook_summary", _playbook_summary(playbook_card)))
        review_status = _playbook_review_status_note(playbook_card)
        if review_status is not None:
            core_lines.append(_json_line("playbook_review_status", review_status))
        review_packet_contract = _playbook_review_packet_contract_note(playbook_card)
        if review_packet_contract is not None:
            core_lines.append(_json_line("playbook_review_packet_contract", review_packet_contract))
    core_lines.append(_json_line("return_policy_snapshot", policy_snapshot))
    if memo_context is not None:
        core_lines.append(_json_line("memo_contract_note", memo_context["contract"]))
    memo_writeback_note = _memo_writeback_note(memo_writeback_map)
    if memo_writeback_note is not None:
        core_lines.append(_json_line("memo_writeback_map", memo_writeback_note))
    if core_lines:
        blocks.append(_bucket_block("core", core_lines))

    short_lines: list[str] = []
    if playbook_card is not None:
        short_lines.append(_json_line("playbook_activation_summary", _compact_playbook_bucket(playbook_card)))
    compact_memo = _compact_memo_summary(memo_context)
    if compact_memo is not None:
        short_lines.append(_json_line("compact_memo_summary", compact_memo))
    if short_lines:
        blocks.append(_bucket_block("short", short_lines))

    memory_access = _memory_access_payload(memo_context)
    if memory_access is not None:
        blocks.append(_bucket_block("memory_access", [_json_line("memo_surface", memory_access)]))

    knowledge_access = _knowledge_access_payload(kag_context)
    if knowledge_access is not None:
        blocks.append(_bucket_block("knowledge_access", [_json_line("kag_context", knowledge_access)]))

    blocks.append(_bucket_block("user", [req.user_text]))
    return "\n\n".join(blocks)


def _advisory_trace(
    *,
    req: FederatedRunReq,
    playbook_card: dict[str, Any] | None,
    memo_context: dict[str, Any] | None,
    memo_writeback_map: dict[str, Any] | None,
    kag_context: dict[str, Any] | None,
    policy_snapshot: dict[str, Any],
) -> dict[str, Any]:
    trace: dict[str, Any] = {
        "selectors": {
            "playbook_id": req.playbook_id,
            "playbook_select": req.playbook_select.model_dump(exclude_none=True)
            if req.playbook_select is not None
            else None,
            "kag": req.kag.model_dump(exclude_none=True) if req.kag is not None else None,
            "profile_class": _effective_profile_class(req.profile_class),
        },
        "policy_snapshot": policy_snapshot,
    }
    if playbook_card is not None:
        trace["playbook"] = {
            "summary": _playbook_summary(playbook_card),
            "source_files": playbook_card.get("source_files", []),
        }
        review_status = _playbook_review_status_note(playbook_card)
        if review_status is not None:
            trace["playbook"]["review_status"] = review_status
        review_packet_contract = _playbook_review_packet_contract_note(playbook_card)
        if review_packet_contract is not None:
            trace["playbook"]["review_packet_contract"] = review_packet_contract
    if memo_context is not None:
        trace["memo"] = {
            "selector": memo_context["selector"],
            "contract": memo_context["contract"],
            "surface_refs": memo_context["surface_refs"],
            "sequence": memo_context["sequence"],
            "resolution": memo_context["resolution"],
            "source_files": memo_context.get("contract_source_files", []),
        }
        memo_writeback_note = _memo_writeback_note(memo_writeback_map)
        if memo_writeback_note is not None:
            trace["memo"]["writeback_map"] = memo_writeback_note
    if kag_context is not None:
        trace["kag"] = {
            "selector": kag_context["selector"],
            "resolution": kag_context["resolution"],
            "context": kag_context["payload"],
            "source_files": kag_context.get("source_files", []),
        }
    return trace


def _require_federated_enabled() -> None:
    if not FEDERATED_RUN_ENABLED:
        raise HTTPException(status_code=503, detail="federated run is disabled by configuration")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "langchain-api",
        "embeddings_provider": EMBEDDINGS_PROVIDER,
        "ovms_auth_enabled": bool(OVMS_EMBEDDINGS_API_KEY),
        "ovms_transport": "unix" if OVMS_EMBEDDINGS_UNIX_SOCKET else "http",
        "federated_run_enabled": FEDERATED_RUN_ENABLED,
        "langgraph_inventory_enabled": True,
        "langgraph_inventory_root": str(LANGGRAPH_INVENTORY_ROOT),
        "otlp_trace_export_enabled": LANGGRAPH_INVENTORY_OTLP_ENABLED,
    }


@app.post("/run")
def run(req: RunReq) -> dict[str, Any]:
    trace_context = _runtime_trace_context(req, "run")
    try:
        response = _invoke_run_backend(req)
        response["runtime_trace"] = _record_runtime_trace(trace_context, req, status="ok", response=response)
        return response
    except Exception as exc:
        _record_runtime_trace(trace_context, req, status="error", error=exc)
        detail_key = "upstream_ollama_chat_error" if OLLAMA_NATIVE_CHAT and (
            "litellm" in BASE_URL or "ollama" in BASE_URL
        ) else "upstream_llm_error"
        raise HTTPException(
            status_code=502,
            detail=f"{detail_key}: {type(exc).__name__}: {exc}",
        ) from exc


@app.post("/run/federated")
def run_federated(req: FederatedRunReq) -> dict[str, Any]:
    trace_context = _runtime_trace_context(req, "run_federated")
    try:
        _require_federated_enabled()
        playbook_card = _resolve_playbook_card(req)
        memo_plan = _explicit_memo_plan(req.memo) if req.memo is not None else None
        if memo_plan is None and playbook_card is not None:
            memo_plan = _default_memo_plan_from_playbook(playbook_card)
        memo_context = _resolve_memo_context(memo_plan) if memo_plan is not None else None
        memo_writeback_map = _resolve_memo_writeback_map(memo_context)
        kag_context = _resolve_kag_context(req.kag) if req.kag is not None else None
        policy_snapshot = _load_return_policy_snapshot(req.profile_class)
        federated_prompt = _build_federated_prompt(
            req,
            playbook_card=playbook_card,
            memo_context=memo_context,
            memo_writeback_map=memo_writeback_map,
            kag_context=kag_context,
            policy_snapshot=policy_snapshot,
        )
        backend_req = RunReq(
            session_id=req.session_id,
            user_text=federated_prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        response = _invoke_run_backend(backend_req)
        response["advisory_trace"] = _advisory_trace(
            req=req,
            playbook_card=playbook_card,
            memo_context=memo_context,
            memo_writeback_map=memo_writeback_map,
            kag_context=kag_context,
            policy_snapshot=policy_snapshot,
        )
        response["runtime_trace"] = _record_runtime_trace(
            trace_context,
            req,
            status="ok",
            response=response,
            advisory_trace=response["advisory_trace"],
        )
        return response
    except HTTPException as exc:
        _record_runtime_trace(trace_context, req, status="error", error=exc)
        raise
    except RouteAPIHTTPError as exc:
        _record_runtime_trace(trace_context, req, status="error", error=exc)
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except RouteAPIUnavailableError as exc:
        _record_runtime_trace(trace_context, req, status="error", error=exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _record_runtime_trace(trace_context, req, status="error", error=exc)
        raise HTTPException(
            status_code=502,
            detail=f"upstream_federated_run_error: {type(exc).__name__}: {exc}",
        ) from exc


@app.get("/langgraph/inventory")
def langgraph_inventory(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, LANGGRAPH_INVENTORY_LIMIT))
    latest = _read_json_file(LANGGRAPH_INVENTORY_ROOT / "latest.json")
    return {
        "ok": True,
        "service": "langchain-api",
        "schema": "abyss_stack_langchain_inventory_readout_v1",
        "root": str(LANGGRAPH_INVENTORY_ROOT),
        "thread_inventory_present": bool(_latest_thread_summaries(1)),
        "checkpoint_inventory_present": (LANGGRAPH_INVENTORY_ROOT / "checkpoints").exists(),
        "trace_inventory_present": bool(_latest_trace_summaries(1)),
        "latest": _inventory_summary(latest) if isinstance(latest, dict) else None,
        "threads": _latest_thread_summaries(safe_limit),
        "traces": _latest_trace_summaries(safe_limit),
        "redaction": {
            "raw_prompt_stored": False,
            "raw_answer_stored": False,
            "raw_advisory_payload_stored": False,
        },
    }


@app.get("/threads")
def threads(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, LANGGRAPH_INVENTORY_LIMIT))
    rows = _latest_thread_summaries(safe_limit)
    return {
        "ok": True,
        "schema": "abyss_stack_langchain_threads_v1",
        "threads": rows,
        "count": len(rows),
    }


@app.get("/threads/{thread_id}/checkpoints")
def thread_checkpoints(thread_id: str, limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, LANGGRAPH_INVENTORY_LIMIT))
    safe_thread_id = _safe_inventory_id(thread_id)
    path = _record_path(LANGGRAPH_INVENTORY_ROOT, "threads", f"{safe_thread_id}.jsonl")
    rows = [_inventory_summary(row) for row in _read_jsonl_tail(path, safe_limit)]
    return {
        "ok": True,
        "schema": "abyss_stack_langchain_thread_checkpoints_v1",
        "thread_id": safe_thread_id,
        "checkpoints": rows,
        "count": len(rows),
    }


@app.get("/traces")
def traces(limit: int = 20) -> dict[str, Any]:
    safe_limit = max(1, min(limit, LANGGRAPH_INVENTORY_LIMIT))
    rows = _latest_trace_summaries(safe_limit)
    return {
        "ok": True,
        "schema": "abyss_stack_langchain_traces_v1",
        "traces": rows,
        "count": len(rows),
    }


@app.get("/traces/{trace_id}")
def trace_detail(trace_id: str) -> dict[str, Any]:
    safe_trace_id = _safe_inventory_id(trace_id)
    path = _record_path(LANGGRAPH_INVENTORY_ROOT, "traces", f"{safe_trace_id}.json")
    record = _read_json_file(path)
    if record is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return {
        "ok": True,
        "schema": "abyss_stack_langchain_trace_detail_v1",
        "trace": _inventory_summary(record),
    }


@app.post("/langgraph/smoke")
def langgraph_smoke(req: LangGraphSmokeReq) -> dict[str, Any]:
    trace_context = _runtime_trace_context(req, "synthetic_smoke")
    response = {
        "ok": True,
        "backend": "synthetic",
        "model": "none",
        "answer": "langchain-api inventory smoke recorded",
    }
    runtime_trace = _record_runtime_trace(trace_context, req, status="ok", response=response)
    return {
        "ok": True,
        "service": "langchain-api",
        "runtime_trace": runtime_trace,
    }


@app.post("/embeddings")
def embeddings(req: EmbeddingsReq) -> dict[str, Any]:
    items = _normalize_input(req.input)
    try:
        if EMBEDDINGS_PROVIDER == "ovms":
            return _ovms_embeddings(req, items)
        if EMBEDDINGS_PROVIDER == "ollama":
            return _ollama_embeddings(req, items)
        if EMBEDDINGS_PROVIDER == "disabled":
            raise HTTPException(
                status_code=503,
                detail="embeddings_disabled: current runtime selection does not provide an embeddings backend",
            )
        raise HTTPException(
            status_code=500,
            detail=f"unsupported_embeddings_provider: {EMBEDDINGS_PROVIDER}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"upstream_embeddings_error: {type(exc).__name__}: {exc}",
        ) from exc
