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

QiQi có hai orchestration surfaces:

- direct `delegate_repo_task`: chỉ cho một repo-local assignment đơn giản trong đúng một repository;
- TaskGraph: bắt buộc cho multi-repo, dependency/wave, parallel nodes, selective retry/RESUME, per-node semantic review hoặc replan/reconciliation.

TaskGraph outer loop:

```text
start_graph -> delegate_next -> review -> submit_decisions
                                   | retry -> delegate_next
                                   | replan -> reconcile_graph -> delegate_next
                                   -> graph_state=complete
```

Supported agents nhận shared Work Items directory bằng native `--add-dir` arguments do qiqi_delegate inject. TaskPacket vẫn phải semantically sufficient; Work Item locator/revision cung cấp durable continuity cho tracked task.

Authored graph hiện process-owned. Nếu Graph API trả `code=graph_definition_unavailable` sau MCP restart, QiQi không tiếp tục stale run: mặc định re-author fresh TaskGraph cho remaining verified work. Direct RESUME chỉ là recovery bridge hẹp cho đúng interrupted node khi QiQi còn exact prior `session_id` và sufficient TaskPacket/repository/route; exception này không cho phép bypass Graph cho sibling/remaining work.

## Verification

```bash
bash scripts/workspace-check.sh
```
