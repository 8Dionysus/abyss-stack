use anyhow::{anyhow, Result};
use reqwest::header::{HeaderValue, AUTHORIZATION};
use rmcp::{
    model::{
        CallToolRequestParams, CallToolResponse, CallToolResult, ClientCapabilities,
        ClientInfo, GetTaskParams, Implementation, ProtocolVersion, TaskPayload,
    },
    transport::{
        streamable_http_client::StreamableHttpClientTransportConfig,
        StreamableHttpClientTransport,
    },
    ClientLifecycleMode, ClientServiceExt,
};
use serde_json::{json, Value};
use std::collections::HashMap;

#[tokio::main]
async fn main() -> Result<()> {
    let endpoint = std::env::var("ABYSS_TASKS_ENDPOINT")?;
    let bearer = std::env::var("ABYSS_TASKS_BEARER")?;
    let mut headers = HashMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {bearer}"))?,
    );
    let config = StreamableHttpClientTransportConfig::with_uri(endpoint)
        .custom_headers(headers);
    let transport = StreamableHttpClientTransport::from_config(config);
    let client_info = ClientInfo::new(
        ClientCapabilities::builder().enable_tasks().build(),
        Implementation::new("abyss-rmcp-reference-client", "3.1.2"),
    );
    let client = client_info
        .serve_with_lifecycle(
            transport,
            ClientLifecycleMode::Discover {
                preferred_versions: vec![ProtocolVersion::V_2026_07_28],
            },
        )
        .await?;

    let tools = client.list_tools(Default::default()).await?;
    if !tools.tools.iter().any(|tool| tool.name == "diagnostic_snapshot") {
        return Err(anyhow!("owner diagnostic tool was not discovered"));
    }
    let response = client
        .call_tool_once(
            CallToolRequestParams::new("diagnostic_snapshot")
                .with_arguments(rmcp::object!({ "scope": "deployed" })),
        )
        .await?;
    let created = match response {
        CallToolResponse::Task(created) => created,
        other => return Err(anyhow!("expected task result, got {other:?}")),
    };
    let task_id = created.task.task_id.clone();
    let poll_ms = created.task.poll_interval_ms.unwrap_or(100);
    tokio::time::sleep(std::time::Duration::from_millis(poll_ms)).await;
    let detailed = client
        .peer()
        .get_task(GetTaskParams::new(task_id.clone()))
        .await?;
    let (authority, owner, owner_rerun_count, tool_error_preserved) =
        match detailed.task.payload {
            TaskPayload::Completed { result } => {
                let result: CallToolResult = serde_json::from_value(Value::Object(result))?;
                let structured = result
                    .structured_content
                    .ok_or_else(|| anyhow!("owner structured result is absent"))?;
                (
                    structured.get("authority").and_then(Value::as_str).unwrap_or_default().to_owned(),
                    structured.get("owner").and_then(Value::as_str).unwrap_or_default().to_owned(),
                    structured.get("ownerRerunCount").and_then(Value::as_u64).unwrap_or(u64::MAX),
                    result.is_error == Some(true),
                )
            }
            other => return Err(anyhow!("expected completed task, got {other:?}")),
        };
    if authority != "diagnostic_session_v1" || owner != "abyss-stack" || owner_rerun_count != 0 {
        return Err(anyhow!("owner result identity drifted"));
    }
    let unknown_task_rejected = client
        .peer()
        .get_task(GetTaskParams::new("not-a-real-task"))
        .await
        .is_err();
    if !unknown_task_rejected {
        return Err(anyhow!("unknown task was not rejected"));
    }
    client.cancel().await?;

    let output = json!({
        "schema_version": "abyss_rmcp_tasks_client_observation_v1",
        "rmcp_version": "3.1.2",
        "tasks_extension_declared": true,
        "task_created": true,
        "completed_result_received": true,
        "owner_tool_error_preserved": tool_error_preserved,
        "unknown_task_rejected": unknown_task_rejected,
    });
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
