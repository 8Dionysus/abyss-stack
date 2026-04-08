from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


def _parse_bool(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _load_config_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {}
    return loaded


@dataclass(frozen=True)
class TosGraphSettings:
    service_name: str
    port: int
    config_path: Path
    tos_root: Path
    log_root: Path
    route_default: str
    write_enabled: bool
    neo4j_uri: str | None
    neo4j_user: str | None
    projection_mode: str


def load_settings() -> TosGraphSettings:
    config_path = Path(os.environ.get("TOS_GRAPH_CONFIG_PATH", "/app/config/config.yaml"))
    payload = _load_config_payload(config_path)
    service_cfg = payload.get("service") if isinstance(payload.get("service"), dict) else {}
    source_cfg = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    projection_cfg = payload.get("projection") if isinstance(payload.get("projection"), dict) else {}

    return TosGraphSettings(
        service_name=str(service_cfg.get("name", "tos-graph")),
        port=int(os.environ.get("TOS_GRAPH_PORT", service_cfg.get("port", 5410))),
        config_path=config_path,
        tos_root=Path(os.environ.get("TOS_GRAPH_TOS_ROOT", "/workspace/Tree-of-Sophia")),
        log_root=Path(os.environ.get("TOS_GRAPH_LOG_ROOT", "/app/logs")),
        route_default=str(
            os.environ.get(
                "TOS_GRAPH_ROUTE_DEFAULT",
                source_cfg.get("route_default", "friedrich-nietzsche/thus-spoke-zarathustra/prologue-1"),
            )
        ),
        write_enabled=_parse_bool(os.environ.get("TOS_GRAPH_WRITE_ENABLED"), False),
        neo4j_uri=os.environ.get("TOS_GRAPH_NEO4J_URI"),
        neo4j_user=os.environ.get("TOS_GRAPH_NEO4J_USER"),
        projection_mode=str(projection_cfg.get("mode", "preview_only")),
    )
