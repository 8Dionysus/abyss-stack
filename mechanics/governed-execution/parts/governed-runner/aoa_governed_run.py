#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


SCRIPT_DIR = Path(__file__).resolve().parent


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / "scripts").is_dir() and (candidate / "mechanics").is_dir():
            return candidate
    raise RuntimeError(f"could not find abyss-stack root from {start}")


REPO_ROOT = find_repo_root(SCRIPT_DIR)
BACKEND_DIR = SCRIPT_DIR
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import aoa_governed_execution as governed  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Governed abyss-stack execution lane")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare-request", help="Write a governed execution request template")
    prepare.add_argument("--write", required=True, help="Path to write the request JSON template")

    prepare_canary = subparsers.add_parser("prepare-canary", help="Write a governed canary request template")
    prepare_canary.add_argument("canary_id", help="Canary identifier from the governed canary catalog")
    prepare_canary.add_argument("--write", required=True, help="Path to write the canary request JSON")
    prepare_canary.add_argument("--repo-root", help="Override the repo_root placed into the request")

    materialize = subparsers.add_parser("materialize-canaries", help="Write all governed canary request templates")
    materialize.add_argument("--write-dir", required=True, help="Directory that should receive one request per canary")
    materialize.add_argument("--repo-root", help="Override the repo_root placed into each request")

    run = subparsers.add_parser("run", help="Prepare a new governed run from a request file")
    run.add_argument("--request-file", required=True, help="Path to the governed request JSON")
    run.add_argument("--until", choices=("milestone", "done"), default="done")

    resume = subparsers.add_parser("resume", help="Resume an existing governed run")
    resume.add_argument("run_id", help="Run identifier")
    resume.add_argument("--until", choices=("milestone", "done"), default="done")

    audit = subparsers.add_parser("audit", help="Audit review-packet readiness for an existing governed run")
    audit.add_argument("run_id", help="Run identifier")

    replay = subparsers.add_parser(
        "replay-review-packets",
        help="Rebuild review packets from stored governed-run context without rerunning the mutation lane",
    )
    replay.add_argument("run_id", help="Run identifier")

    handoff = subparsers.add_parser(
        "handoff-brief",
        help="Assemble a review handoff bundle from stored review-packet artifacts and live owner intake maps",
    )
    handoff.add_argument("run_id", help="Run identifier")

    status = subparsers.add_parser("status", help="Inspect governed run state")
    status.add_argument("--all", action="store_true", help="List all governed runs")
    status.add_argument("--explain", action="store_true", help="Render a compact operator-facing summary instead of JSON")
    status.add_argument("run_id", nargs="?", help="Run identifier")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "prepare-request":
        target = Path(args.write).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(governed.default_request_template(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"ok": True, "request_file": str(target)}, indent=2, ensure_ascii=True))
        return 0

    if args.command == "prepare-canary":
        target = Path(args.write).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = governed.request_from_canary(args.canary_id, repo_root=args.repo_root)
        target.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {"ok": True, "canary_id": args.canary_id, "request_file": str(target)},
                indent=2,
                ensure_ascii=True,
            )
        )
        return 0

    if args.command == "materialize-canaries":
        payload = governed.materialize_canary_requests(args.write_dir, repo_root=args.repo_root)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    if args.command == "run":
        payload = governed.prepare_run(args.request_file, until=args.until)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0 if payload.get("status") != "fail" else 1

    if args.command == "resume":
        payload = governed.resume_run(args.run_id, until=args.until)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0 if payload.get("status") != "fail" else 1

    if args.command == "audit":
        payload = governed.audit_run(args.run_id)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 2 if payload.get("audit_verdict") == "blocked" else 0

    if args.command == "replay-review-packets":
        payload = governed.replay_review_packets(args.run_id)
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 2 if payload.get("audit_verdict") == "blocked" else 0

    if args.command == "handoff-brief":
        payload = governed.handoff_brief_run(args.run_id)
        print(governed.render_review_handoff_bundle_brief(payload.get("review_handoff_bundle") or payload))
        return 2 if payload.get("handoff_readiness") == "blocked" else 0

    if args.command == "status":
        if args.all and args.run_id:
            raise SystemExit("status accepts either --all or a run_id, not both")
        if args.all:
            payload = governed.list_runs()
            if args.explain:
                print(governed.render_run_index_explain(payload))
                return 0
        else:
            if not args.run_id:
                raise SystemExit("status requires --all or a run_id")
            payload = governed.status_run(args.run_id)
            if args.explain:
                print(governed.render_status_explain(payload))
                return 0
        print(json.dumps(payload, indent=2, ensure_ascii=True))
        return 0

    raise SystemExit(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
