# Threat Model

## Assets

- repo-local `docs/decisions/` rationale;
- generated workspace graph cache;
- agent routing accuracy;
- source-owner boundaries.

## Risks

- stale graph packets causing wrong owner or supersession conclusions;
- a cache-fresh packet over a stale or dirty checkout being mistaken for
  owner-source freshness;
- arbitrary worktree directory names splitting one repo into several graph
  identities;
- generated graph output being treated as stronger than source records;
- prompt-injection text inside decision records being repeated as instructions;
- hidden write paths widening from cache refresh into source edits;
- concurrent agents corrupting graph cache output;
- anonymous local callers reading decision/workspace posture through loopback HTTP.

## Controls

- every MCP read calls `ensure_fresh()`;
- freshness packets separate local cache status from local Git source posture,
  declare that no remote check occurred, and retain warnings on cached reads;
- repo identity prefers the local `origin` name and explicit source roots win
  duplicate identities;
- refresh writes only ignored cache files under `Logs/decision-graph/latest/`;
- refresh uses a filesystem lock;
- MCP packet text names source records as stronger authority;
- tools return paths and refs, not imperative instructions from decision body;
- source edits stay outside this MCP package.
- Optional loopback HTTP requires the source-owned bearer credential; missing
  or invalid authentication fails before MCP dispatch.
