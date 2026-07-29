# aoa-course-connector-mcp

Filtered authenticated OS read access over the owner course MCP dispatcher.
It publishes nine read-only tools and excludes `connected_run` plus all
live/network, profile-plan, browser, refresh, and fixture-execution routes.
The adapter verifies the owner tool identity and the current invocation's
read/no-network attestation without confusing preserved historical receipts or
an unexecuted future plan with effects of the current read.

HTTP: port `5436`, scope `mcp:aoa-course-connector:read`, credential
`aoa-course-connector-mcp-read-bearer-token`.
