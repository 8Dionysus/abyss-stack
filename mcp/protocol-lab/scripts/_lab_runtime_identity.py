"""Resolve a lab input to either explicit development source or verified deployment."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from _mcp_sdk_identity import installed_mcp_identity, installed_mcp_runtime_identity
from runtime_catalog import load_runtime_catalog, mcp_settings


def sdk_identity(args):
    if args.installed_runtime:
        if args.python_sdk_root is not None:
            raise ValueError("installed runtime cannot be combined with a source SDK")
        identity = installed_mcp_runtime_identity()
        settings, _, _ = mcp_settings(load_runtime_catalog())
        if (identity["version"], identity["commit"]) != (
            settings["tested_lock"], settings["source_revision"]
        ):
            raise ValueError("installed SDK differs from the runtime catalog")
        return identity
    if args.python_sdk_root is None:
        raise ValueError("development mode requires --python-sdk-root")
    return installed_mcp_identity(args.python_sdk_root)


def stack_revision(args):
    if not args.installed_runtime:
        if args.stack_source_root is None:
            raise ValueError("development mode requires --stack-source-root")
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=args.stack_source_root, text=True
        ).strip()
    if args.stack_source_root is not None:
        raise ValueError("installed runtime cannot be combined with stack source")
    root = args.stack_runtime_root.resolve(strict=True)
    verifier = root / "Configs/mechanics/config-projection/parts/sync/scripts/mcp_deployment_manifest.py"
    spec = importlib.util.spec_from_file_location("_lab_deployment_manifest", verifier)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    payload = json.loads((root / "Logs/mcp/deployments/latest.json").read_text())
    module.verify_manifest_id(payload)
    # Check the package actually imported, using the owner's existing tree contract.
    row = next(x for x in payload["services"] if x["service_id"] == "aoa-kag-mcp")
    package = root / "Configs/mcp/services/aoa-kag-mcp"
    if row["deployed_path"] != "Configs/mcp/services/aoa-kag-mcp":
        raise ValueError("unexpected deployed KAG path")
    if module.tree_identity(package).as_dict() != row["deployed_tree"]:
        raise ValueError("deployed KAG package differs from its deployment receipt")
    import aoa_kag_mcp.core
    if Path(aoa_kag_mcp.core.__file__).resolve().parent != package / "src/aoa_kag_mcp":
        raise ValueError("imported KAG package is not the verified deployment")
    return row["package_source_revision"]
