# System Map

Tệp này chỉ mô tả **semantic contract và boundary liên repository** mà `repos.yaml`
không thể suy ra. `repos.yaml` là canonical repository registry cho workspace name,
repository name, Git-root path, role, workflow membership (`required_for`) và dependency
basics (`depends_on`).

Không lặp full repository list, Git-root path, role hoặc dependency registry trong file
này. Khi chỉ cần chọn repository hoặc dependency wave, dùng `repos.yaml` mà không đọc
`SYSTEM_MAP.md`.

## Hạ tầng và Tích hợp Dùng chung

- Hạ tầng dùng chung: `{{SHARED_INFRASTRUCTURE}}`
- Command integration chính: `{{INTEGRATION_COMMAND}}`

Chỉ ghi facts ở đây khi chúng là shared-infrastructure/integration semantics, không phải
một repository registry khác.

## Contract Liên Repository

| Contract | Producer | Consumers | Kiểu | Compatibility rule | Source of truth |
|---|---|---|---|---|---|
| `{{CONTRACT_NAME}}` | `{{PRODUCER}}` | `{{CONSUMERS}}` | `HTTP / event / schema` | `{{COMPATIBILITY_RULE}}` | `{{SPEC_OR_CODE_PATH}}` |

Bảng này giữ producer–consumer semantics và link tới live owner source. Durable reusable
conclusion về contract/flow có thể được distill vào **Shared Knowledge Store** qua
Knowledge MCP, nhưng không được dùng để thay thế live source-of-truth link tại đây.

## Ranh giới Dữ liệu và Ownership

| Dữ liệu hoặc resource | Owner | Consumer được phép | Cách truy cập |
|---|---|---|---|
| `{{RESOURCE}}` | `{{OWNER_MODULE}}` | `{{ALLOWED_CONSUMERS}}` | `{{API_EVENT_OR_READ_MODEL}}` |

Không truy cập trực tiếp database, bảng, queue hoặc internal endpoint của repo khác
trừ khi bảng này cho phép rõ ràng.

## Luồng Tích hợp Không Suy ra từ Registry

Chỉ thêm row khi `depends_on` không đủ để xác định behavior hoặc sequencing. Nếu không có
flow đặc biệt thì để bảng trống.

| Flow | Trigger | Order/constraint | Source of truth |
|---|---|---|---|

## Kiểm thử Integration

| Kiểm tra | Repository liên quan | Command | Điều kiện trước khi chạy |
|---|---|---|---|
| `{{SMOKE_OR_CONTRACT_CHECK}}` | `{{AFFECTED_MODULES}}` | `{{COMMAND}}` | `{{DEPENDENCIES}}` |

## Thay đổi Breaking và Rollback

- Owner của contract: `{{CONTRACT_OWNER_OR_TEAM}}`
- Quy trình deprecation: `{{DEPRECATION_POLICY}}`
- Điều kiện xóa contract cũ: `{{REMOVAL_CONDITION}}`
- Rollback: `{{ROLLBACK_APPROACH}}`
