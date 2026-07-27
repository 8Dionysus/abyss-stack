# aoa-xda-connector-mcp

Authenticated read-only access to already-built local XDA connector packets.
It preserves owner evidence fields and refuses to invent the documented
`query-hybrid` route while the owner CLI has no such command.

HTTP uses port `5438`, scope `mcp:aoa-xda-connector:read`, and the
`aoa-xda-connector-mcp-read-bearer-token` credential.
