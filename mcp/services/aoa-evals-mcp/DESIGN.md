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
`aoa-evals-mcp` owns just-in-time access, selection helpers, and route prompts.
`abyss-stack` owns the runnable MCP service package.

## Operation

An agent should be able to start from a proof question:

```text
aoa_evals_select(proof_question, filters)
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
aoa_evals_report_skeleton(name, evidence_refs)
```

The skeleton route leaves the verdict unset. It exists to preserve report shape
and source refs before a reviewer reads the source bundle.

## Source Discovery

The server resolves `aoa-evals` in this order:

- explicit `AOA_EVALS_ROOT` or `AOA_EVALS_SOURCE_ROOT`;
- sibling checkout under the workspace root;
- `/srv/AbyssOS/aoa-evals`;
- `~/src/aoa-evals`;
- an explicitly configured stack mirror under `Knowledge/federation/aoa-evals`.

The mirror path is read-only support. Source authority stays with `aoa-evals`.

## Readiness

The first layer is ready when:

- resources, tools, and prompts exist and are smoke-tested;
- catalog, capsule, section, comparison, report, and runtime-candidate readers
  can be read;
- report skeletons keep verdict unset;
- the Codex plane can resolve `aoa_evals`;
- validation proves the service did not become a runner, publisher, promoter,
  or source writer.
