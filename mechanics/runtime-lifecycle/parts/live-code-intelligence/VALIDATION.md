# LIVE code-intelligence validation

Run from the source checkout root. On managed hosts, launch through the host's
resource route and use a reserved scratch `TMPDIR`. These source tests do not
install a provider, admit an artifact, activate services, or prove live health.

## Focused source contract

```bash
python -m unittest discover -s mechanics/runtime-lifecycle/parts/live-code-intelligence/tests -v
```

The suite covers bootstrap lifecycle and state recovery, machine-gate schemas,
authenticated LSP boundaries, exact input capture, drift/size/path rejection,
sealed descriptor staging and failure cleanup. It uses test-only trust fixtures,
not host keys or registry admission. Sealed staging requires Linux anonymous-file
sealing; unavailable platform support fails closed rather than widening input
mounts.

## Repository integration

Use the root [validation route](../../../../VALIDATION.md) for the `source-fast`
lane and default `tests` lane. The part is listed in
`docs/testing/test_inventory.json` and collected by the existing mechanic-local
test route; no new command lane or validator bypass is introduced.

## Real-provider boundary

An external SCIP/LSP run needs fresh exact MACHINE admission and installation
identity, complete captured source/configuration/resolver inputs, bounded host
resource/storage routes and an isolated launch. Keep native output and KAG
normalization evidence distinct. A successful canary is not a signed session
gate, deployed lifecycle, EVALS verdict or Goal acceptance.
