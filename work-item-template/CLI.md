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

## Detail

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
- checkpoints.

Section rỗng vẫn được hiển thị với count `0` để dễ thấy task còn blocker/question/
handoff hay không.

Raw JSON chỉ dùng khi debug:

```bash
agent-work-item show redmine:113387 --json
```

## Read-only guarantee

CLI mở SQLite bằng URI `mode=ro`. Nó không dùng Work Item mutation API, không tạo
schema, không chạy write PRAGMA và không thay revision/document state. `work-item-template-check.sh`
khóa invariant này và phải fail nếu CLI có mutation path.

## Installation

`install-user-mcp.sh` cài cả hai wrapper vào `~/.local/bin` mặc định:

```text
agent-work-item-mcp   # MCP runtime cho agents
agent-work-item       # read-only human viewer
```

Cả hai wrapper nhận cùng `WORK_ITEM_DB_PATH` do installer cấu hình.
