from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "aoa_machine_fit.py"


def load_module():
    spec = importlib.util.spec_from_file_location("aoa_machine_fit_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_preset(root: Path, name: str, profiles: list[str]) -> None:
    preset_path = root / "compose" / "presets" / f"{name}.txt"
    preset_path.parent.mkdir(parents=True)
    preset_path.write_text("\n".join(profiles) + "\n", encoding="utf-8")


def test_load_profile_names_prefers_source_checkout_over_stale_deployed_configs(tmp_path) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    deployed_configs = tmp_path / "deployed-configs"
    write_preset(source_root, "intel-full", ["substrate", "intel-worker", "tools", "observability"])
    write_preset(deployed_configs, "intel-full", ["intel", "tools", "observability"])

    module.SCRIPT_ROOT = source_root
    module.DEFAULT_CONFIGS_ROOT = deployed_configs

    assert module.load_profile_names("intel-full") == [
        "substrate",
        "intel-worker",
        "tools",
        "observability",
    ]


def test_load_profile_names_falls_back_to_deployed_configs_when_source_preset_is_absent(
    tmp_path,
) -> None:
    module = load_module()
    source_root = tmp_path / "source"
    deployed_configs = tmp_path / "deployed-configs"
    source_root.mkdir()
    write_preset(deployed_configs, "agent-full", ["agentic", "tools", "observability"])

    module.SCRIPT_ROOT = source_root
    module.DEFAULT_CONFIGS_ROOT = deployed_configs

    assert module.load_profile_names("agent-full") == ["agentic", "tools", "observability"]
