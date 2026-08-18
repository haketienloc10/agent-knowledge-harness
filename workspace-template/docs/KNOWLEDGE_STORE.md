# Shared Knowledge Store

Knowledge Store là kho Markdown dùng chung, **độc lập với repository và current
working directory của agent**. QiQi và execution agent cùng truy cập store qua
Knowledge MCP; source/test trong repository vẫn là live implementation truth.

## Runtime boundary

```text
QiQi / Codex child / Claude child
            ↓
       qiqi_knowledge MCP
            ↓
QIQI_KNOWLEDGE_ROOT (absolute path)
            ↓
INDEX.md + canonical Markdown documents
```

`qiqi_knowledge` là MCP riêng với hai public tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Nó không phụ thuộc `repos.yaml`, workspace root, repository Git root hoặc CWD của
caller. `context.repo` và `context.domain` chỉ là ranking hint, không phải access
boundary.

## Khởi tạo store

Chọn một absolute path ổn định, có thể là Git repository riêng:

```bash
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
uv sync --project mcp/knowledge
bash scripts/qiqi-knowledge-store.sh init
bash scripts/qiqi-knowledge-store.sh check
```

Store rỗng ban đầu chỉ có `INDEX.md`. Documents được materialize theo scope:

```text
INDEX.md
global/<scope...>/<canonical-name>.md
systems/<scope...>/<canonical-name>.md
repos/<scope...>/<canonical-name>.md
domains/<scope...>/<canonical-name>.md
```

Ví dụ:

```text
domain:checkout.payment:retry-after-commit
→ domains/checkout/payment/retry-after-commit.md
```

Knowledge identity không phải filesystem path. ID có format:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

`scope.kind` hiện hỗ trợ `global`, `system`, `repo`, `domain`.

## Đăng ký MCP ở user scope

Knowledge MCP phải available cho cả QiQi tại workspace và child agent được Herdr
launch tại repository root. Vì vậy không đăng ký Knowledge MCP trong project
`.codex/config.toml`; đăng ký nó ở user scope của từng agent CLI.

Từ workspace đã cài template:

```bash
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
launcher="$PWD/scripts/qiqi-knowledge-mcp-server.sh"

codex mcp add qiqi_knowledge \
  --env QIQI_KNOWLEDGE_ROOT="$QIQI_KNOWLEDGE_ROOT" \
  -- bash "$launcher"

claude mcp add qiqi_knowledge --scope user \
  --env QIQI_KNOWLEDGE_ROOT="$QIQI_KNOWLEDGE_ROOT" \
  -- bash "$launcher"
```

Nếu `qiqi_knowledge` đã tồn tại, inspect/remove cấu hình cũ trước rồi add lại với
exact launcher/store root mong muốn.

Xác minh:

```bash
codex mcp get qiqi_knowledge
claude mcp get qiqi_knowledge
```

## Read lifecycle

Đầu mỗi work turn, agent:

1. hiểu concern của task;
2. sinh nhiều search terms liên quan;
3. ưu tiên canonical English concepts, thêm original-language/domain aliases khi
   hữu ích;
4. gọi `knowledge_read` trước investigation.

Ví dụ:

```text
[
  "payment retry",
  "transaction commit",
  "idempotency",
  "retry thanh toán"
]
```

MCP chỉ đọc `INDEX.md` để rank document, sau đó mở exact top matches. Ranking ưu
tiên ID/canonical name, `routing.keywords`, aliases, `when_to_read`, summary và
sau cùng title. Body không phải routing source trong MVP.

Tool trả ID, relative path, document revision, routing metadata, sources, score,
match reason và content.

## Write lifecycle

Trước khi finalize work, agent review xem task vừa xác nhận reusable durable
knowledge nào. Agent gọi `knowledge_write` kể cả khi không có update:

```text
knowledge_write(entries=[])
```

`entries=[]` nghĩa knowledge review đã được thực hiện và không có gì đáng persist.

Agent **submit semantic knowledge, không tạo file**. Không có `filename`, `path`,
`directory` hay `index_path` trong write contract. MCP sở hữu ID validation,
canonical path, `mkdir`, Markdown rendering, locking, atomic file replace và
`INDEX.md` update.

Create entry bỏ `id` và `expected_revision`, nhưng phải có:

```yaml
canonical_name: retry-after-commit
title: Quy tắc retry sau commit
scope:
  kind: domain
  id: checkout.payment
routing:
  summary: Payment must not be retried after a successful transaction commit.
  when_to_read:
    - modifying payment retry behavior
    - changing transaction commit handling
  keywords:
    - payment
    - retry
    - transaction
    - commit
    - idempotency
  aliases:
    - retry thanh toán
content: |
  Nội dung có thể dùng tiếng Việt, English hoặc mixed.
sources:
  - type: repo
    repo: checkout
    path: src/payment/retry.ts
    ref: abc123
```

`canonical_name`, scope ID và routing concepts dùng canonical identifiers/terms.
`routing.summary`, `when_to_read` và `keywords` ưu tiên English để nhiều agent dùng
chung một retrieval vocabulary. `aliases` optional và có thể đa ngôn ngữ.

**Không có field `language`.** Content dùng ngôn ngữ nào cũng được.

Update entry dùng exact `id` và `expected_revision` do `knowledge_read` trả. Scope
và `canonical_name` không được đổi trong update; rename/move không thuộc MVP.
Revision conflict bị reject để tránh agent ghi đè human/agent update mới hơn.

## Canonical Markdown format

MCP render document như sau; human có thể tạo/sửa trực tiếp nếu tuân cùng format:

```markdown
---
version: 1
id: domain:checkout.payment:retry-after-commit
canonical_name: retry-after-commit
title: Quy tắc retry sau commit
scope:
  kind: domain
  id: checkout.payment
routing:
  summary: Payment must not be retried after a successful transaction commit.
  when_to_read:
    - modifying payment retry behavior
  keywords:
    - payment
    - retry
    - idempotency
  aliases:
    - retry thanh toán
sources:
  - type: repo
    repo: checkout
    path: src/payment/retry.ts
    ref: abc123
---

# Quy tắc retry sau commit

Content tự do về ngôn ngữ.
```

Source types hỗ trợ: `repo`, `document`, `decision`, `manual`. Durable knowledge
phải có provenance; finding chưa đủ evidence không được lưu như verified fact.

## Human edit workflow

Human edit là first-class workflow. Store không có hidden database bắt buộc.

Sau khi thêm/sửa metadata hoặc move document ngoài MCP:

```bash
export QIQI_KNOWLEDGE_ROOT=/absolute/path/to/shared-knowledge
bash scripts/qiqi-knowledge-store.sh reindex
bash scripts/qiqi-knowledge-store.sh check
```

`reindex` scan canonical detail documents và regenerate `INDEX.md`. `check` xác
minh front matter, unique ID, canonical ID/path và exact index projection.

Không sửa `INDEX.md` như source of truth. Detail document metadata là canonical;
`INDEX.md` chỉ là materialized read-routing index.

## Source truth và staleness

Shared knowledge là distilled reusable context, không thay live owner-repository
source/test. Nếu agent đang làm owner repo và knowledge mâu thuẫn source/test đã
xác minh, source/test thắng. Agent phải dùng evidence mới để cập nhật shared
knowledge trước khi finalize hoặc báo rõ persistence blocker.

QiQi vẫn broker execution/live result giữa repositories. Knowledge MCP chỉ broker
durable reusable knowledge; việc repo agent đọc shared knowledge không cho phép nó
mở sibling repository source hoặc sibling `.qiqi/runs` artifact.
