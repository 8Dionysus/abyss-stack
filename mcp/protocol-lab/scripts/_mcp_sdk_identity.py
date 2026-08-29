"""Fail-closed identity checks for the Python MCP SDK used by lab runners."""

from __future__ import annotations

import importlib.util
from importlib.metadata import PackageNotFoundError, distribution
import subprocess
from pathlib import Path


MCP_SDK_SOURCE_REVISIONS = {
    "2.0.0": "6f69a3758ebf2ee55ce050f58b470ce11af71133",
    "2.1.1": "0921d94a74db900dccd2d534842aa7b6160542d2",
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


def _installed_package_root() -> Path:
    spec = importlib.util.find_spec("mcp")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError("the installed MCP package location is unavailable")
    locations = [Path(item).resolve() for item in spec.submodule_search_locations]
    if len(locations) != 1:
        raise RuntimeError("the installed MCP package has ambiguous locations")
    return locations[0]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


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

    package_root = _installed_package_root()
    if not _is_under(package_root, root):
        raise RuntimeError(
            "the imported Python MCP package is not loaded from the attested "
            f"checkout: {package_root}"
        )
    return {"version": installed_version, "commit": source_revision}
