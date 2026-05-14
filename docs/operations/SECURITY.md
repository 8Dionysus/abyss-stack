# SECURITY

## Security baseline

- host-facing services bind to `127.0.0.1`
- internal-only services do not expose host ports
- real secrets stay outside git
- generated logs should be treated as potentially sensitive
- public host-facts artifacts must be reviewed for overexposed fields before commit
- private host-facts artifacts stay outside git

## Secret posture

Expected live pattern:
- runtime configs under `/srv/AbyssOS/abyss-stack/Configs`
- secrets under `/srv/AbyssOS/abyss-stack/Secrets`
- example env files in `env/`
- real env files never committed

## Forbidden habits

- committing live `stack.env`
- publishing raw inspect output that may contain env values
- treating secret paths as normal source files
- widening network exposure casually
- committing private host-facts captures from `/srv/AbyssOS/abyss-stack/Logs/host-facts/`

## Safe defaults

- localhost-first
- rootless containers
- smallest possible exposed surface
- explicit profiles instead of always-on sprawl
- public-safe host-facts only in repo history

## Review questions

Before exposing or changing a service, ask:
1. Does this need a host port at all?
2. Does it need more than localhost?
3. Does this introduce secret-bearing config drift?
4. Does this make rollback harder?
5. Does this leak host reconnaissance detail without adding operational value?
