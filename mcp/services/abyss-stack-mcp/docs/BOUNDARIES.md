# Boundaries

## Owns

- stack runtime topology observations;
- source/package/deploy/process/endpoint/consumer linkage;
- stack-local canary and rollback evidence refs;
- compact runtime discovery and selected inspection;
- non-executing runtime plan candidates.

## Does not own

- sibling capability or payload meaning;
- `aoa-sdk` registry or activation authority;
- `aoa-evals` proof verdicts;
- durable memory acceptance;
- source or owner acceptance;
- external connector policy;
- runtime execution approval.

The package may report explicit evidence issued by the named acceptance owner
and bind it to the accepted source revision and package digest. It cannot infer
or manufacture owner acceptance from process state, a model response, or a
canary.

Likewise, it may report a proof-owner verdict and its exact proved target, but
cannot compute, reinterpret, or self-issue the `aoa-evals` proof.

Direct owner adapters remain direct. This service is not a semantic proxy,
universal bus, workflow engine, or authority merger.
