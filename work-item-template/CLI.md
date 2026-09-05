# Work Item human CLI

`agent-work-item` là human-facing, strictly read-only view của cùng canonical SQLite
Work Item store mà QiQi sử dụng qua MCP. Repository child không dùng store này để hiểu
hoặc persist delegated TaskPacket. CLI không có lệnh create, update, complete hoặc delete.

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

## Work Item detail

```bash
agent-work-item show redmine:113387
```

Detail được bố cục để nhìn một lượt canonical snapshot/material history:

- ID, status, phase, revision, created/updated;
- summary;
- current requirements;
- repositories, repo status, summary và verification;
- **thin artifact index** (metadata/size, không body);
- questions;
- decisions;
- changes;
- blockers;
- handoffs;
- next actions;
- checkpoints.

Section rỗng vẫn được hiển thị với count `0` để dễ thấy task còn blocker/question/
handoff/artifact hay không.

Raw JSON chỉ dùng khi debug:

```bash
agent-work-item show redmine:113387 --json
```

`show --json` cũng chỉ chứa thin artifact index.

## Optional artifact detail

Full artifact body chỉ được đọc khi gọi explicit:

```bash
agent-work-item artifact redmine:113387 report:1
```

Default artifact view là diagnostic human view: nó hiển thị artifact metadata, summary,
section id/order và chunk/size counters quanh stored body.

Chỉ xem một section:

```bash
agent-work-item artifact redmine:113387 report:1 --section code-review
```

### Copy/paste-ready raw view

Khi cần copy report trực tiếp sang Redmine hoặc surface khác, dùng:

```bash
agent-work-item artifact redmine:113387 report:1 --raw
```

`--raw` chỉ stream theo thứ tự:

```text
<section title>

<stored section body>

<section title>

<stored section body>
```

Nó không in artifact metadata, summary, revision, section id, chunk counters hoặc
separator diagnostic. Stored chunks được stream nối tiếp nguyên văn theo `chunk_index`;
chunk boundary không tạo newline/ký tự mới nên một từ bị chia giữa hai stored chunks vẫn
copy ra liền mạch.

Có thể lấy raw của đúng một section; title của section vẫn được giữ để block copy-paste
hoàn chỉnh:

```bash
agent-work-item artifact redmine:113387 report:1 \
  --section solution \
  --raw
```

`--raw` không materialize toàn artifact trong RAM. Nó dùng cùng read-only streaming path
như diagnostic text view. `--raw` và `--json` mutually exclusive.

Raw artifact JSON dùng khi cần structured/debug output:

```bash
agent-work-item artifact redmine:113387 report:1 --json
```

Chỉ explicit `--json` mới materialize selected artifact trong memory.

Human CLI có thể stream full artifact ra terminal vì đây không phải MCP/LLM context.
MCP agent-side vẫn đọc artifact body theo bounded section chunks.

## Read-only guarantee

CLI mở SQLite bằng URI `mode=ro`. Nó không dùng Work Item/artifact mutation API,
không tạo schema, không chạy write PRAGMA và không thay Work Item hay artifact revision.
Default diagnostic view, `--raw` và `--json` đều là observer paths;
`work-item-template-check.sh` khóa invariant read-only này và phải fail nếu CLI có
mutation path.

## Installation

`install-user-mcp.sh` cài cả hai wrapper vào `~/.local/bin` mặc định:

```text
agent-work-item-mcp   # user-scope Work Item MCP service used by QiQi/orchestration
agent-work-item       # read-only human viewer
```

Cả hai wrapper nhận cùng `WORK_ITEM_DB_PATH` do installer cấu hình.
