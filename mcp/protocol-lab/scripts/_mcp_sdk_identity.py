"""Fail-closed identity checks for the Python MCP SDK used by lab runners."""

from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
from importlib.metadata import PackageNotFoundError, distribution
import json
import subprocess
import urllib.parse
from pathlib import Path


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
PYTHON_MCP_VERSION = "2.1.1"
PYTHON_MCP_COMMIT = MCP_SDK_SOURCE_REVISIONS[PYTHON_MCP_VERSION]


def attested_mcp_sdk_source_revision(version: str) -> str:
    """Map an observed released SDK version to its reviewed source revision."""
    try:
        return MCP_SDK_SOURCE_REVISIONS[version]
    except KeyError as exc:
        raise RuntimeError(
            f"the observed MCP SDK version has no reviewed source attestation: {version}"
        ) from exc


def _git_head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _checkout_is_clean(root: Path) -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout


def _installed_package_root(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError(f"the installed {module_name} package location is unavailable")
    locations = [Path(item) for item in spec.submodule_search_locations]
    if len(locations) != 1:
        raise RuntimeError(f"the installed {module_name} package has ambiguous locations")
    package_root = locations[0]
    if package_root.is_symlink():
        raise RuntimeError(f"the installed {module_name} package root is a symlink")
    package_root = package_root.resolve()
    if not package_root.is_dir():
        raise RuntimeError(f"the installed {module_name} package root is not a directory")
    return package_root


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_package_digest(package_root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(package_root.rglob("*")):
        if "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise RuntimeError(f"the MCP SDK package contains a symlink: {path}")
        if not path.is_file():
            continue
        digest.update(path.relative_to(package_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _editable_mcp_source_digest(
    distribution_metadata: object,
    package_root: Path,
    source_revision: str,
) -> str | None:
    read_text = getattr(distribution_metadata, "read_text")
    raw_direct_url = read_text("direct_url.json")
    if raw_direct_url is None:
        return None
    try:
        direct_url = json.loads(raw_direct_url)
    except json.JSONDecodeError as exc:
        raise RuntimeError("the editable MCP SDK direct_url metadata is invalid") from exc
    if not isinstance(direct_url, dict):
        raise RuntimeError("the editable MCP SDK direct_url metadata is not an object")
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
        raise RuntimeError("the imported MCP SDK package is outside its editable checkout")
    if not _checkout_is_clean(source_root):
        raise RuntimeError("the editable MCP SDK source checkout is dirty")
    actual_revision = _git_head(source_root)
    if actual_revision != source_revision:
        raise RuntimeError(
            "the editable MCP SDK source checkout does not match its reviewed revision: "
            f"{actual_revision}"
        )
    return _source_package_digest(package_root)


def _distribution_record_digest(
    distribution_metadata: object,
    *,
    distribution_name: str,
    sdk_version: str,
) -> str:
    read_text = getattr(distribution_metadata, "read_text")
    raw_record = read_text("RECORD")
    if raw_record is None:
        raise RuntimeError(f"the {distribution_name} distribution omitted RECORD")
    metadata_path = Path(getattr(distribution_metadata, "_path"))
    distribution_info = metadata_path.name
    site_packages = metadata_path.parent.resolve()
    package_prefix = "mcp/" if distribution_name == "mcp" else "mcp_types/"
    canonical_rows: list[tuple[str, str, str]] = []
    try:
        rows = csv.reader(io.StringIO(raw_record, newline=""))
        for row in rows:
            if len(row) != 3:
                raise RuntimeError(f"the {distribution_name} RECORD contains an invalid row")
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
                raise RuntimeError(f"the {distribution_name} RECORD contains an unsafe path: {relative_name}")
            if "__pycache__" in path_parts:
                continue
            if relative_name in {
                f"{distribution_info}/INSTALLER",
                f"{distribution_info}/REQUESTED",
            }:
                continue
            if relative_name == f"{distribution_info}/RECORD":
                if encoded_digest or recorded_size:
                    raise RuntimeError(f"the {distribution_name} RECORD row must be self-unsigned")
                canonical_rows.append((relative_name, "", ""))
                continue
            if not encoded_digest.startswith("sha256=") or not recorded_size.isdigit():
                raise RuntimeError(f"the {distribution_name} RECORD has an invalid file attestation")
            target = Path(getattr(distribution_metadata, "locate_file")(Path(relative_name)))
            if target.is_symlink() or not target.is_file():
                raise RuntimeError(f"the {distribution_name} RECORD target is not a regular file: {relative_name}")
            resolved_target = target.resolve()
            if not _is_under(resolved_target, site_packages):
                raise RuntimeError(f"the {distribution_name} RECORD target escapes site-packages: {relative_name}")
            if resolved_target.stat().st_size != int(recorded_size):
                raise RuntimeError(f"the {distribution_name} RECORD size does not match: {relative_name}")
            actual_digest = base64.urlsafe_b64encode(
                bytes.fromhex(_sha256_file(resolved_target))
            ).decode("ascii").rstrip("=")
            if encoded_digest != f"sha256={actual_digest}":
                raise RuntimeError(f"the {distribution_name} RECORD digest does not match: {relative_name}")
            canonical_rows.append((relative_name, encoded_digest, recorded_size))
    except csv.Error as exc:
        raise RuntimeError(f"the {distribution_name} RECORD is not valid CSV") from exc
    if not canonical_rows:
        raise RuntimeError(f"the {distribution_name} RECORD is empty")
    canonical_payload = "\n".join(
        ",".join(row) for row in sorted(canonical_rows)
    ).encode("utf-8")
    actual_record_digest = f"sha256:{hashlib.sha256(canonical_payload).hexdigest()}"
    expected_record_digest = MCP_SDK_DISTRIBUTION_RECORD_DIGESTS[sdk_version][distribution_name]
    if actual_record_digest != expected_record_digest:
        raise RuntimeError(
            f"the {distribution_name} distribution bytes are not the reviewed "
            f"{sdk_version} artifact: {actual_record_digest}"
        )
    return actual_record_digest


def installed_mcp_identity(sdk_root: Path) -> dict[str, str]:
    """Return the installed identity only when it is tied to a clean SDK checkout.

    The runner must be executed by an environment whose imported ``mcp`` package
    lives inside the supplied checkout (a regular or editable installation).  A
    matching version in an unrelated cache or a locally patched package is not
    sufficient evidence for a protocol receipt.
    """

    root = sdk_root.resolve(strict=True)
    if not _checkout_is_clean(root):
        raise RuntimeError("the attested Python MCP SDK checkout is dirty")
    source_revision = _git_head(root)
    if source_revision != PYTHON_MCP_COMMIT:
        raise RuntimeError(
            "the attested Python MCP SDK checkout does not match v2.1.1: "
            f"{source_revision}"
        )

    try:
        installed_version = distribution("mcp").version
    except PackageNotFoundError as exc:
        raise RuntimeError("the installed Python MCP SDK distribution is unavailable") from exc
    if installed_version != PYTHON_MCP_VERSION:
        raise RuntimeError(
            "the installed Python MCP SDK does not match v2.1.1: "
            f"{installed_version}"
        )

    package_root = _installed_package_root("mcp")
    if not _is_under(package_root, root):
        raise RuntimeError(
            "the imported Python MCP package is not loaded from the attested "
            f"checkout: {package_root}"
        )
    try:
        mcp_types_distribution = distribution("mcp-types")
    except PackageNotFoundError as exc:
        raise RuntimeError("the installed MCP SDK wire-types distribution is unavailable") from exc
    if mcp_types_distribution.version != PYTHON_MCP_VERSION:
        raise RuntimeError(
            "the installed MCP SDK wire-types distribution does not match v2.1.1: "
            f"{mcp_types_distribution.version}"
        )
    mcp_types_package_root = _installed_package_root("mcp_types")
    mcp_types_site_packages = Path(
        getattr(mcp_types_distribution, "_path")
    ).parent.resolve()
    if not _is_under(mcp_types_package_root, mcp_types_site_packages):
        raise RuntimeError(
            "the imported MCP SDK wire-types package is not loaded from its "
            f"attested distribution: {mcp_types_package_root}"
        )
    mcp_digest = _editable_mcp_source_digest(
        distribution("mcp"),
        package_root,
        source_revision,
    ) or _distribution_record_digest(
        distribution("mcp"),
        distribution_name="mcp",
        sdk_version=installed_version,
    )
    mcp_types_digest = _distribution_record_digest(
        mcp_types_distribution,
        distribution_name="mcp-types",
        sdk_version=installed_version,
    )
    combined = (
        f"mcp:{installed_version}:{mcp_digest}\n"
        f"mcp-types:{installed_version}:{mcp_types_digest}\n"
    ).encode("utf-8")
    return {
        "version": installed_version,
        "commit": source_revision,
        "artifact_digest": f"sha256:{hashlib.sha256(combined).hexdigest()}",
    }
