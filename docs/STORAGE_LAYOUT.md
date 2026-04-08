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
    federation/
  Logs/
    diagnostics/
    eval-exports/
    host-facts/
    memo-exports/
    rpg/
    platform-adaptations/
    runtime-benchmarks/
  .codex-home/
```

## Meaning of the main directories

- `generated/rpg/` — source-managed public-safe RPG transport collections for SDK loading, review, and runtime parity checks
- `Configs/` — deployed stack repo material such as compose modules, profiles, scripts, docs, config templates, and runtime config files bootstrapped from those templates
- `Secrets/` — real env files, API keys, and secret-bearing runtime material
- `Services/` — persistent state for databases and runtime services, plus source-seeded build contexts and service-local inputs for lightweight helper services such as `langchain-api`, `litellm`, `docs-api`, `qwen3-tts-api`, and `tts_router`
- `Models/` — local model weights and related serving artifacts
- `Knowledge/` — local knowledge corpora, helper inputs, and runtime-local mirrors of public-safe federation surfaces such as `Knowledge/federation/aoa-agents/`, `Knowledge/federation/aoa-routing/`, `Knowledge/federation/aoa-memo/`, `Knowledge/federation/aoa-evals/`, `Knowledge/federation/aoa-playbooks/`, `Knowledge/federation/aoa-kag/`, and the source-owned companion `Knowledge/federation/tos-source/`
- `Logs/` — logs and generated runtime artifacts, including diagnostic spine sessions, diagnosis companions, reviewed diagnosis refs, repair handoffs, and `last_good` anchors under `Logs/diagnostics/`, local private host-facts captures under `Logs/host-facts/`, memo export candidates under `Logs/memo-exports/`, eval export candidates under `Logs/eval-exports/`, RPG runtime copies under `Logs/rpg/`, platform-adaptation records under `Logs/platform-adaptations/`, and runtime benchmark artifacts under `Logs/runtime-benchmarks/`
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

## Runtime-only seam

Not every runtime subtree is source-managed yet.

Current intentional seam:

- `Services/aoa-browser/ms-playwright/` remains runtime-only browser payload
- the `aoa-browser` service now uses a source-managed build context, but its browser payload remains machine-local runtime state

## Secret rule

Never commit or publish real runtime material from:
- `/srv/abyss-stack/Secrets`
- live `stack.env`
- any secret-bearing mounted file used by services
- private host-facts captures under `/srv/abyss-stack/Logs/host-facts/`
- diagnostic spine artifacts under `/srv/abyss-stack/Logs/diagnostics/`
- private memo export candidates under `/srv/abyss-stack/Logs/memo-exports/`
- private eval export candidates under `/srv/abyss-stack/Logs/eval-exports/`
- public-safe RPG runtime copies under `/srv/abyss-stack/Logs/rpg/`
- private platform-adaptation captures under `/srv/abyss-stack/Logs/platform-adaptations/`
