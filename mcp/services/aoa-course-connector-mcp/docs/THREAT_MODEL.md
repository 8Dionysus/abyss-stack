# Threat model

Risks include leaking private source refs or auth state, invoking connected
network work, credential reuse, and duplicating owner truth. Controls are a
dedicated bearer/scope, nine-tool allowlist, forced redaction, recursive
network-touch denial, owner-root verification, loopback transport, and a
read-only no-network unit.
