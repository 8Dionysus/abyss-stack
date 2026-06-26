# AoA Evals MCP Design

## Thesis

`aoa-evals` should be callable by OS Abyss as a bounded proof organ without
copying its whole proof canon into every prompt.

The stable form is:

```text
proof question -> aoa_evals MCP -> generated reader/source refs -> bundle-local review
```

MCP is the access layer. It is intentionally weaker than authored eval bundles,
generated reader builders, and bundle-local report contracts.

## Contexts

`aoa-evals` owns proof meaning.
Generated readers own deterministic read models.
Runtime-candidate readers own candidate evidence shapes.
Stack runtime exports own private candidate records under
`Logs/eval-exports/`.
`aoa-evals-mcp` owns just-in-time access, selection helpers, and route prompts.
`abyss-stack` owns the runnable MCP service package.

## Operation

An agent should be able to start from a proof question:

```text
aoa_evals_select(proof_question, filters)
aoa_evals_find_or_propose(proof_question, proposal)
```

Then the agent can inspect a candidate:

```text
aoa_evals_inspect(name)
aoa_evals_expand(name, section_key)
```

Comparison and runtime evidence use separate bounded routes:

```text
aoa_evals_comparison(baseline_mode)
aoa_evals_runtime_evidence_template(name)
aoa_evals_runtime_status()
aoa_evals_validate_evidence_candidate(packet)
aoa_evals_runtime_candidate_exports(limit)
aoa_evals_read_runtime_candidate_export(record_id, include_payload=false)
aoa_evals_report_skeleton(name, evidence_refs)
```

The skeleton route leaves the verdict unset. It exists to preserve report shape
and source refs before a reviewer reads the source bundle.

Find-or-propose is the eval birth access route. It searches existing evals,
optionally attaches stack-owned runtime candidate export refs, and returns a
candidate `eval_need_v1` packet for the `aoa-evals` repo-local scaffold helper.
It does not approve the packet, create a bundle, or bypass the scaffold
helper's review gates.

Candidate validation is a pre-ingestion gate. It checks schema shape,
provenance refs, review posture, and known eval/template routing. It does not
persist, accept, score, compare, publish, or turn a packet into a verdict.

Runtime status reports which root is selected, whether an approved mirror is
present, which generated readers and candidate schemas are available, and which
refresh command owns the mirror.

Runtime candidate exports are stack-owned private records produced by governed
execution. MCP can list compact metadata, validate the nested candidate packet,
and read one export for review routing. It does not write the export, mark it
accepted, or move it into `aoa-evals`.

## Source Discovery

The server resolves `aoa-evals` in this order:

- explicit `AOA_EVALS_ROOT` or `AOA_EVALS_SOURCE_ROOT`;
- sibling checkout under the workspace root;
- `/srv/AbyssOS/aoa-evals`;
- `~/src/aoa-evals`;
- an explicitly configured stack mirror under `Knowledge/federation/aoa-evals`.

The mirror path is read-only support. Source authority stays with `aoa-evals`.

The server resolves the stack runtime root from `AOA_STACK_ROOT`,
`AOA_ABYSS_STACK_RUNTIME_ROOT`, `AOA_ABYSS_STACK_ROOT`, or
`<workspace-root>/abyss-stack`, then reads `Logs/eval-exports/` as a private
candidate lane.

When the stack federation sync wrapper refreshes the mirror, it writes
`manifest/federation_mirror_manifest.json` with source commit, generated time,
required files, and compact counts. MCP treats the manifest as freshness
evidence, not proof authority.

## Local Port Inventory

Repo-local `evals/` ports are exposed as a read-only workspace inventory before
any write route. The inventory scans Git roots below the OS Abyss workspace,
ignores worktrees and runtime-heavy stack paths, excludes `aoa-evals` as the
central proof owner, and classifies each repo as `missing`, `stale_candidate`,
`invalid`, `skeleton`, or `active`.

Each entry carries pressure counts, validator issues, central-name overlaps,
and a route recommendation such as `valid_skeleton_keep_dormant`,
`active_intake_select_then_apply_or_design`, or `invalid_active_repair`.
The recommendation is a routing hint only. It must not promote local pressure,
accept evidence, compute a verdict, or create central bundles.

The producer/consumer lock for this read-model is
`aoa-evals:docs/architecture/local_eval_port_inventory.contract.v1.json`.
`aoa-evals` owns the status vocabulary, summary keys, route keys, discovery
ignore policy, and authority boundary. The MCP implementation loads that
contract from the selected source or mirror root, reports the loaded contract
metadata, and uses fallback constants only when older mirrors have not yet
carried the contract.

## Readiness

The first layer is ready when:

- resources, tools, and prompts exist and are smoke-tested;
- catalog, capsule, section, comparison, report, and runtime-candidate readers
  can be read;
- find-or-propose returns valid `eval_need_v1` context without source mutation;
- report skeletons keep verdict unset;
- candidate validation keeps `human_review_required`/`review_required` true;
- runtime candidate export listing does not include private payloads by default;
- runtime status exposes missing or unmanifested mirrors;
- local-port inventory covers top-level and nested Git roots without scanning
  runtime-heavy stack state;
- local-port inventory route keys and summary keys match the central
  `aoa-evals` inventory contract;
- local-port write tools return audit receipts that keep dry-run, path
  confinement, validation, activation, side effects, and proof-forbidden fields
  visible to agents;
- the Codex plane can resolve `aoa_evals`;
- validation proves the service did not become a runner, publisher, promoter,
  or source writer.
