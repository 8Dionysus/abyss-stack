#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from kag_runtime import exact, graph, vector
from kag_runtime.bundle import RetrievalBundle, write_json_atomic
from kag_runtime.transport import JsonHttpClient


DEFAULT_STACK_ROOT = Path(os.environ.get("AOA_STACK_ROOT", "/srv/AbyssOS/abyss-stack"))
TARGETS = ("exact", "vector", "graph")
RECEIPT_SCHEMA_VERSION = "abyss-stack-repo-self-kag-materialization-receipt-v1"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _targets(values: Sequence[str]) -> list[str]:
    selected = (
        list(TARGETS)
        if "all" in values
        else [item for item in TARGETS if item in values]
    )
    if not selected:
        raise SystemExit("at least one --target is required")
    return selected


def _dotenv_values(path: Path, keys: set[str]) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in keys:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def _neo4j_headers(stack_root: Path) -> dict[str, str]:
    user = os.environ.get("AOA_KAG_NEO4J_USER") or os.environ.get("AOA_RAG_NEO4J_USER")
    password = os.environ.get("AOA_KAG_NEO4J_PASSWORD") or os.environ.get(
        "AOA_RAG_NEO4J_PASSWORD"
    )
    raw = os.environ.get("AOA_KAG_NEO4J_AUTH") or os.environ.get("NEO4J_AUTH")
    if not raw and (not user or not password):
        deployed = _dotenv_values(
            stack_root / "Secrets" / "Configs" / "stack.env",
            {"NEO4J_AUTH", "AOA_RAG_NEO4J_USER", "AOA_RAG_NEO4J_PASSWORD"},
        )
        user = user or deployed.get("AOA_RAG_NEO4J_USER")
        password = password or deployed.get("AOA_RAG_NEO4J_PASSWORD")
        raw = deployed.get("NEO4J_AUTH")
    if (not user or not password) and raw and raw.lower() != "none" and "/" in raw:
        user, password = raw.split("/", 1)
    if not user or not password:
        raise SystemExit("Neo4j credentials are required for the graph target")
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _client_headers(env_name: str) -> dict[str, str]:
    value = os.environ.get(env_name)
    return {"api-key": value} if value else {}


def _receipt(
    bundle: RetrievalBundle,
    *,
    target: str,
    started_at: str,
    duration_seconds: float,
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "target": target,
        "status": "current",
        "started_at": started_at,
        "completed_at": _now(),
        "duration_seconds": round(duration_seconds, 3),
        "bundle_identity": dict(bundle.manifest["bundle_identity"]),
        "projection_identity": dict(bundle.manifest["projection_identity"]),
        "federation_identity": dict(bundle.manifest["federation_identity"]),
        "result": result,
    }


def _write_receipt(
    runtime_root: Path,
    bundle: RetrievalBundle,
    target: str,
    receipt: dict[str, Any],
) -> None:
    projection_root = runtime_root / "receipts" / bundle.projection_digest
    target_path = projection_root / f"{target}.json"
    write_json_atomic(target_path, receipt)
    current_path = runtime_root / "current.json"
    current: dict[str, Any] = {
        "schema_version": "abyss-stack-repo-self-kag-current-v1",
        "bundle_identity": dict(bundle.manifest["bundle_identity"]),
        "projection_identity": dict(bundle.manifest["projection_identity"]),
        "federation_identity": dict(bundle.manifest["federation_identity"]),
        "targets": {},
    }
    if current_path.is_file():
        try:
            observed = json.loads(current_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            observed = None
        if (
            isinstance(observed, dict)
            and observed.get("projection_identity") == current["projection_identity"]
        ):
            current = observed
    current["updated_at"] = _now()
    current.setdefault("targets", {})[target] = {
        "status": "current",
        "receipt": str(target_path),
        "completed_at": receipt["completed_at"],
        "result": receipt["result"],
    }
    write_json_atomic(current_path, current)


def _vector_progress(completed: int, total: int) -> None:
    if completed == total or completed % 1024 == 0:
        print(f"[kag-runtime:vector] {completed}/{total}", flush=True)


def _graph_progress(family: str, completed: int, total: int) -> None:
    if completed == total or completed % 10000 == 0:
        print(f"[kag-runtime:graph:{family}] {completed}/{total}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize verified OS Abyss repo-self KAG runtime projections."
    )
    parser.add_argument("--bundle-dir", type=Path)
    parser.add_argument("--stack-root", type=Path, default=DEFAULT_STACK_ROOT)
    parser.add_argument(
        "--target",
        action="append",
        choices=(*TARGETS, "all"),
        default=[],
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--sqlite-path", type=Path)
    parser.add_argument(
        "--affected-owner",
        action="append",
        default=[],
        help=(
            "Advance only these owner slices plus touching cross-owner relations. "
            "May be repeated; currently enforced for the exact target."
        ),
    )
    parser.add_argument(
        "--owner-scoped",
        action="store_true",
        help=(
            "Use owner-addressed runtime projection slices. Without "
            "--affected-owner this bootstraps every owner."
        ),
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help=(
            "Atomically return exact, vector, and graph owner-scoped targets "
            "to their mutually matching last-good projection."
        ),
    )
    parser.add_argument(
        "--embedding-url",
        default=os.environ.get("AOA_KAG_EMBEDDING_URL", "http://127.0.0.1:5403"),
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.environ.get("AOA_KAG_QDRANT_URL", "http://127.0.0.1:6333"),
    )
    parser.add_argument("--qdrant-alias", default=vector.DEFAULT_ALIAS)
    parser.add_argument(
        "--neo4j-url",
        default=os.environ.get("AOA_KAG_NEO4J_HTTP_URL", "http://127.0.0.1:7474"),
    )
    parser.add_argument(
        "--neo4j-database",
        default=os.environ.get("AOA_KAG_NEO4J_DATABASE", "neo4j"),
    )
    parser.add_argument(
        "--graph-channel",
        default=os.environ.get("AOA_KAG_GRAPH_CHANNEL", graph.DEFAULT_CHANNEL),
    )
    parser.add_argument(
        "--vector-batch-size",
        type=int,
        default=vector.DEFAULT_EMBEDDING_BATCH_SIZE,
    )
    parser.add_argument("--graph-batch-size", type=int, default=1000)
    parser.add_argument("--http-timeout", type=float, default=180.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = _targets(args.target)
    affected_owners = sorted(
        {str(item).strip() for item in args.affected_owner if str(item).strip()}
    )
    if args.rollback:
        if set(selected) != set(TARGETS) or not args.owner_scoped:
            raise SystemExit(
                "--rollback requires --owner-scoped and --target all"
            )
        if args.check or affected_owners:
            raise SystemExit(
                "--rollback cannot be combined with --check or --affected-owner"
            )
    if affected_owners and not args.owner_scoped and any(
        target in {"vector", "graph"} for target in selected
    ):
        raise SystemExit(
            "--affected-owner requires --owner-scoped for vector or graph"
        )
    runtime_root = args.stack_root.resolve() / "Knowledge" / "kag" / "repo-self"
    sqlite_path = (
        args.sqlite_path.resolve()
        if args.sqlite_path
        else runtime_root / "exact" / "repo-self.sqlite3"
    )
    if args.rollback:
        qdrant = JsonHttpClient(
            args.qdrant_url,
            headers=_client_headers("AOA_KAG_QDRANT_API_KEY"),
            timeout=args.http_timeout,
        )
        graph_client = JsonHttpClient(
            args.neo4j_url,
            headers=_neo4j_headers(args.stack_root.resolve()),
            timeout=args.http_timeout,
        )
        graph_projection = graph.Neo4jProjection(
            graph_client,
            args.neo4j_database,
            args.graph_channel,
        )
        vector_state_path = runtime_root / "vector" / "owner-slices.json"
        graph_state_path = runtime_root / "graph" / "owner-slices.json"
        exact_candidate = exact.rollback_candidate(sqlite_path)
        vector_candidate = vector.owner_slice_rollback_candidate(
            qdrant=qdrant,
            state_path=vector_state_path,
        )
        graph_candidate = graph.owner_slice_rollback_candidate(
            graph=graph_projection,
            state_path=graph_state_path,
        )
        identities = {
            (
                str(candidate["projection_digest"]),
                str(candidate["bundle_digest"]),
                str(candidate["federation_digest"]),
            )
            for candidate in (
                exact_candidate,
                vector_candidate,
                graph_candidate,
            )
        }
        if len(identities) != 1:
            raise SystemExit(
                "last-good exact/vector/graph identities do not match; "
                "rollback refused"
            )
        projection_digest, bundle_digest, federation_digest = identities.pop()
        results = {
            "exact": exact.rollback(sqlite_path),
            "vector": vector.rollback_owner_slices(
                qdrant=qdrant,
                state_path=vector_state_path,
            ),
            "graph": graph.rollback_owner_slices(
                graph=graph_projection,
                state_path=graph_state_path,
            ),
        }
        completed_at = _now()
        receipt = {
            "schema_version": (
                "abyss-stack-repo-self-kag-projection-rollback-receipt-v1"
            ),
            "completed_at": completed_at,
            "projection_identity": {
                "local_id": "projection:os-abyss:repo-self-retrieval",
                "content_digest": projection_digest,
            },
            "bundle_identity": {
                "local_id": "bundle:os-abyss:repo-self-retrieval",
                "content_digest": bundle_digest,
            },
            "federation_identity": {
                "local_id": "projection:os-abyss:repo-self-federation",
                "content_digest": federation_digest,
            },
            "targets": results,
        }
        receipt_path = (
            runtime_root / "receipts" / projection_digest / "rollback.json"
        )
        write_json_atomic(receipt_path, receipt)
        write_json_atomic(
            runtime_root / "current.json",
            {
                "schema_version": "abyss-stack-repo-self-kag-current-v1",
                "updated_at": completed_at,
                "bundle_identity": receipt["bundle_identity"],
                "projection_identity": receipt["projection_identity"],
                "federation_identity": receipt["federation_identity"],
                "targets": {
                    target: {
                        "status": "current",
                        "completed_at": completed_at,
                        "result": result,
                        "rollback_receipt": str(receipt_path),
                    }
                    for target, result in results.items()
                },
            },
        )
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.bundle_dir is None:
        raise SystemExit("--bundle-dir is required unless --rollback is used")
    bundle = RetrievalBundle.open(args.bundle_dir)
    verification = bundle.verify()
    reports: dict[str, Any] = {"bundle": verification, "targets": {}}

    for target in selected:
        started_at = _now()
        started = time.monotonic()
        if target == "exact":
            result = (
                exact.check(bundle, sqlite_path)
                if args.check
                else (
                    exact.materialize_affected_owners(
                        bundle,
                        sqlite_path,
                        affected_owners=affected_owners,
                    )
                    if affected_owners
                    else exact.materialize(bundle, sqlite_path)
                )
            )
        elif target == "vector":
            qdrant = JsonHttpClient(
                args.qdrant_url,
                headers=_client_headers("AOA_KAG_QDRANT_API_KEY"),
                timeout=args.http_timeout,
            )
            owner_state_path = runtime_root / "vector" / "owner-slices.json"
            if args.check and args.owner_scoped:
                result = vector.check_owner_slices(
                    bundle,
                    qdrant=qdrant,
                    state_path=owner_state_path,
                )
            elif args.check:
                result = vector.check(bundle, qdrant=qdrant, alias=args.qdrant_alias)
            else:
                embeddings = JsonHttpClient(
                    args.embedding_url,
                    headers=_client_headers("AOA_KAG_EMBEDDING_API_KEY"),
                    timeout=args.http_timeout,
                )
                result = (
                    vector.materialize_owner_slices(
                        bundle,
                        qdrant=qdrant,
                        embeddings=embeddings,
                        state_path=owner_state_path,
                        affected_owners=affected_owners,
                        batch_size=args.vector_batch_size,
                        progress=_vector_progress,
                    )
                    if args.owner_scoped
                    else vector.materialize(
                        bundle,
                        qdrant=qdrant,
                        embeddings=embeddings,
                        alias=args.qdrant_alias,
                        batch_size=args.vector_batch_size,
                        progress=_vector_progress,
                    )
                )
        else:
            neo4j = JsonHttpClient(
                args.neo4j_url,
                headers=_neo4j_headers(args.stack_root.resolve()),
                timeout=args.http_timeout,
            )
            graph_projection = graph.Neo4jProjection(
                neo4j,
                args.neo4j_database,
                args.graph_channel,
            )
            owner_state_path = runtime_root / "graph" / "owner-slices.json"
            if args.check and args.owner_scoped:
                result = graph.check_owner_slices(
                    bundle,
                    graph=graph_projection,
                    state_path=owner_state_path,
                )
            elif args.check:
                result = graph.check(bundle, graph=graph_projection)
            else:
                result = (
                    graph.materialize_owner_slices(
                        bundle,
                        graph=graph_projection,
                        state_path=owner_state_path,
                        affected_owners=affected_owners,
                        batch_size=args.graph_batch_size,
                        progress=_graph_progress,
                    )
                    if args.owner_scoped
                    else graph.materialize(
                        bundle,
                        graph=graph_projection,
                        batch_size=args.graph_batch_size,
                        progress=_graph_progress,
                    )
                )
        reports["targets"][target] = result
        if not args.check:
            receipt = _receipt(
                bundle,
                target=target,
                started_at=started_at,
                duration_seconds=time.monotonic() - started,
                result=result,
            )
            _write_receipt(runtime_root, bundle, target, receipt)
        print(f"[kag-runtime:{target}] ok", flush=True)

    print(json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
