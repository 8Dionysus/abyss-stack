# Machine Fit Direction

The current contour is read-only toward machine control and conservative toward
accelerator-specific tuning.

Short term:

- keep host facts public/private split explicit
- keep fit records advisory unless runtime checks confirm the path
- keep the read-only `aoa-machine-bridge` route aligned with `abyss-machine`
  without mutating `/srv/abyss-machine`

Next movement should consume the bridge from runtime diagnosis and launch
planning before adding any automatic stack-side policy action.
