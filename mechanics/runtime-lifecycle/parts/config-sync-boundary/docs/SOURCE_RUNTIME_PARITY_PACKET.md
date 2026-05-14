# Source Runtime Parity Packet

## Role

This packet owns the machine/runtime link for source-authored stack changes. It
proves that the source checkout can project into a runtime `Configs` mirror
without treating live private state as source truth.

Use it after a source topology, mechanics, script, config-template, deployment,
or route-card change that must be visible to the deployed runtime mirror.

## Packet Gates

Run the gates in this order:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py

tmp_root="$(mktemp -d /tmp/abyss-stack-parity.XXXXXX)"
AOA_STACK_ROOT="${tmp_root}/runtime" \
AOA_CONFIGS_ROOT="${tmp_root}/runtime/Configs" \
  scripts/aoa-install-layout
AOA_STACK_ROOT="${tmp_root}/runtime" \
AOA_CONFIGS_ROOT="${tmp_root}/runtime/Configs" \
  scripts/aoa-sync-configs --delete
python scripts/validate_stack.py \
  --parity-check \
  --deployed-configs-root "${tmp_root}/runtime/Configs"

AOA_STACK_ROOT=/srv/AbyssOS/abyss-stack \
AOA_CONFIGS_ROOT=/srv/AbyssOS/abyss-stack/Configs \
  scripts/aoa-sync-configs --delete
python scripts/validate_stack.py \
  --parity-check \
  --deployed-configs-root /srv/AbyssOS/abyss-stack/Configs
(
  cd /srv/AbyssOS/abyss-stack/Configs
  python scripts/validate_stack.py
)
```

The synthetic gate proves portability before touching the machine. The live
sync gate updates only repo-managed source surfaces under the deployed
`Configs` mirror, including public quest route metadata required for deployed
Configs self-validation. It does not bootstrap secrets, start services, enable
systemd units, delete runtime logs, or copy `Secrets/`, `Logs/`, `Models/`,
live `stack.env`, databases, model files, or private captures into git.

## 2026-05-13 Verdict

The packet was run after the residual quest packet closeout. Source validation,
nested AGENTS validation, synthetic projection parity, live deployed
`/srv/AbyssOS/abyss-stack/Configs` parity, and runtime Configs mirror validation
all passed after an explicit `aoa-sync-configs --delete` to the deployed
Configs mirror.

This closes the machine/runtime parity block for repo-managed source surfaces.
It does not claim live service health; that belongs to the cutover packet and
runtime status checks.

## Stop-Lines

- do not edit `/srv/AbyssOS/abyss-stack/Configs` by hand
- do not use parity success as a service-health claim
- do not sync private runtime state back into source
- do not use `--delete` outside repo-managed `Configs` projection routes
- do not start, stop, or restart services from this packet
