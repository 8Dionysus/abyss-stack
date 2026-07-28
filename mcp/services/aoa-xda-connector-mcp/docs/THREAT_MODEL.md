# Threat model

Primary risks are credential reuse, unexpected network access, source-command
drift, path disclosure, and overclaiming local evidence. Mitigations are a
dedicated bearer/scope, loopback transport, a four-tool allowlist, read-only
systemd sandboxing, packet boundary checks, and owner-preserving evidence.
