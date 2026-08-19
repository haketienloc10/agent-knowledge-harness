# Shared Knowledge Template

Template này triển khai **Shared Knowledge Store độc lập với workspace/repository
hiện tại** và một user-scoped MCP dùng chung cho QiQi, Codex/Claude execution
agents và human maintenance.

Knowledge Store là Markdown + Git-friendly filesystem. Agent **không tạo file trực
tiếp**; agent submit semantic knowledge qua MCP. Human có thể sửa/tạo Markdown trực
tiếp nếu tuân thủ schema rồi chạy check/reindex.

## Boundary

```text
Product/workspace Git repos
= live source, test, implementation, topology, execution artifacts

Shared Knowledge Store
= reusable, non-trivial, evidence-backed distilled knowledge

Knowledge MCP
= retrieval + storage mechanics

Agent / knowledge-distill skill
= semantic query generation + semantic distillation
```

Shared knowledge không phải oracle mạnh hơn live owner source/test. Nếu agent đang
làm trong owner repo và knowledge mâu thuẫn source/test hiện tại, source/test hiện
tại thắng; chỉ update shared knowledge sau khi kết luận mới được verify.

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
│   ├── core.py
│   ├── server.py
│   ├── pyproject.toml
│   └── tests/test_core.py
├── scripts/
│   ├── install-user-mcp.sh
│   ├── knowledge-cli.sh
│   ├── knowledge-mcp-server.sh
│   ├── knowledge-template-check.sh
│   └── knowledge.py
└── skills/knowledge-distill/SKILL.md
```

`store/` có thể nằm trong template hoặc trỏ sang Git repository/path riêng khi
installer chạy. MCP chỉ dùng exact `KNOWLEDGE_STORE_ROOT`; **không suy luận store
từ current working directory**.

## Public MCP API

MVP expose đúng hai tools:

```text
knowledge_read(keywords, context?, limit?)
knowledge_write(entries)
```

Không expose list-files, arbitrary read-path, write-path, delete-path hay generic
filesystem tool.

## Read contract

Caller hiểu task trước, tự sinh nhiều search terms rồi gọi:

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
  "limit": 5
}
```

`context.repo` và `context.domain` **chỉ boost ranking**. Chúng không giới hạn
namespace được đọc.

Retrieval deterministic, index-first và ưu tiên:

1. exact knowledge ID;
2. `canonical_name`;
3. routing `keywords`;
4. multilingual/project `aliases`;
5. `when_to_read`;
6. `summary`;
7. title/scope/path.

MCP không dùng embedding, vector DB, translator hoặc LLM.

`knowledge_read` trả selected content cùng:

- stable `id`;
- canonical `path`;
- SHA-256 `revision`;
- scope/summary;
- matched query terms + match reason;
- provenance sources.

Khi selected detail file đã bị human sửa nhưng index revision chưa reindex, read
fail rõ thay vì silently dùng stale document.

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

Update phải dùng exact identity + optimistic revision từ `knowledge_read`:

```yaml
id: domain:checkout.payment:retry-after-commit
expected_revision: <sha256 returned by knowledge_read>
canonical_name: retry-after-commit
...
```

Stale revision bị reject; không last-write-wins.

### Empty review

Knowledge review cuối work không có durable candidate vẫn gọi:

```json
{"entries": []}
```

Tool trả `reviewed: true` và không mutate store.

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
- read verify revision của selected detail với index;
- document/content/result counts bounded.

Human direct edit không bị ép lấy MCP lock; optimistic revision + stale-index check
chống silent overwrite đối với concurrent agent update đã được quan sát qua revision.
Human và MCP ghi đúng cùng document ở đúng khoảnh khắc cuối vẫn là external writer
race; nếu cần strict serialization cho manual edits thì human workflow phải tránh
edit đồng thời với active MCP write.

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
fallback current Python khi environment đã có `filelock` + `PyYAML`; sau đó compile
source, chạy unit tests và check template store:

```bash
bash scripts/knowledge-template-check.sh
```

Nếu chưa có runtime dependencies, checker fail rõ và yêu cầu `uv sync`; network
setup không phải side effect ngầm của checker.

## User/global MCP installation

Installer yêu cầu `uv`, sync MCP runtime dependencies, initialize store, tạo stable
wrapper và đăng ký server tên `knowledge` với available clients:

```bash
bash scripts/install-user-mcp.sh --store-root /path/to/shared-knowledge/store
```

- Codex: `codex mcp add knowledge -- <stable-wrapper>`; current CLI writes its
  normal/global config unless user has separately configured project override.
- Claude Code: `claude mcp add knowledge --scope user <stable-wrapper>`.
- Nếu registration `knowledge` đã tồn tại và output không trỏ tới stable wrapper,
  installer **fail** thay vì overwrite user configuration.
- Rerun installer với cùng stable wrapper là idempotent; wrapper có thể được updated
  để trỏ store root mới.

Mở fresh agent session sau installation. Nếu một repo/project tự định nghĩa MCP tên
`knowledge`, nó có thể shadow user/global registration; repo/workspace templates cố
ý không tạo project knowledge config và setup smoke test phải bắt conflict này.

## Runtime validation

Sau `uv sync --project mcp/knowledge`, có thể kiểm MCP runtime import/launch riêng.
Unit tests core:

```bash
mcp/knowledge/.venv/bin/python -m unittest discover -s mcp/knowledge/tests -v
```

Fresh-session acceptance cần xác minh cả QiQi và Herdr-launched Codex/Claude child
thực sự thấy `knowledge_read` / `knowledge_write`; local config edit không làm tool
xuất hiện trong session đã chạy sẵn.
