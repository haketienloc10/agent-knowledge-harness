# Work Item human CLI

`agent-work-item` là human-facing, strictly read-only view của cùng canonical SQLite
Work Item store mà QiQi và repository agents sử dụng qua MCP. CLI không có lệnh create,
update, complete hoặc delete.

## Overview

```bash
agent-work-item list
```

Không truyền subcommand cũng tương đương `list`:

```bash
agent-work-item
```

Header hiển thị exact count theo global status:

```text
WORK ITEMS
TOTAL 4  ACTIVE 2  WAITING 0  BLOCKED 1  DONE 1  CANCELLED 0
```

Bảng bên dưới hiển thị:

```text
ID | STATUS | PHASE | REPOS | UPDATED | TITLE
```

Filter khi cần:

```bash
agent-work-item list --status active
agent-work-item list --repository search_air
agent-work-item list --status blocked --limit 20
```

Count trên header luôn là count toàn store; filter chỉ áp dụng cho bảng ticket bên dưới.

## Task detail

```bash
agent-work-item show redmine:113387
```

Detail được bố cục để nhìn một lượt toàn canonical snapshot/material history:

- ID, status, phase, revision, created/updated;
- summary;
- current requirements;
- repositories, repo status, summary và verification;
- questions;
- decisions;
- changes;
- blockers;
- handoffs;
- next actions;
- checkpoints;
- thin artifact index.

Section rỗng vẫn được hiển thị với count `0` để dễ thấy task còn blocker/question/
handoff/artifact hay không.

Artifact index không chứa body. Mỗi row chỉ cho biết artifact id/type/state/revision,
section count, size, title và Work Item revision mà artifact dựa vào.

Raw JSON chỉ dùng khi debug:

```bash
agent-work-item show redmine:113387 --json
```

JSON này vẫn chỉ gắn thin artifact index, không hydrate artifact body.

## Artifact detail

Artifact là detail optional như intake, investigation, plan, review hoặc report. Chỉ khi
cần xem detail mới dùng `artifact`.

Xem metadata + section outline, không đọc body:

```bash
agent-work-item artifact redmine:113387 report:1 --manifest
```

Xem full artifact:

```bash
agent-work-item artifact redmine:113387 report:1
```

CLI stream từng stored chunk ra stdout thay vì gom toàn body vào memory trước khi in.
Điều này phù hợp với report/investigation dài.

Chỉ xem một section:

```bash
agent-work-item artifact redmine:113387 report:1 \
  --section verification
```

Output manifest cho biết:

```text
artifact state/type/revision
based_on_work_item_revision
created/updated
section count / total size
summary
ordered section manifest
```

Sau manifest, nếu không dùng `--manifest`, body được in theo từng heading:

```text
## Requirement review  [requirements]
...

## Verification  [verification]
...
```

## Read-only guarantee

CLI mở SQLite bằng URI `mode=ro`. Nó không dùng Work Item/artifact mutation API, không
tạo schema, không chạy write PRAGMA và không thay revision/document/artifact state.
`work-item-template-check.sh` khóa invariant này và phải fail nếu CLI có mutation path.

Nếu DB cũ chưa từng được artifact-capable MCP mở thì `show` coi artifact count là `0`.
CLI không tự tạo artifact schema; artifact schema chỉ được MCP storage layer tạo lazily.

## Installation

`install-user-mcp.sh` cài cả hai wrapper vào `~/.local/bin` mặc định:

```text
agent-work-item-mcp   # MCP runtime cho agents
agent-work-item       # read-only human viewer
```

Cả hai wrapper nhận cùng `WORK_ITEM_DB_PATH` do installer cấu hình.

Chi tiết artifact contract và payload bounds nằm trong `ARTIFACTS.md`.
