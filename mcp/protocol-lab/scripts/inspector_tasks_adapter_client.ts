import { pathToFileURL } from "node:url";
import path from "node:path";

async function main(): Promise<void> {
  const inspectorRoot = process.env.ABYSS_INSPECTOR_ROOT;
  const endpoint = process.env.ABYSS_TASKS_ENDPOINT;
  const bearer = process.env.ABYSS_TASKS_BEARER;
  if (!inspectorRoot || !endpoint || !bearer) {
    throw new Error("Inspector root, endpoint, and bearer environment are required");
  }

  const load = async (relative: string) =>
    import(pathToFileURL(path.join(inspectorRoot, relative)).href);
  const { InspectorClient } = await load("core/mcp/inspectorClient.ts");
  const { createTransportNode } = await load("core/mcp/node/transport.ts");
  const { eraToVersionNegotiation } = await load("core/mcp/types.ts");

  const client = new InspectorClient(
  { type: "streamable-http", url: endpoint },
  {
    environment: { transport: createTransportNode },
    versionNegotiation: eraToVersionNegotiation("modern"),
    advertisedExtensions: { "io.modelcontextprotocol/tasks": true },
    listChangedNotifications: {
      tools: false,
      resources: false,
      prompts: false,
    },
    serverSettings: {
      headers: [{ key: "Authorization", value: `Bearer ${bearer}` }],
      metadata: [],
      env: [],
      connectionTimeout: 5000,
      requestTimeout: 10000,
      taskTtl: 60000,
      maxFetchRequests: 100,
      roots: [],
      protocolEra: "modern",
      advertisedExtensions: { "io.modelcontextprotocol/tasks": true },
    },
  },
);

  const messages: Array<Record<string, unknown>> = [];
  client.addEventListener("message", (event: { detail: Record<string, unknown> }) => {
    messages.push(event.detail);
  });

  try {
  await client.connect();
  if (client.getProtocolEra() !== "modern") {
    throw new Error("Inspector did not retain the modern protocol era");
  }
  if (!client.isTasksExtensionNegotiated()) {
    throw new Error("Inspector did not negotiate the Tasks extension");
  }
  const listed = await client.listTools();
  const tool = listed.tools.find(
    (item: { name: string }) => item.name === "diagnostic_snapshot",
  );
  if (!tool) throw new Error("owner diagnostic tool was not discovered");

  messages.length = 0;
  const invocation = await client.callToolStream(tool, { scope: "deployed" });
  const structured = invocation.result?.structuredContent as
    | Record<string, unknown>
    | undefined;
  if (
    structured?.authority !== "diagnostic_session_v1" ||
    structured?.owner !== "abyss-stack" ||
    structured?.ownerRerunCount !== 0
  ) {
    throw new Error("Inspector did not receive the bounded owner result");
  }

  const requests = messages.filter(
    (item) => item.direction === "request" && "message" in item,
  );
  const methods = requests
    .map((item) => {
      const message = item.message as Record<string, unknown>;
      return typeof message.method === "string" ? message.method : "";
    })
    .filter(Boolean);
  if (!methods.includes("tasks/get")) {
    throw new Error("Inspector did not poll tasks/get");
  }
  if (methods.includes("tasks/list") || methods.includes("tasks/result")) {
    throw new Error("Inspector emitted removed Tasks methods");
  }
  const taskEligibleRequests = requests.filter((item) => {
    const message = item.message as Record<string, unknown>;
    return message.method === "tools/call" || message.method === "tasks/get";
  });
  const extensionOnEveryRequest = taskEligibleRequests.every((item) => {
    const message = item.message as {
      params?: {
        _meta?: Record<string, unknown>;
      };
    };
    const capabilities = message.params?._meta?.[
      "io.modelcontextprotocol/clientCapabilities"
    ] as { extensions?: Record<string, unknown> } | undefined;
    return capabilities?.extensions?.["io.modelcontextprotocol/tasks"] !== undefined;
  });
  if (!extensionOnEveryRequest) {
    throw new Error("Inspector omitted per-request Tasks capability");
  }

  let unknownTaskRejected = false;
  try {
    await client.getRequestorTask("not-a-real-task");
  } catch {
    unknownTaskRejected = true;
  }
  if (!unknownTaskRejected) throw new Error("unknown task was not rejected");

  const wrongBearer = await fetch(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      Authorization: "Bearer deliberately-wrong",
      "Content-Type": "application/json",
      "MCP-Protocol-Version": "2026-07-28",
      "Mcp-Method": "tools/list",
    },
    body: JSON.stringify({
      jsonrpc: "2.0",
      id: "wrong-bearer",
      method: "tools/list",
      params: {},
    }),
  });
  if (wrongBearer.status !== 401) {
    throw new Error(`wrong bearer returned ${wrongBearer.status}, expected 401`);
  }

  process.stdout.write(
    JSON.stringify({
      schema_version: "abyss_inspector_tasks_client_observation_v1",
      inspector_version: "2.1.0",
      protocol_era: client.getProtocolEra(),
      protocol_version: client.getProtocolVersion(),
      tasks_extension_negotiated: client.isTasksExtensionNegotiated(),
      methods,
      removed_methods_absent: true,
      extension_on_every_task_request: true,
      owner_result_received: true,
      owner_tool_error_preserved: invocation.result?.isError === true,
      unknown_task_rejected: true,
      wrong_bearer_http_status: wrongBearer.status,
    }),
  );
  } finally {
    await client.disconnect().catch(() => undefined);
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
