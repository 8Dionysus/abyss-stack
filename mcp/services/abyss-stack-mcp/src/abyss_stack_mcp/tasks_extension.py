"""Production-bounded MCP Tasks extension for stack read diagnostics.

The extension creates durable, principal-bound task handles and runs only the
existing read-only ``StackMCPApplication.inspect`` route.  A task identifier is
never authorization, admission, or effect authority.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
import secrets
import subprocess
import urllib.parse
from collections.abc import Mapping, Sequence
from importlib.metadata import PackageNotFoundError, distribution, version
from pathlib import Path
from typing import Any, Literal

from aoa_sdk.organs import (
    FileTaskStore,
    MCPTaskRequestContext,
    MCPTasksAdapter,
    MCPTasksAdapterError,
)
from aoa_sdk.organs.registry import canonical_json_bytes, sha256_digest
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, ServerRequestContext
from mcp.server.extension import Extension, MethodBinding, ToolBinding
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolRequestParams, RequestParams, ToolAnnotations
from pydantic import ConfigDict, Field

from .core import StackMCPApplication


TASKS_EXTENSION_ID = "io.modelcontextprotocol/tasks"
TASKS_PROTOCOL_VERSION = "2026-07-28"
TASK_TOOL = "stack_runtime_inspect_task"
DEFAULT_TASK_ROOT = Path(
    "/srv/AbyssOS/abyss-stack/Logs/mcp/tasks/abyss-stack-read"
)
MCP_SDK_SOURCE_REVISIONS = {
    "2.0.0": "6f69a3758ebf2ee55ce050f58b470ce11af71133",
    "2.1.1": "0921d94a74db900dccd2d534842aa7b6160542d2",
}
MCP_SDK_DISTRIBUTION_RECORD_DIGESTS = {
    "2.0.0": {
        "mcp": "sha256:8628cb26882a3728c4414b445901e7b758bd9674ff879ff13e35e9fc5392250b",
        "mcp-types": "sha256:5c74bc79a98b5e207c23b65ce211d9c450b207e4347bf8302d78f82da3528f95",
    },
    "2.1.1": {
        "mcp": "sha256:8023abb83ccd24e167d5ad39a5296ce87040c52972f714b3576fcb8ce1b28a14",
        "mcp-types": "sha256:d315ab265f62420dc87baadbb9373013330833aeced8950d9951f8b9d71eee0c",
    },
}


class _TaskGetParams(RequestParams):
    model_config = ConfigDict(populate_by_name=True)
    task_id: str = Field(alias="taskId", min_length=43, max_length=128)


class _TaskUpdateParams(_TaskGetParams):
    input_responses: dict[str, Any] = Field(alias="inputResponses")


class _TaskPayloadStore:
    """Private content-addressed payload store used by the durable handles."""

    def __init__(self, root: Path) -> None:
        self.root = root / "payloads"
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or not self.root.is_dir():
            raise RuntimeError("MCP task payload root must be a non-symlink directory")
        self.root.chmod(0o700)

    def put(self, payload: Mapping[str, Any]) -> tuple[str, str]:
        value = dict(payload)
        digest = sha256_digest(value)
        identity = digest.removeprefix("sha256:")
        path = self.root / f"{identity}.json"
        if path.is_symlink():
            raise RuntimeError("MCP task payload path must not be a symlink")
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if not path.exists():
            temporary = self.root / (
                f".{identity}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
            )
            fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            try:
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(temporary, path)
            path.chmod(0o600)
        return f"owner://abyss-stack/mcp-task-payload/{identity}", digest

    def _read(self, ref: str) -> dict[str, Any]:
        prefix = "owner://abyss-stack/mcp-task-payload/"
        if not ref.startswith(prefix):
            raise KeyError(ref)
        identity = ref.removeprefix(prefix)
        if len(identity) != 64 or any(char not in "0123456789abcdef" for char in identity):
            raise KeyError(ref)
        path = self.root / f"{identity}.json"
        if path.is_symlink() or not path.is_file():
            raise KeyError(ref)
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or sha256_digest(value) != f"sha256:{identity}":
            raise KeyError(ref)
        return value

    def resolve_result(self, record: Any) -> Mapping[str, Any]:
        return self._read(record.result_ref)

    def resolve_error(self, record: Any) -> Mapping[str, Any]:
        return self._read(record.error_ref)

    def resolve_input_request(self, record: Any, request: Any) -> Mapping[str, Any]:
        raise KeyError((record.task_id, request.request_key))


def tasks_enabled_from_environment() -> bool:
    value = os.environ.get("ABYSS_STACK_MCP_TASKS_ENABLED", "").strip()
    if value not in {"", "0", "1"}:
        raise SystemExit("ABYSS_STACK_MCP_TASKS_ENABLED must be 0 or 1")
    return value == "1"


def task_root_from_environment() -> Path:
    return Path(os.environ.get("ABYSS_STACK_MCP_TASK_ROOT", str(DEFAULT_TASK_ROOT)))


def running_mcp_sdk_version() -> str:
    """Read the installed SDK version from the process serving the task."""
    try:
        return version("mcp")
    except PackageNotFoundError as exc:
        raise RuntimeError("the serving MCP SDK package is not installed") from exc


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _installed_mcp_package_root() -> Path:
    spec = importlib.util.find_spec("mcp")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError("the serving MCP SDK package location is unavailable")
    locations = [Path(item).resolve() for item in spec.submodule_search_locations]
    if len(locations) != 1:
        raise RuntimeError("the serving MCP SDK package has ambiguous locations")
    package_root = locations[0]
    if not package_root.is_dir() or package_root.is_symlink():
        raise RuntimeError("the serving MCP SDK package root is not a regular directory")
    return package_root


def _git_output(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"unable to attest the MCP SDK checkout at {root}") from exc


def _checkout_is_clean(root: Path) -> bool:
    return not _git_output(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise RuntimeError(f"unable to read attested MCP SDK file: {path}") from exc
    return digest.hexdigest()


def _source_package_digest(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise RuntimeError(f"the serving MCP SDK package contains a symlink: {path}")
        if not path.is_file():
            continue
        digest.update(path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise RuntimeError(f"unable to read attested MCP SDK file: {path}") from exc
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _editable_mcp_source_digest(
    distribution_metadata: Any,
    package_root: Path,
    source_revision: str,
) -> str | None:
    raw_direct_url = distribution_metadata.read_text("direct_url.json")
    if raw_direct_url is None:
        return None
    try:
        direct_url = json.loads(raw_direct_url)
    except json.JSONDecodeError as exc:
        raise RuntimeError("the serving MCP SDK direct_url metadata is invalid") from exc
    if not isinstance(direct_url, dict):
        raise RuntimeError("the serving MCP SDK direct_url metadata is not an object")
    directory_info = direct_url.get("dir_info")
    if not isinstance(directory_info, dict) or not directory_info.get("editable"):
        return None
    raw_url = direct_url.get("url")
    if not isinstance(raw_url, str):
        raise RuntimeError("the editable MCP SDK direct_url metadata omitted its URL")
    parsed_url = urllib.parse.urlparse(raw_url)
    if parsed_url.scheme != "file" or parsed_url.netloc not in {"", "localhost"}:
        raise RuntimeError("the editable MCP SDK must use a local file URL")
    source_root = Path(urllib.parse.unquote(parsed_url.path)).resolve()
    if not source_root.is_dir() or source_root.is_symlink():
        raise RuntimeError("the editable MCP SDK source checkout is unavailable")
    if not _is_under(package_root, source_root):
        raise RuntimeError(
            "the imported MCP SDK package is not inside its attested source checkout"
        )
    if not _checkout_is_clean(source_root):
        raise RuntimeError("the editable MCP SDK source checkout is dirty")
    actual_revision = _git_output(source_root, "rev-parse", "HEAD")
    if actual_revision != source_revision:
        raise RuntimeError(
            "the editable MCP SDK source checkout does not match its reviewed revision: "
            f"{actual_revision}"
        )
    return _source_package_digest(package_root)


def _distribution_record_digest(
    distribution_metadata: Any,
    *,
    distribution_name: str,
    sdk_version: str,
) -> str:
    raw_record = distribution_metadata.read_text("RECORD")
    if raw_record is None:
        raise RuntimeError(f"the serving {distribution_name} distribution omitted RECORD")
    distribution_info = Path(distribution_metadata._path).name
    site_packages = Path(distribution_metadata._path).parent.resolve()
    package_prefix = "mcp/" if distribution_name == "mcp" else "mcp_types/"
    canonical_rows: list[tuple[str, str, str]] = []
    try:
        rows = csv.reader(io.StringIO(raw_record, newline=""))
        for row in rows:
            if len(row) != 3:
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD contains an invalid row"
                )
            relative_name, encoded_digest, recorded_size = row
            path_parts = relative_name.split("/")
            if distribution_name == "mcp" and relative_name == "../../../bin/mcp":
                continue
            if (
                not relative_name
                or "\\" in relative_name
                or relative_name.startswith("/")
                or "//" in relative_name
                or relative_name.startswith("../")
                or "/../" in relative_name
                or not (
                    relative_name.startswith(package_prefix)
                    or relative_name.startswith(f"{distribution_info}/")
                )
            ):
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD contains an unsafe path: "
                    f"{relative_name}"
                )
            if "__pycache__" in path_parts:
                continue
            if relative_name in {
                f"{distribution_info}/INSTALLER",
                f"{distribution_info}/REQUESTED",
            }:
                continue
            if relative_name == f"{distribution_info}/RECORD":
                if encoded_digest or recorded_size:
                    raise RuntimeError(
                        f"the serving {distribution_name} RECORD row must be self-unsigned"
                    )
                canonical_rows.append((relative_name, "", ""))
                continue
            if not encoded_digest.startswith("sha256=") or not recorded_size.isdigit():
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD has an invalid file attestation"
                )
            target = Path(distribution_metadata.locate_file(Path(relative_name)))
            if target.is_symlink() or not target.is_file():
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD target is not a regular file: "
                    f"{relative_name}"
                )
            resolved_target = target.resolve()
            if not _is_under(resolved_target, site_packages):
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD target escapes site-packages: "
                    f"{relative_name}"
                )
            if resolved_target.stat().st_size != int(recorded_size):
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD size does not match: "
                    f"{relative_name}"
                )
            actual_digest = base64.urlsafe_b64encode(
                bytes.fromhex(_sha256_file(resolved_target))
            ).decode("ascii").rstrip("=")
            if encoded_digest != f"sha256={actual_digest}":
                raise RuntimeError(
                    f"the serving {distribution_name} RECORD digest does not match: "
                    f"{relative_name}"
                )
            canonical_rows.append((relative_name, encoded_digest, recorded_size))
    except csv.Error as exc:
        raise RuntimeError(f"the serving {distribution_name} RECORD is not valid CSV") from exc
    if not canonical_rows:
        raise RuntimeError(f"the serving {distribution_name} RECORD is empty")
    canonical_payload = "\n".join(
        ",".join(row) for row in sorted(canonical_rows)
    ).encode("utf-8")
    actual_record_digest = f"sha256:{hashlib.sha256(canonical_payload).hexdigest()}"
    expected_record_digest = MCP_SDK_DISTRIBUTION_RECORD_DIGESTS[sdk_version][
        distribution_name
    ]
    if actual_record_digest != expected_record_digest:
        raise RuntimeError(
            f"the serving {distribution_name} distribution bytes are not the reviewed "
            f"{sdk_version} artifact: {actual_record_digest}"
        )
    return actual_record_digest


def _installed_mcp_sdk_artifact_digest(
    sdk_version: str,
    source_revision: str,
) -> str:
    try:
        mcp_distribution = distribution("mcp")
        mcp_types_distribution = distribution("mcp-types")
    except PackageNotFoundError as exc:
        raise RuntimeError("the serving MCP SDK dependency distributions are incomplete") from exc
    if mcp_distribution.version != sdk_version:
        raise RuntimeError(
            "the serving MCP SDK distribution version does not match its identity: "
            f"{mcp_distribution.version}"
        )
    if mcp_types_distribution.version != sdk_version:
        raise RuntimeError(
            "the serving MCP wire-types distribution version does not match its SDK: "
            f"{mcp_types_distribution.version}"
        )
    package_root = _installed_mcp_package_root()
    mcp_source_digest = _editable_mcp_source_digest(
        mcp_distribution,
        package_root,
        source_revision,
    )
    mcp_digest = mcp_source_digest or _distribution_record_digest(
        mcp_distribution,
        distribution_name="mcp",
        sdk_version=sdk_version,
    )
    mcp_types_digest = _distribution_record_digest(
        mcp_types_distribution,
        distribution_name="mcp-types",
        sdk_version=sdk_version,
    )
    combined = (
        f"mcp:{sdk_version}:{mcp_digest}\n"
        f"mcp-types:{sdk_version}:{mcp_types_digest}\n"
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(combined).hexdigest()}"


def running_mcp_sdk_identity() -> tuple[str, str, str]:
    """Return SDK identity only after its source and installed bytes are attested."""
    sdk_version = running_mcp_sdk_version()
    try:
        source_revision = MCP_SDK_SOURCE_REVISIONS[sdk_version]
    except KeyError as exc:
        raise RuntimeError(
            "the serving MCP SDK version has no reviewed source attestation: "
            f"{sdk_version}"
        ) from exc
    artifact_digest = _installed_mcp_sdk_artifact_digest(sdk_version, source_revision)
    return sdk_version, source_revision, artifact_digest


class StackReadTasksExtension(Extension):
    """Opt-in task surface for one existing stack read operation."""

    identifier = TASKS_EXTENSION_ID

    def __init__(self, application: StackMCPApplication, root: Path) -> None:
        self.application = application
        self.payloads = _TaskPayloadStore(root)
        self.store = FileTaskStore(root / "store")
        self._workers: dict[str, asyncio.Task[None]] = {}
        self.adapter = MCPTasksAdapter(
            self.store,
            self.payloads,
            enabled=True,
            cancel_sink=self._cancel,
            enforce_poll_interval=True,
        )

    def settings(self) -> dict[str, Any]:
        return {"taskTools": [TASK_TOOL]}

    def tools(self) -> Sequence[ToolBinding]:
        def stack_runtime_inspect_task(
            organ_id: str,
            policy_family: Literal["read"] = "read",
            view: Literal[
                "identity",
                "parity",
                "process",
                "endpoint",
                "registry",
                "consumer",
                "schema",
                "freshness",
                "proof",
                "acceptance",
                "canary",
                "rollback",
                "drift",
                "full",
            ] = "full",
            idempotency_key: str | None = None,
        ) -> dict[str, Any]:
            """Run one durable, cancellable stack read inspection task."""

            raise RuntimeError("Tasks-aware tools/call interceptor was bypassed")

        annotations = ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        )
        return (
            ToolBinding(
                fn=stack_runtime_inspect_task,
                kwargs={
                    "name": TASK_TOOL,
                    "annotations": annotations,
                    "structured_output": True,
                },
            ),
        )

    def methods(self) -> Sequence[MethodBinding]:
        versions = frozenset({TASKS_PROTOCOL_VERSION})
        return (
            MethodBinding("tasks/get", _TaskGetParams, self._get, versions),
            MethodBinding("tasks/update", _TaskUpdateParams, self._update, versions),
            MethodBinding("tasks/cancel", _TaskGetParams, self._cancel_request, versions),
        )

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> Any:
        if params.name != TASK_TOOL:
            return await call_next(ctx)
        arguments = dict(params.arguments or {})
        domain_arguments = {
            "organ_id": arguments.get("organ_id"),
            "policy_family": arguments.get("policy_family", "read"),
            "view": arguments.get("view", "full"),
        }
        if not isinstance(domain_arguments["organ_id"], str):
            raise MCPError(code=-32602, message="organ_id is required")
        supplied_key = arguments.get("idempotency_key")
        if supplied_key is not None and not isinstance(supplied_key, str):
            raise MCPError(code=-32602, message="idempotency_key must be a string")
        context = self._context(ctx)
        digest = hashlib.sha256(
            canonical_json_bytes(
                {
                    "principal": context.principal_id,
                    "arguments": domain_arguments,
                    "idempotency_key": supplied_key,
                }
            )
        ).hexdigest()
        try:
            created = self.adapter.create_task_result(
                context,
                tool_name=TASK_TOOL,
                arguments=domain_arguments,
                owner_run_ref=f"owner://abyss-stack/mcp-read-task/{digest}",
                idempotency_key=f"mcp-{digest}",
                ttl_seconds=900,
                poll_interval_ms=250,
                task_support="required",
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc
        assert created is not None
        task_id = created["taskId"]
        record = self.store.get(
            task_id,
            principal_id=context.principal_id,
            organ_id=context.organ_id,
            contour_id=context.contour_id,
        )
        if record.status == "working" and task_id not in self._workers:
            self._workers[task_id] = asyncio.create_task(
                self._execute(context, task_id, domain_arguments)
            )
        return created

    async def _get(self, ctx: ServerRequestContext[Any, Any], params: _TaskGetParams) -> Any:
        try:
            return self.adapter.get_task(self._context(ctx), task_id=params.task_id)
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _update(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: _TaskUpdateParams,
    ) -> Any:
        try:
            return self.adapter.update_task(
                self._context(ctx),
                task_id=params.task_id,
                input_responses=params.input_responses,
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _cancel_request(
        self,
        ctx: ServerRequestContext[Any, Any],
        params: _TaskGetParams,
    ) -> Any:
        try:
            return self.adapter.cancel_task(
                self._context(ctx),
                task_id=params.task_id,
            )
        except MCPTasksAdapterError as exc:
            raise self._mcp_error(exc) from exc

    async def _execute(
        self,
        context: MCPTaskRequestContext,
        task_id: str,
        arguments: dict[str, Any],
    ) -> None:
        try:
            (
                mcp_sdk,
                mcp_sdk_source_revision,
                mcp_sdk_artifact_digest,
            ) = running_mcp_sdk_identity()
            owner_payload = await asyncio.to_thread(self.application.inspect, **arguments)
            metadata = owner_payload.get("metadata")
            if not isinstance(metadata, dict):
                raise RuntimeError("owner inspection omitted result metadata")
            owner_payload = {
                **owner_payload,
                "metadata": {
                    **metadata,
                    "mcp_sdk": mcp_sdk,
                    "mcp_sdk_source_revision": mcp_sdk_source_revision,
                    "mcp_sdk_artifact_digest": mcp_sdk_artifact_digest,
                },
            }
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(owner_payload, ensure_ascii=False, sort_keys=True),
                    }
                ],
                "structuredContent": owner_payload,
                "isError": False,
            }
            ref, digest = self.payloads.put(result)
            record = self.store.get(
                task_id,
                principal_id=context.principal_id,
                organ_id=context.organ_id,
                contour_id=context.contour_id,
            )
            if record.status != "working":
                return
            self.store.complete(
                task_id,
                principal_id=context.principal_id,
                organ_id=context.organ_id,
                contour_id=context.contour_id,
                expected_revision=record.revision,
                result_ref=ref,
                result_digest=digest,
                evidence_refs=("owner://abyss-stack/runtime-observation",),
            )
        except asyncio.CancelledError:
            return
        except Exception:
            error = {"code": -32603, "message": "Owner read task execution failed"}
            ref, digest = self.payloads.put(error)
            try:
                record = self.store.get(
                    task_id,
                    principal_id=context.principal_id,
                    organ_id=context.organ_id,
                    contour_id=context.contour_id,
                )
                if record.status == "working":
                    self.store.fail(
                        task_id,
                        principal_id=context.principal_id,
                        organ_id=context.organ_id,
                        contour_id=context.contour_id,
                        expected_revision=record.revision,
                        error_ref=ref,
                        error_digest=digest,
                    )
            except Exception:
                return
        finally:
            self._workers.pop(task_id, None)

    def _cancel(self, record: Any) -> None:
        worker = self._workers.get(record.task_id)
        if worker is not None:
            worker.cancel()
        current = self.store.get(
            record.task_id,
            principal_id=record.principal_id,
            organ_id=record.organ_id,
            contour_id=record.contour_id,
        )
        if current.cancellation_outcome == "pending":
            self.store.acknowledge_cancel(
                record.task_id,
                principal_id=record.principal_id,
                organ_id=record.organ_id,
                contour_id=record.contour_id,
                expected_revision=current.revision,
                accepted=True,
            )

    @staticmethod
    def _context(ctx: ServerRequestContext[Any, Any]) -> MCPTaskRequestContext:
        token = get_access_token()
        principal = token.client_id if token is not None else "local-os-stdio"
        capabilities = ctx.session.client_capabilities
        capability_payload = (
            capabilities.model_dump(by_alias=True, mode="json", exclude_none=True)
            if capabilities is not None
            else {}
        )
        request = ctx.request
        request_headers = getattr(request, "headers", {}) if request is not None else {}
        return MCPTaskRequestContext(
            principal_id=principal,
            organ_id="abyss-stack",
            contour_id="read",
            protocol_version=ctx.protocol_version,
            client_capabilities=capability_payload,
            transport="streamable_http" if request is not None else "stdio",
            headers=dict(request_headers),
        )

    @staticmethod
    def _mcp_error(error: MCPTasksAdapterError) -> MCPError:
        return MCPError(code=error.code, message=error.message, data=error.data)
