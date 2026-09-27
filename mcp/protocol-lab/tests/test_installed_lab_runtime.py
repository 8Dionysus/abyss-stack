"""The watcher must bind its verdict to the runtime it actually exercised."""
import sys
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
identity = importlib.import_module("_lab_runtime_identity")
sdk_identity = identity.sdk_identity
stack_revision = identity.stack_revision
require_same_sdk = importlib.import_module("normalize_protocol_watch_run").require_same_sdk


def test_installed_sdk_rejects_old_catalog_version(monkeypatch):
    monkeypatch.setattr(identity, "installed_mcp_runtime_identity", lambda: {"version": "2.0.0", "commit": "old"})
    monkeypatch.setattr(identity, "load_runtime_catalog", lambda: {})
    monkeypatch.setattr(identity, "mcp_settings", lambda _: ({"tested_lock": "2.1.1", "source_revision": "new"}, {}, {}))
    with pytest.raises(ValueError, match="differs from"):
        sdk_identity(SimpleNamespace(installed_runtime=True, python_sdk_root=None))


def test_installed_mode_rejects_source_override():
    with pytest.raises(ValueError, match="combined"):
        sdk_identity(SimpleNamespace(installed_runtime=True, python_sdk_root=Path("old")))
    with pytest.raises(ValueError, match="combined"):
        stack_revision(SimpleNamespace(installed_runtime=True, stack_source_root=Path("old")))


def test_mixed_sdk_receipts_cannot_pass():
    sdk = {"version": "2.1.1", "commit": "new", "artifact_digest": "sha256:one"}
    row = dict(zip(("python_mcp_version", "python_mcp_commit", "python_mcp_artifact_digest"), sdk.values()))
    pair = {"exact_inputs": row}
    require_same_sdk({"python_sdk": sdk}, pair, pair, pair, {"server": row})
    for key in sdk:
        wrong = dict(sdk, **{key: "different"})
        with pytest.raises(ValueError, match="different SDK"):
            require_same_sdk({"python_sdk": wrong}, pair, pair, pair, {"server": row})
    with pytest.raises(ValueError, match="incomplete"):
        require_same_sdk({"python_sdk": {}}, pair, pair, pair, {"server": row})
