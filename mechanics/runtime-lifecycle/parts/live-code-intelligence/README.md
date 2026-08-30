# LIVE Code Intelligence

## Mechanic card

This part owns the first runtime-local LIVE code-observation slice for a
Python working tree. It snapshots source bytes, emits provider-neutral
definitions/references/calls/imports with an exact source epoch, and advances
only complete observations to `current.json`.

### Trigger

Use this part when a runtime needs a bounded LIVE view of a changing source
tree before an owner-qualified INDEXED projection is available.

### abyss-stack owns

- provider lifecycle mechanics for the bootstrap observer;
- source-epoch calculation and bounded file invalidation;
- candidate/current/last-good state, refresh receipts, and read-only status;
- the configured Python bootstrap provider identity and state-root layout.

### Stronger owner split

`aoa-kag` owns the meaning and normalization of code observations. `abyss-machine`
owns installed provider artifacts and admission. `aoa-evals` owns proof and
verdicts. An eventual LSP, Tree-sitter, SCIP, or Ctags adapter must enter
through the same envelope rather than changing this runtime state contract.

### Inputs

- a source root containing public-safe Python working-tree bytes;
- `config/python-ast-live-provider.json`;
- an operator-selected runtime state root outside the source checkout;
- optionally, an `abyss-machine` content-addressed registry/gate bundle outside
  the source root. A raw JSON evidence receipt is never an admitted input.

### Outputs

- `current.json` after a complete parse;
- `candidate.json` plus a degradation receipt after a parse or size failure;
- `last-good.json` after a later successful promotion;
- one bounded operation receipt per lifecycle action under `operations/`;
- compact definitions and references query envelopes carrying source epoch and
  freshness, result totals, and an explicit truncation flag when the bounded
  result limit is reached;
- provider-neutral lifecycle, LSP-session, observation-lane, and owner-review
  read models, with machine-owned receipt details only after an owner-gated
  registry record passes the boundary.

The executable boundary is the module itself. A caller supplies one operation
(`discover`, `refresh`, `status`, `definitions`, `references`, `restart`,
`last_good`, `canary`, or `rollback`) plus explicit config, source-root, and
state-root arguments; the boundary emits one JSON result with
`PROVIDER_BOUNDARY_SCHEMA`. Refresh state also carries a
machine-bound observation envelope. Its stable blast-radius universe is the
union of the previous and current source-file sets, so partial and complete
deletions remain bounded by `0.0..1.0`.

Refreshes serialize per state root, source traversal rejects symlink escapes,
and source ingestion hashes the tree without retaining an aggregate byte buffer;
the provider rereads at most one bounded file payload at a time for parsing,
verifying its digest and size against the scan. The configuration digest covers
provider, source, state, and owner-boundary identity so a route or ownership
change forces a fresh observation. Current and last-good fallback are served
only when that identity still matches the active configuration.

The machine envelope records the source-local installation identity, artifact
subject/source reference, trust and admission posture, declared resource
envelope, and the fact that machine-owned live measurement is still
`unobserved`. These fields are candidate evidence, not an admission or health
receipt. Runtime entry validates the complete authored provider schema and
accepts only the exact Python bootstrap identity, owner boundaries, and
unadmitted source-candidate machine posture. Self-asserted trusted/admitted
values, missing installation identity, extra schema fields, and persisted
provider or machine-envelope mismatches fail closed.

Machine evidence may be supplied with `--machine-evidence`, but that argument
accepts only the bundle described by
`config/schemas/machine-code-intelligence-gate.schema.json`. The bundle binds an
exact inner record to `cas://sha256:...` registry and gate references, then
verifies a detached Ed25519 signature over the exact provider/config/source,
claim-limit, and registry-record identities. The public key is read only from
the fixed root-owned machine trust anchor
`/etc/abyss-machine/trust/code-intelligence-gate-ed25519.json`; it is never
accepted from the receipt, config, path, owner string, or a private Python
marker. If the anchor or signature is absent/invalid, the runtime fails closed.

The inner v1 record remains useful as a provider-neutral evidence shape and is
validated against `config/schemas/machine-code-intelligence-evidence.schema.json`,
but its unkeyed `receipt_digest` is integrity-only and cannot authenticate the
issuer. A gated record can describe a Python lane and a second-language lane
without turning either into KAG meaning, proof, deployment, or owner
acceptance. An observed LSP session must bind its source root, the exact
provider-specific artifact when one is supplied, and, when arguments are used,
the exact command digest; the launched executable must match that admitted
artifact digest. Document URIs are canonicalized and contained within the
admitted source root before requests leave the process. Only evidence returned
by the authenticated gate route can authorize an LSP session; direct caller
mappings remain untrusted. Machine health is rechecked whenever a binding is
emitted or an LSP session is started, so stale evidence falls back to the
unobserved candidate posture while already-captured source snapshots remain
queryable. A script-backed LSP command must name one absolute interpreter whose
digest is separately admitted by the machine receipt; helper shebangs and
inherited `PATH` selection are rejected. Launches use the admitted runtime root
as their fixed working directory, and generic requests/notifications recursively
validate URI-bearing parameters against that root. `open_document` admits only
bounded UTF-8 bytes whose digest matches the signed source-epoch manifest, so an
unsaved buffer or a changed working-tree file cannot be attributed to this
admitted source-root session. This source candidate contains no machine key,
registry admission, provider installation, or live runtime evidence.

The LSP child receives a fixed minimal environment (`PATH`, C locale, and
`PYTHONNOUSERSITE`); caller-controlled Python path and native-loader variables
are not inherited. Python receives only a fixed `PYTHONPATH` rooted in the
manifest-bound runtime directory and starts with site initialization disabled.
Generic request validation also rejects any local `file:` URI found in nested
values, including server-defined command argument arrays. Both
the file-size setting and its machine resource envelope remain capped by the
authored 1,000,000-byte limit even for programmatic configuration construction.

Persisted machine summaries are compared with the authenticated evidence captured
when the runtime instance was admitted; changing both persisted copies cannot
rewrite that provenance. An LSP session is admitted only for an observed `stdio`
transport, and its response reader bounds each header line, the cumulative header
bytes, and the header count before allocating a message body. The machine
session evidence also binds a sorted digest manifest of the complete runtime
root, so a script-backed LSP cannot import an unadmitted sibling or package;
Python launches use `-S` plus a fixed manifest-root `PYTHONPATH` to keep site
packages and `sitecustomize` outside the launch boundary. The source-root
manifest binds each opened document to the observed `source_epoch`; changing
the working-tree file after admission is rejected rather than silently
re-attributed to the old epoch.

The runtime exposes provider-neutral lifecycle operations (`refresh`,
`restart`, `last_good`, `canary`, and `rollback`), an explicit LSP-session
surface, observation lanes, an explicit bounded provider-worker queue, and an
`owner_review` surface. Python source work is drained in deterministic,
serialized batches while candidate/current/last-good promotion remains under
the refresh lock. Source reads use descriptor-relative, no-follow parent walks
on POSIX, and status/discover/definitions/references hold the refresh lock
across their complete state snapshot. LSP start/close/restart transitions are
serialized per session. `restart` executes a fresh complete source scan and parse;
`last_good` returns the identity-validated rollback pointer; `canary` parses
the working tree without promotion; and `rollback` atomically restores
`last-good.json` as current while clearing a failed candidate. State promotion,
candidate handling, transition receipts, and the corresponding operation
receipt are rolled back together if receipt publication fails. Each action
writes one bounded per-operation receipt under the state root. The
substantially different TypeScript/LSP lane is exposed as a receipt-only,
not-started worker route until its owner supplies live evidence. These are
stack-local source-state actions and do not claim a deployed provider process,
installation, admission, health, proof, landing, or owner acceptance.

### Must not claim

- LSP availability, installation, deployment, or service health;
- semantic identity across rename, move, split, or merge;
- INDEXED knowledge, PROVEN evidence, proof, or owner acceptance;
- that a green source test is a live runtime check;
- that a machine-bound candidate envelope is provider installation, trust,
  admission, deployment, or live health evidence.

### Validation

```bash
python -m unittest mechanics/runtime-lifecycle/parts/live-code-intelligence/tests/test_live_code_intelligence.py -v
python -m py_compile mechanics/runtime-lifecycle/parts/live-code-intelligence/live_code_intelligence.py
python3 -m json.tool mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-evidence.schema.json
python3 -m json.tool mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-gate.schema.json
python3 -m json.tool mechanics/runtime-lifecycle/parts/live-code-intelligence/config/schemas/machine-code-intelligence-gate-public-key.schema.json
```

### Next route

Route normalized observation admission to `aoa-kag`, installed provider and
resource questions to `abyss-machine`, and refactor/proof evaluation to
`aoa-evals`. Runtime activation remains an explicit operator action.
