# Shared Knowledge Template

Template này triển khai **Shared Knowledge Store độc lập với workspace/repository
hiện tại** và user-scoped Knowledge MCP dùng chung cho QiQi, execution agents và
human maintenance.

Knowledge Store là Markdown + Git-friendly filesystem. Agent **không tạo file trực
tiếp**; agent submit semantic knowledge qua MCP. Human có thể sửa/tạo Markdown trực
tiếp nếu tuân schema rồi chạy check/reindex.

## Boundary

```text
Product/workspace Git repos
= live source, test, implementation, topology, execution artifacts

Shared Knowledge Store
= reusable, non-trivial, evidence-backed distilled knowledge

Knowledge MCP
= search/read/write + storage mechanics

Agent / knowledge-distill skill
= semantic query generation + semantic distillation
```

Shared knowledge không phải oracle mạnh hơn live owner source/test. Nếu knowledge
mâu thuẫn source/test hiện tại, live owner evidence thắng; chỉ update shared
knowledge sau khi replacement conclusion được verify.

## Layout

```text
knowledge-template/
├── .gitignore
├── README.md
├── store/
│   ├── INDEX.md
│   ├── global/
│   ├── systems/
│   ├── repos/
│   └── domains/
├── mcp/knowledge/
│   ├── contracts.py
│   ├── core.py
│   ├── server.py
│   ├── pyproject.toml
│   └── tests/
├── scripts/
│   ├── install-user-mcp.sh
│   ├── install-user-skill.sh
│   ├── knowledge-cli.sh
│   ├── knowledge-mcp-server.sh
│   ├── knowledge-template-check.sh
│   └── knowledge.py
└── skills/knowledge-distill/SKILL.md
```

`store/` có thể nằm trong template hoặc trỏ sang Git repository/path riêng khi
installer chạy. MCP chỉ dùng exact `KNOWLEDGE_STORE_ROOT`; **không suy luận store từ
current working directory**.

## Public MCP API

Post-MVP API dùng progressive disclosure với ba tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_write(entries)
```

Không expose list-files, arbitrary read-path, write-path, delete-path hay generic
filesystem tool.

### Nguyên tắc progressive disclosure

```text
knowledge_search(top N)
→ bounded routing decision cards
→ agent chọn 1–2 exact IDs
→ knowledge_read(ids)
→ full semantic content + provenance + revision
```

Search card phải đủ để **chọn** document, nhưng không được thay thế full document.
Agent không dùng search summary/card như evidence đầy đủ cho material implementation,
verification hoặc update khi content/provenance/uncertainty có thể ảnh hưởng quyết định.

`knowledge_search` cố ý **không trả revision**. Vì vậy update bắt buộc full-read
existing knowledge trước khi có `expected_revision`.

## Search contract

Caller hiểu task trước, tạo một số discriminative concepts rồi gọi:

```json
{
  "keywords": [
    "payment retry",
    "transaction commit",
    "idempotency",
    "retry thanh toán"
  ],
  "context": {
    "repo": "checkout",
    "domain": "checkout.payment"
  },
  "limit": 10
}
```

`context.repo` và `context.domain` **chỉ boost ranking**. Chúng không giới hạn
namespace được đọc và không tự tạo relevance khi không có semantic match.

Search deterministic, index-first và ưu tiên:

1. exact knowledge ID;
2. `canonical_name`;
3. routing `keywords`;
4. multilingual/project `aliases`;
5. `when_to_read`;
6. `summary`.

`title`, scope và physical path không tự tạo relevance. Context chỉ boost entry đã
có semantic match. MCP không dùng embedding, vector DB, translator hoặc LLM.

Mỗi search hit chỉ trả bounded decision card:

```json
{
  "id": "domain:checkout.payment:retry-after-commit",
  "title": "Quy tắc retry thanh toán sau commit",
  "scope": {"kind": "domain", "id": "checkout.payment"},
  "summary": "Do not retry payment after confirmed commit.",
  "when_to_read": [
    "modifying payment retry behavior",
    "investigating duplicate payment"
  ],
  "matches": [
    {"query": "payment retry", "field": "keyword"}
  ],
  "score": 110
}
```

Search card **không trả**:

- `content`;
- `sources`;
- `revision`;
- physical `path`;
- `canonical_name` duplicate ngoài stable ID.

`limit` là maximum candidate cards, không phải số full documents cần hydrate.
Search response cũng không echo lại input `keywords`/`context`.

Mặc dù search không serialize detail content, selected top hits vẫn được load để
verify ID + revision với generated index. Human sửa detail nhưng chưa reindex vẫn
làm search fail rõ thay vì silently dùng stale routing metadata.

## Full read contract

Sau search, hydrate chỉ exact IDs thực sự cần:

```json
{
  "ids": [
    "domain:checkout.payment:retry-after-commit"
  ]
}
```

Mỗi call hydrate tối đa **2 unique IDs**. Nếu hai candidate gần nhau, read cả hai;
không hydrate toàn bộ top-N chỉ vì search `limit` lớn.

Full read trả semantic payload có thể dùng an toàn cho reasoning/update:

- stable `id`;
- SHA-256 `revision`;
- `canonical_name`;
- title + scope;
- full nested `routing`;
- provenance `sources`;
- semantic `content`.

`content` **không chứa canonical H1** vì title là field riêng và writer tự render H1.
Điều này cho phép read → modify → write round-trip mà không tạo duplicate heading.

Physical `path` không thuộc read API. Caller không cần biết filesystem layout.

Nếu exact ID không tồn tại, read fail rõ và caller phải search lại. Nếu detail bị
human sửa nhưng index revision chưa reindex, read fail stale-index rõ.

## Write contract

Agent **không truyền filename, path, directory hoặc INDEX path**.

Create payload:

```yaml
canonical_name: retry-after-commit
title: Quy tắc retry thanh toán sau commit
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
    - không retry sau commit
content: |
  Nội dung có thể viết tiếng Việt, English hoặc mixed.
sources:
  - kind: repo
    locator: checkout:src/payment/retry.ts
    ref: 8f31abc
```

MCP derive:

```text
id   = domain:checkout.payment:retry-after-commit
path = domains/checkout/payment/retry-after-commit.md
```

MCP tự tạo parent directories, render canonical Markdown, write atomically và
regenerate `INDEX.md`.

### Update

Update phải search existing concept, full-read exact target, rồi dùng exact identity
+ optimistic revision từ `knowledge_read`:

```yaml
id: domain:checkout.payment:retry-after-commit
expected_revision: <sha256 returned by knowledge_read>
canonical_name: retry-after-commit
...
```

Full read trả toàn bộ `routing`/`sources`/`content` để caller không phải reconstruct
metadata từ search card. Stale revision bị reject; không last-write-wins.

### Empty review

Knowledge review cuối work không có durable candidate vẫn có thể gọi:

```json
{"entries": []}
```

Tool trả `reviewed: true` và không mutate store khi policy thật sự yêu cầu review.
Không dùng empty write như ceremony cho task trivial được phép skip review.

## Identity, scope và canonical path

Identity không phải filesystem path:

```text
<scope-kind>:<scope-id>:<canonical-name>
```

Supported scopes:

```text
global
system
repo
domain
```

Examples:

```text
global:engineering:deployment-conventions
system:checkout-order:event-compatibility
repo:checkout:repository-runtime-notes
domain:checkout.payment:retry-after-commit
```

Canonical mapping:

```text
global:<id>:<name> → global/<id>/<name>.md
system:<id>:<name> → systems/<id>/<name>.md
repo:<id>:<name>   → repos/<id>/<name>.md
domain:a.b:<name>  → domains/a/b/<name>.md
```

`canonical_name` dùng lowercase kebab-case. `scope.id` chỉ dùng lowercase
letters/numbers với `.` hoặc `-`; slash/path traversal không hợp lệ. Resolved
physical path phải nằm trong store root, kể cả khi namespace parent là symlink.

## Language policy

**Không có field `language`.**

```text
canonical_name
routing.summary
routing.when_to_read
routing.keywords
→ canonical terminology, ưu tiên English

routing.aliases
→ multilingual aliases, legacy names, acronyms, project terms

content
→ tự do: Vietnamese / English / mixed
```

Retrieval không phụ thuộc ngôn ngữ của body.

## Provenance

`sources` bắt buộc. Mỗi source:

```yaml
kind: repo | document | decision | manual | url
locator: <stable locator>
ref: <optional revision/version>
note: <optional context>
```

Unverified guess/hypothesis không được persist như durable fact. Human-authored
curated knowledge có thể dùng `manual` hoặc `decision` khi phù hợp.

## Human-authored documents

Human có thể trực tiếp tạo/sửa detail Markdown. Detail file là canonical metadata
source; `INDEX.md` là generated routing projection.

```md
---
version: 1
id: domain:checkout.payment:retry-after-commit
canonical_name: retry-after-commit
title: Quy tắc retry thanh toán sau commit
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
  - kind: manual
    locator: architecture review 2026-08-19
---

# Quy tắc retry thanh toán sau commit

Content tự do.
```

Maintenance dùng đúng Python runtime đã `uv sync` cho Knowledge MCP:

```bash
bash scripts/knowledge-cli.sh check --root /path/to/store
bash scripts/knowledge-cli.sh reindex --root /path/to/store
bash scripts/knowledge-cli.sh check --root /path/to/store
```

Wrong canonical path, duplicate ID, malformed metadata hoặc stale index làm checker
fail; tooling không silently move human file.

## Integrity model

- filesystem lock cho cross-process write/reindex;
- optimistic `expected_revision` cho update;
- revision check lại ngay trước replace;
- `resolve()` + root containment chống path/symlink escape;
- temp-file + `fsync` + `os.replace` cho detail/index;
- batch validate trước mutation;
- in-process rollback detail/index khi exception;
- crash giữa detail write và index update có thể để index stale; detail metadata
  vẫn canonical và `knowledge reindex` repair;
- search verify revision của selected top hits với index mà không serialize body;
- exact read verify revision trước khi trả full content;
- document/content/search-result/full-read counts đều bounded.

Human direct edit không bị ép lấy MCP lock; optimistic revision + stale-index check
chống silent overwrite đối với concurrent agent update đã được quan sát qua revision.
Human và MCP ghi đúng cùng document ở đúng khoảnh khắc cuối vẫn là external writer
race; nếu cần strict serialization cho manual edits thì human workflow phải tránh
edit đồng thời với active MCP write.

## Context-budget model

`MAX_CONTENT_CHARS` vẫn bảo vệ từng detail document, nhưng search không còn scale
context theo `limit × full document size`.

```text
knowledge_search(limit=10)
→ tối đa 10 bounded cards

knowledge_read(ids)
→ tối đa 2 full documents/call
```

Do đó context tăng theo số document agent **chủ động chọn để đọc**, không theo số
candidate cần xem để route.

## Maintenance CLI

Sau khi đã `uv sync --project mcp/knowledge`, dùng stable launcher:

```bash
bash scripts/knowledge-cli.sh init --root /path/to/store
bash scripts/knowledge-cli.sh check --root /path/to/store
bash scripts/knowledge-cli.sh reindex --root /path/to/store
```

`knowledge.py` là implementation Python của CLI; `knowledge-cli.sh` chọn
`mcp/knowledge/.venv/bin/python` để không phụ thuộc Python packages global.

## Offline template checker

Checker không tự download dependencies. Nó ưu tiên synced project `.venv` nếu có,
fallback current Python khi environment đã có `filelock` + `PyYAML` + `pydantic` +
`mcp`; sau đó compile source, chạy unit/server-contract tests và check template store:

```bash
bash scripts/knowledge-template-check.sh
```

Checker xác minh ba public tools, thin search schema, bounded exact read, write schema
và integrity behavior. Nó không khóa implementation vào một tool-description prose
quá dài.

## User/global MCP installation

Installer yêu cầu `uv`, sync MCP runtime dependencies, initialize store, cài
`knowledge-distill` skill, tạo stable wrapper và đăng ký server tên `knowledge` với
available clients:

```bash
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

- Codex: `codex mcp add knowledge -- <stable-wrapper>`;
- Claude Code: `claude mcp add knowledge --scope user <stable-wrapper>`;
- existing registration cùng tên nhưng không trỏ stable wrapper làm installer fail
  thay vì overwrite user configuration;
- rerun với cùng wrapper là idempotent.

Mở fresh agent session sau installation. Nếu repo/project tự định nghĩa MCP tên
`knowledge`, nó có thể shadow user/global registration; setup smoke test phải bắt
conflict này.

## Runtime validation

Sau `uv sync --project mcp/knowledge`:

```bash
mcp/knowledge/.venv/bin/python -m unittest discover -s mcp/knowledge/tests -v
bash scripts/knowledge-template-check.sh
```

Fresh-session acceptance cần xác minh QiQi và Herdr-launched Codex/Claude child thực
sự thấy đủ:

```text
knowledge_search
knowledge_read
knowledge_write
```

Local config edit không làm tool xuất hiện trong session đã chạy sẵn.
