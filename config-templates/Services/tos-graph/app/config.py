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


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    loaded: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        loaded[key.strip()] = value.strip()
    return loaded


def _split_neo4j_auth(raw: str | None) -> tuple[str | None, str | None]:
    if not raw or "/" not in raw:
        return None, None
    user, password = raw.split("/", 1)
    user = user.strip() or None
    password = password.strip() or None
    return user, password


@dataclass(frozen=True)
class TosGraphSettings:
    service_name: str
    port: int
    config_path: Path
    stack_env_path: Path
    tos_root: Path
    log_root: Path
    corpus_index_path: Path
    philosophy_atlas_projection_path: Path
    philosophy_graph_views_path: Path
    philosophy_graph_projection_path: Path
    material_planting_projection_path: Path
    philosophy_post_planting_audit_path: Path
    default_view: str
    default_philosophy_view: str
    write_enabled: bool
    neo4j_uri: str | None
    neo4j_user: str | None
    neo4j_password: str | None
    neo4j_database: str
    projection_mode: str


def load_settings() -> TosGraphSettings:
    config_path = Path(os.environ.get("TOS_GRAPH_CONFIG_PATH", "/app/config/config.yaml"))
    stack_env_path = Path(os.environ.get("TOS_GRAPH_STACK_ENV_PATH", "/app/config/runtime-stack.env"))
    payload = _load_config_payload(config_path)
    runtime_env_payload = _load_env_file(stack_env_path)
    service_cfg = payload.get("service") if isinstance(payload.get("service"), dict) else {}
    source_cfg = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    projection_cfg = payload.get("projection") if isinstance(payload.get("projection"), dict) else {}
    ui_cfg = payload.get("ui") if isinstance(payload.get("ui"), dict) else {}
    fallback_user, fallback_password = _split_neo4j_auth(
        os.environ.get("NEO4J_AUTH") or runtime_env_payload.get("NEO4J_AUTH")
    )

    tos_root = Path(os.environ.get("TOS_GRAPH_TOS_ROOT", "/workspace/Tree-of-Sophia"))
    def source_path(env_name: str, config_key: str, default: str) -> Path:
        raw_path = Path(os.environ.get(env_name, source_cfg.get(config_key, default)))
        return raw_path if raw_path.is_absolute() else tos_root / raw_path

    corpus_index_path = source_path(
        "TOS_GRAPH_CORPUS_INDEX_PATH",
        "corpus_index",
        "ToS/derived-exports/tos_corpus_index.min.json",
    )
    philosophy_atlas_projection_path = source_path(
        "TOS_GRAPH_PHILOSOPHY_ATLAS_PROJECTION_PATH",
        "philosophy_atlas_projection",
        "ToS/derived-exports/philosophy_atlas_projection.min.json",
    )
    philosophy_graph_views_path = source_path(
        "TOS_GRAPH_PHILOSOPHY_GRAPH_VIEWS_PATH",
        "philosophy_graph_views",
        "ToS/derived-exports/philosophy_graph_views.min.json",
    )
    philosophy_graph_projection_path = source_path(
        "TOS_GRAPH_PHILOSOPHY_GRAPH_PROJECTION_PATH",
        "philosophy_graph_projection",
        "ToS/derived-exports/philosophy_graph_projection.min.json",
    )
    material_planting_projection_path = source_path(
        "TOS_GRAPH_MATERIAL_PLANTING_PROJECTION_PATH",
        "material_planting_projection",
        "ToS/derived-exports/material_planting_projection.min.json",
    )
    philosophy_post_planting_audit_path = source_path(
        "TOS_GRAPH_PHILOSOPHY_POST_PLANTING_AUDIT_PATH",
        "philosophy_post_planting_audit",
        "ToS/philosophy/graph-workbench/review-packets/table-i-post-planting-audit.json",
    )

    return TosGraphSettings(
        service_name=str(service_cfg.get("name", "tos-graph")),
        port=int(os.environ.get("TOS_GRAPH_PORT", service_cfg.get("port", 5410))),
        config_path=config_path,
        stack_env_path=stack_env_path,
        tos_root=tos_root,
        log_root=Path(os.environ.get("TOS_GRAPH_LOG_ROOT", "/app/logs")),
        corpus_index_path=corpus_index_path,
        philosophy_atlas_projection_path=philosophy_atlas_projection_path,
        philosophy_graph_views_path=philosophy_graph_views_path,
        philosophy_graph_projection_path=philosophy_graph_projection_path,
        material_planting_projection_path=material_planting_projection_path,
        philosophy_post_planting_audit_path=philosophy_post_planting_audit_path,
        default_view=str(os.environ.get("TOS_GRAPH_DEFAULT_VIEW", ui_cfg.get("default_view", "corpus-topology"))),
        default_philosophy_view=str(
            os.environ.get("TOS_GRAPH_DEFAULT_PHILOSOPHY_VIEW", ui_cfg.get("default_philosophy_view", "chronology"))
        ),
        write_enabled=_parse_bool(os.environ.get("TOS_GRAPH_WRITE_ENABLED"), False),
        neo4j_uri=os.environ.get("TOS_GRAPH_NEO4J_URI"),
        neo4j_user=os.environ.get("TOS_GRAPH_NEO4J_USER") or fallback_user,
        neo4j_password=os.environ.get("TOS_GRAPH_NEO4J_PASSWORD") or fallback_password,
        neo4j_database=str(os.environ.get("TOS_GRAPH_NEO4J_DATABASE", projection_cfg.get("database", "neo4j"))),
        projection_mode=str(os.environ.get("TOS_GRAPH_PROJECTION_MODE", projection_cfg.get("mode", "preview_only"))),
    )
