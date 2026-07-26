# Agent OS Adapter

This part owns the `abyss-stack` production bridge for the `aoa-sdk` Agent OS
control plane.

The bridge is a local subprocess JSON interface. It persists runtime-owned
session state and admits three exact owner-pinned lanes. `AOA-P-0011`
repository mutation delegates to the existing governed runner. `AOA-P-0031`
reviews a typed A2A return without executing a child, and `AOA-P-0032` carries
an owner degradation receipt through durable pause, restore, and resume. It is
not a daemon, listener, route resolver, generic plan interpreter, playbook
author, eval organ, memory organ, or closeout authority.

Compilation-ready profiles retain the selected lane's exact runtime approval
projection. The bridge compares descriptor, profile, and plan instead of
accepting approvals inserted after compilation.

The Python bridge must be paired with an explicit installed-SDK interpreter
and isolated mode; the executable shebang is an operator convenience, not the
package-binding contract.

For C5, cross-owner evidence completeness is validated by the SDK before
dispatch. This runtime owner accepts only the exact final closeout ref and
validates its plan, session, outcome, and owner scope.

The active contract is [CONTRACT](CONTRACT.md), the exact supported profile
and plan-to-runtime mapping is [runtime-profile.v1.json](runtime-profile.v1.json),
and the focused checks are listed in [VALIDATION](VALIDATION.md).
