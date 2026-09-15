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

`work-items/` là current mutable task resource cấp workspace. Runtime export:

```text
QIQI_WORK_ITEMS_DIR=<workspace>/work-items
```

Launcher tự tạo directory nếu thiếu; user không cần export machine-local path.

QiQi dùng `$work-item` để quản lý lifecycle request → investigation/plan → implementation → verification/review → final report. Dossier không lưu turn history.

## Delegation

QiQi delegate repo-local work qua `delegate_repo_task`. Supported agents nhận shared Work Items directory bằng native `--add-dir` integration. TaskPacket vẫn phải semantically sufficient; Work Item cung cấp durable continuity cho tracked task.

## Verification

```bash
bash scripts/workspace-check.sh
```
