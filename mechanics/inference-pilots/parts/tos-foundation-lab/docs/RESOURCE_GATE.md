# Resource and Candidate Gate

## Current host-independent law

Run this gate immediately before a material execution, even when an earlier
machine-fit report exists.

Check:

- free bytes and pressure state on `/srv`;
- available RAM, zram/swap use, load, and current AI/container services;
- current `abyss-machine cooling status` episode, thresholds, distribution,
  and whether owner telemetry is missing;
- required CPU/GPU/NPU/OpenVINO/Vulkan capabilities;
- exact software/runtime/model availability and revision;
- candidate license and rights compatibility;
- expected download, installed size, cache growth, output size, and timeout;
- output, cache, runtime, and temporary paths;
- cleanup/retention decision and rollback/stop procedure.

Missing telemetry is a warning or a block according to the experiment spec; it
is never treated as a cool machine.

## Sequential admission

```text
research candidate
  -> verify license and intended use
    -> storage preflight
      -> install/download one candidate
        -> checksum and inventory
          -> bounded run
            -> retention/rejection decision
              -> only then consider another candidate
```

## Host-owned thermal admission

The committed suite does not invent an independent temperature cutoff. It
asks `abyss-machine resource plan` for the declared experiment class/kind and
records `abyss-machine cooling status` in the preflight receipt. On this thin
laptop the current owner contract treats stable 100--105 C as monitored active
range, above 105 C as watch/routing territory, 106 C as hot, and 109 C as
critical/emergency territory. Those numbers remain host-owned configuration,
not constants copied into the experiment suite.

A watch-band observation is retained as a warning and routing signal; it does
not independently veto operator-controlled work when the current owner plan
allows it. Missing required owner telemetry, owner denial, or the current
owner critical band blocks a new run. Existing work is not killed or
re-affinitized by this laboratory.

The non-thermal committed defaults remain at least 20 GiB free on `/srv`, at
least 8 GiB available RAM, and load below 8. Host storage and resource owners
may impose stricter pressure denial. An operator must not bypass that denial
merely because raw free bytes look sufficient.

## No-download lane

Existing verified runtimes and models are preferred for the first wave. A
challenger that is absent remains `requires-setup` until its exact license,
size, checksum route, and retention plan are approved. Shortlist membership is
not download authorization.

When setup is complete, readiness is demonstrated by
`runtime-manifest.schema.json`: the manifest must live inside the exact
versioned runtime root, close over every file and symlink in that tree, expose
only owner-contained commands, contain no secret-bearing environment fields,
and name the exact operator-confirmed removal target. The preflight verifies
that manifest again immediately before preparing a run.
