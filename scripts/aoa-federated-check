#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_HEALTH_URL = "http://127.0.0.1:5403/health"
DEFAULT_RUN_URL = "http://127.0.0.1:5403/run/federated"
DEFAULT_QUERY_MODE = "local_search"
DEFAULT_INSPECT_ID = "AOA-K-0011"
DEFAULT_PLAYBOOK_ID = "AOA-P-0008"
DEFAULT_MEMO_ID = "AOA-M-0001"
DEFAULT_MEMO_FAMILY = "router"
DEFAULT_MEMO_MODE = "semantic"
DEFAULT_MEMO_SEQUENCE = ["recall_contract", "inspect", "capsule"]
DEFAULT_QUERY_PROMPT = "Return one short line only. This is a federated advisory seam check."
DEFAULT_INSPECT_PROMPT = "Use the Zarathustra retrieval surface as advisory context only. Return one short line only."
DEFAULT_PLAYBOOK_PROMPT = "Summarize the current route in one short line only."
DEFAULT_MEMO_PROMPT = "Use this memo card if it helps. Return one short line only."


def _request_json(
    url: str,
    *,
    payload: dict[str, Any] | None,
    timeout_s: float,
) -> tuple[int, dict[str, Any], float]:
    req = urllib.request.Request(
        url=url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )

    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
        status = resp.status
    elapsed_s = round(time.perf_counter() - start, 3)

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"expected JSON object from {url}, got {type(parsed).__name__}")
    return status, parsed, elapsed_s


def build_probe_payload(
    *,
    prompt: str | None = None,
    query_mode: str | None = DEFAULT_QUERY_MODE,
    inspect_id: str | None = None,
    playbook_id: str | None = None,
    memo_id: str | None = None,
    max_tokens: int = 64,
) -> dict[str, Any]:
    selector_count = sum(value is not None for value in (query_mode, inspect_id, playbook_id, memo_id))
    if selector_count != 1:
        raise ValueError("specify exactly one advisory selector")
    if prompt is None:
        if memo_id is not None:
            prompt = DEFAULT_MEMO_PROMPT
        elif inspect_id is not None:
            prompt = DEFAULT_INSPECT_PROMPT
        elif playbook_id is not None:
            prompt = DEFAULT_PLAYBOOK_PROMPT
        else:
            prompt = DEFAULT_QUERY_PROMPT
    payload = {
        "user_text": prompt,
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    if playbook_id is not None:
        payload["playbook_id"] = playbook_id
    elif memo_id is not None:
        payload["memo"] = {"family": DEFAULT_MEMO_FAMILY, "mode": DEFAULT_MEMO_MODE, "id": memo_id}
    else:
        payload["kag"] = {"inspect_id": inspect_id} if inspect_id is not None else {"query_mode": query_mode}
    return payload


def run_check(
    *,
    url: str,
    health_url: str,
    timeout_s: float,
    require_enabled: bool,
    query_mode: str | None = DEFAULT_QUERY_MODE,
    inspect_id: str | None = None,
    playbook_id: str | None = None,
    memo_id: str | None = None,
) -> dict[str, Any]:
    health_status, health_body, health_elapsed_s = _request_json(
        health_url,
        payload=None,
        timeout_s=timeout_s,
    )

    if not health_body.get("ok"):
        return {
            "ok": False,
            "state": "fail",
            "url": url,
            "health_url": health_url,
            "health_http_status": health_status,
            "gate_enabled": None,
            "elapsed_s": health_elapsed_s,
            "error": "health payload did not report ok=true",
        }

    gate_enabled = bool(health_body.get("federated_run_enabled"))
    if not gate_enabled:
        return {
            "ok": not require_enabled,
            "state": "not_enabled" if not require_enabled else "disabled",
            "url": url,
            "health_url": health_url,
            "health_http_status": health_status,
            "http_status": None,
            "gate_enabled": False,
            "elapsed_s": health_elapsed_s,
            "validation": {
                "expected": {"federated_run_enabled": True} if require_enabled else {"federated_run_enabled": False},
                "observed": {"federated_run_enabled": False},
            },
            "error": None if not require_enabled else "federated advisory gate is disabled",
        }

    payload = build_probe_payload(
        query_mode=query_mode,
        inspect_id=inspect_id,
        playbook_id=playbook_id,
        memo_id=memo_id,
    )
    status, body, elapsed_s = _request_json(
        url,
        payload=payload,
        timeout_s=timeout_s,
    )

    answer = str(body.get("answer") or "").strip()
    advisory_trace = body.get("advisory_trace")
    selectors = advisory_trace.get("selectors") if isinstance(advisory_trace, dict) else None
    kag_trace = advisory_trace.get("kag") if isinstance(advisory_trace, dict) else None
    playbook_trace = advisory_trace.get("playbook") if isinstance(advisory_trace, dict) else None
    memo_trace = advisory_trace.get("memo") if isinstance(advisory_trace, dict) else None
    observed_selector = selectors.get("kag") if isinstance(selectors, dict) else None
    observed_playbook_selector = selectors.get("playbook_id") if isinstance(selectors, dict) else None
    observed_resolution = kag_trace.get("resolution") if isinstance(kag_trace, dict) else None
    kag_context = kag_trace.get("context") if isinstance(kag_trace, dict) else None
    observed_surface_id = kag_context.get("surface_id") if isinstance(kag_context, dict) else None
    observed_source_files = kag_trace.get("source_files") if isinstance(kag_trace, dict) else None
    playbook_summary = playbook_trace.get("summary") if isinstance(playbook_trace, dict) else None
    observed_playbook_summary_id = playbook_summary.get("playbook_id") if isinstance(playbook_summary, dict) else None
    observed_playbook_source_files = playbook_trace.get("source_files") if isinstance(playbook_trace, dict) else None
    observed_review_packet_contract = playbook_trace.get("review_packet_contract") if isinstance(playbook_trace, dict) else None
    memo_selector = memo_trace.get("selector") if isinstance(memo_trace, dict) else None
    observed_memo_source = memo_selector.get("source") if isinstance(memo_selector, dict) else None
    observed_memo_family = memo_selector.get("family") if isinstance(memo_selector, dict) else None
    observed_memo_mode = memo_selector.get("mode") if isinstance(memo_selector, dict) else None
    observed_memo_id = memo_selector.get("id") if isinstance(memo_selector, dict) else None
    observed_memo_resolution = memo_trace.get("resolution") if isinstance(memo_trace, dict) else None
    observed_memo_sequence = memo_trace.get("sequence") if isinstance(memo_trace, dict) else None
    observed_memo_source_files = memo_trace.get("source_files") if isinstance(memo_trace, dict) else None

    if playbook_id is not None:
        validation = {
            "expected": {
                "selector": playbook_id,
                "playbook_summary_id": playbook_id,
                "playbook_source_files": True,
                "review_packet_contract": True,
                "non_empty_answer": True,
            },
            "observed": {
                "selector": observed_playbook_selector,
                "playbook_summary_id": observed_playbook_summary_id,
                "playbook_source_files": bool(observed_playbook_source_files),
                "review_packet_contract": isinstance(observed_review_packet_contract, dict),
                "non_empty_answer": bool(answer),
            },
        }

        ok = (
            status == 200
            and bool(answer)
            and observed_playbook_selector == playbook_id
            and observed_playbook_summary_id == playbook_id
            and isinstance(observed_playbook_source_files, list)
            and bool(observed_playbook_source_files)
            and isinstance(observed_review_packet_contract, dict)
        )
    elif memo_id is not None:
        validation = {
            "expected": {
                "memo_selector_source": "request",
                "memo_selector_family": DEFAULT_MEMO_FAMILY,
                "memo_selector_mode": DEFAULT_MEMO_MODE,
                "memo_selector_id": memo_id,
                "memo_resolution": "capsule",
                "memo_sequence": DEFAULT_MEMO_SEQUENCE,
                "memo_source_files": True,
                "non_empty_answer": True,
            },
            "observed": {
                "memo_selector_source": observed_memo_source,
                "memo_selector_family": observed_memo_family,
                "memo_selector_mode": observed_memo_mode,
                "memo_selector_id": observed_memo_id,
                "memo_resolution": observed_memo_resolution,
                "memo_sequence": observed_memo_sequence,
                "memo_source_files": bool(observed_memo_source_files),
                "non_empty_answer": bool(answer),
            },
        }

        ok = (
            status == 200
            and bool(answer)
            and observed_memo_source == "request"
            and observed_memo_family == DEFAULT_MEMO_FAMILY
            and observed_memo_mode == DEFAULT_MEMO_MODE
            and observed_memo_id == memo_id
            and observed_memo_resolution == "capsule"
            and observed_memo_sequence == DEFAULT_MEMO_SEQUENCE
            and isinstance(observed_memo_source_files, list)
            and bool(observed_memo_source_files)
        )
    elif inspect_id is not None:
        validation = {
            "expected": {
                "selector": {"inspect_id": inspect_id},
                "kag_resolution": "inspect",
                "kag_surface_id": inspect_id,
                "kag_source_files": True,
                "non_empty_answer": True,
            },
            "observed": {
                "selector": observed_selector,
                "kag_resolution": observed_resolution,
                "kag_surface_id": observed_surface_id,
                "kag_source_files": bool(observed_source_files),
                "non_empty_answer": bool(answer),
            },
        }

        ok = (
            status == 200
            and bool(answer)
            and observed_selector == {"inspect_id": inspect_id}
            and observed_resolution == "inspect"
            and observed_surface_id == inspect_id
            and isinstance(observed_source_files, list)
            and bool(observed_source_files)
        )
    else:
        assert query_mode is not None
        validation = {
            "expected": {
                "selector": {"query_mode": query_mode},
                "kag_resolution": "query_mode",
                "non_empty_answer": True,
            },
            "observed": {
                "selector": observed_selector,
                "kag_resolution": observed_resolution,
                "non_empty_answer": bool(answer),
            },
        }

        ok = (
            status == 200
            and bool(answer)
            and observed_selector == {"query_mode": query_mode}
            and observed_resolution == "query_mode"
        )

    result: dict[str, Any] = {
        "ok": ok,
        "state": "pass" if ok else "fail",
        "url": url,
        "health_url": health_url,
        "health_http_status": health_status,
        "http_status": status,
        "gate_enabled": True,
        "elapsed_s": elapsed_s,
        "answer": answer,
        "validation": validation,
    }
    if not ok:
        result["error"] = "federated response did not satisfy the advisory contract"
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded federated advisory contract check through langchain-api."
    )
    parser.add_argument("--url", default=DEFAULT_RUN_URL)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--query-mode", default=None)
    parser.add_argument("--inspect-id", default=None)
    parser.add_argument("--playbook-id", default=None)
    parser.add_argument("--memo-id", default=None)
    parser.add_argument("--require-enabled", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    query_mode = args.query_mode
    inspect_id = args.inspect_id
    playbook_id = args.playbook_id
    memo_id = args.memo_id
    if query_mode is None and inspect_id is None and playbook_id is None and memo_id is None:
        query_mode = DEFAULT_QUERY_MODE
    selector_count = sum(value is not None for value in (query_mode, inspect_id, playbook_id, memo_id))
    if selector_count != 1:
        parser.error("use exactly one of --query-mode, --inspect-id, --playbook-id, or --memo-id")

    try:
        result = run_check(
            url=args.url,
            health_url=args.health_url,
            timeout_s=args.timeout,
            require_enabled=args.require_enabled,
            query_mode=query_mode,
            inspect_id=inspect_id,
            playbook_id=playbook_id,
            memo_id=memo_id,
        )
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="ignore")
        result = {
            "ok": False,
            "state": "fail",
            "url": args.url,
            "health_url": args.health_url,
            "http_status": exc.code,
            "gate_enabled": None,
            "elapsed_s": None,
            "error": f"http_error {exc.code}: {payload[:300]}",
        }
    except Exception as exc:
        result = {
            "ok": False,
            "state": "fail",
            "url": args.url,
            "health_url": args.health_url,
            "http_status": None,
            "gate_enabled": None,
            "elapsed_s": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if args.json:
        sys.stdout.write(json.dumps(result, ensure_ascii=True) + "\n")
    else:
        if result.get("state") == "not_enabled":
            print(f"skip federated advisory gate disabled at {args.health_url}")
        elif result.get("ok"):
            print(f"ok   federated advisory {args.url} {result.get('elapsed_s')}s")
        else:
            detail = result.get("error") or result.get("validation")
            print(f"fail federated advisory {args.url} {detail}")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
