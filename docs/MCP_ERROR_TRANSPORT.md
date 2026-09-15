# MCP Error Transport Contract

Python MCP services hiện còn trong harness:

- `knowledge-template/mcp/knowledge`
- `workspace-template/mcp/qiqi_delegate`

Filesystem Work Item **không phải MCP service** và không thuộc error-transport contract này.

## Public failure categories

### Normal control flow

Dùng successful structured result khi caller dự kiến branch như orchestration bình thường.

### Anticipated actionable failure

Dùng `mcp.server.mcpserver.exceptions.ToolError` cho failure expected/actionable. Model-visible message dùng stable shape:

```text
code=<stable_code>; <detail>; action=<exact recovery>
```

Không expose physical secret/path detail nếu semantic identifier đủ.

### Unexpected internal fault

Không convert arbitrary programming defect thành model-actionable error. Để SDK mask unexpected exception và giữ traceback ở server logs.

## Shared Knowledge

Validation/conflict/not-found có recovery rõ dùng `ToolError`; unknown store/internal failure giữ unexpected. Redact absolute physical paths.

## QiQi Delegate

Execution boundary classify anticipated preflight/runtime failures từ trusted execution metadata. TaskPacket/user text không được chọn public error code. Result-capture failure có thể trả exact preserved resume key nếu key đã persist trước failure.

## Dependency + regression

MCP SDK upgrade là explicit compatibility work. Update pin cùng public-boundary regression tests cho các MCP service còn tồn tại.
