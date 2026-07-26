# Agent OS Adapter

This part owns the first `abyss-stack` production bridge for the
`aoa-sdk` Agent OS control plane.

The bridge is a local subprocess JSON interface. It persists runtime-owned
session state and delegates the admitted `AOA-P-0011` execution contour to the
existing governed runner. It is not a daemon, listener, route resolver,
playbook author, eval organ, memory organ, or closeout authority.

The Python bridge must be paired with an explicit installed-SDK interpreter
and isolated mode; the executable shebang is an operator convenience, not the
package-binding contract.

The active contract is [CONTRACT](CONTRACT.md), the exact supported profile
and plan-to-runtime mapping is [runtime-profile.v1.json](runtime-profile.v1.json),
and the focused checks are listed in [VALIDATION](VALIDATION.md).
