# STORAGE LAYOUT

## Canonical roots

- `/srv/abyss-stack` — active deployed runtime root
- `/abyss` — optional mounted vault for heavy data

See also: [PATHS](PATHS.md) for the distinction between source checkout paths and deployed runtime paths.

## Active runtime tree

Expected live structure under `/srv/abyss-stack`:

```text
/srv/abyss-stack/
  Configs/
  Secrets/
  Services/
  Models/
  Knowledge/
  Logs/
  .codex-home/
```

## Meaning of the main directories

- `Configs/` — deployed stack repo material such as compose modules, profiles, scripts, docs, config templates, and runtime config files bootstrapped from those templates
- `Secrets/` — real env files, API keys, and secret-bearing runtime material
- `Services/` — persistent state for databases and runtime services, plus a few runtime service-local inputs such as the LiteLLM config file
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
- `/srv/abyss-stack/Secrets`
- live `stack.env`
- any secret-bearing mounted file used by services
