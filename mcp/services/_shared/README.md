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
bearer verification primitive. Callers may select an explicit environment
variable, systemd credential name, scope, and client identity so owner and
policy planes do not share an authentication contour. The legacy defaults
remain transitional compatibility only. Real credentials remain outside git
under the deployed stack `Secrets/` tree.

`codex_http_client.sh` is the matching client-side launcher for hosts that use
authenticated loopback owners. It validates the compatibility credential and
the owner-distinct Decisions, Memo, Evals, KAG, Session Memory, Stats, Abyss
Machine, staged ToS corpus, 4PDA, Telegram, Discord, Course, StackOverflow, and
XDA read credentials, plus the distinct Memo and Evals candidate credentials.
It places each bearer only in its named variable in the launched Codex process
environment and then execs the installed Codex binary. It does not replace
that binary, persist bearer values in shell configuration, merge MCP
owner/contour boundaries, or imply that the ToS wrapper/canary admission
already exists.
