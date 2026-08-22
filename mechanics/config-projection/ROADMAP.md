# Config Projection Roadmap

## Current route

- keep public templates in `config-templates/`
- keep env examples in `env/`
- keep bootstrap, sync, and render implementation bodies under package parts
- keep multi-owner Codex hook composition neutral, source-first, and
  independently reversible
- keep durable Codex hook installs content-addressed and separate from
  session-owned typed context publication
- keep parity validation source-first and synthetic unless live mode is
  explicitly requested

## Next candidates

- split render checks by config family if render logic becomes too broad
- add focused tests for bootstrap and sync helpers if shell behavior grows
- activate a composed user hook config only after the exact definition is
  reviewed/trusted and a rollback receipt target is selected
- promote more deployment-path detail into `parts/deployment-paths/` only when
  root `docs/runtime/PATHS.md` becomes too dense

## Stop-lines

- do not commit live `stack.env`, secrets, rendered private config, or host
  captures
- do not make deployed `Configs` the source authority
- do not make federation mirror content a config-projection ownership claim
- do not make coexistence imply a dependency between owner hook repositories
  or treat configuration presence as invocation or benefit
