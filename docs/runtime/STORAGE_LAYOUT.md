# STORAGE LAYOUT

## Canonical roots

- `/srv/AbyssOS/abyss-stack` — active deployed runtime root
- `/abyss` — optional mounted vault for heavy data

See also: [PATHS](PATHS.md) for the distinction between source checkout paths and deployed runtime paths.

## Active runtime tree

Expected live structure under `/srv/AbyssOS/abyss-stack`:

```text
/srv/AbyssOS/abyss-stack/
  Configs/
  Secrets/
  Services/
    monitoring/
      prometheus/
      alertmanager/
      loki/
      tempo/
      alloy/
      grafana/
  Models/
  Knowledge/
    federation/
    kag/
      repo-self/
        cas/
          objects/sha256/
        distribution/
          owners/
          composition/
          current.json
        exact/
          repo-self.sqlite3
          repo-self.last-good.sqlite3
        vector/
          owner-slices.json
          owner-slices.last-good.json
        graph/
          owner-slices.json
          owner-slices.last-good.json
        receipts/
        current.json
  Logs/
    machine-bridge/
    diagnostics/
    eval-exports/
    host-facts/
    memo-exports/
    rpg/
    tos-graph/
    platform-adaptations/
    runtime-benchmarks/
  .codex-home/
```

## Meaning of the main directories

- `mechanics/federation-seams/parts/rpg-runtime/generated/` — source-managed public-safe RPG transport collections for SDK loading, review, and runtime parity checks
- `Configs/` — deployed stack repo material such as compose modules, profiles, scripts, docs, config templates, and runtime config files bootstrapped from those templates
- `Secrets/` — real env files, API keys, and secret-bearing runtime material
- `Services/` — persistent state for databases and runtime services, plus source-managed build contexts and service-local inputs for lightweight helper services such as `langchain-api`, `litellm`, `docs-api`, `route-api`, `rerank-api`, `tos-graph`, `qwen3-tts-api`, `babelvox-tts-api`, and `tts_router`
- `Services/monitoring/` — explicit bind-mounted Prometheus, Alertmanager,
  Loki, Tempo, Alloy, and Grafana state. These paths keep persistence under the
  stack owner and carry private SELinux relabeling through the rendered Podman
  mount contract.
- `Models/` — local model weights and related serving artifacts
- `Knowledge/` — local knowledge corpora; verified repo-self KAG CAS objects,
  candidate/current/last-good distribution state, exact/vector/graph
  projections, coordinated last-good state, and receipts under
  `Knowledge/kag/repo-self/`; and
  runtime-local mirrors of public-safe federation surfaces such as
  `Knowledge/federation/aoa-agents/`,
  `Knowledge/federation/aoa-routing/`,
  `Knowledge/federation/aoa-memo/`,
  `Knowledge/federation/aoa-evals/`,
  `Knowledge/federation/aoa-playbooks/`,
  `Knowledge/federation/aoa-kag/`, and the source-owned companion
  `Knowledge/federation/tos-source/`

KAG CAS and distribution state are mutable runtime read models. They may be
recreated from verified owner-family releases or exact owner source snapshots
and must not be copied back into Git as canonical records.

The exact SQLite database is one physical store with owner-local transactional
updates. Qdrant collections are content-addressed per owner. Neo4j owner-node
slices and directional owner-pair relation/reference slices are immutable and
selected through the current state map. Their `*.last-good.*` coordinates keep
one previous mutually consistent generation for bounded rollback; they are
runtime state, not a second source of truth.
- `Logs/` — logs and generated runtime artifacts, including stack-side `abyss-machine` bridge records under `Logs/machine-bridge/`, diagnostic spine sessions, diagnosis companions, reviewed diagnosis refs, repair handoffs, and `last_good` anchors under `Logs/diagnostics/`, local private host-facts captures under `Logs/host-facts/`, memo export candidates under `Logs/memo-exports/`, eval export candidates under `Logs/eval-exports/`, RPG runtime copies under `Logs/rpg/`, ToS graph helper artifacts under `Logs/tos-graph/`, platform-adaptation records under `Logs/platform-adaptations/`, and runtime benchmark artifacts under `Logs/runtime-benchmarks/`
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
- `/srv/AbyssOS/abyss-stack/Secrets`
- live `stack.env`
- any secret-bearing mounted file used by services
- private machine-bridge captures under `/srv/AbyssOS/abyss-stack/Logs/machine-bridge/`
- private host-facts captures under `/srv/AbyssOS/abyss-stack/Logs/host-facts/`
- diagnostic spine artifacts under `/srv/AbyssOS/abyss-stack/Logs/diagnostics/`
- private memo export candidates under `/srv/AbyssOS/abyss-stack/Logs/memo-exports/`
- private eval export candidates under `/srv/AbyssOS/abyss-stack/Logs/eval-exports/`
- public-safe RPG runtime copies under `/srv/AbyssOS/abyss-stack/Logs/rpg/`
- private platform-adaptation captures under `/srv/AbyssOS/abyss-stack/Logs/platform-adaptations/`
