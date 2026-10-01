# Unified workspace installer

`setup-workspace.sh` là entrypoint setup hiện tại cho QiQi workspace.

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace
```

## Interactive choices

Wizard hỏi ba lựa chọn độc lập:

```text
QiQi coordinator clients
  1) Claude Code
  2) Codex
  3) Both

Herdr execution agents
  1) Claude Code
  2) Codex
  3) Both

Default delegation route    # chỉ hỏi khi execution agents = Both
  1) Claude balanced
  2) Codex balanced
```

Supported examples:

```text
Claude parent -> Claude child
Claude parent -> Codex child
Codex parent  -> Claude child
Codex parent  -> Codex child
Both parents  -> Both child families
```

## What gets installed

### Work Item

Current main uses filesystem-native Work Items. There is no Work Item MCP.

Installer runs:

```bash
work-item-template/scripts/install-workspace-skill.sh \
  --clients <selected coordinators> \
  <workspace>
```

Only selected QiQi parent clients receive workspace `$work-item` skill discovery.
Repository children do not receive this lifecycle skill.

### Shared Knowledge

Knowledge remains a user-scope MCP + skill. It may be used by parent or repository execution agents, so installer registers it for the union of both selected client sets.

Example:

```text
coordinator = codex
agents      = claude
Knowledge   = codex + claude
```

### qiqi_delegate coordinator adapter

Codex uses tracked workspace `.codex/config.toml`.

Claude uses `workspace/scripts/setup-claude.sh` to generate coordinator project settings and add `qiqi_delegate` at Claude **local scope**. No workspace `.mcp.json` is created.

### Herdr execution integrations

Only selected repository execution families are installed:

```bash
herdr integration install claude
herdr integration install codex
```

## Machine-local runtime preference

Installer writes:

```text
<workspace>/.qiqi/config.local.json
```

Shape:

```json
{
  "version": 1,
  "coordinators": ["claude", "codex"],
  "execution_agents": ["claude", "codex"],
  "default_route": "claude-balanced"
}
```

The file is ignored by workspace source control. It is execution preference/capability state, not Work Item/Knowledge/task truth.

`instructions/model-routing.md` reads it only just-in-time for actual delegation. If absent, legacy behavior is preserved and `claude-balanced` is the fallback.

## Claude child isolation

When Claude is selected as coordinator or execution agent, setup provisions each concrete repository from `repos.yaml` with machine-local:

```text
<repo>/.claude/settings.local.json
```

If a workspace Claude coordinator adapter exists, it is excluded with an absolute `claudeMdExcludes` entry. Auto-memory is also disabled. The local settings file is added to the repository Git info/exclude and must not be tracked.

For Codex-parent/Claude-child topology the helper runs in `--children-only` mode, so Claude is not accidentally enabled as a workspace coordinator.

## Non-interactive mode

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace \
  --coordinators both \
  --agents both \
  --default-route codex \
  --non-interactive
```

Single execution-agent selections infer their corresponding balanced default automatically:

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace \
  --coordinators codex \
  --agents claude \
  --non-interactive
```

The second example resolves `default_route=claude-balanced`.

Optional flags:

```text
--knowledge-store PATH
--skip-knowledge
--skip-verify
```

## Existing workspace migration

Run harness migrations first, including legacy Work Item SQLite export/removal steps required by the current migration chain. Then run unified setup from the **latest harness checkout**:

```bash
bash scripts/migrate-workspace.sh /absolute/path/to/workspace --verify
bash scripts/setup-workspace.sh /absolute/path/to/workspace
```

The setup installer does not silently export/delete legacy Work Item data or recreate the removed Work Item MCP.

## E2E gates

Before considering a new setup contract complete:

1. `bash scripts/workspace-check.sh` passes in the materialized workspace.
2. Selected parent client sees `qiqi_delegate`.
3. Selected execution-agent Herdr integrations report `current`.
4. Claude coordinator `/memory` has auto-memory off.
5. Direct Claude session from nested repo does not load workspace coordinator instructions.
6. Delegation through selected default route settles and preserves current Work Item mount + native result-capture behavior.
