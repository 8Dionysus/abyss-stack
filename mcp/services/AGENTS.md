# AGENTS.md

## Applies to

This card applies to `mcp/services/` and every MCP service package below it.

## Role

`mcp/services/` is the service-package district for stack-owned Model Context
Protocol servers. It keeps runnable MCP access planes below one route instead
of leaving service packages directly in the root-adjacent `mcp/` district.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; `mcp/services/README.md` and the service-local `AGENTS.md` are semantic routes when needed, and entering this subtree does not require an unconditional inventory.
## Boundaries

Service packages may own MCP server code, service-local docs, tests, prompts,
resources, tools, and smoke helpers. Source authority stays with the owner layer
named by the service-local route card.

## Validation

The runnable package map lives in `mcp/services/README.md`. For one package,
use its service-local `VALIDATION.md` route; do not inherit or run unrelated
package matrices. For a district-wide change, use the named `mcp-services`
lane in the on-demand validation map.

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

When a service path, local route card, or root district route changes, alsouse the on-demand validation route in `VALIDATION.md`.


## Closeout

Name the service package, the MCP surface that changed, and whether the change
only moved access-plane topology or also changed resources, tools, prompts, or
runtime exposure.
