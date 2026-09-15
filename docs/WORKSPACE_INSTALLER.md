# Unified QiQi Workspace Installer

## Entry point

Từ harness checkout:

```bash
bash scripts/setup-workspace.sh /path/to/workspace
```

Installer là entrypoint khuyến nghị cho setup runtime của workspace đã được copy/migrate từ `workspace-template`.

## Interactive flow

Wizard hỏi ba lựa chọn độc lập:

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

Coordinator là client chạy QiQi ở workspace root. Execution agent là native CLI được `qiqi_delegate` launch qua Herdr tại exact repository root. Hai tập này có thể khác nhau, ví dụ:

```text
Coordinator: Codex
Execution:   Claude
Default:     claude-balanced
```

## Installer thực hiện gì

Installer:

1. validate workspace contract cơ bản;
2. cài/refresh Global Work Item MCP và Shared Knowledge MCP cho union của coordinator + execution clients;
3. sync dependency của `mcp/qiqi_delegate`;
4. configure Claude coordinator nếu được chọn;
5. verify Codex project adapter nếu Codex coordinator được chọn;
6. provision Claude child isolation nếu Claude được dùng làm execution agent;
7. cài Herdr integration cho execution agents đã chọn;
8. ghi machine-local `.qiqi/config.local.json` chứa coordinator/agent/default-route preference;
9. chạy qiqi_delegate unit tests + `workspace-check.sh` trừ khi `--skip-verify`.

## Machine-local route preference

Generated file:

```json
{
  "version": 1,
  "coordinators": ["claude", "codex"],
  "execution_agents": ["claude", "codex"],
  "default_route": "claude-balanced"
}
```

nằm tại:

```text
.qiqi/config.local.json
```

File này được ignore và không phải product/task truth. `instructions/model-routing.md` chỉ đọc nó just-in-time khi một turn thực sự delegate.

## Claude child isolation

Claude Code có thể discover workspace ancestor `.claude/CLAUDE.md` khi chạy bên trong nested repository. `claudeMdExcludes` cần absolute path, nên installer không commit path đó.

Thay vào đó, với mỗi repository trong `repos.yaml`, installer generate:

```text
<repo>/.claude/settings.local.json
```

và thêm file này vào:

```text
<repo>/.git/info/exclude
```

Generated setting exclude exact absolute workspace coordinator adapter và disable Claude auto-memory. Vì vậy cả delegated child lẫn `cd repo && claude` đều giữ isolation mà không tạo source-controlled machine path.

## Non-interactive examples

Claude coordinator + Claude execution:

```bash
bash scripts/setup-workspace.sh /path/to/workspace \
  --coordinators claude \
  --agents claude \
  --default-route claude \
  --non-interactive
```

Codex coordinator + Claude execution:

```bash
bash scripts/setup-workspace.sh /path/to/workspace \
  --coordinators codex \
  --agents claude \
  --default-route claude \
  --non-interactive
```

Both coordinators + both execution agents, Codex default:

```bash
bash scripts/setup-workspace.sh /path/to/workspace \
  --coordinators both \
  --agents both \
  --default-route codex \
  --non-interactive
```

Optional paths:

```bash
--work-item-db /path/to/work-items.sqlite3
--knowledge-store /path/to/shared-knowledge/store
```

For an environment where global MCPs are already managed separately:

```bash
--skip-global-mcp
```

## Acceptance before merge

At minimum run one E2E for every enabled coordinator/execution combination. For Claude child isolation, from an actual registered repo:

```bash
claude
/memory
/mcp
```

The child must not load workspace coordinator instructions and must not see workspace-local `qiqi_delegate`. Claude auto-memory must be off.
