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
- normative host posture and public-safe/private host-facts contracts
- runtime benchmark policies, schemas, normalized manifests, and raw runtime evidence
- runtime-facing return policy, context rebuild posture, and return-event logging

## Belongs elsewhere

- AoA ecosystem-level meaning in `Agents-of-Abyss`
- ToS knowledge architecture meaning in `Tree-of-Sophia`
- reusable techniques in `aoa-techniques`
- bounded execution workflows in `aoa-skills`
- proof surfaces in `aoa-evals`
- portable verdict logic for runtime benchmark meaning in `aoa-evals`
- routing truth in `aoa-routing`
- memory objects and recall contracts in `aoa-memo`
- role contracts in `aoa-agents`
- scenario compositions in `aoa-playbooks`
- derived knowledge substrate meaning in `aoa-kag`
- authored reasons, scenario triggers, and semantic anchor meaning from sibling AoA repositories

## Anti-drift rule

When a new file or subsystem is proposed, ask:

1. Is this runtime or authored meaning?
2. Is this deployment glue or a source-of-truth layer?
3. Would placing it here duplicate the authority of a sibling AoA repository?

If the answer points to authored meaning or duplicated authority, it does not belong here.

Runtime benchmark evidence may live here; proof wording about what that evidence means does not.
Public-safe host-facts contracts may live here; private captures belong in runtime logs, not git history.
