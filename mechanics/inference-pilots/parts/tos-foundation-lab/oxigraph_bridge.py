#!/usr/bin/env python3
"""Execute one isolated RDF projection inside the pinned PyOxigraph runtime."""

from __future__ import annotations

import json
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


RUN_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{7,95}$")
ALLOWED_STORE_ROOT = Path(
    "/srv/abyss-machine/storage/artifacts/tree-of-sophia-foundation-lab"
)

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XSD = "http://www.w3.org/2001/XMLSchema#"
PROV = "http://www.w3.org/ns/prov#"
TOS = "urn:tos:vocab:"

PREFIXES = f"""
PREFIX rdf: <{RDF}>
PREFIX xsd: <{XSD}>
PREFIX prov: <{PROV}>
PREFIX tos: <{TOS}>
"""

QUERY_CATALOG = {
    "subject_predicate": PREFIXES
    + """
SELECT DISTINCT ?claim_id ?object ?object_kind ?object_value WHERE {
  ?claim tos:claimId ?claim_id ;
         tos:subject <__SUBJECT_IRI__> ;
         tos:predicateName __PREDICATE_LITERAL__ ;
         tos:object ?object ;
         tos:objectKind ?object_kind .
  OPTIONAL { ?object tos:refValue ?object_value . }
}
""",
    "claim_family": PREFIXES
    + """
SELECT DISTINCT ?claim_id ?subject_value ?object ?object_kind ?object_value WHERE {
  <__SEED_CLAIM_IRI__> (tos:alternativeTo|^tos:alternativeTo)* ?claim .
  ?claim tos:claimId ?claim_id ;
         tos:subject ?subject ;
         tos:object ?object ;
         tos:objectKind ?object_kind .
  ?subject tos:refValue ?subject_value .
  OPTIONAL { ?object tos:refValue ?object_value . }
}
""",
    "path": PREFIXES
    + """
SELECT DISTINCT ?claim_id ?claim_order ?subject_value ?object ?object_kind ?object_value WHERE {
  ?claim tos:claimId ?claim_id ;
         tos:claimOrder ?claim_order ;
         tos:subject ?subject ;
         tos:object ?object ;
         tos:objectKind ?object_kind .
  ?subject tos:refValue ?subject_value .
  OPTIONAL { ?object tos:refValue ?object_value . }
}
ORDER BY ?claim_order
""",
    "layer_inventory": PREFIXES
    + """
SELECT ?layer (COUNT(DISTINCT ?claim) AS ?claim_count) WHERE {
  ?claim rdf:type tos:Claim ; tos:layer ?layer .
}
GROUP BY ?layer
ORDER BY ?layer
""",
    "review_inventory": PREFIXES
    + """
SELECT DISTINCT ?claim_id WHERE {
  ?claim rdf:type tos:Claim ;
         tos:claimId ?claim_id ;
         tos:reviewStatus __REVIEW_STATUS_LITERAL__ .
}
ORDER BY ?claim_id
""",
    "traceability_inventory": PREFIXES
    + """
SELECT ?claim_id ?evidence_count (COUNT(DISTINCT ?evidence) AS ?observed_evidence_count) WHERE {
  ?claim rdf:type tos:Claim ;
         tos:claimId ?claim_id ;
         tos:canonicalTraceable true ;
         tos:subject ?subject ;
         tos:predicate ?predicate ;
         tos:object ?object ;
         tos:madeBy ?maker ;
         prov:wasGeneratedBy ?event ;
         tos:evidenceCount ?evidence_count ;
         tos:evidence ?evidence ;
         tos:reviewStatus ?review_status ;
         tos:reviewCount ?review_count ;
         tos:claimGraph ?graph .
  ?graph tos:assertedBy ?claim .
  GRAPH ?graph { ?subject ?predicate ?object . }
}
GROUP BY ?claim_id ?evidence_count
HAVING (COUNT(DISTINCT ?evidence) = ?evidence_count)
ORDER BY ?claim_id
""",
}


def _compact(value: str) -> str:
    return " ".join(value.split())


def query_catalog() -> dict[str, str]:
    return {key: _compact(value) for key, value in sorted(QUERY_CATALOG.items())}


def _encoded(value: str) -> str:
    return quote(value, safe="._~-", encoding="utf-8", errors="strict")


def claim_iri(claim_id: str) -> str:
    return f"urn:tos:claim:{_encoded(claim_id)}"


def ref_iri(value: str, kind: str = "tos_id") -> str:
    prefix = "path" if kind == "repo_path" else "id"
    return f"urn:tos:{prefix}:{_encoded(value)}"


def predicate_iri(value: str) -> str:
    return f"urn:tos:predicate:{_encoded(value)}"


def graph_iri(lab_run: str, claim_id: str) -> str:
    return f"urn:tos:graph:{lab_run}:claim:{_encoded(claim_id)}"


def manifest_graph_iri(lab_run: str) -> str:
    return f"urn:tos:graph:{lab_run}:manifest"


def dataset_iri(lab_run: str) -> str:
    return f"urn:tos:dataset:{lab_run}"


def agent_iri(agent_ref: str) -> str:
    return f"urn:tos:agent:{_encoded(agent_ref)}"


def _term_value(term: Any) -> str | None:
    if term is None:
        return None
    value = getattr(term, "value", None)
    return str(value) if value is not None else str(term)


def _literal_lexical(value: str) -> str:
    from pyoxigraph import Literal

    return str(Literal(value))


def _reference_term(value: str, kind: str) -> Any:
    from pyoxigraph import Literal, NamedNode

    if kind == "literal":
        return Literal(value)
    return NamedNode(ref_iri(value, kind))


def _add_reference_metadata(
    quads: list[Any],
    term: Any,
    value: str,
    kind: str,
    graph: Any,
) -> None:
    from pyoxigraph import Literal, NamedNode, Quad

    if kind == "literal":
        return
    quads.extend(
        [
            Quad(term, NamedNode(RDF + "type"), NamedNode(TOS + "Reference"), graph),
            Quad(term, NamedNode(TOS + "refValue"), Literal(value), graph),
            Quad(term, NamedNode(TOS + "refKind"), Literal(kind), graph),
        ]
    )


def _projection_quads(lab_run: str, rows: list[dict[str, Any]]) -> list[Any]:
    from pyoxigraph import Literal, NamedNode, Quad

    rdf_type = NamedNode(RDF + "type")
    manifest_graph = NamedNode(manifest_graph_iri(lab_run))
    dataset = NamedNode(dataset_iri(lab_run))
    quads: list[Any] = [
        Quad(dataset, rdf_type, NamedNode(TOS + "LabDataset"), manifest_graph),
        Quad(dataset, NamedNode(TOS + "labRun"), Literal(lab_run), manifest_graph),
    ]

    for order, row in enumerate(rows):
        claim_id = str(row["claim_id"])
        claim = NamedNode(claim_iri(claim_id))
        claim_graph = NamedNode(graph_iri(lab_run, claim_id))
        predicate = NamedNode(predicate_iri(str(row["predicate"])))
        subject = _reference_term(str(row["subject_ref"]), str(row["subject_kind"]))
        object_term = _reference_term(str(row["object_ref"]), str(row["object_kind"]))
        maker = NamedNode(agent_iri(str(row["maker_ref"])))
        event = _reference_term(str(row["provenance_event_ref"]), "tos_id")

        quads.extend(
            [
                Quad(dataset, NamedNode(TOS + "claimGraph"), claim_graph, manifest_graph),
                Quad(claim_graph, rdf_type, NamedNode(TOS + "ClaimGraph"), manifest_graph),
                Quad(claim_graph, NamedNode(TOS + "assertedBy"), claim, manifest_graph),
                Quad(claim_graph, NamedNode(TOS + "labRun"), Literal(lab_run), manifest_graph),
                Quad(claim, rdf_type, NamedNode(TOS + "Claim"), claim_graph),
                Quad(claim, NamedNode(TOS + "claimId"), Literal(claim_id), claim_graph),
                Quad(claim, NamedNode(TOS + "claimOrder"), Literal(order), claim_graph),
                Quad(claim, NamedNode(TOS + "claimType"), Literal(str(row["claim_type"])), claim_graph),
                Quad(
                    claim,
                    NamedNode(TOS + "assertionLayer"),
                    Literal(str(row["assertion_layer"])),
                    claim_graph,
                ),
                Quad(claim, NamedNode(TOS + "layer"), Literal(str(row["layer"])), claim_graph),
                Quad(claim, NamedNode(TOS + "subject"), subject, claim_graph),
                Quad(claim, NamedNode(TOS + "predicate"), predicate, claim_graph),
                Quad(
                    claim,
                    NamedNode(TOS + "predicateName"),
                    Literal(str(row["predicate"])),
                    claim_graph,
                ),
                Quad(claim, NamedNode(TOS + "object"), object_term, claim_graph),
                Quad(
                    claim,
                    NamedNode(TOS + "objectKind"),
                    Literal(str(row["object_kind"])),
                    claim_graph,
                ),
                Quad(claim, NamedNode(TOS + "madeBy"), maker, claim_graph),
                Quad(claim, NamedNode(PROV + "wasGeneratedBy"), event, claim_graph),
                Quad(
                    claim,
                    NamedNode(TOS + "evidenceCount"),
                    Literal(int(row["evidence_count"])),
                    claim_graph,
                ),
                Quad(
                    claim,
                    NamedNode(TOS + "reviewStatus"),
                    Literal(str(row["review_status"])),
                    claim_graph,
                ),
                Quad(
                    claim,
                    NamedNode(TOS + "reviewCount"),
                    Literal(int(row["review_count"])),
                    claim_graph,
                ),
                Quad(
                    claim,
                    NamedNode(TOS + "epistemicStatus"),
                    Literal(str(row["epistemic_status"])),
                    claim_graph,
                ),
                Quad(
                    claim,
                    NamedNode(TOS + "visibility"),
                    Literal(str(row["visibility"])),
                    claim_graph,
                ),
                Quad(
                    claim,
                    NamedNode(TOS + "canonicalTraceable"),
                    Literal(bool(row["canonical_traceable"])),
                    claim_graph,
                ),
                Quad(claim, NamedNode(TOS + "claimGraph"), claim_graph, claim_graph),
                Quad(maker, NamedNode(TOS + "agentRef"), Literal(str(row["maker_ref"])), claim_graph),
                Quad(subject, predicate, object_term, claim_graph),
            ]
        )
        _add_reference_metadata(
            quads, subject, str(row["subject_ref"]), str(row["subject_kind"]), claim_graph
        )
        _add_reference_metadata(
            quads, object_term, str(row["object_ref"]), str(row["object_kind"]), claim_graph
        )
        _add_reference_metadata(
            quads, event, str(row["provenance_event_ref"]), "tos_id", claim_graph
        )
        for evidence_ref in row["evidence_refs"]:
            evidence_kind = "repo_path" if str(evidence_ref).startswith("ToS/") else "tos_id"
            evidence = _reference_term(str(evidence_ref), evidence_kind)
            quads.append(Quad(claim, NamedNode(TOS + "evidence"), evidence, claim_graph))
            _add_reference_metadata(
                quads, evidence, str(evidence_ref), evidence_kind, claim_graph
            )
        for alternative_ref in row["alternative_claim_refs"]:
            quads.append(
                Quad(
                    claim,
                    NamedNode(TOS + "alternativeTo"),
                    NamedNode(claim_iri(str(alternative_ref))),
                    claim_graph,
                )
            )
    return quads


def _select(store: Any, sparql: str) -> list[dict[str, Any]]:
    result = store.query(sparql, use_default_graph_as_union=True)
    variables = [variable.value for variable in result.variables]
    return [{name: solution[name] for name in variables} for solution in result]


def _subject_predicate(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    sparql = QUERY_CATALOG["subject_predicate"].replace(
        "__SUBJECT_IRI__", ref_iri(str(parameters["subject_ref"]))
    ).replace("__PREDICATE_LITERAL__", _literal_lexical(str(parameters["predicate"])))
    rows = _select(store, sparql)
    claim_refs = sorted({_term_value(row["claim_id"]) for row in rows})
    node_refs = sorted(
        {
            _term_value(row["object_value"])
            for row in rows
            if _term_value(row["object_kind"]) == "tos_id"
            and _term_value(row["object_value"]) is not None
        }
    )
    literal_values = sorted(
        {
            _term_value(row["object"])
            for row in rows
            if _term_value(row["object_kind"]) == "literal"
        }
    )
    detail = {"literal_object_values": literal_values} if literal_values else {}
    return {"claim_refs": claim_refs, "node_refs": node_refs, "detail": detail}


def _claim_family(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    sparql = QUERY_CATALOG["claim_family"].replace(
        "__SEED_CLAIM_IRI__", claim_iri(str(parameters["seed_claim_ref"]))
    )
    rows = _select(store, sparql)
    claim_refs = sorted({_term_value(row["claim_id"]) for row in rows})
    node_refs = {
        _term_value(row["subject_value"])
        for row in rows
        if _term_value(row["subject_value"]) is not None
    }
    node_refs.update(
        _term_value(row["object_value"])
        for row in rows
        if _term_value(row["object_kind"]) == "tos_id"
        and _term_value(row["object_value"]) is not None
    )
    literal_values = sorted(
        {
            _term_value(row["object"])
            for row in rows
            if _term_value(row["object_kind"]) == "literal"
        }
    )
    return {
        "claim_refs": claim_refs,
        "node_refs": sorted(node_refs),
        "detail": {"literal_object_values": literal_values},
    }


def _path(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    rows = _select(store, QUERY_CATALOG["path"])
    edges: list[tuple[str, str, str]] = []
    for row in rows:
        if _term_value(row["object_kind"]) != "tos_id":
            continue
        subject = _term_value(row["subject_value"])
        object_value = _term_value(row["object_value"])
        claim_id = _term_value(row["claim_id"])
        if subject is not None and object_value is not None and claim_id is not None:
            edges.append((subject, object_value, claim_id))
    start = str(parameters["start_ref"])
    end = str(parameters["end_ref"])
    maximum_hops = int(parameters["maximum_claim_hops"])
    queue: list[tuple[str, list[str], list[str]]] = [(start, [], [start])]
    cursor = 0
    while cursor < len(queue):
        current, claim_path, node_path = queue[cursor]
        cursor += 1
        if current == end:
            return {"claim_refs": claim_path, "node_refs": node_path, "detail": {}}
        if len(claim_path) >= maximum_hops:
            continue
        for subject, object_value, claim_id in edges:
            if subject != current or object_value in node_path:
                continue
            queue.append(
                (object_value, [*claim_path, claim_id], [*node_path, object_value])
            )
    return {"claim_refs": [], "node_refs": [], "detail": {"path_found": False}}


def _layer_inventory(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    del parameters
    rows = _select(store, QUERY_CATALOG["layer_inventory"])
    counts = {
        str(_term_value(row["layer"])): int(str(_term_value(row["claim_count"])))
        for row in rows
    }
    return {
        "claim_refs": [],
        "node_refs": sorted(counts),
        "detail": {"layer_claim_counts": dict(sorted(counts.items()))},
    }


def _review_inventory(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    sparql = QUERY_CATALOG["review_inventory"].replace(
        "__REVIEW_STATUS_LITERAL__", _literal_lexical(str(parameters["review_status"]))
    )
    rows = _select(store, sparql)
    return {
        "claim_refs": sorted({_term_value(row["claim_id"]) for row in rows}),
        "node_refs": [],
        "detail": {},
    }


def _traceability_inventory(store: Any, parameters: dict[str, Any]) -> dict[str, Any]:
    del parameters
    rows = _select(store, QUERY_CATALOG["traceability_inventory"])
    claim_refs = sorted({_term_value(row["claim_id"]) for row in rows})
    return {
        "claim_refs": claim_refs,
        "node_refs": [],
        "detail": {"mechanically_traceable_claim_count": len(claim_refs)},
    }


OPERATIONS = {
    "subject_predicate": _subject_predicate,
    "claim_family": _claim_family,
    "path": _path,
    "layer_inventory": _layer_inventory,
    "review_inventory": _review_inventory,
    "traceability_inventory": _traceability_inventory,
}


def _execute_queries(store: Any, queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in queries:
        operation = str(query["operation"])
        if operation not in OPERATIONS:
            raise RuntimeError(f"unsupported frozen RDF query operation: {operation}")
        parameters = query.get("parameters", {})
        started = time.perf_counter()
        first = OPERATIONS[operation](store, parameters)
        first_ms = (time.perf_counter() - started) * 1000
        warm_latencies: list[float] = []
        for _ in range(5):
            started = time.perf_counter()
            repeated = OPERATIONS[operation](store, parameters)
            warm_latencies.append((time.perf_counter() - started) * 1000)
            if repeated != first:
                raise RuntimeError(f"non-deterministic Oxigraph answer for {query['query_id']}")
        results.append(
            {
                "query_id": query["query_id"],
                "operation": operation,
                "returned_claim_refs": first["claim_refs"],
                "returned_node_refs": first["node_refs"],
                "detail": first["detail"],
                "first_query_ms": first_ms,
                "warm_latency_ms_median_of_5": statistics.median(warm_latencies),
                "warm_latencies_ms": warm_latencies,
            }
        )
    return results


def _inventory(store: Any) -> dict[str, Any]:
    layer_rows = _select(store, QUERY_CATALOG["layer_inventory"])
    layer_counts = {
        str(_term_value(row["layer"])): int(str(_term_value(row["claim_count"])))
        for row in layer_rows
    }
    count_query = PREFIXES + """
SELECT (COUNT(DISTINCT ?claim) AS ?claim_count)
       (COUNT(DISTINCT ?graph) AS ?claim_graph_count)
       (COUNT(DISTINCT ?evidence_statement) AS ?evidence_statement_count)
       (COUNT(DISTINCT ?alternative_statement) AS ?alternative_statement_count)
WHERE {
  ?claim rdf:type tos:Claim ; tos:claimGraph ?graph .
  OPTIONAL {
    ?claim tos:evidence ?evidence .
    BIND(CONCAT(STR(?claim), "|", STR(?evidence)) AS ?evidence_statement)
  }
  OPTIONAL {
    ?claim tos:alternativeTo ?alternative .
    BIND(CONCAT(STR(?claim), "|", STR(?alternative)) AS ?alternative_statement)
  }
}
"""
    counts = _select(store, count_query)[0]
    assertion_query = PREFIXES + """
SELECT (COUNT(DISTINCT ?claim) AS ?direct_assertion_count) WHERE {
  ?claim rdf:type tos:Claim ;
         tos:claimGraph ?graph ;
         tos:subject ?subject ;
         tos:predicate ?predicate ;
         tos:object ?object .
  ?graph tos:assertedBy ?claim .
  GRAPH ?graph { ?subject ?predicate ?object . }
}
"""
    assertions = _select(store, assertion_query)[0]
    literal_query = PREFIXES + """
SELECT (COUNT(DISTINCT ?claim) AS ?literal_object_claim_count) WHERE {
  ?claim rdf:type tos:Claim ; tos:objectKind "literal" .
}
"""
    literals = _select(store, literal_query)[0]
    return {
        "quad_count": len(store),
        "named_graph_count": len(list(store.named_graphs())),
        "claim_count": int(str(_term_value(counts["claim_count"]))),
        "claim_graph_count": int(str(_term_value(counts["claim_graph_count"]))),
        "manifest_graph_count": 1,
        "direct_assertion_count": int(
            str(_term_value(assertions["direct_assertion_count"]))
        ),
        "evidence_statement_count": int(
            str(_term_value(counts["evidence_statement_count"]))
        ),
        "alternative_statement_count": int(
            str(_term_value(counts["alternative_statement_count"]))
        ),
        "literal_object_claim_count": int(
            str(_term_value(literals["literal_object_claim_count"]))
        ),
        "claim_layers": dict(sorted(layer_counts.items())),
    }


def _canonical_nquads(store: Any) -> str:
    from pyoxigraph import RdfFormat

    dumped = store.dump(format=RdfFormat.N_QUADS).decode("utf-8")
    lines = sorted(line for line in dumped.splitlines() if line)
    return "".join(f"{line}\n" for line in lines)


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    import pyoxigraph
    from pyoxigraph import Store

    lab_run = str(payload.get("lab_run", ""))
    if not RUN_KEY_RE.fullmatch(lab_run):
        raise RuntimeError("invalid isolated RDF lab_run key")
    store_path = Path(str(payload.get("store_path", ""))).resolve()
    run_root = Path(str(payload.get("run_root", ""))).resolve()
    if not store_path.is_relative_to(ALLOWED_STORE_ROOT.resolve()):
        raise RuntimeError("Oxigraph store is outside the allowed laboratory artifact root")
    if not store_path.is_relative_to(run_root) or store_path.name != "oxigraph":
        raise RuntimeError("Oxigraph store must be the run-local derived-store/oxigraph path")
    rows = payload.get("claims")
    queries = payload.get("queries")
    if not isinstance(rows, list) or len(rows) != 13:
        raise RuntimeError("Oxigraph bridge requires exactly 13 projected claims")
    if not isinstance(queries, list) or len(queries) != 10:
        raise RuntimeError("Oxigraph bridge requires exactly 10 frozen queries")
    if store_path.exists():
        raise RuntimeError("Oxigraph store path must be absent before materialization")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = Store(store_path.as_posix())
    quads = _projection_quads(lab_run, rows)
    started = time.perf_counter()
    store.bulk_extend(quads)
    store.flush()
    build_seconds = time.perf_counter() - started
    inventory = _inventory(store)
    query_results = _execute_queries(store, queries)
    nquads = _canonical_nquads(store)
    return {
        "pyoxigraph_version": pyoxigraph.__version__,
        "build_seconds": build_seconds,
        "inventory": inventory,
        "query_results": query_results,
        "canonical_nquads": nquads,
        "query_catalog": query_catalog(),
        "mapping": {
            "assertion_identity": "explicit claim resource plus one claim named graph",
            "direct_assertion": "subject predicate object inside the claim named graph",
            "identity_term": "NamedNode with refValue and refKind metadata",
            "literal_term": "RDF Literal retained as claim object",
            "provenance": "claim resource maker event evidence review and claimGraph links",
            "rdf_star_used": False,
        },
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise RuntimeError("bridge payload must be an object")
        result = execute(payload)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error_type": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
