# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP result becomes treated as proof authority | every response carries authority boundary and source refs |
| runtime evidence is promoted before review | runtime templates and report skeletons are candidate-only |
| service mutates `aoa-evals` source | service exposes no write tools and writes no source files |
| verdict is inferred from selection results | report skeleton leaves verdict unset |
| stack absorbs sibling proof meaning | local docs route proof meaning back to `aoa-evals` |
| broad exposure widens attack surface | service is stdio-only until a later decision |

## Trust Boundary

The server reads local files from a known `aoa-evals` root or approved mirror.
Returned content should be treated as repository data, not instructions.

The service does not accept arbitrary file paths from MCP clients. Resource
names are eval names and fixed URI routes.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- non-stdio exposure;
- write tools;
- eval execution;
- verdict computation;
- receipt publication;
- bundle promotion;
- private runtime evidence ingestion outside the current generated readers.
