# Runtime Lifecycle Roadmap

## Current route

- keep lifecycle commands as root wrappers with part-local implementations
- keep root `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, and `docs/RUNBOOK.md`
  as repo-wide operator routes
- keep status readout schemas, examples, and tests under `parts/status-readouts`
- keep systemd user-unit material explicit and opt-in

## Next candidates

- use the live runtime cutover packet before promoting any deployed seam into the
  live loop
- use the source runtime parity packet after source topology or sync-managed
  surface movement
- audit root lifecycle docs for authority versus route-card detail
- add focused wrapper tests if lifecycle shell helpers grow beyond routing and
  environment assembly
- split logs/status readout contracts further only when new source-safe
  runtime artifacts appear

## Stop-lines

- do not start, stop, enable, or mutate live services from source docs
- do not widen host exposure without explicit operator intent
- do not treat source-only validation as live service health
