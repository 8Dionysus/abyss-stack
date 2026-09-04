from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any


MATERIAL_SCHEMA_VERSION = "tos_material_planting_projection_v1"
PUBLIC_PLANTING_AUTHORITIES = {
    "reviewed": "ToS/review-ledger/",
    "canonical": "ToS/canon/",
}
PUBLIC_REVIEW_STATUSES = {
    "accepted",
    "accepted_with_limits",
    "human_accepted",
    "human-adjudicated",
    "human-reviewed",
    "human_reviewed",
    "legal-reviewed",
    "reviewed",
    "canonical",
}

PUBLIC_NODE_TYPES = {
    "agent": "material-agent",
    "artifact_witness": "material-artifact",
    "canon_node": "material-event",
    "collection": "material-collection",
    "corpus_record": "material-record",
    "critical_reconstruction": "material-composite",
    "edition": "material-edition",
    "event": "material-event",
    "expression": "material-expression",
    "inscription": "material-artifact",
    "item": "material-item",
    "organization": "material-organization",
    "place": "material-place",
    "reference": "material-reference",
    "representation": "material-representation",
    "scholarly_composite": "material-composite",
    "synoptic_composite": "material-composite",
    "work": "material-work",
}

PUBLIC_PRESENTATION_TYPES = {
    "agent": "material-agent",
    "place": "material-place",
    "organization": "material-organization",
    "work": "material-work",
    "expression": "material-expression",
    "edition": "material-edition",
    "item": "material-item",
    "artifact": "material-artifact",
    "composite": "material-composite",
    "event": "material-event",
    "representation": "material-representation",
    "reference": "material-reference",
    "relation": "material-relation",
    "cluster": "material-collection",
}

INTERNAL_RECORD_FIELDS = {
    "$schema",
    "schema_version",
    "review_status",
    "authority",
    "rights_refs",
    "source_record_ref",
    "source_record_sha256",
    "source_schema_version",
    "source_record_type",
    "identity_status",
    "reviews",
    "participant_bindings",
    "existing_event_ref",
    "provenance_event_ref",
    "supersedes_ref",
    "source_anchor_refs",
    "derivation_refs",
    "subject_ref",
    "source_ref",
    "source_refs",
    "evidence_refs",
    "review_refs",
}

STRUCTURAL_RELATION_PRESENTATION = {
    "event_participant": {
        "label_ru": "участник события",
        "label_en": "event participant",
    },
    "represents": {
        "label_ru": "представляет",
        "label_en": "represents",
    },
    "derived_from": {
        "label_ru": "создано на основе",
        "label_en": "derived from",
    },
    "references": {
        "label_ru": "указывает на",
        "label_en": "points to",
    },
}


class MaterialProjectionError(RuntimeError):
    """Raised when the optional material planting projection is malformed."""


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def _language_pair(value: Any) -> tuple[str, str] | None:
    payload = _dict(value)
    ru = str(payload.get("ru") or "").strip()
    en = str(payload.get("en") or "").strip()
    return (ru, en) if ru and en else None


def _multilingual(
    ru: str,
    en: str,
    source_ref: str | None = None,
    original: str | None = None,
    translation_status: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "tos_multilingual_label_v1",
        "label": {"original": original, "ru": ru or en, "en": en or ru},
        "language": {"original_language": None, "original_script": None, "transliteration": None},
        "translation_status": translation_status
        or {"original": "pending", "ru": "source", "en": "source"},
        "source_ref": source_ref,
    }


def _source_refs(item: dict[str, Any]) -> list[str]:
    refs: set[str] = set()
    for key in (
        "source_ref",
        "source_record_ref",
        "source_refs",
        "source_owner_refs",
        "evidence_refs",
        "review_refs",
        "rights_refs",
        "derivation_refs",
        "source_anchor_refs",
    ):
        value = item.get(key)
        if isinstance(value, str) and value:
            refs.add(value)
        elif isinstance(value, list):
            refs.update(str(ref) for ref in value if isinstance(ref, str) and ref)
    locator = _dict(item.get("locator"))
    if isinstance(locator.get("record_ref"), str) and locator["record_ref"]:
        refs.add(str(locator["record_ref"]))
    access = _dict(item.get("access"))
    if isinstance(access.get("url"), str) and access["url"]:
        refs.add(str(access["url"]))
    return sorted(refs)


def _primary_source(item: dict[str, Any]) -> str | None:
    refs = _public_source_refs(item)
    return refs[0] if refs else None


def _public_source_refs(item: dict[str, Any]) -> list[str]:
    """Keep public addresses; owner paths and workflow identifiers stay server-side."""
    return [
        ref
        for ref in _source_refs(item)
        if ref.startswith(("https://", "http://", "doi:", "urn:"))
    ]


def _merge_strings(*values: Iterable[str]) -> list[str]:
    return sorted({item for value in values for item in value if item})


def _public_node_type(owner_record: dict[str, Any]) -> str:
    for value in (
        owner_record.get("source_record_type"),
        owner_record.get("record_kind"),
    ):
        public_type = PUBLIC_NODE_TYPES.get(str(value or ""))
        if public_type:
            return public_type
    return "material-record"


def _public_subject_type(existing_type: Any, presentation_kind: Any) -> str:
    existing = str(existing_type or "")
    if existing and existing != "material-record":
        return existing
    return PUBLIC_PRESENTATION_TYPES.get(str(presentation_kind or ""), "material-record")


class MaterialProjectionAdapter:
    """Adapts the source-owned material planting packet to the existing site graph contract."""

    def __init__(self, path: Path, source_root: Path | None = None) -> None:
        self.path = path
        self.source_root = source_root

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> dict[str, Any]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise MaterialProjectionError(f"material projection must be a JSON object: {self.path.as_posix()}")
        if payload.get("schema_version") != MATERIAL_SCHEMA_VERSION:
            raise MaterialProjectionError(f"material projection schema_version must be {MATERIAL_SCHEMA_VERSION}")
        return payload

    def overlay(self) -> dict[str, Any]:
        if not self.exists():
            return {}
        return self._adapt(self.load())

    @staticmethod
    def _public_planting(
        planting: dict[str, Any],
        unresolved_by_id: dict[str, dict[str, Any]],
    ) -> bool:
        posture = str(planting.get("knowledge_posture") or "")
        authority_prefix = PUBLIC_PLANTING_AUTHORITIES.get(posture)
        authority_ref = planting.get("authority_ref")
        if authority_prefix is None or not isinstance(authority_ref, str) or not authority_ref.startswith(authority_prefix):
            return False
        return not any(
            "public_projection" in _string_list(unresolved_by_id.get(ref, {}).get("blocking_for"))
            for ref in _string_list(planting.get("unresolved_refs"))
        )

    @staticmethod
    def _public_relation(relation: dict[str, Any]) -> bool:
        posture = str(relation.get("relation_posture") or "")
        policy = str(relation.get("projection_policy") or "")
        review_status = str(relation.get("review_status") or "")
        review_refs = _string_list(relation.get("review_refs"))
        return (
            review_status in {"accepted", "accepted_with_limits"}
            and bool(review_refs)
            and (
                (posture == "reviewed" and policy == "reviewed_relation")
                or (posture == "canonical" and policy == "canonical_relation")
            )
        )

    @staticmethod
    def _public_record(record: dict[str, Any], *, planting_subject: bool = False) -> bool:
        if _language_pair(record.get("label")) is None:
            return False
        if planting_subject:
            label = record.get("label")
            source_field = str(_dict(label).get("source_field") or "")
            return source_field not in {"abstract", "description", "distilled_thesis", "notes", "source_anchor", "summary"}
        review_status = str(record.get("review_status") or "")
        authority = _dict(record.get("authority"))
        source_ref = str(record.get("source_record_ref") or record.get("source_ref") or "")
        return (
            review_status in PUBLIC_REVIEW_STATUSES
            or authority.get("publication_authority") is True
            or source_ref.startswith("ToS/review-ledger/")
            or source_ref.startswith("ToS/canon/")
        )

    def _adapt(self, payload: dict[str, Any]) -> dict[str, Any]:
        ready_views = [
            item
            for item in _dict_list(payload.get("view_projections"))
            if item.get("status") == "ready" and isinstance(item.get("view_id"), str) and item.get("view_id")
        ]
        if not ready_views:
            return {}

        unresolved_by_id = {
            str(item.get("unresolved_id")): item
            for item in _dict_list(payload.get("unresolved"))
            if isinstance(item.get("unresolved_id"), str)
        }
        all_plantings: dict[str, dict[str, Any]] = {}
        for posture, items in _dict(payload.get("site_plantings_by_posture")).items():
            for planting in _dict_list(items):
                material = dict(planting)
                material.setdefault("knowledge_posture", str(posture))
                planting_id = str(material.get("planting_id") or "")
                if planting_id:
                    all_plantings[planting_id] = material

        plantings = {
            planting_id: planting
            for planting_id, planting in all_plantings.items()
            if self._public_planting(planting, unresolved_by_id)
        }
        if not plantings:
            return {}

        records = _dict(payload.get("records"))
        embedded_records_by_id: dict[str, dict[str, Any]] = {}
        for collection, id_key in (
            ("events", "event_id"),
            ("representations", "representation_id"),
            ("references", "reference_id"),
            ("corpus_records", "record_id"),
        ):
            for record in _dict_list(records.get(collection)):
                record_id = str(record.get(id_key) or "")
                if record_id:
                    embedded_records_by_id[record_id] = record

        owner_records_by_id = {
            str(item.get("record_id")): item
            for item in _dict_list(payload.get("owner_records"))
            if isinstance(item.get("record_id"), str)
        }
        relations_by_id = {
            str(item.get("relation_id")): item
            for item in _dict_list(payload.get("relations"))
            if isinstance(item.get("relation_id"), str)
        }
        plantings = {
            planting_id: planting
            for planting_id, planting in plantings.items()
            if (
                (subject_record := (
                    owner_records_by_id.get(str(planting.get("subject_ref") or ""))
                    or embedded_records_by_id.get(str(planting.get("subject_ref") or ""))
                ))
                and self._public_record(subject_record, planting_subject=True)
            )
        }
        if not plantings:
            return {}

        record_views: dict[str, set[str]] = {}
        relation_views: dict[str, set[str]] = {}
        planting_views: dict[str, set[str]] = {}
        for view in ready_views:
            view_id = str(view["view_id"])
            view_planting_ids = [ref for ref in _string_list(view.get("site_planting_refs")) if ref in plantings]
            for planting_id in view_planting_ids:
                planting_views.setdefault(planting_id, set()).add(view_id)
                planting = plantings[planting_id]
                subject_ref = str(planting.get("subject_ref") or "")
                if subject_ref:
                    record_views.setdefault(subject_ref, set()).add(view_id)
                interactions = _dict(planting.get("interactions"))
                for ref in _merge_strings(
                    _string_list(planting.get("record_refs")),
                    _string_list(interactions.get("hover_record_refs")),
                ):
                    record = owner_records_by_id.get(ref) or embedded_records_by_id.get(ref)
                    if record and self._public_record(record, planting_subject=ref == subject_ref):
                        record_views.setdefault(ref, set()).add(view_id)
                for relation_id in _string_list(interactions.get("relation_refs")):
                    relation = relations_by_id.get(relation_id)
                    if not relation or not self._public_relation(relation):
                        continue
                    relation_views.setdefault(relation_id, set()).add(view_id)
                    for endpoint_key in ("subject_ref", "object_ref"):
                        endpoint = str(relation.get(endpoint_key) or "")
                        if endpoint and (endpoint in owner_records_by_id or endpoint in embedded_records_by_id):
                            record_views.setdefault(endpoint, set()).add(view_id)

        plantings = {
            planting_id: planting
            for planting_id, planting in plantings.items()
            if planting_id in planting_views
        }
        if not plantings:
            return {}

        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        for owner_record in owner_records_by_id.values():
            node_id = str(owner_record.get("record_id") or "")
            if not node_id or node_id not in record_views:
                continue
            label_pair = _language_pair(owner_record.get("label"))
            if label_pair is None:
                continue
            ru, en = label_pair
            label = _dict(owner_record.get("label"))
            original = str(label.get("original") or "") or None
            translation_status = {
                "original": "source" if original else "pending",
                "ru": "source",
                "en": "source",
            }
            summary = _dict(owner_record.get("summary"))
            summary_pair = _language_pair(summary)
            summary_ru = summary_pair[0] if summary_pair else None
            summary_en = summary_pair[1] if summary_pair else None
            self._upsert_node(
                nodes,
                node_id=node_id,
                node_type=_public_node_type(owner_record),
                ru=ru,
                en=en,
                original=original,
                translation_status=translation_status,
                source_refs=_public_source_refs(owner_record),
                view_ids=sorted(record_views.get(node_id, set())),
                graph_layers=["material-record"],
                properties={
                    "public_summary_ru": summary_ru,
                    "public_summary_en": summary_en,
                },
            )

        record_specs = (
            ("events", "event_id", "material-event"),
            ("representations", "representation_id", "material-representation"),
            ("references", "reference_id", "material-reference"),
            ("corpus_records", "record_id", "material-record"),
        )
        for collection, id_key, node_type in record_specs:
            for record in _dict_list(records.get(collection)):
                node_id = str(record.get(id_key) or "")
                if not node_id or node_id not in record_views:
                    continue
                label_pair = _language_pair(record.get("label"))
                if label_pair is None:
                    continue
                ru, en = label_pair
                summary_pair = _language_pair(record.get("description"))
                properties = {
                    key: value
                    for key, value in record.items()
                    if key not in INTERNAL_RECORD_FIELDS | {id_key, "label", "description", "source_refs"}
                }
                if summary_pair:
                    properties["public_summary_ru"] = summary_pair[0]
                    properties["public_summary_en"] = summary_pair[1]
                if node_type == "material-event" and str(properties.get("event_space") or "") == "corpus_provenance":
                    properties["public_role"] = "source_note"
                self._upsert_node(
                    nodes,
                    node_id=node_id,
                    node_type=node_type,
                    ru=ru,
                    en=en,
                    source_refs=_public_source_refs(record),
                    view_ids=sorted(record_views.get(node_id, set())),
                    graph_layers=[node_type],
                    properties=properties,
                )

        for planting in plantings.values():
            planting_id = str(planting.get("planting_id") or "")
            subject_ref = str(planting.get("subject_ref") or "")
            if not planting_id or not subject_ref:
                continue
            subject = nodes.get(subject_ref, {})
            multilingual = _dict(subject.get("multilingual"))
            subject_label = _dict(multilingual.get("label"))
            ru = str(subject_label.get("ru") or subject.get("label") or subject_ref)
            en = str(subject_label.get("en") or subject.get("label") or subject_ref)
            original = subject_label.get("original") if isinstance(subject_label.get("original"), str) else None
            subject_properties = _dict(subject.get("properties"))
            view_ids = sorted(planting_views.get(planting_id, set()))
            self._upsert_node(
                nodes,
                node_id=subject_ref,
                node_type=_public_subject_type(subject.get("node_type"), planting.get("presentation_kind")),
                ru=ru,
                en=en,
                original=original,
                translation_status=_dict(multilingual.get("translation_status")) or None,
                source_refs=_merge_strings(_string_list(subject.get("source_refs")), _public_source_refs(planting)),
                view_ids=view_ids,
                graph_layers=["material-record"],
                properties={
                    "public_summary_ru": subject_properties.get("public_summary_ru"),
                    "public_summary_en": subject_properties.get("public_summary_en"),
                },
            )

        for relation_id, relation in relations_by_id.items():
            if relation_id not in relation_views:
                continue
            subject_ref = str(relation.get("subject_ref") or "")
            object_ref = str(relation.get("object_ref") or "")
            if not subject_ref or not object_ref or subject_ref not in nodes or object_ref not in nodes:
                continue
            view_ids = sorted(relation_views.get(relation_id, set()))
            display = _dict(relation.get("display"))
            edges[relation_id] = {
                "edge_id": relation_id,
                "from_id": subject_ref,
                "to_id": object_ref,
                "predicate_id": str(relation.get("predicate") or "material_relation"),
                "view_ids": view_ids,
                "graph_layers": ["material-relation"],
                "source_ref": _primary_source(relation),
                "source_refs": _public_source_refs(relation),
                "properties": {
                    key: value
                    for key, value in relation.items()
                    if key not in INTERNAL_RECORD_FIELDS
                    | {
                        "relation_id",
                        "subject_ref",
                        "object_ref",
                        "predicate",
                        "relation_posture",
                        "projection_policy",
                        "review_refs",
                    }
                }
                | {"display": display},
            }

        public_records = {
            collection: [
                record
                for record in _dict_list(records.get(collection))
                if str(record.get(id_key) or "") in record_views
            ]
            for collection, id_key in (
                ("events", "event_id"),
                ("representations", "representation_id"),
                ("references", "reference_id"),
                ("corpus_records", "record_id"),
            )
        }
        self._add_structural_edges(nodes, edges, public_records, record_views, set(relations_by_id))

        clusters: list[dict[str, Any]] = []
        for planting in plantings.values():
            planting_id = str(planting.get("planting_id") or "")
            subject_ref = str(planting.get("subject_ref") or "")
            view_ids = sorted(planting_views.get(planting_id, set()))
            if not planting_id or not subject_ref or not view_ids:
                continue
            interactions = _dict(planting.get("interactions"))
            relation_ids = [ref for ref in _string_list(interactions.get("relation_refs")) if ref in edges]
            member_ids: set[str] = {subject_ref}
            member_ids.update(ref for ref in _string_list(interactions.get("hover_record_refs")) if ref in nodes)
            member_ids.update(ref for ref in _string_list(planting.get("record_refs")) if ref in nodes)
            for relation_id in relation_ids:
                member_ids.add(str(edges[relation_id]["from_id"]))
                member_ids.add(str(edges[relation_id]["to_id"]))
            subject = nodes.get(subject_ref, {})
            multilingual = _dict(subject.get("multilingual"))
            subject_label = _dict(multilingual.get("label"))
            subject_properties = _dict(subject.get("properties"))
            cluster_sources = _merge_strings(_public_source_refs(planting), _string_list(subject.get("source_refs")))
            ru = str(subject_label.get("ru") or subject.get("label") or subject_ref)
            en = str(subject_label.get("en") or subject.get("label") or subject_ref)
            original = subject_label.get("original") if isinstance(subject_label.get("original"), str) else None
            layers = ["material-cluster"]
            clusters.append(
                {
                    "cluster_id": planting_id,
                    "cluster_kind": f"material-{planting.get('presentation_kind') or 'cluster'}",
                    "label": ru,
                    "multilingual": _multilingual(
                        ru,
                        en,
                        cluster_sources[0] if cluster_sources else None,
                        original,
                        _dict(multilingual.get("translation_status")) or None,
                    ),
                    "member_node_ids": sorted(member_ids),
                    "member_edge_ids": relation_ids,
                    "view_ids": view_ids,
                    "graph_layers": layers,
                    "source_ref": cluster_sources[0] if cluster_sources else None,
                    "source_refs": cluster_sources,
                    "properties": {
                        "member_count": len(member_ids),
                        "edge_count": len(relation_ids),
                        "public_summary_ru": subject_properties.get("public_summary_ru"),
                        "public_summary_en": subject_properties.get("public_summary_en"),
                    },
                }
            )

        view_payloads: list[dict[str, Any]] = []
        for source_view in ready_views:
            view_id = str(source_view["view_id"])
            if not any(view_id in views for views in planting_views.values()):
                continue
            view_nodes = [node for node in nodes.values() if view_id in _string_list(node.get("view_ids"))]
            view_node_ids = {str(node["node_id"]) for node in view_nodes}
            view_edges = [edge for edge in edges.values() if view_id in _string_list(edge.get("view_ids"))]
            for edge in view_edges:
                for endpoint in (str(edge["from_id"]), str(edge["to_id"])):
                    if endpoint not in view_node_ids and endpoint in nodes:
                        view_nodes.append(nodes[endpoint])
                        view_node_ids.add(endpoint)
            source_refs = sorted(
                {
                    ref
                    for item in [*view_nodes, *view_edges]
                    for ref in _string_list(item.get("source_refs"))
                }
            )
            graph_layers = sorted(
                {
                    layer
                    for item in [*view_nodes, *view_edges]
                    for layer in _string_list(item.get("graph_layers"))
                }
            )
            label_pair = _language_pair(source_view.get("label"))
            description_pair = _language_pair(source_view.get("description"))
            if label_pair is None or description_pair is None:
                continue
            view_ru, view_en = label_pair
            description_ru, description_en = description_pair
            view_payloads.append(
                {
                    "view_id": view_id,
                    "title": view_ru,
                    "public_visibility": "public",
                    "public_presentation": {
                        "label": {"ru": view_ru, "en": view_en},
                        "description": {"ru": description_ru, "en": description_en},
                    },
                    "multilingual": _multilingual(view_ru, view_en),
                    "purpose": description_ru,
                    "properties": {
                        "public_summary_ru": description_ru,
                        "public_summary_en": description_en,
                    },
                    "layout_hint": view_id.replace("_", "-"),
                    "review_intent": "",
                    "route_card": None,
                    "source_ref": source_refs[0] if source_refs else None,
                    "source_refs": source_refs,
                    "graph_layers": graph_layers,
                    "nodes": sorted(view_nodes, key=lambda item: str(item.get("node_id"))),
                    "edges": sorted(view_edges, key=lambda item: str(item.get("edge_id"))),
                }
            )

        graph_layer_ids = sorted(
            {
                layer
                for item in [*nodes.values(), *edges.values(), *clusters]
                for layer in _string_list(item.get("graph_layers"))
            }
        )
        layer_counts = [
            {
                "layer_id": layer,
                "node_count": sum(layer in _string_list(item.get("graph_layers")) for item in nodes.values()),
                "edge_count": sum(layer in _string_list(item.get("graph_layers")) for item in edges.values()),
                "cluster_count": sum(layer in _string_list(item.get("graph_layers")) for item in clusters),
            }
            for layer in graph_layer_ids
        ]
        return {
            "views": view_payloads,
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "clusters": clusters,
            "review_packets": [],
            "graph_layers": [
                {"layer_id": layer, "source_ref": None, "use": "accepted material content"}
                for layer in graph_layer_ids
            ],
            "layer_counts": layer_counts,
            "unresolved_review_surfaces": [],
            "counts": {
                "material_views": len(view_payloads),
                "material_nodes": len(nodes),
                "material_edges": len(edges),
                "material_clusters": len(clusters),
                "material_unresolved": 0,
            },
        }

    @staticmethod
    def _upsert_node(
        nodes: dict[str, dict[str, Any]],
        *,
        node_id: str,
        node_type: str,
        ru: str,
        en: str,
        source_refs: list[str],
        view_ids: list[str],
        graph_layers: list[str],
        properties: dict[str, Any],
        original: str | None = None,
        translation_status: dict[str, str] | None = None,
    ) -> None:
        existing = nodes.get(node_id)
        if existing is None:
            nodes[node_id] = {
                "node_id": node_id,
                "node_type": node_type,
                "label": ru or en or node_id,
                "multilingual": _multilingual(
                    ru or node_id,
                    en or node_id,
                    source_refs[0] if source_refs else None,
                    original,
                    translation_status,
                ),
                "properties": properties,
                "source_ref": source_refs[0] if source_refs else None,
                "source_refs": source_refs,
                "view_ids": sorted(set(view_ids)),
                "graph_layers": sorted(set(graph_layers)),
            }
            return
        existing["view_ids"] = _merge_strings(_string_list(existing.get("view_ids")), view_ids)
        existing["graph_layers"] = _merge_strings(_string_list(existing.get("graph_layers")), graph_layers)
        existing["source_refs"] = _merge_strings(_string_list(existing.get("source_refs")), source_refs)
        if str(existing.get("node_type") or "") == "material-record" and node_type != "material-record":
            existing["node_type"] = node_type
        if not existing.get("source_ref") and source_refs:
            existing["source_ref"] = source_refs[0]
        existing_properties = _dict(existing.get("properties"))
        existing_properties.update({key: value for key, value in properties.items() if value not in (None, "", [], {})})
        existing["properties"] = existing_properties
        if ru or en:
            existing["label"] = ru or en
            existing["multilingual"] = _multilingual(
                ru or str(existing.get("label") or node_id),
                en or str(existing.get("label") or node_id),
                str(existing.get("source_ref") or "") or None,
                original,
                translation_status,
            )

    def _add_structural_edges(
        self,
        nodes: dict[str, dict[str, Any]],
        edges: dict[str, dict[str, Any]],
        records: dict[str, Any],
        record_views: dict[str, set[str]],
        relation_ids: set[str],
    ) -> None:
        def node_label(node_id: str, language: str) -> str:
            multilingual = _dict(nodes.get(node_id, {}).get("multilingual"))
            labels = _dict(multilingual.get("label"))
            return str(labels.get(language) or nodes.get(node_id, {}).get("label") or node_id)

        def add_edge(
            edge_id: str,
            from_id: str,
            to_id: str,
            predicate: str,
            presentation: str,
            source: dict[str, Any],
            layers: list[str],
        ) -> None:
            if from_id not in nodes or to_id not in nodes:
                return
            view_ids = sorted(record_views.get(from_id, set()) | record_views.get(to_id, set()))
            labels = STRUCTURAL_RELATION_PRESENTATION[presentation]
            edges.setdefault(
                edge_id,
                {
                    "edge_id": edge_id,
                    "from_id": from_id,
                    "to_id": to_id,
                    "predicate_id": predicate,
                    "view_ids": view_ids,
                    "graph_layers": layers,
                    "source_ref": _primary_source(source),
                    "source_refs": _public_source_refs(source),
                    "properties": {
                        "display": {
                            **labels,
                            "hover_ru": f"{node_label(from_id, 'ru')} — {labels['label_ru']} — {node_label(to_id, 'ru')}.",
                            "hover_en": f"{node_label(from_id, 'en')} — {labels['label_en']} — {node_label(to_id, 'en')}.",
                        }
                    },
                },
            )

        for event in _dict_list(records.get("events")):
            event_id = str(event.get("event_id") or "")
            for index, binding in enumerate(_dict_list(event.get("participant_bindings"))):
                participant_ref = str(binding.get("participant_ref") or "")
                if event_id and participant_ref:
                    role = str(binding.get("role") or "participant")
                    add_edge(
                        f"material:event-binding:{event_id}:{index}:{participant_ref}",
                        event_id,
                        participant_ref,
                        role,
                        "event_participant",
                        event,
                        ["material-relation"],
                    )

        for representation in _dict_list(records.get("representations")):
            representation_id = str(representation.get("representation_id") or "")
            subject_ref = str(representation.get("subject_ref") or "")
            if representation_id and subject_ref:
                add_edge(
                    f"material:representation-subject:{representation_id}:{subject_ref}",
                    representation_id,
                    subject_ref,
                    "represents",
                    "represents",
                    representation,
                    ["material-relation"],
                )
            for index, derivation_ref in enumerate(_string_list(representation.get("derivation_refs"))):
                if representation_id and derivation_ref not in relation_ids:
                    add_edge(
                        f"material:representation-derivation:{representation_id}:{index}:{derivation_ref}",
                        representation_id,
                        derivation_ref,
                        "derived_from",
                        "derived_from",
                        representation,
                        ["material-relation"],
                    )

        for reference in _dict_list(records.get("references")):
            reference_id = str(reference.get("reference_id") or "")
            subject_ref = str(reference.get("subject_ref") or "")
            if reference_id and subject_ref:
                add_edge(
                    f"material:reference-subject:{reference_id}:{subject_ref}",
                    reference_id,
                    subject_ref,
                    "references",
                    "references",
                    reference,
                    ["material-relation"],
                )


def merge_material_overlay(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    if not overlay:
        return base
    for key in ("views", "nodes", "edges", "clusters", "review_packets", "graph_layers", "layer_counts", "unresolved_review_surfaces"):
        base_items = _dict_list(base.get(key))
        overlay_items = _dict_list(overlay.get(key))
        if key == "views":
            identity = "view_id"
        elif key == "nodes":
            identity = "node_id"
        elif key == "edges":
            identity = "edge_id"
        elif key == "clusters":
            identity = "cluster_id"
        elif key == "review_packets":
            identity = "view_id"
        elif key in {"graph_layers", "layer_counts"}:
            identity = "layer_id"
        else:
            identity = "unresolved_id"
        existing = {str(item.get(identity)) for item in base_items if item.get(identity)}
        base[key] = [*base_items, *(item for item in overlay_items if str(item.get(identity)) not in existing)]

    counts = _dict(base.get("counts"))
    counts.update(_dict(overlay.get("counts")))
    counts.update(
        {
            "views": len(_dict_list(base.get("views"))),
            "nodes": len(_dict_list(base.get("nodes"))),
            "edges": len(_dict_list(base.get("edges"))),
            "clusters": len(_dict_list(base.get("clusters"))),
            "review_packets": len(_dict_list(base.get("review_packets"))),
            "graph_layers": len(_dict_list(base.get("graph_layers"))),
            "unresolved_review_surfaces": len(_dict_list(base.get("unresolved_review_surfaces"))),
        }
    )
    base["counts"] = counts
    return base
