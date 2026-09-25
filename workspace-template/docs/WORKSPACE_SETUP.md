# Workspace setup

## Recommended installer

Sau khi materialize hoặc migrate workspace, chạy từ harness checkout:

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace
```

Wizard chọn độc lập QiQi coordinator (`claude|codex|both`), Herdr execution agents (`claude|codex|both`) và default balanced route khi cả hai execution agents được enable.

Installer thực hiện current-main setup contract:

- cài workspace-scoped `$work-item` skill chỉ cho coordinator đã chọn;
- cài Shared Knowledge skill/MCP cho union của coordinator + execution agents;
- configure Claude coordinator/local-scope `qiqi_delegate` khi được chọn;
- provision Claude nested-repo isolation khi Claude là coordinator hoặc execution agent;
- verify Codex project adapter khi Codex là coordinator;
- install Herdr integrations chỉ cho selected execution agents;
- lưu machine-local `.qiqi/config.local.json` với `coordinators`, `execution_agents`, `default_route`;
- chạy `scripts/workspace-check.sh`.

Non-interactive example:

```bash
bash scripts/setup-workspace.sh /absolute/path/to/workspace \
  --coordinators both \
  --agents both \
  --default-route claude \
  --non-interactive
```

Work Item **không còn là MCP/SQLite service**. Unified installer không cài/recreate legacy `work_item` MCP.

## Layout

```text
<workspace>/
├── AGENTS.md
├── identity.md
├── repos.yaml
├── SYSTEM_MAP.md
├── work-items/
├── .agents/skills/work-item/    # khi Codex coordinator được chọn
├── .claude/skills/work-item/    # khi Claude coordinator được chọn
├── .claude/CLAUDE.md            # generated khi Claude coordinator được chọn
├── instructions/
├── mcp/qiqi_delegate/
└── scripts/
```

`work-items/` là workspace-level current task resource. Runtime mới không cài Global Work Item MCP và không tạo SQLite Work Item DB.

`$work-item` cũng là **workspace-scoped QiQi parent skill**. Repo child không nhận một copy riêng của skill; child dùng TaskPacket + mounted Work Item read-only context theo repo `AGENTS.md`.

## Runtime

Parent QiQi/$work-item resolve canonical task resource trực tiếp tại `<workspace>/work-items`; parent không dựa vào environment variable được một MCP child process export.

`scripts/qiqi-mcp-server.sh` resolve workspace root, `mkdir -p work-items`, export `QIQI_WORK_ITEMS_DIR=<workspace>/work-items` cho qiqi_delegate và start MCP. qiqi_delegate dùng alias này để inject native additional-dir access cho Codex/Claude.

Child **không phụ thuộc vào env inheritance từ Herdr server**. Với tracked task, TaskPacket truyền absolute dossier locator:

```text
work_item_path=<absolute-workspace-path>/work-items/<directory-key>; id=<canonical-id>; revision=<n>
```

## Claude Code coordinator + child isolation

Claude coordinator setup nằm trong:

```bash
bash scripts/setup-claude.sh
```

Unified installer gọi helper này tự động khi cần. Helper không tạo workspace `.mcp.json`; thay vào đó:

```text
.claude/CLAUDE.md -> @../AGENTS.md
qiqi_delegate      -> Claude local MCP scope for workspace project
```

Claude nested repo có thể discover ancestor coordinator instructions. Vì `claudeMdExcludes` match absolute path, setup generate machine-local project-local settings. Ordinary checkout dùng:

```text
<repo>/.claude/settings.local.json
```

Linked Git worktree dùng local settings tại **main checkout root** của repository, theo Claude Code settings resolution. Helper resolve `git rev-parse --git-common-dir`, lấy parent directory làm canonical settings root, và ghi:

```text
<main-checkout>/.claude/settings.local.json
```

File chứa exclusion tới exact workspace `.claude/CLAUDE.md` và auto-memory guards, rồi được thêm vào repository common Git `info/exclude`. Installer fail nếu `.claude/settings.local.json` đang tracked, tránh commit machine-specific absolute path.

Case Codex coordinator + Claude execution agent dùng:

```bash
bash scripts/setup-claude.sh --children-only
```

để chỉ provision child isolation mà không enable Claude coordinator.

## Work Item ID/path

Canonical ID match `^[a-z][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9._-]*$`. Filesystem key replace colon separator đầu tiên bằng `~`, ví dụ `redmine:116655 -> redmine~116655`.

`~` loại bỏ collision do separator, nhưng canonical external-id phân biệt hoa/thường trong khi filesystem macOS/Windows thường không. Vì vậy Work Items root dùng contract **casefold-unique**: không được có hai directory key khác spelling nhưng cùng `casefold()`. Trước create/read/write `$work-item` phải reject sibling casefold-equivalent; nếu dossier đã tồn tại thì front-matter `00_WORK_ITEM.md.id` phải khớp exact canonical ID. Đồng thời reject invalid/traversal ID và verify resolved dossier vẫn nằm dưới Work Items root.

Canonical dossier filenames:

```text
00_WORK_ITEM.md
10_intake.md?
20_investigation.md?
30_plan.md?
40_review.md?
references/?
90_report.textile?
```

Numeric prefixes là part of filename contract. Dùng gaps `10/20/30/40/.../90` để có thể chèn future material phases mà không rename toàn bộ dossier. Legacy unprefixed names không được coexist với numbered targets.

## Legacy SQLite cutover

Nếu máy đã có legacy Work Item DB, **export trước khi gỡ user-scoped/global `work_item` MCP registration**:

```bash
cd agent-knowledge-harness/work-item-template
python3 scripts/export-legacy-work-items.py --workspace /absolute/path/to/workspace
```

Default source là `~/.local/share/agent-work-items/work-items.sqlite3` hoặc `WORK_ITEM_DB_PATH`. Legacy installer từng hỗ trợ `--db-path`; nếu đã dùng option đó, phải truyền exact DB bằng `--db /absolute/path/to/work-items.sqlite3`. Missing selected DB là lỗi, không được coi như export rỗng thành công.

Exporter đọc toàn bộ Work Item + artifact/section/chunk trong một SQLite read snapshot và preflight toàn bộ output trước filesystem write. Current dossier giữ current-state semantics như pending handoff và repository verification; lifecycle docs giữ revision provenance/Textile shape; full raw backup giữ chunk metadata tại `<workspace>/.qiqi/migration-backups/v0024/legacy-work-items/` với permission hạn chế. Source SQLite không bị sửa/xóa và partial artifact schema fail closed. Export cũng reject canonical IDs có directory keys casefold-equivalent để kết quả portable qua case-sensitive lẫn case-insensitive filesystems.

Legacy model cho phép một số decision provenance/evidence extension fields và không có Acceptance Criteria section tương đương protocol mới. Vì vậy imported `00_WORK_ITEM.md` có `legacy_reconciliation_required: true` và trỏ tới protected archive. Trước substantive continuation/completion/report, QiQi phải reconcile material legacy acceptance/provenance từ archive vào living state, increment revision rồi bỏ flag; archive không trở thành runtime history source sau reconciliation.

Không chạy thêm legacy Work Item mutation trong lúc export. Nếu exporter báo conflict/schema error, reconcile trước. Sau export thành công, kiểm tra dossiers cần thiết rồi **gỡ registration cũ một cách verified**:

```bash
cd agent-knowledge-harness/work-item-template
bash scripts/remove-legacy-user-mcp.sh
```

Helper chỉ remove registration `work_item` khi current definition còn trỏ tới managed legacy `agent-work-item-mcp`/`work-item-mcp-server.sh`; nếu cùng tên nhưng là registration khác, script fail thay vì xóa. Với CLI không cài trên máy, script cảnh báo để user kiểm tra client đó riêng.

## Work Item lifecycle skill

Unified installer gọi skill installer với exact coordinator selection. Manual form:

```bash
cd /path/to/agent-knowledge-harness/work-item-template
bash scripts/work-item-template-check.sh
bash scripts/install-workspace-skill.sh --clients claude|codex|both /absolute/path/to/workspace
```

Expected runtime paths chỉ cho selected coordinator clients:

```text
<workspace>/.agents/skills/work-item/SKILL.md
<workspace>/.claude/skills/work-item/SKILL.md
```

Skill có internal `phases/intake.md`, `phases/investigation.md`, `phases/planning.md`, `phases/review.md`; đây không phải các top-level Agent Skills.

Installer yêu cầu workspace có `repos.yaml` + `identity.md`, preflight selected workspace targets trước mutation và chỉ adopt unmanaged target nếu toàn tree giống source. Historical harness-managed user/global `work-item` copies cho selected clients được cleanup **sau** successful workspace install; same-name global entry không có managed marker bị fail closed và không bị xóa.

Không chạy installer bên trong từng repo con và không copy `.agents/.claude` Work Item skill vào repo child. Repo agent chỉ đọc TaskPacket + mounted Work Item/lifecycle docs, không mutate canonical dossier.

Sau install/update, mở fresh QiQi session **từ workspace root** để refresh workspace skill discovery.

`00_WORK_ITEM.md` là current canonical state; numbered lifecycle docs là living semantic state, không append-only history. Requirement change rewrite effective requirements, increment revision và reconcile prior investigation/plan/review theo materiality.

## v27 filename migration

Workspace đã có dossier theo contract cũ cần rename một lần sau khi apply migration v27:

```bash
python3 scripts/migrate-work-item-filenames-v27.py --dry-run
python3 scripts/migrate-work-item-filenames-v27.py
```

Mapping:

```text
WORK_ITEM.md        -> 00_WORK_ITEM.md
intake.md           -> 10_intake.md
investigation.md    -> 20_investigation.md
plan.md             -> 30_plan.md
review.md           -> 40_review.md
report.textile      -> 90_report.textile
```

Helper preflight toàn bộ dossiers trước mutation, reject symlink/non-regular file và reject bất kỳ old/new collision nào. Nếu rename runtime fail, nó rollback các rename đã thực hiện trong run đó. `references/` không đổi.

## Herdr + qiqi_delegate readiness

Unified installer chỉ cài Herdr integrations cho selected execution agents. Manual equivalent:

```bash
herdr integration install claude   # nếu Claude execution được enable
herdr integration install codex    # nếu Codex execution được enable
herdr integration status
uv sync --project mcp/qiqi_delegate
```

Khi `.qiqi/config.local.json` tồn tại, `workspace-check.sh` chỉ yêu cầu `current` cho adapters tương ứng với `execution_agents`. Workspace legacy không có local config giữ behavior cũ và verify mọi adapter được cấu hình trong `instructions/agent-routing.yaml`.

## Repo delegation

TaskPacket vẫn chứa objective/scope/acceptance đầy đủ. Child được đọc exact mounted dossier từ `work_item_path`, bắt đầu ở `00_WORK_ITEM.md`, nhưng không mutate canonical dossier và không chạy Work Item lifecycle thay QiQi.

`instructions/model-routing.md` không phải mandatory startup material. Khi actual delegation bắt đầu, QiQi resolve `.qiqi/config.local.json` nếu có: route chỉ được chọn trong `execution_agents` đã enable và `default_route` là deterministic fallback. Nếu local config không tồn tại, fallback vẫn là `claude-balanced`.

## Verification

Sau khi `repos.yaml` đã được materialize thành repository thực, workspace skill đã cài, Work Item filenames đã ở canonical numbered form và selected Herdr integrations đã cài:

```bash
bash scripts/workspace-check.sh
```

Checker verify repository registry shape, `required_for`/`depends_on`, duplicate/unknown/self dependencies, dependency cycles, relative paths, exact Git roots, duplicate roots, local route config, qiqi_delegate tests và selected Herdr integration readiness. Harness CI dùng `QIQI_TEMPLATE_CHECK=1` chỉ để validate unmaterialized template placeholders mà không giả vờ kiểm machine-local Git roots/Herdr state.
