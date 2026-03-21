# SECURITY

## Security baseline

- host-facing services bind to `127.0.0.1`
- internal-only services do not expose host ports
- real secrets stay outside git
- generated logs should be treated as potentially sensitive

## Secret posture

Expected live pattern:
- runtime configs under `/srv/abyss-stack/Configs`
- secrets under `/srv/abyss-stack/Secrets`
- example env files in `env/`
- real env files never committed

## Forbidden habits

- committing live `stack.env`
- publishing raw inspect output that may contain env values
- treating secret paths as normal source files
- widening network exposure casually

## Safe defaults

- localhost-first
- rootless containers
- smallest possible exposed surface
- explicit profiles instead of always-on sprawl

## Review questions

Before exposing or changing a service, ask:
1. Does this need a host port at all?
2. Does it need more than localhost?
3. Does this introduce secret-bearing config drift?
4. Does this make rollback harder?
