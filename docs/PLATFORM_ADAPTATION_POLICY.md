# PLATFORM ADAPTATION POLICY

## Purpose
This document defines the bounded platform-adaptation record surface for `abyss-stack`.

It exists for the cases where:
- host facts tell you what the machine is
- runtime benchmarks tell you what happened
- but you still need one compact record of what platform seam bent, what adaptation fixed it, and where that fix should travel next

## What belongs here
Use this surface for:
- host-specific performance tuning
- hybrid CPU or accelerator quirks
- WSL or Windows bridge performance notes
- backend route changes caused by platform behavior
- filesystem, mount, cgroup, or container-runtime peculiarities
- bounded compose overlays that should be re-applied on matching hosts
- platform-local adaptations that should be easy to reapply or retest later

Do not use this surface for:
- generic incident timelines
- secret-bearing diagnostics
- broad capability claims
- proof-layer verdicts
- authored meaning from sibling AoA repositories
- unbounded free-form troubleshooting diaries

## Relationship to other artifacts
- `aoa-host-facts` records what a concrete machine looks like
- `aoa-machine-fit` records what runtime posture that machine should currently prefer
- runtime benchmarks record measured runtime behavior
- platform-adaptation records connect the two with bounded diagnosis and adaptation notes

This is the missing middle layer.

## Artifact surfaces
- `mechanics/machine-fit/parts/platform-adaptations/schemas/schema.v1.json` defines the public contract
- `mechanics/machine-fit/parts/platform-adaptations/examples/platform-adaptation.public.json.example` shows the intended public-safe shape
- `${AOA_STACK_ROOT}/Logs/platform-adaptations/` is the local capture root

## Capture modes

### `public`
Use when the record may live in git or be shared across machines.

It should include:
- the platform seam in plain language
- the affected services and runtime path
- the bounded adaptation that helped
- compact before/after metrics
- portability notes and retest triggers
- refs to public-safe host facts or non-secret benchmark summaries when available

It must not include:
- usernames or home paths unless intentionally public
- hostnames, exact local IPs, or mount sources
- secret-bearing env values
- private rendered config

### `private`
Use when preserving a local deployment record or carrying forward machine-local evidence.

It may add:
- fuller local refs
- exact local file paths
- local-only benchmark or log refs
- machine-local deployment notes

It still must not capture secrets.

## Storage contract
Recommended active tree:

```text
${AOA_STACK_ROOT}/Logs/platform-adaptations/
  latest/
    latest.private.json
  records/
    2026-03-27T210430Z__performance__ollama-core-ultra/
      adaptation.private.json
      notes.md
```

Rules:
- keep the machine-readable record small and export-friendly
- put bulky raw evidence elsewhere and reference it
- prefer refs to host-facts and benchmark artifacts over copying their content
- do not assume local absolute paths survive export to another machine

## What a strong record captures
- the seam and symptom
- the scope of impact
- the bounded diagnosis
- the adaptation that changed runtime behavior
- a compact before/after read
- portability guidance
- explicit non-claims

## Export rule
These records should be easy to carry from:
- Linux to another Linux host
- Linux to Windows plus WSL on the same machine
- one runtime root to another

Prefer a small JSON record plus a few refs over a large prose dump.

## Suggested commands

Public-safe scaffold:

```bash
scripts/aoa-platform-adaptation \
  --mode public \
  --title "Short seam title" \
  --summary "One bounded summary" \
  --issue-class performance
```

Local private capture:

```bash
scripts/aoa-platform-adaptation \
  --mode private \
  --title "Short seam title" \
  --summary "One bounded summary" \
  --issue-class performance \
  --overlay compose/tuning/example.yml \
  --write "${AOA_STACK_ROOT}/Logs/platform-adaptations/latest/latest.private.json"
```

## Boundary to preserve
`abyss-stack` may own the runtime-local record of a platform seam and its adaptation.

It does not own the global meaning of that record beyond bounded runtime posture.
