"""Decision index metadata and generated read-model contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote


DECISIONS_DIR = Path("docs/decisions")
INDEXES_DIR = DECISIONS_DIR / "indexes"
GENERATED_DIR = DECISIONS_DIR / "generated"
INDEX_CONTRACT_PATH = INDEXES_DIR / "index_contract.yaml"
INDEX_CONTRACT_SCHEMA = "abyss_stack_decision_index_contract_v1"
DECISION_GRAPH_SCHEMA = "abyss_stack_decision_graph_v1"
DECISION_ID_PREFIX = "ABYSS-STACK-D"
PATH_POLICY = "full_canonical_id_filename"
SOURCE_GLOB = "docs/decisions/ABYSS-STACK-D-*.md"
REQUIRED_METADATA = (
    "Original date",
    "Surface classes",
    "Stack lanes",
    "Mechanic parents",
    "Guard families",
    "Posture",
)
GENERATED_INDEX_PATHS = (
    INDEXES_DIR / "README.md",
    INDEXES_DIR / "by-number.md",
    INDEXES_DIR / "by-date.md",
    INDEXES_DIR / "by-surface.md",
    INDEXES_DIR / "by-stack-lane.md",
    INDEXES_DIR / "by-mechanic.md",
    INDEXES_DIR / "by-guard.md",
)
GENERATED_GRAPH_PATHS = (
    GENERATED_DIR / "README.md",
    GENERATED_DIR / "decision_graph.json",
)
STATIC_DECISION_SURFACE_PATHS = (
    DECISIONS_DIR / "AGENTS.md",
    DECISIONS_DIR / "README.md",
    DECISIONS_DIR / "TEMPLATE.md",
)
LOCAL_DECISION_SURFACE_PATHS = (
    *STATIC_DECISION_SURFACE_PATHS,
    INDEX_CONTRACT_PATH,
    *GENERATED_INDEX_PATHS,
    *GENERATED_GRAPH_PATHS,
)
DECISION_ID_RE = re.compile(r"^- Decision ID: (ABYSS-STACK-D-(\d{4}))$", re.MULTILINE)
DATE_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FULL_ID_FILENAME_RE = re.compile(r"^(ABYSS-STACK-D-(\d{4}))-.+\.md$")
TOP_METADATA_RE = re.compile(r"^- (?P<key>[A-Za-z][A-Za-z0-9 _-]*):\s*(?P<value>.*)$", re.MULTILINE)
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
DECISION_ID_TOKEN_RE = re.compile(r"ABYSS-STACK-D-\d{4}")

SURFACE_CLASS_ORDER = (
    "root/topology",
    "authority/boundary",
    "docs route",
    "runtime topology",
    "runtime profile",
    "source/runtime boundary",
    "mechanic package",
    "mechanic part",
    "MCP access plane",
    "federation/read-model",
    "host bridge",
    "machine evidence",
    "quest/lane",
    "generated/readout",
    "validation guard",
    "legacy/provenance",
)
STACK_LANE_ORDER = (
    "runtime root",
    "runtime mechanics",
    "source checkout",
    "config projection",
    "runtime lifecycle",
    "machine fit",
    "inference pilots",
    "service selection",
    "profiles and presets",
    "systemd units",
    "docs and routes",
    "questbook",
    "MCP services",
    "federation seams",
    "governed execution",
    "diagnostics",
    "runtime repair",
    "decision lane",
)
MECHANIC_PARENT_ORDER = (
    "agon-runtime",
    "config-projection",
    "diagnostic-spine",
    "experience-runtime",
    "federation-seams",
    "governed-execution",
    "inference-pilots",
    "machine-fit",
    "runtime-lifecycle",
    "runtime-repair",
    "cross-mechanic",
)
GUARD_FAMILY_ORDER = (
    "decision index/read-model",
    "docs route",
    "source/runtime boundary",
    "runtime topology",
    "public-safe config",
    "profile composition",
    "host evidence freshness",
    "MCP port confinement",
    "read-only access plane",
    "service selection",
    "questbook",
    "systemd allowlist",
    "legacy containment",
    "release/tooling",
    "validation lane",
)


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    number: int
    title: str
    path: Path
    status: str
    date: str
    owner_surfaces: tuple[str, ...]
    surface_classes: tuple[str, ...]
    stack_lanes: tuple[str, ...]
    mechanic_parents: tuple[str, ...]
    guard_families: tuple[str, ...]
    posture: str
    source_surfaces: tuple[str, ...]
    superseded_by: tuple[str, ...]

    @property
    def repo_path(self) -> str:
        return self.path.as_posix()

    @property
    def index_link(self) -> str:
        return f"../{self.path.name}"


def split_metadata_value(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not value or value == "none":
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def split_inline_code_or_value(value: str) -> tuple[str, ...]:
    coded_values = tuple(item.strip() for item in INLINE_CODE_RE.findall(value) if item.strip())
    if coded_values:
        return coded_values
    return split_metadata_value(value)


def parse_title(text: str, *, path: Path) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    raise ValueError(f"{path.as_posix()} is missing a level-one title")


def parse_decision_id(text: str, *, path: Path) -> tuple[str, int]:
    match = DECISION_ID_RE.search(text)
    if not match:
        raise ValueError(f"{path.as_posix()} is missing '- Decision ID: ABYSS-STACK-D-####'")
    return match.group(1), int(match.group(2))


def parse_top_metadata(text: str, *, path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    top_section = text.split("\n## ", 1)[0]
    for match in TOP_METADATA_RE.finditer(top_section):
        metadata[match.group("key").strip().lower()] = match.group("value").strip()
    for key in ("status", "owner surface"):
        if key not in metadata:
            raise ValueError(f"{path.as_posix()} is missing top metadata '- {key.title()}: <value>'")
    return metadata


def parse_index_metadata(text: str, *, path: Path) -> dict[str, str]:
    marker = "\n## Index Metadata\n"
    if marker not in text:
        raise ValueError(f"{path.as_posix()} is missing ## Index Metadata")
    section = text.split(marker, 1)[1]
    next_heading = section.find("\n## ")
    if next_heading != -1:
        section = section[:next_heading]

    metadata: dict[str, str] = {}
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        metadata[key.strip().lower()] = value.strip()

    required = {field.lower() for field in REQUIRED_METADATA}
    missing = sorted(required - set(metadata))
    if missing:
        raise ValueError(
            f"{path.as_posix()} index metadata is missing: {', '.join(missing)}"
        )
    return metadata


def parse_original_date(metadata: dict[str, str], *, path: Path) -> str:
    value = metadata["original date"].strip()
    if not DATE_VALUE_RE.match(value):
        raise ValueError(f"{path.as_posix()} original date must use YYYY-MM-DD")
    return value


def parse_bullet_section(text: str, heading: str) -> tuple[str, ...]:
    marker = f"\n## {heading}\n"
    if marker not in text:
        return ()
    section = text.split(marker, 1)[1]
    next_heading = section.find("\n## ")
    if next_heading != -1:
        section = section[:next_heading]

    values: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line.startswith("- "):
            continue
        entry = line[2:].strip()
        values.extend(split_inline_code_or_value(entry))
    return tuple(dict.fromkeys(value for value in values if value))


def parse_superseded_by(top_metadata: dict[str, str]) -> tuple[str, ...]:
    value = top_metadata.get("superseded by", "")
    if not value:
        return ()
    return tuple(dict.fromkeys(DECISION_ID_TOKEN_RE.findall(value)))


def load_decision_record(path: Path, *, repo_root: Path) -> DecisionRecord:
    text = path.read_text(encoding="utf-8")
    relative_path = path.relative_to(repo_root)
    decision_id, number = parse_decision_id(text, path=relative_path)
    title = parse_title(text, path=relative_path)
    top_metadata = parse_top_metadata(text, path=relative_path)
    metadata = parse_index_metadata(text, path=relative_path)
    return DecisionRecord(
        decision_id=decision_id,
        number=number,
        title=title,
        path=relative_path,
        status=top_metadata["status"].lower(),
        date=parse_original_date(metadata, path=relative_path),
        owner_surfaces=split_inline_code_or_value(top_metadata["owner surface"]),
        surface_classes=split_metadata_value(metadata["surface classes"]),
        stack_lanes=split_metadata_value(metadata["stack lanes"]),
        mechanic_parents=split_metadata_value(metadata["mechanic parents"]),
        guard_families=split_metadata_value(metadata["guard families"]),
        posture=metadata["posture"].strip(),
        source_surfaces=parse_bullet_section(text, "Source surfaces"),
        superseded_by=parse_superseded_by(top_metadata),
    )


def collect_decision_records(repo_root: Path) -> tuple[list[DecisionRecord], list[tuple[str, str]]]:
    records: list[DecisionRecord] = []
    issues: list[tuple[str, str]] = []
    decisions_root = repo_root / DECISIONS_DIR
    if not decisions_root.is_dir():
        return records, [(DECISIONS_DIR.as_posix(), "decision directory is missing")]

    for path in sorted(
        item
        for item in decisions_root.glob("*.md")
        if item.name not in {"AGENTS.md", "README.md", "TEMPLATE.md"}
    ):
        try:
            record = load_decision_record(path, repo_root=repo_root)
        except ValueError as exc:
            issues.append((path.relative_to(repo_root).as_posix(), str(exc)))
            continue

        filename_match = FULL_ID_FILENAME_RE.match(record.path.name)
        if not filename_match:
            issues.append(
                (
                    record.repo_path,
                    "decision path must use the full canonical ID filename format",
                )
            )
        elif filename_match.group(1) != record.decision_id:
            issues.append(
                (
                    record.repo_path,
                    "decision path canonical ID must match the note Decision ID",
                )
            )
        elif int(filename_match.group(2)) != record.number:
            issues.append(
                (
                    record.repo_path,
                    "decision path number must match the note Decision ID number",
                )
            )
        records.append(record)

    numbers = [record.number for record in records]
    if len(numbers) != len(set(numbers)):
        issues.append((DECISIONS_DIR.as_posix(), "decision numbers must be unique"))
    if numbers != sorted(numbers):
        issues.append((DECISIONS_DIR.as_posix(), "decision records must sort by number"))

    ids = [record.decision_id for record in records]
    if len(ids) != len(set(ids)):
        issues.append((DECISIONS_DIR.as_posix(), "decision IDs must be unique"))
    return records, issues


def ordered_values(values: Iterable[str], preferred_order: Sequence[str]) -> list[str]:
    seen = set(values)
    ordered = [value for value in preferred_order if value in seen]
    ordered.extend(sorted(seen - set(ordered)))
    return ordered


def display_title(record: DecisionRecord) -> str:
    if record.title.startswith(record.decision_id):
        return record.title
    return f"{record.decision_id} {record.title}"


def bullet_line(record: DecisionRecord) -> str:
    return (
        f"- [{display_title(record)}]({record.index_link}) "
        f"(`{record.repo_path}`)"
    )


def render_generated_notice() -> str:
    return (
        "<!-- Generated by scripts/generate_decision_indexes.py; "
        "do not edit by hand. -->\n\n"
    )


def render_indexes_readme() -> str:
    return (
        "# Decision Lookup Indexes\n\n"
        + render_generated_notice()
        + "These files are generated read models from decision-note `Index Metadata`.\n"
        + "Decision notes own rationale; these indexes only make lookup cheaper for agents.\n\n"
        + "## Indexes\n\n"
        + "- [By number](by-number.md)\n"
        + "- [By date](by-date.md)\n"
        + "- [By surface class](by-surface.md)\n"
        + "- [By stack lane](by-stack-lane.md)\n"
        + "- [By mechanic parent](by-mechanic.md)\n"
        + "- [By validation or guard family](by-guard.md)\n"
        + "\n"
        + "Machine-readable decision graph read models live under "
        + "[../generated/](../generated/README.md).\n"
    )


def render_by_number(records: Sequence[DecisionRecord]) -> str:
    lines = [
        "# Decisions By Number",
        "",
        render_generated_notice().rstrip(),
        "",
        "| Decision ID | Date | Decision | Path | Surface classes | Stack lanes | Mechanic parents | Guard families | Posture |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {decision_id} | {date} | [{title}]({link}) | `{path}` | {surfaces} | {lanes} | {parents} | {guards} | {posture} |".format(
                decision_id=record.decision_id,
                date=record.date,
                title=display_title(record),
                link=record.index_link,
                path=record.repo_path,
                surfaces=", ".join(record.surface_classes) or "none",
                lanes=", ".join(record.stack_lanes) or "none",
                parents=", ".join(record.mechanic_parents) or "none",
                guards=", ".join(record.guard_families) or "none",
                posture=record.posture,
            )
        )
    return "\n".join(lines) + "\n"


def render_by_date(records: Sequence[DecisionRecord]) -> str:
    lines = ["# Decisions By Date", "", render_generated_notice().rstrip(), ""]
    for date in sorted({record.date for record in records}):
        lines.extend([f"## {date}", ""])
        for record in records:
            if record.date == date:
                lines.append(bullet_line(record))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_grouped_index(
    *,
    title: str,
    records: Sequence[DecisionRecord],
    attribute: str,
    preferred_order: Sequence[str],
) -> str:
    values: list[str] = []
    for record in records:
        values.extend(getattr(record, attribute))
    lines = ["# " + title, "", render_generated_notice().rstrip(), ""]
    for value in ordered_values(values, preferred_order):
        lines.extend([f"## {value}", ""])
        for record in records:
            if value in getattr(record, attribute):
                lines.append(bullet_line(record))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_index_files(records: Sequence[DecisionRecord]) -> dict[Path, str]:
    return {
        INDEXES_DIR / "README.md": render_indexes_readme(),
        INDEXES_DIR / "by-number.md": render_by_number(records),
        INDEXES_DIR / "by-date.md": render_by_date(records),
        INDEXES_DIR / "by-surface.md": render_grouped_index(
            title="Decisions By Surface Class",
            records=records,
            attribute="surface_classes",
            preferred_order=SURFACE_CLASS_ORDER,
        ),
        INDEXES_DIR / "by-stack-lane.md": render_grouped_index(
            title="Decisions By Stack Lane",
            records=records,
            attribute="stack_lanes",
            preferred_order=STACK_LANE_ORDER,
        ),
        INDEXES_DIR / "by-mechanic.md": render_grouped_index(
            title="Decisions By Mechanic Parent",
            records=records,
            attribute="mechanic_parents",
            preferred_order=MECHANIC_PARENT_ORDER,
        ),
        INDEXES_DIR / "by-guard.md": render_grouped_index(
            title="Decisions By Validation Or Guard Family",
            records=records,
            attribute="guard_families",
            preferred_order=GUARD_FAMILY_ORDER,
        ),
    }


def graph_node_id(kind: str, value: str) -> str:
    return f"{kind}:{quote(value, safe='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-/')}"


def build_decision_graph(records: Sequence[DecisionRecord]) -> dict[str, object]:
    nodes: dict[str, dict[str, object]] = {}
    edges: dict[tuple[str, str, str], dict[str, str]] = {}

    def add_node(kind: str, value: str, **properties: object) -> str:
        node_id = graph_node_id(kind, value)
        node = nodes.setdefault(
            node_id,
            {
                "id": node_id,
                "type": kind,
                "label": value,
            },
        )
        node.update(properties)
        return node_id

    def add_edge(source: str, target: str, edge_type: str) -> None:
        key = (source, target, edge_type)
        edges.setdefault(
            key,
            {
                "source": source,
                "target": target,
                "type": edge_type,
            },
        )

    repo_id = add_node("repo", "abyss-stack", role="decision_record_owner")

    previous_decision_id: str | None = None
    for record in records:
        decision_node_id = add_node(
            "decision",
            record.decision_id,
            title=display_title(record),
            status=record.status,
            date=record.date,
            path=record.repo_path,
            posture=record.posture,
        )
        add_edge(repo_id, decision_node_id, "OWNS_DECISION")

        if previous_decision_id is not None:
            add_edge(previous_decision_id, decision_node_id, "NEXT_DECISION")
        previous_decision_id = decision_node_id

        date_node_id = add_node("date", record.date)
        status_node_id = add_node("status", record.status)
        add_edge(decision_node_id, date_node_id, "DATED")
        add_edge(decision_node_id, status_node_id, "HAS_STATUS")

        for value in record.owner_surfaces:
            add_edge(decision_node_id, add_node("owner_surface", value), "OWNED_BY_SURFACE")
        for value in record.surface_classes:
            add_edge(decision_node_id, add_node("surface_class", value), "HAS_SURFACE_CLASS")
        for value in record.stack_lanes:
            add_edge(decision_node_id, add_node("stack_lane", value), "IN_STACK_LANE")
        for value in record.mechanic_parents:
            add_edge(decision_node_id, add_node("mechanic_parent", value), "UNDER_MECHANIC_PARENT")
        for value in record.guard_families:
            add_edge(decision_node_id, add_node("guard_family", value), "GUARDED_BY")
        for value in record.source_surfaces:
            add_edge(decision_node_id, add_node("source_surface", value), "CITES_SOURCE_SURFACE")
        for target_decision_id in record.superseded_by:
            add_edge(decision_node_id, graph_node_id("decision", target_decision_id), "SUPERSEDED_BY")

    node_values = sorted(nodes.values(), key=lambda item: str(item["id"]))
    edge_values = sorted(edges.values(), key=lambda item: (item["source"], item["type"], item["target"]))
    node_type_counts: dict[str, int] = {}
    edge_type_counts: dict[str, int] = {}
    for node in node_values:
        node_type = str(node["type"])
        node_type_counts[node_type] = node_type_counts.get(node_type, 0) + 1
    for edge in edge_values:
        edge_type = edge["type"]
        edge_type_counts[edge_type] = edge_type_counts.get(edge_type, 0) + 1

    return {
        "schema": DECISION_GRAPH_SCHEMA,
        "owner": "docs/decisions",
        "source_glob": SOURCE_GLOB,
        "generated_by": "scripts/generate_decision_indexes.py",
        "authority_note": "Decision records own rationale; this graph is a generated navigation read model.",
        "decision_count": len(records),
        "node_count": len(node_values),
        "edge_count": len(edge_values),
        "node_type_counts": dict(sorted(node_type_counts.items())),
        "edge_type_counts": dict(sorted(edge_type_counts.items())),
        "nodes": node_values,
        "edges": edge_values,
    }


def render_decision_graph_json(records: Sequence[DecisionRecord]) -> str:
    return json.dumps(build_decision_graph(records), ensure_ascii=True, indent=2, sort_keys=True) + "\n"


def render_decision_graph_readme(records: Sequence[DecisionRecord]) -> str:
    graph = build_decision_graph(records)
    node_counts = graph["node_type_counts"]
    edge_counts = graph["edge_type_counts"]
    assert isinstance(node_counts, dict)
    assert isinstance(edge_counts, dict)

    lines = [
        "# Decision Graph Read Model",
        "",
        render_generated_notice().rstrip(),
        "",
        "Decision records own rationale; this directory contains generated graph read models for navigation and impact lookup.",
        "",
        "## Files",
        "",
        "- [decision_graph.json](decision_graph.json)",
        "",
        "## Counts",
        "",
        f"- Decisions: {graph['decision_count']}",
        f"- Nodes: {graph['node_count']}",
        f"- Edges: {graph['edge_count']}",
        "",
        "## Node Types",
        "",
    ]
    for node_type, count in node_counts.items():
        lines.append(f"- `{node_type}`: {count}")
    lines.extend(["", "## Edge Types", ""])
    for edge_type, count in edge_counts.items():
        lines.append(f"- `{edge_type}`: {count}")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This graph is source-generated from `docs/decisions/ABYSS-STACK-D-*.md` metadata and source-surface lists.",
            "It does not replace the decision records and does not author runtime truth.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_generated_files(records: Sequence[DecisionRecord]) -> dict[Path, str]:
    rendered = dict(render_index_files(records))
    rendered[GENERATED_DIR / "README.md"] = render_decision_graph_readme(records)
    rendered[GENERATED_DIR / "decision_graph.json"] = render_decision_graph_json(records)
    return rendered


def load_index_contract(repo_root: Path) -> tuple[dict[str, object] | None, list[tuple[str, str]]]:
    path = repo_root / INDEX_CONTRACT_PATH
    if not path.is_file():
        return None, [(INDEX_CONTRACT_PATH.as_posix(), "decision index contract is missing")]

    contract: dict[str, object] = {}
    current_list_key: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - ") and current_list_key is not None:
            value = line[4:].strip()
            existing = contract.setdefault(current_list_key, [])
            if not isinstance(existing, list):
                return None, [(INDEX_CONTRACT_PATH.as_posix(), f"{current_list_key} must be a list")]
            existing.append(value)
            continue
        if line.startswith("  "):
            return None, [(INDEX_CONTRACT_PATH.as_posix(), f"unsupported YAML line: {line}")]
        if ":" not in line:
            return None, [(INDEX_CONTRACT_PATH.as_posix(), f"unsupported YAML line: {line}")]
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            contract[key] = value
            current_list_key = None
        else:
            contract[key] = []
            current_list_key = key
    return contract, []


def validate_index_contract_payload(contract: dict[str, object]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    expected = [path.as_posix() for path in GENERATED_INDEX_PATHS]
    expected_graphs = [path.as_posix() for path in GENERATED_GRAPH_PATHS]
    if contract.get("schema") != INDEX_CONTRACT_SCHEMA:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                f"schema must be {INDEX_CONTRACT_SCHEMA}",
            )
        )
    if contract.get("decision_id_prefix") != DECISION_ID_PREFIX:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                f"decision_id_prefix must be {DECISION_ID_PREFIX}",
            )
        )
    if contract.get("path_policy") != PATH_POLICY:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                f"path_policy must be {PATH_POLICY}",
            )
        )
    if contract.get("source_glob") != SOURCE_GLOB:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                f"source_glob must be {SOURCE_GLOB}",
            )
        )
    if contract.get("generated_indexes") != expected:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                "generated_indexes must match the decision index read-model set",
            )
        )
    if contract.get("generated_graphs") != expected_graphs:
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                "generated_graphs must match the decision graph read-model set",
            )
        )
    if contract.get("required_metadata") != list(REQUIRED_METADATA):
        issues.append(
            (
                INDEX_CONTRACT_PATH.as_posix(),
                "required_metadata must match the parsed decision metadata fields",
            )
        )
    return issues


def validate_decision_index_surfaces(repo_root: Path) -> list[tuple[str, str]]:
    records, issues = collect_decision_records(repo_root)
    issues.extend(validate_decision_lane_surfaces(repo_root))
    contract, contract_issues = load_index_contract(repo_root)
    issues.extend(contract_issues)
    if contract is not None:
        issues.extend(validate_index_contract_payload(contract))

    if issues:
        return issues

    rendered = render_generated_files(records)
    for relative_path, expected_text in rendered.items():
        path = repo_root / relative_path
        if not path.is_file():
            issues.append((relative_path.as_posix(), "generated decision read model is missing"))
            continue
        if path.read_text(encoding="utf-8") != expected_text:
            issues.append(
                (
                    relative_path.as_posix(),
                    "generated decision read model is stale; run python scripts/generate_decision_indexes.py",
                )
            )
    return issues


def validate_decision_lane_surfaces(repo_root: Path) -> list[tuple[str, str]]:
    decisions_root = repo_root / DECISIONS_DIR
    if not decisions_root.is_dir():
        return [(DECISIONS_DIR.as_posix(), "decision directory is missing")]

    allowed_paths = {path.as_posix() for path in LOCAL_DECISION_SURFACE_PATHS}
    issues: list[tuple[str, str]] = []
    for path in sorted(decisions_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(repo_root)
        relative_text = relative.as_posix()
        if relative_text in allowed_paths:
            continue
        if relative.parent == DECISIONS_DIR and FULL_ID_FILENAME_RE.match(path.name):
            continue
        issues.append(
            (
                relative_text,
                "unmodeled decision-lane surface; add it to the local decision surface contract or move it outside docs/decisions",
            )
        )
    return issues
