# Claude Code cho QiQi Workspace

## Mục tiêu

Claude Code có thể chạy QiQi coordinator bằng command native:

```bash
cd /path/to/multi-repo
claude
```

Không dùng `workspace/.mcp.json`. `qiqi_delegate` là orchestration capability của QiQi coordinator, nên phải được đăng ký ở Claude Code **local scope** cho đúng workspace thay vì project scope có thể được discover từ cây thư mục.

## Cấu hình một lần

Sau khi copy/migrate workspace template:

```bash
cd /path/to/multi-repo
bash scripts/setup-claude.sh
```

Script đăng ký:

```text
qiqi_delegate -> local scope -> scripts/qiqi-mcp-server.sh
```

Sau đó khởi động bình thường:

```bash
claude
```

Kiểm tra registration:

```bash
claude mcp get qiqi_delegate
```

`work_item` và `knowledge` vẫn là user-scoped MCP được cài bởi template tương ứng; workspace không tạo project/local copy của hai canonical services này.

## Coordinator instructions

Claude Code không đọc `AGENTS.md` trực tiếp. Workspace dùng:

```text
.claude/CLAUDE.md
  -> @../AGENTS.md
```

Không đặt `CLAUDE.md` tại workspace root. Repository child có thể nằm bên dưới workspace root; root-level `CLAUDE.md` là ancestor instruction và có thể bị child Claude session load cùng repo-local instructions. Đặt adapter tại `.claude/CLAUDE.md` giữ coordinator startup native trong workspace nhưng không tạo ancestor `workspace/CLAUDE.md` cho child repositories.

## Memory boundary

`.claude/settings.json` dùng hai lớp guard:

```json
{
  "autoMemoryEnabled": false,
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
```

`autoMemoryEnabled=false` là project setting khai báo intent. `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` là runtime hard guard được Claude Code hỗ trợ để không load hoặc ghi auto-memory. Dùng cả hai vì QiQi không được có hidden machine-local task/product truth.

Canonical mutable task state vẫn thuộc Global Work Item MCP; reusable durable truth vẫn thuộc Knowledge MCP.

`scripts/qiqi-mcp-server.sh` cũng export:

```bash
CLAUDE_CODE_DISABLE_AUTO_MEMORY=1
```

cho runtime descendants, vì Claude repository children là TaskPacket executors và không được mang hidden machine-local task memory giữa các independent delegated sessions.

## Scope boundary

```text
Claude QiQi launched at workspace root
├── .claude/CLAUDE.md -> AGENTS.md
├── .claude/settings.json
├── auto memory         disabled by setting + env guard
├── qiqi_delegate       local scope
├── work_item           user scope
└── knowledge           user scope

Claude child launched at exact repository root
├── repo-local CLAUDE.md / AGENTS.md
├── no workspace-local qiqi_delegate registration
└── auto memory disabled by qiqi_delegate runtime environment
```

Repository child vẫn có thể thấy user-scoped capabilities theo machine policy, nhưng TaskPacket closed-world invariant không thay đổi: child không dùng Work Item/Knowledge/hidden coordinator state để reconstruct missing task semantics.

## Verification

```bash
uv run --project mcp/qiqi_delegate python -m unittest discover -s mcp/qiqi_delegate/tests -v
bash scripts/workspace-check.sh
```

Trong fresh Claude coordinator session, `/memory` phải báo:

```text
Auto-memory: off
```

Nếu vẫn `on`, chạy `/status` và kiểm tra managed/local settings có override project configuration hay không; không merge khi auto memory của coordinator còn bật.

Contract test `test_claude_workspace_config.py` bảo vệ các invariant:

- không có workspace `.mcp.json`;
- Claude coordinator import canonical `AGENTS.md`;
- coordinator auto memory có cả declarative setting và runtime env guard;
- `qiqi_delegate` registration dùng local scope;
- delegated Claude runtime tắt auto memory.
