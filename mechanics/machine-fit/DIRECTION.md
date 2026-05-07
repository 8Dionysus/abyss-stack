# Machine Fit Direction

The current contour is read-only toward machine control and conservative toward
accelerator-specific tuning.

Short term:

- keep host facts public/private split explicit
- keep fit records advisory unless runtime checks confirm the path
- prepare a future read-only bridge to `/srv/abyss-machine` without mutating it

Next movement should define the exact bridge contract before any code reads
machine-side state automatically.

