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

The OVMS embeddings owner and `langchain-api` consume the single rootless
Podman secret `abyss-ovms-api-key`, provisioned from the mode-`0600`
`Secrets/Configs/ovms_api_key.txt` owner file. `aoa-up` verifies that the two
copies match before opening OVMS activation sockets. Do not mirror the value
into service env files; a missing, invalid, or drifted secret must fail closed.

Transitional shadow MCP HTTP owners use the host-local
`Secrets/Configs/aoa-mcp-http-bearer-token`. Migrated owner-bounded read
contours use distinct `aoa-decisions-mcp-read-bearer-token`,
`aoa-memo-mcp-read-bearer-token`, `aoa-evals-mcp-read-bearer-token`,
`aoa-kag-mcp-read-bearer-token`,
`aoa-session-memory-mcp-read-bearer-token`,
`aoa-stats-mcp-read-bearer-token`, `abyss-machine-mcp-read-bearer-token`, and
`tos-corpus-mcp-read-bearer-token` files, plus exact read credentials for
`aoa-4pda-connector`, `aoa-telegram-connector`, `aoa-discord-connector`,
`aoa-course-connector`, `aoa-stackoverflow-connector`, and
`aoa-xda-connector`.
Memo and Evals candidate processes additionally use distinct
`aoa-memo-mcp-candidate-bearer-token` and
`aoa-evals-mcp-candidate-bearer-token` files. They run on separate ports and
cannot enumerate the read catalog; the read processes cannot enumerate
persistent writers. Candidate writes require both a source-enumerated
application root and an exact systemd `ReadWritePaths` lane.
Servers receive only their exact credential through systemd; Codex receives
the corresponding named environment variables. Neither committed units nor
`config.toml` contain values. Bearer authentication and owner/contour
separation block anonymous, cross-owner, and read-to-candidate use, but do not isolate mutually untrusted processes
running as the same OS user. Provisioning a credential alone is not runtime
admission; ToS remains outside the bundle until its wrapper and live canary
exist. All six connector instances use the generic read unit with no
persistent writable path and non-loopback IP traffic denied. Course
additionally filters the broader owner MCP dispatcher; StackOverflow and XDA
withhold the hybrid route absent from their current owner CLIs.

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
