"""Canonical authenticated loopback transport helper for vendored MCP packages."""

from __future__ import annotations

import hmac
import os
import re
from pathlib import Path
from typing import Any, NamedTuple


TOKEN_ENV_VAR = "AOA_MCP_HTTP_BEARER_TOKEN"
CREDENTIAL_NAME = "aoa-mcp-http-bearer-token"
AUTH_SCOPE = "mcp:access"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,512}")
_CREDENTIAL_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,128}")
_ENV_NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,127}")
_SCOPE_PATTERN = re.compile(r"[A-Za-z0-9:._/-]{1,128}")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class TransportSettings(NamedTuple):
    transport: str
    host: str | None
    port: int | None


class StaticBearerTokenVerifier:
    """Verify one host-local bearer without logging or serializing it."""

    __slots__ = ("_client_id", "_expected", "_issuer", "_resource", "_scope")

    def __init__(
        self,
        token: str,
        *,
        issuer: str,
        resource: str,
        scope: str = AUTH_SCOPE,
        client_id: str = "aoa-loopback-codex",
    ) -> None:
        self._expected = token.encode("utf-8")
        self._issuer = issuer
        self._resource = resource
        self._scope = scope
        self._client_id = client_id

    async def verify_token(self, token: str) -> Any | None:
        from mcp.server.auth.provider import AccessToken  # type: ignore[import-not-found]

        if not hmac.compare_digest(self._expected, token.encode("utf-8")):
            return None
        return AccessToken(
            token=token,
            client_id=self._client_id,
            scopes=[self._scope],
            resource=self._resource,
            subject="local-operator",
            claims={"iss": self._issuer},
        )


def transport_settings(default_port: int) -> TransportSettings:
    transport = os.environ.get("AOA_MCP_TRANSPORT", "stdio").strip() or "stdio"
    if transport == "stdio":
        return TransportSettings(transport="stdio", host=None, port=None)
    if transport != "streamable-http":
        raise SystemExit(f"unsupported AOA_MCP_TRANSPORT: {transport}")

    host = os.environ.get("AOA_MCP_HOST", "127.0.0.1").strip()
    if host not in _LOOPBACK_HOSTS:
        raise SystemExit("AOA_MCP_HOST must remain loopback-only")

    raw_port = str(os.environ.get("AOA_MCP_PORT", default_port)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit("AOA_MCP_PORT must be an integer from 1 through 65535") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("AOA_MCP_PORT must be an integer from 1 through 65535")
    return TransportSettings(transport=transport, host=host, port=port)


def _credential_token(credential_name: str = CREDENTIAL_NAME) -> str | None:
    credential_dir = os.environ.get("CREDENTIALS_DIRECTORY", "").strip()
    if not credential_dir:
        return None
    credential_path = Path(credential_dir) / credential_name
    if not credential_path.exists() and not credential_path.is_symlink():
        return None
    if credential_path.is_symlink() or not credential_path.is_file():
        raise SystemExit("MCP HTTP bearer credential must be a regular non-symlink file")
    try:
        raw = credential_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SystemExit("unable to read the MCP HTTP bearer credential") from exc
    return raw.removesuffix("\n")


def _bearer_token(
    *,
    token_env_var: str = TOKEN_ENV_VAR,
    credential_name: str = CREDENTIAL_NAME,
) -> str:
    env_token = os.environ.get(token_env_var)
    credential_token = _credential_token(credential_name)
    for candidate in (env_token, credential_token):
        if candidate is not None and _TOKEN_PATTERN.fullmatch(candidate) is None:
            raise SystemExit("invalid bearer credential; require 43-512 URL-safe characters")
    if env_token is not None and credential_token is not None:
        if not hmac.compare_digest(env_token.encode("utf-8"), credential_token.encode("utf-8")):
            raise SystemExit("conflicting bearer credentials from environment and systemd")
    token = env_token if env_token is not None else credential_token
    if token is None:
        raise SystemExit(
            "streamable HTTP requires bearer authentication via "
            f"{token_env_var} or systemd credential {credential_name}"
        )
    return token


def _http_authority(host: str, port: int) -> str:
    rendered_host = f"[{host}]" if host == "::1" else host
    return f"http://{rendered_host}:{port}"


def _loopback_transport_security(port: int) -> Any:
    from mcp.server.transport_security import (  # type: ignore[import-not-found]
        TransportSecuritySettings,
    )

    authorities = [
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        f"[::1]:{port}",
    ]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=authorities,
        allowed_origins=[f"http://{authority}" for authority in authorities],
    )


def http_auth_kwargs(
    default_port: int,
    *,
    token_env_var: str = TOKEN_ENV_VAR,
    credential_name: str = CREDENTIAL_NAME,
    auth_scope: str = AUTH_SCOPE,
    client_id: str = "aoa-loopback-codex",
) -> dict[str, Any]:
    if _ENV_NAME_PATTERN.fullmatch(token_env_var) is None:
        raise SystemExit("invalid MCP bearer environment-variable name")
    if _CREDENTIAL_NAME_PATTERN.fullmatch(credential_name) is None:
        raise SystemExit("invalid MCP systemd credential name")
    if _SCOPE_PATTERN.fullmatch(auth_scope) is None:
        raise SystemExit("invalid MCP authorization scope")
    if not client_id or len(client_id) > 128:
        raise SystemExit("invalid MCP client identity")
    settings = transport_settings(default_port)
    if settings.transport == "stdio":
        return {}
    assert settings.host is not None
    assert settings.port is not None

    token = _bearer_token(
        token_env_var=token_env_var,
        credential_name=credential_name,
    )
    authority = _http_authority(settings.host, settings.port)
    issuer = f"{authority}/"
    resource = f"{authority}/mcp"

    from mcp.server.auth.settings import AuthSettings  # type: ignore[import-not-found]

    return {
        "auth": AuthSettings(
            issuer_url=issuer,
            required_scopes=[auth_scope],
            resource_server_url=resource,
        ),
        "token_verifier": StaticBearerTokenVerifier(
            token,
            issuer=issuer,
            resource=resource,
            scope=auth_scope,
            client_id=client_id,
        ),
        "transport_security": _loopback_transport_security(settings.port),
    }
