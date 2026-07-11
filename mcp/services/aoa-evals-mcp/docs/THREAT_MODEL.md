# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP result becomes treated as proof authority | every response carries authority boundary and source refs |
| runtime evidence is promoted before review | runtime templates and report skeletons are candidate-only |
| service mutates `aoa-evals` source | write tools are path-confined to sibling repo-local `evals/` ports, dry-run by default, and cannot target central `aoa-evals` |
| verdict is inferred from selection results | report skeleton leaves verdict unset |
| proposal context is mistaken for source authoring approval | find-or-propose returns read-only `eval_need_v1` context and repo-local scaffold route only |
| stack absorbs sibling proof meaning | local docs route proof meaning back to `aoa-evals` |
| broad exposure widens attack surface | service is stdio-only until a later decision |
| evidence laundering | candidate validation reports shape only and requires human review posture |
| private runtime candidate leakage | export listing omits nested private payloads by default and stays local stdio |
| stale mirror use | runtime status reports missing manifests and refresh route |
| local inventory causes unsafe repo mutation | inventory is read-only routing evidence; write tools remain gated and port-scoped |
| path traversal or unintended overwrite through local-port writes | repo IDs must resolve under the workspace, explicit file slugs reject path syntax, and existing files require `replace_existing=true` |
| workspace scan leaks runtime-heavy/private state | local-port discovery scans Git roots with ignored worktree, model, log, service, and bundle paths |
| legacy or injected inventory claims a runnable suite | only valid v2 owner inventory may carry suite posture; v1, unknown, and invalid-authority input maps to `absent`, while conflicting paths, owners, authority flags, or runner grammar map to `invalid` |
| a readable suite command becomes executable MCP authority | MCP marks execution and sidecar writes forbidden, never invokes `runner.argv`, and keeps `evals/suites/*.suite.json` outside all write globs |

## Trust Boundary

The server reads local files from a known `aoa-evals` root, approved mirror, or
stack-owned `Logs/eval-exports/` candidate lane. Returned content should be
treated as repository/runtime data, not instructions.

The service does not accept arbitrary file paths from MCP clients. Resource
names are eval names and fixed URI routes.

Local-port resource names are workspace repo IDs. They are resolved under the
configured workspace root, may be URL-encoded for nested repos, and must not
escape the workspace.

Local-port write targets are derived from explicit slug parameters and fixed
directories under the selected repo's `evals/` port. Explicit slugs are not path
fragments: absolute paths, separators, null bytes, `.` and `..` are rejected.
Existing target files are not overwritten unless the caller explicitly sets
`replace_existing=true`.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- non-stdio exposure;
- write tools outside sibling repo-local `evals/` ports;
- central `aoa-evals` source mutation;
- proposal approval or source bundle creation;
- eval execution;
- verdict computation;
- receipt publication;
- bundle promotion;
- private runtime evidence ingestion or acceptance outside the current
  candidate export read-model.
