from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_WORKSPACE_ROOT = Path("/srv/AbyssOS")

CATALOG_MIN = Path("generated/eval_catalog.min.json")
CATALOG_FULL = Path("generated/eval_catalog.json")
CAPSULES = Path("generated/eval_capsules.json")
SECTIONS = Path("generated/eval_sections.full.json")
COMPARISON_SPINE = Path("generated/comparison_spine.json")
REPORT_INDEX = Path("generated/eval_report_index.min.json")
RUNTIME_TEMPLATE_INDEX = Path(
    "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_template_index.min.json"
)
RUNTIME_INTAKE = Path(
    "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_intake.min.json"
)

STOP_LINES = [
    "Do not run general evals.",
    "Do not compute verdicts.",
    "Do not publish receipts.",
    "Do not promote bundles.",
    "Do not mutate aoa-evals source from MCP.",
    "Do not treat runtime evidence, generated readers, or MCP output as stronger than bundle-local EVAL.md and eval.yaml.",
    "Do not move proof authority into abyss-stack.",
]


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON reader: {path}") from exc


def _list_from(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _lower(value: Any) -> str:
    return str(value or "").casefold()


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^a-zA-Z0-9_.:/-]+", text.casefold()) if token]


def _text_blob(record: dict[str, Any]) -> str:
    values: list[str] = []
    for key, value in record.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            values.append(str(value or ""))
        elif isinstance(value, list):
            values.extend(str(item) for item in value if not isinstance(item, dict))
        elif isinstance(value, dict):
            values.extend(str(item) for item in value.values() if not isinstance(item, (dict, list)))
    return " ".join(values).casefold()


def _match_filter(record: dict[str, Any], key: str, expected: Any) -> bool:
    if key == "limit":
        return True
    if key == "evidence_kind":
        return expected in record.get("evidence_kinds", [])
    if key == "proof_surface_kind":
        return expected in record.get("proof_surface_kinds", [])
    if key == "skill_dependency":
        return expected in record.get("skill_dependencies", [])
    if key == "technique_dependency":
        return expected in record.get("technique_dependencies", [])
    actual = record.get(key)
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, list):
        return expected in actual
    return _lower(actual) == _lower(expected)


def _normalize_filters(filters: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        if value in ("", None):
            continue
        normalized[str(key)] = value
    return normalized


def _name(record: dict[str, Any]) -> str:
    return str(record.get("name") or record.get("eval_name") or record.get("eval_anchor") or "")


def _source_ref(evals_root: Path, rel: str | None) -> str | None:
    if not rel:
        return None
    return (evals_root / rel).as_posix()


@dataclass(slots=True)
class AoAEvalsMCPState:
    workspace_root: Path
    evals_root: Path
    root_kind: str = "source"

    @classmethod
    def discover(
        cls,
        workspace_root: str | Path | None = None,
        evals_root: str | Path | None = None,
    ) -> "AoAEvalsMCPState":
        root = Path(
            workspace_root
            or os.environ.get("AOA_WORKSPACE_ROOT")
            or DEFAULT_WORKSPACE_ROOT
        ).expanduser().resolve()
        selected = cls._resolve_evals_root(root, evals_root)
        root_kind = "approved_mirror" if "Knowledge/federation/aoa-evals" in selected.as_posix() else "source"
        return cls(workspace_root=root, evals_root=selected, root_kind=root_kind)

    @staticmethod
    def _resolve_evals_root(workspace_root: Path, evals_root: str | Path | None = None) -> Path:
        candidates: list[Path] = []
        if evals_root:
            candidates.append(Path(evals_root).expanduser())
        for env_name in ("AOA_EVALS_ROOT", "AOA_EVALS_SOURCE_ROOT"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser())
        candidates.extend(
            [
                workspace_root / "aoa-evals",
                DEFAULT_WORKSPACE_ROOT / "aoa-evals",
                Path.home() / "src" / "aoa-evals",
            ]
        )
        for env_name in ("AOA_ABYSS_STACK_RUNTIME_ROOT", "AOA_ABYSS_STACK_ROOT"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser() / "Knowledge" / "federation" / "aoa-evals")
        candidates.append(DEFAULT_WORKSPACE_ROOT / "abyss-stack" / "Knowledge" / "federation" / "aoa-evals")

        for candidate in candidates:
            resolved = candidate.resolve()
            if (resolved / CATALOG_MIN).is_file() or (resolved / CATALOG_FULL).is_file():
                return resolved

        searched = "\n".join(f"- {path}" for path in candidates)
        raise FileNotFoundError(
            "Could not locate aoa-evals generated readers. Set AOA_EVALS_ROOT.\nSearched:\n"
            + searched
        )

    def authority_boundary(self) -> dict[str, Any]:
        return {
            "mcp_role": "read-only access plane over bounded proof surfaces",
            "stronger_owner": "bundle-local EVAL.md and eval.yaml",
            "service_owner": "abyss-stack owns the runnable MCP package only",
            "root_kind": self.root_kind,
            "stop_lines": STOP_LINES,
        }

    def _payload(self, rel: Path) -> Any:
        return _read_json(self.evals_root / rel)

    def catalog_payload(self) -> dict[str, Any]:
        payload = self._payload(CATALOG_MIN) or self._payload(CATALOG_FULL) or {}
        return payload if isinstance(payload, dict) else {"evals": payload}

    def catalog_records(self) -> list[dict[str, Any]]:
        return _list_from(self.catalog_payload(), "evals")

    def capsule_records(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(CAPSULES), "evals")

    def section_records(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(SECTIONS), "evals")

    def comparison_records(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(COMPARISON_SPINE), "evals")

    def report_records(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(REPORT_INDEX), "reports")

    def runtime_templates(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(RUNTIME_TEMPLATE_INDEX), "templates")

    def runtime_intake_templates(self) -> list[dict[str, Any]]:
        return _list_from(self._payload(RUNTIME_INTAKE), "templates")

    def build_catalog(self) -> dict[str, Any]:
        catalog = self.catalog_payload()
        records = self.catalog_records()
        return {
            "schema": "aoa_evals_catalog_resource_v1",
            "evals_root": self.evals_root.as_posix(),
            "root_kind": self.root_kind,
            "count": len(records),
            "source_reader": CATALOG_MIN.as_posix(),
            "source_of_truth": catalog.get("source_of_truth") if isinstance(catalog, dict) else None,
            "evals": records,
            "authority_boundary": self.authority_boundary(),
        }

    def _find_by_name(self, records: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        target = name.casefold()
        for record in records:
            if _name(record).casefold() == target:
                return record
        return None

    def _require_bundle(self, name: str) -> dict[str, Any]:
        record = self._find_by_name(self.catalog_records(), name)
        if record is None:
            raise ValueError(f"unknown eval bundle: {name}")
        return record

    def inspect_bundle(self, name: str) -> dict[str, Any]:
        catalog = self._require_bundle(name)
        capsule = self._find_by_name(self.capsule_records(), name)
        sections = self._find_by_name(self.section_records(), name)
        reports = [report for report in self.report_records() if report.get("eval_name") == name]
        return {
            "schema": "aoa_evals_bundle_inspection_v1",
            "name": name,
            "catalog": catalog,
            "capsule": capsule,
            "section_keys": [
                section.get("key")
                for section in (sections or {}).get("sections", [])
                if isinstance(section, dict)
            ],
            "reports": reports,
            "source_refs": {
                "eval": _source_ref(self.evals_root, catalog.get("eval_path")),
                "manifest": _source_ref(
                    self.evals_root,
                    str(catalog.get("eval_path", "")).replace("/EVAL.md", "/eval.yaml")
                    if catalog.get("eval_path")
                    else None,
                ),
                "generated_catalog": (self.evals_root / CATALOG_MIN).as_posix(),
                "generated_capsules": (self.evals_root / CAPSULES).as_posix(),
                "generated_sections": (self.evals_root / SECTIONS).as_posix(),
            },
            "authority_boundary": self.authority_boundary(),
        }

    def expand_bundle(self, name: str, section_key: str | None = None) -> dict[str, Any]:
        self._require_bundle(name)
        record = self._find_by_name(self.section_records(), name)
        sections = [section for section in (record or {}).get("sections", []) if isinstance(section, dict)]
        if section_key:
            selected = next((section for section in sections if section.get("key") == section_key), None)
            if selected is None:
                return {
                    "schema": "aoa_evals_bundle_sections_v1",
                    "name": name,
                    "section_key": section_key,
                    "found": False,
                    "available_section_keys": [section.get("key") for section in sections],
                    "authority_boundary": self.authority_boundary(),
                }
            sections = [selected]
        return {
            "schema": "aoa_evals_bundle_sections_v1",
            "name": name,
            "section_key": section_key,
            "found": bool(sections),
            "sections": sections,
            "source_reader": (self.evals_root / SECTIONS).as_posix(),
            "authority_boundary": self.authority_boundary(),
        }

    def select(self, proof_question: str = "", filters: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized_filters = _normalize_filters(filters)
        limit = int(normalized_filters.get("limit") or 12)
        capsules = {record.get("name"): record for record in self.capsule_records()}
        comparisons = {record.get("name"): record for record in self.comparison_records()}
        tokens = _tokens(proof_question)
        matches: list[dict[str, Any]] = []
        for record in self.catalog_records():
            if not all(_match_filter(record, key, value) for key, value in normalized_filters.items()):
                continue
            name = str(record.get("name") or "")
            merged = {
                **record,
                "capsule": capsules.get(name),
                "comparison": comparisons.get(name),
            }
            blob = _text_blob(merged)
            score = sum(1 for token in tokens if token in blob)
            if tokens and score == 0:
                continue
            matches.append(
                {
                    "name": name,
                    "score": score,
                    "summary": record.get("summary"),
                    "category": record.get("category"),
                    "status": record.get("status"),
                    "baseline_mode": record.get("baseline_mode"),
                    "claim_type": record.get("claim_type"),
                    "report_format": record.get("report_format"),
                    "eval_path": record.get("eval_path"),
                    "use_when_short": (capsules.get(name) or {}).get("use_when_short"),
                    "what_this_does_not_prove": (capsules.get(name) or {}).get("what_this_does_not_prove"),
                    "selection_summary": (comparisons.get(name) or {}).get("selection_summary"),
                }
            )
        matches.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
        return {
            "schema": "aoa_evals_selection_v1",
            "proof_question": proof_question,
            "filters": normalized_filters,
            "count": len(matches),
            "matches": matches[:limit],
            "authority_boundary": self.authority_boundary(),
        }

    def comparison(self, baseline_mode: str | None = None) -> dict[str, Any]:
        records = self.comparison_records()
        if baseline_mode:
            records = [record for record in records if _lower(record.get("baseline_mode")) == baseline_mode.casefold()]
        return {
            "schema": "aoa_evals_comparison_spine_v1",
            "baseline_mode": baseline_mode,
            "count": len(records),
            "evals": records,
            "source_reader": (self.evals_root / COMPARISON_SPINE).as_posix(),
            "authority_boundary": self.authority_boundary(),
        }

    def runtime_evidence_template(self, name: str = "") -> dict[str, Any]:
        all_templates = self.runtime_intake_templates() or self.runtime_templates()
        target = name.casefold()
        direct: list[dict[str, Any]] = []
        generic: list[dict[str, Any]] = []
        for template in all_templates:
            haystack = " ".join(
                str(template.get(key) or "")
                for key in ("template_name", "eval_anchor", "verdict_bundle_ref", "source_example_ref")
            ).casefold()
            if target and target in haystack:
                direct.append(template)
            elif template.get("template_kind") == "runtime_evidence_selection" and not template.get("eval_anchor"):
                generic.append(template)
        if not target:
            direct = all_templates
            generic = []
        return {
            "schema": "aoa_evals_runtime_evidence_template_v1",
            "name": name,
            "count": len(direct),
            "templates": direct,
            "generic_runtime_selection_templates": generic[:6],
            "source_reader": (self.evals_root / RUNTIME_INTAKE).as_posix()
            if self.runtime_intake_templates()
            else (self.evals_root / RUNTIME_TEMPLATE_INDEX).as_posix(),
            "candidate_posture": "candidate_until_eval_review",
            "authority_boundary": self.authority_boundary(),
        }

    def report_skeleton(self, name: str, evidence_refs: list[str] | None = None) -> dict[str, Any]:
        inspection = self.inspect_bundle(name)
        catalog = inspection["catalog"]
        evidence_refs = evidence_refs or []
        return {
            "schema": "aoa_evals_report_skeleton_v1",
            "candidate_only": True,
            "eval_name": name,
            "source_bundle_ref": catalog.get("eval_path"),
            "manifest_ref": str(catalog.get("eval_path", "")).replace("/EVAL.md", "/eval.yaml"),
            "report_format": catalog.get("report_format"),
            "evidence_refs": evidence_refs,
            "sections": {
                "object_under_evaluation": catalog.get("object_under_evaluation"),
                "bounded_claim": "fill from bundle-local EVAL.md after review",
                "candidate_evidence": evidence_refs,
                "review_notes": [],
                "verdict": "UNSET: MCP must not compute verdicts",
                "limitations": [],
                "owner_return_route": "interpret through bundle-local EVAL.md/eval.yaml and report contract",
            },
            "candidate_templates": self.runtime_evidence_template(name).get("templates", []),
            "authority_boundary": self.authority_boundary(),
        }

    def reports(self) -> dict[str, Any]:
        records = self.report_records()
        return {
            "schema": "aoa_evals_report_index_v1",
            "count": len(records),
            "reports": records,
            "source_reader": (self.evals_root / REPORT_INDEX).as_posix(),
            "authority_boundary": self.authority_boundary(),
        }

    def runtime_candidate_templates_resource(self) -> dict[str, Any]:
        templates = self.runtime_intake_templates() or self.runtime_templates()
        return {
            "schema": "aoa_evals_runtime_candidate_templates_v1",
            "count": len(templates),
            "templates": templates,
            "source_reader": (self.evals_root / RUNTIME_INTAKE).as_posix()
            if self.runtime_intake_templates()
            else (self.evals_root / RUNTIME_TEMPLATE_INDEX).as_posix(),
            "candidate_posture": "candidate_until_eval_review",
            "authority_boundary": self.authority_boundary(),
        }

    def read_resource(self, uri: str) -> dict[str, Any]:
        parsed = urlparse(uri)
        if parsed.scheme != "aoa-evals":
            raise ValueError(f"unsupported resource scheme: {uri}")
        route = (parsed.netloc + parsed.path).strip("/")
        parts = [unquote(part) for part in route.split("/") if part]
        if parts == ["catalog"]:
            return self.build_catalog()
        if parts == ["comparison-spine"]:
            return self.comparison()
        if parts == ["runtime-candidate-templates"]:
            return self.runtime_candidate_templates_resource()
        if parts == ["reports"]:
            return self.reports()
        if len(parts) == 2 and parts[0] == "bundle":
            return self.inspect_bundle(parts[1])
        if len(parts) == 3 and parts[0] == "bundle" and parts[2] == "sections":
            return self.expand_bundle(parts[1])
        raise ValueError(f"unsupported aoa-evals resource: {uri}")
