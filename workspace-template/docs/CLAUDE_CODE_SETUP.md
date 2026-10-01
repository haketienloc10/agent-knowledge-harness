# Claude Code setup cho QiQi workspace

## Mục tiêu

Sau setup một lần, Claude QiQi coordinator khởi động native:

```bash
cd /absolute/path/to/workspace
claude
```

Không dùng wrapper command và không dùng workspace `.mcp.json` cho `qiqi_delegate`.

Recommended entrypoint là unified harness installer:

```bash
bash /path/to/agent-knowledge-harness/scripts/setup-workspace.sh /absolute/path/to/workspace
```

Nếu cần chạy riêng Claude helper:

```bash
cd /absolute/path/to/workspace
bash scripts/setup-claude.sh
```

## Coordinator adapter

Claude Code không đọc `AGENTS.md` trực tiếp. Setup materialize:

```text
<workspace>/.claude/CLAUDE.md
  -> @../AGENTS.md
```

Không tạo `<workspace>/CLAUDE.md` và không tạo `<workspace>/.mcp.json`.

`qiqi_delegate` được đăng ký bằng Claude **local MCP scope** tại đúng workspace project:

```text
qiqi_delegate -> bash <workspace>/scripts/qiqi-mcp-server.sh
```

`work-items/` vẫn là filesystem task truth của current main. Shared Knowledge vẫn là user-scope MCP; Work Item không phải MCP.

## Coordinator auto-memory boundary

Setup merge-safe vào `<workspace>/.claude/settings.json`:

```json
{
  "autoMemoryEnabled": false,
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  },
  "permissions": {
    "allow": [
      "mcp__qiqi_delegate__delegate_repo_task"
    ]
  }
}
```

Hai guard giữ hidden Claude auto-memory ngoài Sources of Truth của QiQi. Existing unrelated settings được preserve; invalid JSON hoặc incompatible field shape fail closed.

## Nested repository isolation

Claude launched từ nested repository có thể discover ancestor workspace coordinator instructions. Vì `claudeMdExcludes` match absolute path, không commit exclusion vào repo source.

`setup-claude.sh` đọc every concrete `repos.yaml` path và generate machine-local project settings. Với ordinary checkout, path là:

```text
<repo>/.claude/settings.local.json
```

Với linked Git worktree, Claude Code đọc project-local settings tại **main checkout root** của repository, nên helper resolve `git rev-parse --git-common-dir` và ghi:

```text
<main-checkout>/.claude/settings.local.json
```

Ví dụ runtime value:

```json
{
  "claudeMdExcludes": [
    "/absolute/path/to/workspace/.claude/CLAUDE.md"
  ],
  "autoMemoryEnabled": false,
  "env": {
    "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"
  }
}
```

Machine-local file được thêm vào repository common Git `info/exclude`. Nếu `.claude/settings.local.json` đang tracked, installer fail thay vì ghi absolute machine path vào source control.

## Codex coordinator + Claude execution agent

Claude child isolation không phụ thuộc Claude có phải coordinator hay không. Unified installer dùng:

```bash
bash scripts/setup-claude.sh --children-only
```

cho topology:

```text
QiQi parent = Codex
repo child  = Claude
```

Mode này không đăng ký Claude local `qiqi_delegate` và không tạo workspace coordinator `CLAUDE.md`; nó chỉ provision repo-local child settings/auto-memory guard.

## Scope boundary

```text
Claude QiQi @ workspace root
├── .claude/CLAUDE.md -> AGENTS.md
├── .claude/settings.json
├── qiqi_delegate       Claude local scope
├── Knowledge           user scope when selected
└── Work Item           workspace filesystem + workspace skill

Claude child @ exact repository Git root/worktree
├── repo-local CLAUDE.md / AGENTS.md
├── canonical .claude/settings.local.json (machine-local; main checkout for worktrees)
├── workspace coordinator CLAUDE.md excluded
├── auto-memory disabled
├── no workspace-local qiqi_delegate registration
└── mounted workspace work-items/ supplied by qiqi_delegate during delegation
```

TaskPacket + Work Item contracts của current main không đổi: child không dùng hidden coordinator conversation/memory để reconstruct missing objective/scope/acceptance.

## E2E verification

Sau unified setup:

```bash
cd /absolute/path/to/workspace
claude
```

`/memory` của coordinator phải cho thấy workspace `.claude/CLAUDE.md` import `AGENTS.md`, và auto-memory phải off.

Sau đó kiểm nested repo trực tiếp:

```bash
cd /absolute/path/to/workspace/path/from/repos.yaml
claude
```

`/memory` không được load workspace `.claude/CLAUDE.md`/QiQi coordinator policy và auto-memory phải off. Với linked worktree, verify canonical local settings file nằm ở main checkout root như Claude Code settings resolution quy định.

Cuối cùng delegate một read-only task từ QiQi qua route Claude để verify Herdr integration, exact repo root, Work Item additional-dir mount và native final-response capture vẫn hoạt động trên current qiqi_delegate implementation.
