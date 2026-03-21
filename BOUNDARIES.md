# BOUNDARIES

This file names what belongs in `abyss-stack` and what must stay elsewhere.

## Belongs here

- compose modules
- runtime profiles
- systemd user units
- container and service topology
- storage and mount contracts
- localhost and internal-only network posture
- secrets handling rules for infrastructure
- backup, restore, smoke, and incident procedures
- infra helper services and adapters
- platform-aware path contracts for Fedora-first deployment and Windows-usable workflows

## Belongs elsewhere

- AoA ecosystem-level meaning in `Agents-of-Abyss`
- ToS knowledge architecture meaning in `Tree-of-Sophia`
- reusable techniques in `aoa-techniques`
- bounded execution workflows in `aoa-skills`
- proof surfaces in `aoa-evals`
- routing truth in `aoa-routing`
- memory objects and recall contracts in `aoa-memo`
- role contracts in `aoa-agents`
- scenario compositions in `aoa-playbooks`
- derived knowledge substrate meaning in `aoa-kag`

## Anti-drift rule

When a new file or subsystem is proposed, ask:

1. Is this runtime or authored meaning?
2. Is this deployment glue or a source-of-truth layer?
3. Would placing it here duplicate the authority of a sibling AoA repository?

If the answer points to authored meaning or duplicated authority, it does not belong here.
