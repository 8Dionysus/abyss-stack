---
name: abyss-self-diagnostic-spine
description: Diagnose or review one concrete Abyss runtime target through the abyss-stack diagnostic spine, using current owner evidence and last-good, drift, or freshness comparison. Use for a named preset, profile, truth goal, or diagnostic_session_v1. Do not use for generic health questions, artifact trust, source disputes, immediate repair/restart, session mining, or when no runtime evidence is needed.
---

# Abyss Self-Diagnostic Spine

## Intent

Use the `abyss-stack` owner interface to locate one concrete runtime target,
obtain or inspect one typed diagnostic packet, and return an evidence-linked
review without acquiring repair authority.

This owner package is the canonical procedure. The semantic graph, KAG record,
installed copy, generated diagnostic catalog, and runtime packet are derived or
observed surfaces; none replaces it.

## Return to the owner source

Use the skill directory reported by the host as the bundle root.

1. When it is `<owner-root>/skills/abyss-self-diagnostic-spine/`, require the
   adjacent owner root to be an `abyss-stack` source checkout and use it.
2. Otherwise read only `.aoa-skill-source.json` beside this `SKILL.md`.
3. Require `schema_version` to be `aoa_skill_source_receipt_v1` or
   `aoa_skill_source_receipt_v2`,
   `name=abyss-self-diagnostic-spine`, `owner_repo=abyss-stack`,
   `source_path=skills/abyss-self-diagnostic-spine`, and `version=0.2.4`.
   For v2 also require non-empty `digest`, `source_fingerprint`,
   `source_fingerprint_scope`, and `prompt_description_sha256`. When
   `capability_graph_hash` is present, require it to be a non-empty string and
   preserve it.
4. Follow the exact `owner_root` and `source_path` from that receipt. Require
   the owner contract to repeat the same identity, version, and admitted
   lifecycle.
5. Stop as `blocked_owner_source` when the receipt or owner package is missing,
   ambiguous, or version-stale. Do not search sibling repositories for a
   plausible copy.

Report the receipt schema and v2 identity dimensions when present. The receipt
is a machine-local source locator and package identity record, not proof of
owner acceptance, current runtime health, or successful execution.

After an installed copy resolves the canonical bundle, switch the bundle root
to that exact owner directory. Do not reread its `SKILL.md` and do not read
references from the installed copy. Read the contract and selected procedure
only from the canonical owner bundle.

## Start

From the resolved canonical bundle, before target reads or execution:

1. Read [references/contract.yaml](references/contract.yaml).
2. Select exactly one operation: `observe`, `capture`, or `review`.
3. Confirm the required target, truth goal, freshness intent, and effect
   authority.
4. Read [references/diagnose.md](references/diagnose.md) and execute only the
   selected branch.

When the owner root or packet path is already supplied, use it directly. Do
not run directory listings, workspace-wide search, `find`, `rg --files`, or Git
history to rediscover it. Read only the exact owner surfaces named by the
selected branch. A missing named surface blocks the operation; it does not
authorize exploratory search.

Do not load a shared recovery procedure before the owner packet has produced a
verified handoff.

## Owner boundary

- `abyss-stack` owns the diagnostic CLI, schemas, runtime evidence shape,
  truth-status axes, drift vocabulary, and owner-local packet meaning.
- `aoa-session-recovery` owns shared diagnosis and repair procedure after an
  explicit handoff; it does not redefine the owner packet.
- A diagnostic session, companion, reviewed ref, or repair handoff is evidence
  or a candidate. It is not mutation approval, proof, owner acceptance, or a
  successful repair.
- Default execution is read-only. Any file write or latest, last-good, or
  reviewed promotion requires an exact explicit request and the corresponding
  owner CLI flag.

## Stop

Return one typed result with:

- selected operation and concrete target;
- canonical owner source and observation source;
- schema and freshness verdict;
- per-axis states, drift classes, unknowns, and exit class;
- actual effects and skipped checks;
- bounded next owner or explicit blocker;
- claim limit.

Stop after one packet and one review. Do not retry with broader selectors,
repair the runtime, refresh unrelated evidence, promote an anchor, mutate a
quest, or turn a handoff into owner acceptance.
