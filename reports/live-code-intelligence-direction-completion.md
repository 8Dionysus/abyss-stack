# LIVE code-intelligence direction — generation 63

## Return

- Goal: `01a02fec-b609-7120-b11c-fa80d34ee86a`
- Owner: `abyss-stack`
- Direction: `LIVE`
- Task: `actor-task:code-intelligence.live-code-intelligence-direction.01a02fec-b609-7120-b11c-fa80d34ee86a.g63.whole-continuation`
- Incarnation: `incarnation:code-intelligence.live-code-intelligence-direction.01a02fec-b609-7120-b11c-fa80d34ee86a.g63.whole-continuation`
- Decision: `submit_for_review`
- Status: `review_required`
- Fresh source work: yes; base `origin/main` at `acee6d7684959ceaace27464c81f1ba23a4f03ea`

Generation 63 continued the reviewed whole LIVE direction in the canonical
`mechanics/runtime-lifecycle/parts/live-code-intelligence/` owner part. The
source contains a bounded Python-AST observation provider, source epochs and
dependency invalidation, candidate/current/last-good lifecycle transitions, the
exact G59 provider-neutral MACHINE consumer ABI, and fail-closed config and
persisted-state hardening. This continuation also rejects tampered persisted
observations, lifecycle records, and malformed last-good records before they
can affect query or discovery claims, and preserves a validated last-good
fallback during degraded refresh. LSP launch identity is bound to the admitted
executable artifact, command, fixed working directory, separately admitted
script interpreter, source root, and observed stdio transport; generic
URI-bearing requests are recursively contained, including local `file:` URIs
hidden in arbitrary nested command arguments; and opened document text must
match a signed per-file source-epoch manifest rather than mutable disk alone.
Machine health is rechecked at binding emission and launch; authenticated
persisted summaries remain bound to capture-time evidence; response headers
are bounded; parser resource failures degrade explicitly; source reads are
parent-symlink-safe on POSIX; state readers and LSP lifecycle transitions are
serialized; and bounded queries report totals and truncation. The LSP child
receives a fixed minimal environment without caller-controlled Python path or
native-loader variables. Python script launches use `-S` and a fixed
manifest-root `PYTHONPATH`, while the complete runtime-root dependency
manifest is rechecked before each launch. The programmatic file-size setting
and its machine envelope remain capped by the authored 1,000,000-byte limit.

The lifecycle contract is executable at the same boundary: `restart` performs
a fresh full source rebuild, `last_good` returns an identity-validated target,
`canary` parses without promotion, and `rollback` restores the validated
last-good snapshot under the state lock. Each lifecycle action leaves one
bounded operation receipt. Source scanning retains no aggregate file-content
buffer: parsing rereads and verifies at most one bounded file at a time. State
promotion, degraded candidates, transition receipts, and operation receipts
roll back together if publication fails. Undecodable POSIX filenames degrade to
explicit diagnostics instead of aborting the refresh. These are stack-local
source-state actions and do not claim a deployed provider process lifecycle.

This is source readiness only. No MACHINE artifact, trust anchor, registry
promotion, provider admission, installation, activation, deployment, runtime
observation, transport, semantic acceptance, proof/eval verdict, or owner
acceptance is claimed.

## Changed paths

- Added the complete source-local part:
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/README.md`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/live_code_intelligence.py`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/tests/test_live_code_intelligence.py`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/config/python-ast-live-provider.json`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/live-code-intelligence-provider.schema.json`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-evidence.schema.json`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-gate.schema.json`
  - `mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-gate-public-key.schema.json`
- Updated canonical routes and source records:
  - `mechanics/runtime-lifecycle/README.md`
  - `mechanics/runtime-lifecycle/DIRECTION.md`
  - `mechanics/runtime-lifecycle/ROADMAP.md`
  - `mechanics/runtime-lifecycle/PARTS.md`
  - `mechanics/runtime-lifecycle/parts/README.md`
  - `mechanics/runtime-lifecycle/PROVENANCE.md`
  - `mechanics/runtime-lifecycle/LANDING_LOG.md`
  - `docs/testing/test_inventory.json`
  - `CHANGELOG.md`
  - `tests/test_schema_contracts.py` (active-schema discovery manifest)

The derived repo-local KAG family was refreshed with the CI-pinned
`aoa-kag@72cea62c76ee8b32304c7c358734276c47833b9a` generator and an explicit
measured-exceedance receipt against base
`acee6d7684959ceaace27464c81f1ba23a4f03ea`. Its exact current identities and
measurements are carried only by
`kag/indexes/index_family.manifest.json` and the digest-addressed receipt
selected by that manifest, avoiding a second stale copy in this report. The
family is navigation data only; it is not authored source authority, provider
trust, consumer admission, deployment, runtime observation, semantic
acceptance, proof/eval, or owner acceptance.

The implementation preserves the existing-root-owned-anchor-only posture:
`/etc/abyss-machine/trust/code-intelligence-gate-ed25519.json` is a required
external trust anchor, not one created by this work. The G59 Universal Ctags
candidate remains unsigned and unadmitted; only its reviewed ABI was integrated.

## Strongest owner-local validation

- Focused LIVE unit tests: `67 passed`.
- Ruff on source and tests: `All checks passed`.
- Python compilation: passed.
- Provider config plus four schemas: all five JSON documents parsed.
- Provider config against its Draft 2020-12 schema: passed.
- Active-schema contract tests: `9 passed`.
- Topology tests: `11 passed`.
- `python3 scripts/validate_stack.py`: `validation passed`.
- `python3 scripts/validate_nested_agents.py`: `53 required nested documents passed`.
- Pinned repo-local KAG family gate: passed with a digest-bound measured-
  exceedance receipt; the committed receipt carries the exact generated and
  tracked-family measurements.

Repository-wide residuals are separate from the changed-surface result:

- `python3 scripts/ci_gate.py --mode source-fast` passed through
  `validate_stack`, then stopped because the local `aoa-stats` validator was
  unavailable at both checked owner-worktree paths.
- `python3 scripts/ci_gate.py --mode tests` collected `2814` tests but stopped
  on seven collection errors: six installed-MCP API errors (`MCPError` versus
  `McpError`, and missing `MCPServer` from `mcp.server`) plus the unavailable
  `aoa_sdk.contracts.programmatic_execution` module from the rebased base seam.

## Reviewed boundaries retained

- G58 accepted the fail-closed source candidate and provider-neutral lifecycle,
  state, observation, and LSP direction. Its rejected machine trust,
  admission, deployment, runtime, proof, and acceptance claims remain
  rejected.
- G59 accepted the exact MACHINE consumer ABI for source integration. Its
  unsigned Universal Ctags candidate remains unpromoted, untrusted,
  uninstalled, unadmitted, undeployed, and unexecuted.
- G60 does not supply a proof/eval verdict; eval remains a separate owner gate.
- G62 accepted the exact owner-bound source return and continuation obligation,
  but rejected the claimed landing, runtime proof, provider execution,
  repository-wide validation, transport semantics, proof/eval verdict, and
  owner acceptance. G63 reclassification authorizes this holder to carry the
  same whole direction through source-only GitHub landing.
- No G42 INDEXED output was accepted because no exact later master disposition
  was supplied.

## Runtime return ABI

```text
from_status: active
to_status: review_required
owner: abyss-stack
approval_posture: master_review_required
rollback_reentry_route: master:01a02fec-b609-7120-b11c-fa80d34ee86a
proposed_action: wake_parent
condition_id: validated-return
```

The completion JSON contains the exact task, continuation, correlation,
incarnation, immutable-input digests, changed-path hashes, validation claims,
and residual boundary.

## Effects and next route

No services, host configuration, storage, secrets, trust roots, provider
artifacts, runtime processes, or external admission state were mutated. The
source is ready for the authorized source-only Git landing route, subject to
GitHub checks; source landing and owner acceptance remain distinct claims.
After landing, the next substantive gates are MACHINE producer evidence and
admission, deployed runtime/restart/last-good and LSP/transport evidence, then
semantic and proof/eval review.

## Fixed validation commands

The required fixed commands are recorded in the completion JSON and are run
last after this artifact is added, with no source mutation after they pass.
