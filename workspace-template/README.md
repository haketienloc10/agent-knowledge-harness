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

## Verification

```bash
bash scripts/workspace-check.sh
```
