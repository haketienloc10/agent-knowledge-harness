# MCP Error Transport Contract

All Python MCP services in this repository target MCP Python SDK `2.1.1` until an explicit compatibility upgrade is reviewed.

Affected services:

- `knowledge-template/mcp/knowledge`
- `work-item-template/mcp/work_item`
- `workspace-template/mcp/qiqi_delegate`

## Public failure categories

### 1. Normal control-flow result

Use a normal successful tool result when the caller is expected to branch on the condition as ordinary orchestration flow.

Example: a missing Work Item during lookup may return `found=false` with a structured error object so QiQi can decide whether to create it.

Do not mark normal control flow as a failed MCP tool call merely to attach an error string.

### 2. Anticipated, model-actionable tool failure

Use `mcp.server.mcpserver.exceptions.ToolError` when the tool cannot complete but the failure is expected and the caller can act on it.

The model-visible message should use the stable shape:

```text
code=<stable_code>; <detail>; action=<exact recovery>
```

Every anticipated `ToolError` must include an explicit `action=` recovery instruction; generic conflict/validation fallbacks are not exempt.

`ToolError` is required because MCP SDK 2.1.1 returns it as `is_error=true` while preserving its message in tool content. Plain `ValueError` and `RuntimeError` raised from a tool body are treated as unexpected crashes and are masked by the SDK.

Examples include revision conflicts, missing artifact/section targets, invalid repository/route selection, stale Herdr integration, active delegation conflicts, and native result-capture failures with a preserved resume key.

### 3. Unexpected internal fault

Do not convert arbitrary programming defects or unknown internal exceptions into model-actionable failures.

Unexpected exception types must remain SDK-masked so callers receive the generic tool execution error while server logs retain the traceback. This avoids leaking arbitrary implementation details, tracebacks, paths, or secrets.

## Information-boundary rules

Model-visible actionable errors must not expose physical filesystem paths or other operator-only implementation details when a stable semantic identifier or redacted placeholder is sufficient. Shared Knowledge redacts absolute physical paths before constructing `ToolError` messages.

QiQi Delegate must classify errors from trusted execution metadata, not from TaskPacket/user text. When Herdr command diagnostics include the delegated prompt, the prompt is replaced with a fixed `<task-packet>` placeholder before the public error classifier sees the message.

## Service-specific policy

### Shared Knowledge

Domain validation/conflict/not-found conditions that already carry explicit recovery semantics are raised as `ToolError`. Unknown store/internal failures remain unexpected failures. Physical store/document paths are redacted from model-visible actionable error detail.

### Work Item

Existing structured normal-control-flow results remain structured results. Raised artifact/history/revision/validation failures that are recoverable use `ToolError`. Unknown store/internal failures remain unexpected failures.

### QiQi Delegate

The execution boundary converts the implementation's anticipated `ValueError`/`RuntimeError` preflight and runtime failures into classified `ToolError` messages. Other exception types remain unexpected and SDK-masked.

The classification must not invent lifecycle state, native session identity, or agent response. If the implementation has already persisted native session ownership before a later capture failure, the existing exact resume key may be included in the actionable error.

TaskPacket content must never select the public error code. Diagnostic command rendering and Herdr detail returned to the classifier use a redacted task-packet placeholder.

## Dependency, migration, and regression policy

Each MCP project pins:

```toml
mcp==2.1.1
```

Tests assert the effective installed version and exercise externally visible behavior through the SDK in-memory `Client.call_tool()` boundary where applicable. Dependency-bearing QiQi Delegate tests run inside the `mcp/qiqi_delegate` uv project environment rather than the system Python environment.

Changes to managed workspace MCP files must also advance the workspace migration sequence so an existing workspace can receive the same contract as a fresh template checkout.

An MCP SDK upgrade is explicit compatibility work. Update the pin only together with public-boundary regression verification for all three services.
