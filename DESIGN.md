# DESIGN.md

System-form design for `abyss-stack`.

## Role

This file describes the intended shape of the `abyss-stack` runtime substrate.
It is not the charter, roadmap, deployment guide, architecture diagram, or agent
instruction card.

It answers one question: what form should the runtime body take so AoA, ToS, and
the wider AbyssOS workspace can grow without the infrastructure absorbing their
meaning?

## Thesis

`abyss-stack` is the runtime body of the ecosystem. Its best form is explicit,
portable, recoverable infrastructure that can run services, project configs,
carry evidence, and expose bounded seams without becoming the constitutional
center, the authored corpus, or the proof layer.

The source checkout should describe how to create a runtime. The deployed
runtime should carry the live state needed to operate it. The two must stay
connected, but they must not collapse into the same thing.

## Design as Appearance

A healthy `abyss-stack` looks like a working runtime map:

- a source-only GitHub mirror that can bootstrap a machine without carrying live
  secrets, models, logs, or private captures
- an explicit deployed runtime root under `/srv/AbyssOS/abyss-stack`
- clear districts for compose modules, config templates, env examples, systemd
  units, scripts, mechanics, MCP access planes, local memo and stats ports,
  docs, tests, and local agent overlays
- profile and preset surfaces that make service selection visible
- mechanic packages that describe runtime moves as packages and parts, not as a
  flat pile of historical files
- generated catalogs and diagnostic outputs that are useful companions but never
  stronger than their source documents

If the repository can be skimmed from root to package to part without guessing
which surface owns the truth, the design is working.

## Anatomy

The runtime body has these organs:

- **source checkout**: versioned public-safe source, templates, scripts, docs,
  schemas, examples, tests, and workflows
- **deployed runtime root**: the operator-owned live tree where configs, state,
  logs, models, and secrets may exist outside source history
- **config projection**: install, sync, render, bootstrap, and parity contracts
  that connect source to runtime without blurring authority
- **service topology**: Podman modules, profiles, presets, ports, networks, and
  helper-service build contexts
- **working substrate selection**: the conservative `substrate` profile owned
  by this repo, with workflow automation, local workers, federation seams,
  tools, and observability layered through explicit profiles or presets
- **lifecycle control**: start, stop, wait, smoke, logs, status, warmup, and
  systemd-user flows
- **machine fit**: host facts, reference-platform posture, bridge capture,
  platform adaptation, and bounded local tuning
- **inference pilots**: local trials, promotion loops, and model-route evidence
  that stay runtime-owned rather than proof-owned
- **federation seams**: opt-in runtime bridges to sibling repositories that
  consume or mirror surfaces without stealing their authority
- **runtime knowledge projections**: manifest-bound exact, lexical, vector,
  and graph read models built from owner-qualified KAG records and consumed
  through storage-neutral application ports
- **MCP access planes**: stdio or authenticated host-local adapters that expose
  bounded live or derived context while keeping owner-layer authority intact
- **local memo port**: runtime-side memory candidates, receipts, exports, and
  local notes that route durable review to `aoa-memo`
- **local stats port**: runtime-owned statistical questions whose definitions
  stay beside their owner evidence while `aoa-stats` supplies shared grammar
  and cross-owner composition
- **diagnostics and repair**: read models, receipts, closeout contracts, and
  repair posture that support honest operation without claiming autonomous
  healing
- **validators and tests**: the executable memory that keeps topology, required
  files, hygiene, and route contracts from drifting silently

## Operation

The expected runtime path is:

1. Start from the source checkout.
2. Choose a profile, preset, or mechanic route with visible intent.
3. Create or update the runtime layout through documented scripts.
4. Project public-safe configs from source to runtime.
5. Keep private state in runtime-owned locations outside git.
6. Run the narrow validator or smoke path that proves the changed contract.
7. Leave evidence where the next operator or agent can find it.

Every operation should preserve a return path: what changed, what was checked,
what was not checked, and what surface owns the next decision.

## Design Principles

- **Runtime, not meaning.** This repository runs and supports the ecosystem; it
  does not author the doctrine of sibling layers.
- **Source before runtime.** Public source explains and creates runtime; live
  runtime state does not become source truth.
- **Profiles before hidden coupling.** Service selection should be visible in
  profiles, presets, scripts, and docs.
- **Substrate before workers.** The working AbyssOS base should be runnable
  from `abyss-stack` without silently pulling workflow automation, model
  workers, federation seams, tools, or dashboards into every startup.
- **Localhost-first exposure.** Network posture should begin narrow and widen
  only through explicit operator intent.
- **Rootless by default.** Runtime control should prefer rootless Podman and
  user-scoped systemd unless a specific operation proves otherwise.
- **Portable mirror, private state.** GitHub should be enough to bootstrap; it
  should not contain secrets, heavy models, local databases, logs, or captures.
- **Mechanics are packages.** Runtime moves belong in named packages with parts,
  provenance, landing notes, and validation paths.
- **Seams are subordinate.** Federation routes may support sibling truth, but
  they cannot replace it.
- **Local semantics, shared grammar.** Runtime populations, windows, and
  evidence stay with their stack owner; `aoa-stats` validates their common
  measurement form without absorbing that meaning.
- **Adapters schedule; owners select inputs.** Runtime adapters may invoke a
  sibling's deployed command, but they should not duplicate that sibling's
  internal registry or source-selection policy when the command owns a stable
  default.
- **Generated companions stay companions.** Catalogs, indexes, diagnostics, and
  reports help navigation; source surfaces remain authoritative.
- **Recovery is part of design.** A runtime surface is incomplete if it cannot
  be stopped, inspected, repaired, or rolled back with bounded evidence.

## Good Design Feels Like

- a new machine can be bootstrapped from the checkout by following documented
  scripts and public-safe examples
- root docs answer "where do I go" quickly, then hand off to package-local
  surfaces
- service, storage, port, and secret boundaries are visible before runtime
  mutation
- legacy names appear only in provenance, legacy homes, or compatibility bridges
- validation fails on obvious dangerous drift but does not become a brittle
  policy maze

## Bad Design Smells Like

- root folders act as a flat attic for unrelated runtime artifacts
- live `/srv/AbyssOS/abyss-stack` files are treated as if they were source
- public docs make private machine claims without source evidence
- generated surfaces become the only place a route can be understood
- old wave, seed, version, or experiment labels are active topology names
- sibling repository meaning is copied here instead of routed to its owner
- validators ignore important route surfaces or block ordinary public examples

## Relationship to Other Root Surfaces

- `README.md` introduces the repository and routes readers by need.
- `CHARTER.md` authorizes the repository's owner lane.
- `BOUNDARIES.md` names what belongs here and what must stay elsewhere.
- `AGENTS.md` tells agents how to move safely through the repository.
- `DESIGN.AGENTS.md` describes the intended shape of agent-facing guidance.
- `ROADMAP.md` names current direction and future triggers.
- `docs/runtime/ARCHITECTURE.md` maps the runtime structure in more concrete detail.
- `mechanics/README.md` is the atlas for runtime moves.

## Use by Agents

Before changing root topology, source/runtime contracts, mechanics shape,
deployment posture, federation seams, diagnostics, or generated/source authority,
check this file. If a change makes this file inaccurate, update it or add a
decision note explaining why the design moved.
