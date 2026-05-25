# Boundaries

## Authority Split

| Context | Owns | Does not own |
| --- | --- | --- |
| `aoa-evals` | bounded proof bundles, verdict logic, generated reader contracts, runtime-candidate posture | runtime service execution |
| generated readers | deterministic catalog, capsule, section, comparison, and report read models | proof interpretation stronger than source bundles |
| runtime-candidate readers | candidate evidence and artifact hook templates | accepted proof or verdicts |
| `aoa-evals-mcp` | read-only access, selection, inspection, expansion, comparison, template lookup, report skeletons | eval running, verdict computation, receipt publication, bundle promotion, source mutation |
| `abyss-stack` | runnable MCP package and stdio service topology | proof meaning |

## Interface

`aoa-evals-mcp` reads source/generated `aoa-evals` surfaces or an approved
runtime mirror. It returns compact JSON objects with source refs and explicit
authority boundaries.

Report skeletons are candidates. Runtime evidence templates are candidates.
The bundle-local source files and review guides decide whether evidence can
support a bounded report.

## Stop Lines

- No general eval runner.
- No verdict computation.
- No receipt publication.
- No bundle promotion.
- No `aoa-evals` source mutation.
- No treating MCP/generated/runtime output as stronger than source bundles.
- No moving proof authority into `abyss-stack`.
