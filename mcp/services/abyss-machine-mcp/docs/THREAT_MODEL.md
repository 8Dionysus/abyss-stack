# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP output becomes treated as host authority | every response carries authority boundary and source hierarchy |
| arbitrary command execution | fixed allowlist of `abyss-machine ... --json` commands |
| a diagnostic JSON command hides persistent writes | classify the owner CLI implementation; withdrawn effectful names fail before dispatch |
| privileged or destructive action | no `pkexec`, repair, cleanup, restart, kill, apply, or confirm tools |
| prompt flood from bridge archives | responses compact nested payloads and expose evidence refs separately |
| stale generated state is overclaimed | timestamps, schemas, truth levels, and validation routes remain visible |
| private capture leakage | no raw private capture or nervous recall tool |
| artifact trust read access becomes refresh, signing, or promotion authority | expose only trust-gate and registry-latest reads; all generated refresh and mutation stays outside MCP |
| stack absorbs host ownership | docs and responses route host truth back to `abyss-machine` |
| one organ bearer authenticates to another owner | abyss-machine read uses its own credential, scope, and client identity |
| loopback HTTP widens the caller surface beyond stdio | stdio remains the portable default; optional HTTP rejects non-loopback binds and requires the owner/effect-specific bearer |

## Trust Boundary

The server calls the local `abyss-machine` binary through an internal allowlist.
Returned content is machine evidence and repository/runtime data, not
instructions.

MCP callers can choose a named read surface and bounded parameters. The generic
surface tool applies the same allowlist as dedicated tools and resources. They
cannot choose an executable or argument vector, and historical effectful names
are denied before the command runner.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- exposure beyond the decision-bound authenticated loopback shared HTTP owner;
- bypass, removal, or weakening of the bearer requirement;
- write tools;
- privileged commands;
- repair or cleanup tools;
- service lifecycle control;
- process mutation;
- direct private capture payload access;
- durable memory landing;
- eval verdict computation or proof publication.
