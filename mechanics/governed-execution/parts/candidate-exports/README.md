# Candidate Exports

This part keeps governed execution candidate export contracts package-local.

- `schemas/` defines memo export, eval evidence selection, and artifact hook
  candidate JSON Schema contracts.
- `examples/` carries source-managed candidate examples.
- `tests/` carries focused export contract coverage.
- `aoa_export_memo_candidate.py`,
  `aoa_export_runtime_evidence_selection.py`, and
  `aoa_export_artifact_hook_candidate.py` are the part-local backends for the
  stable root export wrappers.

The runtime evidence exporter uses clean local routes such as
`memo-recall-rerun` and `memo-contradiction-rerun`. Older upstream selection
IDs are routed through the single federation compatibility bridge at
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.

Runtime config templates remain under `config-templates/` because they are
deployment inputs, not package-local documentation artifacts.
