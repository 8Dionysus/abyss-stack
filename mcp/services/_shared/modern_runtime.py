"""Canonical MCP 2.x runtime policy for standalone organ packages.

Owner packages keep their own tools, resources, prompts, and authorization
policy. This module owns only the shared native MCP 2.x launch seam and the
modern protocol admission policy. It deliberately does not emulate the
removed FastMCP/settings surface or expose private SDK aliases.
"""

from __future__ import annotations

import json
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from mcp.server import MCPServer

try:
    from ._runtime_config import (
        MCP_PROTOCOL_PATH,
        MCP_PROTOCOL_VERSION,
        MCP_SDK_MAJOR,
        MCP_TESTED_SDK_LOCK,
        TRANSPORT_CONFIG,
    )
except ImportError:  # pragma: no cover - canonical helper import
    from runtime_config import (  # type: ignore[import-not-found]
        MCP_PROTOCOL_PATH,
        MCP_PROTOCOL_VERSION,
        MCP_SDK_MAJOR,
        MCP_TESTED_SDK_LOCK,
        TRANSPORT_CONFIG,
    )


_VERSION_MAJOR = re.compile(r"^(\d+)(?:\.|$)")


def _major(version_text: str) -> int:
    match = _VERSION_MAJOR.match(version_text.strip())
    if match is None:
        raise RuntimeError(f"unable to determine MCP SDK major from {version_text!r}")
    return int(match.group(1))


def require_supported_sdk() -> None:
    """Fail closed unless the exact reviewed MCP SDK pair is installed."""

    try:
        installed = version(TRANSPORT_CONFIG.sdk_distribution)
    except PackageNotFoundError as exc:  # pragma: no cover - import guard
        raise RuntimeError("the MCP SDK is not installed") from exc
    if _major(installed) != MCP_SDK_MAJOR or installed != MCP_TESTED_SDK_LOCK:
        raise RuntimeError(
            "OS Abyss organ servers require exact MCP SDK "
            f"{MCP_TESTED_SDK_LOCK}; observed {installed}"
        )

    try:
        installed_types = version(TRANSPORT_CONFIG.sdk_companion_distribution)
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "OS Abyss organ servers require the exact MCP companion distribution "
            f"{TRANSPORT_CONFIG.sdk_companion_distribution}=={MCP_TESTED_SDK_LOCK}"
        ) from exc
    if (
        _major(installed_types) != MCP_SDK_MAJOR
        or installed_types != MCP_TESTED_SDK_LOCK
    ):
        raise RuntimeError(
            "OS Abyss organ servers require exact MCP companion distribution "
            f"{TRANSPORT_CONFIG.sdk_companion_distribution}=={MCP_TESTED_SDK_LOCK}; "
            f"observed {installed_types}"
        )

    required_methods = (
        "run",
        "streamable_http_app",
        "run_streamable_http_async",
    )
    missing = [name for name in required_methods if not hasattr(MCPServer, name)]
    if missing:
        raise RuntimeError(
            "installed MCP SDK lacks the native MCP 2.x API: "
            + ", ".join(missing)
        )


class _ModernOnlyHTTPApp:
    """Reject non-modern protocol handshakes before the SDK dispatches them."""

    def __init__(self, app: Any, *, mcp_path: str) -> None:
        self.app = app
        self.mcp_path = mcp_path.rstrip("/") or "/"

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        path = str(scope.get("path", "")).rstrip("/") or "/"
        if scope.get("type") == "http" and path == self.mcp_path:
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1").strip(" \t")
                for key, value in scope.get("headers", ())
            }
            requested = headers.get("mcp-protocol-version")
            if requested != MCP_PROTOCOL_VERSION:
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": TRANSPORT_CONFIG.modern_only_rejection_code,
                            "message": (
                                "OS Abyss organ endpoints require modern MCP "
                                f"{MCP_PROTOCOL_VERSION}"
                            ),
                            "data": {
                                "supported": [MCP_PROTOCOL_VERSION],
                                "requested": requested or "missing",
                            },
                        },
                    },
                    separators=(",", ":"),
                ).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 400,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (
                                b"mcp-protocol-version",
                                MCP_PROTOCOL_VERSION.encode("ascii"),
                            ),
                            (b"content-length", str(len(payload)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": payload})
                return
        await self.app(scope, receive, send)


class ModernMCPServer(MCPServer):
    """Native MCP 2.x server with the reviewed modern-only HTTP policy."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        require_supported_sdk()
        super().__init__(*args, **kwargs)

    @property
    def application_version(self) -> str | None:
        """Read the server identity stored by the MCP 2.x server."""

        return self.version

    def streamable_http_app(self, **kwargs: Any) -> Any:
        streamable_http_path = kwargs.get(
            "streamable_http_path", MCP_PROTOCOL_PATH
        )
        if streamable_http_path != MCP_PROTOCOL_PATH:
            raise ValueError(
                "MCP streamable HTTP path must remain "
                f"{MCP_PROTOCOL_PATH!r}; observed {streamable_http_path!r}"
            )
        app = super().streamable_http_app(**kwargs)
        if not TRANSPORT_CONFIG.modern_only:
            return app
        return _ModernOnlyHTTPApp(app, mcp_path=streamable_http_path)


def run_server(server: ModernMCPServer, auth_config: Any) -> None:
    """Run one package through the native MCP 2.x transport API."""

    settings = auth_config.transport
    if settings.transport == TRANSPORT_CONFIG.default_transport:
        server.run(TRANSPORT_CONFIG.default_transport)
        return
    if settings.transport != TRANSPORT_CONFIG.streamable_http_transport:
        raise RuntimeError(f"unsupported MCP transport: {settings.transport}")
    if settings.host is None or settings.port is None:
        raise RuntimeError("streamable HTTP transport requires host and port")
    server.run(
        TRANSPORT_CONFIG.streamable_http_transport,
        host=settings.host,
        port=settings.port,
        streamable_http_path=settings.streamable_http_path,
        json_response=True,
        stateless_http=True,
        transport_security=auth_config.transport_security,
    )
