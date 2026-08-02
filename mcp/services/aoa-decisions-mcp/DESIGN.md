# AoA Decisions MCP Design

## Thesis

Decision rationale should be fast to inspect from any repo without loading all
decision records into every prompt.

`aoa-decisions-mcp` exposes a generated workspace graph as an access plane. The
source remains each repo's `docs/decisions/` lane.

## Operation

Every read resource and tool calls `require_fresh()` before reading graph
outputs. Cache freshness is based on a deterministic fingerprint of discovered
workspace decision lanes plus local Git source posture. If decision content,
HEAD, the available local tracking ref, ahead/behind relation, or clean/dirty
posture changes, the read contour fails closed without creating or rewriting
output.

```text
repo-local docs/decisions
  -> owner CLI or internal-effect refresh contour
  -> Logs/decision-graph/latest
  -> read contour parity check
  -> MCP packets
```

The default `read` contour exposes navigation reads and a non-writing cache
posture tool. The `internal_effect` contour is a separate process surface that
exposes only cache posture and explicit refresh. The two contours must use
different credentials when deployed. The owner-local CLI can prepare the same
cache without exposing an effectful MCP route.

The optional `decision-retrieval` capability profile narrows the read contour
to three tools and two addressable resources. Its stack-owned manifest binds
the access runtime to the federated repository decision owners without moving
rationale authority into `abyss-stack`. A normalized `decision_views`
projection makes owner identity, status, rationale summary, lineage, source
reference, and observed local source revision explicit while preserving the
repo-local record as the source of full rationale.

The graph builder also owns a decision-surface registry. Every fingerprinted
file under `docs/decisions/` must either become a known graph node type or be
reported in summary issues as an unmodeled surface.

Source posture is intentionally local-only. The builder compares each checkout
with an existing local tracking ref without fetching. It returns exact
comparison basis and `remote_freshness_checked=false`; source lag is advisory
and does not become a structural graph issue. When source warnings exist, the
MCP status is degraded from `fresh` or `refreshed` to the corresponding
`-with-source-warnings` status while preserving a separate `cache_status`.
Packet-level freshness carries counts plus a compact warning projection; full
Git posture remains on graph, repo, and issue surfaces so ordinary search
packets do not pay the context cost of every SHA.

Repo identity comes from the local `origin` URL when available, with the
checkout directory name as fallback. This keeps arbitrarily named worktrees in
the canonical repo slice. If the workspace and an explicit extra root resolve
to the same identity, the explicit root wins so the running source checkout is
not merged with a second copy.

## Boundaries

- The graph is a navigation read model.
- Repo-local decision records own rationale.
- Repo-local validators and generated indexes own local decision-lane health.
- The read MCP contour never writes cache files, lock directories, or source.
- The internal-effect contour writes only ignored cache files under
  `Logs/decision-graph/latest/`.
- A read credential cannot enumerate or invoke refresh.
- MCP does not fetch, switch, reset, clean, or otherwise mutate source repos.
- The `decision-retrieval` profile cannot be selected for the cache-refresh
  `internal_effect` contour.
- Cache freshness does not claim owner-source or remote freshness.
- Unknown decision-lane surface types require graph-registry work before agents
  rely on them through this MCP.
- Hook, timer, daemon, and durable registry installation are separate owner
  decisions.

## Agent Use

Agents should use this MCP before broad manual scans when the task involves:

- finding decision rationale;
- checking supersession or impact;
- mapping changed paths, source surfaces, or owner surfaces to related
  decisions;
- checking graph issues or cross-repo decision-lane coverage posture;
- creating or correcting a decision record;
- auditing cross-repo decision-lane symmetry;
- identifying source surfaces cited by prior decisions.

When the MCP packet points to a repo-local file, inspect that file before making
source-truth claims.
