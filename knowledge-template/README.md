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
= progressive search/read + whole/partial mutation + storage mechanics

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
│   ├── partial_contracts.py
│   ├── partial_update.py
│   ├── sections.py
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

Progressive API có sáu tools:

```text
knowledge_search(keywords, context?, limit?)
knowledge_read(ids)
knowledge_read_metadata(ids)
knowledge_read_section(id, section_id)
knowledge_write(entries)
knowledge_update(id, expected_revision, changes)
```

Ba API cũ `knowledge_search`, `knowledge_read`, `knowledge_write` giữ nguyên contract.
`knowledge_write` vẫn hỗ trợ create và full-document replacement để backward-compatible;
partial mutation là surface bổ sung, không thay storage model.

Không expose list-files, arbitrary read-path, write-path, delete-path hay generic
filesystem tool.

### Nguyên tắc progressive disclosure

```text
knowledge_search(top N)
→ bounded routing decision cards
→ agent chọn exact target
→ đọc smallest sufficient semantic scope:
     full document | metadata + section index | one section
→ mutate smallest safe semantic scope
```

Search card phải đủ để **chọn** document, nhưng không được thay thế exact read.
Agent không dùng search summary/card như evidence đầy đủ cho material implementation,
verification hoặc update khi content/provenance/uncertainty có thể ảnh hưởng quyết định.

`knowledge_search` cố ý **không trả revision**. Existing-target mutation phải lấy exact
SHA-256 revision từ một exact read surface: full read, metadata read hoặc section read.

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

## Exact read contracts

### Full document

Khi conclusion cần toàn concept, hydrate exact IDs:

```json
{
  "ids": [
    "domain:checkout.payment:retry-after-commit"
  ]
}
```

Mỗi `knowledge_read` call hydrate tối đa **2 unique IDs**. Full read trả:

- stable `id`;
- SHA-256 `revision`;
- `canonical_name`;
- title + scope;
- full nested `routing`;
- provenance `sources`;
- semantic `content`.

`content` **không chứa canonical H1** vì title là field riêng và writer tự render H1.
Physical `path` không thuộc read API.

### Metadata-only

Khi chỉ sửa title/routing/sources hoặc cần biết section nào tồn tại mà không hydrate
large content:

```json
{
  "ids": ["domain:checkout.payment:retry-after-commit"]
}
```

qua `knowledge_read_metadata` trả exact identity/revision + title/scope/routing/sources
và thin section index:

```json
{
  "sections": [
    {"id": "contract", "heading": "## Contract"},
    {"id": "verification", "heading": "## Verification"}
  ]
}
```

Nó **không trả `content`**. Server có thể đọc canonical file nội bộ để verify/derive
section index; mục tiêu của API này là không đưa whole content vào agent context/payload.

### One semantic section

Khi chỉ cần một existing marked section:

```text
knowledge_read_section(
  id="domain:checkout.payment:retry-after-commit",
  section_id="verification"
)
```

trả:

```text
id
revision              # whole-document SHA-256 revision
section_id
heading                # exact stored H2-H6 heading
content                # section body only
```

Section read không trả whole document. Missing section fail rõ; caller phải dùng exact
section ID đã quan sát từ canonical document/metadata read, không invent ID.

Nếu exact document ID không tồn tại, read fail rõ và caller phải search lại. Nếu detail
bị human sửa nhưng index revision chưa reindex, exact read fail stale-index rõ.

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

### Full-document update compatibility

Existing `knowledge_write` update vẫn hợp lệ:

```yaml
id: domain:checkout.payment:retry-after-commit
expected_revision: <sha256 returned by knowledge_read>
canonical_name: retry-after-commit
...
```

Đây là whole semantic document replacement. Dùng khi toàn concept cần re-distill hoặc
caller intentionally muốn replace toàn metadata/content. Stale revision bị reject;
không last-write-wins.

### Partial update

`knowledge_update` nhận exact `id`, whole-document `expected_revision` và typed `changes`.
Caller không resend phần không đổi; MCP hydrate current canonical document server-side,
apply patch rồi delegate persistence lại chính whole-document write path hiện có.
Do đó lock, atomic replace, rollback, index refresh và revision checks không có
implementation thứ hai.

Metadata-only:

```yaml
id: domain:checkout.payment:retry-after-commit
expected_revision: <sha256 from exact read>
changes:
  metadata:
    routing:
      summary: Updated durable routing boundary.
      keywords:
        - payment
        - retry
        - commit
```

Whole content only:

```yaml
changes:
  content: |
    Replacement durable content body.
```

One section body:

```yaml
changes:
  section:
    id: verification
    content: |
      Run focused verification first, then the full suite.
```

Rules:

- metadata patch chỉ cho `title`, partial nested `routing`, hoặc full intended `sources`;
- `canonical_name`/`scope` không patch được nên identity/path không đổi âm thầm;
- metadata có thể combine atomically với whole-content **hoặc** one-section mutation;
- whole-content và one-section replacement mutually exclusive trong cùng call;
- omitted field = unchanged; explicit `null` bị reject, không có merge-patch deletion;
- partial update vẫn tạo một SHA-256 revision mới cho **whole document**;
- không có metadata revision hoặc per-section revision riêng;
- revision conflict → exact reread → reconcile → retry.

## Stable semantic sections

Large structured knowledge có thể opt-in stable sections trong cùng content body:

```markdown
<!-- knowledge-section:contract -->
## Contract

Durable contract text.

<!-- knowledge-section:failure-modes -->
## Failure modes

Durable failure-mode text.
```

Contract:

- section ID lowercase kebab-case, unique trong document;
- marker là exact standalone line, không indent;
- marker phải immediately followed bởi Markdown H2-H6 heading;
- heading là presentation; marker ID là stable semantic identity;
- section boundary là marker-to-marker, không dựa vào heading level;
- tối đa 100 marked sections/document;
- small/legacy knowledge không có marker vẫn hợp lệ;
- section replacement chỉ thay body, giữ marker + heading;
- replacement body không được inject `knowledge-section` marker;
- missing section không implicit create;
- API hiện không có section add/delete/reorder/rename primitive.

Nếu cần structural rewrite, full-read rồi whole-content replacement. Section markers
chỉ là mutation address trong một document; storage vẫn **one Markdown document = one
semantic concept = one whole-document revision**.

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

<!-- knowledge-section:contract -->
## Contract

Content tự do.
```

Nếu human dùng reserved `knowledge-section` marker thì phải tuân marker contract ở
trên. MCP read/write/update surfaces reject malformed reserved marker thay vì đoán
section structure.

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
- optimistic whole-document `expected_revision` cho full/partial update;
- revision check lại ngay trước replace;
- partial adapter reconstruct full semantic payload **server-side** rồi reuse existing
  `write_knowledge` transaction path;
- `resolve()` + root containment chống path/symlink escape;
- temp-file + `fsync` + `os.replace` cho detail/index;
- batch validate trước mutation;
- in-process rollback detail/index khi exception;
- crash giữa detail write và index update có thể để index stale; detail metadata
  vẫn canonical và `knowledge reindex` repair;
- search verify revision của selected top hits với index mà không serialize body;
- exact reads verify revision trước khi trả requested semantic scope;
- section replacement không implicit create section hoặc inject new markers;
- document/content/search-result/full-read counts đều bounded.

Human direct edit không bị ép lấy MCP lock; optimistic revision + stale-index check
chống silent overwrite đối với concurrent agent update đã được quan sát qua revision.
Human và MCP ghi đúng cùng document ở đúng khoảnh khắc cuối vẫn là external writer
race; nếu cần strict serialization cho manual edits thì human workflow phải tránh
edit đồng thời với active MCP write.

## Context-budget model

`MAX_CONTENT_CHARS` vẫn bảo vệ từng detail document, nhưng search và scoped read không
scale context theo `limit × full document size`.

```text
knowledge_search(limit=10)
→ tối đa 10 bounded cards

knowledge_read(ids)
→ tối đa 2 full documents/call

knowledge_read_metadata(ids)
→ exact metadata/provenance/revision + thin section index; no content

knowledge_read_section(id, section_id)
→ one section body + whole-document revision

knowledge_update(...)
→ request chỉ chứa changed semantic scope
```

Do đó large Knowledge không bắt agent resend whole document khi chỉ đổi metadata,
whole content riêng, hoặc một marked section.

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

Checker xác minh sáu public tools, thin search schema, bounded exact/scoped reads,
typed full/partial mutation, stable section parser và existing storage integrity
behavior. Nó khóa partial update vào existing whole-document concurrency/transaction
path thay vì cho tạo persistence model thứ hai.

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
knowledge_read_metadata
knowledge_read_section
knowledge_write
knowledge_update
```

Local config edit không làm tool xuất hiện trong session đã chạy sẵn.
