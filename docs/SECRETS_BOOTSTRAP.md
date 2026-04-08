# SECRETS BOOTSTRAP

This document explains which secret-bearing files the runtime currently expects and how to create them without leaking them into git.

## Core rule

Public-safe examples may live in the repository.
Real secrets do not.

## Expected secret-bearing files

### 1. Stack env

Recommended real location:
- `/srv/abyss-stack/Secrets/Configs/stack.env`

Expected runtime path used by compose:
- `/srv/abyss-stack/Configs/stack.env`

Recommended pattern:
- keep the real file under `Secrets/Configs/`
- symlink it into `Configs/stack.env`

Example:

```bash
cp env/stack.env.example /srv/abyss-stack/Secrets/Configs/stack.env
ln -sfn /srv/abyss-stack/Secrets/Configs/stack.env /srv/abyss-stack/Configs/stack.env
chmod 600 /srv/abyss-stack/Secrets/Configs/stack.env
```

### 2. LangChain API env

Real location:
- `/srv/abyss-stack/Secrets/Configs/langchain-api.env`

Bootstrap from example:

```bash
cp env/langchain-api.env.example /srv/abyss-stack/Secrets/Configs/langchain-api.env
chmod 600 /srv/abyss-stack/Secrets/Configs/langchain-api.env
```

### 3. OVMS API env

Real location:
- `/srv/abyss-stack/Secrets/Configs/ovms-api.env`

Bootstrap from example:

```bash
cp env/ovms-api.env.example /srv/abyss-stack/Secrets/Configs/ovms-api.env
chmod 600 /srv/abyss-stack/Secrets/Configs/ovms-api.env
```

### 4. OVMS raw API key file

Real location:
- `/srv/abyss-stack/Secrets/Configs/ovms_api_key.txt`

Create it manually and keep permissions tight:

```bash
printf '%s\n' 'CHANGE_ME_REAL_VALUE' > /srv/abyss-stack/Secrets/Configs/ovms_api_key.txt
chmod 600 /srv/abyss-stack/Secrets/Configs/ovms_api_key.txt
```

### 5. ToS graph helper env

Real location:
- `/srv/abyss-stack/Secrets/Configs/tos-graph.env`

Bootstrap from example:

```bash
cp env/tos-graph.env.example /srv/abyss-stack/Secrets/Configs/tos-graph.env
chmod 600 /srv/abyss-stack/Secrets/Configs/tos-graph.env
```

Related stack-level defaults that usually belong in `/srv/abyss-stack/Configs/stack.env`:
- `AOA_TOS_ROOT=/srv/Tree-of-Sophia`
- `AOA_TOS_GRAPH_HOST_PORT=5410`
- `TOS_GRAPH_WRITE_ENABLED=false`

## Minimum expectation

Before trying to run the full Intel-aware or agentic surface, ensure that these paths exist in real form.

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
