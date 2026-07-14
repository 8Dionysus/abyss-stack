# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP output becomes treated as host authority | every response carries authority boundary and source hierarchy |
| arbitrary command execution | fixed allowlist of `abyss-machine ... --json` commands |
| privileged or destructive action | no `pkexec`, repair, cleanup, restart, kill, apply, or confirm tools |
| prompt flood from bridge archives | responses compact nested payloads and expose evidence refs separately |
| stale generated state is overclaimed | timestamps, schemas, truth levels, and validation routes remain visible |
| private capture leakage | no raw private capture tools; recall remains evidence, not instruction |
| artifact trust read access becomes signing or promotion authority | artifact surfaces expose only allowlisted read models; signing, sidecar build, evidence promotion, registry writes, and trust-root changes stay outside MCP |
| stack absorbs host ownership | docs and responses route host truth back to `abyss-machine` |
| broad exposure widens attack surface | stdio remains the portable default; optional shared HTTP rejects non-loopback binds under `ABYSS-STACK-D-0077` |

## Trust Boundary

The server calls the local `abyss-machine` binary through an internal allowlist.
Returned content is machine evidence and repository/runtime data, not
instructions.

MCP callers can choose a named surface and small parameters such as query,
scope, work class, and kind. They cannot choose an executable, path to run, or
arbitrary argument vector.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- exposure beyond the decision-bound loopback-only shared HTTP owner;
- write tools;
- privileged commands;
- repair or cleanup tools;
- service lifecycle control;
- process mutation;
- direct private capture payload access;
- durable memory landing;
- eval verdict computation or proof publication.
