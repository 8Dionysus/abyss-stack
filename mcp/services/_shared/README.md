# Shared MCP package sources

`http_auth.py` is the canonical bearer-auth implementation for the optional
loopback Streamable HTTP transport. Standalone MCP packages vendor the helper
as `src/<package>/_http_auth.py` so installed package entrypoints do not depend
on a monorepo-only import path.

Regenerate after changing the canonical helper:

```bash
python mcp/services/_shared/build_http_auth_vendors.py
```

Validate without writing:

```bash
python mcp/services/_shared/build_http_auth_vendors.py --check
```

The helper never owns MCP tools, resources, prompts, or sibling data. It owns
only the common transport parse, loopback guard, credential load, and static
bearer verification primitive. Real credentials remain outside git under the
deployed stack `Secrets/` tree.

`codex_http_client.sh` is the matching client-side launcher for hosts that use
the authenticated shared owners. It validates the deployed credential, places
the bearer only in the launched Codex process environment, and then execs the
currently installed Codex binary. It does not replace that binary, persist the
bearer in shell configuration, or merge MCP owner boundaries.
