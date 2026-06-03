"""Decision index metadata and generated read-model contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


DECISIONS_DIR = Path("docs/decisions")
INDEXES_DIR = DECISIONS_DIR / "indexes"
INDEX_CONTRACT_PATH = INDEXES_DIR / "index_contract.yaml"
INDEX_CONTRACT_SCHEMA = "abyss_stack_decision_index_contract_v1"
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
DECISION_ID_RE = re.compile(r"^- Decision ID: (ABYSS-STACK-D-(\d{4}))$", re.MULTILINE)
DATE_VALUE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FULL_ID_FILENAME_RE = re.compile(r"^(ABYSS-STACK-D-(\d{4}))-.+\.md$")

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
    date: str
    surface_classes: tuple[str, ...]
    stack_lanes: tuple[str, ...]
    mechanic_parents: tuple[str, ...]
    guard_families: tuple[str, ...]
    posture: str

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


def load_decision_record(path: Path, *, repo_root: Path) -> DecisionRecord:
    text = path.read_text(encoding="utf-8")
    relative_path = path.relative_to(repo_root)
    decision_id, number = parse_decision_id(text, path=relative_path)
    title = parse_title(text, path=relative_path)
    metadata = parse_index_metadata(text, path=relative_path)
    return DecisionRecord(
        decision_id=decision_id,
        number=number,
        title=title,
        path=relative_path,
        date=parse_original_date(metadata, path=relative_path),
        surface_classes=split_metadata_value(metadata["surface classes"]),
        stack_lanes=split_metadata_value(metadata["stack lanes"]),
        mechanic_parents=split_metadata_value(metadata["mechanic parents"]),
        guard_families=split_metadata_value(metadata["guard families"]),
        posture=metadata["posture"].strip(),
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
    contract, contract_issues = load_index_contract(repo_root)
    issues.extend(contract_issues)
    if contract is not None:
        issues.extend(validate_index_contract_payload(contract))

    if issues:
        return issues

    rendered = render_index_files(records)
    for relative_path, expected_text in rendered.items():
        path = repo_root / relative_path
        if not path.is_file():
            issues.append((relative_path.as_posix(), "generated decision index is missing"))
            continue
        if path.read_text(encoding="utf-8") != expected_text:
            issues.append(
                (
                    relative_path.as_posix(),
                    "generated decision index is stale; run python scripts/generate_decision_indexes.py",
                )
            )
    return issues
