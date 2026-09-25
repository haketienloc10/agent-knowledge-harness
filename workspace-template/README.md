# Workspace template

Workspace template cung cấp QiQi orchestration, repo registry, shared Work Items và `qiqi_delegate`.

```text
AGENTS.md
identity.md
repos.yaml
SYSTEM_MAP.md
work-items/
instructions/
mcp/qiqi_delegate/
scripts/
```

## Unified setup

Sau khi materialize/migrate workspace, chạy installer từ harness checkout:

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace
```

Wizard cho chọn độc lập:

- QiQi coordinator: Claude Code, Codex hoặc cả hai;
- Herdr execution agents: Claude Code, Codex hoặc cả hai;
- default balanced route khi cả hai execution agents được enable.

Installer cài workspace-scoped `$work-item` skill cho coordinator đã chọn, Shared Knowledge skill/MCP cho union của coordinator + execution agents, Herdr integrations cho execution agents, và ghi machine-local preference tại `.qiqi/config.local.json`.

Codex coordinator dùng tracked `.codex/config.toml`. Claude coordinator được materialize bởi `scripts/setup-claude.sh`: `.claude/CLAUDE.md` import canonical `AGENTS.md`, `qiqi_delegate` được đăng ký Claude local-scope, và nested repo child isolation được ghi machine-locally vào từng repo `.claude/settings.local.json`. Workspace template không dùng `.mcp.json` cho `qiqi_delegate`.

## Work Items

`work-items/` là current mutable task resource cấp workspace và là canonical parent-side location:

```text
<workspace>/work-items
```

QiQi/$work-item resolve path này trực tiếp từ active workspace root; parent không cần một env do MCP child export.

Khi `qiqi_delegate` chạy child, launcher tạo directory nếu thiếu và export delegated-runtime alias:

```text
QIQI_WORK_ITEMS_DIR=<workspace>/work-items
```

Alias này chỉ dùng để mount cùng resource vào supported child agents.

QiQi dùng `$work-item` để quản lý lifecycle request → investigation/plan → implementation → verification/review → final report. Dossier không lưu turn history.

## Delegation

QiQi delegate repo-local work qua `delegate_repo_task`. Supported agents nhận shared Work Items directory bằng native `--add-dir` arguments do qiqi_delegate inject. TaskPacket vẫn phải semantically sufficient; Work Item locator/revision cung cấp durable continuity cho tracked task.

Nếu `.qiqi/config.local.json` tồn tại, route policy chỉ chọn execution-agent family đã enable và dùng configured `default_route`. Workspace cũ chưa chạy unified installer giữ fallback `claude-balanced`.

## Verification

```bash
bash scripts/workspace-check.sh
```

Real workspace có local setup config chỉ yêu cầu Herdr integrations cho execution agents đã chọn; workspace legacy không có config tiếp tục verify toàn bộ adapters trong `agent-routing.yaml`.
