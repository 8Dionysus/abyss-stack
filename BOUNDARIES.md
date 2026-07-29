# BOUNDARIES

This file names what belongs in `abyss-stack` and what must stay elsewhere.

## Belongs here

- compose modules
- runtime profiles
- working substrate selection and explicit runtime layers
- systemd user units
- container and service topology
- storage and mount contracts
- localhost and internal-only network posture
- secrets handling rules for infrastructure
- backup, restore, smoke, and incident procedures
- infra helper services and adapters
- runtime-owned MCP access planes and adapters
- local memory ports for runtime candidates, receipts, exports, and local notes
- runtime-owned statistical questions, measurement definitions, and live
  derivations over stack-owned evidence
- platform-aware path contracts for Fedora-first deployment and Windows-usable workflows
- normative host posture and public-safe/private host-facts contracts
- runtime benchmark policies, schemas, normalized manifests, and raw runtime evidence
- platform-adaptation policies and bounded public-safe/private tuning records
- runtime-facing return policy, context rebuild posture, and return-event logging
- canonical agent procedures whose applicability, tool binding, typed output,
  and termination are owned by this runtime

## Belongs elsewhere

- AoA ecosystem-level meaning in `Agents-of-Abyss`
- ToS knowledge architecture meaning in `Tree-of-Sophia`
- reusable techniques in `aoa-techniques`
- shared bounded execution workflows and skill-system doctrine in `aoa-skills`
- proof surfaces in `aoa-evals`
- portable verdict logic for runtime benchmark meaning in `aoa-evals`
- routing truth and the stable routing producer in `aoa-sdk`; the literal
  `aoa-routing` runtime namespace remains a compatibility ABI
- memory objects and recall contracts in `aoa-memo`
- role contracts in `aoa-agents`
- scenario compositions in `aoa-playbooks`
- derived knowledge substrate meaning in `aoa-kag`
- shared measurement grammar and cross-owner statistical composition in
  `aoa-stats`
- authored reasons, scenario triggers, and semantic anchor meaning from sibling AoA repositories

## Anti-drift rule

When a new file or subsystem is proposed, ask:

1. Is this runtime or authored meaning?
2. Is this deployment glue or a source-of-truth layer?
3. Would placing it here duplicate the authority of a sibling AoA repository?

If the answer points to authored meaning or duplicated authority, it does not belong here.

Runtime benchmark evidence may live here; proof wording about what that evidence means does not.
Public-safe host-facts contracts may live here; private captures belong in runtime logs, not git history.
Platform-adaptation records may live here; they should stay bounded to runtime seams, adaptations, and portability notes.
Runtime statistical meaning may live here; shared measurement grammar and
cross-owner conclusions do not.

## Related root surfaces

- `CHARTER.md` authorizes the owner lane.
- `DESIGN.md` describes the intended runtime form.
- `DESIGN.AGENTS.md` describes the intended agent-route form.
- `AGENTS.md` tells agents how to move through those surfaces.
