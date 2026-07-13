from __future__ import annotations

import json
from http.client import RemoteDisconnected
from typing import Any, Mapping
from urllib import error, request


class HttpJsonError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


class JsonHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        headers: Mapping[str, str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout = timeout

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json", **self.headers}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        target = f"{self.base_url}/{path.lstrip('/')}"
        call = request.Request(target, data=body, headers=headers, method=method)
        try:
            with request.urlopen(call, timeout=self.timeout) as response:
                raw = response.read()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise HttpJsonError(exc.code, f"HTTP {exc.code} from {target}: {detail}") from exc
        except error.URLError as exc:
            raise HttpJsonError(0, f"request failed for {target}: {exc.reason}") from exc
        except (ConnectionError, RemoteDisconnected, TimeoutError) as exc:
            raise HttpJsonError(0, f"request failed for {target}: {exc}") from exc
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HttpJsonError(0, f"non-JSON response from {target}") from exc
        if not isinstance(decoded, dict):
            raise HttpJsonError(0, f"non-object JSON response from {target}")
        return decoded
