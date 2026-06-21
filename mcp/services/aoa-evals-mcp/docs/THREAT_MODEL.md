# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP result becomes treated as proof authority | every response carries authority boundary and source refs |
| runtime evidence is promoted before review | runtime templates and report skeletons are candidate-only |
| service mutates `aoa-evals` source | service exposes no write tools and writes no source files |
| verdict is inferred from selection results | report skeleton leaves verdict unset |
| proposal context is mistaken for source authoring approval | find-or-propose returns read-only `eval_need_v1` context and repo-local scaffold route only |
| stack absorbs sibling proof meaning | local docs route proof meaning back to `aoa-evals` |
| broad exposure widens attack surface | service is stdio-only until a later decision |
| evidence laundering | candidate validation reports shape only and requires human review posture |
| private runtime candidate leakage | export listing omits nested private payloads by default and stays local stdio |
| stale mirror use | runtime status reports missing manifests and refresh route |
| local inventory causes unsafe repo mutation | inventory is read-only routing evidence; write tools remain gated and port-scoped |
| workspace scan leaks runtime-heavy/private state | local-port discovery scans Git roots with ignored worktree, model, log, service, and bundle paths |

## Trust Boundary

The server reads local files from a known `aoa-evals` root, approved mirror, or
stack-owned `Logs/eval-exports/` candidate lane. Returned content should be
treated as repository/runtime data, not instructions.

The service does not accept arbitrary file paths from MCP clients. Resource
names are eval names and fixed URI routes.

Local-port resource names are workspace repo IDs. They are resolved under the
configured workspace root, may be URL-encoded for nested repos, and must not
escape the workspace.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- non-stdio exposure;
- write tools;
- proposal approval or source bundle creation;
- eval execution;
- verdict computation;
- receipt publication;
- bundle promotion;
- private runtime evidence ingestion or acceptance outside the current
  candidate export read-model.
