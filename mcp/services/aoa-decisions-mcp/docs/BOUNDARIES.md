# Boundaries

`aoa-decisions-mcp` is an access plane over generated decision graph outputs.

It may:

- check graph freshness;
- rebuild the ignored local graph cache;
- return compact graph packets, repo slices, decision slices, and search
  results;
- point agents back to source decision records.

It may not:

- edit repo-local decision records;
- create durable decisions;
- promote graph packets to source truth;
- install hooks, timers, daemons, or background services;
- decide proof, memory, routing, skill, KAG, playbook, stats, or source
  doctrine for another repo.

When graph output and a source decision record disagree, the source record wins.
When a decision record and current source code disagree, inspect the current
source owner before acting.
