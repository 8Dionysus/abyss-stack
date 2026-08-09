# SECRETS BOOTSTRAP

This document explains which secret-bearing files the runtime currently expects and how to create them without leaking them into git.

## Core rule

Public-safe examples may live in the repository.
Real secrets do not.

## Expected secret-bearing files

### 1. Stack env

Recommended real location:
- `/srv/AbyssOS/abyss-stack/Secrets/Configs/stack.env`

Expected runtime path used by compose:
- `/srv/AbyssOS/abyss-stack/Configs/stack.env`

Recommended pattern:
- keep the real file under `Secrets/Configs/`
- symlink it into `Configs/stack.env`

Example:

```bash
cp env/stack.env.example /srv/AbyssOS/abyss-stack/Secrets/Configs/stack.env
ln -sfn /srv/AbyssOS/abyss-stack/Secrets/Configs/stack.env /srv/AbyssOS/abyss-stack/Configs/stack.env
chmod 600 /srv/AbyssOS/abyss-stack/Secrets/Configs/stack.env
```

`N8N_RUNNERS_AUTH_TOKEN` must be a long random shared secret. It is consumed by
the n8n main container and the `n8n-task-runners` sidecar; do not commit the
live value.

### 2. LangChain API env

Real location:
- `/srv/AbyssOS/abyss-stack/Secrets/Configs/langchain-api.env`

Bootstrap from example:

```bash
cp env/langchain-api.env.example /srv/AbyssOS/abyss-stack/Secrets/Configs/langchain-api.env
chmod 600 /srv/AbyssOS/abyss-stack/Secrets/Configs/langchain-api.env
```

### 3. OVMS API env

Real location:
- `/srv/AbyssOS/abyss-stack/Secrets/Configs/ovms-api.env`

Bootstrap from example:

```bash
cp env/ovms-api.env.example /srv/AbyssOS/abyss-stack/Secrets/Configs/ovms-api.env
chmod 600 /srv/AbyssOS/abyss-stack/Secrets/Configs/ovms-api.env
```

### 4. OVMS raw API key file

Real location:
- `/srv/AbyssOS/abyss-stack/Secrets/Configs/ovms_api_key.txt`

Create it manually and keep permissions tight:

```bash
printf '%s\n' 'CHANGE_ME_REAL_VALUE' > /srv/AbyssOS/abyss-stack/Secrets/Configs/ovms_api_key.txt
chmod 600 /srv/AbyssOS/abyss-stack/Secrets/Configs/ovms_api_key.txt
```

### 5. ToS graph helper env

Real location:
- `/srv/AbyssOS/abyss-stack/Secrets/Configs/tos-graph.env`

Bootstrap from example:

```bash
cp env/tos-graph.env.example /srv/AbyssOS/abyss-stack/Secrets/Configs/tos-graph.env
chmod 600 /srv/AbyssOS/abyss-stack/Secrets/Configs/tos-graph.env
```

Related stack-level defaults that usually belong in `/srv/AbyssOS/abyss-stack/Configs/stack.env`:
- `AOA_TOS_ROOT=/srv/AbyssOS/Tree-of-Sophia`
- `AOA_TOS_GRAPH_HOST_PORT=5410`
- `TOS_GRAPH_WRITE_ENABLED=false`
- `NEO4J_AUTH=neo4j/<runtime-secret>`

If `TOS_GRAPH_NEO4J_PASSWORD` is omitted from `tos-graph.env`, the helper
derives Neo4j credentials from the mounted stack-level `NEO4J_AUTH` value at
runtime instead of duplicating the secret into a second committed example.

### 6. Optional authenticated MCP HTTP bearer

Real location:

- `/srv/AbyssOS/abyss-stack/Secrets/Configs/aoa-mcp-http-bearer-token`

This credential is required only when the optional shared Streamable HTTP MCP
owners are used. Provision it through the explicit source-owned route:

```bash
scripts/aoa-install-systemd --provision-mcp-http-auth
```

The command creates a missing `Secrets/Configs` directory with mode `0700` but
preserves the permissions of an existing directory. It rejects symlinked
secret roots or credential files, creates a long random URL-safe value with
mode `0600`, reuses an existing valid value, and never prints or replaces it.
The user unit consumes the file through `LoadCredential`; Codex config stores
only `bearer_token_env_var = "AOA_MCP_HTTP_BEARER_TOKEN"`. General layout
checks do not require this optional secret when MCP remains on stdio.

The source-isolated owner-bounded read set uses eight additional non-committed
files:

- `aoa-decisions-mcp-read-bearer-token`
- `aoa-memo-mcp-read-bearer-token`
- `aoa-evals-mcp-read-bearer-token`
- `aoa-kag-mcp-read-bearer-token`
- `aoa-session-memory-mcp-read-bearer-token`
- `aoa-stats-mcp-read-bearer-token`
- `abyss-machine-mcp-read-bearer-token`
- `tos-corpus-mcp-read-bearer-token`

Provision them with:

```bash
scripts/aoa-install-systemd --provision-organ-mcp-read-auth
```

The command rejects equal owner tokens and emits only a secret-local digest
manifest. Corresponding Codex registrations name the exact owner environment
variable; no token value belongs in `config.toml`. The ToS credential may be
provisioned before its wrapper/canary gate, but must not be interpreted as live
bundle admission.

Memo and Evals use two additional candidate credentials:

- `aoa-memo-mcp-candidate-bearer-token`
- `aoa-evals-mcp-candidate-bearer-token`

Provision them with:

```bash
scripts/aoa-install-systemd --provision-organ-mcp-candidate-auth
```

This action also ensures the fourteen read credentials exist, rejects any
equal value across the complete sixteen-credential set, and publishes only
candidate digests in a separate secret-local manifest.

## Minimum expectation

Before trying to run the full Intel-aware or local-worker surface, ensure that
its required paths exist in real form. The legacy `aoa-mcp-http@...` route is
retired and non-startable; provision the owner read bearers before
starting an `aoa-organ-mcp-read@...` owner.

## Helpful check

Use:

```bash
aoa-check-layout
```

For stricter enforcement:

```bash
aoa-check-layout --strict
```

## Reminder

Do not commit:
- live `.env` files
- raw API key files
- screenshots or logs that expose the values
