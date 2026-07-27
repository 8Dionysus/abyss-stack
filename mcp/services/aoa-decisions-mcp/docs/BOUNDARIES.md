# Boundaries

`aoa-decisions-mcp` is an access plane over generated decision graph outputs.

It may:

- check graph freshness;
- report local checkout posture against already available local tracking refs;
- return compact graph packets, repo slices, decision slices, and search
  results;
- point agents back to source decision records.

The separate internal-effect contour may:

- rebuild the ignored local graph cache;
- report cache posture;
- write only beneath `Logs/decision-graph/latest/`.

It may not:

- edit repo-local decision records;
- create durable decisions;
- promote graph packets to source truth;
- install hooks, timers, daemons, or background services;
- fetch remotes or mutate source checkout state;
- decide proof, memory, routing, skill, KAG, playbook, stats, or source
  doctrine for another repo.

The read contour may not create its output directory, acquire a refresh lock,
or repair missing or stale cache output. It fails closed until an owner
operator or separately credentialed internal-effect process prepares the cache.

When graph output and a source decision record disagree, the source record wins.
When a decision record and current source code disagree, inspect the current
source owner before acting.

`cache_status=fresh` proves only parity with the current local filesystem.
`remote_freshness_checked=false` is a hard claim limit, not an invitation to
infer remote currency. Source warnings must be carried into repo-local
inspection rather than converted into graph issues or hidden by cache refresh.
