"""Canonical MCP 2026-07-28 runtime seam for standalone organ packages.

The organ packages keep their owner-specific tools, resources, prompts, and
authorization policy.  This module owns only the shared server/transport seam
needed to run those catalogs on the stable Python MCP 2.x implementation.
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from mcp.server import MCPServer


PROTOCOL_VERSION = "2026-07-28"
SUPPORTED_MCP_SDK = "2.1.1"


class _ModernOnlyHTTPApp:
    """Reject handshake-era traffic before the dual-era SDK can admit it."""

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
            if requested != PROTOCOL_VERSION:
                payload = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32022,
                            "message": (
                                "OS Abyss organ endpoints require modern MCP "
                                f"{PROTOCOL_VERSION}"
                            ),
                            "data": {
                                "supported": [PROTOCOL_VERSION],
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
                            (b"mcp-protocol-version", PROTOCOL_VERSION.encode("ascii")),
                            (b"content-length", str(len(payload)).encode("ascii")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": payload})
                return
        await self.app(scope, receive, send)


def require_supported_sdk() -> None:
    """Fail closed instead of silently negotiating through an older SDK."""

    try:
        installed = version("mcp")
    except PackageNotFoundError as exc:  # pragma: no cover - import guard
        raise RuntimeError("the MCP SDK is not installed") from exc
    if installed != SUPPORTED_MCP_SDK:
        raise RuntimeError(
            "OS Abyss organ servers require the exact modern MCP SDK "
            f"{SUPPORTED_MCP_SDK}; observed {installed}"
        )


class AbyssMCPServer(MCPServer):
    """Small compatibility seam from the former FastMCP surface to MCP 2.x.

    MCP 2.x deliberately replaced ``FastMCP`` with ``MCPServer``.  The owner
    packages already use the decorator/managers that MCPServer retains; only
    constructor-owned HTTP settings and the low-level identity alias need a
    bounded bridge while the packages are migrated without rewriting their
    domain logic.
    """

    def __init__(
        self,
        *args: Any,
        json_response: bool = False,
        stateless_http: bool = True,
        transport_security: Any | None = None,
        modern_only_http: bool = True,
        host: str = "127.0.0.1",
        port: int = 8000,
        **kwargs: Any,
    ) -> None:
        require_supported_sdk()
        super().__init__(*args, **kwargs)
        self._abyss_json_response = json_response
        self._abyss_stateless_http = stateless_http
        self._abyss_transport_security = transport_security
        self._abyss_modern_only_http = modern_only_http
        # Existing owner packages bind application-owned serverInfo.version
        # through this reviewed seam.  It aliases the same MCP 2.x server.
        self._mcp_server = self._lowlevel_server
        # Preserve the package-local launch shape until every package can pass
        # host/port directly.  Pydantic settings intentionally has no such
        # source fields, so these are runtime-only attributes.
        object.__setattr__(self.settings, "host", host)
        object.__setattr__(self.settings, "port", port)

    def configure_http(self, host: str, port: int) -> None:
        """Bind the reviewed loopback address used by the package launcher."""

        object.__setattr__(self.settings, "host", host)
        object.__setattr__(self.settings, "port", port)

    def run(
        self,
        transport: Literal["stdio", "sse", "streamable-http"] = "stdio",
        **kwargs: Any,
    ) -> None:
        if transport == "streamable-http":
            kwargs.setdefault("host", self.settings.host)
            kwargs.setdefault("port", self.settings.port)
            kwargs.setdefault("json_response", self._abyss_json_response)
            kwargs.setdefault("stateless_http", self._abyss_stateless_http)
            kwargs.setdefault(
                "transport_security", self._abyss_transport_security
            )
        super().run(transport=transport, **kwargs)

    def streamable_http_app(self, **kwargs: Any) -> Any:
        streamable_http_path = kwargs.get("streamable_http_path", "/mcp")
        kwargs.setdefault("host", self.settings.host)
        kwargs.setdefault("json_response", self._abyss_json_response)
        kwargs.setdefault("stateless_http", self._abyss_stateless_http)
        kwargs.setdefault("transport_security", self._abyss_transport_security)
        app = super().streamable_http_app(**kwargs)
        if not self._abyss_modern_only_http:
            return app
        return _ModernOnlyHTTPApp(app, mcp_path=streamable_http_path)
