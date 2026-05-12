# REFERENCE PLATFORM SPEC

This document defines the machine-readable host-facts layer for `abyss-stack`.

## Why it exists

`REFERENCE_PLATFORM.md` tells you the intended host shape.
The host-facts layer records what a concrete machine actually looks like.
The machine-fit layer then decides what that host should currently prefer.

## Artifact surfaces

- `mechanics/machine-fit/parts/host-facts/schemas/schema.v1.json` defines the v1 public contract.
- `mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json.example` shows the intended public-safe shape while the repository is still on scaffold-only host facts.
- `mechanics/machine-fit/parts/host-facts/examples/reference-host.public.json` is the future commit-safe snapshot for the chosen canonical Linux reference host and should not be added until that host is selected and reviewed.
- `${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json` is the local fuller snapshot and must not be committed.

## Capture modes

### `public`

Use when the artifact may live in git. It should include:
- OS family and version
- kernel release
- architecture
- CPU model and counts
- total memory and swap
- Podman, compose, systemd-user, and SELinux posture
- stack root and vault root posture
- storage summaries for `/`, `${AOA_STACK_ROOT}`, and `${AOA_VAULT_ROOT}`

It must not include:
- serial numbers
- MAC addresses
- local IP addresses
- secret-bearing env values
- disk UUIDs
- exact mount sources
- usernames or home paths unless intentionally public

### `private`

Use when debugging or preserving a local deployment record. It may add:
- hostname
- exact mount sources
- block-device names and mountpoints
- fuller CPU and storage detail

It still must not capture secrets.

## Top-level contract

Required top-level keys:
- `artifact_kind`
- `schema_version`
- `capture_mode`
- `captured_at`
- `captured_by`
- `platform`
- `runtime`
- `paths`

Optional sections:
- `cpu`
- `memory`
- `acceleration`
- `storage`
- `redaction`

## Review rule

If a proposed field makes attacker reconnaissance easier but does not materially help runtime understanding, it does not belong in the public artifact.

## Recommended flow

1. Update or confirm the normative posture in `REFERENCE_PLATFORM.md`.
2. Capture a public snapshot and review it before commit.
3. Capture a private snapshot locally when you need fuller deployment evidence.
4. Keep the schema version stable until the contract changes.
5. Use [MACHINE_FIT_POLICY](MACHINE_FIT_POLICY.md) when you need the bounded current-host runtime posture.
6. When the shape changes, update this doc, the schema, the capture script, validation, and workflow coverage together.

## Suggested commands

```bash
scripts/aoa-host-facts --mode public --write /tmp/reference-host.public.review.json
scripts/aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/latest.private.json"
```

## Expected review sequence

1. capture
2. inspect the public artifact for overexposed fields
3. commit the public artifact only when you are refreshing the chosen canonical Linux reference host
4. leave the private artifact in `${AOA_STACK_ROOT}/Logs/host-facts/`
