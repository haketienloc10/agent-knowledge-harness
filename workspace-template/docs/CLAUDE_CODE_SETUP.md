# Claude Code cho QiQi Workspace

## Mục tiêu

Claude Code có thể chạy QiQi coordinator bằng command native:

```bash
cd /path/to/multi-repo
claude
```

Không dùng `workspace/.mcp.json`. `qiqi_delegate` là orchestration capability của QiQi coordinator, nên phải được đăng ký ở Claude Code **local scope** cho đúng workspace thay vì project scope có thể được discover từ cây thư mục.

## Cài đặt khuyến nghị

Từ harness checkout, dùng installer thống nhất:

```bash
bash scripts/setup-workspace.sh /path/to/multi-repo
```

Installer cho chọn độc lập:

```text
Coordinator clients
  1) Claude Code
  2) Codex
  3) Both

Herdr execution agents
  1) Claude Code
  2) Codex
  3) Both

Default delegation route
  1) Claude balanced
  2) Codex balanced
```

Nếu chọn Claude làm coordinator, installer gọi workspace helper `scripts/setup-claude.sh` để tạo/merge Claude project config và đăng ký:

```text
qiqi_delegate -> Claude local scope -> scripts/qiqi-mcp-server.sh
```

Nếu Claude chỉ là execution agent nhưng không phải coordinator, installer gọi:

```bash
bash scripts/setup-claude.sh --children-only
```

để chỉ provision isolation cho repository child, không enable Claude coordinator.

`work_item` và `knowledge` vẫn là user-scoped MCP. Unified installer đăng ký hai service này cho union của coordinator clients và execution agents đã chọn.

## Coordinator instructions

Claude Code không đọc `AGENTS.md` trực tiếp. Khi Claude coordinator được chọn, setup generate:

```text
.claude/CLAUDE.md
  -> @../AGENTS.md
```

Không đặt `CLAUDE.md` tại workspace root.

Claude có thể discover ancestor `.claude/CLAUDE.md` từ nested repository. Vì `claudeMdExcludes` match absolute path, không commit exclusion vào repo template. Setup đọc `repos.yaml` và generate cho từng repo:

```text
<repo>/.claude/settings.local.json
```

với dạng:

```json
{
  "claudeMdExcludes": [
    "/absolute/workspace/.claude/CLAUDE.md"
  ],
  "autoMemoryEnabled": false,
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
```

Absolute path là machine-local nên file này được thêm vào `<repo>/.git/info/exclude`, không commit vào repository child.

Nếu workspace không có Claude coordinator adapter thì `--children-only` không tạo exclusion giả; nó vẫn tạo child auto-memory guard.

## Memory boundary

Workspace coordinator `.claude/settings.json` dùng hai lớp guard:

```json
{
  "autoMemoryEnabled": false,
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
```

`autoMemoryEnabled=false` khai báo intent; `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` là runtime hard guard. QiQi không dùng hidden machine-local auto-memory làm task/product truth.

Canonical mutable task state vẫn thuộc Global Work Item MCP; reusable durable truth vẫn thuộc Knowledge MCP.

`scripts/qiqi-mcp-server.sh` cũng export:

```bash
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
```

cho delegated runtime descendants.

## Scope boundary

```text
Claude QiQi launched at workspace root
├── generated .claude/CLAUDE.md -> AGENTS.md
├── generated/merged .claude/settings.json
├── auto memory         disabled
├── qiqi_delegate       local scope
├── work_item           user scope
└── knowledge           user scope

Claude child launched at exact repository root
├── repo-local policy
├── generated .claude/settings.local.json
│    └── excludes workspace coordinator CLAUDE.md by absolute path
├── no workspace-local qiqi_delegate registration
└── auto memory disabled
```

Repository child vẫn có thể thấy user-scoped capabilities theo machine policy, nhưng TaskPacket closed-world invariant không thay đổi: child không dùng Work Item/Knowledge/hidden coordinator state để reconstruct missing task semantics.

## Verification

Static/unit:

```bash
uv run --project mcp/qiqi_delegate python -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Coordinator E2E:

```bash
cd /path/to/multi-repo
claude
/memory
/mcp
```

Expected:

```text
Auto-memory: off
qiqi_delegate: connected
```

Child isolation E2E:

```bash
cd /path/to/multi-repo/<repo>
claude
/memory
/mcp
```

Expected:

- workspace `.claude/CLAUDE.md` không xuất hiện trong effective memory;
- `qiqi_delegate` local registration của workspace không xuất hiện;
- repo-local policy vẫn được load;
- auto-memory off.

Nếu child vẫn load workspace coordinator instructions hoặc thấy `qiqi_delegate`, không merge.
