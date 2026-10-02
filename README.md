# Agent Knowledge Harness

Harness cho multi-repository QiQi workspace với các thành phần chính:

- `workspace-template/`: SLP control plane — Supervisor policy + QiQi Lead orchestration + `qiqi_delegate`;
- `repo-template/`: SLP Peer execution policy cho từng Git root;
- `work-item-template/`: workspace-scoped filesystem-native Work Item lifecycle skill/templates;
- `knowledge-template/`: user-scoped Shared Knowledge MCP cho reusable durable knowledge;
- `user-rules-template/`: user-scoped response/orchestration rules cho Claude Code và Codex;
- `writing-template/`: user-scoped writing skills, bắt đầu với `ste-vi`;
- `migrations/`: upgrade definitions cho workspace/repo đã cài harness.

## SLP architecture

```text
                 Human
                   |
        +----------+----------+
        |                     |
   Supervisor              Lead (QiQi)
   governance                 |
                              +-- Peer A
                              +-- Peer B
                              +-- Peer C
```

Supervisor là oversight plane, không phải technical Lead thứ hai. QiQi giữ vai trò Lead và là canonical Work Item writer/cross-repo orchestrator. Repository child agents là Peers với bounded ownership và independent technical judgment.

Shared contract: `workspace-template/docs/WORKSPACE_PROTOCOL.md`. Supervisor instructions: `workspace-template/instructions/supervisor.md`.

Delegation chỉ được coi là đóng khi có đủ `Lead brief -> actual Peer response -> explicit Lead disposition`; runtime `DONE` hoặc passing tests chỉ là evidence, không tự đồng nghĩa acceptance.
## Sources of truth

```text
workspace/work-items/  = current mutable product-task truth
Knowledge MCP          = reusable durable truth
Repo source/test       = implementation truth
.qiqi/state            = runtime/session truth
```

Work Item không còn là MCP/SQLite service. `qiqi_delegate` mount `<workspace>/work-items` vào supported child agents bằng shared directory runtime contract.

Work Item là current semantic state, không phải execution history. Multi-turn investigation/implementation rewrite living state; requirement changes rewrite effective current requirements rồi reconcile prior findings theo materiality.

## User-scope response và writing

Cài skill viết và response rules cho cả Codex và Claude Code:

```bash
bash writing-template/scripts/install-user-skill.sh
bash user-rules-template/scripts/install-user-rules.sh
```

`ste-vi` áp dụng STE-lite cho tiếng Việt: câu ngắn, thuật ngữ ổn định, technical name giữ nguyên và quan hệ nhân quả rõ. Đây là cách viết lấy cảm hứng từ ASD-STE100, không phải tuyên bố compliance ASD-STE100 cho tiếng Việt.

Codex đọc user instruction từ `${CODEX_HOME:-$HOME/.codex}/AGENTS.md` và user skill từ
`${CODEX_HOME:-$HOME/.codex}/skills/ste-vi`. Claude Code đọc instruction từ
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/CLAUDE.md` và user skill từ
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/ste-vi`. Hai installer tôn trọng cả
`CODEX_HOME` và `CLAUDE_CONFIG_DIR` khi các biến này được cấu hình.

`user-rules-template` giữ policy chọn hình thức giải thích ở tầng response: bắt đầu bằng text, chuyển sang diagram khi độ khó nằm ở quan hệ/luồng, và cân nhắc interactive HTML khi cần thao tác với state hoặc input.

Hai template này cài vào user home, không materialize vào workspace/repo con và không cần migration chỉ vì thay đổi nội dung của chúng.

## Work Item template

`$work-item` là workspace/QiQi lifecycle skill. Harness expose một skill duy nhất với internal phase references cho intake/investigation/planning/review; repo child chỉ đọc TaskPacket + mounted Work Item và không sở hữu canonical lifecycle.

```bash
cd work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-workspace-skill.sh /path/to/workspace
```

Installer materialize cùng Work Item skill tree vào `<workspace>/.agents/skills/work-item` và `<workspace>/.claude/skills/work-item`; không copy skill xuống repo con.

Operational protocol: `work-item-template/skills/work-item/SKILL.md`.

## Workspace migration

Với máy có legacy Work Item SQLite, cutover theo thứ tự:

1. export exact legacy DB theo `work-item-template/README.md` (nếu old installer dùng custom `--db-path`, truyền exact path bằng `--db`);
2. kiểm tra imported dossiers/archive rồi chạy `work-item-template/scripts/remove-legacy-user-mcp.sh` để gỡ registration cũ có xác minh ownership;
3. migrate workspace/repositories;
4. cài/update workspace-scoped `$work-item` skill, cài Herdr Codex/Claude integrations và chạy workspace verification;
5. mở fresh QiQi agent session từ workspace root.

```bash
bash scripts/migrate-workspace.sh /path/to/workspace --dry-run
bash scripts/migrate-workspace.sh /path/to/workspace --verify
```

`--verify` trên workspace thực kiểm canonical repo/dependency registry, exact Git roots, qiqi_delegate tests và Herdr integration readiness.

Historical migration files mô tả contract tại thời điểm áp dụng; migration mới supersede current runtime/policy nhưng không rewrite lịch sử.
