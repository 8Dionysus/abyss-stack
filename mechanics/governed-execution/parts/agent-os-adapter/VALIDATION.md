# Validation

Run:

```bash
AOA_SDK_SOURCE_ROOT=/path/to/aoa-sdk \
/path/to/installed-sdk-venv/bin/python \
  -m pytest -q mechanics/governed-execution/parts/agent-os-adapter/tests
python -m py_compile mechanics/governed-execution/parts/agent-os-adapter/aoa_agent_os_runtime.py
python scripts/validate_stack.py
python scripts/validate_decision_records.py
python scripts/validate_nested_agents.py
```

The focused suite uses a disposable Git repository, the real governed runner,
typed A2A and owner degradation artifacts, injected safe
gate/advisory/proposal and review-packet-trace providers, and subprocess
restores over the public bridge executable. The deterministic suite never calls
the live advisory endpoint; dedicated live receipts remain separate evidence.
The subprocess proof supplies a deliberately spoofed
`PYTHONPATH`; the explicit interpreter and `-I` must still select the packaged
SDK. Each golden success path starts with the installed public compiler v3
chain and reaches the bridge without post-compilation plan mutation. A release
gate must repeat the suite from a clean environment against the packaged
`aoa-sdk`, not only an SDK source checkout.

The C5 paired case performs the real governed mutation through both approvals,
keeps eval and memory refs out of the runtime outcome, composes a complete
external-owner chain in the installed SDK, and closes the durable runtime with
only the exact final closeout ref crossing the bridge.

The A2A paired cases prove successful and incomplete reviewed returns without
calling the governed mutation backend. The degradation case proves partial
progress, durable pause, restore in a new subprocess/Runner from the exact
`SessionHandle`, duplicate-safe resume, external eval/memo/checkpoint
composition, and final closeout.
