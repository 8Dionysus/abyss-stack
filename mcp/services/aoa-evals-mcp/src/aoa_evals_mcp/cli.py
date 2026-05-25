from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .core import AoAEvalsMCPState


def _print(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_filter(values: list[str] | None) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for item in values or []:
        if "=" not in item:
            raise SystemExit(f"filter must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if value.casefold() == "true":
            parsed: Any = True
        elif value.casefold() == "false":
            parsed = False
        else:
            parsed = value
        filters[key] = parsed
    return filters


def main() -> None:
    parser = argparse.ArgumentParser(prog="aoa-evals-mcp")
    parser.add_argument("--workspace-root", default=None)
    parser.add_argument("--evals-root", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("catalog")

    inspect = sub.add_parser("inspect")
    inspect.add_argument("name")

    expand = sub.add_parser("expand")
    expand.add_argument("name")
    expand.add_argument("--section-key")

    select = sub.add_parser("select")
    select.add_argument("--proof-question", default="")
    select.add_argument("--filter", action="append")

    find_or_propose = sub.add_parser("find-or-propose")
    find_or_propose.add_argument("--proof-question", default="")
    find_or_propose.add_argument("--proposal-file")

    comparison = sub.add_parser("comparison")
    comparison.add_argument("--baseline-mode")

    template = sub.add_parser("runtime-evidence-template")
    template.add_argument("name")

    sub.add_parser("runtime-status")

    validate = sub.add_parser("validate-evidence-candidate")
    validate.add_argument("--candidate-file", required=True)

    exports = sub.add_parser("runtime-candidate-exports")
    exports.add_argument("--limit", type=int, default=20)

    read_export = sub.add_parser("read-runtime-candidate-export")
    read_export.add_argument("record_id")
    read_export.add_argument("--include-payload", action="store_true")

    skeleton = sub.add_parser("report-skeleton")
    skeleton.add_argument("name")
    skeleton.add_argument("--evidence-ref", action="append")

    resource = sub.add_parser("read-resource")
    resource.add_argument("uri")

    args = parser.parse_args()
    state = AoAEvalsMCPState.discover(workspace_root=args.workspace_root, evals_root=args.evals_root)

    if args.command == "catalog":
        _print(state.build_catalog())
    elif args.command == "inspect":
        _print(state.inspect_bundle(args.name))
    elif args.command == "expand":
        _print(state.expand_bundle(args.name, args.section_key))
    elif args.command == "select":
        _print(state.select(args.proof_question, _parse_filter(args.filter)))
    elif args.command == "find-or-propose":
        proposal = None
        if args.proposal_file:
            proposal = json.loads(Path(args.proposal_file).read_text(encoding="utf-8"))
        _print(state.find_or_propose(args.proof_question, proposal))
    elif args.command == "comparison":
        _print(state.comparison(args.baseline_mode))
    elif args.command == "runtime-evidence-template":
        _print(state.runtime_evidence_template(args.name))
    elif args.command == "runtime-status":
        _print(state.runtime_status())
    elif args.command == "validate-evidence-candidate":
        packet = json.loads(Path(args.candidate_file).read_text(encoding="utf-8"))
        _print(state.validate_evidence_candidate(packet))
    elif args.command == "runtime-candidate-exports":
        _print(state.runtime_candidate_exports(limit=args.limit))
    elif args.command == "read-runtime-candidate-export":
        _print(state.read_runtime_candidate_export(args.record_id, include_payload=args.include_payload))
    elif args.command == "report-skeleton":
        _print(state.report_skeleton(args.name, args.evidence_ref))
    elif args.command == "read-resource":
        _print(state.read_resource(args.uri))


if __name__ == "__main__":
    main()
