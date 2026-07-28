# Threat Model

## Protected Assets

- Account/session material used by Telegram collection modes.
- Private or permission-limited conversation content.
- Local generated indexes, graphs, receipts, and caches.
- Connector packet provenance and permission reports.

## Risks

- Exposing write/build/login/import/crawl commands as MCP tools.
- Returning answers without permission or provenance context.
- Treating public-channel evidence and account-visible evidence as the same
  permission class.
- Committing generated or private connector state into public Git history.
- Letting a live network lookup masquerade as a local evidence answer.
- Letting anonymous local HTTP callers read permission-limited evidence.

## Controls

- MCP exposes only read-only commands.
- Answer packets preserve `evidence_chain`, `permission_report`, and report
  fields.
- Boundary checks flag packets that do not prove local search behavior.
- Runtime storage roots are configured outside abyss-stack.
- Optional loopback HTTP requires the exact Telegram read credential, scope,
  and client identity before MCP dispatch; its managed unit has no persistent
  write path and denies non-loopback IP traffic. Stdio remains the portable
  default.
