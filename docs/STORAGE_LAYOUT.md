# STORAGE LAYOUT

## Canonical roots

- `/srv/abyss` — active runtime root
- `/abyss` — optional mounted vault for heavy data

## Active runtime tree

Expected live structure under `/srv/abyss`:

```text
/srv/abyss/
  Configs/
  Secrets/
  Services/
  Models/
  Knowledge/
  Logs/
  .codex-home/
```

## Meaning of the main directories

- `Configs/` — compose modules, profiles, scripts, and service configs
- `Secrets/` — real env files, API keys, and secret-bearing runtime material
- `Services/` — persistent state for databases and runtime services
- `Models/` — local model weights and related serving artifacts
- `Knowledge/` — local knowledge corpora and helper inputs
- `Logs/` — logs and generated runtime artifacts
- `.codex-home/` — isolated agent or codex-style runtime home

## Heavy-data caution

`/abyss` must not be assumed to exist just because it exists in the architecture.
Before heavy operations, check whether it is actually mounted.

Recommended checks:

```bash
findmnt /abyss
ls -la /abyss | head
```

If `/abyss` is not mounted, heavy writes may spill onto the system disk.

## Secret rule

Never commit or publish real runtime material from:
- `/srv/abyss/Secrets`
- live `stack.env`
- any secret-bearing mounted file used by services
