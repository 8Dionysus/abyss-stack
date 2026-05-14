# Profile Machine-Fit Packet

## Role

This packet closes the source-side profile rollout obligation by tying profile
and preset review to a public-safe machine-fit record. It is a source-checkout
packet, not a live service-health claim and not a copy of sibling-owned layer
meaning.

Use it when `docs/profiles/PROFILES.md`, `docs/profiles/PRESETS.md`, or
`docs/profiles/PROFILE_RECIPES.md` changes in a way that needs current host-fit evidence
before a runtime rollout.

## Packet Surface

The packet is complete when these public-safe checks can run together from the
source checkout:

- `scripts/aoa-host-facts --mode public --write /tmp/<packet>/host-facts.public.json`
- `scripts/aoa-machine-bridge --mode public --write /tmp/<packet>/machine-bridge.public.json`
- `scripts/aoa-platform-adaptation --mode public --write /tmp/<packet>/platform-adaptation.public.json`
- `scripts/aoa-machine-fit --mode public --write /tmp/<packet>/machine-fit.public.json`
- `scripts/aoa-profile-modules --profile substrate --profile curation --paths`
- `scripts/aoa-profile-endpoints --profile substrate --profile curation`
- `scripts/aoa-profile-modules --profile agentic --profile federation --paths`
- `scripts/aoa-profile-endpoints --profile agentic --profile federation`

## 2026-05-13 Verdict

The 2026-05-13 packet produced public-safe host facts, a ready read-only
machine-bridge record, a bounded platform-adaptation note, and a qualified
machine-fit record. The fit record recommended the `intel-full` preset with the
`intel`, `tools`, and `observability` profile set while keeping conservative
llama.cpp runtime settings and explicit overlay recommendations.

That is enough to close the source profile-rollout quest: profile and preset
review now has a bounded machine-fit packet route. It is not enough to claim
live service availability, private host readiness, or sibling-layer acceptance.

## Stop-Lines

- do not commit private captures from `Logs/host-facts/`,
  `Logs/machine-fit/`, `Logs/machine-bridge/`, or
  `Logs/platform-adaptations/`
- do not treat a fit recommendation as a service-health proof
- do not promote profile defaults without rerunning the packet on the target
  machine
- do not copy AoA, ToS, skill, memo, eval, playbook, routing, KAG, or stats
  doctrine into this repository
