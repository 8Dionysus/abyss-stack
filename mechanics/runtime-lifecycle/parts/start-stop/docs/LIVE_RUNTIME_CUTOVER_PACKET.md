# Live Runtime Cutover Packet

## Role

This packet owns the active route for live runtime-loop cutover. It covers
runtime-loop consumption, operational cutover decisions, platform hardening,
and source/deployed parity without making source validation pretend to be live
runtime health.

Use it when deciding whether a source-ready or deployed runtime seam should
become part of the live loop.

## Required Inputs

- a green source/runtime parity packet
- current host facts and machine-fit posture
- explicit profile or preset intent
- runtime status evidence from the deployed mirror
- diagnostic output when a truth goal or repair handoff is in question
- federation checks when live advisory seams are selected

## Cutover Gates

Run the read-only gates before any start, stop, restart, or systemd action:

```bash
python scripts/validate_stack.py
python scripts/validate_stack.py \
  --parity-check \
  --deployed-configs-root /srv/AbyssOS/abyss-stack/Configs
scripts/aoa-host-facts --mode public --write /tmp/abyss-stack-host-facts.public.json
scripts/aoa-machine-bridge --mode public --write /tmp/abyss-stack-machine-bridge.public.json
scripts/aoa-machine-fit --mode public --write /tmp/abyss-stack-machine-fit.public.json
scripts/aoa-profile-endpoints --preset agent-federation
scripts/aoa-federated-check
scripts/aoa-status --autonomy --json
scripts/aoa-diagnose --profile core --truth-goal deployed --write /tmp/abyss-stack-diagnostic-session.public.json
```

Only after these gates are reviewed should an operator choose one explicit
mutation route such as `aoa-up`, `aoa-down`, `aoa-smoke --with-internal`,
`aoa-install-systemd`, or a profile/preset change.

## 2026-05-14 UTC / 2026-05-13 Local Verdict

The packet was run as a read-only cutover inspection after live Configs parity
was restored. Public host facts, machine bridge, and machine-fit records were
captured into `/tmp`; the machine bridge reported `ready`, and machine-fit
reported a `qualified` `intel-full` posture. Profile endpoint rendering for
`agent-federation` worked.

The live autonomy and federation checks still reported runtime-loop drift:
`aoa-status --autonomy --json` failed on `route_api_health_failed` and
`route_api_surface_status_invalid`, while `aoa-diagnose --preset
agent-federation --truth-goal deployed` exited
`repairable_under_governance`. That is the correct result: live runtime cutover
is not silently promoted. The next live-loop action is tracked as
`ABYSS-STACK-Q-0009` and must be an explicit operator choice after reviewing
route-api health, closure reporting, federation layer readiness, and diagnostic
handoff posture.

## Stop-Lines

- do not start, stop, restart, or enable services from the source closeout
- do not widen host exposure while turning a seam live
- do not treat source/deployed parity as live service health
- do not promote federation, RPG, diagnostic, memo, eval, playbook, KAG, or ToS
  seams into runtime authority without owner-boundary review
- do not hide runtime drift by rewriting roadmap language
