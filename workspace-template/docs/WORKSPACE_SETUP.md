# Workspace setup

## Layout

```text
<workspace>/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── work-items/
├── instructions/
├── mcp/qiqi_delegate/
└── scripts/
```

`work-items/` là workspace-level current task resource. Không cài Global Work Item MCP và không tạo SQLite Work Item DB.

## Runtime

Parent QiQi/$work-item resolve canonical task resource trực tiếp tại `<workspace>/work-items`; parent không dựa vào environment variable được một MCP child process export.

`scripts/qiqi-mcp-server.sh` resolve workspace root, `mkdir -p work-items`, export `QIQI_WORK_ITEMS_DIR=<workspace>/work-items` trong delegated runtime và start `qiqi_delegate`.

`QIQI_WORK_ITEMS_DIR` là child-facing mount alias. qiqi_delegate map cùng `filesystem.additional_dirs` capability sang native `--add-dir` arguments cho cả Codex và Claude; không cần wrapper agent riêng.

## Work Item lifecycle

Cài/update `$work-item` skill từ harness:

```bash
cd work-item-template
bash scripts/install-user-skill.sh
```

Tracked task nằm tại `work-items/<id>/`. `WORK_ITEM.md` là current canonical state; lifecycle docs là living semantic state, không append-only history.

Requirement change:

1. rewrite effective current requirements;
2. increment revision;
3. reconcile prior investigation/plan/review với requirement mới;
4. giữ finding cũ nếu fact còn đúng, reinterpret khi implication đổi, revalidate/remove khi assumption đã supersede.

## Repo delegation

TaskPacket vẫn chứa objective/scope/acceptance đầy đủ. Với tracked task, QiQi truyền locator + revision qua `context.trusted_facts`; child được đọc mounted Work Item nhưng không mutate canonical dossier.

`instructions/model-routing.md` không phải mandatory startup material. Default delegation route là `claude-balanced`; khi một turn thực sự delegate, QiQi đọc route policy just-in-time ngay trước route decision rồi chọn exact route.

## Verification

```bash
bash scripts/workspace-check.sh
```
