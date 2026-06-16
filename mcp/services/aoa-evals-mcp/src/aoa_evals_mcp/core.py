from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft202012Validator


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
RUNTIME_TEMPLATE_INDEX_MIRROR = Path("generated/runtime_candidate_template_index.min.json")
RUNTIME_INTAKE = Path(
    "mechanics/audit/parts/candidate-readers/generated/runtime_candidate_intake.min.json"
)
RUNTIME_INTAKE_MIRROR = Path("generated/runtime_candidate_intake.min.json")
RUNTIME_EVIDENCE_SCHEMA = Path(
    "mechanics/audit/parts/selected-evidence-packets/schemas/runtime-evidence-selection.schema.json"
)
RUNTIME_EVIDENCE_SCHEMA_MIRROR = Path("schemas/runtime-evidence-selection.schema.json")
ARTIFACT_HOOK_SCHEMA = Path(
    "mechanics/audit/parts/artifact-verdict-hooks/schemas/artifact-to-verdict-hook.schema.json"
)
ARTIFACT_HOOK_SCHEMA_MIRROR = Path("schemas/artifact-to-verdict-hook.schema.json")
RUNTIME_TEMPLATE_SCHEMA = Path(
    "mechanics/audit/parts/candidate-readers/schemas/runtime-candidate-template-index.schema.json"
)
RUNTIME_TEMPLATE_SCHEMA_MIRROR = Path("schemas/runtime-candidate-template-index.schema.json")
EVAL_NEED_SCHEMA = Path("mechanics/proof-object/parts/eval-authoring/schemas/eval-need.schema.json")
EVAL_NEED_SCHEMA_MIRROR = Path("schemas/eval-need.schema.json")
MIRROR_MANIFEST = Path("manifest/federation_mirror_manifest.json")
RUNTIME_CANDIDATE_EXPORT_ROOT = Path("Logs/eval-exports")
RUNTIME_CANDIDATE_LATEST_DIRS = (
    "runtime-evidence-selection",
    "artifact-hook",
)
LOCAL_PORT_REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "PORT.yaml",
    "intake/README.md",
    "suites/README.md",
    "reports/README.md",
)
LOCAL_PORT_REQUIRED_FIELDS = (
    "schema_version",
    "owner_repo",
    "status",
    "proof_owner_repo",
    "default_intake_schema",
    "local_role",
    "central_boundary",
)
LOCAL_PORT_BOUNDARY_TOKENS = ("verdict", "scoring", "regression", "proof doctrine")
LOCAL_WRITE_AUTHORITY_BOUNDARY = "no verdict, scoring, regression, or proof doctrine authority"
SAFE_FILE_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,120}$")
LOCAL_NOTE_CONFIG = {
    "suites": {
        "glob_suffix": ".suite.md",
        "schema_version": "local_eval_suite_note_v1",
        "resource_key": "suites",
    },
    "reports": {
        "glob_suffix": ".report.md",
        "schema_version": "local_eval_report_note_v1",
        "resource_key": "reports",
    },
}

READER_GROUPS: dict[str, tuple[Path, ...]] = {
    "catalog": (CATALOG_MIN, CATALOG_FULL),
    "capsules": (CAPSULES,),
    "sections": (SECTIONS,),
    "comparison_spine": (COMPARISON_SPINE,),
    "report_index": (REPORT_INDEX,),
    "runtime_candidate_template_index": (RUNTIME_TEMPLATE_INDEX, RUNTIME_TEMPLATE_INDEX_MIRROR),
    "runtime_candidate_intake": (RUNTIME_INTAKE, RUNTIME_INTAKE_MIRROR),
    "runtime_evidence_schema": (RUNTIME_EVIDENCE_SCHEMA, RUNTIME_EVIDENCE_SCHEMA_MIRROR),
    "artifact_hook_schema": (ARTIFACT_HOOK_SCHEMA, ARTIFACT_HOOK_SCHEMA_MIRROR),
}

STOP_LINES = [
    "Do not run general evals.",
    "Do not compute verdicts.",
    "Do not publish receipts.",
    "Do not promote bundles.",
    "Do not mutate aoa-evals source from MCP.",
    "Do not treat runtime evidence, generated readers, or MCP output as stronger than bundle-local EVAL.md and eval.yaml.",
    "Do not move proof authority into abyss-stack.",
]

ROUTE_TOKEN_STOPWORDS = {
    "a",
    "an",
    "and",
    "artifact",
    "bounded",
    "candidate",
    "compare",
    "eval",
    "evidence",
    "for",
    "in",
    "of",
    "on",
    "or",
    "proof",
    "route",
    "runtime",
    "the",
    "to",
    "selection",
    "surface",
    "with",
}


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON reader: {path}") from exc


def _read_yaml(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML reader: {path}") from exc


def _read_json_first(root: Path, rels: tuple[Path, ...]) -> tuple[Any, Path | None]:
    for rel in rels:
        path = root / rel
        if path.is_file():
            return _read_json(path), rel
    return None, None


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


def _runtime_export_match_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _tokens(text):
        if token in ROUTE_TOKEN_STOPWORDS:
            continue
        if len(token) < 4 and not any(char.isdigit() for char in token):
            continue
        tokens.add(token)
    return tokens


RUNTIME_EXPORT_REF_PREFIX = "runtime-candidate-export:"


def _runtime_export_ref_id(value: str) -> str:
    text = value.casefold().strip()
    if text.startswith(RUNTIME_EXPORT_REF_PREFIX):
        text = text[len(RUNTIME_EXPORT_REF_PREFIX) :]
    return text


def _explicit_runtime_export_ref_ids(values: list[str]) -> set[str]:
    ids: set[str] = set()
    for value in values:
        if not value.casefold().strip().startswith(RUNTIME_EXPORT_REF_PREFIX):
            continue
        record_id = _runtime_export_ref_id(value)
        if record_id:
            ids.add(record_id)
    return ids


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


def _utc_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat()


def _git_commit(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", root.as_posix(), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").casefold()).strip("-")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _bounded_text(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if len(text) >= 12 else fallback


def _enum_value(value: Any, allowed: set[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def _eval_need_name(proof_question: str, proposal: dict[str, Any], matches: list[dict[str, Any]]) -> str:
    explicit = str(proposal.get("name") or "").strip()
    if re.fullmatch(r"aoa-[a-z0-9-]+", explicit):
        return explicit
    if matches:
        match_name = str(matches[0].get("name") or "").strip()
        if re.fullmatch(r"aoa-[a-z0-9-]+", match_name):
            return match_name
    slug = _slug(proof_question)[:80].strip("-")
    return f"aoa-{slug or 'eval-need'}"


def _safe_file_slug(value: str, fallback: str = "local-eval-pressure") -> str:
    slug = _slug(value) or fallback
    slug = slug[:120].strip("-") or fallback
    if not SAFE_FILE_SLUG.fullmatch(slug):
        raise ValueError(f"unsafe local eval file slug: {value!r}")
    return slug


def _safe_repo_name(value: str) -> str:
    repo = str(value or "").strip()
    if not repo or repo in {".", ".."} or "/" in repo or "\\" in repo or "\x00" in repo:
        raise ValueError(f"unsafe repo name: {value!r}")
    return repo


def _relative_repo_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _validate_public_refs(refs: list[str]) -> list[str]:
    issues: list[str] = []
    for ref in refs:
        text = str(ref or "").strip()
        if not text:
            issues.append("refs must not contain empty values")
        if text.startswith("/") or "\\" in text or "\x00" in text:
            issues.append(f"ref is not repo-local/public-safe: {text!r}")
        parts = Path(text).parts
        if ".." in parts:
            issues.append(f"ref must not traverse upward: {text!r}")
        if text.casefold().startswith(("private:", "secret:", "credential:")):
            issues.append(f"ref must not point at private material: {text!r}")
    return issues


def _markdown_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, text
    try:
        _, frontmatter, body = text.split("---\n", 2)
    except ValueError:
        return None, text
    payload = yaml.safe_load(frontmatter)
    return (payload if isinstance(payload, dict) else None), body.lstrip()


def _note_markdown(frontmatter: dict[str, Any], title: str, body_markdown: str) -> str:
    frontmatter_text = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    body = str(body_markdown or "").strip()
    if not body:
        body = f"# {title}\n\nLocal eval-port note."
    return f"---\n{frontmatter_text}\n---\n\n{body}\n"


@dataclass(slots=True)
class AoAEvalsMCPState:
    workspace_root: Path
    evals_root: Path
    root_kind: str = "source"
    source_root: Path | None = None
    mirror_root: Path | None = None
    stack_runtime_root: Path | None = None

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
        source_root = cls._resolve_source_root(root, evals_root)
        mirror_root = cls._resolve_mirror_root(root)
        stack_runtime_root = cls._resolve_stack_runtime_root(root)
        selected = cls._resolve_evals_root(root, evals_root)
        root_kind = "approved_mirror" if "Knowledge/federation/aoa-evals" in selected.as_posix() else "source"
        return cls(
            workspace_root=root,
            evals_root=selected,
            root_kind=root_kind,
            source_root=source_root,
            mirror_root=mirror_root,
            stack_runtime_root=stack_runtime_root,
        )

    @staticmethod
    def _source_candidates(workspace_root: Path, evals_root: str | Path | None = None) -> list[Path]:
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
        return candidates

    @staticmethod
    def _mirror_candidates(workspace_root: Path) -> list[Path]:
        candidates: list[Path] = []
        for env_name in ("AOA_EVALS_MIRROR_ROOT", "AOA_EVALS_RUNTIME_MIRROR_ROOT"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser())
        for env_name in ("AOA_STACK_ROOT", "AOA_ABYSS_STACK_RUNTIME_ROOT", "AOA_ABYSS_STACK_ROOT"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser() / "Knowledge" / "federation" / "aoa-evals")
        candidates.extend(
            [
                workspace_root / "abyss-stack" / "Knowledge" / "federation" / "aoa-evals",
                DEFAULT_WORKSPACE_ROOT / "abyss-stack" / "Knowledge" / "federation" / "aoa-evals",
            ]
        )
        return candidates

    @staticmethod
    def _stack_runtime_candidates(workspace_root: Path) -> list[Path]:
        candidates: list[Path] = []
        for env_name in ("AOA_STACK_ROOT", "AOA_ABYSS_STACK_RUNTIME_ROOT", "AOA_ABYSS_STACK_ROOT"):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser())
        candidates.extend(
            [
                workspace_root / "abyss-stack",
                DEFAULT_WORKSPACE_ROOT / "abyss-stack",
            ]
        )
        return candidates

    @classmethod
    def _resolve_source_root(
        cls,
        workspace_root: Path,
        evals_root: str | Path | None = None,
    ) -> Path | None:
        for candidate in cls._source_candidates(workspace_root, evals_root):
            resolved = candidate.resolve()
            if (resolved / CATALOG_MIN).is_file() or (resolved / CATALOG_FULL).is_file():
                return resolved
        return None

    @classmethod
    def _resolve_mirror_root(cls, workspace_root: Path) -> Path | None:
        first: Path | None = None
        for candidate in cls._mirror_candidates(workspace_root):
            resolved = candidate.resolve()
            first = first or resolved
            if (resolved / CATALOG_MIN).is_file() or (resolved / CATALOG_FULL).is_file():
                return resolved
        return first

    @classmethod
    def _resolve_stack_runtime_root(cls, workspace_root: Path) -> Path | None:
        first: Path | None = None
        for candidate in cls._stack_runtime_candidates(workspace_root):
            resolved = candidate.resolve()
            first = first or resolved
            if (resolved / RUNTIME_CANDIDATE_EXPORT_ROOT).exists() or (
                resolved / "Knowledge" / "federation" / "aoa-evals"
            ).exists():
                return resolved
        return first

    @staticmethod
    def _resolve_evals_root(workspace_root: Path, evals_root: str | Path | None = None) -> Path:
        candidates = AoAEvalsMCPState._source_candidates(workspace_root, evals_root)
        candidates.extend(AoAEvalsMCPState._mirror_candidates(workspace_root))

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
            "mcp_role": "access plane over bounded proof surfaces plus gated repo-local eval-port writes",
            "stronger_owner": "bundle-local EVAL.md and eval.yaml",
            "service_owner": "abyss-stack owns the runnable MCP package only",
            "local_write_scope": "sibling repo evals/intake, evals/suites, evals/reports, and PORT.yaml activation only",
            "root_kind": self.root_kind,
            "stop_lines": STOP_LINES,
        }

    def _payload(self, rel: Path) -> Any:
        return _read_json(self.evals_root / rel)

    def _payload_first(self, *rels: Path) -> tuple[Any, Path | None]:
        return _read_json_first(self.evals_root, tuple(rels))

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
        payload, _ = self._payload_first(RUNTIME_TEMPLATE_INDEX, RUNTIME_TEMPLATE_INDEX_MIRROR)
        return _list_from(payload, "templates")

    def runtime_intake_templates(self) -> list[dict[str, Any]]:
        payload, _ = self._payload_first(RUNTIME_INTAKE, RUNTIME_INTAKE_MIRROR)
        return _list_from(payload, "templates")

    def _local_port_roots(self) -> list[Path]:
        if not self.workspace_root.exists():
            return []
        roots: list[Path] = []
        try:
            children = sorted(path for path in self.workspace_root.iterdir() if path.is_dir())
        except OSError:
            return []
        for child in children:
            if child.name == "aoa-evals":
                continue
            if (child / "evals" / "PORT.yaml").is_file():
                roots.append(child)
        return roots

    def _local_repo_root(self, repo: str) -> Path:
        repo_name = _safe_repo_name(repo)
        root = (self.workspace_root / repo_name).resolve()
        if not _within(self.workspace_root, root):
            raise ValueError(f"repo escapes workspace root: {repo}")
        if not (root / "evals" / "PORT.yaml").is_file():
            raise ValueError(f"repo does not expose a local eval port: {repo}")
        return root

    def _local_port_payload(self, repo_root: Path) -> dict[str, Any]:
        payload = _read_yaml(repo_root / "evals" / "PORT.yaml")
        return payload if isinstance(payload, dict) else {}

    def _local_port_issues(self, repo_root: Path, port: dict[str, Any]) -> list[str]:
        evals_dir = repo_root / "evals"
        issues: list[str] = []
        for rel in LOCAL_PORT_REQUIRED_FILES:
            if not (evals_dir / rel).is_file():
                issues.append(f"missing {rel}")
        for field in LOCAL_PORT_REQUIRED_FIELDS:
            if field not in port:
                issues.append(f"PORT.yaml missing {field}")
        if port.get("schema_version") != "local_eval_port_v1":
            issues.append("PORT.yaml schema_version must be local_eval_port_v1")
        if port.get("owner_repo") != repo_root.name:
            issues.append(f"PORT.yaml owner_repo must be {repo_root.name}")
        if port.get("status") not in {"skeleton", "active"}:
            issues.append("PORT.yaml status must be skeleton or active")
        if port.get("proof_owner_repo") != "aoa-evals":
            issues.append("PORT.yaml proof_owner_repo must be aoa-evals")
        if port.get("default_intake_schema") != "eval_need_v1":
            issues.append("PORT.yaml default_intake_schema must be eval_need_v1")
        boundary = str(port.get("central_boundary") or "").casefold()
        if not boundary:
            issues.append("PORT.yaml central_boundary is required")
        else:
            missing = [token for token in LOCAL_PORT_BOUNDARY_TOKENS if token not in boundary]
            if missing:
                issues.append("PORT.yaml central_boundary must name no verdict, scoring, regression, or proof doctrine authority")
        return issues

    def _local_intake_records(self, repo_root: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        intake_dir = repo_root / "evals" / "intake"
        if not intake_dir.is_dir():
            return records
        for path in sorted(intake_dir.glob("*.eval_need.json")):
            try:
                payload = _read_json(path)
            except ValueError as exc:
                records.append(
                    {
                        "path": _relative_repo_path(path, repo_root),
                        "valid": False,
                        "issues": [str(exc)],
                    }
                )
                continue
            validation = self._validate_eval_need(payload if isinstance(payload, dict) else {})
            records.append(
                {
                    "path": _relative_repo_path(path, repo_root),
                    "name": payload.get("name") if isinstance(payload, dict) else None,
                    "authoring_route": payload.get("authoring_route") if isinstance(payload, dict) else None,
                    "proof_question": payload.get("proof_question") if isinstance(payload, dict) else None,
                    "valid": validation["valid"],
                    "issues": validation["issues"],
                    "packet": payload if isinstance(payload, dict) else None,
                }
            )
        return records

    def _local_note_records(self, repo_root: Path, directory_name: str) -> list[dict[str, Any]]:
        config = LOCAL_NOTE_CONFIG[directory_name]
        records: list[dict[str, Any]] = []
        directory = repo_root / "evals" / directory_name
        if not directory.is_dir():
            return records
        for path in sorted(directory.glob(f"*{config['glob_suffix']}")):
            try:
                frontmatter, body = _markdown_frontmatter(path)
            except (OSError, yaml.YAMLError) as exc:
                records.append(
                    {
                        "path": _relative_repo_path(path, repo_root),
                        "valid": False,
                        "issues": [str(exc)],
                    }
                )
                continue
            issues: list[str] = []
            if frontmatter is None:
                issues.append("missing YAML frontmatter")
                frontmatter = {}
            if frontmatter.get("schema_version") != config["schema_version"]:
                issues.append(f"schema_version must be {config['schema_version']}")
            if frontmatter.get("owner_repo") != repo_root.name:
                issues.append(f"owner_repo must be {repo_root.name}")
            if frontmatter.get("status") not in {"draft", "reviewed"}:
                issues.append("status must be draft or reviewed")
            boundary = str(frontmatter.get("authority_boundary") or "").casefold()
            if not boundary:
                issues.append("authority_boundary is required")
            else:
                missing = [token for token in LOCAL_PORT_BOUNDARY_TOKENS if token not in boundary]
                if missing:
                    issues.append("authority_boundary must name no verdict, scoring, regression, or proof doctrine authority")
            records.append(
                {
                    "path": _relative_repo_path(path, repo_root),
                    "slug": path.name[: -len(config["glob_suffix"])],
                    "title": frontmatter.get("title"),
                    "summary": frontmatter.get("summary"),
                    "status": frontmatter.get("status"),
                    "refs": frontmatter.get("refs", []),
                    "valid": not issues,
                    "issues": issues,
                    "frontmatter": frontmatter,
                    "content_markdown": body,
                }
            )
        return records

    def _local_bundle_count(self, repo_root: Path) -> int:
        evals_dir = repo_root / "evals"
        return sum(1 for _ in evals_dir.glob("**/eval.yaml")) if evals_dir.is_dir() else 0

    def _local_port_summary(self, repo_root: Path, *, include_files: bool = False) -> dict[str, Any]:
        port = self._local_port_payload(repo_root)
        intake = self._local_intake_records(repo_root)
        suites = self._local_note_records(repo_root, "suites")
        reports = self._local_note_records(repo_root, "reports")
        bundle_count = self._local_bundle_count(repo_root)
        active_count = len(intake) + len(suites) + len(reports) + bundle_count
        issues = self._local_port_issues(repo_root, port)
        if port.get("status") == "active" and active_count == 0:
            issues.append("active local eval port must contain local pressure files")
        if port.get("status") == "skeleton" and active_count > 0:
            issues.append("skeleton local eval port must not contain local pressure files")
        issues.extend(
            f"{record['path']}: " + "; ".join(record.get("issues", []))
            for record in [*intake, *suites, *reports]
            if record.get("valid") is False
        )
        result: dict[str, Any] = {
            "repo": repo_root.name,
            "repo_root": repo_root.as_posix(),
            "evals_root": (repo_root / "evals").as_posix(),
            "port": port,
            "status": port.get("status"),
            "counts": {
                "intake": len(intake),
                "suites": len(suites),
                "reports": len(reports),
                "local_bundles": bundle_count,
                "active_pressure": active_count,
            },
            "validation": {
                "valid": not issues,
                "issues": issues,
            },
            "authority_boundary": {
                "local_role": "repo-local eval pressure only",
                "stronger_owner": "aoa-evals central proof doctrine, verdict, scoring, and regression",
                "mcp_write_scope": "local eval-port files only",
            },
        }
        if include_files:
            result.update({"intake": intake, "suites": suites, "reports": reports})
        return result

    def local_ports(self, status: str | None = None, include_skeleton: bool = True) -> dict[str, Any]:
        ports = [self._local_port_summary(root) for root in self._local_port_roots()]
        if status:
            ports = [port for port in ports if str(port.get("status") or "") == status]
        if not include_skeleton:
            ports = [port for port in ports if port.get("status") != "skeleton"]
        return {
            "schema": "aoa_evals_local_ports_v1",
            "workspace_root": self.workspace_root.as_posix(),
            "count": len(ports),
            "ports": ports,
            "read_only": True,
            "write_scope": "use gated write tools for local port files only",
            "authority_boundary": self.authority_boundary(),
        }

    def local_port(self, repo: str) -> dict[str, Any]:
        repo_root = self._local_repo_root(repo)
        result = self._local_port_summary(repo_root, include_files=True)
        result["schema"] = "aoa_evals_local_port_v1"
        result["read_only"] = True
        result["write_scope"] = "local intake, suite notes, and report notes only"
        result["authority_boundary"] = self.authority_boundary()
        return result

    def _local_write_target(self, repo_root: Path, directory_name: str, slug: str, suffix: str) -> Path:
        safe_slug = _safe_file_slug(slug)
        target = repo_root / "evals" / directory_name / f"{safe_slug}{suffix}"
        if not _within(repo_root / "evals", target):
            raise ValueError("local eval write target escapes evals port")
        return target

    def _port_activation_update(self, repo_root: Path) -> tuple[bool, str | None, list[str]]:
        port_path = repo_root / "evals" / "PORT.yaml"
        port = self._local_port_payload(repo_root)
        if port.get("status") != "skeleton":
            return False, None, []
        text = port_path.read_text(encoding="utf-8")
        status_pattern = re.compile(
            r"(?m)^(?P<prefix>status\s*:\s*)(?P<quote>['\"]?)skeleton(?P=quote)(?P<suffix>\s*(?:#.*)?)$"
        )
        updated, count = status_pattern.subn(r"\g<prefix>active\g<suffix>", text, count=1)
        if count != 1:
            return True, None, ["PORT.yaml status line could not be activated safely"]
        return True, updated, []

    def _local_write_gate(self, repo_root: Path) -> tuple[bool, list[str]]:
        port_summary = self._local_port_summary(repo_root)
        issues = list(port_summary.get("validation", {}).get("issues", []))
        activation_needed, _, activation_issues = self._port_activation_update(repo_root)
        issues.extend(activation_issues)
        return activation_needed, issues

    def _maybe_activate_port(self, repo_root: Path, *, apply: bool) -> bool:
        activation_needed, updated, issues = self._port_activation_update(repo_root)
        if not activation_needed:
            return False
        if issues:
            raise ValueError(issues[0])
        if not apply:
            return True
        if updated is None:
            raise ValueError("PORT.yaml status line could not be activated safely")
        (repo_root / "evals" / "PORT.yaml").write_text(updated, encoding="utf-8")
        return True

    def find_or_propose_local(
        self,
        repo: str,
        proof_question: str = "",
        proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        repo_root = self._local_repo_root(repo)
        base = self.find_or_propose(proof_question=proof_question, proposal=proposal)
        packet = base["proposal_context"]["packet"]
        slug = _safe_file_slug(str(packet.get("name") or proof_question or repo_root.name))
        target = self._local_write_target(repo_root, "intake", slug, ".eval_need.json")
        return {
            "schema": "aoa_evals_local_find_or_propose_v1",
            "repo": repo_root.name,
            "local_port": self._local_port_summary(repo_root),
            "central_route": base,
            "local_write_plan": {
                "target_path": target.as_posix(),
                "relative_path": _relative_repo_path(target, repo_root),
                "apply_default": False,
                "tool": "aoa_evals_write_local_intake",
                "port_activation_needed": self._local_port_payload(repo_root).get("status") == "skeleton",
            },
            "candidate_only": True,
            "authority_boundary": self.authority_boundary(),
        }

    def write_local_intake(
        self,
        repo: str,
        packet: dict[str, Any],
        file_slug: str | None = None,
        *,
        apply: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        repo_root = self._local_repo_root(repo)
        packet = packet if isinstance(packet, dict) else {}
        validation = self._validate_eval_need(packet)
        slug = _safe_file_slug(str(file_slug or packet.get("name") or "local-eval-pressure"))
        target = self._local_write_target(repo_root, "intake", slug, ".eval_need.json")
        activated, issues = self._local_write_gate(repo_root)
        issues = [*issues, *validation.get("issues", [])]
        if target.exists() and not replace_existing:
            issues.append("target file already exists; set replace_existing=True to overwrite")
        write_allowed = validation["valid"] and not issues
        if apply and write_allowed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            activated = self._maybe_activate_port(repo_root, apply=True)
        return {
            "schema": "aoa_evals_local_intake_write_v1",
            "repo": repo_root.name,
            "target_path": target.as_posix(),
            "relative_path": _relative_repo_path(target, repo_root),
            "apply": apply,
            "applied": bool(apply and write_allowed),
            "write_allowed": write_allowed,
            "replace_existing": replace_existing,
            "port_activation_needed": activated,
            "validation": {
                **validation,
                "valid": write_allowed,
                "issues": issues,
            },
            "authority_boundary": self.authority_boundary(),
        }

    def _write_local_note(
        self,
        *,
        repo: str,
        directory_name: str,
        note_slug: str,
        title: str,
        summary: str,
        body_markdown: str,
        refs: list[str] | None = None,
        apply: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        repo_root = self._local_repo_root(repo)
        config = LOCAL_NOTE_CONFIG[directory_name]
        safe_slug = _safe_file_slug(note_slug)
        target = self._local_write_target(repo_root, directory_name, safe_slug, str(config["glob_suffix"]))
        refs = [str(ref) for ref in (refs or [])]
        activated, issues = self._local_write_gate(repo_root)
        issues = [*issues, *_validate_public_refs(refs)]
        if len(str(title or "").strip()) < 3:
            issues.append("title must be at least 3 characters")
        if len(str(summary or "").strip()) < 12:
            issues.append("summary must be at least 12 characters")
        if target.exists() and not replace_existing:
            issues.append("target file already exists; set replace_existing=True to overwrite")
        write_allowed = not issues
        frontmatter = {
            "schema_version": config["schema_version"],
            "owner_repo": repo_root.name,
            "status": "draft",
            "title": str(title).strip(),
            "summary": str(summary).strip(),
            "refs": refs,
            "authority_boundary": LOCAL_WRITE_AUTHORITY_BOUNDARY,
        }
        if apply and write_allowed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_note_markdown(frontmatter, str(title).strip(), body_markdown), encoding="utf-8")
            activated = self._maybe_activate_port(repo_root, apply=True)
        return {
            "schema": f"aoa_evals_local_{directory_name[:-1]}_write_v1",
            "repo": repo_root.name,
            "target_path": target.as_posix(),
            "relative_path": _relative_repo_path(target, repo_root),
            "apply": apply,
            "applied": bool(apply and write_allowed),
            "write_allowed": write_allowed,
            "replace_existing": replace_existing,
            "port_activation_needed": activated,
            "frontmatter": frontmatter,
            "validation": {
                "valid": write_allowed,
                "issues": issues,
                "warnings": [],
            },
            "authority_boundary": self.authority_boundary(),
        }

    def write_local_suite_note(
        self,
        repo: str,
        suite_slug: str,
        title: str,
        summary: str,
        body_markdown: str,
        refs: list[str] | None = None,
        *,
        apply: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        return self._write_local_note(
            repo=repo,
            directory_name="suites",
            note_slug=suite_slug,
            title=title,
            summary=summary,
            body_markdown=body_markdown,
            refs=refs,
            apply=apply,
            replace_existing=replace_existing,
        )

    def write_local_report_note(
        self,
        repo: str,
        report_slug: str,
        title: str,
        summary: str,
        body_markdown: str,
        refs: list[str] | None = None,
        *,
        apply: bool = False,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        return self._write_local_note(
            repo=repo,
            directory_name="reports",
            note_slug=report_slug,
            title=title,
            summary=summary,
            body_markdown=body_markdown,
            refs=refs,
            apply=apply,
            replace_existing=replace_existing,
        )

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

    def _eval_need_schema(self) -> tuple[dict[str, Any] | None, Path | None]:
        payload, rel = self._payload_first(EVAL_NEED_SCHEMA, EVAL_NEED_SCHEMA_MIRROR)
        return (payload if isinstance(payload, dict) else None), rel

    def _validate_eval_need(self, proposal: dict[str, Any]) -> dict[str, Any]:
        schema_payload, schema_rel = self._eval_need_schema()
        if schema_payload is None:
            return {
                "valid": False,
                "schema_reader": None,
                "issues": ["eval_need_v1 schema is unavailable from selected aoa-evals root"],
                "warnings": [],
            }
        validator = Draft202012Validator(schema_payload)
        issues: list[str] = []
        for error in sorted(validator.iter_errors(proposal), key=lambda item: (list(item.path), item.message)):
            location = "/".join(str(part) for part in error.path) or "<root>"
            issues.append(f"{location}: {error.message}")
        return {
            "valid": not issues,
            "schema_reader": (self.evals_root / schema_rel).as_posix() if schema_rel else None,
            "issues": issues,
            "warnings": [],
        }

    def _runtime_export_refs_for_proposal(
        self,
        proof_question: str,
        match_names: set[str],
        explicit_refs: list[str],
    ) -> list[dict[str, Any]]:
        tokens = _runtime_export_match_tokens(proof_question)
        explicit_ref_set = _explicit_runtime_export_ref_ids(explicit_refs)
        refs: list[dict[str, Any]] = []
        for entry in self.runtime_candidate_exports(limit=25).get("candidates", []):
            validation = entry.get("validation") if isinstance(entry.get("validation"), dict) else {}
            matched_eval_refs = {
                str(ref)
                for ref in validation.get("matched_eval_refs", [])
                if isinstance(ref, str)
            }
            identifiers = {
                str(entry.get("record_id") or "").casefold(),
                str(entry.get("candidate_id") or "").casefold(),
            }
            haystack = " ".join(
                str(value or "")
                for value in (
                    entry.get("record_id"),
                    entry.get("candidate_id"),
                    entry.get("title"),
                    entry.get("summary"),
                    entry.get("surface_type"),
                    " ".join(sorted(matched_eval_refs)),
                )
            ).casefold()
            token_hits = sum(1 for token in tokens if token in haystack)
            explicit_match = bool(explicit_ref_set & identifiers)
            eval_match = bool(match_names & matched_eval_refs)
            token_match = bool(tokens and token_hits >= min(2, len(tokens)))
            if explicit_ref_set:
                if not explicit_match:
                    continue
            elif not (eval_match or token_match):
                continue
            refs.append(
                {
                    "record_id": entry.get("record_id"),
                    "candidate_id": entry.get("candidate_id"),
                    "surface_type": entry.get("surface_type"),
                    "validation_valid": validation.get("valid"),
                    "matched_eval_refs": sorted(matched_eval_refs),
                    "candidate_payload_included": False,
                    "read_route": (
                        "aoa_evals_read_runtime_candidate_export"
                        f"(record_id={str(entry.get('record_id') or '')!r}, include_payload=False)"
                    ),
                }
            )
        return refs

    def _draft_eval_need_proposal(
        self,
        *,
        proof_question: str,
        input_proposal: dict[str, Any],
        existing_matches: list[dict[str, Any]],
        runtime_export_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        top_match = existing_matches[0] if existing_matches else {}
        related_eval_refs = _string_list(input_proposal.get("related_eval_refs"))
        if not related_eval_refs and existing_matches:
            related_eval_refs = [
                str(match.get("name"))
                for match in existing_matches[:3]
                if str(match.get("name") or "").startswith("aoa-")
            ]

        candidate_evidence_refs = _string_list(input_proposal.get("candidate_evidence_refs"))
        for ref in runtime_export_refs:
            record_id = str(ref.get("record_id") or "")
            if record_id:
                candidate_evidence_refs.append(f"runtime-candidate-export:{record_id}")
        candidate_evidence_refs = sorted(set(candidate_evidence_refs))

        quest_refs = _string_list(input_proposal.get("quest_refs"))
        authoring_route = str(input_proposal.get("authoring_route") or "").strip()
        if authoring_route not in {
            "existing_eval_route",
            "candidate_evidence_packet",
            "quest_record",
            "new_draft_bundle",
        }:
            if related_eval_refs:
                authoring_route = "existing_eval_route"
            elif candidate_evidence_refs:
                authoring_route = "candidate_evidence_packet"
            elif quest_refs:
                authoring_route = "quest_record"
            else:
                authoring_route = "new_draft_bundle"

        category = _enum_value(
            input_proposal.get("category") or top_match.get("category"),
            {"capability", "workflow", "boundary", "artifact", "regression", "comparative", "longitudinal", "stress"},
            "workflow",
        )
        claim_type = _enum_value(
            input_proposal.get("claim_type") or top_match.get("claim_type"),
            {"bounded", "comparative", "regression", "longitudinal"},
            "bounded",
        )
        baseline_mode = _enum_value(
            input_proposal.get("baseline_mode") or top_match.get("baseline_mode"),
            {"none", "fixed-baseline", "previous-version", "peer-compare", "longitudinal-window"},
            "none",
        )
        report_format = _enum_value(
            input_proposal.get("report_format") or top_match.get("report_format"),
            {"summary", "summary-with-breakdown", "comparative-summary"},
            "summary-with-breakdown",
        )

        proposal: dict[str, Any] = {
            "schema_version": "eval_need_v1",
            "name": _eval_need_name(proof_question, input_proposal, existing_matches),
            "proof_question": _bounded_text(proof_question, "Unspecified proof question needs scoped eval routing."),
            "origin_need": _bounded_text(
                input_proposal.get("origin_need"),
                f"OS Abyss needs a bounded eval route for: {proof_question or 'unspecified proof pressure'}",
            ),
            "summary": _bounded_text(
                input_proposal.get("summary") or top_match.get("summary"),
                f"Route and evaluate only the bounded claim named by: {proof_question or 'this proof pressure'}",
            ),
            "object_under_evaluation": _bounded_text(
                input_proposal.get("object_under_evaluation") or top_match.get("object_under_evaluation"),
                "bounded OS Abyss proof surface",
            ),
            "category": category,
            "claim_type": claim_type,
            "baseline_mode": baseline_mode,
            "report_format": report_format,
            "authoring_route": authoring_route,
            "expected_use_when": _string_list(input_proposal.get("expected_use_when"))
            or [_bounded_text(proof_question, "a bounded OS Abyss proof question needs routing")],
            "blind_spot_notes": _string_list(input_proposal.get("blind_spot_notes"))
            or [
                "does not prove broad agent competence",
                "does not accept runtime evidence without bundle-local review",
            ],
        }
        for optional_key in ("verdict_shape", "technique_dependencies", "skill_dependencies"):
            if optional_key in input_proposal:
                proposal[optional_key] = input_proposal[optional_key]
        if related_eval_refs:
            proposal["related_eval_refs"] = sorted(set(related_eval_refs))
        if candidate_evidence_refs:
            proposal["candidate_evidence_refs"] = candidate_evidence_refs
        if quest_refs:
            proposal["quest_refs"] = sorted(set(quest_refs))

        source_refs = _string_list(input_proposal.get("source_refs"))
        for match in existing_matches[:3]:
            eval_path = str(match.get("eval_path") or "")
            if eval_path:
                source_refs.append(f"repo:aoa-evals/{eval_path}")
        if source_refs:
            proposal["source_refs"] = sorted(set(source_refs))

        comparison_surface = input_proposal.get("comparison_surface")
        if baseline_mode == "none":
            proposal["comparison_surface"] = None
        elif comparison_surface is not None:
            proposal["comparison_surface"] = comparison_surface
        else:
            proposal["comparison_surface"] = {
                "baseline_mode": baseline_mode,
                "status": "proposal_only_requires_bundle_local_review",
            }
        return proposal

    def find_or_propose(
        self,
        proof_question: str = "",
        proposal: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        input_proposal = proposal if isinstance(proposal, dict) else {}
        effective_question = str(input_proposal.get("proof_question") or proof_question or "").strip()
        filters = {
            key: input_proposal[key]
            for key in ("category", "claim_type", "baseline_mode")
            if input_proposal.get(key)
        }
        selection = self.select(effective_question, {**filters, "limit": 8} if filters else {"limit": 8})
        existing_matches = selection["matches"]
        match_names = {str(match.get("name") or "") for match in existing_matches}
        runtime_export_refs = self._runtime_export_refs_for_proposal(
            effective_question,
            match_names,
            _string_list(input_proposal.get("candidate_evidence_refs")),
        )
        proposal_packet = self._draft_eval_need_proposal(
            proof_question=effective_question,
            input_proposal=input_proposal,
            existing_matches=existing_matches,
            runtime_export_refs=runtime_export_refs,
        )
        proposal_validation = self._validate_eval_need(proposal_packet)
        authoring_route = proposal_packet["authoring_route"]
        outcome_by_route = {
            "existing_eval_route": "existing_route_required",
            "candidate_evidence_packet": "candidate_evidence_route",
            "quest_record": "quest_route",
            "new_draft_bundle": "new_draft_candidate",
        }
        route_notes: list[str] = []
        if existing_matches:
            route_notes.append("inspect likely existing source eval routes before authoring a parallel bundle")
        if runtime_export_refs:
            route_notes.append("stack-owned runtime candidate exports can be routed as candidate evidence only")
        if authoring_route == "new_draft_bundle":
            route_notes.append("new draft creation remains repo-local and requires scaffold helper review gates")
        if not proposal_validation["valid"]:
            route_notes.append("fix the candidate eval_need_v1 packet before any repo-local scaffold attempt")

        return {
            "schema": "aoa_evals_find_or_propose_v1",
            "read_only": True,
            "source_mutation_allowed": False,
            "candidate_only": True,
            "proof_question": effective_question,
            "outcome": outcome_by_route[authoring_route],
            "existing_matches": existing_matches,
            "runtime_candidate_export_refs": runtime_export_refs,
            "proposal_context": {
                "schema_version": "eval_need_v1",
                "schema_reader": proposal_validation.get("schema_reader"),
                "packet": proposal_packet,
                "repo_local_scaffold_route": (
                    "python mechanics/proof-object/parts/eval-authoring/scripts/"
                    "scaffold_eval_bundle.py --proposal <eval_need.json> --json"
                ),
            },
            "proposal_validation": proposal_validation,
            "route_notes": route_notes,
            "next_route": (
                "inspect existing bundle refs or run the repo-local eval-authoring scaffold helper; "
                "MCP must not write source"
            ),
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
        _, intake_rel = self._payload_first(RUNTIME_INTAKE, RUNTIME_INTAKE_MIRROR)
        _, template_rel = self._payload_first(RUNTIME_TEMPLATE_INDEX, RUNTIME_TEMPLATE_INDEX_MIRROR)
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
            "source_reader": (self.evals_root / (intake_rel or template_rel or RUNTIME_INTAKE)).as_posix(),
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
        _, intake_rel = self._payload_first(RUNTIME_INTAKE, RUNTIME_INTAKE_MIRROR)
        _, template_rel = self._payload_first(RUNTIME_TEMPLATE_INDEX, RUNTIME_TEMPLATE_INDEX_MIRROR)
        return {
            "schema": "aoa_evals_runtime_candidate_templates_v1",
            "count": len(templates),
            "templates": templates,
            "source_reader": (self.evals_root / (intake_rel or template_rel or RUNTIME_INTAKE)).as_posix(),
            "candidate_posture": "candidate_until_eval_review",
            "authority_boundary": self.authority_boundary(),
        }

    def _root_reader_status(self, root: Path | None) -> dict[str, Any]:
        if root is None:
            return {"exists": False, "path": None, "readers": {}, "missing_groups": list(READER_GROUPS)}
        readers: dict[str, Any] = {}
        missing: list[str] = []
        max_mtime = 0.0
        for group, rels in READER_GROUPS.items():
            found = next((rel for rel in rels if (root / rel).is_file()), None)
            if found is None:
                missing.append(group)
                readers[group] = {"present": False, "path": None}
                continue
            path = root / found
            stat = path.stat()
            max_mtime = max(max_mtime, stat.st_mtime)
            readers[group] = {
                "present": True,
                "path": path.as_posix(),
                "mtime_utc": _utc_from_timestamp(stat.st_mtime),
            }
        return {
            "exists": root.exists(),
            "path": root.as_posix(),
            "git_commit": _git_commit(root),
            "latest_reader_mtime_utc": _utc_from_timestamp(max_mtime) if max_mtime else None,
            "readers": readers,
            "missing_groups": missing,
        }

    def runtime_status(self) -> dict[str, Any]:
        selected = self._root_reader_status(self.evals_root)
        source = self._root_reader_status(self.source_root)
        mirror = self._root_reader_status(self.mirror_root)
        manifest = _read_json(self.mirror_root / MIRROR_MANIFEST) if self.mirror_root and (self.mirror_root / MIRROR_MANIFEST).is_file() else None
        candidate_exports = self.runtime_candidate_exports(limit=0)

        freshness_status = "source"
        freshness_notes: list[str] = []
        if self.root_kind == "approved_mirror":
            if not self.mirror_root or not self.mirror_root.exists():
                freshness_status = "mirror_missing"
                freshness_notes.append("approved mirror path is missing")
            elif not manifest:
                freshness_status = "mirror_missing_manifest"
                freshness_notes.append("approved mirror lacks manifest/federation_mirror_manifest.json")
            elif source.get("git_commit") and manifest.get("source_git_commit") != source.get("git_commit"):
                freshness_status = "mirror_source_mismatch"
                freshness_notes.append("mirror manifest source_git_commit differs from source checkout")
            else:
                freshness_status = "mirror_manifest_ok"
        elif self.mirror_root and self.mirror_root.exists():
            freshness_status = "source_with_mirror_available" if manifest else "source_with_unmanifested_mirror"
            if not manifest:
                freshness_notes.append("mirror exists but lacks provenance manifest")

        return {
            "schema": "aoa_evals_runtime_status_v1",
            "workspace_root": self.workspace_root.as_posix(),
            "selected_root": self.evals_root.as_posix(),
            "root_kind": self.root_kind,
            "source_root": self.source_root.as_posix() if self.source_root else None,
            "mirror_root": self.mirror_root.as_posix() if self.mirror_root else None,
            "selected": selected,
            "source": source,
            "mirror": mirror,
            "mirror_manifest": manifest,
            "catalog_count": len(self.catalog_records()),
            "runtime_candidate_template_count": len(self.runtime_intake_templates() or self.runtime_templates()),
            "runtime_candidate_export_count": candidate_exports["count"],
            "runtime_candidate_export_root": candidate_exports["export_root"],
            "freshness": {
                "status": freshness_status,
                "notes": freshness_notes,
                "refresh_command": "scripts/aoa-sync-federation-surfaces --layer aoa-evals",
                "mirror_is_authority": False,
            },
            "authority_boundary": self.authority_boundary(),
        }

    def _runtime_candidate_export_root(self) -> Path | None:
        if self.stack_runtime_root is None:
            return None
        return self.stack_runtime_root / RUNTIME_CANDIDATE_EXPORT_ROOT

    def _runtime_candidate_export_files(self, include_archived: bool = True) -> list[tuple[str, Path]]:
        export_root = self._runtime_candidate_export_root()
        if export_root is None or not export_root.exists():
            return []
        files: list[tuple[str, Path]] = []
        latest_root = export_root / "latest"
        for dir_name in RUNTIME_CANDIDATE_LATEST_DIRS:
            directory = latest_root / dir_name
            if not directory.is_dir():
                continue
            try:
                files.extend(("latest", path) for path in sorted(directory.glob("*.private.json")) if path.is_file())
            except OSError:
                continue
        if include_archived:
            records_root = export_root / "records"
            if records_root.is_dir():
                try:
                    files.extend(
                        ("record", path)
                        for path in sorted(records_root.glob("*/candidate.private.json"))
                        if path.is_file()
                    )
                except OSError:
                    pass
        return files

    def _candidate_validation_summary(self, candidate_payload: Any) -> dict[str, Any]:
        if not isinstance(candidate_payload, dict):
            return {
                "valid": False,
                "surface_type": None,
                "candidate_id": None,
                "issues": ["candidate_payload must be an object"],
                "warnings": [],
            }
        validation = self.validate_evidence_candidate(candidate_payload)
        return {
            "valid": validation["valid"],
            "surface_type": validation.get("surface_type"),
            "candidate_id": validation.get("candidate_id"),
            "matched_eval_refs": validation.get("matched_eval_refs", []),
            "unknown_eval_refs": validation.get("unknown_eval_refs", []),
            "issues": validation.get("issues", []),
            "warnings": validation.get("warnings", []),
        }

    def _runtime_candidate_export_summary(
        self,
        path: Path,
        location: str,
        *,
        include_payload: bool = False,
        detail: bool = False,
    ) -> dict[str, Any]:
        payload = _read_json(path)
        if not isinstance(payload, dict):
            raise ValueError(f"candidate export must be a JSON object: {path}")
        candidate_payload = payload.get("candidate_payload")
        validation = self._candidate_validation_summary(candidate_payload)
        candidate_id = (
            validation.get("candidate_id")
            or payload.get("selection_id")
            or payload.get("hook_id")
            or payload.get("record_id")
        )
        result: dict[str, Any] = {
            "record_id": str(payload.get("record_id") or path.stem),
            "artifact_kind": payload.get("artifact_kind"),
            "capture_mode": payload.get("capture_mode"),
            "exported_at": payload.get("exported_at"),
            "exported_by": payload.get("exported_by"),
            "title": payload.get("title"),
            "summary": payload.get("summary"),
            "candidate_id": str(candidate_id or ""),
            "surface_type": validation.get("surface_type"),
            "location": location,
            "path": path.as_posix(),
            "validation": validation,
            "candidate_payload_included": include_payload,
            "candidate_posture": "runtime_export_is_private_candidate_not_accepted_proof",
        }
        if detail:
            result.update(
                {
                    "source_input_ref": payload.get("source_input_ref"),
                    "source_input_sha256": payload.get("source_input_sha256"),
                    "aoa_evals_contract_refs": payload.get("aoa_evals_contract_refs", []),
                }
            )
        if include_payload:
            result["candidate_payload"] = candidate_payload
        return result

    @staticmethod
    def _dedupe_candidate_exports(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_record: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key = str(entry.get("record_id") or entry.get("path") or "")
            current = by_record.get(key)
            if current is None:
                entry["locations"] = [entry["location"]]
                entry["paths"] = [entry["path"]]
                by_record[key] = entry
                continue
            current.setdefault("locations", []).append(entry["location"])
            current.setdefault("paths", []).append(entry["path"])
            if current.get("location") != "record" and entry.get("location") == "record":
                entry["locations"] = current["locations"]
                entry["paths"] = current["paths"]
                by_record[key] = entry
        return list(by_record.values())

    def runtime_candidate_exports(self, limit: int | None = 20, include_archived: bool = True) -> dict[str, Any]:
        export_root = self._runtime_candidate_export_root()
        entries: list[dict[str, Any]] = []
        invalid_exports: list[dict[str, str]] = []
        for location, path in self._runtime_candidate_export_files(include_archived=include_archived):
            try:
                entries.append(self._runtime_candidate_export_summary(path, location))
            except ValueError as exc:
                invalid_exports.append({"path": path.as_posix(), "error": str(exc)})
        entries = self._dedupe_candidate_exports(entries)
        entries.sort(key=lambda item: (str(item.get("exported_at") or ""), str(item.get("record_id") or "")), reverse=True)
        invalid_shape_entries = [
            entry
            for entry in entries
            if isinstance(entry.get("validation"), dict) and entry["validation"].get("valid") is not True
        ]
        limit_value = max(0, min(int(limit if limit is not None else 20), 100))
        visible = entries[:limit_value] if limit_value else []
        return {
            "schema": "aoa_evals_runtime_candidate_exports_v1",
            "stack_runtime_root": self.stack_runtime_root.as_posix() if self.stack_runtime_root else None,
            "export_root": export_root.as_posix() if export_root else None,
            "count": len(entries),
            "invalid_count": len(invalid_exports),
            "invalid_exports": invalid_exports,
            "candidate_validation": {
                "valid_shape_count": len(entries) - len(invalid_shape_entries),
                "invalid_shape_count": len(invalid_shape_entries),
                "latest_invalid_shape": [
                    {
                        "record_id": entry.get("record_id"),
                        "candidate_id": entry.get("candidate_id"),
                        "surface_type": entry.get("surface_type"),
                        "path": entry.get("path"),
                        "issues": (entry.get("validation") or {}).get("issues", [])[:8],
                    }
                    for entry in invalid_shape_entries[:10]
                ],
                "posture": "invalid_private_candidates_are_reported_for_review_not_accepted_as_proof",
            },
            "limit": limit_value,
            "candidates": visible,
            "private_payloads_included": False,
            "read_only": True,
            "candidate_posture": "stack_owned_private_exports_require_bundle_local_review",
            "authority_boundary": self.authority_boundary(),
        }

    def read_runtime_candidate_export(self, record_id: str, include_payload: bool = False) -> dict[str, Any]:
        target = str(record_id or "").casefold()
        if not target:
            raise ValueError("record_id is required")
        matches: list[dict[str, Any]] = []
        for location, path in self._runtime_candidate_export_files(include_archived=True):
            try:
                entry = self._runtime_candidate_export_summary(
                    path,
                    location,
                    include_payload=include_payload,
                    detail=True,
                )
            except ValueError:
                continue
            identifiers = {
                str(entry.get("record_id") or "").casefold(),
                str(entry.get("candidate_id") or "").casefold(),
                path.stem.casefold(),
                path.parent.name.casefold(),
            }
            if target in identifiers:
                matches.append(entry)
        if not matches:
            raise ValueError(f"unknown runtime candidate export: {record_id}")
        matches.sort(key=lambda item: (item.get("location") != "record", str(item.get("exported_at") or "")))
        selected = matches[0]
        selected["schema"] = "aoa_evals_runtime_candidate_export_v1"
        selected["matched_locations"] = [entry["location"] for entry in matches]
        selected["matched_paths"] = [entry["path"] for entry in matches]
        selected["read_only"] = True
        selected["authority_boundary"] = self.authority_boundary()
        return selected

    def runtime_evidence_schema_resource(self) -> dict[str, Any]:
        schemas: dict[str, Any] = {}
        for surface_type, rels in {
            "runtime_evidence_selection": (RUNTIME_EVIDENCE_SCHEMA, RUNTIME_EVIDENCE_SCHEMA_MIRROR),
            "artifact_to_verdict_hook": (ARTIFACT_HOOK_SCHEMA, ARTIFACT_HOOK_SCHEMA_MIRROR),
            "runtime_candidate_template_index": (RUNTIME_TEMPLATE_SCHEMA, RUNTIME_TEMPLATE_SCHEMA_MIRROR),
        }.items():
            payload, rel = self._payload_first(*rels)
            schemas[surface_type] = {
                "present": payload is not None,
                "source_reader": (self.evals_root / rel).as_posix() if rel else None,
                "schema_id": payload.get("$id") if isinstance(payload, dict) else None,
            }
        return {
            "schema": "aoa_evals_runtime_evidence_schema_resource_v1",
            "schemas": schemas,
            "candidate_posture": "schema_validity_is_not_evidence_acceptance",
            "authority_boundary": self.authority_boundary(),
        }

    def _schema_for_candidate(self, surface_type: str) -> tuple[dict[str, Any] | None, Path | None]:
        rels_by_type = {
            "runtime_evidence_selection": (RUNTIME_EVIDENCE_SCHEMA, RUNTIME_EVIDENCE_SCHEMA_MIRROR),
            "artifact_to_verdict_hook": (ARTIFACT_HOOK_SCHEMA, ARTIFACT_HOOK_SCHEMA_MIRROR),
        }
        rels = rels_by_type.get(surface_type)
        if not rels:
            return None, None
        payload, rel = self._payload_first(*rels)
        return (payload if isinstance(payload, dict) else None), rel

    def validate_evidence_candidate(self, packet: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        warnings: list[str] = []
        if not isinstance(packet, dict):
            return {
                "schema": "aoa_evals_evidence_candidate_validation_v1",
                "valid": False,
                "issues": ["packet must be an object"],
                "warnings": [],
                "authority_boundary": self.authority_boundary(),
            }

        surface_type = str(packet.get("surface_type") or "")
        candidate_id = str(packet.get("selection_id") or packet.get("hook_id") or "")
        candidate_id_slug = _slug(candidate_id)
        schema_payload, schema_rel = self._schema_for_candidate(surface_type)
        if schema_payload is None:
            issues.append(f"unsupported or missing schema for surface_type {surface_type!r}")
        else:
            validator = Draft202012Validator(schema_payload)
            for error in sorted(validator.iter_errors(packet), key=lambda item: list(item.path)):
                location = "/".join(str(part) for part in error.path) or "<root>"
                issues.append(f"{location}: {error.message}")

        known_eval_names = {str(record.get("name") or "") for record in self.catalog_records()}
        template_names = {str(template.get("template_name") or "") for template in self.runtime_intake_templates() or self.runtime_templates()}
        template_eval_anchors = {str(template.get("eval_anchor") or "") for template in self.runtime_intake_templates() or self.runtime_templates()}

        eval_refs: list[str] = []
        if isinstance(packet.get("target_eval"), str):
            eval_refs.append(str(packet["target_eval"]))
        if isinstance(packet.get("eval_anchor"), str):
            eval_refs.append(str(packet["eval_anchor"]))
        if isinstance(packet.get("candidate_eval_refs"), list):
            eval_refs.extend(str(item) for item in packet["candidate_eval_refs"] if isinstance(item, str))

        matched_eval_refs = [
            ref for ref in eval_refs if ref in known_eval_names or ref in template_eval_anchors
        ]
        unknown_eval_refs = [
            ref
            for ref in eval_refs
            if ref.startswith("aoa-") and ref not in known_eval_names and ref not in template_eval_anchors
        ]
        if unknown_eval_refs:
            warnings.append("unknown eval refs require bundle-local review: " + ", ".join(sorted(set(unknown_eval_refs))))

        if surface_type == "runtime_evidence_selection":
            review_posture = packet.get("review_posture") if isinstance(packet.get("review_posture"), dict) else {}
            if review_posture.get("human_review_required") is not True:
                issues.append("review_posture/human_review_required must be true")
        elif surface_type == "artifact_to_verdict_hook":
            report_expectation = packet.get("report_expectation") if isinstance(packet.get("report_expectation"), dict) else {}
            if report_expectation.get("review_required") is not True:
                issues.append("report_expectation/review_required must be true")

        matched_templates = [
            name
            for name in template_names
            if candidate_id_slug and candidate_id_slug in _slug(name)
        ]

        return {
            "schema": "aoa_evals_evidence_candidate_validation_v1",
            "valid": not issues,
            "surface_type": surface_type,
            "candidate_id": candidate_id,
            "schema_reader": (self.evals_root / schema_rel).as_posix() if schema_rel else None,
            "matched_eval_refs": sorted(set(matched_eval_refs)),
            "unknown_eval_refs": sorted(set(unknown_eval_refs)),
            "matched_templates": sorted(set(matched_templates)),
            "issues": issues,
            "warnings": warnings,
            "candidate_posture": "valid_shape_only_until_bundle_local_review",
            "next_route": "bundle-local review before bounded report or optional receipt",
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
        if parts == ["runtime-status"]:
            return self.runtime_status()
        if parts == ["runtime-evidence", "schema"]:
            return self.runtime_evidence_schema_resource()
        if parts == ["runtime-candidate-exports"]:
            return self.runtime_candidate_exports()
        if len(parts) == 2 and parts[0] == "runtime-candidate-export":
            return self.read_runtime_candidate_export(parts[1])
        if parts == ["reports"]:
            return self.reports()
        if parts == ["local-ports"]:
            return self.local_ports()
        if len(parts) == 2 and parts[0] == "local-port":
            return self.local_port(parts[1])
        if len(parts) == 3 and parts[0] == "local-port" and parts[2] == "intake":
            return {
                "schema": "aoa_evals_local_port_intake_v1",
                "repo": parts[1],
                "intake": self._local_intake_records(self._local_repo_root(parts[1])),
                "authority_boundary": self.authority_boundary(),
            }
        if len(parts) == 3 and parts[0] == "local-port" and parts[2] in {"suites", "reports"}:
            return {
                "schema": f"aoa_evals_local_port_{parts[2]}_v1",
                "repo": parts[1],
                parts[2]: self._local_note_records(self._local_repo_root(parts[1]), parts[2]),
                "authority_boundary": self.authority_boundary(),
            }
        if len(parts) == 2 and parts[0] == "bundle":
            return self.inspect_bundle(parts[1])
        if len(parts) == 3 and parts[0] == "bundle" and parts[2] == "sections":
            return self.expand_bundle(parts[1])
        raise ValueError(f"unsupported aoa-evals resource: {uri}")
