# VIA_NEGATIVA_CHECKLIST

This checklist is for `abyss-stack` as the runtime substrate and deployment
body.

## Keep intact

- explicit degradation and repair-safe closeout surfaces
- clear distinction between source checkout, deployed root, and runtime state
- reviewable operator-visible receipts

## Merge, move, suppress, quarantine, deprecate, or remove when found

- hidden auto-repair loops
- runtime docs that duplicate product-edge repo guidance
- obsolete scripts or units kept alive without operator reason

## Questions before adding anything new

1. Does this repair path have a visible stop rule and receipt?
2. Is this runtime guidance better owned by the product repo?
3. Can this obsolete path be archived or removed without breaking recovery?

## Safe exceptions

- a bounded migration shim with short lifetime
- runtime-specific docs that cannot live anywhere else cleanly

## Exit condition

- The runtime body should be explicit under stress, not haunted by shortcuts.
