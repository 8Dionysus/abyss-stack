# On-demand validation routes

This is the human route map for exact validation procedure in `abyss-stack`. Inherited `AGENTS.md` cards retain semantic scope, ownership, risk, lane IDs, and stop-lines; they route here only after the touched surface is known.

Machine-executed reusable lanes remain authoritative in `docs/validation/validation_lanes.json`; use the named lane where one applies. Focused commands below preserve local procedure and warnings without making README or AGENTS inherited context executable.

This is on-demand human procedure only; it does not prove deployed runtime health, external CI/review/merge, artifact admission, sibling-owner acceptance, or Goal completion unless those separate boundaries are explicitly exercised and evidenced.

Each procedure below preserves the original command order and exact command body. Read the source card for its unique warnings and stop-lines before execution.

## Shared repository checks

These repository-wide checks have one owner in this route. Surface-specific procedures link here when they need the same check.

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python scripts/validate_decision_records.py
python scripts/generate_decision_indexes.py --check
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python scripts/validate_local_stats_port.py
systemd-analyze --user verify systemd/user/podman-compose-abyss.service
systemd-analyze --user verify systemd/user/*.service systemd/user/*.timer systemd/user/*.path
systemd-analyze verify systemd/system/*.service systemd/system/*.timer
bash -n scripts/aoa-install-systemd
python -m pytest mcp/services/aoa-memo-mcp/tests -q
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mechanics/agon-runtime/parts/runtime-kernels/tests
python mechanics/agon-runtime/parts/runtime-kernels/build_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/build_mechanical_trial_run_registry.py --check
python -m pytest mechanics/experience-runtime/legacy/artifacts/tests
python -m pytest mechanics/inference-pilots/parts/tos-foundation-lab/tests -q
scripts/aoa-check-layout --ignore-secrets
```

## Shared MCP vendor projection checks

These four checks own the generated vendor projections for the shared MCP
package sources. The `_shared` README retains the regeneration commands and
routes validation here; package-specific MCP procedures link to this section
instead of repeating the projection checks.

```bash
python mcp/services/_shared/build_http_auth_vendors.py --check
python mcp/services/_shared/build_modern_runtime_vendors.py --check
python mcp/services/_shared/build_runtime_config_vendors.py --check
python mcp/services/_shared/build_mcp_bundle_unit.py --check
```

Reusable composed gates remain owned by the validated [validation lane manifest](docs/validation/validation_lanes.json); route by exact lane key (source-fast, tests, or mcp-services) through its runner.

## Repository-wide route

- Source and topology: `source-fast` lane.
- Generated projections: `generated` lane.
- Default deterministic tests: `tests` lane.
- MCP package checks: `mcp-services` lane.
- Full release surface: `release` lane through `scripts/release_check.py`.
- Live parity and deployed runtime checks remain explicit, opt-in, and operator-owned.

## `.agents/AGENTS.md`

### Verify

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `.agents/skills/AGENTS.md`

### Validate

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `AGENTS.md`

### Root source-fast and focused topology checks

Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key. Run the validated tests lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### If `stats/` or its service-selection derivation changes, also run:

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### If the diagnostic spine changes, also run:

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `compose/AGENTS.md`

### Verify

```bash
scripts/aoa-profile-modules --profile substrate --paths
scripts/aoa-profile-endpoints --profile substrate
scripts/aoa-render-services --profile substrate
scripts/aoa-render-config --profile substrate >/dev/null
scripts/aoa-profile-modules --profile workflows --paths
scripts/aoa-profile-endpoints --profile workflows
scripts/aoa-render-config --profile workflows >/dev/null
scripts/aoa-profile-modules --profile local-worker --paths
scripts/aoa-profile-endpoints --profile local-worker
scripts/aoa-render-config --profile local-worker >/dev/null
scripts/aoa-profile-modules --profile intel-worker --paths
scripts/aoa-profile-endpoints --profile intel-worker
scripts/aoa-render-config --profile intel-worker >/dev/null
scripts/aoa-profile-modules --profile fallback-gateway --paths
scripts/aoa-profile-endpoints --profile fallback-gateway
scripts/aoa-render-config --profile fallback-gateway >/dev/null
scripts/aoa-preset-profiles --preset agent-full --paths
scripts/aoa-profile-modules --preset agent-full --paths
scripts/aoa-preset-profiles --preset intel-full --paths
scripts/aoa-profile-modules --preset intel-full --paths
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `config-templates/AGENTS.md`

### Bootstrap route

```bash
scripts/aoa-bootstrap-configs
```

### Verify

```bash
export AOA_STACK_ROOT=/tmp/abyss-stack-test
export AOA_CONFIGS_ROOT=/tmp/abyss-stack-test/Configs
scripts/aoa-install-layout
scripts/aoa-bootstrap-configs --force
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `docs/AGENTS.md`

### Validate

```bash
python -m pytest tests/test_roadmap_parity.py tests/test_decision_records.py tests/test_source_topology_validator_modules.py tests/test_validation_topology.py tests/test_script_topology.py tests/test_test_topology.py
```

Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `docs/decisions/AGENTS.md`

### Validation

```bash
python -m pytest tests/test_decision_records.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Validation (procedure 2)

```bash
python -m pytest tests/test_roadmap_parity.py
```

## `docs/testing/AGENTS.md`

### Validate

```bash
python -m pytest -q tests/test_test_topology.py
```

Run the validated tests lane (docs/validation/validation_lanes.json) by its exact manifest key.

## `docs/validation/AGENTS.md`

### Validate

```bash
python -m pytest -q tests/test_validation_command_authority.py tests/test_validation_topology.py tests/test_script_topology.py
```

Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key.

## `env/AGENTS.md`

### Verify

```bash
scripts/aoa-first-run --strict
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/AGENTS.md`

### Validation

```bash
python -m pytest mcp/protocol-lab/tests -q
```

See the nearest owner validation route (mcp/protocol-lab/VALIDATION.md) for this procedure.

### Validation (procedure 2)

Run the validated mcp-services lane (docs/validation/validation_lanes.json) by its exact manifest key.

### Validation (procedure 3)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/protocol-lab/AGENTS.md`

### Validation

See the nearest owner validation route (mcp/protocol-lab/VALIDATION.md) for this procedure.

## `mcp/services/AGENTS.md`

### Validation

Run the validated mcp-services lane (docs/validation/validation_lanes.json) by its exact manifest key.

### Validation (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/abyss-machine-mcp/AGENTS.md`

### Run

```bash
python mcp/services/abyss-machine-mcp/scripts/abyss_machine_mcp_server.py
```

### Installed server entry point

```bash
abyss-machine-mcp-server
```

### Smoke

```bash
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli brief
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli evidence-map
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli maps --axis by-freshness --query semantic --limit 8
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli context-packet --axis by-eval-packet --reader-profile proof-context --limit 4
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli surface rag-latest
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli surfaces
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli surface memory-pressure
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli surface artifact-trust-gate --artifact-class public_source_seed --consumer-intent agent
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli route --intent "start bounded local AI work" --class heavy --kind ai
PYTHONPATH=mcp/services/abyss-machine-mcp/src python -m abyss_machine_mcp.cli read-resource abyss-machine://brief
```

### Verify

```bash
python mcp/services/abyss-machine-mcp/scripts/validate_machine_mcp.py
python -m pytest mcp/services/abyss-machine-mcp/tests -q
python mcp/services/abyss-machine-mcp/scripts/release_check.py
```

### Verify (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/abyss-stack-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/abyss-stack-mcp/scripts/generate_stack_mcp_contracts.py --check
python mcp/services/abyss-stack-mcp/scripts/validate_stack_mcp.py
python -m pytest mcp/services/abyss-stack-mcp/tests -q
```

See [Shared MCP vendor projection checks](VALIDATION.md#shared-mcp-vendor-projection-checks) for the shared projection checks.

## `mcp/services/aoa-4pda-connector-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/aoa-4pda-connector-mcp/scripts/validate_4pda_connector_mcp.py
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q
```

### Validation (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Validation (procedure 3)

```bash
AOA_4PDA_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-4pda-connector \
python -m pytest mcp/services/aoa-4pda-connector-mcp/tests -q

PYTHONPATH=mcp/services/aoa-4pda-connector-mcp/src \
AOA_4PDA_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-4pda-connector \
python -m aoa_4pda_connector_mcp.cli answer \
  "Xiaomi 13T recovery.img fastboot TWRP" \
  --run 20260621T194521Z__crawl \
  --limit 5
```

## `mcp/services/aoa-course-connector-mcp/AGENTS.md`

### On-demand validation procedure

```bash
python mcp/services/aoa-course-connector-mcp/scripts/validate_course_connector_mcp.py
python -m pytest mcp/services/aoa-course-connector-mcp/tests -q
```

## `mcp/services/aoa-decisions-mcp/AGENTS.md`

### Run

```bash
python mcp/services/aoa-decisions-mcp/scripts/aoa_decisions_mcp_server.py
```

### Run (procedure 2)

```bash
AOA_DECISIONS_MCP_CONTOUR=internal_effect \
  python mcp/services/aoa-decisions-mcp/scripts/aoa_decisions_mcp_server.py
```

### Run (procedure 3)

```bash
PYTHONPATH=mcp/services/aoa-decisions-mcp/src \
  python -m aoa_decisions_mcp.cli refresh
```

### Installed server entry point

```bash
aoa-decisions-mcp-server
```

### Smoke

```bash
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli status
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli summary
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli search "decision graph"
PYTHONPATH=mcp/services/aoa-decisions-mcp/src python -m aoa_decisions_mcp.cli packet --query "decision graph"
```

### Verify

```bash
python mcp/services/aoa-decisions-mcp/scripts/validate_decisions_mcp.py
python -m pytest mcp/services/aoa-decisions-mcp/tests -q
python mcp/services/aoa-decisions-mcp/scripts/release_check.py
```

### Verify (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/aoa-discord-connector-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/aoa-discord-connector-mcp/scripts/validate_discord_connector_mcp.py
python -m pytest mcp/services/aoa-discord-connector-mcp/tests -q
```

### Validation (procedure 2)

Run the validated mcp-services lane (docs/validation/validation_lanes.json) by its exact manifest key. Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Local Smoke

```bash
PYTHONPATH=mcp/services/aoa-discord-connector-mcp/src \
AOA_DISCORD_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-discord-connector \
python -m aoa_discord_connector_mcp.cli source-route
```

## `mcp/services/aoa-evals-mcp/AGENTS.md`

### Shared workspace launcher

```bash
/srv/AbyssOS/.codex/bin/aoa-evals-mcp-server.py
```

### Source-local server contours

```bash
python mcp/services/aoa-evals-mcp/scripts/aoa_evals_mcp_server.py
AOA_MCP_POLICY_FAMILY=candidate python mcp/services/aoa-evals-mcp/scripts/aoa_evals_mcp_server.py
```

### Installed server entry point

```bash
aoa-evals-mcp-server
```

### Smoke

```bash
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli catalog
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli select --proof-question "bounded change verification"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli find-or-propose --proof-question "bounded change verification"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli inspect aoa-bounded-change-quality
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli expand aoa-bounded-change-quality --section-key intent
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-evidence-template aoa-bounded-change-quality
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-status
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli forge-access
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli validate-evidence-candidate --candidate-file /tmp/runtime-evidence-selection.json
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-candidate-exports --limit 5
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli local-ports
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli local-port aoa-memo
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli find-or-propose-local aoa-memo --proof-question "repo-local eval pressure"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli report-skeleton aoa-bounded-change-quality --evidence-ref artifact:example
```

### Verify

```bash
python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py
python -m pytest mcp/services/aoa-evals-mcp/tests -q
python mcp/services/aoa-evals-mcp/scripts/release_check.py
```

## `mcp/services/aoa-kag-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/aoa-kag-mcp/scripts/validate_kag_mcp.py
python -m pytest mcp/services/aoa-kag-mcp/tests -q
```

### Validation (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/aoa-memo-mcp/AGENTS.md`

### Shared workspace launcher

```bash
/srv/AbyssOS/.codex/bin/aoa-memo-mcp-server.py
```

### Source-local server contours

```bash
python mcp/services/aoa-memo-mcp/scripts/aoa_memo_mcp_server.py
AOA_MCP_POLICY_FAMILY=candidate python mcp/services/aoa-memo-mcp/scripts/aoa_memo_mcp_server.py
```

### Installed server entry point

```bash
aoa-memo-mcp-server
```

### Smoke

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli brief --repo Agents-of-Abyss --intent "route memory"
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli validate-candidate path/to/candidate.json
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli validate-port --repo abyss-stack
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli build-port-index --repo abyss-stack --check
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli pending-exports --repo abyss-stack
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli landing-plan --repo abyss-stack --export-ref exports/example.reviewed-intake.json --run-dry-run
```

### Verify

```bash
python mcp/services/aoa-memo-mcp/scripts/release_check.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/aoa-session-memory-mcp/AGENTS.md`

### Run

```bash
python mcp/services/aoa-session-memory-mcp/scripts/aoa_session_memory_mcp_server.py
```

### Run (procedure 2)

```bash
aoa-session-memory-mcp-server
```

### Smoke

```bash
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli status
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli transport-preflight
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-responses --session latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-closeouts --session latest --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-progress-updates --session latest --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli agent-reasoning-windows --session latest --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli task-episodes latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli goal-lifecycles latest --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli answer-neighborhood --session latest --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli trace aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-chain aoa-session-memory-mcp --kind mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-dossier aoa-session-memory-mcp --kind mcp --usage-limit 2 --neighborhood-limit 1 --graph-limit 6 --graph-edge-limit 6
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-audit aoa-session-memory-mcp --kind mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-neighborhood view_image --kind tool --limit 2
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli usage-scenario-audit --seed smoke --sample-size 4
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-audit --profile entity_registry_lookup --seed smoke --sample-size 5 --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-corpus-list
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli live-scenario-corpus-check --case-limit 1
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli search aoa-session-memory --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli search --filter route_signal=tool:view_image --filter doc_type=event --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-inventory --layer skill --limit 10
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli entity-inventory --layer git --limit 10
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli hook-receipts --event-name UserPromptSubmit --only-errors --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli projection-status
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli route-rollup-query exec_command --layer tool --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli direct-event-rollup-query --usage-role result --limit 3
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli route by-mcp aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli brief latest
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli evidence-packet --intent "debug aoa-session-memory-mcp" --anchor aoa-session-memory-mcp
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli freshness-check raw:line:1 --session latest
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-neighborhood aoa-session-memory-mcp --kind mcp --limit 20
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-bridge aoa-session-memory-mcp exec_command --source-kind mcp --target-kind tool --limit 4
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-cooccurrence aoa-session-memory-mcp --kind mcp_service --limit 6
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graphrag-packet aoa-session-memory-mcp --anchor aoa-session-memory-mcp --limit 5
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli graph-quality-audit --limit 4
```

### Verify

```bash
python mcp/services/aoa-session-memory-mcp/scripts/validate_session_memory_mcp.py
python -m pytest mcp/services/aoa-session-memory-mcp/tests -q
python mcp/services/aoa-session-memory-mcp/scripts/release_check.py
```

### Verify (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/aoa-stackoverflow-connector-mcp/AGENTS.md`

### On-demand validation procedure

```bash
python mcp/services/aoa-stackoverflow-connector-mcp/scripts/validate_stackoverflow_connector_mcp.py
python -m pytest mcp/services/aoa-stackoverflow-connector-mcp/tests -q
```

## `mcp/services/aoa-stats-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/aoa-stats-mcp/scripts/validate_stats_mcp.py
python -m pytest mcp/services/aoa-stats-mcp/tests -q
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mcp/services/aoa-telegram-connector-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/aoa-telegram-connector-mcp/scripts/validate_telegram_connector_mcp.py
python -m pytest mcp/services/aoa-telegram-connector-mcp/tests -q
```

### Validation (procedure 2)

Run the validated mcp-services lane (docs/validation/validation_lanes.json) by its exact manifest key. Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Local Smoke

```bash
PYTHONPATH=mcp/services/aoa-telegram-connector-mcp/src \
AOA_TELEGRAM_CONNECTOR_REPO=/srv/AbyssOS/connectors/aoa-telegram-connector \
python -m aoa_telegram_connector_mcp.cli source-route
```

## `mcp/services/aoa-xda-connector-mcp/AGENTS.md`

### On-demand validation procedure

```bash
python mcp/services/aoa-xda-connector-mcp/scripts/validate_xda_connector_mcp.py
python -m pytest mcp/services/aoa-xda-connector-mcp/tests -q
```

## `mcp/services/tos-corpus-mcp/AGENTS.md`

### Validation

```bash
python mcp/services/tos-corpus-mcp/scripts/validate_tos_corpus_mcp.py
python -m pytest mcp/services/tos-corpus-mcp/tests -q
```

### Validation (procedure 2)

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/AGENTS.md`

### Validation

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/agon-runtime/AGENTS.md`

### On-demand validation procedure

```bash
python mechanics/agon-runtime/parts/runtime-kernels/validate_duel_runtime_kernels.py
python mechanics/agon-runtime/parts/runtime-kernels/validate_mechanical_trial_runs.py
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_duel_kernel.py --check
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_trials.py --check
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/agon-runtime/legacy/AGENTS.md`

### On-demand validation procedure

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/config-projection/AGENTS.md`

### On-demand validation procedure

```bash
bash -n scripts/aoa-bootstrap-configs scripts/aoa-sync-configs scripts/aoa-render-config scripts/aoa-render-services
bash -n mechanics/config-projection/parts/bootstrap/aoa_bootstrap_configs.sh mechanics/config-projection/parts/sync/aoa_sync_configs.sh mechanics/config-projection/parts/rendering/aoa_*.sh
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/diagnostic-spine/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/diagnostic-spine/parts/diagnose-wrapper/tests/test_aoa_diagnose.py mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_surface_validator.py -q
bash -n scripts/aoa-doctor scripts/aoa-diagnose
bash -n mechanics/diagnostic-spine/parts/doctor-readiness/aoa_doctor.sh mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.sh
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/experience-runtime/AGENTS.md`

### On-demand validation procedure

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/experience-runtime/legacy/AGENTS.md`

### On-demand validation procedure

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/federation-seams/AGENTS.md`

### On-demand validation procedure

```bash
scripts/aoa-rpg-runtime-projection --generated-only --check
python -m pytest mechanics/federation-seams/parts/rpg-runtime/tests/test_rpg_runtime_projection.py -q
python -m pytest mechanics/federation-seams/parts/sync-wrapper/tests/test_routing_canary.py -q
python -m pytest mechanics/federation-seams/parts/federation-checks/tests/test_route_api_closure_status.py -q
python -m py_compile mechanics/federation-seams/parts/federation-checks/aoa_federated_check.py mechanics/federation-seams/parts/sync-wrapper/aoa_routing_canary.py mechanics/federation-seams/parts/rpg-runtime/aoa_rpg_runtime_projection.py
bash -n scripts/aoa-sync-federation-surfaces mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/federation-seams/parts/memo-seam/AGENTS.md`

### Refresh public-safe memo mirror

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-memo
```

### Inspect memo seam route API

```bash
curl http://127.0.0.1:5402/memo/registry
curl http://127.0.0.1:5402/memo/catalog
curl http://127.0.0.1:5402/memo/object-catalog
curl -X POST http://127.0.0.1:5402/memo/capsule -H 'content-type: application/json' -d '{"family":"doctrine","id":"AOA-M-0002"}'
```

### Emit bounded memo export candidate

```bash
scripts/aoa-export-memo-candidate \
  --runtime-surface checkpoint_export \
  --input-file /tmp/checkpoint-export.json \
  --write
```

### Validation

```bash
bash -n scripts/aoa-sync-federation-surfaces
python -m py_compile mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_runtime_delivery_receipt.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_runtime_erasure.py
python -m pytest -q mechanics/federation-seams/parts/memo-seam/tests/test_active_organ_agent_local_runtime_namespace.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/governed-execution/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/governed-execution/parts/governed-runner/tests mechanics/governed-execution/parts/candidate-exports/tests/test_runtime_eval_evidence_export.py -q
python -m py_compile mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py mechanics/governed-execution/parts/candidate-exports/aoa_export_memo_candidate.py mechanics/governed-execution/parts/candidate-exports/aoa_export_runtime_evidence_selection.py mechanics/governed-execution/parts/candidate-exports/aoa_export_artifact_hook_candidate.py
bash -n scripts/aoa-status
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/governed-execution/parts/ephemeral-worker/AGENTS.md`

### Validation

See the nearest owner validation route (mechanics/governed-execution/parts/ephemeral-worker/VALIDATION.md) for this procedure. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/governed-execution/parts/external-codex-agent/AGENTS.md`

### Validation

See the [external-codex-agent validation route](mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md) for this focused procedure.

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/inference-pilots/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/inference-pilots/parts/local-trials/tests/test_aoa_local_ai_trials.py -q
python -m py_compile mechanics/inference-pilots/parts/llamacpp-pilot/aoa_llamacpp_pilot.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_check.py mechanics/inference-pilots/parts/local-trials/aoa_local_ai_trials.py mechanics/inference-pilots/parts/local-trials/trial_compatibility_bridge.py mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py mechanics/inference-pilots/parts/langgraph-pilot/aoa_langgraph_pilot.py mechanics/inference-pilots/parts/promotion-loop/aoa_runtime_bench_index.py
bash -n scripts/aoa-qwen-bench scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
bash -n mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_bench.sh mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_long_horizon_pilot.sh mechanics/inference-pilots/parts/quiet-bridge-commands/aoa_bounded_autonomy_pilot.sh
python -m py_compile mechanics/inference-pilots/parts/local-trials/compatibility-runners/aoa-local-ai-trials mechanics/inference-pilots/parts/quiet-bridge-commands/runners/aoa-w5-pilot mechanics/inference-pilots/parts/quiet-bridge-commands/runners/aoa-w6-pilot
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/inference-pilots/legacy/AGENTS.md`

### On-demand validation procedure

```bash
scripts/aoa-long-horizon-pilot --help
scripts/aoa-bounded-autonomy-pilot --help
bash -n scripts/aoa-long-horizon-pilot scripts/aoa-bounded-autonomy-pilot
python -m py_compile mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-local-ai-trials mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w5-pilot mechanics/inference-pilots/legacy/trials/artifacts/scripts/aoa-w6-pilot
```

## `mechanics/inference-pilots/parts/tos-foundation-lab/AGENTS.md`

### Validation

```bash
python mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py validate
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/machine-fit/AGENTS.md`

### On-demand validation procedure

```bash
python -m py_compile mechanics/machine-fit/parts/host-facts/aoa_host_facts.py mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py mechanics/machine-fit/parts/platform-adaptations/aoa_platform_adaptation.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/runtime-lifecycle/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/runtime-lifecycle/parts/start-stop/tests/test_aoa_warmup.py -q
python -m pytest mechanics/runtime-lifecycle/parts/status-readouts/tests/test_runtime_hygiene.py -q
bash -n scripts/aoa-install-layout scripts/aoa-check-layout scripts/aoa-first-run scripts/aoa-up scripts/aoa-down scripts/aoa-warmup scripts/aoa-wait scripts/aoa-smoke scripts/aoa-logs scripts/aoa-status scripts/aoa-install-systemd
bash -n mechanics/runtime-lifecycle/parts/first-run-bootstrap/aoa_*.sh mechanics/runtime-lifecycle/parts/start-stop/aoa_*.sh mechanics/runtime-lifecycle/parts/wait-smoke/aoa_*.sh mechanics/runtime-lifecycle/parts/logs-status/aoa_*.sh mechanics/runtime-lifecycle/parts/layout-install/aoa_*.sh mechanics/runtime-lifecycle/parts/user-unit/aoa_*.sh
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/runtime-repair/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/runtime-repair/parts/degradation-receipts/tests/test_degradation_receipts.py mechanics/runtime-repair/parts/repair-safe-closeout/tests/test_repair_safe_closeout_receipts.py mechanics/runtime-repair/parts/a2a-return-dry-run/tests/test_a2a_return_closeout_dry_run.py mechanics/runtime-repair/parts/memo-contradiction-sidecar/tests/test_memo_contradiction_integrity_runner.py
python -m py_compile mechanics/runtime-repair/parts/a2a-return-dry-run/aoa_a2a_return_closeout_dry_run.py mechanics/runtime-repair/parts/memo-contradiction-sidecar/aoa_memo_contradiction_integrity.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `mechanics/runtime-repair/legacy/AGENTS.md`

### On-demand validation procedure

```bash
python -m pytest mechanics/runtime-repair/parts/degradation-receipts/tests/test_degradation_receipts.py mechanics/runtime-repair/parts/repair-safe-closeout/tests/test_repair_safe_closeout_receipts.py
```

## `memo/AGENTS.md`

### Candidate Route

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli create-candidate \
  --repo abyss-stack \
  --evidence-ref mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md \
  --claim "Runtime memory access should route through reviewed local candidates."
```

### Candidate Route (procedure 2)

See the [aoa-memo MCP Smoke route](VALIDATION.md#mcpservicesaoa-memo-mcpagentsmd) for the owner procedure for `validate-candidate`.

### Reviewed Landing Route

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli landing-plan --repo abyss-stack --export-ref exports/path.reviewed-intake.json --run-dry-run
```

The [aoa-memo MCP Smoke route](VALIDATION.md#mcpservicesaoa-memo-mcpagentsmd) owns the `pending-exports` procedure.

### Validation

```bash
AOA_MEMO_ROOT="${AOA_MEMO_ROOT:-/srv/AbyssOS/aoa-memo}"
python "$AOA_MEMO_ROOT/scripts/memory/validate_local_memo_port.py" --path memo
python "$AOA_MEMO_ROOT/scripts/memory/build_local_memo_port_index.py" --path memo --check
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `quests/AGENTS.md`

### Validate

```bash
python quests/scripts/build_quest_examples.py --check
python -m py_compile quests/scripts/quest_surface.py quests/scripts/build_quest_examples.py
python -m pytest tests/test_questbook_surface_contracts.py
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `scripts/AGENTS.md`

### Route-only validation

```bash
python -m py_compile scripts/validate_stack.py mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py mechanics/governed-execution/parts/governed-runner/aoa_governed_run.py mechanics/governed-execution/parts/agent-os-adapter/aoa_agent_os_runtime.py mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py mechanics/machine-fit/parts/host-facts/aoa_host_facts.py mechanics/machine-fit/parts/machine-bridge/aoa_machine_bridge.py mechanics/machine-fit/parts/fit-record/aoa_machine_fit.py mechanics/inference-pilots/parts/qwen-routes/aoa_qwen_run.py
shellcheck scripts/aoa-lib.sh scripts/aoa-diagnose scripts/<touched-script>
shellcheck scripts/aoa-lib.sh mechanics/<package>/parts/<part>/<touched-backend>.sh
bash -n scripts/<touched-script> mechanics/<package>/parts/<part>/<touched-backend>.sh
scripts/aoa-host-facts --mode public
scripts/aoa-machine-bridge --mode public --write /tmp/machine-bridge.public.review.json
scripts/aoa-machine-fit --mode public
```

Run the validated source-fast lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `skills/AGENTS.md`

### Validation

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `stats/AGENTS.md`

### Validation

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `systemd/AGENTS.md`

### Verify

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Unit validation

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `systemd/system/AGENTS.md`

### Privileged install route

```bash
pkexec /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-install-systemd --system-units
```

### Verify

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

## `systemd/user/AGENTS.md`

### Manual user-unit reload and enablement

```bash
systemctl --user daemon-reload
systemctl --user enable --now podman-compose-abyss.service
```

### Durable runtime selection installer

```bash
scripts/aoa-install-systemd --preset intel-full --profile federation --enable-now --restart-now
```

### Link managed user units without starting

```bash
scripts/aoa-install-systemd --all-user-units
```

### User-unit syntax validation

```bash
scripts/aoa-install-systemd
```

See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.

### Explicit enablement test

```bash
scripts/aoa-install-systemd --enable-now
```

## `tests/AGENTS.md`

### Validate

Run the validated tests lane (docs/validation/validation_lanes.json) by its exact manifest key. See [Shared repository checks](VALIDATION.md#shared-repository-checks) for this repository-wide check.
