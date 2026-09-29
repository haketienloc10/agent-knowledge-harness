# Workspace template

Workspace template cung cấp SLP control plane: Supervisor policy, QiQi/Lead orchestration, repo registry, shared Work Items và `qiqi_delegate`.

```text
AGENTS.md                         # Lead policy (QiQi)
identity.md
repos.yaml
SYSTEM_MAP.md
docs/WORKSPACE_PROTOCOL.md        # shared SLP contract
work-items/
instructions/supervisor.md        # Supervisor overlay/policy
instructions/
mcp/qiqi_delegate/
scripts/
```

## SLP roles

- **Supervisor**: governance/oversight; kiểm intent/workflow/communication-loop deviation, không sửa implementation và không accept candidate.
- **Lead (QiQi)**: canonical Work Item writer + cross-repo orchestrator + technical acceptance owner.
- **Peers**: repository-local agents nhận bounded TaskPacket, sở hữu một write/read scope và trả evidence độc lập.

Shared contract: `docs/WORKSPACE_PROTOCOL.md`. Supervisor host/session phải inject `instructions/supervisor.md`; nếu runtime chưa có Supervisor→Lead channel/wake-up mechanism thì phải coi đó là monitoring gap, không giả vờ continuous supervision.
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

QiQi/Lead delegate repo-local Peer work qua `delegate_repo_task`. Supported agents nhận shared Work Items directory bằng native `--add-dir` arguments do qiqi_delegate inject. TaskPacket vẫn phải semantically sufficient; Work Item locator/revision cung cấp durable continuity cho tracked task.

## Verification

```bash
bash scripts/workspace-check.sh
```
