# Exact Content-Addressed Runtime Subject Admission

- Decision ID: ABYSS-STACK-D-0128
- Status: accepted
- Date: 2026-08-20
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`

## Index Metadata

- Original date: 2026-08-20
- Surface classes: public-contract, runtime-profile
- Stack lanes: governed-execution
- Mechanic parents: `mechanics/governed-execution`
- Guard families: model admission, runtime identity, source/runtime separation
- Posture: accepted runtime rationale

## Context

The prepared owner duty names a Codex `0.148.0` realization and an exact
content-addressed runtime subject, while the source and active installed
profile admitted only `0.147.0`. The runtime checked the product, version,
transport, and access regime but ignored the stronger runtime-subject identity.
That allowed a profile to describe a lane without proving that the realization
selected the exact runtime package intended by the owner binding.

## Options considered

- Refresh only the prepared realization back to the older admitted version,
  leaving the source contract unable to admit the prepared owner input.
- Admit the new version by version string alone, preserving a version-only
  runtime identity boundary.
- Pin the prepared version and exact content-addressed runtime subject in the
  source profile, validate that shape, and compare the realization subject
  byte-for-byte during runtime admission.

## Decision

The external Codex runtime profile admits `0.148.0` only together with its
exact `content_addressed_runtime_package` subject. Runtime admission retains
the existing product/version/transport/access/lifecycle checks and additionally
requires the realization's complete `configuration.runtime.runtime_subject`
mapping to equal the profile's `model_admission.runtime_subject` mapping.

## Rationale

Exact subject equality preserves fail-closed owner binding without inferring
package identity from a mutable version label. The profile remains the
abyss-stack runtime contract, while `aoa-models` continues to own the
realization and its meaning. The source repair does not install, deploy, or
claim that the host's active release already matches; those are separate
source/runtime and live-evidence checks.

## Consequences

- Positive: a prepared realization cannot enter the external Codex lane unless
  its exact content-addressed runtime subject is the one admitted by the
  runtime profile.
- Positive: missing or mismatched subject data fails before Codex preflight or
  process launch.
- Tradeoff: the source profile and its paired fixtures now require the `0.148.0`
  subject, so the currently installed older release remains a deliberate
  source/runtime drift until an authorized install route updates it.
- Follow-up: an authorized install/host-canary owner must prove release
  packaging, executable identity, login/catalog preflight, and live process
  behavior before any runtime-health claim is made.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-runtime-profile.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`

## Follow-up route

The next authorized runtime/install owner must reconcile this source profile
with the deployed release and provide a bounded host canary. This decision does
not grant install, deployment, service, secret, wake, or owner-acceptance
authority.
