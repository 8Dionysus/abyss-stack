# Shared MCP package sources

`runtime-config.v1.json` is the single declarative identity catalog for all
fifteen packages: MCP SDK major, modern wire revision, transport policy,
contours, ports, authentication identities, and deployment unit templates.
`runtime_config.py` validates it; `build_runtime_config_vendors.py` projects
only the package-local record into each standalone wheel.

`http_auth.py` is the canonical bearer-auth implementation for the optional
loopback Streamable HTTP transport. Standalone MCP packages vendor the helper
as `src/<package>/_http_auth.py` so installed package entrypoints do not depend
on a monorepo-only import path.

Regenerate after changing the canonical helper:

```bash
python mcp/services/_shared/build_http_auth_vendors.py
python mcp/services/_shared/build_modern_runtime_vendors.py
python mcp/services/_shared/build_runtime_config_vendors.py
python mcp/services/_shared/build_mcp_bundle_unit.py
```

Validate without writing:

```bash
python mcp/services/_shared/build_http_auth_vendors.py --check
python mcp/services/_shared/build_modern_runtime_vendors.py --check
python mcp/services/_shared/build_runtime_config_vendors.py --check
python mcp/services/_shared/build_mcp_bundle_unit.py --check
```

The helper never owns MCP tools, resources, prompts, or sibling data. It owns
only the common transport parse, loopback guard, credential load, and static
bearer verification primitive. Callers must select an explicit environment
variable, systemd credential name, scope, and client identity from the catalog
so owner and policy planes do not share an authentication contour. There is no
shared bearer or v1 compatibility default. Real credentials remain outside
git under the deployed stack `Secrets/` tree.

`codex_http_client.sh` is the matching client-side launcher for hosts that use
authenticated loopback owners. It reads the catalog's client-admitted read
contours (using the live admission registry when present and the declarative
client list otherwise), then checks their units and loopback listeners before
an MCP-consuming run. A missing member requests the bounded modern admission
recovery oneshot without waiting and then starts Codex immediately. MCP
degradation is visible but cannot turn the interactive client into a lifecycle
lock. Metadata-only Codex commands do not request runtime recovery, and
`AOA_MCP_READINESS_SKIP=1` remains an explicit diagnostic escape hatch.
The launcher loads only the read credentials selected by that projection,
places each bearer only in its named variable in the launched Codex process
environment, and then execs the installed Codex binary. It does not replace
that binary, persist bearer values in shell configuration, merge MCP
owner/contour boundaries, or imply that a shadow contour is admitted. The
launcher takes its feature flag and recovery unit from the same catalog; no
second list of ports, units, or credential names is maintained in the shell
route.

`AOA_CODEX_CLIENT_MODE=desktop` reuses the same credential and readiness
boundary for ChatGPT/Codex Desktop, but execs the selected desktop executable
without adding Codex CLI arguments. The user-unit installer binds that mode to
a managed `~/.local/bin/chatgpt` wrapper and a user-scoped copy of the official
desktop entry. The entry stores only paths and mode selection; bearer values
exist only in the launched Desktop process environment. The ordinary Codex
mode remains the default and still adds the catalog-owned MCP feature flag.
